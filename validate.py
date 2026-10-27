#!/usr/bin/env python3
"""Проверка онтологии NIH «It's About Time» (этап N1).

Что проверяется (офлайн, по файлу онтологии и папке evidence/):
  1. Файл: размер <= 3 МБ, Turtle разбирается, только английский текст.
  2. Частичный структурный аудит OWL 2 DL (объявления, простые свойства, карта типов OWL 2).
  3. Резонёр HermiT (owlready2, Java /usr/bin/java): непротиворечивость, невыполнимые классы,
     выведенные принадлежности (классы «известно на момент T», проверка с boxed warning и т. д.).
  4. Контрпримеры: утечка будущего в DL-модели даёт противоречие.
  5. Запросы «на момент T» (SPARQL, rdflib): статичный граф, только valid time, битемпоральный.
  6. Правила целостности в закрытом мире (SPARQL).
  7. Сверка значений онтологии с первичными данными evidence/ (собраны fetch_evidence.py).
  8. Простые метрики (тройки, классы, свойства, экземпляры, аксиомы).

Запуск:  .venv/bin/python validate.py      (отчёт пишется в validation_report.txt рядом с онтологией)
"""
from __future__ import annotations

import datetime as dt
import io
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from pathlib import Path

import owlready2 as o
import rdflib
from rdflib import BNode, Literal, URIRef
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS, SKOS, XSD

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence"
PACKAGE = HERE if (HERE / "ontology").is_dir() else Path("/Users/denis/MyAgentsProjects/UniverseIdeas/solutions/grant-packages/NIH_ITS_ABOUT_TIME")  # публичный репозиторий или пакет гранта
ONTOLOGY = PACKAGE / "ontology" / "its-about-time-bitemporal.ttl"
REPORT = PACKAGE / "ontology" / "validation_report.txt"
JAVA = "/usr/bin/java"
MAX_BYTES = 3 * 1024 * 1024

IAT = rdflib.Namespace("https://w3id.org/iat-bitemporal/ontology#")
IATD = rdflib.Namespace("https://w3id.org/iat-bitemporal/data/")
TIME = rdflib.Namespace("http://www.w3.org/2006/time#")
OBO = rdflib.Namespace("http://purl.obolibrary.org/obo/")
BIOLINK = "https://w3id.org/biolink/vocab/"

# Моменты запросов сценария
T1 = "2024-06-14T15:00:00Z"  # первое назначение
T3 = "2025-01-23T15:00:00Z"  # после сообщения FDA, до публикации новой этикетки в DailyMed
T2 = "2025-03-14T15:00:00Z"  # второе назначение
INSTANTS = {"T1 2024-06-14": T1, "T3 2025-01-23": T3, "T2 2025-03-14": T2}
KNOWN_AS_OF = {T1: "KnownAsOf_20240614T150000Z", T3: "KnownAsOf_20250123T150000Z",
               T2: "KnownAsOf_20250314T150000Z"}

PREFIXES = """
PREFIX iat:  <https://w3id.org/iat-bitemporal/ontology#>
PREFIX iatd: <https://w3id.org/iat-bitemporal/data/>
PREFIX time: <http://www.w3.org/2006/time#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd:  <http://www.w3.org/2001/XMLSchema#>
"""


@dataclass
class Check:
    section: str
    name: str
    ok: bool
    detail: str = ""


