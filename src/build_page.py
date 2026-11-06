#!/usr/bin/env python3
"""Build the Synthetic Suffering Cases page from the case CSV and the search memo.

Usage: python3 build_page.py CASES.csv MEMO.md OUT.html [READINGS.md]

The page follows the design of the Biometric Identification archive
(github.com/scalvini/biometric-identification): a masthead with the distribution of
the cases by genre, tabs in two labelled rows (Database and Analysis), a ledger whose
records open in a panel on the right, set in Helvetica throughout.
The grids of the Matrix and Questions tabs follow the findings grid of the biometric article,
with each circle filled by the share of a genre's cases. Every derived value is
computed here by a stated rule, never recoded by hand; the rules are printed on the
Method tab. Re-run this script whenever the CSV or the memo changes, then republish
the page. The optional fourth argument writes the reading paragraphs to a Markdown
file so that check_prose.py can be run on them."""
import csv
import html
import json
import math
import re
import sys
from collections import Counter, OrderedDict, defaultdict
from urllib.parse import urlparse

import markdown

CSV_PATH, MEMO_PATH, OUT_PATH = sys.argv[1:4]
READINGS_PATH = sys.argv[4] if len(sys.argv) > 4 else None
rows = list(csv.DictReader(open(CSV_PATH, encoding="utf-8-sig")))
memo = open(MEMO_PATH, encoding="utf-8").read()
BUILD_DATE = "6 November 2026"
READINGS_VERSION = "2.1"


def esc(s):
    return html.escape(s or "", quote=True)


# ------------------------------------------------------------------ constants

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]

GENRE_FULL_EXTRA = {
    "7": "7. Victims' advocacy and legal settings",
    "11": "11. Forensic reconstruction and evidentiary uses",
}

SYN_SHORT = OrderedDict([
    ("a", "fully generated person"),
    ("b", "composite or typified person"),
    ("c", "depiction of a real, identifiable person"),
    ("d", "real recording altered by AI"),
])
SYN_FULL = {
    "a": "fully generated person (no referent)",
    "b": "composite or typified person presented as representative of a group",
    "c": "generated depiction of a real, identifiable person (for example AI voices or avatars of deceased victims)",
    "d": "real recording altered by AI so that the sufferer's appearance changes (for example deepfake face replacement to protect identity)",
}
# Proposed mapping of the types of synthesis onto the questions of the one-page summary.
SYN_QUESTION = {
    "a": "Question 1, suffering without a sufferer, and question 3, pity toward someone who does not exist",
    "b": "Question 3, pity toward a type, and question 4, a category that can neither consent nor dissent",
    "c": "Question 4, the consent of an actual person, and question 5, the face and grievability of a person who lived",
    "d": "Question 2, the trace and the witness, where a real recording is altered to protect or to replace its subject",
}

VER = OrderedDict([
    ("primary source", ("primary", "Primary source")),
    ("two secondary sources", ("secondary", "Two secondary sources")),
    ("unverified", ("unverified", "Unverified")),
])

TRUTH_ORDER = [
    "none, illustrative",
    "about a real event with no recordings",
    "about a type or category",
    "about a real identifiable person",
    "presented as an authentic recording (undisclosed)",
]
TRUTH_SHORT = {
    "none, illustrative": "Illustrative, no claim",
    "about a real event with no recordings": "A real event, no recordings",
    "about a type or category": "A type or category",
    "about a real identifiable person": "A real, identifiable person",
    "presented as an authentic recording (undisclosed)": "Presented as an authentic recording",
}
DISC_ORDER = ["none", "label", "caption", "statement", "not established"]
PART_ORDER = ["none", "consulted", "co-created", "authored by survivors", "not applicable"]
PROD_LABEL = {"institution": "Named institution", "individual": "Named individual", "anonymous": "Anonymous or fraudulent"}

QUESTIONS = OrderedDict([
    ("responsibility", ("Responsibility of the producer", r"responsib")),
    ("disclosure", ("Harm that survives disclosure", r"survives? disclosure|beyond (?:the )?label|despite (?:the )?(?:label|disclosure)|disclosure (?:did not|does not|cannot|fails)|after disclosure")),
    ("participation", ("Participation as remedy", r"participation")),
    ("evidentiary", ("Evidentiary versus appellative use", r"evidentiary|appellative")),
])

# Region lookup: the first matching place name in the field decides the region.
REGION_RULES = [
    (r"^\s*(?:not |no specific|no country)", "Not specific"),
    (r"gaza|palestin|israel|iran\b|syria|turkey|west asia|lebanon|yemen|iraq|united arab emirates", "Middle East"),
    (r"sudan|chad|burundi|uganda|nigeria|africa", "Africa"),
    (r"colombia|argentina|dominican|latin america|brazil|mexico|jamaica|cuba", "Latin America"),
    (r"cambodia|bangladesh|hong kong|taiwan|india|vietnam|philippines|myanmar|pakistan|sri lanka|malaysia|china|tibet|asia", "Asia"),
    (r"nauru|manus|australia|papua|new zealand|oceania", "Australia and Oceania"),
    (r"canada|united states|mississippi|colorado|north carolina", "North America"),
    (r"ukraine|russia|chechnya|poland|germany|denmark|france|italy|spain|greece|united kingdom|belgium|monaco|netherlands|switzerland|norway|hungary|europe", "Europe"),
    (r"international|various", "International"),
]
NORTH = {"Europe", "North America", "Australia and Oceania", "International"}
SOUTH = {"Middle East", "Africa", "Latin America", "Asia"}

NEG = re.compile(r"\b(?:no|not|none|neither|nor|without)\b", re.I)
REMOVAL = re.compile(r"withdr\w*|took (?:it |them |the \w+ )?down|taken down|deleted|removed|pulled (?:the|it)|retracted", re.I)
APOLOGY = re.compile(r"apolog", re.I)

GROUPS = [
    ("Production", ["Producer", "Producer type", "Country of the producer", "Medium", "Tool or model"]),
    ("Depiction", ["Country or context of the suffering depicted", "What the image depicts",
                "Type of synthesis", "Truth claim", "Photorealism",
                "Explicit statement that the person shown does not exist"]),
    ("Purpose and disclosure", ["Stated purpose", "Disclosure", "Justification given by the producer",
                                "Participation of the people affected"]),
    ("Reception", ["Reception and debate", "Policy or guideline consequence",
                   'Evidence of the "liar\'s dividend"']),
    ("For the paper", ["Notes for the paper", "Academic discussion"]),
    ("Sources", ["Verification status", "Sources"]),
]

FIELD_DEFS = [
    ("ID", "Case identifier. C01 to C13 are the seed cases of Table 2 in the ICS article."),
    ("Case name", "Name of the case."),
    ("Date first published or circulated", "Month and year."),
    ("Producer", "Who made or published the item."),
    ("Producer type", "NGO; UN agency; government; party or candidate; news organisation; activist or collective; individual; law firm; artist; company; other."),
    ("Genre", "One of the eleven genres of public communication in the search brief."),
    ("Country or context of the suffering depicted", ""),
    ("Country of the producer", ""),
    ("Medium", "still image; video; audio; avatar; mixed."),
    ("Tool or model", "If known."),
    ("What the image depicts", "One sentence."),
    ("Type of synthesis", "a, b, c or d, defined below the table."),
    ("Truth claim", "about a real event with no recordings; about a type or category; about a real identifiable person; none, illustrative."),
    ("Stated purpose", "appeal; advocacy; memorial; evidence; illustration; protection of identity; satire; other."),
    ("Disclosure", "none; label; caption; statement; with the wording."),
    ("Justification given by the producer", "Quoted: consent, safety, absence of images, cost, \"no children were harmed\", other."),
    ("Participation of the people affected", "none; consulted; co-created; authored by survivors; not applicable."),
    ("Explicit statement that the person shown does not exist", "yes or no, with the wording."),
    ("Photorealism", "yes or no."),
    ("Reception and debate", "Who criticised, who defended and the main arguments; withdrawal, apology, platform action."),
    ("Policy or guideline consequence", ""),
    ('Evidence of the "liar\'s dividend"', "Real images dismissed as AI in connection with the case."),
    ("Academic discussion", "References."),
    ("Sources", "URLs with access dates, each marked primary, secondary or fact-check."),
    ("Verification status", "primary source (the producer's own publication or statement); two secondary sources (two independent reports); unverified."),
    ("Notes for the paper", "Why the case matters for the argument and which question it speaks to: responsibility of the producer; harm that survives disclosure; participation as remedy; evidentiary versus appellative use."),
]
CODED = {"Producer type", "Genre", "Medium", "Type of synthesis", "Truth claim", "Stated purpose",
         "Participation of the people affected", "Explicit statement that the person shown does not exist",
         "Photorealism", 'Evidence of the "liar\'s dividend"', "Verification status"}

DERIVED_DEFS = [
    ("Producer kind", "Field 5. 'anonymous' if the producer type contains anonymous, fraudulent, unidentified or engagement; 'individual' if it is 'individual'; otherwise 'institution'. A named producer is an institution or an individual."),
    ("Disclosure at origin", "Field 15. The first word of the field (none, label, caption, statement), or 'not established'."),
    ("Presented as authentic", "Field 13. True when the truth claim is 'presented as an authentic recording (undisclosed)'."),
    ("Disclosure in circulation", "Fields 13 and 15. 'none' when the case is presented as authentic, otherwise the disclosure at origin. A case disclosed at origin and presented as authentic is counted as a label lost in circulation."),
    ("Justification given", "Field 16. True unless the field begins with 'none', 'no justification' or 'not stated'."),
    ("People affected involved", "Field 17. True for consulted, co-created and authored by survivors."),
    ("Real person depicted", "Field 12. True for types c and d."),
    ("Policy or guideline consequence", "Field 21. True unless the field begins with 'none' or 'no'."),
    ("Liar's dividend documented", "Field 22. True unless the field begins with 'none found'."),
    ("Removal reported", "Field 20, keyword rule: withdrew, withdrawn, took down, taken down, deleted, removed, pulled or retracted, unless a negation (no, not, none, neither, nor, without) occurs in the 40 characters before the match. Approximate; the matched passage is readable in the record."),
    ("Apology reported", "Field 20, keyword rule: 'apolog', with the same negation test. Approximate."),
    ("Fact-checked", "Field 24. True when at least one source is marked [fact-check]; the number of such sources is counted."),
    ("Questions for the paper", "Field 26, keyword rules: responsibility ('responsib'); harm that survives disclosure ('survives disclosure', 'beyond the label', 'despite the label or disclosure', 'after disclosure'); participation ('participation'); evidentiary versus appellative ('evidentiary', 'appellative')."),
    ("Region of the suffering, region of the producer", "Fields 7 and 8. The first place name in the field that matches the lookup table below decides the region; where the field records the sharers rather than the creator, the sharers' country is used, as the field does."),
    ("Year", "Field 3. The four-digit year in the field; cases with no year are counted as undated."),
    ("Regime of the genre", "Computed for each genre from the cases: 'qualified' when at least half of the genre's cases keep a disclosure in circulation, otherwise 'unqualified'."),
]


# ------------------------------------------------------------------ helpers

URL_RE = re.compile(r"https?://[^\s<>\"]+")


def clean_url(u):
    while u and u[-1] in ".,;:":
        u = u[:-1]
    while u.endswith(")") and u.count("(") < u.count(")"):
        u = u[:-1]
    return u


def linkify(text):
    out, pos = [], 0
    for m in URL_RE.finditer(text):
        u = clean_url(m.group(0))
        out.append(esc(text[pos:m.start()]))
        host = urlparse(u).netloc
        host = host[4:] if host.startswith("www.") else host
        out.append(f'<a href="{esc(u)}" title="{esc(u)}" target="_blank" rel="noopener">{esc(host)}</a>')
        pos = m.start() + len(u)
    out.append(esc(text[pos:]))
    return "".join(out)


def link_ids(s):
    return re.sub(r"(?<![\w#])(C\d{2,3})(?!\d)", r'<a class="cid" href="#\1">\1</a>', s)


def split_top(s, sep="; "):
    parts, depth, buf, i = [], 0, "", 0
    while i < len(s):
        ch = s[i]
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        if depth == 0 and s.startswith(sep, i):
            parts.append(buf)
            buf, i = "", i + len(sep)
            continue
        buf += ch
        i += 1
    parts.append(buf)
    return [p.strip() for p in parts if p.strip()]


def refs_html(s):
    parts = split_top(s)
    if len(parts) > 1 and all(re.search(r"\b(19|20)\d{2}\b", p) for p in parts):
        return '<ul class="refs">' + "".join(f"<li>{linkify(p)}</li>" for p in parts) + "</ul>"
    return f"<p>{linkify(s)}</p>"


SRC_CLASS = {"primary": "s-primary", "secondary": "s-secondary", "fact-check": "s-check"}


def source_kinds(s):
    out = []
    for line in s.split("\n"):
        m = re.match(r"^\[([^\]]+)\]", line.strip())
        out.append(m.group(1) if m else "")
    return out


def sources_html(s):
    items = []
    for line in s.split("\n"):
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^\[([^\]]+)\]\s*(.*)$", line)
        kind, rest = (m.group(1), m.group(2)) if m else ("", line)
        tag = f'<span class="k {SRC_CLASS.get(kind, "s-other")}">{esc(kind)}</span>' if kind else ""
        items.append(f"<li>{tag}{linkify(rest)}</li>")
    return '<ul class="src">' + "".join(items) + "</ul>"


def datekey(s):
    m = re.match(r"^(" + "|".join(MONTHS) + r") (\d{4})", s)
    if m:
        return f"{m.group(2)}-{MONTHS.index(m.group(1)) + 1:02d}"
    m = re.match(r"^(\d{4})", s)
    if m:
        return f"{m.group(1)}-00"
    return ""


def genre_no(g):
    return g.split(".")[0].strip()


def region_of(text, unknown="Not specific"):
    """The place name that occurs first in the field decides the region; a field that begins with
    'not', 'no specific' or 'no country' has no region."""
    t = text.lower()
    if re.search(REGION_RULES[0][0], t):
        return unknown
    best = None
    for pat, reg in REGION_RULES[1:]:
        m = re.search(pat, t)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), reg)
    return best[1] if best else unknown


WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"]


def words(n):
    return WORDS[n] if 0 <= n < len(WORDS) else str(n)


def negated(text, m):
    return bool(NEG.search(text[max(0, m.start() - 40):m.start()]))


def keyword_hit(pattern, text):
    for m in pattern.finditer(text):
        if not negated(text, m):
            return True
    return False


def pct(n, d):
    return f"{round(100 * n / d)}%" if d else ""


def id_runs(ids):
    nums = sorted(int(i[1:]) for i in ids)
    runs, start, prev = [], None, None
    for n in nums + [None]:
        if start is None:
            start = prev = n
            continue
        if n is not None and n == prev + 1:
            prev = n
            continue
        runs.append((start, prev))
        start = prev = n
    out = []
    for a, b in runs:
        if b - a >= 2:
            out.append(f'<a class="cid" href="#C{a:02d}">C{a:02d}</a> to <a class="cid" href="#C{b:02d}">C{b:02d}</a>')
        else:
            out.extend(f'<a class="cid" href="#C{n:02d}">C{n:02d}</a>' for n in range(a, b + 1))
    return ", ".join(out)


def collapse(field, v):
    if field in ("Producer type", "Stated purpose") and v.startswith("other ("):
        return "other"
    if field == "Explicit statement that the person shown does not exist" and v.startswith("yes"):
        return "yes"
    if field == 'Evidence of the "liar\'s dividend"':
        return "none found" if v.startswith("none found") else "other entries"
    return v


def fbtn(filters, label, cls="cell"):
    return f'<button type="button" class="{cls}" data-filter=\'{esc(json.dumps(filters))}\'>{label}</button>'


# ------------------------------------------------------------------ memo

memo_version = re.search(r"\*\*Version:\*\*\s*([\d.]+)", memo).group(1)
memo_date = re.search(r"\*\*Last updated:\*\*\s*(.+)", memo).group(1).strip()

memo_cov = OrderedDict()
memo_total_searches = ""
for line in memo.split("\n"):
    if not line.startswith("| ") or line.startswith("| Genre") or line.startswith("|---"):
        continue
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    if cells[0].startswith("**Total"):
        memo_total_searches = cells[2].strip("*")
        continue
    no = cells[0].split()[0]
    memo_cov[no] = {"short": cells[0], "searches": cells[2], "cases_memo": cells[1]}

