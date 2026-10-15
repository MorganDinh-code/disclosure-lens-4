"""
batch_tools.py  --  bulk document tools for Disclosure Lens
=============================================================

Put this file in your project ROOT (next to app.py, taxonomy.py and the
`disclosure_lens` folder). Run commands from the VS Code terminal with python3.

ONE-TIME SETUP
    python3 -m pip install pypdf

THE WORKFLOW
    1. Drop PDFs / .htm / .html / .txt files into   data/incoming/
    2. python3 batch_tools.py convert     (makes clean .txt files in data/raw/)
    3. python3 batch_tools.py meta        (auto-fills data/metadata.csv: reads each
       document for date/period/type/ticker, then looks the company and its
       sector up on SEC EDGAR and remembers it in data/company_lookup.csv)
    4. python3 batch_tools.py analyze     (saves records into database/; anything it
       could not work out gets a placeholder: sector "Unassigned", period
       "Unknown-xxxx", blank date. Fix those later in the Owner portal.)
    5. Commit AND push, then wait for Streamlit to redeploy.
       The Database and Stats pages show the new records automatically.

    Zero-touch version:   python3 batch_tools.py all

    Naming files  TICKER_FILINGTYPE_PERIOD_DATE  pre-fills step 4:
        META_Earnings-Call_Q2-2026_2026-07-29.pdf

COMMANDS
    convert   PDFs/HTML -> clean .txt in data/raw/
    meta      create/update data/metadata.csv (never overwrites what you typed)
    analyze   build site records (same code as the Owner portal) -> database/
    status    show counts and what is missing
    all       convert + meta + analyze

OPTIONS
    --force            redo files already converted, or overwrite records
    --src FOLDER       convert from another folder (default data/incoming)
    --keep-tables      keep table text when converting HTML
    --no-auto          meta: skip auto-fill (fill everything by hand)
    --offline          meta: skip the SEC company/sector lookup
    --no-source-text   do not store the full document text inside each record
"""

import argparse
import csv
import difflib
import hashlib
import json
import re
import shutil
import sys
import time
import urllib.request
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

# ----------------------------------------------------------------------------
# Paths (relative to this file, so it works no matter where you run it from)
# ----------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
INCOMING = ROOT / "data" / "incoming"
RAW = ROOT / "data" / "raw"
META_FILE = ROOT / "data" / "metadata.csv"
DB_DIR = ROOT / "database"          # where the website reads its records from
LOOKUP_FILE = ROOT / "data" / "company_lookup.csv"   # remembers each company once (you can edit it)
SEC_CACHE = ROOT / "data" / ".sec_tickers.json"

# SEC EDGAR asks every program to identify itself. Put YOUR real name and email here:
SEC_USER_AGENT = "DisclosureLens research your-email@example.com"

META_COLS = ["filename", "ticker", "company", "sector", "filing_type", "period", "date", "source_url"]
REQUIRED = ["ticker", "company", "sector", "filing_type", "period", "date"]
TERMINAL = (".", "?", "!", '"', "\u201d", ")", ":")


# ----------------------------------------------------------------------------
# 1. TEXT CLEANING  (shared by PDF / HTML / TXT converters)
# ----------------------------------------------------------------------------
def _normalize_chars(s: str) -> str:
    """Fix ligatures, odd spaces, and stray control characters."""
    for a, b in {"\ufb01": "fi", "\ufb02": "fl", "\ufb00": "ff", "\ufb03": "ffi",
                 "\ufb04": "ffl", "\u00a0": " ", "\u2009": " ", "\u200b": "",
                 "\u00ad": "", "\r": ""}.items():
        s = s.replace(a, b)
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s)


def _looks_like_new_block(line: str) -> bool:
    """Bullets and 'Speaker Name:' labels start a new paragraph."""
    if re.match(r"^\s*([\u2022\u25cf\u25aa\-\*]\s+|\(?\d{1,2}[.)]\s+)", line):
        return True
    return bool(re.match(r"^[A-Z][A-Za-z.'\-]+( [A-Z][A-Za-z.'\-]+){0,3}\s*[:\u2014\u2013-]\s", line)
                and len(line) < 400 and line.split(":")[0].count(" ") <= 3)