@dataclass
class Results:
    checks: list[Check] = field(default_factory=list)
    text: list[str] = field(default_factory=list)

    def add(self, section: str, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append(Check(section, name, ok, detail))

    def line(self, s: str = "") -> None:
        self.text.append(s)


def short(x) -> str:
    s = str(x)
    for ns, p in ((str(IATD), "iatd:"), (str(IAT), "iat:"), (str(TIME), "time:"), (str(OBO), "obo:"),
                  (BIOLINK, "biolink:")):
        if s.startswith(ns):
            return p + s[len(ns):]
    return s


# ----------------------------------------------------------------------------------------------
# Загрузка и резонёр
# ----------------------------------------------------------------------------------------------
def load_graph(path: Path = ONTOLOGY) -> rdflib.Graph:
    g = rdflib.Graph()
    g.parse(path, format="turtle")
    return g


def copy_graph(g: rdflib.Graph) -> rdflib.Graph:
    h = rdflib.Graph()
    for t in g:
        h.add(t)
    return h


@dataclass
class Reasoned:
    consistent: bool
    unsat: list[str]
    world: o.World | None
    error: str = ""


def hermit(g: rdflib.Graph, infer_property_values: bool = True) -> Reasoned:
    """Загрузить граф в отдельный World owlready2 (через N-Triples) и запустить HermiT."""
    o.JAVA_EXE = JAVA
    tmpdir = tempfile.mkdtemp(prefix="iat_")
    nt = os.path.join(tmpdir, "onto.nt")
    g.serialize(nt, format="nt", encoding="utf-8")
    w = o.World()
    onto = w.get_ontology("file://" + nt).load()
    buf = io.StringIO()
    try:
        with redirect_stdout(buf), redirect_stderr(buf), onto:
            o.sync_reasoner_hermit(w, infer_property_values=infer_property_values, debug=0)
        unsat = sorted(short(c.iri) for c in w.inconsistent_classes() if c.iri != str(OWL.Nothing))
        return Reasoned(True, unsat, w)
    except o.OwlReadyInconsistentOntologyError as e:
        return Reasoned(False, [], None, str(e)[:300])


def members(w: o.World, iri: str) -> set[str]:
    c = w.search_one(iri=iri)
    return {short(i.iri) for i in c.instances()} if c is not None else set()


# ----------------------------------------------------------------------------------------------
# Запросы «на момент T»
# ----------------------------------------------------------------------------------------------
Q_RECORDS = PREFIXES + """
SELECT ?r ?a ?src WHERE {
  ?r a ?c . ?c rdfs:subClassOf* iat:TemporalKnowledgeRecord .
  ?r iat:recordedIn ?src .
  OPTIONAL { ?r iat:knownFrom ?a }
}"""

# Битемпоральное правило: запись видна на момент T, если knownFrom <= T и её valid time
# содержит T «как это было известно на T»: конец интервала учитывается, только если запись,
# раскрывшая этот конец (iat:endAttestedBy), сама доступна к T.
Q_BITEMPORAL = PREFIXES + """
SELECT DISTINCT ?r WHERE {
  ?r a ?c . ?c rdfs:subClassOf* iat:TemporalKnowledgeRecord .
  ?r iat:recordedIn ?src . FILTER(?src IN (%SOURCES%))
  ?r iat:knownFrom ?a . FILTER(xsd:dateTime(STR(?a)) <= ?T)
  ?r iat:hasValidTime ?i . ?i time:hasBeginning/time:inXSDDateTimeStamp ?b .
  FILTER(xsd:dateTime(STR(?b)) <= ?T)
  FILTER NOT EXISTS {
    ?i time:hasEnd/time:inXSDDateTimeStamp ?e . FILTER(xsd:dateTime(STR(?e)) <= ?T)
    ?i iat:endAttestedBy ?r2 . ?r2 iat:recordedIn ?src2 . FILTER(?src2 IN (%SOURCES%))
    ?r2 iat:knownFrom ?a2 . FILTER(xsd:dateTime(STR(?a2)) <= ?T)
  }
}"""

# Только valid time (однотемпоральная модель): время доступности игнорируется.
Q_VALID_ONLY = PREFIXES + """
SELECT DISTINCT ?r WHERE {
  ?r a ?c . ?c rdfs:subClassOf* iat:TemporalKnowledgeRecord .
  ?r iat:hasValidTime ?i . ?i time:hasBeginning/time:inXSDDateTimeStamp ?b .
  FILTER(xsd:dateTime(STR(?b)) <= ?T)
  FILTER NOT EXISTS { ?i time:hasEnd/time:inXSDDateTimeStamp ?e . FILTER(xsd:dateTime(STR(?e)) <= ?T) }
}"""

# Статичный граф = снимок «как сейчас»: от каждой этикетки только последняя версия (как отдаёт
# openFDA), все остальные записи — без учёта времени.
Q_STATIC = PREFIXES + """
SELECT DISTINCT ?r WHERE {
  ?r a ?c . ?c rdfs:subClassOf* iat:TemporalKnowledgeRecord .
  FILTER NOT EXISTS { ?r a iat:LabelVersion . ?x iat:supersedes ?r }
}"""

Q_LABELS = PREFIXES + "SELECT ?r WHERE { ?r a iat:LabelVersion }"
Q_BW_ATTESTING = PREFIXES + """
SELECT DISTINCT ?r WHERE {
  ?w a iat:BoxedWarning .
  ?r ?p ?w . ?p rdfs:subPropertyOf* iat:attests .
}"""

ALL_SOURCES = ["iatd:src_dailymed", "iatd:src_fda_srlc", "iatd:src_fda_dsc", "iatd:src_synthetic_ehr",
               "iatd:src_this_kg"]
# «DailyMed only»: регуляторное знание только через DailyMed; записи пациента остаются,
# производные записи графа (выведены из сообщения FDA) исключаются вместе с их источником.
DAILYMED_ONLY = ["iatd:src_dailymed", "iatd:src_synthetic_ehr"]


def _sel(g: rdflib.Graph, q: str, T: str | None = None) -> set[str]:
    # Момент T подставляется прямо в текст запроса: initBindings в rdflib не всегда
    # доходит внутрь FILTER NOT EXISTS.
    if T:
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", T)
        q = q.replace("?T", f'"{T}"^^xsd:dateTime')
    return {short(r[0]) for r in g.query(q)}


def availability(g: rdflib.Graph) -> dict[str, dt.datetime | None]:
    out = {}
    for r, a, _ in g.query(Q_RECORDS):
        out[short(r)] = dt.datetime.fromisoformat(str(a).replace("Z", "+00:00")) if a is not None else None
    return out


def as_of(g: rdflib.Graph, view: str, T: str) -> dict:
    """Результат представления на момент T: текущая этикетка, записи с boxed warning, утечки."""
    if view == "static":
        visible = _sel(g, Q_STATIC)
    elif view == "valid-time only":
        visible = _sel(g, Q_VALID_ONLY, T)
    elif view == "bitemporal (all sources)":
        visible = _sel(g, Q_BITEMPORAL.replace("%SOURCES%", ", ".join(ALL_SOURCES)), T)
    elif view == "bitemporal (DailyMed only)":
        visible = _sel(g, Q_BITEMPORAL.replace("%SOURCES%", ", ".join(DAILYMED_ONLY)), T)
    else:
        raise ValueError(view)
    labels = sorted(visible & _sel(g, Q_LABELS))
    bw = visible & _sel(g, Q_BW_ATTESTING)
    used = set(labels) | bw
    tt = dt.datetime.fromisoformat(T.replace("Z", "+00:00"))
    av = availability(g)
    leaked = {r for r in used if av.get(r) is None or av[r] > tt}
    return {"label": labels, "bw_records": bw, "alert": bool(bw), "leaked": leaked}


VIEWS = ["static", "valid-time only", "bitemporal (all sources)", "bitemporal (DailyMed only)"]
V = {n: f"iatd:label_v{n}" for n in (32, 33, 34, 35, 36)}
DSC, SRLC119 = "iatd:dsc_2025-01-22_glatiramer", "iatd:srlc_suppl119"
ALL_BW = {V[34], V[35], V[36], DSC, SRLC119}
STATIC_BW = {V[36], DSC, SRLC119}
EXPECTED = {
    (T1, "static"): ([V[36]], STATIC_BW, STATIC_BW),
    (T1, "valid-time only"): ([V[33]], set(), {V[33]}),
    (T1, "bitemporal (all sources)"): ([V[32]], set(), set()),
    (T1, "bitemporal (DailyMed only)"): ([V[32]], set(), set()),
    (T3, "static"): ([V[36]], STATIC_BW, {V[36], SRLC119}),
    (T3, "valid-time only"): ([V[34]], {V[34], DSC, SRLC119}, {V[34], SRLC119}),
    (T3, "bitemporal (all sources)"): ([V[33]], {DSC}, set()),
    (T3, "bitemporal (DailyMed only)"): ([V[33]], set(), set()),
    (T2, "static"): ([V[36]], STATIC_BW, {V[36], SRLC119}),
    (T2, "valid-time only"): ([V[35]], {V[35], DSC, SRLC119}, {SRLC119}),
    (T2, "bitemporal (all sources)"): ([V[35]], {V[35], DSC}, set()),
    (T2, "bitemporal (DailyMed only)"): ([V[35]], {V[35]}, set()),
}


# ----------------------------------------------------------------------------------------------
# Контрпримеры для резонёра
# ----------------------------------------------------------------------------------------------
def add_check(g: rdflib.Graph, name: str, T: str, records: list[str], contract: bool) -> URIRef:
    c = IATD[name]
    g.add((c, RDF.type, OWL.NamedIndividual))
    g.add((c, RDF.type, IAT.AsOfSafetyCheck))
    g.add((c, IAT.checksPrescription, IATD["rx_SYN001_2024-06"] if T == T1 else IATD["rx_SYN001_2025-03"]))
    g.add((c, IAT.evaluatedAsOf, Literal(T, datatype=XSD.dateTimeStamp)))
    for r in records:
        g.add((c, IAT.usedRecord, IATD[r]))
    if contract:
        rr = BNode()
        g.add((rr, RDF.type, OWL.Restriction))
        g.add((rr, OWL.onProperty, IAT.usedRecord))
        g.add((rr, OWL.allValuesFrom, IAT[KNOWN_AS_OF[T]]))
        g.add((c, RDF.type, rr))
    return c


def counterexamples(base: rdflib.Graph) -> list[dict]:
    out = []

    g = copy_graph(base)
    add_check(g, "check_static_T1", T1, ["label_v36"], contract=True)
    r = hermit(g, False)
    out.append({"name": "A. Static graph: June-2024 check uses the current label v36 (published 2026-06-26), with as-of contract",
                "expected": "INCONSISTENT", "actual": "CONSISTENT" if r.consistent else "INCONSISTENT"})

    g = copy_graph(base)
    add_check(g, "check_validonly_T1", T1, ["label_v33"], contract=True)
    r = hermit(g, False)
    out.append({"name": "B. Valid-time-only model: June-2024 check uses label v33 (valid from 2023-11-30, published 2024-09-27), with contract",
                "expected": "INCONSISTENT", "actual": "CONSISTENT" if r.consistent else "INCONSISTENT"})

    g = copy_graph(base)
    c = add_check(g, "check_static_nocontract_T1", T1, ["label_v36"], contract=False)
    r = hermit(g, False)
    alert = r.consistent and short(c) in members(r.world, str(IAT.CheckRaisingBoxedWarning))
    out.append({"name": "C. Static graph WITHOUT contract: June-2024 check using v36 is classified as raising the boxed warning (false alert, hindsight)",
                "expected": "CONSISTENT + inferred CheckRaisingBoxedWarning",
                "actual": ("CONSISTENT" if r.consistent else "INCONSISTENT")
                          + (" + inferred CheckRaisingBoxedWarning" if alert else " + not inferred")})

    g = copy_graph(base)
    g.add((IATD.label_v33, IAT.includesWarning, IATD.bw_glatiramer_anaphylaxis))
    r = hermit(g, False)
    out.append({"name": "D. Data-quality axiom: claim that label v33 (no LOINC 34066-1 section) includes the boxed warning",
                "expected": "INCONSISTENT", "actual": "CONSISTENT" if r.consistent else "INCONSISTENT"})

    g = copy_graph(base)
    g.add((IAT.BadClass, RDF.type, OWL.Class))
    g.add((IAT.BadClass, RDFS.subClassOf, IAT.LabelVersion))
    g.add((IAT.BadClass, RDFS.subClassOf, IAT.SafetyCommunication))
    r = hermit(g, False)
    out.append({"name": "E. Negative control for the unsatisfiable-class detector: class under two disjoint classes",
                "expected": "CONSISTENT + unsat ['iat:BadClass']",
                "actual": ("CONSISTENT" if r.consistent else "INCONSISTENT") + f" + unsat {r.unsat}"})

    g = copy_graph(base)
    add_check(g, "check_archive_bound_T2", T2, ["srlc_suppl119"], contract=True)
    r = hermit(g, False)
    out.append({"name": "F. March-2025 check uses SrLC SUPPL-119, whose availability is proven only from 2025-08-10 (first archive snapshot listing it)",
                "expected": "INCONSISTENT", "actual": "CONSISTENT" if r.consistent else "INCONSISTENT"})

    g = copy_graph(base)
    add_check(g, "check_unknown_avail_T2", T2, ["srlc_suppl121"], contract=True)
    r = hermit(g, False)
    out.append({"name": "G. Known limitation (open world): March-2025 check uses SrLC SUPPL-121 whose availability time is UNKNOWN",
                "expected": "CONSISTENT (DL cannot detect; closed-world rule R7 and fail-closed SPARQL exclude it)",
                "actual": ("CONSISTENT" if r.consistent else "INCONSISTENT")
                          + " (DL cannot detect; closed-world rule R7 and fail-closed SPARQL exclude it)"})
    for x in out:
        x["ok"] = x["expected"] == x["actual"]
    return out


# ----------------------------------------------------------------------------------------------
# Правила целостности (закрытый мир)
# ----------------------------------------------------------------------------------------------
def integrity(g: rdflib.Graph, res: Results) -> None:
    sec = "6. Closed-world integrity rules"
    q = lambda s: list(g.query(PREFIXES + s))

    bad = q("""SELECT ?r (COUNT(DISTINCT ?i) AS ?n) WHERE { ?r a ?c . ?c rdfs:subClassOf* iat:TemporalKnowledgeRecord .
               OPTIONAL { ?r iat:hasValidTime ?i } } GROUP BY ?r HAVING (COUNT(DISTINCT ?i) != 1)""")
    res.add(sec, "R1a every record has exactly one valid-time interval", not bad, ", ".join(short(b[0]) for b in bad))
    bad = q("""SELECT ?i (COUNT(DISTINCT ?b) AS ?n) WHERE { ?x iat:hasValidTime ?i . OPTIONAL { ?i time:hasBeginning ?b } }
               GROUP BY ?i HAVING (COUNT(DISTINCT ?b) != 1)""")
    res.add(sec, "R1b every valid-time interval has exactly one beginning", not bad, ", ".join(short(b[0]) for b in bad))

    unknown = sorted(short(r[0]) for r in q("""SELECT ?r WHERE { ?r a ?c . ?c rdfs:subClassOf* iat:TemporalKnowledgeRecord .
               FILTER NOT EXISTS { ?r iat:knownFrom ?a } }"""))
    exp = ["iatd:srlc_suppl121"]   # 116 и 119 — верхняя граница по снимкам Internet Archive (решение 11.10.2026)
    res.add(sec, "R2 the only record with unknown availability is SrLC SUPPL-121 (no archive snapshot lists it; fail-closed)",
            unknown == exp, f"{unknown}")

    bad = q("""SELECT ?n ?p WHERE { ?n iat:supersedes ?p .
               ?n iat:knownFrom ?an . ?p iat:knownFrom ?ap .
               ?n iat:hasValidTime/time:hasBeginning/time:inXSDDateTimeStamp ?bn .
               ?p iat:hasValidTime/time:hasBeginning/time:inXSDDateTimeStamp ?bp .
               ?n iat:splVersion ?vn . ?p iat:splVersion ?vp .
               FILTER(xsd:dateTime(STR(?an)) < xsd:dateTime(STR(?ap)) || xsd:dateTime(STR(?bn)) < xsd:dateTime(STR(?bp)) || ?vn <= ?vp) }""")
    n_sup = len(q("SELECT ?n WHERE { ?n iat:supersedes ?p }"))
    res.add(sec, "R3 succession is monotone (version number, valid start, availability)", not bad and n_sup == 4,
            f"{n_sup} supersedes links; violations: {[(short(a), short(b)) for a, b in bad]}")

    bad = q("""SELECT ?i ?j WHERE { ?i time:intervalMeets ?j . ?i time:hasEnd/time:inXSDDateTimeStamp ?e .
               ?j time:hasBeginning/time:inXSDDateTimeStamp ?b . FILTER(xsd:dateTime(STR(?e)) != xsd:dateTime(STR(?b))) }""")
    n = len(q("SELECT ?i WHERE { ?i time:intervalMeets ?j }"))
    res.add(sec, "R4 time:intervalMeets agrees with timestamps (end(i) = begin(j))", not bad and n == 5,
            f"{n} links; violations: {[(short(a), short(b)) for a, b in bad]}")

    bad = q("""SELECT ?i ?r WHERE { ?i iat:endAttestedBy ?r . ?i time:hasEnd/time:inXSDDateTimeStamp ?e .
               ?r iat:hasValidTime/time:hasBeginning/time:inXSDDateTimeStamp ?b . FILTER(xsd:dateTime(STR(?e)) != xsd:dateTime(STR(?b))) }""")
    missing = q("""SELECT ?i WHERE { ?x iat:hasValidTime ?i . ?i time:hasEnd ?e . FILTER NOT EXISTS { ?i iat:endAttestedBy ?r } }""")
    res.add(sec, "R5 every interval end is attested by a record whose validity begins at that end", not bad and not missing,
            f"violations: {[(short(a), short(b)) for a, b in bad]}; ends without attester: {[short(m[0]) for m in missing]}")

    bad = q("""SELECT ?d ?s WHERE { ?d iat:derivedFrom ?s . ?d iat:knownFrom ?ad . ?s iat:knownFrom ?as .
               FILTER(xsd:dateTime(STR(?ad)) < xsd:dateTime(STR(?as))) }""")
    nd = q("""SELECT ?d ?s WHERE { ?d iat:derivedFrom ?s . FILTER NOT EXISTS { ?s iat:knownFrom ?x } }""")
    res.add(sec, "R6 a derived record is never available before its sources", not bad and not nd,
            f"violations: {[(short(a), short(b)) for a, b in bad]}; sources w/o availability: {[short(a[1]) for a in nd]}")

    rows = q("""SELECT ?c ?T ?r ?a WHERE { ?c a iat:AsOfSafetyCheck ; iat:evaluatedAsOf ?T ; iat:usedRecord ?r .
               OPTIONAL { ?r iat:knownFrom ?a } }""")
    bad = [(short(c), short(r)) for c, T, r, a in rows
           if a is None or dt.datetime.fromisoformat(str(a).replace("Z", "+00:00"))
           > dt.datetime.fromisoformat(str(T).replace("Z", "+00:00"))]
    res.add(sec, "R7 every record used by an as-of check was available at the check instant (closed world)",
            not bad and len(rows) == 8, f"{len(rows)} usages; violations: {bad}")

    # R7b: записанные проверки совпадают с битемпоральным запросом
    msgs, ok = [], True
    for c, T in q("SELECT ?c ?T WHERE { ?c a iat:AsOfSafetyCheck ; iat:evaluatedAsOf ?T }"):
        used = {short(r[0]) for r in g.query(PREFIXES + "SELECT ?r WHERE { ?c iat:usedRecord ?r }", initBindings={"c": c})}
        v = as_of(g, "bitemporal (all sources)", str(T))
        labels_used = sorted(u for u in used if u.startswith("iatd:label_"))
        bw_used = {u for u in used if u in ALL_BW}
        this_ok = labels_used == v["label"] and bw_used == v["bw_records"]
        ok &= this_ok
        msgs.append(f"{short(c)}: label {labels_used} vs query {v['label']}; BW records {sorted(bw_used)} vs query {sorted(v['bw_records'])}")
    res.add(sec, "R7b recorded checks use exactly the label and warning records selected by the bitemporal query", ok, " | ".join(msgs))

    bad = q("""SELECT ?w WHERE { ?w a iat:BoxedWarning . FILTER NOT EXISTS { ?r ?p ?w . ?p rdfs:subPropertyOf* iat:attests } }""")
    res.add(sec, "R8 every safety warning is attested by at least one record", not bad, str([short(b[0]) for b in bad]))

    bad = q("""SELECT ?i WHERE { ?i time:hasBeginning/time:inXSDDateTimeStamp ?b ; time:hasEnd/time:inXSDDateTimeStamp ?e .
               FILTER(xsd:dateTime(STR(?e)) <= xsd:dateTime(STR(?b))) }""")
    res.add(sec, "R9 every closed interval has beginning < end", not bad, str([short(b[0]) for b in bad]))

    rows = q("""SELECT ?r ?a ?src WHERE { ?r iat:knownFrom ?a ; iat:recordedIn ?src .
               FILTER(?src IN (iatd:src_dailymed, iatd:src_fda_dsc)) }""")
    bad = [short(r) for r, a, s in rows if not str(a).endswith("T23:59:59-12:00")]
    res.add(sec, "R10 day-precision availability dates use leakage-safe rounding (D T23:59:59-12:00)",
            not bad and len(rows) == 6, f"{len(rows)} records; violations: {bad}")

    txt = ONTOLOGY.read_text(encoding="utf-8")
    cyr = re.findall(r"[Ѐ-ӿ]", txt)
    res.add(sec, "R11 ontology text is English only (no Cyrillic characters)", not cyr, f"{len(cyr)} Cyrillic chars")


# ----------------------------------------------------------------------------------------------
# Сверка с первичными данными (evidence/)
# ----------------------------------------------------------------------------------------------
def ev(name: str):
    return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))


