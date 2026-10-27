# RxNorm code status (RxNav historystatus) for products linked to the Boxed Warning labels

Codes: 1939 (from 1003 SPL sets; 11 codes per set at the median, max 46; 861 codes shared by several sets).

| Status | BPCK | IN | PIN | SBD | SCD | total |
|---|---|---|---|---|---|---|
| Active | 45 | 503 | 210 | 862 | 319 | 1939 |

| Code active since | n |
|---|---|
| 2006–2015 | 853 |
| ≤2005 (initial RxNorm) | 566 |
| 2016–2020 | 356 |
| 2021–2026 | 164 |

Codes with an end date: 0; remapped: 0.

Synthea medication codes: 254; status: {'Active': 246, 'Obsolete': 8}; term types: {'SBD': 29, 'SCD': 211, 'BPCK': 11, 'MIN': 1, 'SCDC': 1, 'SBDC': 1}; with an end date: 8.

Method: RxNav historystatus for every RxCUI linked from the DailyMed SPL sets of the Boxed Warning applications; activeStartDate 042005 is the first RxNorm release, i.e. the code predates the archive, not the drug.

Validity interval of a code (activeStartDate–activeEndDate) is NOT asserted in the 0.2 module: it needs a new property on iat:DrugProduct in the core (to be agreed in N3); the status is recorded here only.

## Synthea prescriptions on obsolete codes

Synthea (1,000 patients, seed 4242) has 62,448 medication prescriptions; 514 of them (0.8%) use 8 RxNorm codes that RxNav now reports as Obsolete, and 40 prescriptions are dated AFTER the code's activeEndDate (month precision): the code's valid time had already ended when the record was created. This is the record/valid-time mismatch the ontology must represent for drug codes (valid-time interval of the code vs. transaction time of the EHR record).

| RxCUI | Name | Active from | Obsolete since | Prescriptions | after end date | first…last start |
|---|---|---|---|---|---|---|
| 897685 | verapamil hydrochloride 80 MG Oral Tablet [Calan] | 032010 | 042026 | 251 | 11 | 2001-10-17…2026-10-09 |
| 757594 | {28 (norethindrone 0.35 MG Oral Tablet) } Pack [Joli | 032008 | 072022 | 96 | 29 | 2015-11-03…2026-08-25 |
| 749762 | {7 (ethinyl estradiol 0.01 MG Oral Tablet) / 84 (eth | 012008 | 092026 | 81 | 0 | 2006-06-21…2026-03-23 |
| 198767 | pancreatin 600 MG Oral Tablet | 042005 | 072026 | 47 | 0 | 1981-01-27…2026-05-30 |
| 749882 | {7 (inert ingredients 1 MG Oral Tablet) / 21 (mestra | 012008 | 072019 | 18 | 0 | 1977-05-03…1997-06-12 |
| 1723208 | 10 ML alfentanil 0.5 MG/ML Injection | 012016 | 052025 | 8 | 0 | 2018-06-19…2024-07-08 |
| 105078 | penicillin G 375 MG/ML Injectable Solution | 042005 | 022026 | 8 | 0 | 1946-05-12…1964-01-16 |
| 1366343 | levonorgestrel 0.00354 MG/HR Drug Implant | 022013 | 052017 | 5 | 0 | 1993-05-05…2004-07-01 |
