"""Input checks: is this the kind of document Disclosure Lens is built for?"""
import re

BOILERPLATE = re.compile(r"forward-looking statements?|safe harbor|private securities litigation reform act|certain statements in this press release|use of non-gaap|reconciliations?\b|adjust the related gaap", re.I)


def split_blocks(text: str) -> list[str]:
    return [p for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]


def strip_boilerplate(text: str):
    """Remove legal 'forward-looking statements' paragraphs. Returns (clean_text, n_removed)."""
    blocks = split_blocks(text)
    keep = [b for b in blocks if not BOILERPLATE.search(b)]
    return "\n\n".join(keep), len(blocks) - len(keep)


def check_document(text: str) -> list[str]:
    """Return plain-English warnings about the input (empty list = looks fine)."""
    out = []
    n_words = len(re.findall(r"[A-Za-z']+", text))
    lines = [l for l in text.splitlines() if l.strip()]
    table_lines = sum(1 for l in lines if sum(c.isdigit() for c in l) / max(1, len(l.replace(" ", ""))) > 0.4)
    if n_words < 100:
        out.append("This text is very short (under 100 words). Position and hedging measures need a full "
                   "narrative such as a whole earnings press release, so results may not be meaningful.")
    if lines and table_lines / len(lines) > 0.2:
        out.append("A lot of this text looks like tables of numbers. Disclosure Lens analyzes the written "
                   "narrative, so remove financial statement tables and keep the prose.")
    if len(split_blocks(text)) < 3:
        out.append("Paragraphs were not detected. Put a blank line between paragraphs so position within "
                   "the document can be measured properly.")
    if n_words > 6000:
        out.append("This is very long (over 6,000 words), which suggests a full 10-K or similar filing. "
                   "The tool works best on short documents such as press releases. Consider analyzing one "
                   "section (for example the MD&A) at a time.")
    return out