key_main, key_box = set(), {}
sec3 = memo.split("## 3.")[1].split("## 4.")[0]
KEY_ENTRIES = re.findall(r"^(\d+)\. \*\*(.+?)\*\*\s*(.+)$", sec3, re.M)
N_KEY = len(KEY_ENTRIES)
for m in re.finditer(r"^(\d+)\. \*\*(.+?)\*\*\s*(.+)$", sec3, re.M):
    n, title, body = m.groups()
    main = re.match(r"(C\d{2,3})", title).group(1)
    item = link_ids(f"<b>{esc(title)}</b> {esc(body)}")
    key_main.add(main)
    key_box[main] = (f"Key case {n} of {N_KEY} in the memo", item)
    for p in re.findall(r"with (C\d{2,3})", title):
        key_box[p] = (f"Paired with {main}, key case {n} of {N_KEY} in the memo", item)

# ------------------------------------------------------------------ derived fields

genre_full = {}
for r in rows:
    genre_full[genre_no(r["Genre"])] = r["Genre"]
genre_full.update({k: v for k, v in GENRE_FULL_EXTRA.items() if k not in genre_full})
genre_short = {no: memo_cov[no]["short"] if no in memo_cov else genre_full[no] for no in genre_full}
GENRES = sorted(genre_full, key=int)
GENRES_WITH = sorted({genre_no(r["Genre"]) for r in rows}, key=int)

D = {}
for r in rows:
    cid = r["ID"]
    pt = r["Producer type"].lower()
    prod = "anonymous" if re.search(r"anonymous|fraudulent|unidentified|engagement", pt) else ("individual" if pt == "individual" else "institution")
    disc = r["Disclosure"].strip().lower().split()[0].rstrip(":,;") if r["Disclosure"].strip() else "not established"
    if disc not in ("none", "label", "caption", "statement"):
        disc = "not established"
    auth = r["Truth claim"].startswith("presented as an authentic recording")
    circ = "none" if auth else disc
    jtxt = r["Justification given by the producer"].strip().lower()
    just = not (jtxt.startswith("none") or jtxt.startswith("no justification") or jtxt.startswith("not stated"))
    part = r["Participation of the people affected"].split(" (")[0].strip()
    syn = r["Type of synthesis"][:1]
    ptxt = r["Policy or guideline consequence"].strip().lower()
    cons = not (ptxt.startswith("none") or ptxt.startswith("no "))
    liar = not r['Evidence of the "liar\'s dividend"'].startswith("none found")
    rec = r["Reception and debate"]
    kinds = source_kinds(r["Sources"])
    notes = r["Notes for the paper"].lower()
    dk = datekey(r["Date first published or circulated"])
    D[cid] = {
        "gno": genre_no(r["Genre"]), "prod": prod, "named": prod != "anonymous",
        "disc": disc, "auth": auth, "circ": circ, "lost": auth and disc in ("label", "caption", "statement"),
        "just": just, "part": part, "involved": part in ("consulted", "co-created", "authored by survivors"),
        "syn": syn, "real": syn in ("c", "d"), "truth": r["Truth claim"],
        "cons": cons, "liar": liar,
        "removal": keyword_hit(REMOVAL, rec), "apology": keyword_hit(APOLOGY, rec),
        "nfact": kinds.count("fact-check"), "fact": kinds.count("fact-check") > 0,
        "q": [k for k, (lab, pat) in QUESTIONS.items() if re.search(pat, notes)],
        "year": dk[:4] if dk else "", "dk": dk,
        "regs": region_of(r["Country or context of the suffering depicted"]),
        "regp": region_of(r["Country of the producer"], "Not established"),
        "ver": VER[r["Verification status"]][0],
        "key": cid in key_main,
    }

by_genre = defaultdict(list)
for r in rows:
    by_genre[D[r["ID"]]["gno"]].append(r)

regime = {}
for g in GENRES_WITH:
    rs = by_genre[g]
    kept = sum(1 for r in rs if D[r["ID"]]["circ"] in ("label", "caption", "statement"))
    regime[g] = "qualified" if kept * 2 >= len(rs) else "unqualified"
for r in rows:
    d = D[r["ID"]]
    d["regime"] = regime[d["gno"]]
    d["group"] = "hum" if d["gno"] == "1" else ("named" if d["regime"] == "qualified" else "other")

for no, info in memo_cov.items():
    got = len(by_genre.get(no, []))
    want = int(re.match(r"\d+", info["cases_memo"]).group(0))
    assert got == want, f"genre {no}: CSV has {got}, memo says {want}"

n_total = len(rows)
ver_counts = Counter(r["Verification status"] for r in rows)
truth_slug = {v: f"t{i + 1}" for i, v in enumerate(TRUTH_ORDER)}
assert set(D[c]["truth"] for c in D) <= set(TRUTH_ORDER)
keys_with_month = sorted(d["dk"] for d in D.values() if d["dk"] and not d["dk"].endswith("-00"))


def month_label(k):
    y, m = k.split("-")
    return f"{MONTHS[int(m) - 1]} {y}"


date_span = f"{month_label(keys_with_month[0])} to {month_label(keys_with_month[-1])}"
YEARS = sorted({d["year"] for d in D.values() if d["year"]})
Q_GENRES = [g for g in GENRES_WITH if regime[g] == "qualified"]
U_GENRES = [g for g in GENRES_WITH if regime[g] == "unqualified"]


def cases_in(genres):
    return [r for r in rows if D[r["ID"]]["gno"] in genres]


def count(rs, key):
    return sum(1 for r in rs if D[r["ID"]][key])


GENRE_PROSE = {"1": "humanitarian communication", "2": "war reporting", "3": "political communication", "4": "activist campaigns",
               "5": "disaster communication", "6": "memorial communication", "7": "victims' advocacy", "8": "documentary and true crime",
               "9": "health campaigns", "10": "advertising", "11": "forensic reconstruction"}


def names(genres):
    labs = [GENRE_PROSE[g] for g in genres]
    return ", ".join(labs[:-1]) + " and " + labs[-1] if len(labs) > 1 else labs[0]


# ------------------------------------------------------------------ statistics for the readings

S = {}
q_rs, u_rs, h_rs = cases_in(Q_GENRES), cases_in(U_GENRES), by_genre["1"]
oq_rs = cases_in([g for g in Q_GENRES if g != "1"])
S.update(n_total=n_total, n_outside=n_total - len(h_rs), n_genres=len(GENRES_WITH), n_q=len(q_rs), n_u=len(u_rs),
         d_q=sum(1 for r in q_rs if D[r["ID"]]["circ"] in ("label", "caption", "statement")),
         j_q=count(q_rs, "just"), p_q=count(q_rs, "involved"), p_u=count(u_rs, "involved"),
         a_u=count(u_rs, "auth"), j_u=count(u_rs, "just"), nm_u=count(u_rs, "named"),
         pol_disc=sum(1 for r in by_genre["3"] if D[r["ID"]]["circ"] in ("label", "caption", "statement")), n_pol=len(by_genre["3"]),
         n_h=len(h_rs), real_h=count(h_rs, "real"), real_oq=count(oq_rs, "real"), n_oq=len(oq_rs),
         lost=count(rows, "lost"), cons_h=count(h_rs, "cons"), cons_q=count(q_rs, "cons"), cons_u=count(u_rs, "cons"),
         rem_q=count(q_rs, "removal"), fc_u=count(u_rs, "fact"), fc_q=count(q_rs, "fact"), liar=count(rows, "liar"), liar_u=count(u_rs, "liar"),
         q_resp=sum(1 for d in D.values() if "responsibility" in d["q"]),
         q_part=sum(1 for d in D.values() if "participation" in d["q"]),
         q_part_q=sum(1 for r in q_rs if "participation" in D[r["ID"]]["q"]),
         q_ev=sum(1 for d in D.values() if "evidentiary" in d["q"]),
         q_ev_h=sum(1 for r in h_rs if "evidentiary" in D[r["ID"]]["q"]),
         q_ev_wd=sum(1 for r in cases_in(["2", "5"]) if "evidentiary" in D[r["ID"]]["q"]),
         q_disc=sum(1 for d in D.values() if "disclosure" in d["q"]),
         ns=sum(1 for d in D.values() if d["regs"] in SOUTH and d["regp"] in NORTH),
         ns_anon=sum(1 for d in D.values() if d["regs"] in SOUTH and d["regp"] == "Not established"),
         south=sum(1 for d in D.values() if d["regs"] in SOUTH))
hy = Counter(D[r["ID"]]["year"] for r in h_rs)
S.update(h2023=hy["2023"], h2024=hy["2024"], h2025=hy["2025"], h2026=hy["2026"])
late = Counter(D[r["ID"]]["gno"] for r in rows if D[r["ID"]]["year"] in ("2025", "2026"))
LATE_GENRES = [g for g in GENRES_WITH if g != "1" and late[g] >= 2]
S["late_genres"], S["late_n"] = names(LATE_GENRES), len(LATE_GENRES)
NOT_SEARCHED_R = [g for g in GENRES if g not in GENRES_WITH]
S["q_names"] = names(Q_GENRES)
S["u_names"] = names(U_GENRES)
pol_rs = by_genre["3"]
vf_rs = cases_in(["7", "11"])
LIAR_Q = [r["ID"] for r in q_rs if D[r["ID"]]["liar"]]
S.update(named_q=count(q_rs, "named"), named_pol=count(pol_rs, "named"),
         inst_pol=sum(1 for r in pol_rs if r["Producer type"] in ("party or candidate", "government", "news organisation")),
         rem_u=count(u_rs, "removal"), none_u=sum(1 for r in u_rs if D[r["ID"]]["disc"] == "none"),
         hum_ur=sum(1 for r in h_rs if D[r["ID"]]["disc"] in ("label", "caption", "statement") and TRUTH_ORDER.index(D[r["ID"]]["truth"]) <= 2),
         q_ev_vf=sum(1 for r in vf_rs if "evidentiary" in D[r["ID"]]["q"]), n_vf=len(vf_rs),
         ss=sum(1 for d in D.values() if d["regs"] in SOUTH and d["regp"] in SOUTH),
         kept4=sum(1 for r in by_genre["4"] if D[r["ID"]]["circ"] in ("label", "caption", "statement")), n4=len(by_genre["4"]))
GENRES_PHRASE = ("all eleven genres of the search brief" if S["n_genres"] == 11 else
                 f"{words(S['n_genres'])} of the eleven genres of the search brief" + (f", of which {words(len(NOT_SEARCHED_R))} {'has' if len(NOT_SEARCHED_R) == 1 else 'have'} not yet been searched" if NOT_SEARCHED_R else ""))
LIAR_REST = ("" if not LIAR_Q else
             f", and the remaining {'one' if len(LIAR_Q) == 1 else words(len(LIAR_Q))} ({', '.join(LIAR_Q)}) {'belongs' if len(LIAR_Q) == 1 else 'belong'} to "
             + names(sorted({D[c]['gno'] for c in LIAR_Q}, key=int)))

# The readings state the pattern of the data of version 2.0 (113 cases). Each claim that is not a bare count is
# checked below, so that a later round of searching that breaks it stops the build until the prose is rewritten.
STOP = ("The readings in READINGS describe the pattern of the data of version 2.0. The new data break it, so rewrite the "
        "readings (and the EV evidence buttons) before rebuilding: ")
assert regime["1"] == "qualified" and regime["3"] == "unqualified", STOP + "humanitarian communication must be qualified and political communication unqualified: " + str(regime)
assert regime["4"] == "qualified", STOP + "activist campaigns are no longer in the qualified regime (coding note on regimes)"
assert S["real_h"] == 0, STOP + f"{S['real_h']} humanitarian cases now depict a real person"
assert 2 * S["named_pol"] > S["n_pol"] and 2 * S["inst_pol"] > S["named_pol"], STOP + "most producers of political communication are no longer named parties, governments or news organisations"
assert 2 * S["named_q"] > S["n_q"] and S["named_q"] * S["n_u"] > S["nm_u"] * S["n_q"], STOP + "named producers are no longer more frequent in the qualified regime"
assert S["h2023"] == max(hy.values()), STOP + "the humanitarian cases no longer cluster in 2023"
assert all(regime.get(g) == "unqualified" and 2 * count(by_genre[g], "auth") > len(by_genre[g]) for g in ("2", "5")), STOP + "war reporting or disaster communication no longer present most images as recordings"
assert 2 * S["hum_ur"] > S["n_h"] and 2 * S["a_u"] > S["n_u"] and 2 * S["none_u"] > S["n_u"], STOP + "the positions on the map have changed"
assert S["fc_u"] * S["n_q"] > S["fc_q"] * S["n_u"] and 2 * S["liar_u"] > S["liar"], STOP + "fact-checking or the liar's dividend no longer concentrate in the unqualified regime"
assert S["ns_anon"] > max(S["ns"], S["ss"]), STOP + "producers that could not be established are no longer the largest group for suffering in the South"

READINGS = {
    "overview": [
        f"Synthetic suffering appears in {GENRES_PHRASE}, and {S['n_outside']} of the {S['n_total']} cases lie outside humanitarian communication. "
        f"The cases divide into two regimes by a single rule, which asks whether at least half of a genre's cases kept a disclosure when the image circulated. "
        f"The qualified regime contains {S['q_names']}. "
        f"In this regime the producer discloses the synthesis in {S['d_q']} of {S['n_q']} cases, gives a justification in {S['j_q']} and involves the people affected in {S['p_q']}. "
        f"The unqualified regime contains {S['u_names']}. "
        f"In this regime the image is presented as an authentic recording in {S['a_u']} of {S['n_u']} cases, a justification is given in {S['j_u']} and the people affected take part in {S['p_u']}.",
        f"Political communication belongs to the unqualified regime, since a disclosure accompanies only {S['pol_disc']} of its {S['n_pol']} cases, although the producer is named in {S['named_pol']} of them and is a party, a government or a news organisation in {S['inst_pol']}. "
        f"The genre therefore tests the responsibility of the producer where no qualification is offered. "
        f"The producer is named in {S['named_q']} of the {S['n_q']} qualified cases against {S['nm_u']} of the {S['n_u']} unqualified cases, so the description of humanitarian use as selective and heavily qualified extends to most genres whose producers put their name to the image, while the qualified genres differ in who is depicted. "
        f"Humanitarian images depict no real person in all {S['n_h']} cases, whereas the images of the other qualified genres depict real people in {S['real_oq']} of {S['n_oq']} cases.",
    ],
    "timeline": [
        f"The humanitarian cases cluster in 2023, when {S['h2023']} of the {S['n_h']} were first published, and {S['cons_h']} of the {S['n_h']} were followed by a policy or guideline consequence. "
        f"After 2023 the humanitarian cases fall to {S['h2024']} in 2024 and to {S['h2025'] + S['h2026']} in 2025 and 2026 together. "
        f"In those two years {words(S['late_n'])} other genres have at least two cases each, namely {S['late_genres']}. "
        f"The record therefore supports both readings of the sector at once, since humanitarian organisations tested the technique in one year and then qualified or withdrew its uses. "
        f"Production meanwhile moved to other genres and, within war reporting and disaster communication, to accounts that present the image as a recording.",
    ],
    "map": [
        f"The map places each case by the disclosure at origin and by the claim made about the image, so that qualification can be read as a position. "
        f"The humanitarian cases occupy mainly the upper right, where a statement or a label accompanies an image that stands for a type or for an event without recordings, as {S['hum_ur']} of the {S['n_h']} do. "
        f"The unqualified genres occupy mainly the bottom row and the first column, since {S['a_u']} of their {S['n_u']} cases were presented as authentic recordings and {S['none_u']} carried no disclosure at origin. "
        f"{words(S['lost']).capitalize()} cases carried a disclosure at origin and still circulated as authentic recordings, which shows that a disclosure does not travel with the image.",
    ],
    "debate": [
        f"The debate differs between the regimes in kind more than in volume. "
        f"A policy or guideline consequence followed {S['cons_q']} of the {S['n_q']} qualified cases and {S['cons_u']} of the {S['n_u']} unqualified cases, and a removal or a withdrawal is reported in {S['rem_q']} qualified and {S['rem_u']} unqualified cases. "
        f"In the unqualified regime the debate consists largely of fact-checking, since fact-checking organisations examined {S['fc_u']} of its {S['n_u']} cases against {S['fc_q']} of the {S['n_q']} qualified cases. "
        f"{words(S['liar_u']).capitalize()} of the {words(S['liar'])} documented instances of the liar's dividend occur in the unqualified regime, where real images were dismissed as synthetic after synthetic images had circulated as real{LIAR_REST}.",
    ],
    "paper": [
        f"The notes relate each case to the four questions of the joint paper, and the counts show where each question has its material. "
        f"The responsibility of the producer arises in {S['q_resp']} cases across every genre, whereas participation as remedy arises in {S['q_part']} cases, {S['q_part_q']} of them in the qualified regime. "
        f"The distinction between evidentiary and appellative use arises in {S['q_ev']} cases, {S['q_ev_h']} of them in humanitarian communication, {S['q_ev_wd']} in war reporting and disaster communication and {S['q_ev_vf']} of the {S['n_vf']} in victims' advocacy and forensic reconstruction, where courts, police forces and families confront it directly. "
        f"The type of synthesis relates the cases to the philosophical questions of the one-page summary. "
        f"Depictions of generated and typified people raise the question of suffering without a sufferer, whereas depictions of real people raise the questions of consent and of the face.",
        f"The regions answer the question of the imbalance between the Global North and the Global South. "
        f"The suffering depicted lies in the Middle East, Africa, Latin America or Asia in {S['south']} cases. "
        f"The producer is in the Global North (Europe, North America, Oceania or an international organisation) in {S['ns']} of them and in the regions depicted in {S['ss']}, while in {S['ns_anon']}, the largest group, it could not be established. "
        f"The imbalance in authorship is therefore hidden in the largest group, where the producer is anonymous, and among named producers those in the regions depicted "
        + ("outnumber" if S["ss"] > S["ns"] else ("equal" if S["ss"] == S["ns"] else "are outnumbered by")) + " those in the North.",
    ],
}

