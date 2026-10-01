"""Financial direction: does the FACT help or hurt the company? (separate from tone)

A change verb (up/down) is paired with the nearest metric (good: revenue, margin... / bad: expenses, losses...):
'revenue increased' and 'expenses declined' are both positive; 'expenses increased' is negative.
If no pair is found, simple keyword rules are used. Rule-based and not yet validated against hand labels.
"""
import re

UP = re.compile(r"\b(increas\w*|grew|grow\w*|rose|rise|rising|up|higher|expand\w*|improv\w*|gain\w*|surg\w*|climb\w*|accelerat\w*|exceed\w*)\b")
DOWN = re.compile(r"\b(decreas\w*|declin\w*|fell|fall\w*|down|lower|drop\w*|contract\w*|reduc\w*|shrank|weaken\w*|slow\w*|dip\w*)\b")
GOOD = re.compile(r"\b(revenues?|sales|income|profit\w*|earnings|margins?|cash flow|eps|bookings|backlog|subscribers?|memberships?|users|customers|orders|growth|demand|dividends?|buybacks?|repurchases?)\b")
BAD = re.compile(r"\b(expenses?|costs?|losses|loss|debt|liabilit\w*|impairments?|charges?|churn|delinquenc\w*|headwinds?|dilution)\b")

NEGATIVE_FACT = ["declined", "decreased", "impairment", "loss", "lowered", "lower guidance", "restructuring",
                 "litigation", "restatement", "going concern", "covenant", "layoffs", "weak", "deteriorat"]
POSITIVE_FACT = ["increased", "grew", "record", "improved", "exceeded"]
SEVERE = ["impairment", "going concern", "litigation", "restatement", "covenant", "restructuring", "layoffs",
          "lowered", "lower guidance"]


def _pair_score(t: str) -> int:
    metrics = [(m.start(), 1) for m in GOOD.finditer(t)] + [(m.start(), -1) for m in BAD.finditer(t)]
    if not metrics:
        return 0
    score = 0
    for rx, sign in ((UP, 1), (DOWN, -1)):
        for m in rx.finditer(t):
            pos, polarity = min(metrics, key=lambda x: abs(x[0] - m.start()))
            if abs(pos - m.start()) <= 60:
                score += sign * polarity
    return score


def direction(text: str) -> int:
    """+1 positive fact, -1 negative fact, 0 neutral."""
    t = text.lower()
    s = _pair_score(t)
    if s:
        return 1 if s > 0 else -1
    if any(k in t for k in NEGATIVE_FACT):
        return -1
    if any(k in t for k in POSITIVE_FACT):
        return 1
    return 0


def is_material_negative(text: str) -> bool:
    """Material = negative AND (contains a quantified figure OR a severe term)."""
    if direction(text) != -1:
        return False
    t = text.lower()
    return bool(re.search(r"\d", t)) or any(k in t for k in SEVERE)
