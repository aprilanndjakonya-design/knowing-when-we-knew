#!/usr/bin/env python3
"""Сбор доказательной базы для онтологии NIH «It's About Time» (этап N1).

Делает только небольшие запросы к публичным API и сохраняет в evidence/ ответы
и извлечённые метаданные (даты, идентификаторы, коды разделов). Тексты этикеток
производителей НЕ сохраняются: архивы SPL распаковываются во временную папку,
из XML берутся только метаданные, папка удаляется.

Запуск:  .venv/bin/python fetch_evidence.py
"""
from __future__ import annotations

import datetime as dt
import glob
import html
import io
import json
import re
import shutil
import sys
import tempfile
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import rdflib

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence"
ONTOLOGY = ((HERE / "ontology") if (HERE / "ontology").is_dir() else Path("/Users/denis/MyAgentsProjects/UniverseIdeas/solutions/grant-packages/NIH_ITS_ABOUT_TIME") / "ontology") / "its-about-time-bitemporal.ttl"
UA = "Mozilla/5.0 (research script; NIH It's About Time stage N1)"
SETID = "aa88f583-4f5f-433b-80b4-1f4c9fb28357"
SPL_VERSIONS = (32, 33, 34, 35, 36)
ACCESS_LOG: list[dict] = []


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch(url: str, purpose: str, data: bytes | None = None, accept: str | None = None,
          max_bytes: int = 2_000_000) -> bytes:
    """Небольшой HTTP-запрос с записью в журнал обращений."""
    headers = {"User-Agent": UA}
    if accept:
        headers["Accept"] = accept
    req = urllib.request.Request(url, data=data, headers=headers)
    for attempt in range(3):  # повтор при таймауте/сетевой ошибке
        ts = now()
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read(max_bytes + 1)
                status = r.status
            break
        except urllib.error.HTTPError as e:
            body, status = b"", e.code
            break
        except (TimeoutError, urllib.error.URLError) as e:
            ACCESS_LOG.append({"url": url, "method": "POST" if data else "GET", "accessed_utc": ts,
                               "http_status": None, "bytes": 0, "purpose": purpose,
                               "error": f"{type(e).__name__}: {e} (attempt {attempt + 1})"})
            if attempt == 2:
                raise
    ACCESS_LOG.append({"url": url, "method": "POST" if data else "GET", "accessed_utc": ts,
                       "http_status": status, "bytes": len(body), "purpose": purpose})
    if len(body) > max_bytes:
        raise RuntimeError(f"response larger than {max_bytes} bytes: {url}")
    return body


def save_json(name: str, obj) -> None:
    (EVIDENCE / name).write_text(json.dumps(obj, indent=1, ensure_ascii=False), encoding="utf-8")


