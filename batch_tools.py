"""
batch_tools.py  --  bulk document tools for Disclosure Lens
=============================================================

Put this file in your project ROOT (the same folder that contains the
`disclosure_lens` folder, `app.py`, and `data/`). Then run commands from the
VS Code terminal.

ONE-TIME SETUP
    pip install pypdf

THE WORKFLOW
    1. Drop PDFs / .htm / .html / .txt files into   data/incoming/
    2. python batch_tools.py all
    3. Open data/database.csv   (one row of scores per document)

    Naming files  COMPANY_FILINGTYPE_DATE.pdf  fills the metadata for you:
        META_EarningsCall_2026-07-29.pdf
        AAPL_10-K_2025-10-31.htm
    Anything else is fine too: you just fill in data/metadata.csv by hand.

COMMANDS
    python batch_tools.py convert   PDFs/HTML -> clean .txt in data/raw/
    python batch_tools.py meta      create/update data/metadata.csv
    python batch_tools.py analyze   run Disclosure Lens on data/raw/*.txt
    python batch_tools.py status    show counts and what is missing
    python batch_tools.py all       convert + meta + analyze

OPTIONS (all optional)
    --force   redo files that were already converted / analyzed
    --src     folder to convert from   (default data/incoming)
    --keep-tables   keep table text when converting HTML (default: dropped,
                    because Disclosure Lens studies narrative text, not tables)
"""

import argparse
import csv
import re
import shutil
import sys
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
DB_FILE = ROOT / "data" / "database.csv"

META_COLS = ["filename", "company", "filing_type", "sector", "date"]
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
# 3. METADATA  (company / filing type / sector / date for the public database)
# ----------------------------------------------------------------------------
def guess_meta(filename: str) -> dict:
    """Reads COMPANY_FILINGTYPE_DATE.txt (e.g. META_EarningsCall_2026-07-29.txt)."""
    parts = Path(filename).stem.split("_")
    row = {"filename": filename, "company": "", "filing_type": "", "sector": "", "date": ""}
    if len(parts) >= 3 and re.match(r"^\d{4}(-\d{2}){0,2}$", parts[-1]):
        row["company"], row["date"] = parts[0], parts[-1]
        row["filing_type"] = " ".join(parts[1:-1])
    return row


def read_meta() -> dict:
    if not META_FILE.exists():
        return {}
    with open(META_FILE, newline="", encoding="utf-8") as f:
        return {r["filename"]: r for r in csv.DictReader(f)}


def write_meta(rows: dict):
    META_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(META_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=META_COLS, extrasaction="ignore")
        w.writeheader()
        for k in sorted(rows):
            w.writerow(rows[k])


def cmd_meta():
    meta = read_meta()
    new = 0
    for p in sorted(RAW.glob("*.txt")):
        if p.name not in meta:
            meta[p.name] = guess_meta(p.name)
            new += 1
    write_meta(meta)
    blank = sum(1 for r in meta.values() if not r.get("sector"))
    print(f"Metadata: {new} new rows added ({len(meta)} total) -> {META_FILE}")
    if blank:
        print(f"  {blank} rows have no sector yet. Open the file in Excel/Numbers and fill it in.")


# ----------------------------------------------------------------------------
# 4. ANALYSIS  (uses your existing Disclosure Lens pipeline)
# ----------------------------------------------------------------------------
def flatten(d, prefix=""):
    """Nested dict -> flat columns. Keeps numbers/text/bool only."""
    out = {}
    if not isinstance(d, dict):
        return out
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(flatten(v, key + "_"))
        elif isinstance(v, bool) or v is None or isinstance(v, (int, float, str)):
            out[key] = v
        elif hasattr(v, "item"):                 # numpy scalar
            try:
                out[key] = v.item()
            except Exception:
                pass
    return out


