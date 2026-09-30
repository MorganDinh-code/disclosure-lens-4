"""Step 1: turn raw text into paragraphs and sentences."""
import re

# Abbreviations whose period must NOT end a sentence.
ABBREVIATIONS = ["Inc.", "Corp.", "Co.", "Ltd.", "U.S.", "approx.", "vs.", "No.", "bn.", "mn.", "Mr.", "Ms.", "Dr."]
_PLACEHOLDER = "<DOT>"


def split_paragraphs(text: str) -> list[str]:
    """Paragraphs are separated by blank lines."""
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def split_sentences(paragraph: str) -> list[str]:
    protected = paragraph
    for abbr in ABBREVIATIONS:
        protected = protected.replace(abbr, abbr.replace(".", _PLACEHOLDER))
    # Split after . ! ? when followed by whitespace and a capital letter, quote or $
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\"$])", protected)
    return [p.replace(_PLACEHOLDER, ".").strip() for p in parts if p.strip()]


def parse_document(text: str) -> list[dict]:
    """Return one record per sentence with its position information.

    Position = sentence number / total sentences (1-indexed), as in your spec.
    """
    records = []
    paragraphs = split_paragraphs(text)
    for p_idx, para in enumerate(paragraphs, start=1):
        sentences = split_sentences(para)
        for s_idx, sent in enumerate(sentences, start=1):
            records.append({
                "text": sent,
                "paragraph": p_idx,
                "sent_in_para": s_idx,
                "sents_in_para": len(sentences),
            })
    total = len(records)
    for i, r in enumerate(records, start=1):
        r["index"] = i
        r["pos_doc"] = i / total
        r["pos_para"] = r["sent_in_para"] / r["sents_in_para"]
    return records