def reflow(lines):
    """
    PDFs break lines at the page width, not at paragraph ends. This rebuilds
    paragraphs: blank line between paragraphs, one block of text inside each.
    Disclosure Lens splits on blank lines, so this step matters.
    """
    lines = [ln.rstrip() for ln in lines]
    lengths = sorted(len(ln) for ln in lines if len(ln.strip()) > 25)
    full = lengths[int(len(lengths) * 0.75)] if lengths else 80
    short_cut = full * 0.6

    paras, cur = [], []

    def flush():
        if cur:
            paras.append(" ".join(cur).strip())
            cur.clear()

    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s:
            flush()
            continue
        if cur and _looks_like_new_block(s) and cur[-1].endswith(TERMINAL):
            flush()
        # dehyphenate "dis-\nclosure"
        if cur and cur[-1].endswith("-") and len(cur[-1]) > 1 and cur[-1][-2].isalpha() and s[:1].islower():
            cur[-1] = cur[-1][:-1] + s
        else:
            cur.append(s)
        # short line that ends a sentence = end of paragraph
        if len(s) < short_cut and s.endswith(TERMINAL):
            flush()
    flush()
    return "\n\n".join(p for p in paras if p)


def _finish(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


# ----------------------------------------------------------------------------
# 2. CONVERTERS
# ----------------------------------------------------------------------------
def pdf_to_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        sys.exit("Missing library. Run:  pip install pypdf")

    reader = PdfReader(str(path))
    pages = [(_normalize_chars(p.extract_text() or "")).split("\n") for p in reader.pages]

    # Remove repeated headers/footers and bare page numbers.
    def key(ln):
        return re.sub(r"\d+", "#", ln.strip().lower())

    def edges(pg):
        idx = [i for i, ln in enumerate(pg) if ln.strip()]
        return set(idx[:2] + idx[-2:])

    # Only the first/last 2 lines of a page can be headers/footers.
    counts = Counter(key(pg[i]) for pg in pages for i in edges(pg))
    n = len(pages)
    page_num = re.compile(r"^\s*(page\s*)?\d{1,4}(\s*(of|/)\s*\d{1,4})?\s*$", re.I)
    cleaned = []
    for pg in pages:
        edge = edges(pg)
        for i, ln in enumerate(pg):
            s = ln.strip()
            if page_num.match(s):
                continue
            if n >= 3 and i in edge and s and len(s) < 70 and counts[key(ln)] >= max(3, 0.5 * n):
                continue
            cleaned.append(ln)
        # no blank line at page boundaries: sentences can continue onto the next page

    text = reflow(cleaned)
    if len(text.split()) < 30:
        raise ValueError("almost no text found (scanned image PDF? it needs OCR first)")
    return _finish(text)


class _HTMLText(HTMLParser):
    BLOCK = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6",
             "section", "article", "blockquote", "pre", "hr", "center"}
    SKIP = {"script", "style", "head", "title", "noscript"}

    def __init__(self, keep_tables=False):
        super().__init__(convert_charrefs=True)
        self.keep_tables = keep_tables
        self.paras, self.buf = [], []
        self.skip = 0
        self.table = 0

    def _flush(self):
        t = re.sub(r"\s+", " ", _normalize_chars("".join(self.buf))).strip()
        if t:
            self.paras.append(t)
        self.buf = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag == "table":
            self._flush()
            self.table += 1
        elif tag in self.BLOCK:
            self._flush()

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag == "table":
            self.table = max(0, self.table - 1)
            self._flush()
        elif tag in self.BLOCK:
            self._flush()

    def handle_data(self, data):
        if self.skip:
            return
        if self.table and not self.keep_tables:
            return
        self.buf.append(data)


