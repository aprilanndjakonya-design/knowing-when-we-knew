#!/usr/bin/env python3
"""Этап N2, пункт 5: длинный хвост задержек DailyMed и основная таблица 2023–2026.

Для каждой заявки с задержкой DailyMed (evidence/srlc_dailymed_bw/<APP>.json, шаг 2) определяем класс носителя:
  history_gap        — история набора в DailyMed начинается ПОЗЖЕ даты одобрения BW-дополнения: «носитель» — просто
                       первая версия в истории, задержка = разрыв истории (DailyMed хранит версии с 2006 г. и не для
                       всех наборов с первой версии), а не задержка публикации;
  publication_delay  — история начинается до одобрения, носитель = первая версия после него (настоящая задержка;
                       по XML-проверке 40 носителей ~85 % верны, остальные — чужая версия между одобрением и BW).
Таблицы: все годы / 2023–2026 / 2023–2026 без history_gap; хвост > 90 дней по классам; по годам.
Выход: evidence/lag_report_bw_recent.{json,md}.  Запуск: .venv/bin/python analyze_lags_recent.py [srlc_dailymed_bw]
"""
from __future__ import annotations

import datetime as dt
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence"
IN_DIR = EVIDENCE / (sys.argv[1] if len(sys.argv) > 1 else "srlc_dailymed_bw")
RECENT_FROM = 2023
TAIL_DAYS = 90


def quantile(xs: list[int], p: float):
    if not xs:
        return None
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))]


def describe(xs: list[int]) -> dict:
    return {"n": len(xs), "median": statistics.median(xs) if xs else None, "p25": quantile(xs, 0.25), "p75": quantile(xs, 0.75),
            "p90": quantile(xs, 0.9), "max": max(xs) if xs else None,
            "share_gt_7": round(sum(1 for x in xs if x > 7) / len(xs), 3) if xs else None,
            "share_gt_30": round(sum(1 for x in xs if x > 30) / len(xs), 3) if xs else None,
            "share_gt_90": round(sum(1 for x in xs if x > 90) / len(xs), 3) if xs else None}