CODING_NOTES = [
    "C01 and C02 are typed b although their descriptions state that the people depicted are fully generated. The type records what the person depicted stands for rather than how the image was made, and in both cases the person depicted stands for a group.",
    "Disclosure in circulation is derived from two fields, since a case whose truth claim is 'presented as an authentic recording (undisclosed)' is recorded as undisclosed in circulation whatever its disclosure at origin.",
    f"{words(sum(1 for d in D.values() if d['dk'].endswith('-00'))).capitalize()} cases carry a year without a month and {words(sum(1 for d in D.values() if not d['dk']))} carry no date. The timeline places the cases dated by year alone in the middle of that year as hollow marks, and it places the undated cases in a separate column.",
    "The keyword rules for removal and apology are approximate, because the reception field is prose; the matched passages are readable in the record of each case, and the policy consequence comes from its own field.",
    f"The regime of a genre is a property of the sample, not of the genre. Activist campaigns moved from the unqualified to the qualified regime in the second round of searching, when {words(S['kept4'])} of their {words(S['n4'])} cases kept a disclosure in circulation, close to the threshold of half.",
]


# ================================================================== presentation
# The layer below follows the Biometric Identification archive. Colours of the genres were
# checked with the dataviz palette validator against white: adjacent genres in genre order
# keep a colour-vision distance of at least 11.7 and a normal-vision distance of at least 15.2.

GENRE_COLOR = OrderedDict([
    ("1", "#1C6A9C"), ("2", "#B8433A"), ("3", "#5A5DBA"), ("4", "#C47A2C"), ("5", "#C0457E"),
    ("6", "#9C8000"), ("7", "#9A3F6F"), ("8", "#2A9D84"), ("9", "#82408F"), ("10", "#4C8A2E"), ("11", "#3B7DD8"),
])
GENRE_TAG = {"1": "Humanitarian", "2": "War", "3": "Political", "4": "Activism", "5": "Disaster", "6": "Memorial",
             "7": "Victims' advocacy", "8": "Documentary", "9": "Health", "10": "Advertising", "11": "Forensic"}
DISCLOSED = ("label", "caption", "statement")
NOT_SEARCHED = [g for g in GENRES if g not in GENRES_WITH]
GRID_GENRES = Q_GENRES + U_GENRES


def gvar(g):
    return f"var(--g{g})" if g in GENRE_COLOR else "var(--ink-3)"


def nice_date(s):
    m = re.match(r"^(" + "|".join(MONTHS) + r") (\d{4})$", s)
    if m:
        return f"{m.group(1)[:3]} {m.group(2)}", False
    m = re.match(r"^(\d{4})", s)
    if m:
        return m.group(1), True
    return "n.d.", True


def short_producer(s):
    s = s.strip()
    cut = len(s)
    for sep in (" (", ", ", "; ", ": ", ". "):
        i = s.find(sep)
        if 0 < i < cut:
            cut = i
    out = s[:cut].strip()
    if len(out) > 64:
        out = out[:61].rsplit(" ", 1)[0] + "…"
    return out


QRE = re.compile(r"&quot;([^<]{1,400}?)&quot;")


def quoted(h):
    """Mark the quotations inside a field, as the biometric page marks its excerpts."""
    return QRE.sub(r'<q class="sq">\1</q>', h)


def first_quote(s):
    m = re.search(r'"([^"]{3,160})"', s)
    return m.group(1) if m else ""


syn_counts = Counter(D[c]["syn"] for c in D)
truth_counts = Counter(D[c]["truth"] for c in D)

# ------------------------------------------------------------------ attributes and filters

A = {}
for r in rows:
    cid = r["ID"]
    d = D[cid]
    A[cid] = {
        "n": int(cid[1:]), "genre": d["gno"], "syn": d["syn"], "truth": truth_slug[d["truth"]], "ver": d["ver"],
        "key": 1 if d["key"] else 0, "d": d["dk"], "year": d["year"] or "undated", "name": r["Case name"].lower(),
        "prod": d["prod"], "named": int(d["named"]), "disc": d["disc"].replace(" ", "-"), "circ": d["circ"].replace(" ", "-"),
        "auth": int(d["auth"]), "lost": int(d["lost"]), "just": int(d["just"]), "part": d["part"].replace(" ", "-"),
        "inv": int(d["involved"]), "real": int(d["real"]), "cons": int(d["cons"]), "liar": int(d["liar"]),
        "rem": int(d["removal"]), "apo": int(d["apology"]), "fact": int(d["fact"]), "q": " ".join(d["q"]),
        "regs": d["regs"], "regp": d["regp"], "regime": d["regime"], "group": d["group"],
        "south": int(d["regs"] in SOUTH), "north": int(d["regp"] in NORTH),
    }


def attr_ok(a, k, v):
    """The same test as the page script, so that every count printed here opens the same cases."""
    if k == "discl":
        return a["disc"] in DISCLOSED
    if k == "circl":
        return a["circ"] in DISCLOSED
    if k == "q":
        return v in a["q"].split()
    neg = v.startswith("!")
    vals = (v[1:] if neg else v).split("|")
    hit = str(a.get(k, "")) in vals
    return not hit if neg else hit


def matches(a, filt):
    return all(attr_ok(a, k, str(v)) for k, v in filt.items())


def n_match(filt):
    return sum(1 for a in A.values() if matches(a, filt))


def fattr(filt):
    return esc(json.dumps(filt, ensure_ascii=False))


# ------------------------------------------------------------------ masthead

n_key = sum(1 for d in D.values() if d["key"])
bar = "".join(
    f'<span style="width:{100 * len(by_genre[g]) / n_total:.3f}%;background:{gvar(g)}" title="{esc(genre_short[g])}: {len(by_genre[g])}"></span>'
    for g in GENRES_WITH)
bar_label = ", ".join(f"{genre_short[g]} {len(by_genre[g])}" for g in GENRES_WITH)
legend = "".join(
    f'<span><span class="dot" style="background:{gvar(g)}"></span>{esc(genre_short[g])} <b>{len(by_genre[g])}</b></span>'
    for g in GENRES_WITH)
legend += "".join(
    f'<span class="ns"><span class="dot hollow"></span>{esc(genre_short[g])} <i>not searched</i></span>' for g in NOT_SEARCHED)
STATS = [("Cases", n_total), ("Genres with cases", len(GENRES_WITH)), ("Outside humanitarian", S["n_outside"]),
         ("Primary source", ver_counts["primary source"]), ("Two secondary", ver_counts["two secondary sources"]),
         ("Unverified", ver_counts["unverified"]), ("Key cases", n_key), ("Searches", memo_total_searches)]
stats_html = "".join(f"<div><dt>{esc(k)}</dt><dd>{esc(str(v))}</dd></div>" for k, v in STATS)

LEDE = (f"The database records {n_total} cases in which a producer presented suffering through images or voices generated or altered with AI, "
        f"first published or circulated between {date_span.replace(' to ', ' and ')}. "
        "The analysis asks whether the qualified use found in humanitarian communication extends to the other genres.")
NOT_SEARCHED_TEXT = ("" if not NOT_SEARCHED else (f"genre {NOT_SEARCHED[0]} not yet searched" if len(NOT_SEARCHED) == 1
                     else "genres " + " and ".join(NOT_SEARCHED) + " not yet searched"))

# ------------------------------------------------------------------ ledger

genre_chips = "".join(
    f'<button type="button" class="chip" data-set="genres" data-v="{g}" aria-pressed="false"><span class="dot" style="background:{gvar(g)}"></span>'
    f'{esc(GENRE_TAG[g])} <span class="n">{len(by_genre[g])}</span></button>' for g in GENRES_WITH)
syn_chips = "".join(
    f'<button type="button" class="chip" data-set="syns" data-v="{k}" aria-pressed="false" title="{esc(SYN_FULL[k])}"><span class="mono code">{k}</span>'
    f'{esc(SYN_SHORT[k])} <span class="n">{syn_counts[k]}</span></button>' for k in SYN_SHORT)
ver_chips = "".join(
    f'<button type="button" class="chip" data-set="vers" data-v="{c}" aria-pressed="false"><span class="vdot v-{c}"></span>{esc(l)} '
    f'<span class="n">{ver_counts[k]}</span></button>' for k, (c, l) in VER.items())


def row_html(r):
    cid = r["ID"]
    d = D[cid]
    g = d["gno"]
    raw = r["Date first published or circulated"]
    date, approx = nice_date(raw)
    vcls, vlabel = VER[r["Verification status"]]
    tags = []
    if d["key"]:
        tags.append('<span class="tag key">Key case</span>')
    tags.append(f'<span class="tag v-{vcls}">{esc(vlabel)}</span>')
    data = " ".join(f'data-{k}="{esc(str(v))}"' for k, v in A[cid].items())
    star = "*" if approx and date != "n.d." else ""
    return (
        f'<div class="row" role="button" tabindex="0" data-id="{cid}" {data}>'
        f'<div class="meta"><span class="date" title="{esc(raw)}">{esc(date)}{star}</span>'
        f'<span class="gen"><span class="dot" style="background:{gvar(g)}"></span>{esc(GENRE_TAG[g])}</span>'
        f'<span class="syn" title="{esc(SYN_FULL[d["syn"]])}">{d["syn"]}</span></div>'
        f'<div class="main"><div class="title">{esc(r["Case name"])}</div>'
        f'<div class="sub">{esc(short_producer(r["Producer"]))} &middot; <span class="mono">{cid}</span></div></div>'
        f'<div class="badges">{"".join(tags)}</div></div>'
    )


ledger_rows = "\n".join(row_html(r) for r in rows)

# ------------------------------------------------------------------ records for the panel


def field_value(fld, v, syn, vcls, vlabel):
    if fld == "Sources":
        return sources_html(v)
    if fld == "Academic discussion":
        return quoted(refs_html(v))
    if fld == "Verification status":
        return f'<span class="tag v-{vcls}">{esc(vlabel)}</span>'
    if fld == "Type of synthesis":
        return f'<span class="mono">{esc(v)}</span> <span class="muted">{esc(SYN_FULL[syn])}</span>'
    return quoted(linkify(v))