def html_to_text(path: Path, keep_tables=False) -> str:
    raw = path.read_bytes().decode("utf-8", errors="ignore")
    p = _HTMLText(keep_tables)
    p.feed(raw)
    p._flush()
    text = "\n\n".join(p.paras)
    if len(text.split()) < 30:
        raise ValueError("almost no text found in HTML")
    return _finish(text)


def txt_to_text(path: Path) -> str:
    text = _normalize_chars(path.read_bytes().decode("utf-8", errors="ignore"))
    if "\n\n" not in text.strip():          # no paragraph breaks -> rebuild them
        text = reflow(text.split("\n"))
    return _finish(text)


def convert_file(path: Path, keep_tables=False) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return pdf_to_text(path)
    if ext in (".htm", ".html"):
        return html_to_text(path, keep_tables)
    if ext == ".txt":
        return txt_to_text(path)
    raise ValueError(f"unsupported file type {ext}")


def safe_name(stem: str) -> str:
    return re.sub(r"[^A-Za-z0-9._\-]+", "_", stem).strip("_")


def cmd_convert(src: Path, force=False, keep_tables=False):
    src.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in src.iterdir() if p.suffix.lower() in (".pdf", ".htm", ".html", ".txt"))
    if not files:
        print(f"No files in {src}. Drop PDFs / HTML / TXT there first.")
        return
    ok = skipped = 0
    failed = []
    for i, p in enumerate(files, 1):
        out = RAW / (safe_name(p.stem) + ".txt")
        if out.exists() and not force:
            skipped += 1
            continue
        try:
            out.write_text(convert_file(p, keep_tables), encoding="utf-8")
            ok += 1
        except Exception as e:
            failed.append((p.name, str(e)))
        if i % 25 == 0:
            print(f"  converted {i}/{len(files)}")
    print(f"Convert: {ok} converted, {skipped} already done, {len(failed)} failed -> {RAW}")
    for name, err in failed:
        print(f"  FAILED: {name} - {err}")


# ----------------------------------------------------------------------------
# 3. METADATA  (what the website needs to file each document)
# ----------------------------------------------------------------------------
def load_taxonomy():
    """Returns (SECTORS, FILING_TYPES) from your taxonomy.py, or (None, None)."""
    sys.path.insert(0, str(ROOT))
    try:
        from taxonomy import FILING_TYPES, SECTORS
        return list(SECTORS), list(FILING_TYPES)
    except Exception:
        return None, None


def _match(value, options):
    """Case-insensitive match of a guessed value to an allowed taxonomy name."""
    if not options:
        return value
    v = re.sub(r"[\s_\-]+", "", value).lower()
    for o in options:
        if re.sub(r"[\s_\-]+", "", o).lower() == v:
            return o
    return ""


def guess_meta(filename: str) -> dict:
    """Blank row. Only a leading ALL-CAPS ticker in the filename (META_...) is trusted here;
    auto_fill reads everything else from the filename and the document text."""
    row = {c: "" for c in META_COLS}
    row["filename"] = filename
    first = Path(filename).stem.split("_")[0]
    if re.fullmatch(r"[A-Z]{1,5}", first):
        row["ticker"] = first
    return row


def read_meta() -> dict:
    if not META_FILE.exists():
        return {}
    with open(META_FILE, newline="", encoding="utf-8") as f:
        return {r["filename"]: r for r in csv.DictReader(f)}


def write_meta(rows: dict):
    META_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(META_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=META_COLS, extrasaction="ignore", restval="")
        w.writeheader()
        for k in sorted(rows):
            w.writerow(rows[k])


def problems(row: dict, sectors, types) -> list:
    """What is wrong with a metadata row (empty list = ready to analyze)."""
    out = [f"missing {c}" for c in REQUIRED if not (row.get(c) or "").strip()]
    if sectors and row.get("sector") and row["sector"] not in sectors:
        out.append(f"sector '{row['sector']}' is not in taxonomy.py")
    if types and row.get("filing_type") and row["filing_type"] not in types:
        out.append(f"filing_type '{row['filing_type']}' is not in taxonomy.py")
    return out