def value(g: rdflib.Graph, s, p):
    vals = list(g.objects(s, p))
    return vals[0] if vals else None


def begin_ts(g: rdflib.Graph, s) -> str:
    i = value(g, s, IAT.hasValidTime)
    return str(value(g, value(g, i, TIME.hasBeginning), TIME.inXSDDateTimeStamp))


def evidence_check(g: rdflib.Graph, res: Results) -> None:
    sec = "7. Cross-check against primary-source evidence"
    spl = {v["spl_version"]: v for v in ev("spl_metadata_copaxone.json")["versions"]}
    hist = {h["spl_version"]: h["published_date"] for h in ev("dailymed_history_copaxone.json")["data"]["history"]}
    for n in (32, 33, 34, 35, 36):
        s = IATD[f"label_v{n}"]
        e = spl[n]
        pub = dt.datetime.strptime(hist[n], "%b %d, %Y").date().isoformat()
        eff = e["spl_effectiveTime"]
        checks = {
            "doc id": str(value(g, s, IAT.splDocumentId)) == e["document_id"],
            "set id": e["set_id"] == str(value(g, IATD.copaxone_spl_set, IAT.splSetId)),
            "valid start = SPL effectiveTime": begin_ts(g, s)[:10] == f"{eff[:4]}-{eff[4:6]}-{eff[6:]}",
            "availability = DailyMed published_date": str(value(g, s, IAT.knownFrom))[:10] == pub,
            "boxed warning section flag": value(g, s, IAT.containsBoxedWarningSection).toPython()
                                           == e["boxed_warning_section_LOINC_34066_1_present"],
            "includesWarning iff BW section": ((s, IAT.includesWarning, IATD.bw_glatiramer_anaphylaxis) in g)
                                               == e["boxed_warning_section_LOINC_34066_1_present"],
            "NDA in SPL": "NDA020622" in e["approval_ids"],
        }
        bad = [k for k, v in checks.items() if not v]
        res.add(sec, f"E1 label v{n} vs DailyMed history + SPL XML (eff {eff}, published {hist[n]})", not bad,
                f"failed: {bad}" if bad else "doc id, set id, valid start, availability, BW flag, NDA match")

    srlc = {e["supplement"]: e for e in ev("srlc_copaxone_metadata.json")["entries"]}
    for sup, appr in (("SUPPL-116", "approval_suppl116"), ("SUPPL-119", "approval_suppl119"),
                      ("SUPPL-121", "approval_suppl121")):
        e = srlc[sup]
        m, d, y = e["approval_date_mmddyyyy"].split("/")
        when = str(value(g, value(g, IATD[appr], IAT.occursAt), TIME.inXSDDateTimeStamp))[:10]
        rec = IATD["srlc_" + sup.lower().replace("-", "")]
        ok = when == f"{y}-{m}-{d}" and str(value(g, rec, IAT.supplementNumber)) == sup
        if sup == "SUPPL-119":
            ok &= e["boxed_warning_newly_added"] and (rec, IAT.approvesWarning, IATD.bw_glatiramer_anaphylaxis) in g
            ok &= begin_ts(g, IATD.bw_glatiramer_anaphylaxis)[:10] == f"{y}-{m}-{d}"
        res.add(sec, f"E2 SrLC {sup} approved {e['approval_date_mmddyyyy']} (sections: {', '.join(e['sections_changed'])})", ok,
                "date, number" + (", BW newly added, warning valid from approval" if sup == "SUPPL-119" else ""))
    wb = ev("srlc_wayback.json")["first_seen_utc"]
    for sup in ("SUPPL-116", "SUPPL-119", "SUPPL-121"):
        rec = IATD["srlc_" + sup.lower().replace("-", "")]
        known = value(g, rec, IAT.knownFrom)
        if sup in wb:
            ok = known is not None and str(known) == wb[sup]
            detail = f"knownFrom {known} = first archive snapshot listing it {wb[sup]} (upper bound)"
        else:
            ok = known is None
            detail = "no archive snapshot lists it -> availability left unknown (fail-closed)"
        res.add(sec, f"E2c SrLC {sup} availability = first Internet Archive snapshot that lists the entry", ok, detail)
    hdr = ev("srlc_copaxone_metadata.json")["header"]
    res.add(sec, "E2b SrLC application number = label set application number",
            hdr["application"].replace("-", "") == str(value(g, IATD.copaxone_spl_set, IAT.applicationNumber)), str(hdr))

    dsc = ev("fda_dsc_metadata.json")
    m, d, y = dsc["dsc_dates_on_page"][0].split("-")
    res.add(sec, f"E3 FDA DSC dated {dsc['dsc_dates_on_page'][0]} = availability of DSC record",
            str(value(g, IATD[DSC[5:]], IAT.knownFrom))[:10] == f"{y}-{m}-{d}", dsc["title"])

    rx = ev("rxnav_glatiramer.json")
    for c in ("1111642", "1487363"):
        s = IATD["rxcui_" + c]
        con = rx["concepts"][c]
        ok = (str(value(g, s, RDFS.label)) == con["name"] and str(value(g, s, IAT.rxnormTermType)) == con["tty"]
              and str(value(g, s, IAT.rxcui)) == c and con["status"] == "Active"
              and rx["spl_set_id"][c] == [str(value(g, IATD.copaxone_spl_set, IAT.splSetId))])
        ndc = [k for k, v in rx["ndcstatus"].items() if v["rxcui"] == c]
        xref = [str(x) for x in g.objects(s, URIRef("http://www.geneontology.org/formats/oboInOwl#hasDbXref"))]
        ok &= bool(ndc) and any(x.replace("NDC:", "").replace("-", "") == ndc[0] for x in xref)
        res.add(sec, f"E4 RxNorm {c}: name, TTY, Active, SPL_SET_ID, NDC", ok, f"{con['name']} ({con['tty']}), NDC11 {ndc}")
    ing = {k: v["name"] for k, v in rx["concepts"].items()}
    res.add(sec, "E4b RxNorm ingredient/brand ids (84375 PIN, 214582 IN, 135779 BN)",
            ing["84375"] == "glatiramer acetate" and ing["214582"] == "glatiramer" and ing["135779"] == "Copaxone", str(ing))

    chebi = ev("chebi_749565.json")
    res.add(sec, "E5 ChEBI 749565 name and release status (ChEBI API)",
            chebi["name"] == str(value(g, OBO.CHEBI_749565, RDFS.label)) and chebi["is_released"], str(chebi))
    mesh = ev("mesh_descriptors.json")
    used_mesh = set(re.findall(r"D\d{6,9}", " ".join(str(o_) for o_ in g.objects(None, URIRef("http://www.geneontology.org/formats/oboInOwl#hasDbXref"))
                                                       ) + " " + " ".join(str(o_) for o_ in g.objects(None, SKOS.exactMatch))))
    res.add(sec, "E5b every MeSH id used is a live MeSH descriptor (NLM MeSH RDF)",
            used_mesh <= set(k for k, v in mesh.items() if v), f"used {sorted(used_mesh)}; labels {mesh}")
    spl_unii = {u for v in spl.values() for (_, u, _) in v["ingredients_classCode_UNII_name"]}
    res.add(sec, "E5c UNII 5M691HL4BO is the active ingredient in all modelled SPL versions",
            "5M691HL4BO" in spl_unii and all(v["ingredients_classCode_UNII_name"][0][1] == "5M691HL4BO" for v in spl.values()),
            "5M691HL4BO = GLATIRAMER ACETATE (classCode ACTIB) in every version; all UNII in SPL: "
            + str(sorted(spl_unii)) + " (3OWL53L36A = MANNITOL, inactive)")

    obo = ev("obo_terms_ols.json")
    used_obo = {str(x) for t in g for x in t if isinstance(x, URIRef) and str(x).startswith(str(OBO))}
    bad = []
    for iri in sorted(used_obo):
        t = obo["terms"].get(iri)
        if not t or t["is_obsolete"] or str(value(g, URIRef(iri), RDFS.label)) not in t["label"]:
            bad.append(short(iri))
    res.add(sec, f"E6 {len(used_obo)} OBO terms: exist in OLS, not obsolete, labels match", not bad, f"problems: {bad}")
    replicated = [(OBO.BFO_0000015, RDFS.subClassOf, OBO.BFO_0000003), (OBO.BFO_0000031, RDFS.subClassOf, OBO.BFO_0000002),
                  (OBO.IAO_0000030, RDFS.subClassOf, OBO.BFO_0000031), (OBO.MONDO_0005314, RDFS.subClassOf, OBO.MONDO_0005301),
                  (OBO.BFO_0000002, OWL.disjointWith, OBO.BFO_0000003)]
    bad = []
    for s, p, o_ in replicated:
        key = "subClassOf" if p == RDFS.subClassOf else "disjointWith"
        if (s, p, o_) not in g or str(o_) not in obo["terms"][str(s)][key]:
            bad.append(f"{short(s)} {key} {short(o_)}")
    for prop in (OBO.BFO_0000062, OBO.BFO_0000063):
        if "http://www.w3.org/2002/07/owl#TransitiveProperty" not in obo["terms"][str(prop)]["rdf_type"] \
                or (prop, RDF.type, OWL.TransitiveProperty) not in g:
            bad.append(f"{short(prop)} transitive")
    for mondo in ("MONDO_0005301", "MONDO_0005314", "MONDO_0100053"):
        ours = [str(x) for x in g.objects(OBO[mondo], URIRef("http://www.geneontology.org/formats/oboInOwl#hasDbXref"))]
        if sorted(ours) != sorted(obo["terms"][str(OBO[mondo])]["hasDbXref_MESH"]):
            bad.append(f"{mondo} MeSH xref {ours}")
    res.add(sec, "E6b replicated OBO axioms (BFO/IAO/RO/MONDO) and MeSH xrefs agree with the source ontologies", not bad,
            f"problems: {bad}; versions: {obo['ontology_versions']}")

    bl = ev("biolink_terms_checked.json")
    used_bl = sorted({str(x) for t in g for x in t if isinstance(x, URIRef) and str(x).startswith(BIOLINK)})
    bad = [short(i) for i in used_bl if not (bl["used_terms"].get(i, {}).get("in_schema")
                                             and bl["used_terms"][i]["w3id_http_status"] == 200)]
    res.add(sec, f"E7 {len(used_bl)} Biolink IRIs exist in Biolink {bl['release_tag']} schema and resolve via w3id (negative control {bl['negative_control_status']})",
            not bad and bl["negative_control_status"] == 404, f"problems: {bad}")

    def camel(name):
        return BIOLINK + "".join(w[:1].upper() + w[1:] for w in name.split(" "))
    bad = []
    for s, o_ in g.subject_objects(RDFS.subClassOf):
        if str(s).startswith(BIOLINK) and str(o_).startswith(BIOLINK):
            entry = bl["used_terms"][str(s)]["schema_entry"]
            if camel(entry.get("is_a", "")) != str(o_):
                bad.append(f"{short(s)} -> {short(o_)}")
    n_bl_sub = sum(1 for s, o_ in g.subject_objects(RDFS.subClassOf) if str(s).startswith(BIOLINK) and str(o_).startswith(BIOLINK))
    res.add(sec, f"E7b {n_bl_sub} replicated Biolink is_a links equal the schema", not bad, f"problems: {bad}")
    res.add(sec, "E7c infores ids used exist in the Biolink Information Resource Registry",
            all(bl["infores"].get(str(x)) for x in g.objects(None, IAT.inforesId)),
            f"{[str(x) for x in g.objects(None, IAT.inforesId)]}; registry check {bl['infores']}")

    w3 = ev("w3c_terms_checked.json")
    tt = w3["owl_time_used_terms"]
    bad = []
    for iri, t in tt.items():
        s = URIRef(iri)
        if not t["declared"]:
            bad.append(f"{short(iri)} not in OWL-Time")

        def q(x):
            return "time:" + str(x).split("#")[1] if str(x).startswith(str(TIME)) else ("xsd:" + str(x).split("#")[1] if "XMLSchema" in str(x) else str(x))
        for p, key in ((RDFS.subClassOf, "subClassOf"), (RDFS.subPropertyOf, "subPropertyOf"), (RDFS.domain, "domain"),
                       (RDFS.range, "range"), (OWL.disjointWith, "disjointWith"), (OWL.inverseOf, "inverseOf")):
            ours = {q(x) for x in g.objects(s, p) if isinstance(x, URIRef)}
            theirs = {("time:" + x if ":" not in x else x) for x in t[key]}
            if not ours <= theirs:
                bad.append(f"{short(iri)} {key} {ours - theirs}")
    res.add(sec, f"E8 {len(tt)} OWL-Time terms exist and replicated axioms are a subset of W3C OWL-Time", not bad,
            f"problems: {bad}; OWL-Time licence {w3['owl_time_license']}")
    res.add(sec, "E9 PROV-O terms used in mappings exist", all(w3["prov_used_terms_declared"].values()),
            str(w3["prov_used_terms_declared"]))
    log = ev("access_log.json")
    res.add(sec, "E10 evidence collected without errors (fetch_evidence.py access log)", not log["errors"],
            f"{len(log['requests'])} requests, first {log['generated_utc']}, errors: {log['errors']}")


