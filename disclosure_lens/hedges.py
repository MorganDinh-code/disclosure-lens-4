"""Module 2: hedge detection. Tiers use the Loughran-McDonald lists when the dictionary file is present."""
import re
from collections import Counter

from . import lexicon

_LOW0 = ["may", "might", "could", "potentially", "possibly", "uncertain", "cannot guarantee", "subject to",
         "depending on"]
_MOD0 = ["expects", "expect", "anticipates", "anticipate", "believes", "likely", "approximately", "generally",
         "typically"]
_HIGH0 = ["will", "delivered", "achieved", "has", "is"]

# Low = starter list + LM Uncertainty + LM Weak modal.  High = starter list + LM Strong modal.
# Moderate (expectation verbs) is this project's own tier; anything in Low or High is removed from it.
LOW = sorted(set(_LOW0) | lexicon.words("uncertainty") | lexicon.words("weak_modal"))
HIGH = sorted(set(_HIGH0) | lexicon.words("strong_modal"))
MODERATE = sorted(set(_MOD0) - set(LOW) - set(HIGH))
_TIERS = {t: ({w for w in ws if " " not in w}, [w for w in ws if " " in w])
          for t, ws in (("low", LOW), ("moderate", MODERATE), ("high", HIGH))}


def words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z']+", text)


def hedge_counts(text: str) -> dict:
    t = re.sub(r"\bmay\s+\d", "", text.lower())  # "May 5" is a date, not a hedge
    c = Counter(lexicon.tokens(t))
    out = {}
    for tier, (single, phrases) in _TIERS.items():
        out[tier] = sum(c[w] for w in single) + sum(len(re.findall(r"\b" + re.escape(p) + r"\b", t)) for p in phrases)
    return out


def hedge_density(text: str) -> float:
    """(low + moderate terms) / total words. High-certainty words are not hedges."""
    n = len(words(text))
    if n == 0:
        return 0.0
    c = hedge_counts(text)
    return (c["low"] + c["moderate"]) / n


def modal_intensity(text: str):
    """Average certainty: 1 = very uncertain, 3 = very certain. None if no modal words."""
    c = hedge_counts(text)
    total = c["low"] + c["moderate"] + c["high"]
    return None if total == 0 else (c["low"] + 2 * c["moderate"] + 3 * c["high"]) / total