# ----------------------------------------------------------------------------
# 3b. AUTO-FILL  (reads each document + looks the company up on SEC EDGAR)
# ----------------------------------------------------------------------------
MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], 1)}
NAME_STOP = {"INC", "INCORPORATED", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LIMITED",
             "PLC", "HOLDINGS", "HOLDING", "GROUP", "THE", "LLC", "LP", "NV", "SA", "AG"}

# SEC industry code (SIC) -> broad sector. Approximate: spot-check the sectors it picks.
SIC_RULES = [
    (6798, 6798, "Real Estate"), (100, 999, "Consumer Staples"), (1000, 1099, "Materials"),
    (1200, 1399, "Energy"), (1400, 1499, "Materials"), (1500, 1799, "Industrials"),
    (2000, 2199, "Consumer Staples"), (2200, 2599, "Consumer Discretionary"), (2600, 2699, "Materials"),
    (2700, 2799, "Communication Services"), (2800, 2829, "Materials"), (2830, 2836, "Healthcare"),
    (2840, 2844, "Consumer Staples"), (2837, 2899, "Materials"), (2900, 2999, "Energy"),
    (3000, 3099, "Materials"), (3100, 3199, "Consumer Discretionary"), (3200, 3399, "Materials"),
    (3400, 3569, "Industrials"), (3570, 3579, "Technology"), (3580, 3599, "Industrials"),
    (3600, 3699, "Technology"), (3700, 3719, "Consumer Discretionary"), (3720, 3799, "Industrials"),
    (3800, 3839, "Technology"), (3840, 3851, "Healthcare"), (3852, 3999, "Consumer Discretionary"),
    (4000, 4799, "Industrials"), (4800, 4899, "Communication Services"), (4900, 4999, "Utilities"),
    (5000, 5099, "Industrials"), (5100, 5199, "Consumer Staples"), (5200, 5399, "Consumer Discretionary"),
    (5400, 5499, "Consumer Staples"), (5500, 5999, "Consumer Discretionary"), (6000, 6499, "Financials"),
    (6500, 6599, "Real Estate"), (6700, 6799, "Financials"), (7000, 7299, "Consumer Discretionary"),
    (7300, 7369, "Industrials"), (7370, 7379, "Technology"), (7380, 7399, "Industrials"),
    (7500, 7599, "Consumer Discretionary"), (7800, 7999, "Communication Services"),
    (8000, 8099, "Healthcare"), (8700, 8799, "Industrials"),
]
SECTOR_WORDS = {
    "Materials": ["material"], "Energy": ["energy", "oil"],
    "Technology": ["technolog", "software"], "Healthcare": ["health", "pharma"],
    "Financials": ["financ", "bank"], "Industrials": ["industr"],
    "Consumer Discretionary": ["discretion", "cyclical", "consumer"],
    "Consumer Staples": ["staple", "defensive", "consumer"], "Utilities": ["utilit"],
    "Real Estate": ["real estate", "reit"], "Communication Services": ["communic", "telecom", "media"],
}
TYPE_WORDS = {"call": ["call", "transcript"], "release": ["release"], "10-K": ["10-k", "annual"],
              "10-Q": ["10-q", "quarterly"], "8-K": ["8-k"], "letter": ["letter"], "mda": ["md&a", "discussion"]}
TYPE_DEFAULT = {"call": "Earnings call", "release": "Earnings release", "10-K": "10-K",
                "10-Q": "10-Q", "8-K": "8-K", "letter": "Shareholder letter", "mda": "MD&A"}


def sec_get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": SEC_USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read().decode("utf-8"))
    time.sleep(0.15)                      # SEC allows at most 10 requests/second
    return data


