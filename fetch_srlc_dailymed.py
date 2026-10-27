#!/usr/bin/env python3
"""Этап N2, шаг 2: связка изменений Boxed Warning (FDA SrLC) с историей версий DailyMed.

Вход — снимок базы SrLC по разделу Boxed Warning за 2016–2026
(`evidence/srlc_bw_sweep_2016_2026.json`, шаг 1). Для каждой заявки (NDA/BLA):
  1) DailyMed `spls.json?application_number=NDA020622` → set id'ы этикеток этой заявки;
  2) `spls/{setid}/history.json` → версии с датами публикации (availability time через DailyMed);
  3) версия-носитель дополнения — ПЕРВАЯ версия, опубликованная не раньше даты одобрения
     дополнения (SrLC «Supplement Date», valid time). Это верхняя оценка доступности и нижняя
     оценка задержки: между одобрением и настоящей версией-носителем могла выйти другая версия.
     Подтверждение по XML (раздел 34066-1) — выборочно, отдельным шагом.
Сохраняется только метаданные: даты, номера, set id. Тексты этикеток не трогаем.
Нагрузка: не больше `--rate` запросов в секунду, повторы с паузой, всё в evidence/access_log.json.

Запуск:  .venv/bin/python fetch_srlc_dailymed.py --from-year 2025 [--limit 50] [--rate 2]
Повторный запуск продолжает с места остановки (готовые заявки лежат в evidence/srlc_dailymed/).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence"
# По умолчанию — снимок ВСЕХ записей SrLC (любой раздел); для BW-списка задать --list/--out.
OUT_DIR = EVIDENCE / "srlc_dailymed_all"
SWEEP = EVIDENCE / "srlc_all_sweep_2016_2026.json"
BASE = "https://dailymed.nlm.nih.gov/dailymed/services/v2"
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
    """GET JSON с журналом; 429/5xx и сетевые ошибки — повтор с нарастающей паузой."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    for attempt in range(retries):
        throttle.wait()
        ts = now()
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read(5_000_000)
                status = r.status
        except urllib.error.HTTPError as e:
            body, status = b"", e.code
        except (TimeoutError, urllib.error.URLError, ConnectionError) as e:
            ACCESS_LOG.append({"url": url, "method": "GET", "accessed_utc": ts, "http_status": None, "bytes": 0,
                               "purpose": purpose, "error": f"{type(e).__name__}: {e} (attempt {attempt + 1})"})
            time.sleep(2 * (attempt + 1))
            continue
        ACCESS_LOG.append({"url": url, "method": "GET", "accessed_utc": ts, "http_status": status,
                           "bytes": len(body), "purpose": purpose})
        if status == 200:
            return json.loads(body.decode("utf-8"))
        if status == 404:
            return None
        if status in (429, 500, 502, 503, 504):
            time.sleep(5 * (attempt + 1))
            continue
        raise RuntimeError(f"HTTP {status}: {url}")
    raise RuntimeError(f"нет ответа после {retries} попыток: {url}")


def parse_mdy(s: str) -> dt.date:
    return dt.datetime.strptime(s, "%m/%d/%Y").date()


def parse_dailymed_date(s: str) -> dt.date | None:
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            pass
    return None


def application_key(row: dict) -> str:
    return f"{row['application_type']}{row['application_number']}"


def process_application(app: str, rows: list[dict], throttle: Throttle) -> dict:
    latest_supplement = max(parse_mdy(r["supplement_date"]) for r in rows)
    database_updated = max(parse_mdy(r["database_updated"]) for r in rows)
    spls = fetch_json(f"{BASE}/spls.json?application_number={urllib.parse.quote(app)}&pagesize=100",
                      f"DailyMed: SPL set ids for {app}", throttle)
    setids = []
    for item in (spls or {}).get("data", []) if spls else []:
        setids.append({"setid": item.get("setid"), "title": item.get("title"),
                       "published_date": item.get("published_date"), "spl_version": item.get("spl_version")})
    labels = []
    for s in setids:
        hist = fetch_json(f"{BASE}/spls/{s['setid']}/history.json", f"DailyMed: history {s['setid']} ({app})", throttle)
        versions = []
        for h in ((hist or {}).get("data", {}) or {}).get("history", []) if hist else []:
            d = parse_dailymed_date(str(h.get("published_date", "")))
            versions.append({"spl_version": h.get("spl_version"), "published_date": d.isoformat() if d else None})
        versions = [v for v in versions if v["published_date"]]
        versions.sort(key=lambda v: (v["published_date"], v["spl_version"] or 0))
        carrier = next((v for v in versions if dt.date.fromisoformat(v["published_date"]) >= latest_supplement), None)
        before = [v for v in versions if dt.date.fromisoformat(v["published_date"]) < latest_supplement]
        labels.append({
            **s,
            "versions": versions,
            "carrier_version": carrier,
            "lag_days_dailymed": ((dt.date.fromisoformat(carrier["published_date"]) - latest_supplement).days
                                  if carrier else None),
            "versions_before_supplement": len(before),
        })
    lags = [l["lag_days_dailymed"] for l in labels if l["lag_days_dailymed"] is not None]
    return {
        "application": app,
        "srlc_rows": rows,
        "latest_bw_supplement_date": latest_supplement.isoformat(),
        "srlc_database_updated": database_updated.isoformat(),
        "lag_days_srlc_database": (database_updated - latest_supplement).days,
        "dailymed_setids": len(setids),
        "labels": labels,
        "lag_days_dailymed_min": min(lags) if lags else None,
        "fetched_utc": now(),
    }


