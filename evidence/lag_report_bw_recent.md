# Boxed Warning: approval → DailyMed publication, main table (2023–2026) and the long tail

Applications with a DailyMed lag: 363; classes: {'publication_delay': 321, 'history_gap': 42}.

| Subset | n | median (days) | p25 | p75 | p90 | max | > 7 d | > 30 d | > 90 d |
|---|---|---|---|---|---|---|---|---|---|
| All years, all carriers | 363 | 15 | 11 | 26 | 251 | 3402 | 0.912 | 0.229 | 0.138 |
| All years, publication delay only | 321 | 14 | 11 | 18 | 45 | 2071 | 0.903 | 0.143 | 0.053 |
| All years, history gap only | 42 | 398.0 | 137 | 1384 | 2237 | 3402 | 0.976 | 0.881 | 0.786 |
| **2023–2026, all carriers** | 159 | 14 | 10 | 17 | 37 | 433 | 0.887 | 0.126 | 0.05 |
| **2023–2026, publication delay only (main table)** | 154 | 14.0 | 10 | 17 | 32 | 390 | 0.883 | 0.104 | 0.026 |
| 2023–2026, history gap only | 5 | 143 | 137 | 272 | 433 | 433 | 1.0 | 0.8 | 0.8 |

SrLC 'Database Updated' lag (where the BW supplement is the latest entry): all years n=98, median 5.0; 2023–2026 n=72, median 5.0, p90 18.

Long tail (> 90 days): 50 applications — {'history_gap': 33, 'publication_delay': 17}; by year: {2016: {'publication_delay': 6, 'history_gap': 11}, 2017: {'history_gap': 3}, 2018: {'history_gap': 5, 'publication_delay': 3}, 2019: {'history_gap': 3, 'publication_delay': 1}, 2020: {'history_gap': 4, 'publication_delay': 1}, 2021: {'history_gap': 2, 'publication_delay': 2}, 2022: {'history_gap': 1}, 2023: {'history_gap': 3, 'publication_delay': 2}, 2025: {'publication_delay': 2, 'history_gap': 1}}.

| Year of BW change | n | history gap | publication delay: n | median | p90 | > 30 d |
|---|---|---|---|---|---|---|
| 2016 | 44 | 15 | 29 | 18 | 225 | 0.345 |
| 2017 | 18 | 3 | 15 | 13 | 36 | 0.133 |
| 2018 | 34 | 6 | 28 | 14.0 | 78 | 0.286 |
| 2019 | 33 | 4 | 29 | 14 | 27 | 0.103 |
| 2020 | 23 | 4 | 19 | 12 | 17 | 0.053 |
| 2021 | 39 | 4 | 35 | 15 | 67 | 0.143 |
| 2022 | 13 | 1 | 12 | 15.5 | 21 | 0.083 |
| 2023 | 58 | 3 | 55 | 14 | 33 | 0.109 |
| 2024 | 36 | 0 | 36 | 13.0 | 19 | 0.0 |
| 2025 | 35 | 2 | 33 | 17 | 38 | 0.303 |
| 2026 | 30 | 0 | 30 | 14.0 | 17 | 0.0 |

Longest publication delays (publication_delay class, > 90 days):

| Application | Drug | Approval | Lag (days) | Versions before supplement |
|---|---|---|---|---|
| NDA022549 | ADASUVE | 2016-09-28 | 2071 | 2 |
| NDA022348 | CALDOLOR | 2016-05-09 | 925 | 4 |
| NDA201194 | OXYCODONE HYDROCHLORIDE | 2018-09-18 | 491 | 1 |
| NDA020990 | ZOLOFT | 2016-12-23 | 411 | 15 |
| NDA208653 | APADAZ | 2023-12-15 | 390 | 2 |
| NDA021618 | TINDAMAX | 2019-06-07 | 362 | 1 |
| NDA210833 | SYMPAZAN | 2021-02-05 | 251 | 3 |
| NDA021234 | FLECTOR | 2016-05-09 | 225 | 1 |
| BLA761275 | TYENNE | 2025-02-28 | 217 | 2 |
| NDA022304 | NUCYNTA | 2018-09-18 | 160 | 2 |
| NDA208090 | XTAMPZA ER | 2018-09-18 | 160 | 3 |
| NDA022192 | FANAPT | 2016-05-26 | 144 | 5 |
| NDA020648 | DIASTAT | 2021-02-05 | 137 | 2 |
| NDA202080 | OXAYDO | 2023-12-15 | 136 | 11 |
| NDA020414 | PYRIDOSTIGMINE BROMIDE | 2025-09-26 | 126 | 5 |

Method: history_gap: the first DailyMed version of the set is published after the supplement approval, so the 'carrier' is merely the first archived version and the lag measures the archive gap, not publication delay. publication_delay: the set has versions before the approval; the carrier is the first version on/after it.