# ----------------------------------------------------------------------------------------------
# DailyMed
# ----------------------------------------------------------------------------------------------
def dailymed() -> None:
    base = "https://dailymed.nlm.nih.gov/dailymed/services/v2"
    spls = json.loads(fetch(f"{base}/spls.json?drug_name=copaxone", "DailyMed: SETID for Copaxone"))
    save_json("dailymed_spls_copaxone.json", spls)
    hist = json.loads(fetch(f"{base}/spls/{SETID}/history.json?pagesize=100", "DailyMed: version history"))
    save_json("dailymed_history_copaxone.json", hist)
    published = {h["spl_version"]: h["published_date"] for h in hist["data"]["history"]}

    H = "{urn:hl7-org:v3}"
    out = []
    tmp = Path(tempfile.mkdtemp(prefix="spl_"))
    try:
        for v in SPL_VERSIONS:
            url = (f"https://dailymed.nlm.nih.gov/dailymed/getFile.cfm?type=zip&setid={SETID}&version={v}")
            blob = fetch(url, f"DailyMed: SPL zip v{v} (metadata extraction only, not stored)")
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                xml_name = [n for n in z.namelist() if n.lower().endswith(".xml")][0]
                z.extract(xml_name, tmp)
            root = ET.parse(tmp / xml_name).getroot()
            codes = [c.get("code") for c in root.iter(H + "code")
                     if c.get("codeSystem") == "2.16.840.1.113883.6.1"]
            mentions = []

            def walk(sec, path):
                c = sec.find(H + "code")
                t = sec.find(H + "title")
                title = re.sub(r"\s+", " ", "".join(t.itertext())).strip() if t is not None else ""
                num = re.match(r"^(\d+(?:\.\d+)?)\b", title)
                code = c.get("code") if c is not None else None
                tag = num.group(1) if num else ("BOXED WARNING" if code == "34066-1" else "")
                p = path + [f"LOINC {code} [{tag}]"]
                own = " ".join("".join(ch.itertext()) for ch in sec if ch.tag != H + "component")
                n = len(re.findall(r"anaphyla", own, re.I))
                if n:
                    mentions.append({"section_path": p, "count": n})
                for comp in sec.findall(H + "component"):
                    for s in comp.findall(H + "section"):
                        walk(s, p)

            for comp in root.find(H + "component").find(H + "structuredBody").findall(H + "component"):
                for s in comp.findall(H + "section"):
                    walk(s, [])
            ingredients = sorted({(i.get("classCode"),
                                   i.find(H + "ingredientSubstance/" + H + "code").get("code"),
                                   i.find(H + "ingredientSubstance/" + H + "name").text)
                                  for i in root.iter(H + "ingredient")
                                  if i.find(H + "ingredientSubstance/" + H + "code") is not None})
            approvals = sorted({i.get("extension") for a in root.iter(H + "approval")
                                for i in a.iter(H + "id") if i.get("extension")})
            out.append({
                "spl_version": int(root.find(H + "versionNumber").get("value")),
                "document_id": root.find(H + "id").get("root"),
                "set_id": root.find(H + "setId").get("root"),
                "spl_effectiveTime": root.find(H + "effectiveTime").get("value"),
                "dailymed_published_date": published[v],
                "boxed_warning_section_LOINC_34066_1_present": "34066-1" in codes,
                "anaphyla_term_mentions_by_section": mentions,
                "ingredients_classCode_UNII_name": [list(x) for x in ingredients],
                "approval_ids": approvals,
                "zip_url": url,
            })
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    save_json("spl_metadata_copaxone.json", {
        "note": "Extracted from SPL XML: identifiers, dates, LOINC section codes, section numbers and counts "
                "of the term anaphyla*. No labeling text stored; zips were processed in a temp dir and deleted.",
        "versions": out})


# ----------------------------------------------------------------------------------------------
# FDA SrLC and Drug Safety Communications (HTML pages -> metadata only)
# ----------------------------------------------------------------------------------------------
def _text_lines(page: str) -> list[str]:
    body = re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S)
    return [l.strip() for l in html.unescape(re.sub(r"<[^>]+>", "\n", body)).split("\n") if l.strip()]


