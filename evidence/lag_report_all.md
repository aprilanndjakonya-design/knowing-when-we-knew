# Delay between approval of any safety-related labeling change (any section) and its availability

Applications in scope (all): 1096; with a DailyMed label: 969; carrier version not yet published: 85; several set ids: 359.

| Availability channel | n | median (days) | p25 | p75 | p90 | max | share > 7 d | share > 30 d |
|---|---|---|---|---|---|---|---|---|
| DailyMed publication of the carrier label version | 884 | 14.0 | 10 | 17 | 38 | 450 | 0.873 | 0.129 |
| FDA SrLC database update | 1096 | 7.0 | 4 | 10 | 16 | 90 | 0.365 | 0.044 |

| Bucket (days) | DailyMed | SrLC |
|---|---|---|
| <0 | 0 | 0 |
| 0 | 3 | 8 |
| 1–7 | 109 | 688 |
| 8–30 | 658 | 352 |
| 31–90 | 82 | 48 |
| >90 | 32 | 0 |

| Year of latest BW change | n (DailyMed) | median | p90 | share > 30 d |
|---|---|---|---|---|
| 2025 | 461 | 15 | 53 | 0.213 |
| 2026 | 423 | 13 | 20 | 0.038 |

Negative SrLC lags (entry updated before the supplement date): 0 — see lag_report.json.

Method: carrier version = first DailyMed version published on/after the supplement approval date (lower bound of the delay; an unrelated version published in between would shorten it). SrLC 'Database Updated' is the last update of the drug's entry (upper bound of availability for the latest supplement only).
