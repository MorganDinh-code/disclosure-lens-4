"""Module 3: linguistic tone. Uses the full Loughran-McDonald Positive/Negative lists (with negation handling)
when the dictionary file is present; otherwise a small starter list."""
from . import lexicon
from .hedges import words

STARTER_POS = {"strong", "record", "excellent", "robust", "pleased", "excited", "confident", "improved", "healthy",
               "opportunities", "momentum", "resilient", "positive", "growth", "delivered", "meaningfully", "achieved"}
STARTER_NEG = {"weak", "declined", "decline", "impairment", "loss", "losses", "deteriorated", "challenging",
               "difficult", "decreased", "adverse", "risk", "uncertain", "litigation", "restructuring", "charge"}
POSITIVE = lexicon.words("positive") or STARTER_POS
NEGATIVE = lexicon.words("negative") or STARTER_NEG
SCALE = 10  # scales so typical sentences land between -1 and +1


def tone_score(text: str) -> float:
    """Tone in [-1, 1] = (positive - negative words) / total words, scaled."""
    n = len(words(text))
    if not n:
        return 0.0
    if lexicon.available():
        p, m = lexicon.tone_counts(lexicon.tokens(text), POSITIVE, NEGATIVE)
    else:
        ws = [w.lower() for w in words(text)]
        p, m = sum(w in POSITIVE for w in ws), sum(w in NEGATIVE for w in ws)
    return max(-1.0, min(1.0, SCALE * (p - m) / n))