def fda() -> None:
    search_url = ("https://www.accessdata.fda.gov/scripts/cder/safetylabelingchanges/"
                  "index.cfm?event=searchResult.page")
    page = fetch(search_url, "FDA SrLC: search drug_name=copaxone",
                 data=urllib.parse.urlencode({"drug_name": "copaxone", "TextSearch": ""}).encode()
                 ).decode("utf-8", "replace")
    ids = sorted(set(re.findall(r"DrugNameID=(\d+)", page)))
    row = _text_lines(page)
    i = row.index("Database Updated") if "Database Updated" in row else -1
    search_row = row[i + 1:i + 9] if i >= 0 else []

    detail_url = ("https://www.accessdata.fda.gov/scripts/cder/safetylabelingchanges/"
                  f"index.cfm?event=searchdetail.page&DrugNameID={ids[0]}")
    lines = _text_lines(fetch(detail_url, "FDA SrLC: Copaxone detail page").decode("utf-8", "replace"))
    sections = ["Boxed Warning", "Contraindications", "Warnings and Precautions", "Adverse Reactions",
                "Drug Interactions", "Use in Specific Populations", "Patient Counseling Information",
                "Patient Information", "Medication Guide"]
    entries, cur = [], None
    for k in range(lines.index("Expand all"), len(lines)):
        l = lines[k]
        if l.startswith("Questions related to the drug data"):
            break
        if re.fullmatch(r"\d{2}/\d{2}/\d{4}", l) and k + 1 < len(lines) and re.fullmatch(r"\(SUPPL-\d+\)", lines[k + 1]):
            cur = {"approval_date_mmddyyyy": l, "supplement": lines[k + 1].strip("()"),
                   "sections_changed": [], "boxed_warning_newly_added": False}
            entries.append(cur)
            continue
        if cur is None:
            continue
        for s in sections:
            if l.lower() == s.lower() or re.fullmatch(rf"\d+\s+{re.escape(s)}", l, re.I):
                if s not in cur["sections_changed"]:
                    cur["sections_changed"].append(s)
        if l == "Boxed Warning" and k + 1 < len(lines) and lines[k + 1].startswith("Newly added"):
            cur["boxed_warning_newly_added"] = True
    j = lines.index("COPAXONE")
    save_json("srlc_copaxone_metadata.json", {
        "search_url": search_url + " (POST drug_name=copaxone)", "drug_name_ids_found": ids,
        "search_result_row": search_row, "detail_url": detail_url,
        "header": {"drug": lines[j], "application": lines[j + 1].strip("()")},
        "note": "Metadata only (approval dates, supplement numbers, section names parsed heuristically from "
                "headings). The page does NOT state when each entry was first posted, so SrLC availability "
                "time is UNVERIFIED.",
        "entries": entries})

    list_url = "https://www.fda.gov/drugs/drug-safety-and-availability/drug-safety-communications"
    lst = fetch(list_url, "FDA DSC: list page").decode("utf-8", "replace")
    rows = []
    for tr in re.findall(r"<tr.*?</tr>", lst, flags=re.S):
        if "glatiramer" in tr.lower():
            rows.append([html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c))).strip()
                         for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, flags=re.S)])
    dsc_url = ("https://www.fda.gov/drugs/drug-safety-communications/fda-adds-boxed-warning-about-rare-"
               "serious-allergic-reaction-called-anaphylaxis-multiple-sclerosis")
    d = fetch(dsc_url, "FDA DSC: glatiramer communication page").decode("utf-8", "replace")
    save_json("fda_dsc_metadata.json", {
        "list_url": list_url, "list_rows_with_glatiramer": rows, "source_url": dsc_url,
        "title": html.unescape(re.findall(r"<title>(.*?)</title>", d, flags=re.S)[0]).replace(" | FDA", "").strip(),
        "dsc_dates_on_page": sorted(set(re.findall(r"\b(\d{2}-\d{2}-\d{4})\b", d))),
        "page_content_current_as_of": (re.findall(r"Content current as of:.*?(\d{2}/\d{2}/\d{4})", d, flags=re.S) or [None])[0],
        "note": "Metadata only. The communication is dated 2025-01-22; the web page was edited later."})