def main() -> int:
    rows = []
    for p in sorted(IN_DIR.glob("*.json")):
        a = json.loads(p.read_text(encoding="utf-8"))
        d = a.get("lag_days_dailymed_min")
        if a["dailymed_setids"] == 0 or d is None:
            continue
        approval = dt.date.fromisoformat(a["latest_bw_supplement_date"])
        lab = next(l for l in a["labels"] if l.get("carrier_version") and l["lag_days_dailymed"] == d)
        hist_start = min(dt.date.fromisoformat(v["published_date"]) for v in lab["versions"])
        cls = "history_gap" if hist_start > approval else "publication_delay"
        row0 = a["srlc_rows"][0]
        latest_any = row0.get("latest_supplement_date_any_section")
        srlc_ok = latest_any is None or dt.datetime.strptime(latest_any, "%m/%d/%Y").date() == approval
        rows.append({"application": a["application"], "drug": row0["drug_name"], "approval": approval.isoformat(), "year": approval.year,
                     "lag_dailymed": d, "class": cls, "history_start": hist_start.isoformat(), "versions_in_history": len(lab["versions"]),
                     "versions_before_supplement": lab.get("versions_before_supplement"),
                     "lag_srlc": a["lag_days_srlc_database"] if srlc_ok else None})

    def table(sel):
        xs = [r["lag_dailymed"] for r in sel]
        return describe(xs)

    recent = [r for r in rows if r["year"] >= RECENT_FROM]
    pub = [r for r in rows if r["class"] == "publication_delay"]
    recent_pub = [r for r in recent if r["class"] == "publication_delay"]
    tail = [r for r in rows if r["lag_dailymed"] > TAIL_DAYS]
    report = {
        "generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "applications_with_lag": len(rows),
        "classes": dict(Counter(r["class"] for r in rows)),
        "tables": {"all_years_all": table(rows), "all_years_publication_delay": table(pub),
                   "all_years_history_gap": table([r for r in rows if r["class"] == "history_gap"]),
                   f"{RECENT_FROM}_2026_all": table(recent), f"{RECENT_FROM}_2026_publication_delay": table(recent_pub),
                   f"{RECENT_FROM}_2026_history_gap": table([r for r in recent if r["class"] == "history_gap"])},
        "srlc": {"all_years": describe([r["lag_srlc"] for r in rows if r["lag_srlc"] is not None]),
                 f"{RECENT_FROM}_2026": describe([r["lag_srlc"] for r in recent if r["lag_srlc"] is not None])},
        "tail_gt_90": {"n": len(tail), "by_class": dict(Counter(r["class"] for r in tail)),
                       "by_year": {y: dict(c) for y, c in sorted(defaultdict(Counter, {}).items())}},
        "by_year": {}, "rows": rows,
        "method_note": "history_gap: the first DailyMed version of the set is published after the supplement approval, so the "
                       "'carrier' is merely the first archived version and the lag measures the archive gap, not publication delay. "
                       "publication_delay: the set has versions before the approval; the carrier is the first version on/after it.",
    }
    by_year_tail = defaultdict(Counter)
    for r in tail:
        by_year_tail[r["year"]][r["class"]] += 1
    report["tail_gt_90"]["by_year"] = {y: dict(c) for y, c in sorted(by_year_tail.items())}
    by_year = defaultdict(list)
    for r in rows:
        by_year[r["year"]].append(r)
    for y, rs in sorted(by_year.items()):
        rp = [r for r in rs if r["class"] == "publication_delay"]
        report["by_year"][y] = {"n": len(rs), "history_gap": sum(1 for r in rs if r["class"] == "history_gap"),
                                "publication_delay": table(rp)}
    (EVIDENCE / "lag_report_bw_recent.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")

    def line(name, t):
        return f"| {name} | {t['n']} | {t['median']} | {t['p25']} | {t['p75']} | {t['p90']} | {t['max']} | {t['share_gt_7']} | {t['share_gt_30']} | {t['share_gt_90']} |"
    T = report["tables"]
    md = ["# Boxed Warning: approval → DailyMed publication, main table (2023–2026) and the long tail", "",
          f"Applications with a DailyMed lag: {len(rows)}; classes: {report['classes']}.", "",
          "| Subset | n | median (days) | p25 | p75 | p90 | max | > 7 d | > 30 d | > 90 d |", "|---|---|---|---|---|---|---|---|---|---|",
          line("All years, all carriers", T["all_years_all"]), line("All years, publication delay only", T["all_years_publication_delay"]),
          line("All years, history gap only", T["all_years_history_gap"]),
          line(f"**{RECENT_FROM}–2026, all carriers**", T[f"{RECENT_FROM}_2026_all"]),
          line(f"**{RECENT_FROM}–2026, publication delay only (main table)**", T[f"{RECENT_FROM}_2026_publication_delay"]),
          line(f"{RECENT_FROM}–2026, history gap only", T[f"{RECENT_FROM}_2026_history_gap"]),
          "", f"SrLC 'Database Updated' lag (where the BW supplement is the latest entry): all years n={report['srlc']['all_years']['n']}, "
              f"median {report['srlc']['all_years']['median']}; {RECENT_FROM}–2026 n={report['srlc'][f'{RECENT_FROM}_2026']['n']}, "
              f"median {report['srlc'][f'{RECENT_FROM}_2026']['median']}, p90 {report['srlc'][f'{RECENT_FROM}_2026']['p90']}.", "",
          f"Long tail (> {TAIL_DAYS} days): {len(tail)} applications — {report['tail_gt_90']['by_class']}; by year: {report['tail_gt_90']['by_year']}.", "",
          "| Year of BW change | n | history gap | publication delay: n | median | p90 | > 30 d |", "|---|---|---|---|---|---|---|"]
    for y, v in report["by_year"].items():
        t = v["publication_delay"]
        md.append(f"| {y} | {v['n']} | {v['history_gap']} | {t['n']} | {t['median']} | {t['p90']} | {t['share_gt_30']} |")
    md += ["", "Longest publication delays (publication_delay class, > 90 days):", "", "| Application | Drug | Approval | Lag (days) | Versions before supplement |", "|---|---|---|---|---|"]
    for r in sorted([r for r in tail if r["class"] == "publication_delay"], key=lambda r: -r["lag_dailymed"])[:15]:
        md.append(f"| {r['application']} | {r['drug'][:28]} | {r['approval']} | {r['lag_dailymed']} | {r['versions_before_supplement']} |")
    md += ["", "Method: " + report["method_note"]]
    (EVIDENCE / "lag_report_bw_recent.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md[:16]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
