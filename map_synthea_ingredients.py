#!/usr/bin/env python3
"""Этап N2, шаг 5: коды назначений Synthea (RxCUI клинических препаратов) → действующие вещества RxNorm.

Synthea пишет в medications.csv CODE = RxCUI (SCD/SBD). База SrLC называет действующее вещество
(«ACTIVE INGREDIENT») и заявку (NDA/BLA референтного препарата), поэтому связка идёт через
ингредиент: RxNav `rxcui/{c}/properties.json` (имя, TTY) и `rxcui/{c}/related.json?tty=IN+PIN+MIN`.
Результат — evidence/synthea_rxcui_ingredients.json: {rxcui: {name, tty, ingredients: [{rxcui, name, tty}]}}.
Условия RxNav: без лицензии, ≤ 20 запросов/с (идём ≤ --rate), атрибуция NLM. Повторный запуск — продолжает.

Запуск:  .venv/bin/python map_synthea_ingredients.py [--rate 2]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence"
MEDS = HERE / "synthea" / "medications.csv"
OUT = EVIDENCE / "synthea_rxcui_ingredients.json"
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rate", type=float, default=2.0)
    args = ap.parse_args()
    throttle = Throttle(args.rate)
    codes: dict[str, int] = {}
    with MEDS.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            codes[row["CODE"]] = codes.get(row["CODE"], 0) + 1
    out = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    todo = [c for c in sorted(codes, key=lambda c: -codes[c]) if c not in out]
    print(f"кодов в назначениях: {len(codes)}, к обработке: {len(todo)}", flush=True)
    t0 = time.time()
    for i, c in enumerate(todo, 1):
        try:
            p = (fetch_json(f"{BASE}/rxcui/{c}/properties.json", f"RxNav: properties {c}", throttle) or {}).get("properties") or {}
            rel = fetch_json(f"{BASE}/rxcui/{c}/related.json?tty=IN+PIN+MIN", f"RxNav: ingredients of {c}", throttle) or {}
            ings = [{"rxcui": x["rxcui"], "name": x["name"], "tty": g["tty"]}
                    for g in ((rel.get("relatedGroup") or {}).get("conceptGroup") or [])
                    for x in (g.get("conceptProperties") or [])]
            out[c] = {"name": p.get("name"), "tty": p.get("tty"), "prescriptions": codes[c], "ingredients": ings}
        except Exception as e:
            ERRORS.append(f"{c}: {type(e).__name__}: {e}")
            print(f"[FAIL] {c}: {e}", file=sys.stderr, flush=True)
        if i % 25 == 0 or i == len(todo):
            OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
            print(f"  {i}/{len(todo)} за {time.time() - t0:.0f} с, ошибок {len(ERRORS)}", flush=True)
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    log_path = EVIDENCE / "access_log.json"
    prev = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else {"generated_utc": now(), "errors": [], "requests": []}
    prev["updated_utc"] = now()
    prev["errors"] = prev.get("errors", []) + [f"map_synthea_ingredients: {e}" for e in ERRORS]
    prev["requests"] = prev.get("requests", []) + ACCESS_LOG
    log_path.write_text(json.dumps(prev, indent=1, ensure_ascii=False), encoding="utf-8")
    with_ing = sum(1 for v in out.values() if v["ingredients"])
    print(f"{len(ACCESS_LOG)} запросов, ошибок {len(ERRORS)}; кодов {len(out)}, с ингредиентами {with_ing}")
    return 1 if ERRORS else 0


if __name__ == "__main__":
    sys.exit(main())
