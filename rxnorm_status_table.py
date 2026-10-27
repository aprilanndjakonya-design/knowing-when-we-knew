#!/usr/bin/env python3
"""Этап N2, пункт 6: статусы кодов RxNorm у продуктов, привязанных к этикеткам.

Вход: evidence/setid_rxcui.json (set id → RxCUI, RxNav rxcui.json?idtype=SPL_SET_ID) и evidence/rxcui_history.json
(RxNav historystatus: status Active/Obsolete/Remapped/Quantified/NotCurrent, activeStartDate MMYYYY, activeEndDate,
remappedDate), плюс evidence/synthea_rxcui_ingredients.json (коды назначений Synthea).
Считает: статус × тип термина; годы начала действия кода; коды с датой конца / перекодировкой; кодов на набор SPL;
статусы кодов Synthea. Выход: evidence/rxnorm_status_table.{json,md}.  Запуск: .venv/bin/python rxnorm_status_table.py
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


def start_year(s: str | None):
    return int(s[-4:]) if s and len(s) >= 6 and s[-4:].isdigit() else None


def main() -> int:
    hist = json.loads((EVIDENCE / "rxcui_history.json").read_text(encoding="utf-8"))
    setid_rx = json.loads((EVIDENCE / "setid_rxcui.json").read_text(encoding="utf-8"))
    syn = json.loads((EVIDENCE / "synthea_rxcui_ingredients.json").read_text(encoding="utf-8")) if (EVIDENCE / "synthea_rxcui_ingredients.json").exists() else {}
    status_tty = defaultdict(Counter)
    years = Counter()
    ended, remapped = [], []
    for code, h in hist.items():
        status_tty[h.get("status") or "?"][h.get("tty") or "?"] += 1
        y = start_year(h.get("activeStartDate"))
        years["≤2005 (initial RxNorm)" if y and y <= 2005 else ("2006–2015" if y and y <= 2015 else ("2016–2020" if y and y <= 2020 else ("2021–2026" if y else "unknown")))] += 1
        if h.get("activeEndDate"):
            ended.append(code)
        if h.get("remappedDate"):
            remapped.append(code)
    per_set = [len(v.get("rxcuis", [])) for v in setid_rx.values()]
    codes_in_sets = Counter(c for v in setid_rx.values() for c in v.get("rxcuis", []))
    # Коды Synthea, которых нет среди кодов этикеток, — дотягиваем их historystatus (RxNav, те же обвязки, что в шаге 4)
    syn_path = EVIDENCE / "rxcui_history_synthea.json"
    syn_hist = json.loads(syn_path.read_text(encoding="utf-8")) if syn_path.exists() else {}
    missing = [c for c in syn if c not in hist and c not in syn_hist]
    if missing:
        sys.path.insert(0, str(HERE))
        from map_setids_rxcui import Throttle, fetch_json, BASE  # noqa: E402
        throttle = Throttle(4.0)
        for i, c in enumerate(missing, 1):
            h = fetch_json(f"{BASE}/rxcui/{c}/historystatus.json", f"RxNav: history status {c} (Synthea)", throttle)
            st = ((h or {}).get("rxcuiStatusHistory") or {})
            meta, attrs = st.get("metaData", {}) or {}, st.get("attributes", {}) or {}
            syn_hist[c] = {"name": attrs.get("name"), "tty": attrs.get("tty"), "status": meta.get("status"),
                           "activeStartDate": meta.get("activeStartDate"), "activeEndDate": meta.get("activeEndDate"),
                           "remappedDate": (st.get("derivedConcepts") or {}).get("remappedDate")}
            if i % 50 == 0 or i == len(missing):
                syn_path.write_text(json.dumps(syn_hist, indent=1, ensure_ascii=False), encoding="utf-8")
                print(f"Synthea codes: {i}/{len(missing)}", flush=True)
    syn_status = Counter((hist.get(c) or syn_hist.get(c) or {}).get("status") or "not_fetched" for c in syn)
    syn_tty = Counter((hist.get(c) or syn_hist.get(c) or {}).get("tty") or "?" for c in syn)
    syn_ended = [c for c in syn if ((hist.get(c) or syn_hist.get(c) or {}).get("activeEndDate"))]
    res = {"generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "codes": len(hist),
           "status_by_tty": {s: dict(c) for s, c in status_tty.items()}, "status_totals": {s: sum(c.values()) for s, c in status_tty.items()},
           "active_start_year_buckets": dict(years), "codes_with_end_date": len(ended), "codes_remapped": len(remapped),
           "spl_sets": len(setid_rx), "codes_per_set": {"min": min(per_set), "median": statistics.median(per_set), "max": max(per_set)},
           "codes_shared_by_several_sets": sum(1 for c, n in codes_in_sets.items() if n > 1),
           "synthea_codes": len(syn), "synthea_code_status": dict(syn_status), "synthea_code_tty": dict(syn_tty),
           "synthea_codes_with_end_date": syn_ended,
           "method_note": "RxNav historystatus for every RxCUI linked from the DailyMed SPL sets of the Boxed Warning applications; "
                          "activeStartDate 042005 is the first RxNorm release, i.e. the code predates the archive, not the drug.",
           "ontology_note": "Validity interval of a code (activeStartDate–activeEndDate) is NOT asserted in the 0.2 module: it needs a new "
                            "property on iat:DrugProduct in the core (to be agreed in N3); the status is recorded here only."}
    (EVIDENCE / "rxnorm_status_table.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    ttys = sorted({t for c in status_tty.values() for t in c})
    md = ["# RxNorm code status (RxNav historystatus) for products linked to the Boxed Warning labels", "",
          f"Codes: {len(hist)} (from {len(setid_rx)} SPL sets; {res['codes_per_set']['median']} codes per set at the median, max {res['codes_per_set']['max']}; "
          f"{res['codes_shared_by_several_sets']} codes shared by several sets).", "",
          "| Status | " + " | ".join(ttys) + " | total |", "|---|" + "---|" * (len(ttys) + 1)]
    for s, c in status_tty.items():
        md.append(f"| {s} | " + " | ".join(str(c.get(t, 0)) for t in ttys) + f" | {sum(c.values())} |")
    md += ["", "| Code active since | n |", "|---|---|"] + [f"| {k} | {v} |" for k, v in years.most_common()] + [
        "", f"Codes with an end date: {len(ended)}; remapped: {len(remapped)}.", "",
        f"Synthea medication codes: {len(syn)}; status: {dict(syn_status)}; term types: {dict(syn_tty)}; with an end date: {len(syn_ended)}.", "", "Method: " + res["method_note"], "", res["ontology_note"]]
    (EVIDENCE / "rxnorm_status_table.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
