"""Compute the headline metrics from the sentence records."""
from statistics import mean

from . import lexicon
from .classify import direction, is_material_negative
from .hedges import hedge_counts, hedge_density, modal_intensity, words
from .tone import tone_score


def annotate(records: list[dict]) -> list[dict]:
    for r in records:
        r["direction"] = direction(r["text"])
        r["material_neg"] = is_material_negative(r["text"])
        r["hedge_density"] = hedge_density(r["text"])
        r["modal"] = modal_intensity(r["text"])
        r["tone"] = tone_score(r["text"])
        r["hits"] = lexicon.find_hits(r["text"])
        r["tone_gap"] = r["tone"] - r["direction"]  # positive gap on a negative fact = spin
    return records


def _window_density(records, i, k=1):
    """Hedge density over sentence i and its +/- k neighbours."""
    lo, hi = max(0, i - k), min(len(records), i + k + 1)
    text = " ".join(r["text"] for r in records[lo:hi])
    n = len(words(text))
    c = hedge_counts(text)
    return (c["low"] + c["moderate"]) / n if n else 0.0


def summarize(records: list[dict]) -> dict:
    neg = [r for r in records if r["material_neg"]]
    pos = [r for r in records if r["direction"] == 1]
    out = {"n_sentences": len(records), "n_material_neg": len(neg), "n_positive": len(pos)}

    # --- Module 1: Order ---
    if neg:
        out["mean_pos_negative"] = mean(r["pos_doc"] for r in neg)
    if pos:
        out["mean_pos_positive"] = mean(r["pos_doc"] for r in pos)
    if neg and pos:
        out["placement_asymmetry"] = out["mean_pos_negative"] - out["mean_pos_positive"]
    if neg:
        first = neg[0]
        headline_sents = sum(1 for r in records if r["paragraph"] == 1)
        out["distance_from_headline"] = first["index"] - headline_sents - 1  # sentences between
        out["first_negative_pos"] = first["pos_doc"]

    # --- Module 2: Hedging (+/-1 sentence window) ---
    idx = {id(r): i for i, r in enumerate(records)}
    neg_h = mean(_window_density(records, idx[id(r)]) for r in neg) if neg else None
    pos_h = mean(_window_density(records, idx[id(r)]) for r in pos) if pos else None
    out["hedge_near_negative"], out["hedge_near_positive"] = neg_h, pos_h
    out["hedging_asymmetry"] = neg_h / pos_h if (neg_h is not None and pos_h) else None

    # --- Module 3: Tone vs. financial outcome ---
    negatives_all = [r for r in records if r["direction"] == -1]
    if negatives_all:
        out["framing_ratio"] = mean(r["tone"] > 0 for r in negatives_all)
        out["mean_tone_gap_on_negatives"] = mean(r["tone_gap"] for r in negatives_all)
    return out