def summarize(results: list[dict]) -> dict:
    lags = [r["lag_days_dailymed_min"] for r in results if r["lag_days_dailymed_min"] is not None]
    srlc = [r["lag_days_srlc_database"] for r in results]
    no_label = [r["application"] for r in results if r["dailymed_setids"] == 0]
    no_carrier = [r["application"] for r in results if r["dailymed_setids"] > 0 and r["lag_days_dailymed_min"] is None]

    def q(xs, p):
        xs = sorted(xs)
        return xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))] if xs else None

    def bucket(xs):
        b = {"0": 0, "1-7": 0, "8-30": 0, "31-90": 0, ">90": 0, "<0": 0}
        for x in xs:
            b["<0" if x < 0 else "0" if x == 0 else "1-7" if x <= 7 else "8-30" if x <= 30 else "31-90" if x <= 90 else ">90"] += 1
        return b
    return {
        "applications": len(results),
        "with_dailymed_label": len(results) - len(no_label),
        "no_dailymed_label": no_label,
        "no_carrier_version_yet": no_carrier,
        "lag_dailymed_days": {"n": len(lags), "median": statistics.median(lags) if lags else None,
                              "p25": q(lags, 0.25), "p75": q(lags, 0.75), "p90": q(lags, 0.9), "max": max(lags) if lags else None,
                              "buckets": bucket(lags)},
        "lag_srlc_database_days": {"n": len(srlc), "median": statistics.median(srlc) if srlc else None,
                                   "p90": q(srlc, 0.9), "buckets": bucket(srlc)},
        "generated_utc": now(),
    }


def main() -> int:
    global SWEEP, OUT_DIR
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-year", type=int, default=2025, help="заявки с последним BW-дополнением не раньше этого года")
    ap.add_argument("--to-year", type=int, default=2100)
    ap.add_argument("--limit", type=int, default=0, help="не больше N заявок за запуск (0 = все)")
    ap.add_argument("--rate", type=float, default=2.0, help="запросов в секунду")
    ap.add_argument("--list", default=str(SWEEP), help="JSON со строками SrLC (rows[])")
    ap.add_argument("--out", default=str(OUT_DIR), help="каталог результатов по заявкам")
    args = ap.parse_args()
    SWEEP, OUT_DIR = Path(args.list), Path(args.out)

    sweep = json.loads(SWEEP.read_text(encoding="utf-8"))["rows"]
    by_app: dict[str, list[dict]] = {}
    for r in sweep:
        y = parse_mdy(r["supplement_date"]).year
        if args.from_year <= y <= args.to_year:
            by_app.setdefault(application_key(r), []).append(r)
    OUT_DIR.mkdir(exist_ok=True)
    todo = [a for a in sorted(by_app) if not (OUT_DIR / f"{a}.json").exists()]
    if args.limit:
        todo = todo[: args.limit]
    print(f"заявок в выборке {len(by_app)}, к обработке {len(todo)}, частота {args.rate}/с", flush=True)
    throttle = Throttle(args.rate)
    t0 = time.time()
    for i, app in enumerate(todo, 1):
        try:
            res = process_application(app, by_app[app], throttle)
            (OUT_DIR / f"{app}.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
        except Exception as e:  # фиксируем и идём дальше; заявка останется в todo следующего запуска
            ERRORS.append(f"{app}: {type(e).__name__}: {e}")
            print(f"[FAIL] {app}: {e}", file=sys.stderr, flush=True)
        if i % 25 == 0 or i == len(todo):
            print(f"  {i}/{len(todo)} за {time.time() - t0:.0f} с, ошибок {len(ERRORS)}", flush=True)

    results = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(OUT_DIR.glob("*.json"))]
    results = [r for r in results if application_key(r["srlc_rows"][0]) in by_app or True]
    summary = summarize(results)
    (OUT_DIR.parent / (OUT_DIR.name + "_summary.json")).write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")

    log_path = EVIDENCE / "access_log.json"
    prev = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else {"generated_utc": now(), "errors": [], "requests": []}
    prev["updated_utc"] = now()
    prev["errors"] = prev.get("errors", []) + [f"fetch_srlc_dailymed: {e}" for e in ERRORS]
    prev["requests"] = prev.get("requests", []) + ACCESS_LOG
    log_path.write_text(json.dumps(prev, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(ACCESS_LOG)} запросов, {sum(r['bytes'] for r in ACCESS_LOG)} байт, ошибок {len(ERRORS)}; "
          f"сводка: {json.dumps(summary['lag_dailymed_days'], ensure_ascii=False)}")
    return 1 if ERRORS else 0


if __name__ == "__main__":
    sys.exit(main())
