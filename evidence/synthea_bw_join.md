# Synthea prescriptions vs. Boxed Warning availability windows

Synthea medication codes: 254; matched to ingredients with a BW change (2016–2026): 56 codes, 39 ingredients.

| Count | Value |
|---|---|
| prescriptions_bw_drugs | 9314 |
| prescriptions_other_drugs | 53134 |
| rx_approved_carrier_unknown | 3771 |
| rx_approved_not_yet_in_dailymed | 94 |
| rx_approved_window_doubtful | 703 |
| rx_available | 2962 |
| rx_before_approval | 1784 |

| Ingredient(s) | Prescriptions | before approval | in window (≤180 d) | window doubtful (>180 d) | carrier unknown | available | BW supplements / applications | first BW approval |
|---|---|---|---|---|---|---|---|---|
| METFORMIN | 3225 | 583 | 17 | 0 | 2586 | 39 | 6 / 5 | 2017-04-05 |
| IBUPROFEN | 1753 | 75 | 0 | 320 | 0 | 1358 | 1 / 1 | 2016-05-09 |
| TACROLIMUS | 1012 | 352 | 10 | 0 | 0 | 650 | 2 / 2 | 2018-05-24 |
| ACETAMINOPHEN + OXYCODONE | 843 | 88 | 0 | 0 | 755 | 0 | 2 / 1 | 2016-12-16 |
| OXYCODONE | 684 | 58 | 47 | 69 | 105 | 405 | 22 / 8 | 2016-12-16 |
| FENTANYL | 311 | 25 | 10 | 0 | 124 | 152 | 32 / 11 | 2016-12-16 |
| NAPROXEN | 260 | 68 | 0 | 174 | 0 | 18 | 5 / 5 | 2016-05-09 |
| HYDROCODONE | 240 | 16 | 0 | 116 | 43 | 65 | 5 / 2 | 2016-12-16 |
| METOPROLOL | 206 | 157 | 0 | 14 | 0 | 35 | 1 / 1 | 2022-01-12 |
| TRAMADOL | 189 | 17 | 6 | 0 | 119 | 47 | 9 / 3 | 2016-12-16 |
| ETONOGESTREL | 106 | 99 | 0 | 0 | 0 | 7 | 2 / 1 | 2026-01-16 |
| MEDROXYPROGESTERONE | 96 | 32 | 0 | 0 | 0 | 64 | 1 / 1 | 2019-12-23 |
| OXALIPLATIN | 60 | 51 | 0 | 0 | 9 | 0 | 1 / 1 | 2024-10-31 |
| MIDAZOLAM | 42 | 25 | 0 | 0 | 0 | 17 | 2 / 2 | 2021-02-05 |
| CIPROFLOXACIN | 39 | 7 | 0 | 0 | 0 | 32 | 4 / 4 | 2016-07-26 |
| MEPERIDINE | 36 | 8 | 0 | 0 | 20 | 8 | 6 / 2 | 2016-12-16 |
| VANCOMYCIN | 26 | 16 | 1 | 0 | 8 | 1 | 2 / 1 | 2021-05-28 |
| CLONAZEPAM | 24 | 20 | 0 | 0 | 0 | 4 | 3 / 2 | 2016-12-16 |
| DIAZEPAM | 20 | 15 | 0 | 1 | 0 | 4 | 8 / 4 | 2016-12-16 |
| REMIFENTANIL | 20 | 5 | 0 | 3 | 0 | 12 | 1 / 1 | 2016-12-16 |
| BEVACIZUMAB | 20 | 20 | 0 | 0 | 0 | 0 | 1 / 1 | 2017-12-05 |
| LIRAGLUTIDE | 13 | 1 | 0 | 0 | 0 | 12 | 1 / 1 | 2016-09-22 |
| DOCETAXEL | 11 | 7 | 0 | 0 | 0 | 4 | 4 / 4 | 2019-06-21 |
| MORPHINE | 11 | 2 | 1 | 2 | 0 | 6 | 28 / 14 | 2016-12-16 |
| SUFENTANIL | 10 | 5 | 0 | 0 | 0 | 5 | 1 / 1 | 2016-12-16 |

Prescriptions inside an 'approved but not yet published' window: 94 (unique prescriptions).