# ----------------------------------------------------------------------------------------------
# Структурный аудит OWL 2 DL (частичный) и метрики
# ----------------------------------------------------------------------------------------------
OWL2_DATATYPES = {str(XSD[x]) for x in ("string", "boolean", "integer", "nonNegativeInteger", "dateTime",
                                        "dateTimeStamp", "decimal", "double", "float", "anyURI")} | \
                 {str(RDF.PlainLiteral), str(RDF.langString)}


def dl_audit(g: rdflib.Graph, res: Results) -> None:
    sec = "2. Structural OWL 2 DL audit (partial)"
    builtin = (str(RDF), str(RDFS), str(OWL), str(XSD))
    objp = set(g.subjects(RDF.type, OWL.ObjectProperty))
    datp = set(g.subjects(RDF.type, OWL.DatatypeProperty))
    annp = set(g.subjects(RDF.type, OWL.AnnotationProperty))
    classes = set(g.subjects(RDF.type, OWL.Class))
    preds = {p for p in g.predicates() if not str(p).startswith(builtin)}
    undeclared = sorted(short(p) for p in preds if p not in objp | datp | annp)
    res.add(sec, "every non-builtin predicate is declared (object/datatype/annotation property)", not undeclared, str(undeclared))
    clash = (objp & datp) | (objp & annp) | (datp & annp)
    res.add(sec, "no IRI is declared as two kinds of property", not clash, str([short(x) for x in clash]))
    used_cls = set()
    for p in (RDFS.subClassOf, OWL.equivalentClass, OWL.someValuesFrom, OWL.allValuesFrom, OWL.onClass, OWL.disjointWith):
        for s, o_ in g.subject_objects(p):
            for x in (s, o_):
                if isinstance(x, URIRef) and not str(x).startswith(str(XSD)):
                    used_cls.add(x)
    for s, c in g.subject_objects(RDF.type):
        if isinstance(c, URIRef) and not str(c).startswith(builtin):
            used_cls.add(c)
    undecl_cls = sorted(short(c) for c in used_cls if c not in classes and c not in objp | datp and c != OWL.Thing)
    res.add(sec, "every class used in axioms or class assertions is declared owl:Class", not undecl_cls, str(undecl_cls))
    inds = {s for s, c in g.subject_objects(RDF.type) if isinstance(s, URIRef) and c in classes}
    not_named = sorted(short(i) for i in inds if (i, RDF.type, OWL.NamedIndividual) not in g)
    res.add(sec, "every individual is declared owl:NamedIndividual", not not_named, str(not_named))
    pun = inds & classes
    res.add(sec, "no punning between classes and individuals", not pun, str([short(x) for x in pun]))
    # простые свойства: на транзитивных (и их надсвойствах) не должно быть ограничений простоты
    trans = set(g.subjects(RDF.type, OWL.TransitiveProperty))
    nonsimple = set(trans)
    changed = True
    while changed:
        changed = False
        for s, o_ in g.subject_objects(RDFS.subPropertyOf):
            if s in nonsimple and o_ not in nonsimple:
                nonsimple.add(o_)
                changed = True
        for s, o_ in g.subject_objects(OWL.inverseOf):
            for a, b in ((s, o_), (o_, s)):
                if a in nonsimple and b not in nonsimple:
                    nonsimple.add(b)
                    changed = True
    need_simple = set()
    for t in (OWL.FunctionalProperty, OWL.InverseFunctionalProperty, OWL.AsymmetricProperty, OWL.IrreflexiveProperty):
        need_simple |= set(g.subjects(RDF.type, t)) & objp
    for r in g.subjects(RDF.type, OWL.Restriction):
        if any(g.objects(r, p) for p in (OWL.qualifiedCardinality, OWL.maxQualifiedCardinality, OWL.minQualifiedCardinality,
                                         OWL.cardinality, OWL.maxCardinality, OWL.minCardinality)):
            need_simple |= set(g.objects(r, OWL.onProperty)) & objp
    viol = sorted(short(p) for p in need_simple & nonsimple)
    res.add(sec, "global restrictions: functional/inverse-functional/asymmetric/irreflexive/cardinality only on simple properties",
            not viol, f"non-simple: {sorted(short(p) for p in nonsimple)}; violations: {viol}")
    # литералы в логических аксиомах — только из карты типов OWL 2
    bad = set()
    for s, p, o_ in g:
        if isinstance(o_, Literal) and o_.datatype and (p in datp or p in (OWL.hasValue, XSD.maxInclusive)):
            if str(o_.datatype) not in OWL2_DATATYPES:
                bad.add((short(p), str(o_.datatype)))
        if p in (RDFS.range, OWL.onDataRange, OWL.onDatatype) and str(o_).startswith(str(XSD)) and str(o_) not in OWL2_DATATYPES:
            bad.add((short(s), str(o_)))
    res.add(sec, "datatypes in logical axioms belong to the OWL 2 datatype map (xsd:date only in annotations)", not bad, str(sorted(bad)))
    res.add(sec, "no owl:imports (self-contained for offline reasoning)", not list(g.objects(None, OWL.imports)), "")


