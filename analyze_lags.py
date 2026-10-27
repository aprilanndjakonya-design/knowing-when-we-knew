#!/usr/bin/env python3
"""Этап N2, шаг 3: задержка знания по изменениям Boxed Warning.

Читает evidence/srlc_dailymed/<APP>.json (шаг 2) и считает:
  - задержку DailyMed: дата публикации версии-носителя − дата одобрения дополнения (valid → availability);
  - задержку SrLC: «Database Updated» − дата одобрения (доступность через базу FDA);
  - распределения по годам и корзинам, доли > 7 и > 30 дней, отрицательные случаи списком.
Пишет evidence/lag_report.json и lag_report.md (таблицы для PDF) и lag_hist.svg (гистограмма без зависимостей).

Запуск:  .venv/bin/python analyze_lags.py
"""
from __future__ import annotations

import datetime as dt
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence"
import sys
IN_DIR = EVIDENCE / (sys.argv[1] if len(sys.argv) > 1 else "srlc_dailymed_all")
TAG = IN_DIR.name.replace("srlc_dailymed_", "")
SCOPE = {"bw": "a Boxed Warning change", "all": "any safety-related labeling change (any section)"}.get(TAG, TAG)
BUCKETS = [("<0", lambda d: d < 0), ("0", lambda d: d == 0), ("1–7", lambda d: 1 <= d <= 7), ("8–30", lambda d: 8 <= d <= 30),
           ("31–90", lambda d: 31 <= d <= 90), (">90", lambda d: d > 90)]


def bucket(d: int) -> str:
    return next(name for name, f in BUCKETS if f(d))


def quantile(xs: list[int], p: float):
    if not xs:
        return None
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))]


def describe(xs: list[int]) -> dict:
    return {"n": len(xs), "median": statistics.median(xs) if xs else None, "mean": round(statistics.mean(xs), 1) if xs else None,
            "p25": quantile(xs, 0.25), "p75": quantile(xs, 0.75), "p90": quantile(xs, 0.9), "max": max(xs) if xs else None,
            "share_gt_7": round(sum(1 for x in xs if x > 7) / len(xs), 3) if xs else None,
            "share_gt_30": round(sum(1 for x in xs if x > 30) / len(xs), 3) if xs else None,
            "buckets": {name: sum(1 for x in xs if f(x)) for name, f in BUCKETS}}