# ----------------------------------------------------------------------------------------------
# RxNav (RxNorm), ChEBI, MeSH
# ----------------------------------------------------------------------------------------------
def rxnav() -> None:
    base = "https://rxnav.nlm.nih.gov/REST"
    res = {"name_lookup": {}, "concepts": {}, "spl_set_id": {}, "ndcstatus": {}}
    for name in ("glatiramer", "glatiramer acetate", "copaxone"):
        r = json.loads(fetch(f"{base}/rxcui.json?name={urllib.parse.quote(name)}&search=0", f"RxNav: rxcui for {name}"))
        res["name_lookup"][name] = r.get("idGroup", {}).get("rxnormId")
    res["drugs_copaxone"] = [
        {"tty": g["tty"], "rxcui": p["rxcui"], "name": p["name"]}
        for g in json.loads(fetch(f"{base}/drugs.json?name=copaxone", "RxNav: drugs for copaxone"))["drugGroup"].get("conceptGroup", [])
        for p in (g.get("conceptProperties") or [])]
    for c in ("214582", "84375", "135779", "1111642", "1487363"):
        p = json.loads(fetch(f"{base}/rxcui/{c}/properties.json", f"RxNav: properties {c}"))["properties"]
        h = json.loads(fetch(f"{base}/rxcui/{c}/historystatus.json", f"RxNav: history status {c}"))["rxcuiStatusHistory"]
        m = h.get("metaData", {})
        res["concepts"][c] = {"name": p["name"], "tty": p["tty"], "suppress": p.get("suppress"),
                              "status": m.get("status"), "activeStartDate": m.get("activeStartDate"),
                              "activeEndDate": m.get("activeEndDate")}
    for c in ("1111642", "1487363"):
        r = json.loads(fetch(f"{base}/rxcui/{c}/property.json?propName=SPL_SET_ID", f"RxNav: SPL_SET_ID {c}"))
        res["spl_set_id"][c] = [x["propValue"] for x in (r.get("propConceptGroup") or {}).get("propConcept", [])]
    for ndc in ("68546031730", "68546032512"):
        s = json.loads(fetch(f"{base}/ndcstatus.json?ndc={ndc}", f"RxNav: NDC status {ndc}"))["ndcStatus"]
        res["ndcstatus"][ndc] = {k: s.get(k) for k in ("ndc11", "status", "rxcui", "conceptName")}
    save_json("rxnav_glatiramer.json", res)

    chebi = json.loads(fetch("https://www.ebi.ac.uk/chebi/backend/api/public/compound/CHEBI:749565/",
                             "ChEBI API: CHEBI:749565"))
    save_json("chebi_749565.json", {k: chebi.get(k) for k in ("chebi_accession", "name", "stars", "is_released")})

    mesh = {}
    for d in ("D000068717", "D000707", "D009103", "D020529"):
        j = json.loads(fetch(f"https://id.nlm.nih.gov/mesh/{d}.json", f"NLM MeSH RDF: {d}"))
        label = j.get("label") or j.get("rdfs:label")
        if isinstance(label, list):
            label = label[0]
        if isinstance(label, dict):
            label = label.get("@value")
        mesh[d] = label
    save_json("mesh_descriptors.json", mesh)


# ----------------------------------------------------------------------------------------------
# OBO terms (EBI OLS4), Biolink, OWL-Time, PROV-O: terms actually used in the ontology
# ----------------------------------------------------------------------------------------------
def used_iris(prefix: str) -> list[str]:
    g = rdflib.Graph()
    g.parse(ONTOLOGY, format="turtle")
    seen = set()
    for t in g:
        for x in t:
            if isinstance(x, rdflib.URIRef) and str(x).startswith(prefix):
                seen.add(str(x))
    return sorted(seen)


def obo_terms() -> None:
    ont_for = {"BFO": "bfo", "IAO": "iao", "RO": "ro", "MONDO": "mondo", "CHEBI": "chebi"}
    props = {"BFO_0000062", "BFO_0000063", "RO_0000057"}
    out = {}
    for iri in used_iris("http://purl.obolibrary.org/obo/"):
        local = iri.rsplit("/", 1)[1]
        kind = "properties" if local in props else "classes"
        ont = "ro" if local in props else ont_for[local.split("_")[0]]
        enc = urllib.parse.quote(urllib.parse.quote(iri, safe=""), safe="")
        j = json.loads(fetch(f"https://www.ebi.ac.uk/ols4/api/v2/ontologies/{ont}/{kind}/{enc}", f"OLS4: {local}"))

        def vals(key):
            v = j.get(key)
            if v is None:
                return []
            v = v if isinstance(v, list) else [v]
            return [x.get("value") if isinstance(x, dict) else x for x in v]
        out[iri] = {
            "ontology": ont, "kind": kind, "label": vals("label"),
            "is_obsolete": j.get("isObsolete"),
            "rdf_type": vals("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"),
            "subClassOf": [x for x in vals("http://www.w3.org/2000/01/rdf-schema#subClassOf") if isinstance(x, str)],
            "disjointWith": vals("http://www.w3.org/2002/07/owl#disjointWith"),
            "domain": vals("http://www.w3.org/2000/01/rdf-schema#domain"),
            "range": vals("http://www.w3.org/2000/01/rdf-schema#range"),
            "inverseOf": vals("http://www.w3.org/2002/07/owl#inverseOf"),
            "hasDbXref_MESH": [x for x in vals("http://www.geneontology.org/formats/oboInOwl#hasDbXref")
                               if isinstance(x, str) and x.startswith("MESH:")],
        }
    versions = {}
    for ont in sorted(set(ont_for.values())):
        cfg = json.loads(fetch(f"https://www.ebi.ac.uk/ols4/api/ontologies/{ont}", f"OLS4: {ont} version"))["config"]
        versions[ont] = cfg.get("versionIri")
    save_json("obo_terms_ols.json", {"ontology_versions": versions, "terms": out})