def norm_name(s: str) -> str:
    s = re.sub(r"[^A-Z0-9 ]+", " ", s.upper().replace("&", " AND "))
    return " ".join(t for t in s.split() if t not in NAME_STOP)


def get_sec_index():
    """Downloads SEC's ticker list once (cached 30 days). Returns None if offline."""
    try:
        if SEC_CACHE.exists() and time.time() - SEC_CACHE.stat().st_mtime < 30 * 86400:
            rows = json.loads(SEC_CACHE.read_text())
        else:
            raw = sec_get_json("https://www.sec.gov/files/company_tickers.json")
            rows = [{"ticker": v["ticker"], "title": v["title"], "cik": v["cik_str"]} for v in raw.values()]
            SEC_CACHE.parent.mkdir(parents=True, exist_ok=True)
            SEC_CACHE.write_text(json.dumps(rows))
    except Exception as e:
        print(f"  (Could not reach SEC EDGAR: {type(e).__name__}. Skipping company/sector lookup; "
              "everything else is still auto-filled.)")
        return None
    by_ticker, by_name = {}, {}
    for r in rows:
        by_ticker.setdefault(r["ticker"].upper(), r)
        by_name.setdefault(norm_name(r["title"]), r)
    return {"by_ticker": by_ticker, "by_name": by_name}


def resolve_company(ticker_hints, name_hint, sec):
    for t in ticker_hints:
        if t and t.upper() in sec["by_ticker"]:
            return sec["by_ticker"][t.upper()]
    if name_hint:
        n = norm_name(name_hint)
        if n in sec["by_name"]:
            return sec["by_name"][n]
        close = difflib.get_close_matches(n, list(sec["by_name"]), n=1, cutoff=0.9)
        if close:
            return sec["by_name"][close[0]]
    return None


def sic_to_sector(sic, sectors):
    label = next((lab for lo, hi, lab in SIC_RULES if lo <= sic <= hi), None)
    if label is None:
        return "", ""
    if not sectors:
        return label, label
    for s in sectors:                                    # exact name first
        if s.lower() == label.lower():
            return s, label
    for kw in SECTOR_WORDS.get(label, []):               # then keyword match
        for s in sectors:
            if kw in s.lower():
                return s, label
    return "", label                                     # no matching name in taxonomy.py


def pretty_company(name: str) -> str:
    if name.isupper():
        name = name.title()
        name = re.sub(r"\b(Inc|Corp|Co|Ltd|Plc|Llc|Lp)\b\.?", lambda m: m.group(1) + ".", name)
        name = name.replace("Corp.", "Corp.").replace("Co.", "Co.")
    return name


def read_lookup() -> dict:
    if not LOOKUP_FILE.exists():
        return {}
    with open(LOOKUP_FILE, newline="", encoding="utf-8") as f:
        return {r["ticker"].upper(): r for r in csv.DictReader(f)}


def write_lookup(rows: dict):
    LOOKUP_FILE.parent.mkdir(parents=True, exist_ok=True)
    cols = ["ticker", "company", "sector", "sic", "sic_description"]
    with open(LOOKUP_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, restval="", extrasaction="ignore")
        w.writeheader()
        for k in sorted(rows):
            w.writerow(rows[k])


def company_info(entry, lookup, sectors):
    """company_lookup.csv first (your edits win); otherwise ask SEC once and remember."""
    t = entry["ticker"].upper()
    row = lookup.get(t)
    if row and row.get("company") and row.get("sector"):
        return row
    row = dict(row or {"ticker": t, "company": pretty_company(entry["title"]), "sector": "",
                       "sic": "", "sic_description": ""})
    try:
        data = sec_get_json(f"https://data.sec.gov/submissions/CIK{int(entry['cik']):010d}.json")
        sic = int(data.get("sic") or 0)
        row["sic"], row["sic_description"] = sic or "", data.get("sicDescription", "")
        if not row.get("sector") and sic:
            row["sector"], _ = sic_to_sector(sic, sectors)
    except Exception:
        pass
    lookup[t] = row
    return row


