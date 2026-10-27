#!/usr/bin/env python3
"""Этап N2, шаг 1б: список лекарств с изменениями Boxed Warning + даты именно BW-дополнений.

Вход: evidence/srlc_bw_list_2016_2026.json (569 строк формы «Date Search», раздел BW) и
evidence/srlc_bw_details.json (детальные страницы SrLC, разобранные в браузере: по DrugNameID —
записи {date, suppl, sections[], bw_new}). Выход: evidence/srlc_bw_list_dated.json в формате строк
для fetch_srlc_dailymed.py: supplement_date = дата ПОСЛЕДНЕГО дополнения с разделом Boxed Warning
(в окне 2016–2026), плюс все BW-дополнения списком и признак «Newly added».
Строки без единого BW-дополнения в деталях (разбор не нашёл) — отдельным списком `unresolved`.

Запуск:  .venv/bin/python build_bw_dated_list.py
"""
from __future__ import annotations

import datetime as dt
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence"


def mdy(s: str) -> dt.date:
    return dt.datetime.strptime(s, "%m/%d/%Y").date()


def main() -> int:
    rows = json.loads((EVIDENCE / "srlc_bw_list_2016_2026.json").read_text(encoding="utf-8"))["rows"]
    details = json.loads((EVIDENCE / "srlc_bw_details.json").read_text(encoding="utf-8"))["details"]
    out, unresolved, newly = [], [], 0
    for r in rows:
        d = details.get(r["drug_name_id"])
        bw = [e for e in (d or {}).get("entries", []) if "Boxed Warning" in e["sections"] and mdy(e["date"]).year >= 2016]
        if not bw:
            unresolved.append({**r, "detail_status": (d or {}).get("status"), "entries": len((d or {}).get("entries", []))})
            continue
        bw.sort(key=lambda e: mdy(e["date"]))
        latest = bw[-1]
        newly += any(e["bw_new"] for e in bw)
        out.append({
            "drug_name": r["drug_name"], "active_ingredient": r["active_ingredient"],
            "application_number": r["application_number"], "application_type": r["application_type"],
            "supplement_date": latest["date"], "supplement": latest["suppl"], "boxed_warning_newly_added": latest["bw_new"],
            "bw_supplements": [{"date": e["date"], "suppl": e["suppl"], "newly_added": e["bw_new"], "sections": e["sections"]} for e in bw],
            "latest_supplement_date_any_section": r["latest_supplement_date_any_section"],
            "database_updated": r["database_updated"], "drug_name_id": r["drug_name_id"],
        })
    years = Counter(r["supplement_date"][-4:] for r in out)
    multi = sum(1 for r in out if len(r["bw_supplements"]) > 1)
    same_as_latest = sum(1 for r in out if r["supplement_date"] == r["latest_supplement_date_any_section"])
    summary = {"rows": len(out), "applications": len({r['application_type'] + r['application_number'] for r in out}),
               "unresolved": len(unresolved), "with_newly_added_bw": newly, "with_several_bw_supplements": multi,
               "bw_supplement_equals_latest_any": same_as_latest, "by_year_of_latest_bw_supplement": dict(sorted(years.items())),
               "generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    (EVIDENCE / "srlc_bw_list_dated.json").write_text(json.dumps({"summary": summary, "rows": out, "unresolved": unresolved}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