def biolink() -> None:
    rel = json.loads(fetch("https://api.github.com/repos/biolink/biolink-model/releases/latest",
                           "GitHub: latest Biolink release"))
    tag = rel.get("tag_name")
    y = fetch(f"https://raw.githubusercontent.com/biolink/biolink-model/{tag}/src/biolink_model/schema/biolink_model.yaml",
              f"Biolink schema YAML {tag}").decode("utf-8")
    lines = y.split("\n")
    sec, cur, terms = None, None, {"classes": {}, "slots": {}}
    for l in lines:
        m = re.match(r"^(\w+):\s*$", l)
        if m:
            sec, cur = m.group(1), None
            continue
        m = re.match(r"^  ([^ #][^:]*):\s*$", l)
        if m and sec in terms:
            cur = m.group(1)
            terms[sec][cur] = {}
            continue
        m = re.match(r"^    (is_a|domain|range):\s*(\S.*)$", l)
        if m and sec in terms and cur:
            terms[sec][cur][m.group(1)] = m.group(2).strip()

    def camel(name):
        return "".join(w[:1].upper() + w[1:] for w in name.split(" "))

    def snake(name):
        return name.replace(" ", "_")
    by_iri = {}
    for n, v in terms["classes"].items():
        by_iri["https://w3id.org/biolink/vocab/" + camel(n)] = {"kind": "class", "name": n, **v}
    for n, v in terms["slots"].items():
        by_iri["https://w3id.org/biolink/vocab/" + snake(n)] = {"kind": "slot", "name": n, **v}
    used = {}
    for iri in used_iris("https://w3id.org/biolink/vocab/"):
        local = iri.rsplit("/", 1)[1]
        body = fetch(iri, f"w3id resolution of biolink:{local}", max_bytes=3_000_000)
        used[iri] = {"in_schema": iri in by_iri, "schema_entry": by_iri.get(iri),
                     "w3id_http_status": ACCESS_LOG[-1]["http_status"]}
    neg = "https://w3id.org/biolink/vocab/NoSuchTermXyz"
    fetch(neg, "w3id negative control (expect 404)")
    infores_yaml = fetch("https://raw.githubusercontent.com/biolink/information-resource-registry/main/infores_catalog.yaml",
                         "Biolink infores catalog").decode("utf-8")
    ids = set(re.findall(r"^\s+id:\s+(infores:\S+)", infores_yaml, flags=re.M))
    infores = {i: (i in ids) for i in ("infores:dailymed", "infores:rxnorm", "infores:chebi", "infores:mesh",
                                       "infores:mondo")}
    infores["fda_srlc_or_dsc_like_ids_found"] = sorted(i for i in ids if re.search(r"srlc|safety-?comm|drug-safety", i))
    save_json("biolink_terms_checked.json", {
        "release_tag": tag, "release_published_at": rel.get("published_at"),
        "yaml_declared_version": (re.findall(r"^version:\s*(\S+)", y, flags=re.M) or [None])[0],
        "license": (re.findall(r"^license:\s*(\S+)", y, flags=re.M) or [None])[0],
        "n_classes": len(terms["classes"]), "n_slots": len(terms["slots"]),
        "used_terms": used, "negative_control_status": ACCESS_LOG[-2]["http_status"],
        "time_type_definition": re.findall(r"^  time type:\n((?:    .*\n)+)", y, flags=re.M)[:1],
        "date_time_related_slots": {n: v for n, v in terms["slots"].items()
                                    if re.search(r"date|time|avail|known|publish|retriev|valid|onset|interval", n, re.I)},
        "infores": infores})