def record(r):
    cid = r["ID"]
    d = D[cid]
    g = d["gno"]
    vcls, vlabel = VER[r["Verification status"]]
    parts = []
    if cid in key_box:
        lab, item = key_box[cid]
        parts.append(f'<div class="dnote"><p class="dnl">{esc(lab)}</p><p>{quoted(item)}</p></div>')
    tags = [f'<span class="tag rg-{d["regime"]}">{esc(d["regime"].capitalize())} regime</span>',
            f'<span class="tag v-{vcls}">{esc(vlabel)}</span>']
    if d["key"]:
        tags.insert(0, '<span class="tag key">Key case</span>')
    parts.append('<div class="dtags">' + "".join(tags) + "</div>")
    head = [("ID", f'<span class="mono">{cid}</span><button class="copy" type="button" data-copy="{cid}">Copy</button>'),
            ("Date", esc(r["Date first published or circulated"])), ("Genre", esc(r["Genre"]))]
    parts.append('<dl class="dl">' + "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in head) + "</dl>")
    for title, fields in GROUPS:
        dl = "".join(f"<dt>{esc(f)}</dt><dd>{field_value(f, r[f], d['syn'], vcls, vlabel)}</dd>" for f in fields)
        parts.append(f'<section class="dgrp"><h4>{esc(title)}</h4><dl class="dl">{dl}</dl></section>')
    der = [
        ("Regime of the genre", d["regime"]),
        ("Producer kind", PROD_LABEL[d["prod"]].lower()),
        ("Disclosure at origin", d["disc"]),
        ("Disclosure in circulation", d["circ"] + (" (label lost in circulation)" if d["lost"] else "")),
        ("Justification given", "yes" if d["just"] else "no"),
        ("People affected involved", "yes" if d["involved"] else "no"),
        ("Real person depicted", "yes" if d["real"] else "no"),
        ("Policy or guideline consequence", "yes" if d["cons"] else "no"),
        ("Removal reported, apology reported", ("yes" if d["removal"] else "no") + ", " + ("yes" if d["apology"] else "no")),
        ("Fact-checked", f"yes ({d['nfact']} {'fact-check' if d['nfact'] == 1 else 'fact-checks'} among the sources)" if d["fact"] else "no"),
        ("Liar's dividend documented", "yes" if d["liar"] else "no"),
        ("Questions for the paper", ", ".join(QUESTIONS[k][0].lower() for k in d["q"]) or "none matched"),
        ("Region of the suffering, region of the producer", f"{d['regs']}; {d['regp']}"),
    ]
    parts.append('<section class="dgrp"><h4>Derived by rule</h4><dl class="dl">' +
                 "".join(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in der) + "</dl></section>")
    eyebrow = f'<span class="dot" style="background:{gvar(g)}"></span>{esc(genre_short[g])} &middot; {cid}'
    blob = " ".join([cid] + [r[f] for f in r]).lower()
    blob = re.sub(r"\s+", " ", blob)
    return {"t": r["Case name"], "e": eyebrow, "b": "".join(parts), "s": blob}


RECS = {r["ID"]: record(r) for r in rows}
recs_json = json.dumps(RECS, ensure_ascii=False).replace("</", "<\\/")

# ------------------------------------------------------------------ timeline (lanes by genre)


def timeline_svg():
    rad, gap = 6.5, 3.0
    step = 2 * rad + gap
    years_in = [int(d["dk"][:4]) for d in D.values() if d["dk"]]
    Y0, Y1 = min(years_in), max(years_in) + 1
    left, pxm, months = 182, 10.0, 12 * (Y1 - Y0)
    plot_r = left + months * pxm
    nd_x0 = plot_r + 18
    nd_w = 58
    W = nd_x0 + nd_w + 10
    top = 40

    def xpos(d):
        dk = d["dk"]
        if not dk:
            return nd_x0 + nd_w / 2
        y, m = int(dk[:4]), int(dk[5:])
        if m == 0:
            return left + ((y - Y0) * 12 + 6) * pxm
        return left + ((y - Y0) * 12 + (m - 1) + 0.5) * pxm

    lanes = []
    for g in GENRES_WITH:
        items = sorted(by_genre[g], key=lambda r: (xpos(D[r["ID"]]), int(r["ID"][1:])))
        placed = []
        for r in items:
            x = xpos(D[r["ID"]])
            for k in (0, -1, 1, -2, 2, -3, 3, -4, 4):
                y = k * step
                if all(((x - px) ** 2 + (y - py) ** 2) ** 0.5 >= 2 * rad + 1.5 for px, py, _ in placed):
                    placed.append((x, y, r))
                    break
        kmax = max(abs(p[1]) for p in placed) / step if placed else 0
        lanes.append((g, placed, max(54, (2 * kmax + 1) * step + 22)))
    H = top + sum(h for _, _, h in lanes) + 12
    out = [f'<svg id="tl" viewBox="0 0 {W:.0f} {H:.0f}" role="group" aria-label="Cases by date and genre">']
    for y in range(Y0, Y1 + 1):
        x = left + (y - Y0) * 12 * pxm
        out.append(f'<line class="grid" x1="{x:.1f}" y1="{top - 14}" x2="{x:.1f}" y2="{H - 6:.0f}"/>')
        if y < Y1:
            out.append(f'<text class="yr" x="{x + 6:.1f}" y="{top - 20}">{y}</text>')
    out.append(f'<line class="grid dash" x1="{nd_x0 - 8:.1f}" y1="{top - 14}" x2="{nd_x0 - 8:.1f}" y2="{H - 6:.0f}"/>')
    out.append(f'<text class="yr" x="{nd_x0 + nd_w / 2:.1f}" y="{top - 20}" text-anchor="middle">n.d.</text>')
    cy0 = top
    for g, placed, h in lanes:
        cy = cy0 + h / 2
        out.append(f'<line class="lane" x1="{left}" y1="{cy:.1f}" x2="{plot_r:.1f}" y2="{cy:.1f}"/>')
        out.append(f'<text class="lbl" x="12" y="{cy + 5:.1f}">{esc(GENRE_TAG[g])}</text>')
        out.append(f'<text class="lbn" x="{left - 14}" y="{cy + 5:.1f}" text-anchor="end">{len(by_genre[g])}</text>')
        for x, dy, r in placed:
            cid = r["ID"]
            d = D[cid]
            yy = cy + dy
            approx = (not d["dk"]) or d["dk"].endswith("-00")
            tip = f"{cid} {r['Case name']}, {r['Date first published or circulated']}"
            fill = "var(--bg)" if approx else gvar(g)
            stroke = gvar(g) if approx else "var(--bg)"
            out.append(
                f'<g class="pt" tabindex="0" role="button" data-id="{cid}" data-cons="{int(d["cons"])}" data-key="{int(d["key"])}" '
                f'data-auth="{int(d["auth"])}" data-lost="{int(d["lost"])}" aria-label="{esc(tip)}"><title>{esc(tip)}</title>'
                f'<circle class="ring" cx="{x:.1f}" cy="{yy:.1f}" r="{rad + 3.6:.1f}"/>'
                f'<circle class="mk{" hol" if approx else ""}" cx="{x:.1f}" cy="{yy:.1f}" r="{rad}" style="fill:{fill};stroke:{stroke}"/></g>')
        cy0 += h
    out.append("</svg>")
    return "".join(out)


RING_OPTS = [("cons", "Policy or guideline consequence"), ("key", "Key cases in the memo"), ("auth", "Presented as authentic"),
             ("lost", "Label lost in circulation"), ("none", "No ring")]
RING_N = {"cons": count(rows, "cons"), "key": n_key, "auth": count(rows, "auth"), "lost": S["lost"]}
ring_opts = "".join(f'<option value="{k}">{esc(l)}{f" ({RING_N[k]})" if k in RING_N else ""}</option>' for k, l in RING_OPTS)
timeline_html = (
    f'<div class="tlbar"><label class="flabel" for="ring">Ring</label><select id="ring">{ring_opts}</select>'
    '<span class="tlkey"><svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true"><circle cx="9" cy="9" r="5" class="kfill"/></svg>dated to the month'
    '<svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true"><circle cx="9" cy="9" r="5" class="khol"/></svg>dated by year alone, or n.d.'
    '<svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true"><circle cx="9" cy="9" r="4" class="kfill"/><circle cx="9" cy="9" r="7.6" class="kring"/></svg>ringed</span></div>'
    '<div class="tl-wrap">' + timeline_svg() + "</div>"
)

# ------------------------------------------------------------------ grids in the manner of the biometric article


def ball(k, n, size=28):
    c = size / 2
    rr = c - 2
    if n == 0:
        return ""
    share = k / n
    base = f'<circle cx="{c}" cy="{c}" r="{rr}" class="b0"/>'
    if share <= 0:
        return f'<svg class="ball" viewBox="0 0 {size} {size}" width="{size}" height="{size}" aria-hidden="true">{base}</svg>'
    if share >= 1:
        return f'<svg class="ball" viewBox="0 0 {size} {size}" width="{size}" height="{size}" aria-hidden="true"><circle cx="{c}" cy="{c}" r="{rr}" class="b1"/></svg>'

    a = 2 * math.pi * share
    x, y = c + rr * math.sin(a), c - rr * math.cos(a)
    large = 1 if share > 0.5 else 0
    wedge = f'<path class="bw" d="M{c},{c} L{c},{c - rr} A{rr},{rr} 0 {large} 1 {x:.2f},{y:.2f} Z"/>'
    return f'<svg class="ball" viewBox="0 0 {size} {size}" width="{size}" height="{size}" aria-hidden="true">{base}{wedge}<circle cx="{c}" cy="{c}" r="{rr}" class="bo"/></svg>'


NA_MARK = '<svg class="na" viewBox="0 0 28 28" width="28" height="28" aria-hidden="true"><line x1="7" y1="14" x2="21" y2="14"/></svg>'


def grid_cell(filt, g, label):
    n = len(by_genre.get(g, [])) if g != "all" else n_total
    full = dict(filt) if g == "all" else {**filt, "genre": g}
    k = n_match(full)
    who = "All genres" if g == "all" else GENRE_TAG[g]
    return (f'<td class="gc{" sep" if g in (GRID_GENRES[0], U_GENRES[0], "all") else ""}">'
            f'<button type="button" class="bcell" data-filter="{fattr(full)}" aria-label="{esc(who)}, {esc(label)}: {k} of {n} cases">'
            f'{ball(k, n)}<span class="bn">{k}/{n}</span></button></td>')


def grid_table(groups, first_head):
    head1 = (f'<tr class="h1"><th></th><th class="gl sep" colspan="{len(Q_GENRES)}">Qualified regime</th>'
             f'<th class="gl sep" colspan="{len(U_GENRES)}">Unqualified regime</th>'
             + ('<th class="gl sep">Not searched</th>' if NOT_SEARCHED else "")
             + '<th class="gl sep">All</th></tr>')
    cols = []
    for g in GRID_GENRES:
        cols.append(f'<th class="gh{" sep" if g in (GRID_GENRES[0], U_GENRES[0]) else ""}"><span class="gt"><span class="dot" style="background:{gvar(g)}"></span>{esc(GENRE_TAG[g])}</span>'
                    f'<span class="gs">{len(by_genre[g])} cases</span></th>')
    if NOT_SEARCHED:
        cols.append(f'<th class="gh dim sep"><span class="gt"><span class="dot hollow"></span>{" and ".join(NOT_SEARCHED)}</span><span class="gs">genres</span></th>')
    cols.append(f'<th class="gh sep"><span class="gt">All genres</span><span class="gs">{n_total} cases</span></th>')
    head2 = f'<tr class="h2"><th class="rh">{esc(first_head)}</th>' + "".join(cols) + "</tr>"
    body = []
    ncols = len(GRID_GENRES) + (1 if NOT_SEARCHED else 0) + 2
    for gtitle, gsub, items in groups:
        body.append(f'<tr class="grow"><th colspan="{ncols}"><b>{esc(gtitle)}</b>{f" <i>{esc(gsub)}</i>" if gsub else ""}</th></tr>')
        for label, sub, filt in items:
            cells = "".join(grid_cell(filt, g, label) for g in GRID_GENRES)
            cells += f'<td class="gc na-c sep">{NA_MARK}</td>' if NOT_SEARCHED else ""
            cells += grid_cell(filt, "all", label)
            body.append(f'<tr><th class="rl" scope="row"><span class="rn">{esc(label)}</span><span class="rs">{esc(sub)}</span></th>{cells}</tr>')
    return f'<div class="tbl-wrap grid-wrap"><table class="grid">' + f"<thead>{head1}{head2}</thead><tbody>{''.join(body)}</tbody></table></div>"


GRID_LEGEND = (
    '<div class="glegend">'
    f'<span>{ball(1, 1, 22)}All cases of the genre</span><span>{ball(1, 2, 22)}Half of them</span>'
    f'<span>{ball(0, 1, 22)}None of them</span><span>{NA_MARK}Not searched</span></div>'
)

MATRIX_GROUPS = [
    ("Producer and disclosure", "", [
        ("Named producer", "producer type, field 5", {"named": "1"}),
        ("Disclosed at origin", "disclosure, field 15", {"discl": "1"}),
        ("Still disclosed in circulation", "truth claim and disclosure, fields 13 and 15", {"circl": "1"}),
        ("Justification given", "justification, field 16", {"just": "1"}),
        ("People affected involved", "participation, field 17", {"inv": "1"}),
        ("Named, disclosed and justified", "fields 5, 13, 15 and 16", {"named": "1", "circl": "1", "just": "1"}),
    ]),
    ("Depiction", "", [
        ("Presented as authentic", "truth claim, field 13", {"auth": "1"}),
        ("Real person depicted", "type of synthesis c or d, field 12", {"real": "1"}),
    ]),
    ("Reception", "", [
        ("Removal reported", "reception, field 20, keyword rule", {"rem": "1"}),
        ("Apology reported", "reception, field 20, keyword rule", {"apo": "1"}),
        ("Policy or guideline consequence", "field 21", {"cons": "1"}),
        ("Fact-checked", "sources marked fact-check, field 24", {"fact": "1"}),
        ("Liar's dividend documented", "field 22", {"liar": "1"}),
    ]),
    ("Sources", "", [
        ("Unverified", "verification status, field 25", {"ver": "unverified"}),
    ]),
]
LIAR_FIELD = 'Evidence of the "liar\'s dividend"'
liar_items = "".join(
    f'<li style="--gc:{gvar(D[r["ID"]]["gno"])}"><button type="button" class="lnk" data-case="{r["ID"]}"><span class="mono">{r["ID"]}</span> {esc(r["Case name"])}</button>'
    f'<p>{quoted(linkify(r[LIAR_FIELD]))}</p></li>'
    for r in rows if D[r["ID"]]["liar"])
matrix_html = (
    '<p class="intro">Each circle shows the share of a genre\'s cases that carry the element named in its row, and the numbers under it give the count of those cases and the genre\'s total. '
    "Selecting a circle lists those cases in the Ledger, and the Method tab gives the rule by which each element is derived from the fields.</p>"
    + grid_table(MATRIX_GROUPS, "Element") + GRID_LEGEND
    + '<p class="tnote">A genre belongs to the qualified regime when at least half of its cases keep a disclosure in circulation, and the dotted lines separate the two regimes' + (" from the genres not yet searched.</p>" if NOT_SEARCHED else ".</p>")
    + '<div class="section"><h2>The documented instances of the liar\'s dividend</h2><ul class="liar">' + liar_items + "</ul></div>"
)

QUESTION_GROUPS = [
    ("The four questions of the joint paper", "", [(lab, "notes for the paper, field 26", {"q": k}) for k, (lab, pat) in QUESTIONS.items()]),
]
SYN_GROUPS = [
    ("Who is depicted", "", [(f"{k} {SYN_SHORT[k]}", "speaks to " + SYN_QUESTION[k][0].lower() + SYN_QUESTION[k][1:] + " (proposed)", {"syn": k}) for k in SYN_SHORT]),
]


def hexrgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


REG_ORDER = ["Middle East", "Africa", "Latin America", "Asia", "Europe", "North America", "Australia and Oceania", "International", "Not specific", "Not established"]
regs_present = [x for x in REG_ORDER if any(d["regs"] == x for d in D.values())]
regp_present = [x for x in REG_ORDER if any(d["regp"] == x for d in D.values())]
reg_max = max(sum(1 for d in D.values() if d["regs"] == a and d["regp"] == b) for a in regs_present for b in regp_present)
ar, ag_, ab = hexrgb("#174E70")
reg_rows = []
for rs_ in regs_present:
    cells = []
    for rp in regp_present:
        v = sum(1 for d in D.values() if d["regs"] == rs_ and d["regp"] == rp)
        if not v:
            cells.append('<td class="cell zero">&middot;</td>')
            continue
        al = 0.08 + 0.72 * v / reg_max
        ink = "#FFFFFF" if al > 0.5 else "var(--ink)"
        cells.append(f'<td class="cell hit" style="background:rgba({ar},{ag_},{ab},{al:.2f});color:{ink}">'
                     f'<button type="button" class="cbtn" data-filter="{fattr({"regs": rs_, "regp": rp})}" aria-label="Suffering in {esc(rs_)}, producer in {esc(rp)}: {v}">{v}</button></td>')
    tot = sum(1 for d in D.values() if d["regs"] == rs_)
    south = " south" if rs_ in SOUTH else ""
    reg_rows.append(f'<tr class="{south.strip()}"><td class="dname">{esc(rs_)}</td>{"".join(cells)}'
                    f'<td class="num"><button type="button" class="cbtn" data-filter="{fattr({"regs": rs_})}">{tot}</button></td></tr>')
regtable = (
    '<div class="tbl-wrap"><table class="regions"><thead><tr><th>Suffering depicted in</th>'
    + "".join(f'<th class="num">{esc(rp)}</th>' for rp in regp_present) + '<th class="num">All</th></tr></thead><tbody>'
    + "".join(reg_rows) + "</tbody></table></div>"
)
questions_html = (
    '<p class="intro">The notes for the paper relate each case to the four questions of the joint paper, and a case can bear on several questions at once. '
    "The second grid relates the type of synthesis to the questions of the one-page summary, and the table below it compares the region of the suffering with the region of the producer.</p>"
    + grid_table(QUESTION_GROUPS, "Question")
    + '<p class="tnote">A case counts for a question when its notes for the paper name the question, by the keyword rules given on the Method tab.</p>'
    + grid_table(SYN_GROUPS, "Type of synthesis") + GRID_LEGEND
    + '<p class="tnote">The links in italics under each type of synthesis are proposed links to the questions of the one-page summary.</p>'
    + '<div class="section"><h2>Where the suffering is and where the producer is</h2>' + regtable
    + '<p class="tnote">The columns give the region of the producer, or of the sharers where the field records them, and the Method tab gives the lookup table.</p></div>'
)

# ------------------------------------------------------------------ qualification map


def dot(x, y, d, r):
    shape = d["prod"]
    st = f'style="fill:{gvar(d["gno"])}"'
    if shape == "institution":
        return f'<circle class="dt" cx="{x:.1f}" cy="{y:.1f}" r="{r}" {st}/>'
    if shape == "individual":
        return f'<path class="dt" d="M{x:.1f},{y - r - 1:.1f} L{x + r + 1:.1f},{y:.1f} L{x:.1f},{y + r + 1:.1f} L{x - r - 1:.1f},{y:.1f} Z" {st}/>'
    return f'<rect class="dt" x="{x - r:.1f}" y="{y - r:.1f}" width="{2 * r}" height="{2 * r}" {st}/>'


def map_svg(rs, big=True):
    cw, ch = (136, 96) if big else (24, 19)
    left, top = (178, 52) if big else (0, 0)
    r = 6 if big else 3
    step = 17 if big else 7.5
    per_row = 7 if big else 3
    W = left + cw * len(DISC_ORDER) + (8 if big else 0)
    H = top + ch * len(TRUTH_ORDER) + (8 if big else 0)
    p = [f'<svg class="map{"" if big else " mini"}" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="{"group" if big else "img"}" aria-label="Qualification map">']
    for i in range(len(DISC_ORDER) + 1):
        x = left + i * cw
        p.append(f'<line class="grid{" dash" if i == len(DISC_ORDER) - 1 else ""}" x1="{x}" x2="{x}" y1="{top}" y2="{top + ch * len(TRUTH_ORDER)}"/>')
    for j in range(len(TRUTH_ORDER) + 1):
        y = top + j * ch
        p.append(f'<line class="grid" x1="{left}" x2="{left + cw * len(DISC_ORDER)}" y1="{y}" y2="{y}"/>')
    if big:
        for i, dc in enumerate(DISC_ORDER):
            p.append(f'<text class="axl" x="{left + i * cw + cw / 2:.1f}" y="{top - 12}" text-anchor="middle">{esc(dc.capitalize())}</text>')
        p.append(f'<text class="axt" x="{left}" y="{top - 34}">DISCLOSURE AT ORIGIN</text>')
        for j, tc in enumerate(TRUTH_ORDER):
            lab = TRUTH_SHORT[tc]
            wds = lab.split()
            lines = [" ".join(wds[:3]), " ".join(wds[3:])] if len(wds) > 3 else [lab]
            y0 = top + j * ch + ch / 2 - (7 if len(lines) > 1 else 0)
            for k, ln in enumerate(lines):
                p.append(f'<text class="axl" x="{left - 12}" y="{y0 + k * 15 + 5:.1f}" text-anchor="end">{esc(ln)}</text>')
    cells = defaultdict(list)
    for rr in rs:
        d = D[rr["ID"]]
        cells[(d["disc"], d["truth"])].append(rr)
    for (dc, tc), items in cells.items():
        i, j = DISC_ORDER.index(dc), TRUTH_ORDER.index(tc)
        x0 = left + i * cw + (16 if big else 4.5)
        y0 = top + j * ch + (18 if big else 5)
        for k, rr in enumerate(sorted(items, key=lambda z: int(z["ID"][1:]))):
            d = D[rr["ID"]]
            x = x0 + (k % per_row) * step
            y = y0 + (k // per_row) * step
            if big:
                tip = f"{rr['ID']} {rr['Case name']} ({genre_short[d['gno']]}; {PROD_LABEL[d['prod']].lower()})"
                p.append(f'<g class="pt mdot" tabindex="0" role="button" data-id="{rr["ID"]}" aria-label="{esc(tip)}"><title>{esc(tip)}</title>{dot(x, y, d, r)}</g>')
            else:
                p.append(dot(x, y, d, r))
    p.append("</svg>")
    return "".join(p)


map_legend = (
    '<div class="maplegend">'
    + "".join(f'<span><span class="dot" style="background:{gvar(g)}"></span>{esc(GENRE_TAG[g])}</span>' for g in GENRES_WITH)
    + '<span class="sepv" aria-hidden="true"></span>'
    '<span><svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><circle class="shape" cx="7" cy="7" r="5.5"/></svg>Named institution</span>'
    '<span><svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path class="shape" d="M7,0.8 L13.2,7 L7,13.2 L0.8,7 Z"/></svg>Named individual</span>'
    '<span><svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><rect class="shape" x="1.5" y="1.5" width="11" height="11"/></svg>Anonymous or fraudulent</span>'
    "</div>"
)
map_small = "".join(
    f'<div class="mapmini"><p class="mmt"><span class="dot" style="background:{gvar(g)}"></span>{esc(GENRE_TAG[g])} <span class="muted">{len(by_genre[g])}</span></p>{map_svg(by_genre[g], big=False)}</div>'
    for g in GENRES_WITH)
map_html = (
    '<p class="intro">Each mark is one case, placed in a column by its disclosure at origin and in a row by the claim made about the image. '
    "The colour gives the genre and the shape gives the kind of producer, and selecting a mark opens the record of the case.</p>"
    + map_legend + '<div class="tl-wrap map-wrap">' + map_svg(rows) + "</div>"
    + f'<p class="tnote">Marks in the bottom row that sit outside the first column are the {S["lost"]} cases whose disclosure was lost in circulation.</p>'
    + '<div class="section"><h2>The same map, one genre at a time</h2><div class="mapgrid">' + map_small + "</div>"
    + '<p class="tnote">The small maps repeat the columns and rows of the large map for each genre in turn.</p></div>'
)

# ------------------------------------------------------------------ readings across the genres

EV = {
    "R1": [("Qualified regime", {"regime": "qualified"}), ("Unqualified regime", {"regime": "unqualified"}),
           ("Qualified regime, still disclosed in circulation", {"regime": "qualified", "circl": "1"}),
           ("Unqualified regime, presented as authentic", {"regime": "unqualified", "auth": "1"})],
    "R2": [("Political communication", {"genre": "3"}), ("Political communication, still disclosed in circulation", {"genre": "3", "circl": "1"}),
           ("Humanitarian communication", {"genre": "1"}), ("Other qualified genres, real person depicted", {"group": "named", "real": "1"})],
    "R3": [("Humanitarian communication, 2023", {"genre": "1", "year": "2023"}),
           ("Humanitarian communication, policy or guideline consequence", {"genre": "1", "cons": "1"}),
           ("Humanitarian communication, 2024 to 2026", {"genre": "1", "year": "2024|2025|2026"}),
           ("Other genres, 2025 and 2026", {"genre": "!1", "year": "2025|2026"})],
    "R4": [("Label lost in circulation", {"lost": "1"})],
    "R5": [("Qualified regime, policy or guideline consequence", {"regime": "qualified", "cons": "1"}),
           ("Unqualified regime, policy or guideline consequence", {"regime": "unqualified", "cons": "1"}),
           ("Qualified regime, removal reported", {"regime": "qualified", "rem": "1"}),
           ("Unqualified regime, removal reported", {"regime": "unqualified", "rem": "1"}),
           ("Unqualified regime, fact-checked", {"regime": "unqualified", "fact": "1"}),
           ("Liar's dividend documented", {"liar": "1"})],
    "R6": [("Responsibility of the producer", {"q": "responsibility"}), ("Participation as remedy", {"q": "participation"}),
           ("Evidentiary versus appellative use", {"q": "evidentiary"}),
           ("Victims' advocacy and forensic reconstruction, evidentiary versus appellative use", {"genre": "7|11", "q": "evidentiary"}),
           ("Generated or typified person", {"syn": "a|b"}),
           ("Real person depicted", {"real": "1"})],
    "R7": [("Suffering in the Global South", {"south": "1"}), ("Producer in the Global North", {"south": "1", "north": "1"}),
           ("Producer in the regions depicted", {"south": "1", "regp": "Middle East|Africa|Latin America|Asia"}),
           ("Producer not established", {"south": "1", "regp": "Not established"})],
}
assert n_match({"regime": "qualified"}) == S["n_q"] and n_match({"regime": "unqualified", "auth": "1"}) == S["a_u"]
assert n_match({"regime": "qualified", "circl": "1"}) == S["d_q"] and n_match({"lost": "1"}) == S["lost"]
assert n_match({"genre": "1", "year": "2023"}) == S["h2023"] and n_match({"genre": "1", "cons": "1"}) == S["cons_h"]
assert n_match({"group": "named", "real": "1"}) == S["real_oq"] and n_match({"regime": "unqualified", "fact": "1"}) == S["fc_u"]
assert n_match({"q": "responsibility"}) == S["q_resp"] and n_match({"south": "1", "north": "1"}) == S["ns"]
assert n_match({"south": "1", "regp": "Not established"}) == S["ns_anon"] and n_match({"south": "1"}) == S["south"]
assert n_match({"regime": "unqualified", "cons": "1"}) == S["cons_u"] and n_match({"regime": "unqualified", "rem": "1"}) == S["rem_u"]
assert n_match({"genre": "7|11", "q": "evidentiary"}) == S["q_ev_vf"] and n_match({"south": "1", "regp": "Middle East|Africa|Latin America|Asia"}) == S["ss"]
assert n_match({"liar": "1", "regime": "qualified"}) == len(LIAR_Q)

CARDS = [
    ("R1", "Two regimes of qualification", ("matrix", "Matrix"), READINGS["overview"][:1]),
    ("R2", "Political communication and the person depicted", ("matrix", "Matrix"), READINGS["overview"][1:]),
    ("R3", "Humanitarian cases over time", ("timeline", "Timeline"), READINGS["timeline"]),
    ("R4", "Disclosure at origin and in circulation", ("map", "Map"), READINGS["map"]),
    ("R5", "Debate in each regime", ("matrix", "Matrix"), READINGS["debate"]),
    ("R6", "The four questions of the joint paper", ("questions", "Questions"), READINGS["paper"][:1]),
    ("R7", "The Global North and the Global South", ("questions", "Questions"), READINGS["paper"][1:]),
]
assert sum(len(c[3]) for c in CARDS) == sum(len(v) for v in READINGS.values())


def ev_buttons(rid):
    out = []
    for label, filt in EV[rid]:
        g = filt.get("genre", "")
        col = gvar(g) if g in GENRE_COLOR else "var(--accent)"
        k = n_match(filt)
        out.append(f'<button type="button" class="evb" style="--gc:{col}" data-filter="{fattr(filt)}"><span>{esc(label)}</span>'
                   f'<b class="mono">{k} {"case" if k == 1 else "cases"}</b></button>')
    if rid == "R4":
        for r in rows:
            d = D[r["ID"]]
            if not d["lost"]:
                continue
            qt = first_quote(split_top(r["Disclosure"], "; ")[0])
            body = f"<q>{esc(qt)}</q>" if qt else f'<i>{esc(r["Disclosure"].split(":")[0])}</i>'
            out.append(f'<button type="button" class="evb" style="--gc:{gvar(d["gno"])}" data-case="{r["ID"]}">'
                       f'<span><span class="mono">{r["ID"]}</span> {esc(r["Case name"])}</span>{body}</button>')
    return "".join(out)


readings_html = (
    '<p class="intro">Seven readings compare the genres on the counts of the other analysis tabs, and the buttons under each reading list the cases behind its counts.</p>'
    '<div class="readings">'
    + "".join(
        f'<article class="reading" id="read-{rid}"><div class="rtop"><span class="rid">{rid}</span><h2>{esc(title)}</h2>'
        f'<button type="button" class="rq" data-go="{view}">{esc(vlab)}</button></div>'
        + "".join(f"<p>{esc(p)}</p>" for p in paras)
        + f'<div class="evs">{ev_buttons(rid)}</div></article>'
        for rid, title, (view, vlab), paras in CARDS)
    + "</div>"
)

# ------------------------------------------------------------------ method

der_vals = {
    "Producer kind": Counter(PROD_LABEL[d["prod"]].lower() for d in D.values()),
    "Disclosure at origin": Counter(d["disc"] for d in D.values()),
    "Presented as authentic": Counter("yes" if d["auth"] else "no" for d in D.values()),
    "Disclosure in circulation": Counter(d["circ"] + (" (label lost)" if d["lost"] else "") for d in D.values()),
    "Justification given": Counter("yes" if d["just"] else "no" for d in D.values()),
    "People affected involved": Counter("yes" if d["involved"] else "no" for d in D.values()),
    "Real person depicted": Counter("yes" if d["real"] else "no" for d in D.values()),
    "Policy or guideline consequence": Counter("yes" if d["cons"] else "no" for d in D.values()),
    "Liar's dividend documented": Counter("yes" if d["liar"] else "no" for d in D.values()),
    "Removal reported": Counter("yes" if d["removal"] else "no" for d in D.values()),
    "Apology reported": Counter("yes" if d["apology"] else "no" for d in D.values()),
    "Fact-checked": Counter("yes" if d["fact"] else "no" for d in D.values()),
    "Questions for the paper": Counter(QUESTIONS[k][0].lower() for d in D.values() for k in d["q"]),
    "Region of the suffering, region of the producer": Counter(f"suffering in {d['regs']}" for d in D.values()),
    "Year": Counter(d["year"] or "undated" for d in D.values()),
    "Regime of the genre": Counter(f"{genre_short[g]}: {regime[g]}" for g in GENRES_WITH),
}
REF_RE = re.compile(r"^((?:Fields?) \d+(?: and \d+)?)[.,]\s*(.*)$", re.S)


def method_card(name, rule):
    m = REF_RE.match(rule)
    ref, text = (m.group(1), m.group(2)) if m else ("All the cases of each genre", rule)
    text = text[:1].upper() + text[1:]
    vals = "".join(f"<span>{esc(str(k))}<i>{n}</i></span>" for k, n in sorted(der_vals[name].items(), key=lambda kv: (-kv[1], str(kv[0]))))
    return (f'<article class="cat"><div class="h"><h3>{esc(name)}</h3></div><div class="ref">{esc(ref)}</div>'
            f'<p>{esc(text)}</p><div class="subs">{vals}</div></article>')


region_rows = "".join(f'<tr><td class="num">{i}</td><td class="pat">{esc(pat)}</td><td>{esc(reg)}</td></tr>' for i, (pat, reg) in enumerate(REGION_RULES, 1))
NOTE_LABELS = ["Type of synthesis", "Disclosure in circulation", "Dates", "Keyword rules", "Regimes"]
assert len(NOTE_LABELS) == len(CODING_NOTES)
method_html = (
    '<p class="intro">Each card gives a value derived from the fields of the CSV, with the rule that derives it and the values that the rule produces. '
    "The derived values supply the Matrix, the Timeline, the Map and the Questions tab, and the coding notes below state where a rule is approximate.</p>"
    '<div class="cats">' + "".join(method_card(n, r) for n, r in DERIVED_DEFS) + "</div>"
    '<div class="section"><h2>Region lookup</h2><p>The place name that occurs first in the field decides the region, and a field that begins with not, no specific or no country has none.</p>'
    '<div class="tbl-wrap"><table class="fields"><thead><tr><th class="num">#</th><th>Place names (regular expression, case-insensitive)</th><th>Region</th></tr></thead>'
    f"<tbody>{region_rows}</tbody></table></div></div>"
    '<div class="notesec"><h2>Coding notes</h2><dl>' + "".join(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in zip(NOTE_LABELS, CODING_NOTES)) + "</dl></div>"
)

# ------------------------------------------------------------------ fields

field_rows = []
for i, (fld, dfn) in enumerate(FIELD_DEFS, 1):
    if fld in CODED:
        c = Counter(collapse(fld, r[fld]) for r in rows)
        if fld == "Genre":
            vals = "; ".join(f"{esc(k)} ({n})" for k, n in sorted(c.items(), key=lambda kv: int(genre_no(kv[0]))))
        else:
            vals = "; ".join(f"{esc(k)} ({n})" for k, n in sorted(c.items(), key=lambda kv: (-kv[1], kv[0])))
    else:
        vals = '<span class="muted">free text</span>'
    field_rows.append(f'<tr><td class="num">{i}</td><td class="dname">{esc(fld)}</td>'
                      f'<td>{esc(dfn) if dfn else "<span class=\"muted\">free text</span>"}</td><td>{vals}</td></tr>')
syn_list = "".join(f'<li><span class="mono code">{k}</span> {esc(SYN_FULL[k])} <span class="muted">({syn_counts[k]} cases)</span></li>' for k in SYN_SHORT)
fields_html = (
    f'<p class="intro">Each case is recorded in the {len(FIELD_DEFS)} fields below, defined as in the search brief of 26 October 2026, with the values in use counted from the CSV. '
    'Codes added during the search, such as "presented as an authentic recording (undisclosed)", are defined in the Codebook sheet of the spreadsheet, and the Method tab gives the values derived from these fields.</p>'
    f'<div class="tbl-wrap"><table class="fields"><thead><tr><th class="num">#</th><th>Field</th><th>Definition in the search brief</th><th>Values in use</th></tr></thead><tbody>{"".join(field_rows)}</tbody></table></div>'
    f'<div class="section"><h2>Types of synthesis</h2><ul class="synlist">{syn_list}</ul></div>'
)

# ------------------------------------------------------------------ memo with its coverage table and annex

cov_rows = []
for no, info in memo_cov.items():
    rs = by_genre.get(no, [])
    vc = Counter(r["Verification status"] for r in rs)
    if rs:
        gcell = (f'<button type="button" class="lnk" data-filter="{fattr({"genre": no})}"><span class="dot" style="background:{gvar(no)}"></span>'
                 f"{esc(info['short'])}</button>")
        ids = id_runs([r["ID"] for r in rs])
    else:
        gcell = f'<span class="muted"><span class="dot hollow"></span>{esc(info["short"])}</span>'
        ids = '<span class="muted">none</span>'
    cov_rows.append(
        f'<tr{" class=missing" if not rs else ""}><td>{gcell}</td><td class="num">{len(rs)}</td><td class="ids">{ids}</td>'
        f'<td class="num">{vc["primary source"]}</td><td class="num">{vc["two secondary sources"]}</td>'
        f'<td class="num">{vc["unverified"]}</td><td>{esc(info["searches"])}</td></tr>')
coverage_table = (
    '<div class="tbl-wrap"><table class="cov"><thead><tr><th>Genre</th><th class="num">Cases</th><th>IDs</th><th class="num">Primary source</th>'
    '<th class="num">Two secondary</th><th class="num">Unverified</th><th>Searches (languages)</th></tr></thead><tbody>'
    + "".join(cov_rows) + '</tbody><tfoot><tr class="total">'
    f'<td>Total</td><td class="num">{len(rows)}</td><td></td><td class="num">{ver_counts["primary source"]}</td>'
    f'<td class="num">{ver_counts["two secondary sources"]}</td><td class="num">{ver_counts["unverified"]}</td><td>{esc(memo_total_searches)}</td>'
    "</tr></tfoot></table></div>"
    '<p class="tnote">Selecting a genre lists its cases in the Ledger, and the verification columns are counted from the CSV.</p>'
)

body_md = memo.split("## Annex")[0]
body_md = re.sub(r"^# .*\n+", "", body_md, count=1)
body_md = re.sub(r"^> \*\*Version:\*\*.*\n> \*\*Last updated:\*\*.*\n+", "", body_md, flags=re.M)
lines_, out_, in_tbl = body_md.split("\n"), [], False
for line in lines_:
    if line.startswith("|"):
        if not in_tbl:
            out_.append("%%COVERAGE%%")
            in_tbl = True
        continue
    in_tbl = False
    out_.append(line)
body_md = "\n".join(out_)
body_md = re.sub(r"(?<![\w#\[])(C\d{2,3})(?!\d)", r"[\1](#\1)", body_md)
memo_body = markdown.markdown(body_md).replace('<a href="#C', '<a class="cid" href="#C')
memo_body = memo_body.replace("<p>%%COVERAGE%%</p>", coverage_table)
assert "%%COVERAGE%%" not in memo_body

annex = memo.split("## Annex")[1]
annex_title = "Annex" + annex.split("\n", 1)[0]
paras = [p.strip() for p in annex.split("\n\n") if p.strip().startswith("**")]
lead_rows, excl_html = [], []
for p in paras:
    m = re.match(r"\*\*(.+?)\.\*\*\s*(.*)", p, re.S)
    label, body = m.group(1), m.group(2).strip()
    if label == "One source only":
        for it in split_top(body.rstrip("."), "; "):
            lead_rows.append((it, "One source only", ""))
    elif label.startswith("Not located"):
        sentences = re.split(r"(?<=\.)\s+(?=Genre \d+ leads are)", body)
        for it in split_top(sentences[0].rstrip("."), "; "):
            lead_rows.append((it, "Not located or not yet searched", ""))
        for s_ in sentences[1:]:
            gm = re.match(r"Genre (\d+) leads are (.*)\.$", s_.strip(), re.S)
            if gm:
                for it in split_top(gm.group(2), ", "):
                    lead_rows.append((it, f"Lead for genre {gm.group(1)}, not yet searched", gm.group(1)))
    else:
        excl_html.append(f"<p><b>{esc(label)}.</b> {link_ids(esc(body))}</p>")
LEAD_GENRES = any(g for _, _, g in lead_rows)
leads_table = (
    '<div class="tbl-wrap"><table class="leads"><thead><tr><th class="num">#</th><th>Candidate</th><th>Status</th>'
    + ("<th>Genre</th>" if LEAD_GENRES else "") + "</tr></thead><tbody>"
    + "".join(f'<tr><td class="num">{i}</td><td>{link_ids(esc(c[:1].upper() + c[1:]))}</td><td>{esc(s_)}</td>'
              + (f'<td>{esc(genre_short[g]) if g else ""}</td>' if LEAD_GENRES else "") + "</tr>"
              for i, (c, s_, g) in enumerate(lead_rows, 1))
    + "</tbody></table></div>"
)
memo_html = (
    f'<p class="eyebrow memometa">Search memo &middot; version {esc(memo_version)} &middot; {esc(memo_date)}</p>'
    f'<div class="prose">{memo_body}</div>'
    f'<div class="section"><h2>{esc(annex_title)}</h2>'
    f'<p class="caption">Leads for the next search round ({len(lead_rows)})</p>{leads_table}'
    f'<div class="prose excl">{"".join(excl_html)}</div></div>'
)

# ------------------------------------------------------------------ page

CSS = r"""
/* Design of the Biometric Identification archive, set in Helvetica: single light theme on white.
   Layout: one case database in two parts. A masthead with the distribution of the cases by genre, then tabs
   in two labelled rows, the database (ledger, timeline, memo, fields) and the analysis (matrix, map,
   questions, readings across the genres, method). The record of a case opens in a panel on the right. */
:root {
  --bg: #FFFFFF;
  --panel: #FFFFFF;
  --tint: #F4F6F5;
  --ink: #101413;
  --ink-2: #2E3633;
  --ink-3: #4F5955;
  --rule: #CBD2CE;
  --rule-2: #E3E7E5;
  --accent: #174E70;
  --accent-soft: #E6EFF5;
  --focus: #B86E00;
  --ok: #1E6B3E;
  --ok-soft: #E7F2EA;
  --warn: #8F5600;
  --warn-soft: #F8EEDF;
  --scrim: rgba(16, 20, 19, 0.30);
  --shadow: 0 1px 2px rgba(16, 20, 19, 0.06), 0 12px 32px rgba(16, 20, 19, 0.12);
%GENRE_TOKENS%
  --f-sans: "Helvetica Neue", Helvetica, Arial, sans-serif;
  color-scheme: light;
}
* { box-sizing: border-box; }
[hidden] { display: none !important; }
html { background: var(--bg); padding-top: env(safe-area-inset-top, 0px); padding-bottom: env(safe-area-inset-bottom, 0px); scroll-padding-top: env(safe-area-inset-top, 0px); }
body { margin: 0; background: var(--bg); color: var(--ink); font-family: var(--f-sans); font-size: 16px; line-height: 1.55; }
.wrap { max-width: 1240px; margin: 0 auto; padding-left: max(20px, env(safe-area-inset-left, 0px)); padding-right: max(20px, env(safe-area-inset-right, 0px)); padding-block: 28px 72px; }
a { color: var(--accent); text-underline-offset: 2px; }
:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; border-radius: 4px; }
.mono { font-variant-numeric: tabular-nums; }
.muted { color: var(--ink-3); }
.eyebrow { font-family: var(--f-sans); font-size: 13px; letter-spacing: 0.05em; text-transform: uppercase; color: var(--ink-3); }
.dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 6px; vertical-align: 0; flex: none; }
.dot.hollow { background: var(--panel); box-shadow: inset 0 0 0 1.5px var(--ink-3); }
q, q.sq { quotes: "\201C" "\201D" "\2018" "\2019"; }
q.sq { color: var(--ink); }

/* masthead */
.masthead { display: grid; gap: 14px; padding-bottom: 22px; border-bottom: 1px solid var(--rule); }
h1 { margin: 0; font-size: clamp(30px, 4.6vw, 48px); line-height: 1.02; font-weight: 700; letter-spacing: -0.01em; text-wrap: balance; }
.lede { margin: 0; max-width: 72ch; color: var(--ink-2); font-size: 18px; line-height: 1.5; }
.casebar { display: flex; height: 14px; border-radius: 3px; overflow: hidden; background: var(--rule-2); gap: 2px; }
.casebar span { display: block; height: 100%; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 20px; font-size: 15px; color: var(--ink-2); }
.legend b { font-weight: 600; color: var(--ink); font-variant-numeric: tabular-nums; }
.legend .ns { color: var(--ink-3); }
.legend .ns i { font-style: italic; }
.stats { display: flex; flex-wrap: wrap; gap: 10px 28px; margin: 4px 0 0; }
.stats div { display: grid; }
.stats dt { font-size: 12.5px; color: var(--ink-3); text-transform: uppercase; letter-spacing: 0.06em; font-family: var(--f-sans); }
.stats dd { margin: 0; font-size: 26px; font-weight: 700; font-variant-numeric: tabular-nums; }

/* tabs, one row for each part */
.tabs { display: grid; margin: 20px 0 20px; border-bottom: 1px solid var(--rule); }
.tgroup { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 0 2px; }
.tgroup + .tgroup { border-top: 1px solid var(--rule-2); }
.tglabel { flex: 0 0 156px; align-self: center; font: 500 12px/1 var(--f-sans); letter-spacing: 0.06em; text-transform: uppercase; color: var(--ink-3); }
.tabs button { appearance: none; border: 0; background: none; color: var(--ink-2); font: 600 16px/1 var(--f-sans); padding: 13px 11px 11px; border-bottom: 3px solid transparent; margin-bottom: -1px; cursor: pointer; }
.tabs button[aria-selected="true"] { color: var(--accent); border-bottom-color: var(--accent); }
.tabs button:hover { color: var(--ink); }

/* band of the analysis tabs */
.aband { display: flex; flex-wrap: wrap; gap: 10px 14px; align-items: center; margin: -4px 0 22px; }
.status { display: inline-flex; align-items: center; gap: 8px; width: fit-content; font-size: 14.5px; color: var(--ink-2); padding: 6px 11px; border: 1px dashed var(--focus); border-radius: 999px; }
.status b { color: var(--focus); font-weight: 600; }
.kchip { appearance: none; display: inline-flex; align-items: center; gap: 7px; font: 500 14px/1 var(--f-sans); color: var(--ink); border-radius: 4px; padding: 7px 10px; cursor: pointer; border: 1px solid; }
.kchip .n { font-family: var(--f-sans); font-size: 12.5px; }
.kchip.rg-qualified { background: var(--ok-soft); border-color: var(--ok); }
.kchip.rg-qualified .n { color: var(--ok); }
.kchip.rg-unqualified { background: var(--warn-soft); border-color: var(--warn); }
.kchip.rg-unqualified .n { color: var(--warn); }
.kchip:hover { box-shadow: inset 0 -2px 0 currentColor; }

.intro { margin: 0 0 18px; max-width: 80ch; color: var(--ink-2); font-size: 16px; }
.tnote { font-size: 15px; color: var(--ink-2); max-width: 90ch; margin: 12px 0 0; }
.section { display: grid; gap: 12px; margin-top: 34px; }
.section h2, .notesec h2 { margin: 0; font-size: 22px; font-weight: 700; }
.section > p { margin: 0; max-width: 78ch; color: var(--ink-2); }
.caption { font-weight: 700; font-size: 19px; margin: 0; }

/* filters */
.filters { display: grid; gap: 12px; padding: 16px; background: var(--tint); border: 1px solid var(--rule-2); border-radius: 6px; margin-bottom: 14px; }
.frow { display: flex; flex-wrap: wrap; gap: 8px 10px; align-items: center; }
.flabel { font-family: var(--f-sans); font-size: 12.5px; letter-spacing: 0.06em; text-transform: uppercase; color: var(--ink-3); min-width: 92px; }
input[type="search"], select { font: 15px var(--f-sans); color: var(--ink); background: var(--panel); border: 1px solid var(--rule); border-radius: 5px; padding: 8px 10px; max-width: 100%; }
input[type="search"] { flex: 1 1 260px; min-width: 0; }
.chip { appearance: none; display: inline-flex; align-items: center; gap: 6px; font: 500 14px/1.15 var(--f-sans); color: var(--ink); background: var(--panel); border: 1px solid var(--rule); border-radius: 999px; padding: 7px 11px; cursor: pointer; text-align: left; }
.chip[aria-pressed="true"] { background: var(--accent-soft); border-color: var(--accent); box-shadow: inset 0 0 0 1px var(--accent); }
.chip .n { font-family: var(--f-sans); font-size: 12.5px; color: var(--ink-3); }
.chip .code { font-size: 12.5px; color: var(--ink-2); border: 1px solid var(--rule); border-radius: 3px; padding: 0 5px; }
.vdot { display: inline-block; width: 9px; height: 9px; border-radius: 2px; border: 1.5px solid; }
.vdot.v-primary { border-color: var(--ok); background: var(--ok-soft); }
.vdot.v-secondary { border-color: var(--accent); background: var(--accent-soft); }
.vdot.v-unverified { border-color: var(--warn); background: var(--warn-soft); }
.check { display: inline-flex; align-items: center; gap: 6px; font-size: 15px; color: var(--ink); cursor: pointer; }
.btn { appearance: none; font: 600 15px/1 var(--f-sans); color: var(--accent); background: transparent; border: 1px solid var(--accent); border-radius: 5px; padding: 9px 12px; cursor: pointer; }
.btn:hover { background: var(--accent-soft); }
.countrow { display: flex; flex-wrap: wrap; gap: 8px 12px; align-items: center; margin: 0 0 8px; }
.count { font-size: 15px; color: var(--ink-2); margin: 0; }
.fchip { display: inline-flex; align-items: center; gap: 6px; font-size: 13.5px; color: var(--ink); background: var(--accent-soft); border: 1px solid var(--accent); border-radius: 999px; padding: 4px 6px 4px 11px; }
.fchip button { appearance: none; border: 0; background: transparent; color: var(--accent); font: 600 16px/1 var(--f-sans); cursor: pointer; padding: 0 4px; }

/* ledger */
.ledger { display: grid; border-top: 1px solid var(--rule); }
.row { display: grid; grid-template-columns: 82px 124px 30px minmax(0, 1fr) auto; gap: 14px; align-items: start; padding: 14px 8px; border-bottom: 1px solid var(--rule-2); cursor: pointer; }
.row:hover { background: var(--accent-soft); }
.row .date { font-family: var(--f-sans); font-size: 14px; color: var(--ink-2); padding-top: 2px; white-space: nowrap; }
.row .gen { display: inline-flex; align-items: center; font-size: 15px; color: var(--ink); white-space: nowrap; padding-top: 1px; }
.row .syn { display: inline-block; font-family: var(--f-sans); font-size: 13px; font-weight: 500; padding: 1px 0; width: 26px; border: 1px solid var(--rule); border-radius: 3px; color: var(--ink-2); text-align: center; margin-top: 1px; }
.row .title { font-weight: 600; font-size: 17px; line-height: 1.38; overflow-wrap: anywhere; }
.row .sub { font-size: 14.5px; color: var(--ink-3); margin-top: 4px; overflow-wrap: anywhere; }
.row .sub .mono { font-size: 13px; }
.badges { display: flex; flex-wrap: wrap; gap: 6px; justify-content: flex-end; max-width: 230px; }
.tag { display: inline-flex; align-items: center; gap: 4px; font-size: 13px; line-height: 1; padding: 4px 7px; border-radius: 999px; border: 1px solid var(--rule); color: var(--ink-2); white-space: nowrap; }
.tag.key { border-color: var(--accent); color: var(--accent); font-weight: 600; }
.tag.v-primary { border-color: var(--ok); color: var(--ok); }
.tag.v-secondary { border-color: var(--rule); color: var(--ink-2); }
.tag.v-unverified { border-color: var(--warn); color: var(--warn); border-style: dashed; }
.tag.rg-qualified { border-color: var(--ok); color: var(--ok); background: var(--ok-soft); }
.tag.rg-unqualified { border-color: var(--warn); color: var(--warn); background: var(--warn-soft); }
.empty { padding: 24px 6px; color: var(--ink-2); }

/* timeline */
.tlbar { display: flex; flex-wrap: wrap; gap: 10px 14px; align-items: center; margin: 0 0 12px; }
.tlbar .flabel { min-width: 0; }
.tlkey { display: inline-flex; flex-wrap: wrap; gap: 4px 6px; align-items: center; font-size: 14.5px; color: var(--ink-2); }
.tlkey svg { margin-left: 8px; }
.kfill { fill: var(--ink-3); } .khol { fill: var(--panel); stroke: var(--ink-3); stroke-width: 1.8; } .kring { fill: none; stroke: var(--accent); stroke-width: 1.8; }
.tl-wrap { overflow-x: auto; background: var(--panel); border: 1px solid var(--rule-2); border-radius: 6px; padding: 8px 4px; }
.tl-wrap svg#tl { display: block; min-width: 880px; width: 100%; height: auto; }
svg .grid { stroke: var(--rule-2); stroke-width: 1; }
svg .grid.dash { stroke: var(--rule); stroke-dasharray: 2 4; }
svg .lane { fill: none; stroke: var(--rule); stroke-width: 1; }
svg .lbl { fill: var(--ink); font: 600 15px var(--f-sans); }
svg .lbn { fill: var(--ink-3); font: 13px var(--f-sans); }
svg .yr { fill: var(--ink-2); font: 14px var(--f-sans); }
svg .pt { cursor: pointer; }
svg .pt:focus { outline: none; }
svg .mk { stroke-width: 1.5; }
svg .mk.hol { stroke-width: 2.2; }
svg .ring { fill: none; stroke: var(--accent); stroke-width: 2; opacity: 0; }
svg .pt.ringed .ring { opacity: 1; }
svg .pt:hover .mk, svg .pt:focus-visible .mk { stroke: var(--focus); stroke-width: 3; }
svg .pt:hover .dt, svg .pt:focus-visible .dt { stroke: var(--focus); stroke-width: 3; }

/* map */
.map-wrap { padding: 10px 6px; }
svg.map { display: block; max-width: 100%; height: auto; }
.map-wrap svg.map { min-width: 760px; width: 100%; }
svg .axl { fill: var(--ink-2); font: 14px var(--f-sans); }
svg .axt { fill: var(--ink-3); font: 500 12px var(--f-sans); letter-spacing: 0.06em; }
svg .dt { stroke: var(--bg); stroke-width: 2; }
.maplegend { display: flex; flex-wrap: wrap; gap: 6px 16px; align-items: center; font-size: 14.5px; color: var(--ink-2); margin: 0 0 12px; }
.maplegend svg { margin-right: 6px; vertical-align: -2px; }
.maplegend .shape { fill: var(--ink-3); }
.sepv { width: 1px; height: 16px; background: var(--rule); }
.mapgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 14px 18px; }
.mapmini { border: 1px solid var(--rule-2); border-radius: 6px; padding: 10px 10px 8px; min-width: 0; }
.mmt { margin: 0 0 6px; font-weight: 600; font-size: 15px; display: flex; align-items: center; gap: 2px; }
.mmt .muted { font: 13px var(--f-sans); margin-left: 4px; }
svg.mini .grid { stroke: var(--rule-2); }

/* grids in the manner of the biometric article */
.tbl-wrap { overflow-x: auto; border: 1px solid var(--rule-2); border-radius: 6px; background: var(--panel); }
table { border-collapse: collapse; width: 100%; font-size: 15.5px; line-height: 1.45; }
th, td { text-align: left; vertical-align: top; padding: 11px 14px; border-bottom: 1px solid var(--rule-2); }
th { font: 600 12.5px/1.3 var(--f-sans); letter-spacing: 0.04em; text-transform: uppercase; color: var(--ink-2); background: var(--tint); }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; font-family: var(--f-sans); font-size: 14px; }
.grid-wrap { margin-top: 4px; }
table.grid { min-width: 980px; }
table.grid th, table.grid td { padding: 8px 6px; vertical-align: middle; }
table.grid thead th { background: var(--panel); text-transform: none; letter-spacing: 0; }
table.grid tr.h1 th { font: 500 12px/1.2 var(--f-sans); letter-spacing: 0.06em; text-transform: uppercase; color: var(--ink-3); text-align: center; border-bottom: 0; padding-top: 12px; }
table.grid th.gh { text-align: center; min-width: 70px; }
table.grid .gt { display: inline-flex; align-items: center; font: 700 15px/1.2 var(--f-sans); color: var(--ink); white-space: nowrap; }
table.grid .gt .dot { margin-right: 5px; }
table.grid .gs { display: block; font: italic 400 13.5px/1.3 var(--f-sans); color: var(--ink-3); margin-top: 3px; }
table.grid th.dim .gt { color: var(--ink-3); }
table.grid th.rh { font: 500 12px/1.2 var(--f-sans); letter-spacing: 0.06em; text-transform: uppercase; color: var(--ink-3); vertical-align: bottom; }
table.grid tr.grow th { background: var(--tint); padding: 10px 12px; font: 400 15px/1.3 var(--f-sans); text-transform: none; letter-spacing: 0; color: var(--ink); }
table.grid tr.grow b { font-weight: 700; font-size: 17px; margin-right: 8px; }
table.grid tr.grow i { font: italic 15px var(--f-sans); color: var(--ink-3); }
table.grid th.rl { background: var(--panel); text-transform: none; letter-spacing: 0; min-width: 220px; max-width: 300px; padding-left: 12px; }
table.grid .rn { display: block; font: 500 15.5px/1.3 var(--f-sans); color: var(--ink); }
table.grid .rs { display: block; font: italic 14px/1.35 var(--f-sans); color: var(--ink-3); margin-top: 2px; }
table.grid td.gc { text-align: center; }
table.grid .sep { border-left: 1.5px dotted var(--rule); }
.bcell { appearance: none; display: inline-grid; justify-items: center; gap: 2px; background: none; border: 0; padding: 4px 6px; border-radius: 6px; cursor: pointer; color: var(--ink); }
.bcell:hover { background: var(--accent-soft); }
.bcell .bn { font: 12.5px/1 var(--f-sans); color: var(--ink-3); font-variant-numeric: tabular-nums; }
.ball .b0, .ball .bo { fill: none; stroke: var(--ink); stroke-width: 1.8; }
.ball .b0 { fill: var(--panel); }
.ball .b1, .ball .bw { fill: var(--ink); stroke: var(--ink); stroke-width: 1.8; }
.ball .bw { stroke: none; }
svg.na line { stroke: var(--ink-3); stroke-width: 2; }
.glegend { display: flex; flex-wrap: wrap; gap: 8px 26px; align-items: center; margin: 14px 0 0; font-size: 15px; color: var(--ink-2); }
.glegend span { display: inline-flex; align-items: center; gap: 8px; }
ul.liar { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; max-width: 96ch; }
ul.liar li { padding: 12px 14px; border: 1px solid var(--rule-2); border-left: 3px solid var(--gc); border-radius: 0 6px 6px 0; }
ul.liar p { margin: 6px 0 0; font-size: 15.5px; color: var(--ink-2); }
.lnk { appearance: none; font: 600 16px/1.35 var(--f-sans); color: var(--accent); background: none; border: 0; padding: 0; cursor: pointer; text-align: left; text-decoration: underline; text-underline-offset: 2px; text-decoration-thickness: 1px; display: inline-flex; align-items: center; }
.lnk .mono { font-size: 13.5px; margin-right: 6px; }

/* tables */
td.cell { text-align: center; font-family: var(--f-sans); font-size: 14px; font-variant-numeric: tabular-nums; padding: 0; }
td.cell.zero { color: var(--rule); padding: 11px 6px; }
.cbtn { appearance: none; font: inherit; color: inherit; background: none; border: 0; padding: 11px 10px; width: 100%; cursor: pointer; }
td.cell.hit:hover { outline: 2px solid var(--accent); outline-offset: -2px; }
td.num .cbtn { padding: 0; width: auto; text-decoration: underline dotted var(--ink-3); text-underline-offset: 3px; }
table.regions { min-width: 860px; }
table.regions td.dname { font-weight: 600; white-space: nowrap; }
tr.south td.dname::before { content: ""; display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: var(--ink-3); margin-right: 8px; vertical-align: 1px; }
tr.total td, tfoot td { font-weight: 700; border-top: 2px solid var(--rule); background: var(--panel); }
tr.missing td { color: var(--ink-3); font-style: italic; }
td.dname { font-weight: 600; }
table.cov { min-width: 820px; }
table.cov td.ids { font-size: 14px; }
table.fields { min-width: 820px; }
table.fields td.dname { min-width: 180px; }
td.pat { font-family: var(--f-sans); font-size: 13px; overflow-wrap: anywhere; }
table.leads { min-width: 680px; }
a.cid { font-family: var(--f-sans); font-size: 0.92em; }
ul.synlist { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; max-width: 90ch; }
ul.synlist .code { display: inline-block; width: 24px; text-align: center; border: 1px solid var(--rule); border-radius: 3px; font-size: 13px; margin-right: 6px; }

/* readings */
.readings { display: grid; gap: 18px; }
.reading { border: 1px solid var(--rule-2); border-radius: 6px; padding: 16px 18px 18px; display: grid; gap: 10px; background: var(--panel); scroll-margin-top: 16px; }
.rtop { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 12px; }
.rid { font: 600 13px/1 var(--f-sans); color: var(--accent); }
.reading h2 { margin: 0; font-size: 21px; font-weight: 700; text-wrap: balance; }
.rq { appearance: none; font: 500 12px/1 var(--f-sans); color: var(--accent); background: var(--panel); border: 1px solid var(--accent); border-radius: 999px; padding: 4px 9px; cursor: pointer; }
.rq:hover { background: var(--accent-soft); }
.reading p { margin: 0; max-width: 84ch; color: var(--ink); font-size: 16px; }
.evs { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 4px; }
.evb { appearance: none; display: inline-flex; flex-direction: column; align-items: flex-start; gap: 4px; max-width: 100%; text-align: left; background: var(--panel); border: 1px solid var(--rule); border-left: 3px solid var(--gc); border-radius: 4px; padding: 7px 10px; cursor: pointer; font: 13.5px/1.3 var(--f-sans); color: var(--ink-2); }
.evb b { font-weight: 500; font-size: 12.5px; color: var(--ink-3); }
.evb q { font: italic 15px/1.35 var(--f-sans); color: var(--ink); overflow-wrap: anywhere; }
.evb i { font: italic 14px/1.35 var(--f-sans); color: var(--ink-3); }
.evb .mono { font-size: 12.5px; color: var(--ink-3); margin-right: 4px; }
.evb:hover { background: var(--accent-soft); }

/* method */
.cats { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 14px; }
.cat { border: 1px solid var(--rule-2); border-top: 4px solid var(--accent); border-radius: 6px; padding: 14px 16px; display: grid; gap: 8px; align-content: start; min-width: 0; }
.cat h3 { margin: 0; font-size: 18px; font-weight: 700; }
.cat .ref { font-family: var(--f-sans); font-size: 12.5px; color: var(--ink-3); text-transform: uppercase; letter-spacing: 0.04em; }
.cat p { margin: 0; font-size: 15px; color: var(--ink-2); overflow-wrap: anywhere; }
.cat .subs { display: flex; flex-wrap: wrap; gap: 5px; }
.cat .subs span { font-size: 12.5px; color: var(--ink-2); border: 1px solid var(--rule); border-radius: 999px; padding: 2px 8px; }
.cat .subs span i { font-style: normal; font-family: var(--f-sans); color: var(--ink-3); margin-left: 5px; }
.notesec { display: grid; gap: 14px; margin-top: 34px; max-width: 92ch; }
.notesec dl { margin: 0; display: grid; grid-template-columns: 190px minmax(0, 1fr); gap: 10px 18px; }
.notesec dt { font: 500 12.5px/1.6 var(--f-sans); letter-spacing: 0.05em; text-transform: uppercase; color: var(--ink-3); }
.notesec dd { margin: 0; color: var(--ink-2); }

/* memo */
.memometa { margin: 0 0 14px; }
.prose { max-width: 80ch; }
.prose h2 { font-size: 22px; font-weight: 700; margin: 28px 0 10px; }
.prose h2:first-child { margin-top: 0; }
.prose p, .prose li { font-size: 16px; line-height: 1.6; color: var(--ink); }
.prose p { margin: 0 0 12px; }
.prose ul, .prose ol { margin: 0 0 14px; padding-left: 22px; display: grid; gap: 8px; }
.prose ol { padding-left: 34px; }
.prose .tbl-wrap { margin: 6px 0 14px; max-width: none; }
.excl { margin-top: 8px; }

/* record panel */
.scrim { position: fixed; inset: 0; background: var(--scrim); z-index: 20; }
.drawer { position: fixed; top: 0; right: 0; bottom: 0; width: min(560px, 100%); background: var(--panel); border-left: 1px solid var(--rule); box-shadow: var(--shadow); z-index: 21; display: flex; flex-direction: column; padding-top: env(safe-area-inset-top, 0px); padding-bottom: env(safe-area-inset-bottom, 0px); padding-right: env(safe-area-inset-right, 0px); }
.dhead { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; padding: 18px 18px 12px; border-bottom: 1px solid var(--rule-2); }
.dhead .eyebrow { display: flex; align-items: center; }
.dhead h3 { margin: 6px 0 0; font-size: 21px; line-height: 1.25; font-weight: 700; text-wrap: balance; overflow-wrap: anywhere; }
.x { appearance: none; border: 1px solid var(--rule); background: var(--panel); color: var(--ink); border-radius: 5px; font: 600 15px/1 var(--f-sans); padding: 9px 12px; cursor: pointer; flex: none; }
.dbody { overflow-y: auto; padding: 14px 18px 28px; display: grid; gap: 18px; align-content: start; }
.dnote { margin: 0; padding: 12px 14px; background: var(--tint); border-left: 3px solid var(--accent); border-radius: 0 4px 4px 0; font-size: 15.5px; line-height: 1.5; }
.dnote p { margin: 0; }
.dnote .dnl { font: 500 12px/1.4 var(--f-sans); letter-spacing: 0.05em; text-transform: uppercase; color: var(--ink-3); margin-bottom: 4px; }
.dtags { display: flex; flex-wrap: wrap; gap: 6px; }
.dgrp h4 { margin: 0 0 8px; font: 600 12.5px/1.2 var(--f-sans); letter-spacing: 0.06em; text-transform: uppercase; color: var(--accent); padding-bottom: 6px; border-bottom: 1px solid var(--rule-2); }
.dl { display: grid; grid-template-columns: 136px minmax(0, 1fr); gap: 10px 14px; margin: 0; font-size: 15px; }
.dl dt { color: var(--ink-3); font-size: 12px; font-family: var(--f-sans); text-transform: uppercase; letter-spacing: 0.04em; padding-top: 2px; line-height: 1.45; }
.dl dd { margin: 0; overflow-wrap: anywhere; line-height: 1.5; }
.dl dd p { margin: 0; }
.copy { appearance: none; margin-left: 8px; font: 600 12px/1 var(--f-sans); color: var(--accent); background: none; border: 1px solid var(--rule); border-radius: 4px; padding: 4px 7px; cursor: pointer; }
ul.src, ul.refs { list-style: none; margin: 0; padding: 0; display: grid; gap: 7px; }
ul.src li, ul.refs li { font-size: 14px; line-height: 1.5; }
ul.refs li { padding-left: 12px; text-indent: -12px; }
.k { display: inline-block; font: 500 11px/1.6 var(--f-sans); padding: 0 6px; border-radius: 999px; margin-right: 6px; border: 1px solid var(--rule); color: var(--ink-2); text-transform: uppercase; letter-spacing: 0.03em; }
.s-primary { border-color: var(--ok); color: var(--ok); }
.s-secondary { border-color: var(--accent); color: var(--accent); }
.s-check { border-color: var(--focus); color: var(--focus); }

footer { margin-top: 44px; padding-top: 16px; border-top: 1px solid var(--rule); font-size: 14px; color: var(--ink-3); max-width: 100ch; }

@media (max-width: 760px) {
  .wrap { padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); }
  .tglabel { flex-basis: 100%; margin: 10px 0 0; }
  .tabs button { padding: 11px 8px 10px; font-size: 15px; }
  .row { grid-template-columns: minmax(0, 1fr); gap: 6px; }
  .row .meta { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
  .badges { justify-content: flex-start; max-width: none; }
  .dl { grid-template-columns: minmax(0, 1fr); gap: 2px 0; }
  .dl dd { margin-bottom: 8px; }
  .notesec dl { grid-template-columns: minmax(0, 1fr); gap: 2px; }
  .notesec dd { margin-bottom: 10px; }
  .stats { gap: 10px 22px; }
  .legend { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 5px 14px; font-size: 14px; line-height: 1.35; }
  .flabel { min-width: 0; flex-basis: 100%; }
}
@media (min-width: 761px) { .row .meta { display: contents; } }
@media (prefers-reduced-motion: no-preference) { .drawer { animation: slide 0.18s ease-out; } @keyframes slide { from { transform: translateX(16px); opacity: 0.6; } to { transform: none; opacity: 1; } } }
"""
CSS = CSS.replace("%GENRE_TOKENS%", "\n".join(f"  --g{g}: {c};" for g, c in GENRE_COLOR.items()))

LABELS = {
    "genre": {g: genre_short[g] for g in GENRES_WITH},
    "syn": {k: f"Type {k}, {SYN_SHORT[k]}" for k in SYN_SHORT},
    "ver": {c: l for k, (c, l) in VER.items()},
    "named": {"1": "Named producer", "0": "Anonymous producer"},
    "discl": {"1": "Disclosed at origin"},
    "circl": {"1": "Still disclosed in circulation"},
    "just": {"1": "Justification given", "0": "No justification"},
    "inv": {"1": "People affected involved", "0": "People affected not involved"},
    "auth": {"1": "Presented as authentic", "0": "Not presented as authentic"},
    "real": {"1": "Real person depicted", "0": "No real person depicted"},
    "cons": {"1": "Policy or guideline consequence", "0": "No policy consequence"},
    "liar": {"1": "Liar's dividend documented"},
    "lost": {"1": "Label lost in circulation"},
    "rem": {"1": "Removal reported"},
    "apo": {"1": "Apology reported"},
    "fact": {"1": "Fact-checked"},
    "q": {k: "Question: " + v[0].lower() for k, v in QUESTIONS.items()},
    "year": {"_": "Year"},
    "regs": {"_": "Suffering in"},
    "regp": {"_": "Producer in"},
    "south": {"1": "Suffering in the Global South"},
    "north": {"1": "Producer in the Global North"},
    "regime": {"qualified": "Qualified regime", "unqualified": "Unqualified regime"},
    "group": {"hum": "Humanitarian communication", "named": "Other qualified genres", "other": "Unqualified genres"},
    "prod": {k: v for k, v in PROD_LABEL.items()},
    "truth": {truth_slug[v]: v for v in TRUTH_ORDER},
}

JS = r"""
(() => {
  const $ = (s) => document.querySelector(s);
  const REC = JSON.parse(document.getElementById('recs').textContent);
  const LABELS = %LABELS%;
  const TABS = ['ledger', 'timeline', 'memo', 'fields', 'matrix', 'map', 'questions', 'readings', 'method'];
  const ANALYSIS = ['matrix', 'map', 'questions', 'readings', 'method'];
  const ALIAS = { overview: 'matrix', cases: 'ledger', debate: 'matrix', paper: 'questions', across: 'readings' };
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const box = $('#ledgerList');
  const rows = Array.from(box.querySelectorAll(':scope > .row'));
  const total = rows.length;
  const state = { q: '', genres: new Set(), syns: new Set(), vers: new Set(), truth: '', key: false, focus: [], sort: 'date' };
  let current = 'ledger';

  /* tabs */
  function setTab(name, keepScroll) {
    if (!TABS.includes(name)) name = 'ledger';
    current = name;
    for (const t of TABS) {
      $('#v-' + t).hidden = t !== name;
      $('#t-' + t).setAttribute('aria-selected', String(t === name));
      $('#t-' + t).tabIndex = t === name ? 0 : -1;
    }
    $('#aband').hidden = !ANALYSIS.includes(name);
    if (location.hash.slice(1) !== name) history.replaceState(null, '', '#' + name);
    if (!keepScroll) {
      const nav = $('#tabs');
      if (nav.getBoundingClientRect().top < 0) nav.scrollIntoView({ block: 'start', behavior: reduce ? 'auto' : 'smooth' });
    }
  }
  document.querySelectorAll('#tabs [role=tab]').forEach((b) => {
    b.addEventListener('click', () => setTab(b.id.slice(2), true));
    b.addEventListener('keydown', (e) => {
      if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
      const i = TABS.indexOf(current) + (e.key === 'ArrowRight' ? 1 : -1);
      const next = TABS[(i + TABS.length) % TABS.length];
      setTab(next, true); $('#t-' + next).focus(); e.preventDefault();
    });
  });

  /* filters */
  function label(k, v) {
    const L = LABELS[k] || {};
    const one = (x) => L[x] || (L._ ? L._ + ' ' + x : k + ' ' + x);
    if (v.startsWith('!')) return 'Not ' + one(v.slice(1)).replace(/^./, (c) => c.toLowerCase());
    const parts = v.split('|');
    if (parts.length > 1) return (L._ || k) + ' ' + parts.slice(0, -1).join(', ') + ' or ' + parts[parts.length - 1];
    return one(v);
  }
  function attrOk(d, k, v) {
    if (k === 'discl') return ['label', 'caption', 'statement'].includes(d.disc);
    if (k === 'circl') return ['label', 'caption', 'statement'].includes(d.circ);
    if (k === 'q') return d.q.split(' ').includes(v);
    const neg = v.startsWith('!');
    const vals = (neg ? v.slice(1) : v).split('|');
    const hit = vals.includes(String(d[k] == null ? '' : d[k]));
    return neg ? !hit : hit;
  }
  function visible(r) {
    const d = r.dataset;
    if (state.genres.size && !state.genres.has(d.genre)) return false;
    if (state.syns.size && !state.syns.has(d.syn)) return false;
    if (state.vers.size && !state.vers.has(d.ver)) return false;
    if (state.truth && d.truth !== state.truth) return false;
    if (state.key && d.key !== '1') return false;
    if (!state.focus.every(({ k, v }) => attrOk(d, k, v))) return false;
    const terms = state.q.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const blob = REC[d.id].s;
    return terms.every((t) => blob.includes(t));
  }
  function byDate(a, b, dir) {
    const x = a.dataset.d, y = b.dataset.d;
    if (!x && !y) return a.dataset.n - b.dataset.n;
    if (!x) return 1;
    if (!y) return -1;
    return dir * x.localeCompare(y) || a.dataset.n - b.dataset.n;
  }
  const ORDER = {
    date: (a, b) => byDate(a, b, 1),
    'date-desc': (a, b) => byDate(a, b, -1),
    genre: (a, b) => a.dataset.genre - b.dataset.genre || byDate(a, b, 1),
    id: (a, b) => a.dataset.n - b.dataset.n,
  };
  function render() {
    rows.slice().sort(ORDER[state.sort]).forEach((r) => box.appendChild(r));
    let n = 0;
    for (const r of rows) { const ok = visible(r); r.hidden = !ok; if (ok) n += 1; }
    $('#count').textContent = (n === total ? 'All ' + total + ' cases shown' : n + (n === 1 ? ' case' : ' cases') + ' shown of ' + total) + ' · * dated by year alone';
    $('#empty').hidden = n > 0;
    $('#focus').innerHTML = state.focus.map((x, i) => '<span class="fchip">' + label(x.k, x.v) + '<button type="button" data-i="' + i + '" aria-label="Remove this filter">×</button></span>').join('');
    document.querySelectorAll('.chip[data-set]').forEach((c) => c.setAttribute('aria-pressed', String(state[c.dataset.set].has(c.dataset.v))));
    $('#ftruth').value = state.truth; $('#fkey').checked = state.key; $('#q').value = state.q; $('#sort').value = state.sort;
  }
  function clearAll() {
    state.q = ''; state.truth = ''; state.key = false; state.focus = [];
    state.genres.clear(); state.syns.clear(); state.vers.clear();
  }
  function setFilters(obj) {
    clearAll();
    for (const [k, raw] of Object.entries(obj)) {
      const v = String(raw);
      const simple = !v.includes('|') && !v.startsWith('!');
      if (k === 'genre' && simple) state.genres.add(v);
      else if (k === 'syn' && simple) state.syns.add(v);
      else if (k === 'ver' && simple) state.vers.add(v);
      else state.focus.push({ k, v });
    }
    render();
    setTab('ledger');
  }
  document.querySelectorAll('.chip[data-set]').forEach((c) => c.addEventListener('click', () => {
    const s = state[c.dataset.set]; s.has(c.dataset.v) ? s.delete(c.dataset.v) : s.add(c.dataset.v); render();
  }));
  let timer;
  $('#q').addEventListener('input', (e) => { clearTimeout(timer); timer = setTimeout(() => { state.q = e.target.value; render(); }, 120); });
  $('#sort').addEventListener('change', (e) => { state.sort = e.target.value; render(); });
  $('#ftruth').addEventListener('change', (e) => { state.truth = e.target.value; render(); });
  $('#fkey').addEventListener('change', (e) => { state.key = e.target.checked; render(); });
  $('#reset').addEventListener('click', () => { clearAll(); state.sort = 'date'; render(); });
  $('#empty-reset').addEventListener('click', () => { clearAll(); render(); });
  $('#focus').addEventListener('click', (e) => { const b = e.target.closest('button[data-i]'); if (b) { state.focus.splice(Number(b.dataset.i), 1); render(); } });

  /* record panel */
  let lastFocus = null;
  function openCase(id) {
    const r = REC[id]; if (!r) return;
    if (!$('#drawer').hidden && $('#drawer').dataset.id === id) return;
    if ($('#drawer').hidden) lastFocus = document.activeElement;
    $('#dcase').innerHTML = r.e; $('#dtitle').textContent = r.t; $('#dbody').innerHTML = r.b;
    $('#drawer').dataset.id = id;
    $('#scrim').hidden = false; $('#drawer').hidden = false;
    $('#dbody').scrollTop = 0;
    if (location.hash.slice(1) !== id) history.replaceState(null, '', '#' + id);
    $('#dclose').focus();
  }
  function closeCase() {
    $('#scrim').hidden = true; $('#drawer').hidden = true; $('#drawer').dataset.id = '';
    history.replaceState(null, '', '#' + current);
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }
  $('#dclose').addEventListener('click', closeCase);
  $('#scrim').addEventListener('click', closeCase);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !$('#drawer').hidden) closeCase(); });
  $('#dbody').addEventListener('click', (e) => {
    const b = e.target.closest('[data-copy]'); if (!b) return;
    const done = () => { b.textContent = 'Copied'; setTimeout(() => { b.textContent = 'Copy'; }, 1400); };
    const fallback = () => { const rg = document.createRange(); rg.selectNodeContents(b.previousElementSibling); const s = window.getSelection(); s.removeAllRanges(); s.addRange(rg); b.textContent = 'Selected'; };
    try { navigator.clipboard.writeText(b.dataset.copy).then(done, fallback); } catch (err) { fallback(); }
  });
  box.addEventListener('click', (e) => { const r = e.target.closest('.row'); if (r) openCase(r.dataset.id); });
  box.addEventListener('keydown', (e) => { if ((e.key === 'Enter' || e.key === ' ') && e.target.classList.contains('row')) { e.preventDefault(); openCase(e.target.dataset.id); } });

  /* marks, grids, evidence and links */
  document.addEventListener('click', (e) => {
    const a = e.target.closest('a[href^="#C"]');
    if (a) { e.preventDefault(); openCase(a.getAttribute('href').slice(1)); return; }
    const pt = e.target.closest('.pt[data-id]');
    if (pt) { openCase(pt.dataset.id); return; }
    const c = e.target.closest('[data-case]');
    if (c) { openCase(c.dataset.case); return; }
    const f = e.target.closest('[data-filter]');
    if (f) { if (!$('#drawer').hidden) closeCase(); setFilters(JSON.parse(f.dataset.filter)); return; }
    const g = e.target.closest('[data-go]');
    if (g) setTab(g.dataset.go);
  });
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    const pt = e.target.closest && e.target.closest('.pt[data-id]');
    if (pt) { e.preventDefault(); openCase(pt.dataset.id); }
  });

  /* timeline ring */
  function ring() {
    const k = $('#ring').value;
    document.querySelectorAll('#tl .pt').forEach((p) => p.classList.toggle('ringed', k !== 'none' && p.dataset[k] === '1'));
  }
  $('#ring').addEventListener('change', ring);

  /* routing */
  function route() {
    const h = decodeURIComponent(location.hash.slice(1));
    if (/^C\d{2,3}$/.test(h) && REC[h]) { if ($('#v-' + current).hidden) setTab('ledger', true); openCase(h); return; }
    const t = ALIAS[h] || h;
    if (!$('#drawer').hidden) { $('#scrim').hidden = true; $('#drawer').hidden = true; }
    setTab(TABS.includes(t) ? t : 'ledger', true);
  }
  window.addEventListener('hashchange', route);
  render(); ring();
  const h0 = decodeURIComponent(location.hash.slice(1));
  if (/^C\d{2,3}$/.test(h0) && REC[h0]) { setTab('ledger', true); openCase(h0); }
  else setTab(TABS.includes(ALIAS[h0] || h0) ? (ALIAS[h0] || h0) : 'ledger', true);
})();
"""
JS = JS.replace("%LABELS%", json.dumps(LABELS, ensure_ascii=False))


def tab(k, lab, sel=False):
    return f'<button role="tab" id="t-{k}" aria-controls="v-{k}" aria-selected="{str(sel).lower()}" tabindex="{0 if sel else -1}">{esc(lab)}</button>'


truth_opts = "".join(f'<option value="{truth_slug[v]}">{esc(TRUTH_SHORT[v])} ({truth_counts[v]})</option>' for v in TRUTH_ORDER if truth_counts[v])
q_names = names(Q_GENRES)
u_names = names(U_GENRES)

page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex">
<title>Synthetic Suffering Cases</title>
<meta name="claude:viewport-fit-sides" content="cover">
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <header class="masthead">
    <div class="eyebrow">Case database &middot; state on {esc(memo_date)}</div>
    <h1>Synthetic Suffering</h1>
    <p class="lede">{esc(LEDE)}</p>
    <div class="casebar" role="img" aria-label="{esc(bar_label)}">{bar}</div>
    <div class="legend">{legend}</div>
    <dl class="stats">{stats_html}</dl>
  </header>

  <nav class="tabs" id="tabs" role="tablist" aria-label="Views">
    <div class="tgroup" role="presentation"><span class="tglabel" aria-hidden="true">Database</span>
      {tab("ledger", "Ledger", True)}{tab("timeline", "Timeline")}{tab("memo", "Search memo")}{tab("fields", "Fields")}
    </div>
    <div class="tgroup" role="presentation"><span class="tglabel" aria-hidden="true">Analysis</span>
      {tab("matrix", "Matrix")}{tab("map", "Map")}{tab("questions", "Questions")}{tab("readings", "Across genres")}{tab("method", "Method")}
    </div>
  </nav>

  <div class="aband" id="aband" hidden>
    <span class="status"><b>Search memo {esc(memo_version)}</b> {esc(memo_total_searches)} searches{", " + esc(NOT_SEARCHED_TEXT) if NOT_SEARCHED_TEXT else ""}</span>
    <button type="button" class="kchip rg-qualified" data-filter="{fattr({"regime": "qualified"})}" title="{esc(q_names)}">Qualified regime <span class="n">{S["n_q"]}</span></button>
    <button type="button" class="kchip rg-unqualified" data-filter="{fattr({"regime": "unqualified"})}" title="{esc(u_names)}">Unqualified regime <span class="n">{S["n_u"]}</span></button>
  </div>

  <section id="v-ledger" role="tabpanel" aria-labelledby="t-ledger">
    <div class="filters">
      <div class="frow">
        <input type="search" id="q" placeholder="Search every field of the cases" aria-label="Search every field of the cases" autocomplete="off">
        <select id="sort" aria-label="Sort order">
          <option value="date">Oldest first</option><option value="date-desc">Newest first</option>
          <option value="genre">By genre</option><option value="id">By ID</option>
        </select>
        <button class="btn" id="reset" type="button">Reset</button>
      </div>
      <div class="frow"><span class="flabel">Genre</span>{genre_chips}</div>
      <div class="frow"><span class="flabel">Synthesis</span>{syn_chips}</div>
      <div class="frow"><span class="flabel">Sources</span>{ver_chips}</div>
      <div class="frow"><span class="flabel">Truth claim</span>
        <select id="ftruth" aria-label="Truth claim"><option value="">Every truth claim</option>{truth_opts}</select>
        <label class="check"><input type="checkbox" id="fkey"> The {words(n_key)} key cases of the memo</label>
      </div>
    </div>
    <div class="countrow"><p class="count" id="count" aria-live="polite">All {n_total} cases shown</p><span id="focus"></span></div>
    <div class="ledger" id="ledgerList">
{ledger_rows}
    </div>
    <div class="empty" id="empty" hidden>No case matches these filters. <button type="button" class="btn" id="empty-reset">Reset the filters</button></div>
  </section>

  <section id="v-timeline" role="tabpanel" aria-labelledby="t-timeline" hidden>
    <p class="intro">Each mark is one case, placed on the line of its genre by the month in which it was first published or circulated. A hollow mark is a case dated by year alone and placed in the middle of that year, and the column n.d. holds the cases without a date.</p>
    {timeline_html}
    <p class="tnote">The ring marks the cases chosen in the menu above the chart, and selecting a mark opens the record of the case.</p>
  </section>

  <section id="v-memo" role="tabpanel" aria-labelledby="t-memo" hidden>
    {memo_html}
  </section>

  <section id="v-fields" role="tabpanel" aria-labelledby="t-fields" hidden>
    {fields_html}
  </section>

  <section id="v-matrix" role="tabpanel" aria-labelledby="t-matrix" hidden>
    {matrix_html}
  </section>

  <section id="v-map" role="tabpanel" aria-labelledby="t-map" hidden>
    {map_html}
  </section>

  <section id="v-questions" role="tabpanel" aria-labelledby="t-questions" hidden>
    {questions_html}
  </section>

  <section id="v-readings" role="tabpanel" aria-labelledby="t-readings" hidden>
    {readings_html}
  </section>

  <section id="v-method" role="tabpanel" aria-labelledby="t-method" hidden>
    {method_html}
  </section>

  <footer>Built on {BUILD_DATE} from synthetic_suffering_cases.csv and synthetic_suffering_memo.md in the Synthetic Suffering project, by build_page.py, which is published beside this page. The design follows the Biometric Identification archive, and links to sources open in a new tab.</footer>
</div>

<div class="scrim" id="scrim" hidden></div>
<aside class="drawer" id="drawer" hidden role="dialog" aria-modal="true" aria-labelledby="dtitle">
  <div class="dhead">
    <div><div class="eyebrow" id="dcase"></div><h3 id="dtitle"></h3></div>
    <button class="x" id="dclose" type="button">Close</button>
  </div>
  <div class="dbody" id="dbody"></div>
</aside>

<script type="application/json" id="recs">{recs_json}</script>
<script>{JS}</script>
</body>
</html>
"""

# ------------------------------------------------------------------ readings file

if READINGS_PATH:
    with open(READINGS_PATH, "w", encoding="utf-8") as fh:
        fh.write("# Readings on the case database page\n\n> **Version:** " + READINGS_VERSION + "  \n> **Last updated:** " + BUILD_DATE + "\n\n")
        for rid, title, _, paras_ in CARDS:
            fh.write(f"## {rid} {title}\n\n" + "\n\n".join(paras_) + "\n\n")
        fh.write("## Coding notes\n\n" + "\n\n".join(CODING_NOTES) + "\n")

open(OUT_PATH, "w", encoding="utf-8").write(page)
print(f"wrote {OUT_PATH}: {len(page.encode('utf-8')):,} bytes, {n_total} cases, {date_span}")
print("regimes:", {genre_short[g]: regime[g] for g in GENRES_WITH})
print("stats:", {k: v for k, v in S.items() if not isinstance(v, str)})
print("lost in circulation:", [c for c in D if D[c]["lost"]], "leads:", len(lead_rows))
