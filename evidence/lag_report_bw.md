# Delay between approval of a Boxed Warning change and its availability

Applications in scope (bw): 530; with a DailyMed label: 401; carrier version not yet published: 38; several set ids: 183.

| Availability channel | n | median (days) | p25 | p75 | p90 | max | share > 7 d | share > 30 d |
|---|---|---|---|---|---|---|---|---|
| DailyMed publication of the carrier label version | 363 | 15 | 11 | 26 | 251 | 3402 | 0.912 | 0.229 |
| FDA SrLC database update | 168 | 6.0 | 4 | 11 | 25 | 187 | 0.339 | 0.089 |

| Bucket (days) | DailyMed | SrLC |
|---|---|---|
| <0 | 0 | 1 |
| 0 | 0 | 1 |
| 1–7 | 32 | 109 |
| 8–30 | 248 | 42 |
| 31–90 | 33 | 8 |
| >90 | 50 | 7 |

| Year of latest BW change | n (DailyMed) | median | p90 | share > 30 d |
|---|---|---|---|---|
| 2016 | 44 | 50.0 | 2237 | 0.523 |
| 2017 | 18 | 13.0 | 283 | 0.278 |
| 2018 | 34 | 14.5 | 491 | 0.412 |
| 2019 | 33 | 15 | 362 | 0.182 |
| 2020 | 23 | 14 | 398 | 0.217 |
| 2021 | 39 | 15 | 72 | 0.205 |
| 2022 | 13 | 16 | 70 | 0.154 |
| 2023 | 58 | 14.0 | 49 | 0.155 |
| 2024 | 36 | 13.0 | 19 | 0.0 |
| 2025 | 35 | 17 | 45 | 0.314 |
| 2026 | 30 | 14.0 | 17 | 0.0 |

Negative SrLC lags (entry updated before the supplement date): 0 — see lag_report.json.

Method: carrier version = first DailyMed version published on/after the supplement approval date (lower bound of the delay; an unrelated version published in between would shorten it). SrLC 'Database Updated' is the last update of the drug's entry: used only where the Boxed Warning supplement is the drug's latest supplement (upper bound of availability).
