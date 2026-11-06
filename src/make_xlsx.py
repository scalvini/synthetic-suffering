"""Write the case database as an Excel workbook with two sheets, Cases and Codebook.
Usage: make_xlsx.py CASES.csv build_page.py OUT.xlsx"""
import ast
import csv
import re
import sys
from collections import Counter

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

csv_path, script_path, out_path = sys.argv[1:4]
rows = list(csv.DictReader(open(csv_path, encoding="utf-8-sig")))
fields = list(rows[0].keys())

# field definitions, coded fields and types of synthesis, as the page states them
tree = ast.parse(open(script_path, encoding="utf-8").read())
consts = {}
for node in tree.body:
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id in ("FIELD_DEFS", "CODED", "SYN_FULL"):
        consts[node.targets[0].id] = ast.literal_eval(node.value)
FIELD_DEFS, CODED, SYN_FULL = consts["FIELD_DEFS"], consts["CODED"], consts["SYN_FULL"]
assert [f for f, _ in FIELD_DEFS] == fields, "field order differs from the CSV"


def collapse(field, v):
    if field in ("Producer type", "Stated purpose") and v.startswith("other ("):
        return "other"
    if field == "Explicit statement that the person shown does not exist" and v.startswith("yes"):
        return "yes"
    if field == 'Evidence of the "liar\'s dividend"':
        return "none found" if v.startswith("none found") else "other entries"
    return v


FONT = "Arial"
base = Font(name=FONT, size=10)
bold = Font(name=FONT, size=10, bold=True)
head_font = Font(name=FONT, size=10, bold=True, color="FFFFFF")
head_fill = PatternFill("solid", fgColor="174E70")
rule = Side(style="thin", color="CBD2CE")
grid = Border(bottom=rule)
wrap_top = Alignment(wrap_text=True, vertical="top")

WIDTHS = {"ID": 7, "Case name": 42, "Date first published or circulated": 14, "Producer": 32, "Producer type": 18,
          "Genre": 28, "Country or context of the suffering depicted": 26, "Country of the producer": 20, "Medium": 11,
          "Tool or model": 20, "What the image depicts": 60, "Type of synthesis": 10, "Truth claim": 26,
          "Stated purpose": 22, "Disclosure": 44, "Justification given by the producer": 50,
          "Participation of the people affected": 22, "Explicit statement that the person shown does not exist": 26,
          "Photorealism": 12, "Reception and debate": 70, "Policy or guideline consequence": 44,
          'Evidence of the "liar\'s dividend"': 44, "Academic discussion": 50, "Sources": 70,
          "Verification status": 20, "Notes for the paper": 80}

wb = Workbook()
ws = wb.active
ws.title = "Cases"
ws.append(fields)
for c in ws[1]:
    c.font, c.fill, c.alignment = head_font, head_fill, Alignment(wrap_text=True, vertical="center")
ws.row_dimensions[1].height = 42
for r in rows:
    ws.append([r[f] for f in fields])
for row in ws.iter_rows(min_row=2):
    for c in row:
        c.font, c.alignment, c.border = base, wrap_top, grid
    ws.row_dimensions[row[0].row].height = 76
for i, f in enumerate(fields, 1):
    ws.column_dimensions[get_column_letter(i)].width = WIDTHS[f]
ws.freeze_panes = "C2"
ws.auto_filter.ref = ws.dimensions

cb = wb.create_sheet("Codebook")
cb["A1"] = "Synthetic Suffering case database: codebook"
cb["A1"].font = Font(name=FONT, size=12, bold=True)
cb["A2"] = (f"Version 2.1, 6 November 2026. {len(rows)} cases in {len(fields)} fields, defined as in the search brief of "
            "26 October 2026; the values in use are counted from the Cases sheet.")
cb["A2"].font = base
cb.append([])
cb.append(["#", "Field", "Definition in the search brief", "Values in use"])
hdr = cb.max_row
for c in cb[hdr]:
    c.font, c.fill, c.alignment = head_font, head_fill, Alignment(vertical="center")
for i, (fld, dfn) in enumerate(FIELD_DEFS, 1):
    if fld in CODED:
        cnt = Counter(collapse(fld, r[fld]) for r in rows)
        key = (lambda kv: int(kv[0].split(".")[0])) if fld == "Genre" else (lambda kv: (-kv[1], kv[0]))
        vals = "; ".join(f"{k} ({n})" for k, n in sorted(cnt.items(), key=key))
    else:
        vals = "free text"
    cb.append([i, fld, dfn or "free text", vals])
cb.append([])
cb.append(["Code", "Type of synthesis", "", "Cases"])
syn_hdr = cb.max_row
for c in cb[syn_hdr]:
    c.font, c.fill = head_font, head_fill
syn = Counter(r["Type of synthesis"][:1] for r in rows)
for k, v in SYN_FULL.items():
    cb.append([k, v, "", syn[k]])
for row in cb.iter_rows(min_row=hdr + 1):
    for c in row:
        if c.row in (hdr, syn_hdr):
            continue
        c.font, c.alignment = (bold if c.column == 2 and c.row < syn_hdr else base), wrap_top
for col, w in zip("ABCD", (6, 34, 60, 70)):
    cb.column_dimensions[col].width = w
cb.freeze_panes = cb.cell(row=hdr + 1, column=1)

wb.properties.title = "Synthetic Suffering case database"
wb.properties.creator = "Marco Scalvini"
wb.save(out_path)
print(f"wrote {out_path}: {len(rows)} cases, {len(fields)} fields, sheets {wb.sheetnames}")