def owl_time_and_prov() -> None:
    t = fetch("https://www.w3.org/2006/time", "W3C OWL-Time (Turtle)", accept="text/turtle").decode("utf-8")
    g = rdflib.Graph()
    g.parse(data=t, format="turtle")
    T = rdflib.Namespace("http://www.w3.org/2006/time#")
    used = {}
    for iri in used_iris(str(T)):
        s = rdflib.URIRef(iri)
        used[iri] = {
            "declared": (s, None, None) in g,
            "types": sorted(g.qname(o) for o in g.objects(s, rdflib.RDF.type)),
            "subClassOf": sorted(g.qname(o) for o in g.objects(s, rdflib.RDFS.subClassOf) if isinstance(o, rdflib.URIRef)),
            "subPropertyOf": sorted(g.qname(o) for o in g.objects(s, rdflib.RDFS.subPropertyOf)),
            "domain": sorted(g.qname(o) for o in g.objects(s, rdflib.RDFS.domain) if isinstance(o, rdflib.URIRef)),
            "range": sorted(g.qname(o) for o in g.objects(s, rdflib.RDFS.range) if isinstance(o, rdflib.URIRef)),
            "disjointWith": sorted(g.qname(o) for o in g.objects(s, rdflib.OWL.disjointWith)),
            "inverseOf": sorted(g.qname(o) for o in g.objects(s, rdflib.OWL.inverseOf)),
        }
    xsd_duration_uses = sum(1 for _ in g.triples((None, None, rdflib.XSD.duration)))
    lic = [str(o) for o in g.objects(rdflib.URIRef("http://www.w3.org/2006/time"), rdflib.DCTERMS.license)]
    p = fetch("https://www.w3.org/ns/prov-o", "W3C PROV-O (Turtle)", accept="text/turtle").decode("utf-8")
    pg = rdflib.Graph()
    pg.parse(data=p, format="turtle")
    P = rdflib.Namespace("http://www.w3.org/ns/prov#")
    prov = {iri: (rdflib.URIRef(iri), None, None) in pg for iri in used_iris(str(P))}
    save_json("w3c_terms_checked.json", {"owl_time_license": lic, "owl_time_triples": len(g),
                                         "owl_time_triples_with_object_xsd_duration": xsd_duration_uses,
                                         "owl_time_used_terms": used, "prov_used_terms_declared": prov})


def licenses() -> None:
    """Лицензии переиспользуемых онтологий (реестр OBO Foundry) и условия RxNav."""
    out = {"obo_foundry_registry": {}, "rxnav_terms": {}}
    for ont in ("mondo", "chebi", "ro", "bfo", "iao"):
        md = fetch(f"https://raw.githubusercontent.com/OBOFoundry/OBOFoundry.github.io/master/ontology/{ont}.md",
                   f"OBO Foundry registry entry: {ont}").decode("utf-8")
        m = re.search(r"^license:\s*\n((?:\s+.*\n){1,3})", md, re.M)
        out["obo_foundry_registry"][ont] = " ".join(m.group(1).split()) if m else None
    tos = fetch("https://lhncbc.nlm.nih.gov/RxNav/TermsofService.html", "RxNav Terms of Service").decode("utf-8", "replace")
    txt = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>|<style.*?</style>", "", tos, flags=re.S))))
    out["rxnav_terms"] = {
        "no_license_needed_phrase_present": "no license is needed to use these APIs" in txt,
        "exception_mentioned": "With one exception" in txt,
        "rate_limit_20_per_second_present": "no more than 20 requests per second" in txt,
    }
    save_json("licenses_checked.json", out)


# ----------------------------------------------------------------------------------------------
# Wayback Machine: верхняя граница времени доступности записей SrLC (решение Дениса 11.10.2026)
# ----------------------------------------------------------------------------------------------
SRLC_DETAIL = ("https://www.accessdata.fda.gov/scripts/cder/safetylabelingchanges/"
               "index.cfm?event=searchdetail.page&DrugNameID=1430")


