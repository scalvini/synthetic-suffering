# Synthetic Suffering

> **Version:** 1.0
> **Last updated:** 6 November 2026

This repository holds a case database of synthetic suffering, compiled by Dr Marco Scalvini (University of the Arts London). Each of the 113 cases records a producer who presented suffering through images or voices generated or altered with AI, first published or circulated between September 2019 and May 2026, in the eleven genres of public communication defined in the search brief. The analysis asks whether the qualified use found in humanitarian communication extends to the other genres.

The research is in preparation, and the database and its readings are provisional.

## The page

`index.html` is a single self-contained page that opens in any browser, and GitHub Pages publishes it at https://scalvini.eu/synthetic-suffering/. Its tabs form two groups.

| Group | Tabs |
|---|---|
| Database | Ledger, Timeline, Search memo, Fields |
| Analysis | Matrix, Map, Questions, Across genres, Method |

A row of the ledger opens the full record of the case, and each count on the analysis tabs lists the cases behind it. The page is set in Helvetica, and it asks search engines not to index it.

## Contents

| Path | What it holds |
|---|---|
| `index.html` | The page, as a complete HTML document |
| `data/synthetic_suffering_cases.csv` | The 113 cases in 26 fields, in UTF-8 with every field quoted |
| `data/synthetic_suffering_cases.xlsx` | The same cases in Excel, with a Codebook sheet that defines the fields and counts the values in use |
| `docs/synthetic_suffering_memo.md` | The search memo, with its assumptions, the coverage by genre, the thirteen key cases and the candidates not entered |
| `docs/synthetic_suffering_readings.md` | The seven readings across the genres and the coding notes, as printed on the page |
| `src/build_page.py` | Builds the page from the CSV and the memo |
| `src/make_xlsx.py` | Builds the Excel file from the CSV |
| `build.sh` | Rebuilds the page, the readings and the Excel file |
| `robots.txt` | Asks crawlers not to index the files where the repository is served at the root of a domain |
| `.nojekyll` | Tells GitHub Pages to publish the files as they are |

## The cases

| Genre | Cases |
|---|---:|
| 1 Humanitarian and NGO | 17 |
| 2 War and conflict | 15 |
| 3 Political communication | 17 |
| 4 Activism and solidarity | 9 |
| 5 Disaster communication | 5 |
| 6 Memorial and historical | 11 |
| 7 Victims' advocacy and legal | 10 |
| 8 Documentary and true crime | 11 |
| 9 Health and medical | 7 |
| 10 Advertising and brand | 4 |
| 11 Forensic and evidentiary | 7 |
| **Total** | **113** |

Of the 113 cases, 71 rest on a primary source, 40 on two secondary sources and 2 are unverified. The search memo gives the searches behind each genre and the reasons for every candidate that was not entered.

## Rebuilding

Run `./build.sh` after any change to the CSV or the memo. The build needs Python 3 with the `markdown` and `openpyxl` packages, and it stops when the data no longer support a reading printed on the page, so that the reading is rewritten before the page is published again.