def metrics(g: rdflib.Graph, w: o.World | None) -> list[str]:
    def own(x):
        return str(x).startswith(str(IAT))
    classes = {c for c in g.subjects(RDF.type, OWL.Class) if isinstance(c, URIRef)}
    objp = set(g.subjects(RDF.type, OWL.ObjectProperty))
    datp = set(g.subjects(RDF.type, OWL.DatatypeProperty))
    annp = set(g.subjects(RDF.type, OWL.AnnotationProperty))
    inds = set(g.subjects(RDF.type, OWL.NamedIndividual))
    restr = list(g.subjects(RDF.type, OWL.Restriction))
    rkind = {}
    for r in restr:
        for p, k in ((OWL.someValuesFrom, "some"), (OWL.allValuesFrom, "only"), (OWL.hasValue, "value"),
                     (OWL.qualifiedCardinality, "exactly"), (OWL.maxQualifiedCardinality, "max")):
            if (r, p, None) in g:
                rkind[k] = rkind.get(k, 0) + 1
    dtr = sum(1 for _ in g.subjects(OWL.withRestrictions, None))
    alldisj = list(g.subjects(RDF.type, OWL.AllDisjointClasses))
    pairwise = sum(len(list(Collection(g, next(g.objects(a, OWL.members))))) for a in alldisj)
    chars = {k: len(set(g.subjects(RDF.type, t)) & (objp | datp)) for k, t in (
        ("functional", OWL.FunctionalProperty), ("inverse functional", OWL.InverseFunctionalProperty),
        ("transitive", OWL.TransitiveProperty), ("asymmetric", OWL.AsymmetricProperty), ("irreflexive", OWL.IrreflexiveProperty))}
    own_cls = {c for c in classes if own(c)}
    asserted_inst = {c for c in own_cls if any((i, RDF.type, c) in g for i in inds)}
    inferred_inst = set()
    if w is not None:
        for c in own_cls:
            oc = w.search_one(iri=str(c))
            if oc is not None and list(oc.instances()):
                inferred_inst.add(c)
    own_props = {p for p in objp | datp if own(p)}
    used_props = {p for p in own_props if any(True for _ in g.subject_objects(p))}
    in_restr = {p for p in own_props if (None, OWL.onProperty, p) in g} - used_props
    via_sub = {p for p in own_props - used_props - in_restr
               if any(sp in used_props for sp in g.subjects(RDFS.subPropertyOf, p))}
    unused = own_props - used_props - in_restr - via_sub
    opa = sum(1 for s, p, o_ in g if p in objp and s in inds)
    dpa = sum(1 for s, p, o_ in g if p in datp and s in inds)
    ca = sum(1 for s, c in g.subject_objects(RDF.type) if s in inds and c != OWL.NamedIndividual)
    lines = [
        f"triples: {len(g)}; file size: {ONTOLOGY.stat().st_size} bytes (limit {MAX_BYTES})",
        f"named classes: {len(classes)} (own iat: {len(own_cls)}, reused: {len(classes) - len(own_cls)} "
        f"[biolink {sum(1 for c in classes if str(c).startswith(BIOLINK))}, OBO {sum(1 for c in classes if str(c).startswith(str(OBO)))}, "
        f"OWL-Time {sum(1 for c in classes if str(c).startswith(str(TIME)))}])",
        f"object properties: {len(objp)} (own {sum(1 for p in objp if own(p))}); datatype properties: {len(datp)} "
        f"(own {sum(1 for p in datp if own(p))}); annotation properties: {len(annp)}",
        f"named individuals: {len(inds)}; class assertions: {ca}; object property assertions: {opa}; "
        f"data property assertions: {dpa}",
        f"TBox: subClassOf {sum(1 for _ in g.triples((None, RDFS.subClassOf, None)))}, equivalentClass "
        f"{sum(1 for _ in g.triples((None, OWL.equivalentClass, None)))}, disjointWith "
        f"{sum(1 for _ in g.triples((None, OWL.disjointWith, None)))}, AllDisjointClasses {len(alldisj)} "
        f"({pairwise} members), domain {sum(1 for _ in g.triples((None, RDFS.domain, None)))}, range "
        f"{sum(1 for _ in g.triples((None, RDFS.range, None)))}, subPropertyOf "
        f"{sum(1 for _ in g.triples((None, RDFS.subPropertyOf, None)))}, inverseOf {sum(1 for _ in g.triples((None, OWL.inverseOf, None)))}",
        f"restrictions: {len(restr)} {dict(sorted(rkind.items()))}; datatype facet restrictions: {dtr}; "
        f"property characteristics: {chars}",
        f"own classes with >=1 instance: asserted {len(asserted_inst)}/{len(own_cls)}, after reasoning "
        f"{len(inferred_inst)}/{len(own_cls)}; without instances: {sorted(short(c) for c in own_cls - inferred_inst)}",
        f"own properties used in assertions: {len(used_props)}/{len(own_props)}; used only inside class restrictions: "
        f"{sorted(short(p) for p in in_restr)}; populated only through sub-properties: "
        f"{sorted(short(p) for p in via_sub)}; unused: {sorted(short(p) for p in unused)}",
    ]
    return lines


