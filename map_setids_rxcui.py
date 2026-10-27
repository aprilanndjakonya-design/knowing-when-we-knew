#!/usr/bin/env python3
"""Этап N2, шаги 4–5: связка этикеток DailyMed (set id) с кодами RxNorm и их историей.

Для каждого set id из evidence/srlc_dailymed/*.json:
  1) RxNav `rxcui.json?idtype=SPL_SET_ID&id=<setid>` → RxCUI продуктов этой этикетки (SCD/SBD и пр.);
  2) RxNav `rxcui/{rxcui}/historystatus.json` → статус и интервал действия кода (activeStart/activeEnd,
     remapped) — «интервал действия кода» для онтологии (шаг 4) и для сопоставления с Synthea (шаг 5):
     назначения Synthea хранят CODE = RxCUI клинического препарата.
Условия RxNav: лицензия не нужна, не больше 20 запросов/с (идём ≤ `--rate`), атрибуция NLM.
Результат: evidence/setid_rxcui.json ({setid: {application, rxcuis: [...]}}) и evidence/rxcui_history.json
({rxcui: {name, tty, status, activeStartDate, activeEndDate, remappedDate?}}). Повторный запуск — продолжает.

Запуск:  .venv/bin/python map_setids_rxcui.py [--rate 2] [--limit N]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence"
IN_DIR = EVIDENCE / "srlc_dailymed_bw"
OUT_SETIDS = EVIDENCE / "setid_rxcui.json"
OUT_HIST = EVIDENCE / "rxcui_history.json"
BASE = "https://rxnav.nlm.nih.gov/REST"
UA = "Mozilla/5.0 (research script; NIH It's About Time stage N2; team Bitemporal KG)"
ACCESS_LOG: list[dict] = []
ERRORS: list[str] = []


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Throttle:
    def __init__(self, rate: float):
        self.min_gap = 1.0 / max(0.1, rate)
        self.last = 0.0

    def wait(self) -> None:
        gap = time.monotonic() - self.last
        if gap < self.min_gap:
            time.sleep(self.min_gap - gap)
        self.last = time.monotonic()


def fetch_json(url: str, purpose: str, throttle: Throttle, retries: int = 4):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    for attempt in range(retries):
        throttle.wait()
        ts = now()
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body, status = r.read(5_000_000), r.status
        except urllib.error.HTTPError as e:
            body, status = b"", e.code
        except (TimeoutError, urllib.error.URLError, ConnectionError) as e:
            ACCESS_LOG.append({"url": url, "method": "GET", "accessed_utc": ts, "http_status": None, "bytes": 0,
                               "purpose": purpose, "error": f"{type(e).__name__}: {e} (attempt {attempt + 1})"})
            time.sleep(2 * (attempt + 1))
            continue
        ACCESS_LOG.append({"url": url, "method": "GET", "accessed_utc": ts, "http_status": status, "bytes": len(body), "purpose": purpose})
        if status == 200:
            return json.loads(body.decode("utf-8")) if body.strip() else {}
        if status == 404:
            return None
        if status in (429, 500, 502, 503, 504):
            time.sleep(5 * (attempt + 1))
            continue
        raise RuntimeError(f"HTTP {status}: {url}")
    raise RuntimeError(f"нет ответа после {retries} попыток: {url}")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rate", type=float, default=2.0)
    ap.add_argument("--limit", type=int, default=0, help="не больше N set id за запуск (0 = все)")
    ap.add_argument("--dir", default=str(IN_DIR))
    args = ap.parse_args()
    in_dir = Path(args.dir)
    throttle = Throttle(args.rate)
    setids = load(OUT_SETIDS)
    hist = load(OUT_HIST)
    todo = []
    for p in sorted(in_dir.glob("*.json")):
        a = json.loads(p.read_text(encoding="utf-8"))
        for l in a["labels"]:
            if l["setid"] and l["setid"] not in setids:
                todo.append((l["setid"], a["application"], l.get("title")))
    if args.limit:
        todo = todo[: args.limit]
    print(f"set id к обработке: {len(todo)} (готово {len(setids)}), RxCUI с историей: {len(hist)}", flush=True)
    t0 = time.time()
    for i, (setid, app, title) in enumerate(todo, 1):
        try:
            r = fetch_json(f"{BASE}/rxcui.json?idtype=SPL_SET_ID&id={setid}", f"RxNav: RxCUI by SPL_SET_ID {setid} ({app})", throttle)
            ids = ((r or {}).get("idGroup") or {}).get("rxnormId") or []
            setids[setid] = {"application": app, "title": title, "rxcuis": ids}
            for c in ids:
                if c in hist:
                    continue
                h = fetch_json(f"{BASE}/rxcui/{c}/historystatus.json", f"RxNav: history status {c}", throttle)
                st = ((h or {}).get("rxcuiStatusHistory") or {})
                meta, attrs = st.get("metaData", {}) or {}, st.get("attributes", {}) or {}
                hist[c] = {"name": attrs.get("name"), "tty": attrs.get("tty"), "status": meta.get("status"),
                           "activeStartDate": meta.get("activeStartDate"), "activeEndDate": meta.get("activeEndDate"),
                           "remappedDate": (st.get("derivedConcepts") or {}).get("remappedDate")}
        except Exception as e:
            ERRORS.append(f"{setid}: {type(e).__name__}: {e}")
            print(f"[FAIL] {setid}: {e}", file=sys.stderr, flush=True)
        if i % 25 == 0 or i == len(todo):
            OUT_SETIDS.write_text(json.dumps(setids, indent=1, ensure_ascii=False), encoding="utf-8")
            OUT_HIST.write_text(json.dumps(hist, indent=1, ensure_ascii=False), encoding="utf-8")
            print(f"  {i}/{len(todo)} за {time.time() - t0:.0f} с, RxCUI {len(hist)}, ошибок {len(ERRORS)}", flush=True)
    OUT_SETIDS.write_text(json.dumps(setids, indent=1, ensure_ascii=False), encoding="utf-8")
    OUT_HIST.write_text(json.dumps(hist, indent=1, ensure_ascii=False), encoding="utf-8")
    log_path = EVIDENCE / "access_log.json"
    prev = load(log_path) or {"generated_utc": now(), "errors": [], "requests": []}
    prev["updated_utc"] = now()
    prev["errors"] = prev.get("errors", []) + [f"map_setids_rxcui: {e}" for e in ERRORS]
    prev["requests"] = prev.get("requests", []) + ACCESS_LOG
    log_path.write_text(json.dumps(prev, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(ACCESS_LOG)} запросов, ошибок {len(ERRORS)}; set id {len(setids)}, RxCUI {len(hist)}")
    return 1 if ERRORS else 0


if __name__ == "__main__":
    sys.exit(main())