def find_period(s: str) -> str:
    s = re.sub(r"_+", " ", s)
    m = re.search(r"\bQ([1-4])[\s\-]*(?:FY)?[\s\-]*'?(20\d{2}|\d{2})\b", s, re.I) or \
        re.search(r"\b([1-4])Q[\s\-]*'?(20\d{2}|\d{2})\b", s, re.I)
    if m:
        y = m.group(2)
        return f"Q{m.group(1)} {y if len(y) == 4 else '20' + y}"
    m = re.search(r"\b(first|second|third|fourth)\s+quarter(?:\s+of)?\s+(?:fiscal\s+)?(20\d{2})", s, re.I)
    if m:
        return f"Q{['first', 'second', 'third', 'fourth'].index(m.group(1).lower()) + 1} {m.group(2)}"
    m = re.search(r"\b(?:FY|fiscal\s+year(?:\s+ended)?)\s*'?(20\d{2})\b", s, re.I)
    return f"FY {m.group(1)}" if m else ""


def find_date(s: str) -> str:
    s = re.sub(r"_+", " ", s)
    m = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", s)
    if m:
        return m.group(0)
    mon = "|".join(MONTHS)
    for pat, order in ((rf"\b({mon})[a-z]*\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(20\d{{2}})\b", "mdy"),
                       (rf"\b(\d{{1,2}})\s+({mon})[a-z]*\.?,?\s+(20\d{{2}})\b", "dmy")):
        m = re.search(pat, s, re.I)
        if m:
            g = m.groups()
            mo, d, y = (g[0], g[1], g[2]) if order == "mdy" else (g[1], g[0], g[2])
            return f"{y}-{MONTHS[mo.lower()]:02d}-{int(d):02d}"
    return ""


def find_type(s: str, types) -> str:
    s = re.sub(r"_+", " ", s).lower()
    key = None
    for k, pat in (("10-K", r"10-?k\b|annual report"), ("10-Q", r"10-?q\b"), ("8-K", r"\b8-?k\b"),
                   ("call", r"earnings[\s\-]*call|conference call|transcript"),
                   ("release", r"press release|earnings release|reports? (?:first|second|third|fourth)"),
                   ("letter", r"letter to (?:share|stock)holders|shareholder letter"),
                   ("mda", r"md&a|management.s discussion")):
        if re.search(pat, s):
            key = k
            break
    if not key:
        return ""
    if not types:
        return TYPE_DEFAULT[key]
    for w in TYPE_WORDS[key]:
        for t in types:
            if w in t.lower():
                return t
    return ""