def wayback() -> None:
    """Снимки страницы SrLC COPAXONE в Internet Archive: какие записи SUPPL видны в каждом снимке.

    Сохраняются только метаданные (время снимка, digest архива, sha256 тела, найденные номера SUPPL и даты
    «MM/DD/YYYY»), HTML не сохраняется. Время первого снимка, где запись видна, — верхняя граница её времени
    доступности: запись была опубликована не позже этого момента (настоящая дата раньше и неизвестна).
    """
    import hashlib
    cdx = ("https://web.archive.org/cdx/search/cdx?url="
           + urllib.parse.quote(SRLC_DETAIL.split("://", 1)[1], safe="")
           + "&output=json&fl=timestamp,statuscode,digest")
    rows = json.loads(fetch(cdx, "Wayback CDX: snapshots of the SrLC COPAXONE page").decode("utf-8"))
    snaps = []
    for ts, status, digest in rows[1:]:
        if status != "200":
            continue
        url = f"https://web.archive.org/web/{ts}id_/{SRLC_DETAIL}"
        body = fetch(url, f"Wayback snapshot {ts} of the SrLC COPAXONE page (metadata only)")
        page = body.decode("utf-8", "replace")
        snaps.append({
            "timestamp": ts,
            "instant_utc": dt.datetime.strptime(ts, "%Y%m%d%H%M%S").strftime("%Y-%m-%dT%H:%M:%SZ"),
            "snapshot_url": f"https://web.archive.org/web/{ts}/{SRLC_DETAIL}",
            "archive_digest": digest,
            "sha256": hashlib.sha256(body).hexdigest(),
            "bytes": len(body),
            "suppl_listed": sorted(set(re.findall(r"SUPPL-(\d+)", page)), key=int),
            "dates_listed": sorted(set(re.findall(r"\b\d{2}/\d{2}/20\d{2}\b", page))),
        })
    first_seen = {}
    for s in sorted(snaps, key=lambda x: x["timestamp"]):
        for n in s["suppl_listed"]:
            first_seen.setdefault(f"SUPPL-{n}", s["instant_utc"])
    save_json("srlc_wayback.json", {
        "page": SRLC_DETAIL, "accessed_utc": now(),
        "rule": "first snapshot listing an entry = upper bound of its availability time (published no later than)",
        "snapshots": snaps, "first_seen_utc": first_seen})


def main() -> int:
    """Без аргументов — все шаги; с аргументами — только названные (журнал дополняется)."""
    EVIDENCE.mkdir(exist_ok=True)
    only = set(sys.argv[1:])
    for f in ("ols_chebi_glatiramer.json", "ols_chebi_749565.json", "rxnav_drugs_copaxone.json"):
        (EVIDENCE / f).unlink(missing_ok=True)
    for f in glob.glob(str(EVIDENCE / "rxnav_hist_*.json")) + glob.glob(str(EVIDENCE / "rxnav_splsetid_*.json")):
        Path(f).unlink()
    steps = [("DailyMed", dailymed), ("FDA", fda), ("RxNav/ChEBI/MeSH", rxnav), ("OBO/OLS", obo_terms),
             ("Biolink", biolink), ("OWL-Time/PROV", owl_time_and_prov), ("Licenses", licenses),
             ("Wayback", wayback)]
    errors = []
    prev = {}
    if only and (EVIDENCE / "access_log.json").exists():
        prev = json.loads((EVIDENCE / "access_log.json").read_text(encoding="utf-8"))
        steps = [s for s in steps if s[0] in only]
    for name, fn in steps:
        try:
            fn()
            print(f"[ok] {name}")
        except Exception as e:  # фиксируем и продолжаем — отчёт покажет, что не удалось
            errors.append(f"{name}: {type(e).__name__}: {e}")
            print(f"[FAIL] {name}: {e}", file=sys.stderr)
    if prev:
        done = {s[0] for s in steps}
        errors = [e for e in prev.get("errors", []) if e.split(":")[0] not in done] + errors
        log = {"generated_utc": prev.get("generated_utc"), "updated_utc": now(), "errors": errors,
               "requests": prev.get("requests", []) + ACCESS_LOG}
    else:
        log = {"generated_utc": now(), "errors": errors, "requests": ACCESS_LOG}
    save_json("access_log.json", log)
    print(f"{len(ACCESS_LOG)} requests, {sum(r['bytes'] for r in ACCESS_LOG)} bytes, errors: {len(errors)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
