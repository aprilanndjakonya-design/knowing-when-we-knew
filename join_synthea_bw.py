#!/usr/bin/env python3
"""Этап N2, шаг 5: назначения Synthea × окна «одобрено, но ещё не опубликовано» по Boxed Warning.

Связка: назначение Synthea (CODE = RxCUI) → действующие вещества (evidence/synthea_rxcui_ingredients.json)
→ записи SrLC по полю ACTIVE INGREDIENT (evidence/srlc_bw_list_dated.json, даты именно BW-дополнений)
→ заявки с историей DailyMed (evidence/srlc_dailymed_bw/<APP>.json).

Агрегация — на уровне ДЕЙСТВУЮЩЕГО ВЕЩЕСТВА, а не пары «назначение × заявка» (иначе опиоид с десятками NDA
считается десятки раз): для вещества берём все его BW-дополнения по всем заявкам и для каждого дополнения —
A = дата одобрения, D = первая публикация версии-носителя в DailyMed по этой заявке. Назначение в дату t попадает в
«окно незнания», если существует дополнение с A ≤ t < D (знание уже одобрено FDA, но текст этикетки ещё не
опубликован в DailyMed); «до одобрения» — если t раньше всех A; «доступно» — если есть дополнение с D ≤ t и нет
открытого окна; «носитель неизвестен» — если для всех дополнений с A ≤ t нет D.
Сопоставление веществ по имени (RxNorm IN/PIN ↔ ACTIVE INGREDIENT SrLC без солей) — допущение, названо в отчёте;
бренд/дженерик не различаются: одобренное для референтного препарата изменение считается знанием о веществе.
Итог — evidence/synthea_bw_join.json и .md (таблица по веществам и список окон для онтологии).

Запуск:  .venv/bin/python join_synthea_bw.py [список] [каталог]
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence"
MEDS = HERE / "synthea" / "medications.csv"
# Окно «одобрено → опубликовано» длиннее этого считаем сомнительным (носитель, вероятно, определён неверно).
WINDOW_CAP_DAYS = 180
SALTS = {"HYDROCHLORIDE", "SODIUM", "POTASSIUM", "ACETATE", "SULFATE", "TARTRATE", "MALEATE", "CITRATE", "MESYLATE",
         "SUCCINATE", "FUMARATE", "BESYLATE", "HYDROBROMIDE", "PHOSPHATE", "CALCIUM", "MAGNESIUM", "BITARTRATE",
         "HYCLATE", "MONOHYDRATE", "DIHYDRATE", "ANHYDROUS", "DISODIUM", "TROMETHAMINE", "ACETONIDE", "PROPIONATE",
         "VALERATE", "DIPROPIONATE", "FUROATE", "XINAFOATE", "TRIHYDRATE", "LACTATE", "GLUCONATE", "BROMIDE",
         "CHLORIDE", "NITRATE", "OXALATE", "PAMOATE", "DECANOATE", "ENANTHATE", "HEMIHYDRATE", "SESQUIHYDRATE",
         "ALFA", "RECOMBINANT", "HUMAN"}


def base_name(s: str) -> str:
    words = [w for w in re.split(r"[\s,]+", s.upper().strip()) if w]
    while words and words[-1] in SALTS:
        words.pop()
    return " ".join(words)


def mdy(s: str) -> dt.date:
    return dt.datetime.strptime(s, "%m/%d/%Y").date()


def main() -> int:
    list_name = sys.argv[1] if len(sys.argv) > 1 else "srlc_bw_list_dated.json"
    in_dir = sys.argv[2] if len(sys.argv) > 2 else "srlc_dailymed_bw"
    ingredients = json.loads((EVIDENCE / "synthea_rxcui_ingredients.json").read_text(encoding="utf-8"))
    rows = json.loads((EVIDENCE / list_name).read_text(encoding="utf-8"))["rows"]
    apps_done = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (EVIDENCE / in_dir).glob("*.json")}

    # вещество → события BW (одобрение, публикация в DailyMed, обновление SrLC) по всем заявкам
    events: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        app = f"{r['application_type']}{r['application_number']}"
        a = apps_done.get(app)
        lab = next((l for l in a["labels"] if l["carrier_version"]), None) if a else None
        D = dt.date.fromisoformat(lab["carrier_version"]["published_date"]) if lab else None
        # Ключ — ВЕСЬ набор действующих веществ продукта: BW комбинации (лизиноприл+ГХТЗ, опиоид+парацетамол)
        # не приписывается компоненту-одиночке.
        key = " + ".join(sorted({base_name(x) for x in r["active_ingredient"].split(";") if base_name(x)}))
        if True:
            b = key
            for e in r["bw_supplements"]:
                A = mdy(e["date"])
                is_latest = e["date"] == r["supplement_date"]
                S = mdy(r["database_updated"]) if (is_latest and r["supplement_date"] == r["latest_supplement_date_any_section"]) else None
                events[b].append({"application": app, "drug": r["drug_name"], "suppl": e["suppl"], "approval": A,
                                  "dailymed": D if is_latest else None, "srlc_updated": S, "newly_added": e["newly_added"],
                                  "fetched": a is not None})

    matched_codes = {}
    for code, info in ingredients.items():
        ins = {base_name(i["name"]) for i in info["ingredients"] if i["tty"] == "IN"}
        key = " + ".join(sorted(ins))
        if key and key in events:
            matched_codes[code] = {"name": info["name"], "ingredients": [key]}

    def classify(t: dt.date, evs: list[dict]):
        approved = [e for e in evs if e["approval"] <= t]
        if not approved:
            return "before_approval", None
        open_windows = [e for e in approved if e["dailymed"] and t < e["dailymed"]]
        plausible = [e for e in open_windows if (e["dailymed"] - e["approval"]).days <= WINDOW_CAP_DAYS]
        if plausible:
            return "approved_not_yet_in_dailymed", min(plausible, key=lambda e: e["approval"])
        if open_windows:
            return "approved_window_doubtful", min(open_windows, key=lambda e: e["approval"])
        if any(e["dailymed"] and e["dailymed"] <= t for e in approved):
            return "available", None
        return "approved_carrier_unknown", None

    counts, per_ing, windows = Counter(), defaultdict(Counter), []
    with MEDS.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            m = matched_codes.get(row["CODE"])
            if not m:
                counts["prescriptions_other_drugs"] += 1
                continue
            t = dt.date.fromisoformat(row["START"][:10])
            counts["prescriptions_bw_drugs"] += 1
            best = None
            for ing in m["ingredients"]:
                pos, ev = classify(t, events[ing])
                per_ing[ing][pos] += 1
                rank = {"approved_not_yet_in_dailymed": 4, "approved_window_doubtful": 3, "approved_carrier_unknown": 2, "available": 1, "before_approval": 0}[pos]
                if best is None or rank > best[0]:
                    best = (rank, pos, ing, ev)
            _, pos, ing, ev = best
            counts[f"rx_{pos}"] += 1
            if pos == "approved_not_yet_in_dailymed":
                windows.append({"patient": row["PATIENT"][:8], "start": t.isoformat(), "code": row["CODE"], "drug": m["name"],
                                "ingredient": ing, "application": ev["application"], "srlc_drug": ev["drug"], "suppl": ev["suppl"],
                                "approval": ev["approval"].isoformat(), "dailymed_available": ev["dailymed"].isoformat(),
                                "srlc_updated": ev["srlc_updated"].isoformat() if ev["srlc_updated"] else None,
                                "newly_added": ev["newly_added"], "window_days": (ev["dailymed"] - ev["approval"]).days,
                                "position_dailymed": pos,
                                "position_srlc": ("approved_not_yet_in_srlc" if ev["srlc_updated"] and t < ev["srlc_updated"] else ("available" if ev["srlc_updated"] else "unknown"))})
    ing_table = []
    for ing, c in sorted(per_ing.items(), key=lambda kv: -sum(kv[1].values())):
        evs = events[ing]
        ing_table.append({"ingredient": ing, "prescriptions": sum(c.values()), **dict(c),
                          "bw_supplements": len(evs), "applications": len({e["application"] for e in evs}),
                          "first_approval": min(e["approval"] for e in evs).isoformat(),
                          "newly_added_any": any(e["newly_added"] for e in evs)})
    out = {"generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "synthea_codes_total": len(ingredients), "synthea_codes_matched_to_bw_ingredients": len(matched_codes),
           "ingredients_matched": len(per_ing), "counts": dict(counts), "ingredient_table": ing_table,
           "hindsight_bias_cases": windows, "matched_codes": matched_codes,
           "method_note": "Per prescription the ingredient-level classification is taken (worst case across the prescription's "
                          "ingredients). A window is open when some BW supplement for the ingredient was approved on/before the "
                          "prescription date but its carrier label version was published in DailyMed only later. Ingredient match by "
                          "base name without salt words; brand/generic not distinguished."}
    (EVIDENCE / "synthea_bw_join.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    md = ["# Synthea prescriptions vs. Boxed Warning availability windows", "",
          f"Synthea medication codes: {len(ingredients)}; matched to ingredients with a BW change (2016–2026): {len(matched_codes)} codes, {len(per_ing)} ingredients.", "",
          "| Count | Value |", "|---|---|"] + [f"| {k} | {v} |" for k, v in sorted(counts.items())] + [
          "", "| Ingredient(s) | Prescriptions | before approval | in window (≤180 d) | window doubtful (>180 d) | carrier unknown | available | BW supplements / applications | first BW approval |", "|---|---|---|---|---|---|---|---|---|"]
    for r in ing_table[:25]:
        md.append(f"| {r['ingredient']} | {r['prescriptions']} | {r.get('before_approval', 0)} | {r.get('approved_not_yet_in_dailymed', 0)} | {r.get('approved_window_doubtful', 0)} | {r.get('approved_carrier_unknown', 0)} | {r.get('available', 0)} | {r['bw_supplements']} / {r['applications']} | {r['first_approval']} |")
    md += ["", f"Prescriptions inside an 'approved but not yet published' window: {len(windows)} (unique prescriptions).", "",
           "| Date | Drug (Synthea) | Ingredient | Reference application | Approval | DailyMed | Window (days) |", "|---|---|---|---|---|---|---|"]
    for w in sorted(windows, key=lambda w: w["start"])[:40]:
        md.append(f"| {w['start']} | {w['drug'][:38]} | {w['ingredient']} | {w['application']} ({w['srlc_drug'][:20]}) | {w['approval']} | {w['dailymed_available']} | {w['window_days']} |")
    (EVIDENCE / "synthea_bw_join.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md[:14]))
    print("…", len(windows), "назначений в окнах незнания")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
