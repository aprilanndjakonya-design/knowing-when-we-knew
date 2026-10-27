# Delay between approval of a Boxed Warning change and its availability

Applications with a BW change in scope: 70; with a DailyMed label: 67; carrier version not yet published: 2; several set ids: 19.

| Availability channel | n | median (days) | p25 | p75 | p90 | max | share > 7 d | share > 30 d |
|---|---|---|---|---|---|---|---|---|
| DailyMed publication of the carrier label version | 65 | 13 | 11 | 17 | 39 | 112 | 0.923 | 0.169 |
| FDA SrLC database update | 70 | 6.0 | 4 | 8 | 11 | 39 | 0.257 | 0.014 |

| Bucket (days) | DailyMed | SrLC |
|---|---|---|
| <0 | 0 | 0 |
| 0 | 0 | 0 |
| 1–7 | 5 | 52 |
| 8–30 | 49 | 17 |
| 31–90 | 10 | 1 |
| >90 | 1 | 0 |

| Year of latest BW change | n (DailyMed) | median | p90 | share > 30 d |
|---|---|---|---|---|
| 2025 | 34 | 16.0 | 45 | 0.294 |
| 2026 | 31 | 13 | 17 | 0.032 |

Negative SrLC lags (entry updated before the supplement date): 0 — see lag_report.json.

Method: carrier version = first DailyMed version published on/after the supplement approval date (lower bound of the delay; an unrelated version published in between would shorten it). SrLC 'Database Updated' is the last update of the drug's entry (upper bound of availability for the latest supplement only).