def svg_hist(buckets_dm: dict, buckets_srlc: dict, path: Path, scope: str = SCOPE) -> None:
    names = [b[0] for b in BUCKETS]
    w, h, pad = 640, 300, 50
    top = max(max(buckets_dm.values()), max(buckets_srlc.values()), 1)
    bw = (w - 2 * pad) / len(names) / 2.6
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" font-family="Helvetica, Arial" font-size="12">',
             f'<text x="{w/2}" y="20" text-anchor="middle" font-size="14">Delay between FDA approval of {scope} and its availability</text>']
    for i, name in enumerate(names):
        x0 = pad + i * (w - 2 * pad) / len(names)
        for j, (vals, color, label) in enumerate(((buckets_dm, "#2a6f97", "DailyMed publication"), (buckets_srlc, "#e07a5f", "FDA SrLC database update"))):
            v = vals.get(name, 0)
            bh = (h - 2 * pad) * v / top
            x = x0 + j * (bw + 4) + 10
            parts.append(f'<rect x="{x:.1f}" y="{h - pad - bh:.1f}" width="{bw:.1f}" height="{bh:.1f}" fill="{color}"/>')
            parts.append(f'<text x="{x + bw/2:.1f}" y="{h - pad - bh - 4:.1f}" text-anchor="middle" font-size="10">{v}</text>')
        parts.append(f'<text x="{x0 + bw + 12:.1f}" y="{h - pad + 16}" text-anchor="middle">{name}</text>')
    parts.append(f'<text x="{w/2}" y="{h - 12}" text-anchor="middle">days (approval → availability)</text>')
    parts.append(f'<rect x="{pad}" y="34" width="12" height="12" fill="#2a6f97"/><text x="{pad + 16}" y="45">DailyMed publication</text>')
    parts.append(f'<rect x="{pad + 170}" y="34" width="12" height="12" fill="#e07a5f"/><text x="{pad + 186}" y="45">FDA SrLC database update</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def main() -> int:
    apps = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(IN_DIR.glob("*.json"))]
    dm, srlc, neg, by_year_dm, by_year_srlc = [], [], [], defaultdict(list), defaultdict(list)
    no_label, no_carrier, multi = [], [], 0
    for a in apps:
        year = int(a["latest_bw_supplement_date"][:4])
        s = a["lag_days_srlc_database"]
        # «Database Updated» относится к ПОСЛЕДНЕЙ записи лекарства (любой раздел): для BW-прогона задержка SrLC
        # осмысленна только когда BW-дополнение и есть последнее дополнение заявки.
        row0 = a["srlc_rows"][0]
        latest_any = row0.get("latest_supplement_date_any_section")
        srlc_applicable = latest_any is None or (latest_any and dt.datetime.strptime(latest_any, "%m/%d/%Y").date().isoformat() == a["latest_bw_supplement_date"])
        if srlc_applicable:
            srlc.append(s)
            by_year_srlc[year].append(s)
        if a["dailymed_setids"] == 0:
            no_label.append(a["application"])
            continue
        if a["dailymed_setids"] > 1:
            multi += 1
        d = a["lag_days_dailymed_min"]
        if d is None:
            no_carrier.append(a["application"])
            continue
        dm.append(d)
        by_year_dm[year].append(d)
        if srlc_applicable and s < 0:
            neg.append({"application": a["application"], "drug": a["srlc_rows"][0]["drug_name"], "supplement": a["latest_bw_supplement_date"],
                        "database_updated": a["srlc_database_updated"], "lag_srlc": s})
    report = {
        "generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "applications": len(apps), "with_dailymed_label": len(apps) - len(no_label), "no_dailymed_label": len(no_label),
        "no_carrier_version_yet": len(no_carrier), "applications_with_several_setids": multi,
        "lag_dailymed_days": describe(dm), "lag_srlc_database_days": describe(srlc),
        "by_year_dailymed": {y: describe(v) for y, v in sorted(by_year_dm.items())},
        "by_year_srlc": {y: describe(v) for y, v in sorted(by_year_srlc.items())},
        "negative_srlc_lags": neg, "no_dailymed_label_list": no_label, "no_carrier_list": no_carrier,
        "method_note": "carrier version = first DailyMed version published on/after the supplement approval date "
                       "(lower bound of the delay; an unrelated version published in between would shorten it). "
                       "SrLC 'Database Updated' is the last update of the drug's entry: used only where the Boxed Warning "
                       "supplement is the drug's latest supplement (upper bound of availability).",
    }
    (EVIDENCE / f"lag_report_{TAG}.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    d1, d2 = report["lag_dailymed_days"], report["lag_srlc_database_days"]
    md = [f"# Delay between approval of {SCOPE} and its availability", "",
          f"Applications in scope ({TAG}): {len(apps)}; with a DailyMed label: {len(apps) - len(no_label)}; "
          f"carrier version not yet published: {len(no_carrier)}; several set ids: {multi}.", "",
          "| Availability channel | n | median (days) | p25 | p75 | p90 | max | share > 7 d | share > 30 d |", "|---|---|---|---|---|---|---|---|---|",
          f"| DailyMed publication of the carrier label version | {d1['n']} | {d1['median']} | {d1['p25']} | {d1['p75']} | {d1['p90']} | {d1['max']} | {d1['share_gt_7']} | {d1['share_gt_30']} |",
          f"| FDA SrLC database update | {d2['n']} | {d2['median']} | {d2['p25']} | {d2['p75']} | {d2['p90']} | {d2['max']} | {d2['share_gt_7']} | {d2['share_gt_30']} |",
          "", "| Bucket (days) | DailyMed | SrLC |", "|---|---|---|"]
    for name, _ in BUCKETS:
        md.append(f"| {name} | {d1['buckets'][name]} | {d2['buckets'][name]} |")
    md += ["", "| Year of latest BW change | n (DailyMed) | median | p90 | share > 30 d |", "|---|---|---|---|---|"]
    for y, v in sorted(by_year_dm.items()):
        dd = describe(v)
        md.append(f"| {y} | {dd['n']} | {dd['median']} | {dd['p90']} | {dd['share_gt_30']} |")
    md += ["", f"Negative SrLC lags (entry updated before the supplement date): {len(neg)} — see lag_report.json.", "",
           "Method: " + report["method_note"]]
    (EVIDENCE / f"lag_report_{TAG}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    svg_hist(d1["buckets"], d2["buckets"], EVIDENCE / f"lag_hist_{TAG}.svg")
    print("\n".join(md[:12]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
