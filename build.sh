#!/bin/sh
# Rebuild the page, the readings and the Excel file from the CSV and the search memo.
set -e
cd "$(dirname "$0")"
python3 src/build_page.py data/synthetic_suffering_cases.csv docs/synthetic_suffering_memo.md index.html docs/synthetic_suffering_readings.md
python3 src/make_xlsx.py data/synthetic_suffering_cases.csv src/build_page.py data/synthetic_suffering_cases.xlsx
