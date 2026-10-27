#!/usr/bin/env python3
"""Этап N2, шаг 6: проверка модуля данных 0.2 (ядро N1 + A-box из build_abox.py).

1. Логика: HermiT (через owlready2, как в validate.py) — ядро + данные вместе: согласованность, невыполнимые классы.
2. Контроль чувствительности: в копию добавляется «утекающая» проверка (usedRecord с knownFrom позже T) —
   HermiT ОБЯЗАН дать INCONSISTENT; иначе детектор утечки не работает на этом объёме.
3. Закрытые правила по данным (SPARQL): у каждой записи знания ровно один интервал с началом; доли записей с
   указанным knownFrom (SrLC / DailyMed); у версий — доля с подтверждённым разделом; у проверок «на момент T» —
   все использованные записи имеют knownFrom ≤ T (утечек нет); размер файла ≤ 3 МБ (лимит подачи).
Выход: evidence/abox_validation.json и печать сводки.  Запуск: .venv/bin/python validate_abox.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time
from pathlib import Path

import rdflib
from rdflib import URIRef, Literal, RDF
from rdflib.namespace import XSD

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate import hermit, load_graph, ONTOLOGY  # noqa: E402  (HermiT-обвязка N1)

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence"
DATA = ONTOLOGY.parent / "its-about-time-data-0.2.ttl"
IAT = "https://w3id.org/iat-bitemporal/ontology#"
IATD = "https://w3id.org/iat-bitemporal/data/"
OWL = "http://www.w3.org/2002/07/owl#"
TIME = "http://www.w3.org/2006/time#"
SUBMISSION_LIMIT = 3 * 1024 * 1024


def q1(g: rdflib.Graph, query: str):
    return [row for row in g.query(query)]


def main() -> int:
    import argparse
    global DATA
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(DATA))
    ap.add_argument("--skip-hermit", action="store_true", help="только закрытые правила (для большого модуля)")
    ap.add_argument("--no-leak-control", action="store_true", help="без второго прогона HermiT с подсаженной утечкой (экономит время на большом модуле)")
    args = ap.parse_args()
    DATA = Path(args.data)
    t0 = time.time()
    core = load_graph(ONTOLOGY)
    data = rdflib.Graph()
    data.parse(DATA, format="turtle")
    g = rdflib.Graph()
    for t in core:
        g.add(t)
    for t in data:
        g.add(t)
    # owl:imports в модуле данных указывает на IRI ядра — в объединённом графе лишний
    g.remove((None, URIRef(OWL + "imports"), None))
    res = {"core_triples": len(core), "data_triples": len(data), "merged_triples": len(g), "data_bytes": DATA.stat().st_size,
           "within_submission_limit": DATA.stat().st_size <= SUBMISSION_LIMIT}

    P = "PREFIX iat: <%s> PREFIX time: <%s> PREFIX owl: <%s> " % (IAT, TIME, OWL)
    res["records"] = int(q1(g, P + "SELECT (COUNT(DISTINCT ?r) AS ?n) WHERE { ?r a ?c . ?c rdfs:subClassOf* iat:TemporalKnowledgeRecord }")[0][0])
    res["records_without_valid_time"] = int(q1(g, P + "SELECT (COUNT(DISTINCT ?r) AS ?n) WHERE { ?r a ?c . ?c rdfs:subClassOf* iat:TemporalKnowledgeRecord . FILTER NOT EXISTS { ?r iat:hasValidTime ?v . ?v time:hasBeginning ?b } }")[0][0])
    res["records_with_two_valid_times"] = int(q1(g, P + "SELECT (COUNT(DISTINCT ?r) AS ?n) WHERE { ?r iat:hasValidTime ?v1 , ?v2 . FILTER(?v1 != ?v2) }")[0][0])
    for cls, key in (("LabelingChangeRecord", "srlc"), ("LabelVersion", "label"), ("PrescriptionRecord", "rx")):
        tot = int(q1(g, P + f"SELECT (COUNT(DISTINCT ?r) AS ?n) WHERE {{ ?r a iat:{cls} }}")[0][0])
        known = int(q1(g, P + f"SELECT (COUNT(DISTINCT ?r) AS ?n) WHERE {{ ?r a iat:{cls} ; iat:knownFrom ?k }}")[0][0])
        res[f"{key}_records"] = tot
        res[f"{key}_with_known_from"] = known
    res["label_versions_section_asserted"] = int(q1(g, P + "SELECT (COUNT(DISTINCT ?r) AS ?n) WHERE { ?r a iat:LabelVersion ; iat:containsBoxedWarningSection ?b }")[0][0])
    # Закрытое правило: ни одна проверка «на момент T» не использует запись, ставшую известной позже T
    leaks = q1(g, P + "SELECT ?chk ?r ?k ?T WHERE { ?chk a iat:AsOfSafetyCheck ; iat:evaluatedAsOf ?T ; iat:usedRecord ?r . ?r iat:knownFrom ?k . FILTER(xsd:dateTime(STR(?k)) > xsd:dateTime(STR(?T))) }")
    res["as_of_checks"] = int(q1(g, P + "SELECT (COUNT(DISTINCT ?c) AS ?n) WHERE { ?c a iat:AsOfSafetyCheck }")[0][0])
    res["as_of_checks_leaking_closed_world"] = len(leaks)
    res["used_records_without_known_from"] = int(q1(g, P + "SELECT (COUNT(*) AS ?n) WHERE { ?c a iat:AsOfSafetyCheck ; iat:usedRecord ?r . FILTER NOT EXISTS { ?r iat:knownFrom ?k } }")[0][0])

    # HermiT: ядро + данные (на большом модуле — пропуск по флагу)
    if args.skip_hermit:
        from validate import Reasoned
        r1 = Reasoned(True, [], None, "skipped")
    else:
        r1 = hermit(g)
    res["hermit"] = {"consistent": r1.consistent, "unsatisfiable_classes": r1.unsat, "error": r1.error, "seconds": round(time.time() - t0, 1)}
    checks_raising = 0
    if r1.consistent and r1.world is not None:
        cls = r1.world[IAT + "CheckRaisingBoxedWarning"]
        checks_raising = len(list(cls.instances())) if cls else 0
    res["checks_raising_boxed_warning_inferred"] = checks_raising

    # Контроль чувствительности: утечка должна дать противоречие
    rows = [] if (args.skip_hermit or args.no_leak_control) else q1(g, P + "SELECT ?chk ?T ?cls WHERE { ?chk a iat:AsOfSafetyCheck ; iat:evaluatedAsOf ?T ; a ?rest . ?rest owl:onProperty iat:usedRecord ; owl:allValuesFrom ?cls } LIMIT 1")
    late = q1(g, P + "SELECT ?r ?k WHERE { ?r a iat:LabelVersion ; iat:knownFrom ?k } ORDER BY DESC(?k) LIMIT 1")
    if rows and late:
        chk, T, cls = rows[0]
        r_iri, k = late[0]
        if dt.datetime.fromisoformat(str(k).replace("Z", "+00:00")) > dt.datetime.fromisoformat(str(T).replace("Z", "+00:00")):
            h = rdflib.Graph()
            for t in g:
                h.add(t)
            h.add((URIRef(chk), URIRef(IAT + "usedRecord"), URIRef(r_iri)))
            r2 = hermit(h)
            res["leak_control"] = {"check": str(chk).replace(IATD, "iatd:"), "T": str(T), "leaked_record": str(r_iri).replace(IATD, "iatd:"),
                                   "known_from": str(k), "hermit_consistent": r2.consistent, "detector_works": not r2.consistent}
        else:
            res["leak_control"] = {"skipped": "нет версии с knownFrom позже T первой проверки"}
    else:
        res["leak_control"] = {"skipped": "отключён флагом --no-leak-control" if args.no_leak_control else "нет проверок «на момент T» в модуле данных"}
    res["generated_utc"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    (EVIDENCE / f"abox_validation_{DATA.stem.replace('its-about-time-data-', '')}.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(res, indent=1, ensure_ascii=False))
    ok = r1.consistent and not r1.unsat and res["records_without_valid_time"] == 0 and res["records_with_two_valid_times"] == 0 \
        and res["as_of_checks_leaking_closed_world"] == 0 and res["within_submission_limit"] \
        and res["leak_control"].get("detector_works", True) and (args.skip_hermit or r1.error == "")
    print("ИТОГ:", "OK" if ok else "ЕСТЬ ПРОБЛЕМЫ")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