def auto_fill(row, path, sec, lookup, sectors, types):
    """Fills only the BLANK cells of a metadata row. Never overwrites what you typed."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    head = text[:6000]
    stem = Path(row["filename"]).stem
    if not row.get("period"):
        row["period"] = find_period(stem) or find_period(head[:3000])
    if not row.get("date"):
        row["date"] = find_date(stem) or find_date(head[:3000])
    if not row.get("filing_type"):
        row["filing_type"] = find_type(stem, types) or find_type(head[:1500], types)
    need_co = not (row.get("ticker") and row.get("company") and row.get("sector"))
    if need_co and sec:
        tick = re.findall(r"\b(?:NYSE|NASDAQ|Nasdaq)(?:\s+American|\s+Arca)?\s*[:\-]\s*([A-Z][A-Z.\-]{0,4})\b", head)
        first = re.split(r"_+", stem)[0]
        hints = ([max(set(tick), key=tick.count)] if tick else []) + \
                ([first.upper()] if re.fullmatch(r"[A-Za-z]{1,5}", first) else []) + [row.get("ticker", "")]
        entry = resolve_company(hints, re.sub(r"[-\s]+", " ", first).strip(), sec)
        if entry:
            info = company_info(entry, lookup, sectors)
            row["ticker"] = row.get("ticker") or info["ticker"]
            row["company"] = row.get("company") or info["company"]
            row["sector"] = row.get("sector") or info.get("sector", "")


def cmd_meta(auto=True, offline=False):
    meta = read_meta()
    new = 0
    for p in sorted(RAW.glob("*.txt")):
        if p.name not in meta:
            meta[p.name] = guess_meta(p.name)
            new += 1
    sectors, types = load_taxonomy()
    if auto:
        if "example.com" in SEC_USER_AGENT and not offline:
            print("  Tip: edit SEC_USER_AGENT near the top of batch_tools.py and put your real email in it "
                  "(SEC asks for this).")
        sec = None if offline else get_sec_index()
        lookup = read_lookup()
        for name, row in meta.items():
            if (RAW / name).exists():
                auto_fill(row, RAW / name, sec, lookup, sectors, types)
        if lookup:
            write_lookup(lookup)
    write_meta(meta)
    incomplete = {k: problems(r, sectors, types) for k, r in meta.items()}
    incomplete = {k: v for k, v in incomplete.items() if v}
    print(f"Metadata: {new} new rows ({len(meta)} total), {len(meta) - len(incomplete)} complete -> {META_FILE}")
    if incomplete:
        print(f"  {len(incomplete)} rows have gaps (they will still be uploaded with placeholders; "
              "you can fill them here or later in the Owner portal):")
        for k, v in list(incomplete.items())[:15]:
            print(f"    {k}: {'; '.join(v)}")
        if len(incomplete) > 15:
            print(f"    ...and {len(incomplete) - 15} more")
        if any("taxonomy" in x for v in incomplete.values() for x in v):
            print("  Allowed sectors:      " + " | ".join(sectors or []))
            print("  Allowed filing types: " + " | ".join(types or []))
        print("  Optional: a company's sector is remembered in data/company_lookup.csv.")


# ----------------------------------------------------------------------------
# 4. ANALYSIS  (builds the same records as the Owner portal -> database/*.json)
# ----------------------------------------------------------------------------
def fill_defaults(row, name, sectors, types):
    """Complete record metadata. Anything unknown gets a visible placeholder to edit later."""
    stem = Path(name).stem
    first = re.split(r"_+", stem)[0]
    h = hashlib.md5(name.encode()).hexdigest()[:4]
    g = lambda k: (row.get(k) or "").strip()
    m = {
        "ticker": g("ticker") or re.sub(r"[^A-Za-z0-9]+", "", first).upper()[:10] or "DOC",
        "company": g("company") or re.sub(r"[-\s]+", " ", first).strip() or stem,
        "sector": g("sector") if g("sector") and (not sectors or g("sector") in sectors) else "Unassigned",
        "filing_type": g("filing_type") if g("filing_type") and (not types or g("filing_type") in types) else "Unassigned",
        "period": g("period") or f"Unknown-{h}",
        "date": g("date"),
    }
    if g("source_url"):
        m["source_url"] = g("source_url")
    gaps = [k for k, ok in (("ticker", g("ticker")), ("company", g("company")),
                            ("sector", m["sector"] != "Unassigned"), ("type", m["filing_type"] != "Unassigned"),
                            ("period", g("period")), ("date", g("date"))) if not ok]
    return m, gaps


def cmd_analyze(force=False, keep_source=True):
    sys.path.insert(0, str(ROOT))
    from disclosure_lens.store import build_record, save_record

    meta = read_meta()
    sectors, types = load_taxonomy()
    files = sorted(RAW.glob("*.txt"))
    if not files:
        print(f"No .txt files in {RAW}. Run the 'convert' command first.")
        return
    print(f"Analyze: {len(files)} documents")
    saved = existing = 0
    gappy, failed = [], []
    for i, p in enumerate(files, 1):
        row = meta.get(p.name) or guess_meta(p.name)
        m, gaps = fill_defaults(row, p.name, sectors, types)
        try:
            record = build_record(p.read_text(encoding="utf-8", errors="ignore"), m)
            if not keep_source:
                record.pop("source_text", None)
            save_record(record, str(DB_DIR), overwrite=force)
            saved += 1
            if gaps:
                gappy.append((p.name, gaps))
        except FileExistsError:
            existing += 1
        except Exception as e:
            failed.append((p.name, f"{type(e).__name__}: {e}"))
        if i % 25 == 0:
            print(f"  processed {i}/{len(files)}")
    print(f"Analyze: {saved} saved to {DB_DIR.name}/, {existing} already there (use --force to replace), "
          f"{len(failed)} failed")
    if gappy:
        print(f"  {len(gappy)} of the saved records have placeholders. Fix them later in the Owner portal "
              "(look for sector 'Unassigned', period 'Unknown-xxxx', or blank date):")
        for name, gaps in gappy[:15]:
            print(f"    {name}: {', '.join(gaps)}")
        if len(gappy) > 15:
            print(f"    ...and {len(gappy) - 15} more")
    for name, err in failed:
        print(f"  FAILED:  {name} - {err}")
    if saved:
        print("Next: commit AND push, then wait for Streamlit to redeploy.")


# ----------------------------------------------------------------------------
# 5. STATUS
# ----------------------------------------------------------------------------
def cmd_status():
    incoming = [p for p in INCOMING.glob("*") if p.suffix.lower() in (".pdf", ".htm", ".html", ".txt")] \
        if INCOMING.exists() else []
    raw = list(RAW.glob("*.txt")) if RAW.exists() else []
    meta = read_meta()
    sectors, types = load_taxonomy()
    ready = sum(1 for r in meta.values() if not problems(r, sectors, types))
    recs = list(DB_DIR.glob("*.json")) if DB_DIR.exists() else []
    print(f"Files in data/incoming        : {len(incoming)}")
    print(f"Converted (data/raw)          : {len(raw)}")
    print(f"Rows in metadata.csv          : {len(meta)}  ({ready} complete)")
    print(f"Records on the site (database): {len(recs)}")
    if recs:
        import json
        c_sec, c_typ = Counter(), Counter()
        todo = 0
        for p in recs:
            try:
                r = json.loads(p.read_text())
                c_sec[r.get("sector", "?")] += 1
                c_typ[r.get("filing_type", "?")] += 1
                if (r.get("sector") == "Unassigned" or r.get("filing_type") == "Unassigned"
                        or str(r.get("period", "")).startswith("Unknown-") or not r.get("date")):
                    todo += 1
            except Exception:
                pass
        if todo:
            print(f"Records with placeholders to fix in the Owner portal: {todo}")
        print("By sector : " + ", ".join(f"{k}: {v}" for k, v in c_sec.most_common(8)))
        print("By type   : " + ", ".join(f"{k}: {v}" for k, v in c_typ.most_common(8)))


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Bulk tools for Disclosure Lens")
    ap.add_argument("command", choices=["convert", "meta", "analyze", "status", "all"])
    ap.add_argument("--force", action="store_true", help="redo files already done")
    ap.add_argument("--src", default=str(INCOMING), help="folder to convert from")
    ap.add_argument("--keep-tables", action="store_true", help="keep table text when converting HTML")
    ap.add_argument("--no-auto", action="store_true", help="meta: do not auto-fill from document text/SEC")
    ap.add_argument("--offline", action="store_true", help="meta: skip the SEC company/sector lookup")
    ap.add_argument("--no-source-text", action="store_true", help="do not store full document text in records")
    a = ap.parse_args()

    if a.command in ("convert", "all"):
        cmd_convert(Path(a.src), a.force, a.keep_tables)
    if a.command in ("meta", "all"):
        cmd_meta(auto=not a.no_auto, offline=a.offline)
    if a.command in ("analyze", "all"):
        cmd_analyze(a.force, keep_source=not a.no_source_text)
    if a.command == "status":
        cmd_status()


if __name__ == "__main__":
    main()
