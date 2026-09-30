"""Financial direction: does the FACT help or hurt the company? (separate from tone)

Rule-based starter. Known limitation you should validate against hand labels:
"Operating expenses declined" is GOOD news, but the word "declined" looks negative.
Fixing cases like this is exactly what your 200-sentence hand-labeled sample is for.
"""
import re

NEGATIVE_FACT = ["declined", "decreased", "impairment", "loss", "lowered", "lower guidance",
                 "restructuring", "litigation", "restatement", "going concern", "covenant",
                 "layoffs", "weak", "deteriorat"]
POSITIVE_FACT = ["increased", "grew", "record", "improved", "exceeded", "up "]
SEVERE = ["impairment", "going concern", "litigation", "restatement", "covenant",
          "restructuring", "layoffs", "lowered", "lower guidance"]


def direction(text: str) -> int:
    """+1 positive fact, -1 negative fact, 0 neutral. Negative wins ties (conservative)."""
    t = text.lower()
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
    has_number = bool(re.search(r"\d", t))
    return has_number or any(k in t for k in SEVERE)
