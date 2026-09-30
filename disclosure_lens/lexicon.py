"""Loughran-McDonald Master Dictionary loader.

The dictionary file is NOT bundled: download it from Notre Dame's SRAF site (sraf.nd.edu), accept their terms,
and put the CSV in the data/ folder (any file name containing 'MasterDictionary').
"""
import csv
import glob
import re
from functools import lru_cache

CATEGORIES = ["negative", "positive", "uncertainty", "litigious", "strong_modal", "weak_modal", "constraining"]
LABELS = {"negative": "Negative", "positive": "Positive", "uncertainty": "Uncertainty", "litigious": "Litigious",
          "strong_modal": "Strong modal", "weak_modal": "Weak modal", "constraining": "Constraining"}
NEGATORS = {"no", "not", "none", "neither", "never", "nobody"}


@lru_cache(maxsize=4)
def load(folder: str = "data"):
    files = sorted(glob.glob(f"{folder}/*MasterDictionary*.csv"))
    if not files:
        return None
    cats = {c: {} for c in CATEGORIES}
    n = 0
    with open(files[-1], encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            row = {re.sub(r"[^a-z]+", "_", k.strip().lower()): v for k, v in row.items() if k}
            w = (row.get("word") or "").strip().lower()
            if not w:
                continue
            n += 1
            for c in CATEGORIES:
                try:
                    y = int(float(row.get(c) or 0))
                except ValueError:
                    y = 0
                if y > 0:
                    cats[c][w] = y
    return {"file": files[-1].split("/")[-1], "cats": cats, "n_words": n}


def available(folder: str = "data") -> bool:
    return load(folder) is not None


def words(cat: str, folder: str = "data") -> set:
    d = load(folder)
    return set(d["cats"][cat]) if d else set()


def lookup(word: str, folder: str = "data") -> dict:
    d = load(folder)
    w = word.strip().lower()
    return {LABELS[c]: d["cats"][c][w] for c in CATEGORIES if d and w in d["cats"][c]}


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z']+", re.sub(r"'s\b", "", text.lower()))


def tone_counts(toks: list[str], pos: set, neg: set):
    """Positive/negative counts. A positive word with a negator in the 3 words before it counts as negative
    (the convention used with this dictionary)."""
    p = n = 0
    for i, w in enumerate(toks):
        if w in pos:
            if NEGATORS & set(toks[max(0, i - 3):i]):
                n += 1
            else:
                p += 1
        elif w in neg:
            n += 1
    return p, n


def find_hits(text: str, folder: str = "data") -> list:
    """Every dictionary word in the text as [start, end, [categories]] (empty list if no dictionary)."""
    d = load(folder)
    if not d:
        return []
    out = []
    for m in re.finditer(r"[A-Za-z']+", text):
        w = re.sub(r"'s$", "", m.group().lower()).strip("'")
        cats = [c for c in CATEGORIES if w in d["cats"][c]]
        if cats:
            out.append([m.start(), m.end(), cats])
    return out


def density_profile(text: str, folder: str = "data"):
    """Category counts and rates per 1,000 words, built from the same hits that are highlighted."""
    d = load(folder)
    if not d:
        return None
    n = max(1, len(re.findall(r"[A-Za-z']+", text)))
    counts = {c: 0 for c in CATEGORIES}
    for _, _, cats in find_hits(text, folder):
        for c in cats:
            counts[c] += 1
    return {"words": n, "per_1000": {LABELS[c]: round(1000 * counts[c] / n, 1) for c in CATEGORIES},
            "counts": {LABELS[c]: counts[c] for c in CATEGORIES}}