| Date | Drug (Synthea) | Ingredient | Reference application | Approval | DailyMed | Window (days) |
|---|---|---|---|---|---|---|
| 2018-05-25 | 24 HR tacrolimus 1 MG Extended Release | TACROLIMUS | NDA050708 (PROGRAF) | 2018-05-24 | 2018-08-10 | 78 |
| 2018-05-31 | 24 HR tacrolimus 1 MG Extended Release | TACROLIMUS | NDA050708 (PROGRAF) | 2018-05-24 | 2018-08-10 | 78 |
| 2018-06-08 | 24 HR tacrolimus 1 MG Extended Release | TACROLIMUS | NDA050708 (PROGRAF) | 2018-05-24 | 2018-08-10 | 78 |
| 2018-07-05 | 24 HR tacrolimus 1 MG Extended Release | TACROLIMUS | NDA050708 (PROGRAF) | 2018-05-24 | 2018-08-10 | 78 |
| 2018-07-06 | 24 HR tacrolimus 1 MG Extended Release | TACROLIMUS | NDA050708 (PROGRAF) | 2018-05-24 | 2018-08-10 | 78 |
| 2018-07-19 | 24 HR tacrolimus 1 MG Extended Release | TACROLIMUS | NDA050708 (PROGRAF) | 2018-05-24 | 2018-08-10 | 78 |
| 2018-07-31 | 24 HR tacrolimus 1 MG Extended Release | TACROLIMUS | NDA050708 (PROGRAF) | 2018-05-24 | 2018-08-10 | 78 |
| 2018-08-03 | 24 HR tacrolimus 1 MG Extended Release | TACROLIMUS | NDA050708 (PROGRAF) | 2018-05-24 | 2018-08-10 | 78 |
| 2018-08-07 | 24 HR tacrolimus 1 MG Extended Release | TACROLIMUS | NDA050708 (PROGRAF) | 2018-05-24 | 2018-08-10 | 78 |
| 2018-08-09 | 24 HR tacrolimus 1 MG Extended Release | TACROLIMUS | NDA050708 (PROGRAF) | 2018-05-24 | 2018-08-10 | 78 |
| 2018-10-06 | Abuse-Deterrent 12 HR oxycodone hydroc | OXYCODONE | NDA208090 (XTAMPZA ER) | 2018-09-18 | 2019-02-25 | 160 |
| 2018-10-08 | Abuse-Deterrent 12 HR oxycodone hydroc | OXYCODONE | NDA208090 (XTAMPZA ER) | 2018-09-18 | 2019-02-25 | 160 |
| 2018-10-09 | Abuse-Deterrent 12 HR oxycodone hydroc | OXYCODONE | NDA208090 (XTAMPZA ER) | 2018-09-18 | 2019-02-25 | 160 |
| 2018-10-11 | Abuse-Deterrent 12 HR oxycodone hydroc | OXYCODONE | NDA208090 (XTAMPZA ER) | 2018-09-18 | 2019-02-25 | 160 |
| 2018-10-12 | Abuse-Deterrent 12 HR oxycodone hydroc | OXYCODONE | NDA208090 (XTAMPZA ER) | 2018-09-18 | 2019-02-25 | 160 |
| 2018-10-16 | Abuse-Deterrent 12 HR oxycodone hydroc | OXYCODONE | NDA208090 (XTAMPZA ER) | 2018-09-18 | 2019-02-25 | 160 |
| 2018-10-31 | Abuse-Deterrent 12 HR oxycodone hydroc | OXYCODONE | NDA208090 (XTAMPZA ER) | 2018-09-18 | 2019-02-25 | 160 |
| 2018-11-10 | Abuse-Deterrent 12 HR oxycodone hydroc | OXYCODONE | NDA208090 (XTAMPZA ER) | 2018-09-18 | 2019-02-25 | 160 |
| 2018-11-11 | Abuse-Deterrent 12 HR oxycodone hydroc | OXYCODONE | NDA208090 (XTAMPZA ER) | 2018-09-18 | 2019-02-25 | 160 |
| 2018-11-17 | Abuse-Deterrent 12 HR oxycodone hydroc | OXYCODONE | NDA208090 (XTAMPZA ER) | 2018-09-18 | 2019-02-25 | 160 |
| 2018-12-06 | Abuse-Deterrent 12 HR oxycodone hydroc | OXYCODONE | NDA208090 (XTAMPZA ER) | 2018-09-18 | 2019-02-25 | 160 |
| 2018-12-08 | Abuse-Deterrent 12 HR oxycodone hydroc | OXYCODONE | NDA208090 (XTAMPZA ER) | 2018-09-18 | 2019-02-25 | 160 |
| 2018-12-15 | Abuse-Deterrent 12 HR oxycodone hydroc | OXYCODONE | NDA208090 (XTAMPZA ER) | 2018-09-18 | 2019-02-25 | 160 |
| 2019-01-05 | Abuse-Deterrent 12 HR oxycodone hydroc | OXYCODONE | NDA208090 (XTAMPZA ER) | 2018-09-18 | 2019-02-25 | 160 |
| 2019-01-12 | Abuse-Deterrent 12 HR oxycodone hydroc | OXYCODONE | NDA208090 (XTAMPZA ER) | 2018-09-18 | 2019-02-25 | 160 |
| 2019-01-16 | Abuse-Deterrent 12 HR oxycodone hydroc | OXYCODONE | NDA208090 (XTAMPZA ER) | 2018-09-18 | 2019-02-25 | 160 |
| 2019-02-07 | Abuse-Deterrent 12 HR oxycodone hydroc | OXYCODONE | NDA208090 (XTAMPZA ER) | 2018-09-18 | 2019-02-25 | 160 |
| 2019-02-09 | Abuse-Deterrent 12 HR oxycodone hydroc | OXYCODONE | NDA208090 (XTAMPZA ER) | 2018-09-18 | 2019-02-25 | 160 |
| 2019-02-15 | Abuse-Deterrent 12 HR oxycodone hydroc | OXYCODONE | NDA208090 (XTAMPZA ER) | 2018-09-18 | 2019-02-25 | 160 |
| 2019-02-16 | Abuse-Deterrent 12 HR oxycodone hydroc | OXYCODONE | NDA208090 (XTAMPZA ER) | 2018-09-18 | 2019-02-25 | 160 |
| 2019-02-18 | Abuse-Deterrent 12 HR oxycodone hydroc | OXYCODONE | NDA208090 (XTAMPZA ER) | 2018-09-18 | 2019-02-25 | 160 |
| 2019-02-19 | Abuse-Deterrent 12 HR oxycodone hydroc | OXYCODONE | NDA208090 (XTAMPZA ER) | 2018-09-18 | 2019-02-25 | 160 |
| 2021-03-24 | 72 HR fentanyl 0.025 MG/HR Transdermal | FENTANYL | NDA022569 (LAZANDA) | 2021-03-04 | 2021-03-31 | 27 |
| 2021-03-25 | 72 HR fentanyl 0.025 MG/HR Transdermal | FENTANYL | NDA022569 (LAZANDA) | 2021-03-04 | 2021-03-31 | 27 |
| 2021-03-25 | 72 HR fentanyl 0.025 MG/HR Transdermal | FENTANYL | NDA022569 (LAZANDA) | 2021-03-04 | 2021-03-31 | 27 |
| 2021-03-29 | 72 HR fentanyl 0.025 MG/HR Transdermal | FENTANYL | NDA022569 (LAZANDA) | 2021-03-04 | 2021-03-31 | 27 |
| 2021-03-30 | 72 HR fentanyl 0.025 MG/HR Transdermal | FENTANYL | NDA022569 (LAZANDA) | 2021-03-04 | 2021-03-31 | 27 |
| 2021-03-30 | 72 HR fentanyl 0.025 MG/HR Transdermal | FENTANYL | NDA022569 (LAZANDA) | 2021-03-04 | 2021-03-31 | 27 |
| 2021-05-05 | 72 HR fentanyl 0.025 MG/HR Transdermal | FENTANYL | NDA202788 (SUBSYS) | 2021-03-04 | 2021-05-06 | 63 |
| 2023-11-29 | methylphenidate hydrochloride 20 MG Or | METHYLPHENIDATE | NDA205489 (COTEMPLA XR-ODT) | 2023-10-13 | 2023-12-01 | 49 |
