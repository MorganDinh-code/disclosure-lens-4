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
    3. python3 batch_tools.py meta        (makes data/metadata.csv)
    4. Open data/metadata.csv in Excel/Numbers and fill the blank cells
       (ticker, company, sector, filing_type, period, date).
       sector and filing_type MUST match taxonomy.py spelling exactly.
    5. python3 batch_tools.py analyze     (saves records into database/)
    6. Commit AND push, then wait for Streamlit to redeploy.
       The Database and Stats pages show the new records automatically.

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
    --no-source-text   do not store the full document text inside each record
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
DB_DIR = ROOT / "database"          # where the website reads its records from

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
    """TICKER_FILINGTYPE_PERIOD[_DATE]  e.g. META_Earnings-Call_Q2-2026_2026-07-29.txt"""
    row = {c: "" for c in META_COLS}
    row["filename"] = filename
    parts = Path(filename).stem.split("_")
    if len(parts) >= 3:
        _, types = load_taxonomy()
        row["ticker"] = parts[0].upper()
        row["filing_type"] = _match(parts[1].replace("-", " "), types)
        if len(parts) >= 4 and re.match(r"^\d{4}-\d{2}-\d{2}$", parts[-1]):
            row["date"] = parts[-1]
            row["period"] = " ".join(parts[2:-1]).replace("-", " ")
        else:
            row["period"] = " ".join(parts[2:]).replace("-", " ")
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


def cmd_meta():
    meta = read_meta()
    new = 0
    for p in sorted(RAW.glob("*.txt")):
        if p.name not in meta:
            meta[p.name] = guess_meta(p.name)
            new += 1
    write_meta(meta)
    sectors, types = load_taxonomy()
    incomplete = {k: problems(r, sectors, types) for k, r in meta.items()}
    incomplete = {k: v for k, v in incomplete.items() if v}
    print(f"Metadata: {new} new rows added ({len(meta)} total) -> {META_FILE}")
    if incomplete:
        print(f"  {len(incomplete)} rows still need fixing before 'analyze' will accept them. "
              "Open the file and fill the blanks.")
    if sectors:
        print("  Allowed sectors:      " + " | ".join(sectors))
    if types:
        print("  Allowed filing types: " + " | ".join(types))


# ----------------------------------------------------------------------------
# 4. ANALYSIS  (builds the same records as the Owner portal -> database/*.json)
# ----------------------------------------------------------------------------
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
    skipped, failed = [], []
    for i, p in enumerate(files, 1):
        row = meta.get(p.name)
        if row is None:
            skipped.append((p.name, ["not in metadata.csv (run: python3 batch_tools.py meta)"]))
            continue
        bad = problems(row, sectors, types)
        if bad:
            skipped.append((p.name, bad))
            continue
        try:
            m = {c: row[c].strip() for c in REQUIRED}
            if (row.get("source_url") or "").strip():
                m["source_url"] = row["source_url"].strip()
            record = build_record(p.read_text(encoding="utf-8", errors="ignore"), m)
            if not keep_source:
                record.pop("source_text", None)
            save_record(record, str(DB_DIR), overwrite=force)
            saved += 1
        except FileExistsError:
            existing += 1
        except Exception as e:
            failed.append((p.name, f"{type(e).__name__}: {e}"))
        if i % 25 == 0:
            print(f"  processed {i}/{len(files)}")
    print(f"Analyze: {saved} saved to {DB_DIR.name}/, {existing} already there (use --force to replace), "
          f"{len(skipped)} skipped, {len(failed)} failed")
    for name, why in skipped:
        print(f"  SKIPPED: {name} - {'; '.join(why)}")
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
        for p in recs:
            try:
                r = json.loads(p.read_text())
                c_sec[r.get("sector", "?")] += 1
                c_typ[r.get("filing_type", "?")] += 1
            except Exception:
                pass
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
    ap.add_argument("--no-source-text", action="store_true", help="do not store full document text in records")
    a = ap.parse_args()

    if a.command in ("convert", "all"):
        cmd_convert(Path(a.src), a.force, a.keep_tables)
    if a.command in ("meta", "all"):
        cmd_meta()
    if a.command in ("analyze", "all"):
        cmd_analyze(a.force, keep_source=not a.no_source_text)
    if a.command == "status":
        cmd_status()


if __name__ == "__main__":
    main()
