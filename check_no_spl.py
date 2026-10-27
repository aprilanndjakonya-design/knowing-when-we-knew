#!/usr/bin/env python3
"""Этап N2, пункт 4: заявки из списка SrLC (Boxed Warning, 2016–2026), у которых DailyMed по номеру заявки не даёт
ни одной этикетки (evidence/lag_report_bw.json → no_dailymed_label_list, 129 шт.). Почему?

Для каждой заявки — Drugs@FDA через openFDA (api.fda.gov/drug/drugsfda.json, search=application_number:"NDA…"):
статусы продуктов (Prescription / Discontinued / None (Tentative Approval) …), спонсор и есть ли у openFDA свой
spl_set_id (если есть — этикетка существует, а запрос DailyMed по номеру заявки её не нашёл).
Классы: not_in_drugsfda · discontinued (все продукты сняты) · marketed_spl_exists (продаётся, у openFDA есть set id)
· marketed_no_spl_mapping (продаётся, set id нет) · tentative · mixed (часть продуктов снята).
Выход: evidence/no_spl_check.json и .md.  Запуск: .venv/bin/python check_no_spl.py [--rate 0.3]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence"


def fetch(app: str):
    q = urllib.parse.quote(f'application_number:"{app}"')
    req = urllib.request.Request(f"https://api.fda.gov/drug/drugsfda.json?search={q}&limit=5",
                                 headers={"User-Agent": "its-about-time-n2/0.1 (research; contact via repo)"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        return None, ("not_in_drugsfda" if e.code == 404 else f"http_{e.code}")
    except Exception as e:  # noqa: BLE001
        return None, f"error_{type(e).__name__}"


def dailymed_by_name(name: str) -> dict:
    """DailyMed v2: spls.json?drug_name=… — заголовки и set id найденных этикеток (до 5)."""
    q = urllib.parse.quote(name.split("(")[0].strip())
    req = urllib.request.Request(f"https://dailymed.nlm.nih.gov/dailymed/services/v2/spls.json?drug_name={q}&pagesize=5",
                                 headers={"User-Agent": "its-about-time-n2/0.1 (research)"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read().decode("utf-8"))
        return {"total": (d.get("metadata") or {}).get("total_elements"),
                "spls": [{"setid": x.get("setid"), "title": (x.get("title") or "")[:80], "published": x.get("published_date")} for x in d.get("data", [])[:5]]}
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}"}


def classify(rec: dict | None, err: str | None) -> str:
    if err:
        return err
    statuses = [p.get("marketing_status", "") for p in rec.get("products", [])]
    spl = (rec.get("openfda") or {}).get("spl_set_id") or []
    if not statuses:
        return "no_products"
    marketed = [s for s in statuses if s in ("Prescription", "Over-the-counter", "Discontinued") and s != "Discontinued"]
    if all(s == "Discontinued" for s in statuses):
        return "discontinued"
    if all(s.startswith("None") for s in statuses):
        return "tentative"
    if marketed and spl:
        return "marketed_spl_exists"
    if marketed and not spl:
        return "marketed_no_spl_mapping"
    return "mixed"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rate", type=float, default=0.3, help="пауза между запросами, с (лимит openFDA без ключа 240/мин)")
    args = ap.parse_args()
    apps = json.loads((EVIDENCE / "lag_report_bw.json").read_text(encoding="utf-8"))["no_dailymed_label_list"]
    out_path = EVIDENCE / "no_spl_check.json"
    done = json.loads(out_path.read_text(encoding="utf-8"))["applications"] if out_path.exists() else {}
    for i, app in enumerate(apps):
        if app in done and not done[app]["class"].startswith(("http_", "error_")) and not (done[app]["class"] == "marketed_no_spl_mapping" and "dailymed_by_name" not in done[app]):
            continue
        srlc = json.loads((EVIDENCE / "srlc_dailymed_bw" / f"{app}.json").read_text(encoding="utf-8"))
        row = srlc["srlc_rows"][0]
        data, err = fetch(app)
        rec = (data or {}).get("results", [None])[0] if data else None
        prods = rec.get("products", []) if rec else []
        done[app] = {"drug_srlc": row["drug_name"], "bw_supplement": srlc["latest_bw_supplement_date"],
                     "class": classify(rec, err), "sponsor": (rec or {}).get("sponsor_name"),
                     "products": [{"brand": p.get("brand_name"), "status": p.get("marketing_status"), "form": p.get("dosage_form")} for p in prods][:6],
                     "openfda_spl_set_ids": ((rec or {}).get("openfda") or {}).get("spl_set_id", [])[:5],
                     "openfda_brand_names": ((rec or {}).get("openfda") or {}).get("brand_name", [])[:5]}
        if done[app]["class"] == "marketed_no_spl_mapping":
            # вторая проверка: есть ли этикетка в DailyMed по ИМЕНИ (значит, она есть, но под другим номером заявки / без него)
            done[app]["dailymed_by_name"] = dailymed_by_name(row["drug_name"])
            time.sleep(args.rate)
        print(f"{i + 1}/{len(apps)} {app} {row['drug_name'][:28]:28} {done[app]['class']}", flush=True)
        time.sleep(args.rate)
    by_class = Counter(v["class"] for v in done.values())
    by_year = defaultdict(Counter)
    for v in done.values():
        by_year[v["bw_supplement"][:4]][v["class"]] += 1
    res = {"generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "applications_checked": len(done),
           "by_class": dict(by_class), "by_year": {y: dict(c) for y, c in sorted(by_year.items())}, "applications": done,
           "method_note": "Drugs@FDA via openFDA by application number; 'marketed_spl_exists' means openFDA maps the application to "
                          "an SPL set id although the DailyMed v2 query by application_number returned nothing (lookup gap on our side)."}
    out_path.write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    md = ["# Applications with a Boxed Warning change but no DailyMed label by application number", "",
          f"Checked: {len(done)} applications (Drugs@FDA via openFDA, {res['generated_utc'][:10]}).", "",
          "| Class | n |", "|---|---|"] + [f"| {k} | {v} |" for k, v in by_class.most_common()] + [
          "", "| Year of BW change | " + " | ".join(k for k, _ in by_class.most_common()) + " |", "|---|" + "---|" * len(by_class)]
    for y, c in sorted(by_year.items()):
        md.append(f"| {y} | " + " | ".join(str(c.get(k, 0)) for k, _ in by_class.most_common()) + " |")
    md += ["", "Examples (first 12 of each non-discontinued class):", "", "| Application | SrLC drug | BW change | Class | Products (brand: status) | openFDA set ids; DailyMed by name |", "|---|---|---|---|---|---|"]
    shown = Counter()
    for app, v in sorted(done.items(), key=lambda kv: (kv[1]["class"], kv[0])):
        if v["class"] == "discontinued" and shown[v["class"]] >= 6:
            continue
        if shown[v["class"]] >= 12:
            continue
        shown[v["class"]] += 1
        prods = "; ".join(f"{p['brand']}: {p['status']}" for p in v["products"][:3])
        byname = v.get("dailymed_by_name")
        note = f"{len(v['openfda_spl_set_ids'])}" + (f"; DailyMed by name: {byname.get('total')} SPL" if byname else "")
        md.append(f"| {app} | {v['drug_srlc'][:30]} | {v['bw_supplement']} | {v['class']} | {prods[:90]} | {note} |")
    (EVIDENCE / "no_spl_check.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md[:12]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