# ----------------------------------------------------------------------------------------------
# Главная функция
# ----------------------------------------------------------------------------------------------
def run() -> Results:
    res = Results()
    sec = "1. File"
    size = ONTOLOGY.stat().st_size
    res.add(sec, f"file size {size} bytes <= 3 MB", size <= MAX_BYTES)
    g = load_graph()
    res.add(sec, f"Turtle parses (rdflib {rdflib.__version__}): {len(g)} triples", len(g) > 0)
    res.add(sec, "ontology header present (owl:Ontology with versionIRI)",
            any(g.objects(None, OWL.versionIRI)) and any(g.subjects(RDF.type, OWL.Ontology)))

    dl_audit(g, res)

    sec = "3. Reasoner (HermiT via owlready2)"
    r = hermit(g, True)
    res.add(sec, "ontology is consistent (no logical contradictions)", r.consistent, r.error)
    res.add(sec, "unsatisfiable named classes: 0", r.consistent and not r.unsat, str(r.unsat))
    inferred = {}
    if r.consistent:
        w = r.world
        exp = {
            "KnownAsOf_20240614T150000Z": {"iatd:label_v32", "iatd:dx_SYN001_rrms", "iatd:rxrec_SYN001_2024-06",
                                           "iatd:srlc_suppl116"},
            "KnownAsOf_20250123T150000Z": {"iatd:label_v32", "iatd:label_v33", DSC, "iatd:assoc_glatiramer_anaphylaxis",
                                           "iatd:dx_SYN001_rrms", "iatd:rxrec_SYN001_2024-06", "iatd:srlc_suppl116"},
            "KnownAsOf_20250314T150000Z": {"iatd:label_v32", "iatd:label_v33", "iatd:label_v34", "iatd:label_v35", DSC,
                                           "iatd:assoc_glatiramer_anaphylaxis", "iatd:dx_SYN001_rrms",
                                           "iatd:rxrec_SYN001_2024-06", "iatd:rxrec_SYN001_2025-03", "iatd:srlc_suppl116"},
            "CheckRaisingBoxedWarning": {"iatd:check_SYN001_2025-03"},
            "GlatiramerAcetateProduct": {"iatd:rxcui_1111642", "iatd:rxcui_1487363"},
        }
        for cls, e in exp.items():
            got = members(w, str(IAT[cls]))
            inferred[cls] = got
            res.add(sec, f"inferred members of iat:{cls} = {sorted(e)}", got == e, f"got {sorted(got)}")
        a = w.search_one(iri=str(IATD.approval_suppl121))
        pb = w.search_one(iri=str(OBO.BFO_0000062))
        got = {short(x.iri) for x in pb[a]}
        res.add(sec, "transitivity of RO 'preceded by': SUPPL-121 approval preceded by SUPPL-116 (inferred)",
                got == {"iatd:approval_suppl119", "iatd:approval_suppl116"}, f"got {sorted(got)}")
        p = w.search_one(iri=str(IATD.patient_SYN001))
        cont = w.search_one(iri=str(OBO.BFO_0000002))
        res.add(sec, "domain/range reasoning: synthetic patient inferred to be a BFO continuant (range of RO 'has participant')",
                cont in p.INDIRECT_is_a, "")

    sec = "4. Temporal-leakage counter-examples (HermiT)"
    for x in counterexamples(g):
        res.add(sec, x["name"], x["ok"], f"expected {x['expected']}; got {x['actual']}")

    sec = "5. As-of queries (SPARQL via rdflib)"
    table = []
    for tname, T in INSTANTS.items():
        for view in VIEWS:
            v = as_of(g, view, T)
            el, ebw, eleak = EXPECTED[(T, view)]
            ok = v["label"] == el and v["bw_records"] == ebw and v["leaked"] == eleak
            table.append((tname, view, v))
            res.add(sec, f"{tname} | {view}: label {v['label']}, boxed warning {'VISIBLE' if v['alert'] else 'not visible'}, "
                         f"leaked records {len(v['leaked'])}", ok,
                    f"BW records {sorted(v['bw_records'])}; leaked {sorted(v['leaked'])}")

    integrity(g, res)
    evidence_check(g, res)

    # ----- текст отчёта
    n_ok = sum(c.ok for c in res.checks)
    res.line("VALIDATION REPORT -- Bitemporal Biomedical Knowledge Ontology (NIH It's About Time, Phase 1, stage N1)")
    res.line(f"generated: {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    res.line(f"ontology:  {ONTOLOGY}")
    jv = subprocess.run([JAVA, "-version"], capture_output=True, text=True).stderr.splitlines()[0]
    res.line(f"tools:     Python {platform.python_version()}, rdflib {rdflib.__version__}, owlready2 "
             f"{getattr(o, 'VERSION', '?')} (HermiT bundled), Java: {jv} ({JAVA})")
    res.line(f"RESULT:    {n_ok}/{len(res.checks)} checks passed" + ("" if n_ok == len(res.checks) else "  <-- FAILURES"))
    res.line()
    res.line("Query instants: T1 = 2024-06-14T15:00Z (first prescription), T3 = 2025-01-23T15:00Z (FDA communication "
             "published, new label not yet in DailyMed), T2 = 2025-03-14T15:00Z (second prescription).")
    res.line()
    res.line("AS-OF SUMMARY (is the anaphylaxis boxed warning visible to a safety check?)")
    res.line(f"  {'instant':<15} {'view':<28} {'current label':<18} {'boxed warning':<14} leaked records")
    for tname, view, v in table:
        res.line(f"  {tname:<15} {view:<28} {','.join(x.replace('iatd:', '') for x in v['label']):<18} "
                 f"{'VISIBLE' if v['alert'] else 'no':<14} {len(v['leaked'])}"
                 + (f" ({', '.join(sorted(x.replace('iatd:', '') for x in v['leaked']))})" if v['leaked'] else ""))
    res.line()
    cur = None
    for c in res.checks:
        if c.section != cur:
            res.line(f"== {c.section}")
            cur = c.section
        res.line(f"  [{'PASS' if c.ok else 'FAIL'}] {c.name}")
        if c.detail:
            res.line(f"         {c.detail}")
    res.line()
    res.line("== 8. Metrics")
    for m in metrics(g, r.world if r.consistent else None):
        res.line(f"  {m}")
    res.line()
    res.line("Notes:")
    res.line("  * Section 2 is a partial structural audit written for this file, not a full OWL 2 DL profile checker "
             "(OWL API profile validation / ROBOT were not installed).")
    res.line("  * The W3C OWL-Time release is not imported: it uses xsd:duration, which is outside the OWL 2 datatype map "
             "and is rejected by HermiT (UnsupportedDatatypeException, checked on 2026-10-07). Axioms of the reused "
             "OWL-Time terms are replicated and checked against the W3C file (E8).")
    res.line("  * Pellet (bundled with owlready2) could not be run: its Apache Jena jars are compiled for class-file "
             "version 69 (Java 25); Java 23 supports up to 67 (UnsupportedClassVersionError, checked 2026-10-07).")
    res.line("  * Views: 'static' = snapshot as of today (only the latest version of each label, as openFDA serves it; "
             "all other records regardless of time); 'valid-time only' = records whose valid time contains T, "
             "availability ignored; 'bitemporal' = records available at T whose valid time contains T as known at T "
             "(an interval end counts only if the record revealing it is available at T); unknown availability = "
             "not available (fail-closed). 'DailyMed only' admits regulatory knowledge only via DailyMed.")
    res.line("  * rdflib does not compare xsd:dateTimeStamp literals natively (silently empty result); all SPARQL "
             "comparisons cast with xsd:dateTime(STR(?x)).")
    res.line("  * Patient data are hand-authored synthetic records (no PHI). Regulatory dates/ids come from public "
             "primary sources (see evidence/ and access_log.json).")
    return res


def main() -> int:
    res = run()
    REPORT.write_text("\n".join(res.text) + "\n", encoding="utf-8")
    print("\n".join(res.text[:5 + 15]))
    failed = [c for c in res.checks if not c.ok]
    for c in failed:
        print(f"FAIL: {c.section} :: {c.name} :: {c.detail}")
    print(f"report written to {REPORT}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
