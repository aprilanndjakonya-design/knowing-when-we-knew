#!/usr/bin/env python3
"""Этап N2, выборочная проверка шага 2: версия-носитель дополнения Boxed Warning подтверждается по SPL XML.

Для выбранных заявок (evidence/srlc_dailymed/<APP>.json) берём версию-носитель (первая версия,
опубликованная не раньше даты одобрения) и предыдущую версию, скачиваем SPL-архивы DailyMed во
временную папку и сравниваем раздел Boxed Warning (LOINC 34066-1): появился ли раздел или изменился
ли его текст (сравнение по хэшу нормализованного текста — сам текст НЕ сохраняется), а также
effectiveTime обеих версий. Итог — evidence/carrier_verification.json.

Исход по заявке: "confirmed" (раздел появился или изменился в версии-носителе), "unchanged"
(раздел есть, но хэш тот же — носитель, вероятно, более поздняя версия или изменение не в тексте
раздела), "no_bw_section" (в носителе нет раздела 34066-1 — странно, разобрать), "error".

Запуск:  .venv/bin/python verify_carriers.py [--sample 20] [--rate 1]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import re
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence"
IN_DIR = EVIDENCE / "srlc_dailymed_bw"
OUT = EVIDENCE / "carrier_verification.json"
UA = "Mozilla/5.0 (research script; NIH It's About Time stage N2; team Bitemporal KG)"
H = "{urn:hl7-org:v3}"
ACCESS_LOG: list[dict] = []


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch(url: str, purpose: str, min_gap: float, state: dict, max_bytes: int = 30_000_000) -> bytes:
    gap = time.monotonic() - state.get("last", 0.0)
    if gap < min_gap:
        time.sleep(min_gap - gap)
    state["last"] = time.monotonic()
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    ts = now()
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            body, status = r.read(max_bytes + 1), r.status
    except urllib.error.HTTPError as e:
        body, status = b"", e.code
    ACCESS_LOG.append({"url": url, "method": "GET", "accessed_utc": ts, "http_status": status, "bytes": len(body),
                       "purpose": purpose})
    if status != 200:
        raise RuntimeError(f"HTTP {status}: {url}")
    if len(body) > max_bytes:
        raise RuntimeError(f"архив больше {max_bytes} байт: {url}")
    return body


def spl_facts(blob: bytes, tmp: Path) -> dict:
    """Метаданные из SPL XML: effectiveTime, версия, есть ли раздел 34066-1 и хэш его текста."""
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        xml_name = [n for n in z.namelist() if n.lower().endswith(".xml")][0]
        z.extract(xml_name, tmp)
    root = ET.parse(tmp / xml_name).getroot()
    (tmp / xml_name).unlink(missing_ok=True)
    bw_texts = []
    for sec in root.iter(H + "section"):
        c = sec.find(H + "code")
        if c is not None and c.get("code") == "34066-1" and c.get("codeSystem") == "2.16.840.1.113883.6.1":
            text = re.sub(r"\s+", " ", "".join(sec.itertext())).strip().lower()
            bw_texts.append(text)
    combined = "\n".join(bw_texts)
    return {
        "spl_version": int(root.find(H + "versionNumber").get("value")),
        "effectiveTime": root.find(H + "effectiveTime").get("value"),
        "bw_section_present": bool(bw_texts),
        "bw_section_count": len(bw_texts),
        "bw_text_sha256": hashlib.sha256(combined.encode("utf-8")).hexdigest() if bw_texts else None,
        "bw_text_chars": len(combined),
    }


def main() -> int:
    global IN_DIR, OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=20)
    ap.add_argument("--rate", type=float, default=1.0)
    ap.add_argument("--apps", nargs="*", default=[], help="конкретные заявки (NDA020622 …)")
    ap.add_argument("--dir", default=str(IN_DIR), help="каталог результатов связки (srlc_dailymed_bw | srlc_dailymed_all)")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    IN_DIR, OUT = Path(args.dir), Path(args.out)
    prev = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"checks": []}
    done = {c["application"] for c in prev["checks"]}
    apps = []
    for p in sorted(IN_DIR.glob("*.json")):
        a = json.loads(p.read_text(encoding="utf-8"))
        if args.apps and a["application"] not in args.apps:
            continue
        if a["application"] in done or not a["labels"]:
            continue
        lab = next((l for l in a["labels"] if l["carrier_version"]), None)
        if lab:
            apps.append((a, lab))
    if not args.apps:
        apps = apps[: args.sample]
    print(f"к проверке: {len(apps)} заявок (готово {len(done)})", flush=True)
    state: dict = {}
    tmp = Path(tempfile.mkdtemp(prefix="spl_verify_"))
    try:
        for a, lab in apps:
            setid, carrier = lab["setid"], lab["carrier_version"]
            versions = [v["spl_version"] for v in lab["versions"]]
            idx = versions.index(carrier["spl_version"])
            prev_v = versions[idx - 1] if idx > 0 else None
            rec = {"application": a["application"], "drug": a["srlc_rows"][0]["drug_name"], "setid": setid,
                   "supplement_date": a["latest_bw_supplement_date"], "carrier": carrier, "previous_version": prev_v,
                   "checked_utc": now()}
            try:
                url_c = f"https://dailymed.nlm.nih.gov/dailymed/getFile.cfm?type=zip&setid={setid}&version={carrier['spl_version']}"
                rec["carrier_spl"] = spl_facts(fetch(url_c, f"DailyMed SPL zip (metadata only) {setid} v{carrier['spl_version']}", 1 / args.rate, state), tmp)
                if prev_v is not None:
                    url_p = f"https://dailymed.nlm.nih.gov/dailymed/getFile.cfm?type=zip&setid={setid}&version={prev_v}"
                    rec["previous_spl"] = spl_facts(fetch(url_p, f"DailyMed SPL zip (metadata only) {setid} v{prev_v}", 1 / args.rate, state), tmp)
                c, p = rec["carrier_spl"], rec.get("previous_spl")
                if not c["bw_section_present"]:
                    rec["verdict"] = "no_bw_section"
                elif p is None or not p["bw_section_present"]:
                    rec["verdict"] = "confirmed"  # раздел появился в носителе (или носитель — первая версия)
                elif p["bw_text_sha256"] != c["bw_text_sha256"]:
                    rec["verdict"] = "confirmed"
                else:
                    rec["verdict"] = "unchanged"
                eff = c["effectiveTime"][:8]
                rec["carrier_effective_vs_supplement"] = (dt.datetime.strptime(eff, "%Y%m%d").date() - dt.date.fromisoformat(a["latest_bw_supplement_date"])).days
            except Exception as e:
                rec["verdict"] = "error"
                rec["error"] = f"{type(e).__name__}: {e}"
            prev["checks"].append(rec)
            print(f"  {rec['application']} {rec['drug'][:28]:28} v{carrier['spl_version']} ← v{prev_v}: {rec['verdict']}"
                  f"{' (eff−suppl ' + str(rec.get('carrier_effective_vs_supplement')) + ' дн)' if 'carrier_effective_vs_supplement' in rec else ''}", flush=True)
            OUT.write_text(json.dumps(prev, indent=1, ensure_ascii=False), encoding="utf-8")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    verdicts = {}
    for c in prev["checks"]:
        verdicts[c["verdict"]] = verdicts.get(c["verdict"], 0) + 1
    prev["summary"] = {"checked": len(prev["checks"]), "verdicts": verdicts, "updated_utc": now(),
                       "note": "Label text is not stored; only LOINC 34066-1 presence, a SHA-256 of the normalised section text, "
                               "effectiveTime and version numbers."}
    OUT.write_text(json.dumps(prev, indent=1, ensure_ascii=False), encoding="utf-8")
    log_path = EVIDENCE / "access_log.json"
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else {"generated_utc": now(), "errors": [], "requests": []}
    log["updated_utc"] = now()
    log["requests"] = log.get("requests", []) + ACCESS_LOG
    log_path.write_text(json.dumps(log, indent=1, ensure_ascii=False), encoding="utf-8")
    print("итог:", json.dumps(prev["summary"]["verdicts"], ensure_ascii=False), f"| {len(ACCESS_LOG)} запросов, {sum(r['bytes'] for r in ACCESS_LOG) // 1_000_000} МБ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