def analyze_text(text: str) -> dict:
    """Runs the same steps as pages/analyze.py, minus Streamlit."""
    sys.path.insert(0, str(ROOT))
    from disclosure_lens import lexicon
    from disclosure_lens.checks import check_document, strip_boilerplate
    from disclosure_lens.metrics import annotate, summarize
    from disclosure_lens.preprocess import parse_document

    text, n_removed = strip_boilerplate(text)
    warnings = check_document(text)
    records = annotate(parse_document(text))
    row = flatten(summarize(records))
    row.update(flatten(lexicon.density_profile(text), "lex_"))
    row["n_paragraphs"] = len(records)
    row["n_words"] = len(text.split())
    row["boilerplate_paragraphs_removed"] = n_removed
    row["warnings"] = " | ".join(str(w) for w in warnings)
    return row


def read_db() -> dict:
    if not DB_FILE.exists():
        return {}
    with open(DB_FILE, newline="", encoding="utf-8") as f:
        return {r["filename"]: r for r in csv.DictReader(f)}


def write_db(rows: dict):
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    cols = list(META_COLS)
    for r in rows.values():
        for c in r:
            if c not in cols:
                cols.append(c)
    with open(DB_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, restval="")
        w.writeheader()
        for k in sorted(rows):
            w.writerow(rows[k])


def cmd_analyze(force=False):
    meta, db = read_meta(), read_db()
    files = sorted(RAW.glob("*.txt"))
    if not files:
        print(f"No .txt files in {RAW}. Run the 'convert' command first.")
        return
    todo = [p for p in files if force or p.name not in db]
    print(f"Analyze: {len(files)} documents, {len(todo)} to do")
    ok, failed = 0, []
    for i, p in enumerate(todo, 1):
        try:
            row = analyze_text(p.read_text(encoding="utf-8", errors="ignore"))
            db[p.name] = {"filename": p.name, **row}
            ok += 1
        except Exception as e:
            failed.append((p.name, f"{type(e).__name__}: {e}"))
        if i % 25 == 0:
            print(f"  analyzed {i}/{len(todo)}")
    # keep company/type/sector/date in the database in sync with metadata.csv
    for name, row in db.items():
        m = meta.get(name) or guess_meta(name)
        for c in META_COLS[1:]:
            row[c] = m.get(c, "")
    write_db(db)
    print(f"Analyze: {ok} done, {len(failed)} failed -> {DB_FILE}")
    for name, err in failed:
        print(f"  FAILED: {name} - {err}")


# ----------------------------------------------------------------------------
# 5. STATUS
# ----------------------------------------------------------------------------
def cmd_status():
    incoming = [p for p in INCOMING.glob("*") if p.suffix.lower() in (".pdf", ".htm", ".html", ".txt")] \
        if INCOMING.exists() else []
    raw = list(RAW.glob("*.txt")) if RAW.exists() else []
    meta, db = read_meta(), read_db()
    print(f"Files in data/incoming : {len(incoming)}")
    print(f"Converted (data/raw)   : {len(raw)}")
    print(f"In metadata.csv        : {len(meta)}")
    print(f"Analyzed (database.csv): {len(db)}")
    not_done = [p.name for p in raw if p.name not in db]
    if not_done:
        print(f"Converted but not analyzed: {len(not_done)}  (run: python batch_tools.py analyze)")
    if db:
        for col, label in (("sector", "Sector"), ("filing_type", "Filing type"), ("company", "Company")):
            c = Counter((r.get(col) or "(blank)") for r in db.values())
            top = ", ".join(f"{k}: {v}" for k, v in c.most_common(8))
            print(f"{label:<12}: {top}")


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Bulk tools for Disclosure Lens")
    ap.add_argument("command", choices=["convert", "meta", "analyze", "status", "all"])
    ap.add_argument("--force", action="store_true", help="redo files already done")
    ap.add_argument("--src", default=str(INCOMING), help="folder to convert from")
    ap.add_argument("--keep-tables", action="store_true", help="keep table text when converting HTML")
    a = ap.parse_args()

    if a.command in ("convert", "all"):
        cmd_convert(Path(a.src), a.force, a.keep_tables)
    if a.command in ("meta", "all"):
        cmd_meta()
    if a.command in ("analyze", "all"):
        cmd_analyze(a.force)
    if a.command == "status":
        cmd_status()


if __name__ == "__main__":
    main()
