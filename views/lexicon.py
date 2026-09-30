import streamlit as st

from disclosure_lens import classify, hedges, lexicon, tone

st.header("Lexicon and frameworks")
st.markdown("Every score comes from a published word list or a stated rule, so results can be checked and reproduced.")

st.subheader("Framework")
st.markdown("""
**Loughran & McDonald (2011)**, *When Is a Liability Not a Liability? Textual Analysis, Dictionaries, and 10-Ks*,
Journal of Finance, 66(1), 35-65. General-purpose dictionaries misread finance language ("liability", "tax",
"cost" are not negative sentiment in a 10-K), so they built finance-specific lists: **negative, positive,
uncertainty, litigious, strong modal, weak modal and constraining** words. The Master Dictionary is maintained by
the University of Notre Dame's Software Repository for Accounting and Finance (SRAF, sraf.nd.edu) and used here
with attribution. Disclosure Lens is an independent project and is not affiliated with or endorsed by the authors.
""")

d = lexicon.load()
if d:
    st.success(f"Full Master Dictionary loaded: **{d['file']}** ({d['n_words']:,} words).")
    st.table({"Category": [lexicon.LABELS[c] for c in lexicon.CATEGORIES],
              "Words": [f"{len(d['cats'][c]):,}" for c in lexicon.CATEGORIES]})
else:
    st.warning("The full Master Dictionary file is not installed on this site, so a small starter lexicon is in use.")


def chips(ws, limit=None):
    ws = sorted(ws)
    shown = ws[:limit] if limit else ws
    return " ".join(f"`{w}`" for w in shown) + (f" … ({len(ws):,} total)" if limit and len(ws) > limit else "")


st.subheader("How words map to the certainty tiers")
lim = 14 if d else None
st.markdown(f"""
| Tier | Meaning | Score | Source | Words |
|---|---|---|---|---|
| **Low certainty** | Doubt or possibility | 1 | LM *uncertainty* + *weak modal*, plus a few phrases (\"subject to\") | {chips(hedges.LOW, lim)} |
| **Moderate** | Expectation or estimate | 2 | Project-defined (no LM equivalent) | {chips(hedges.MODERATE, lim)} |
| **High certainty** | Firm statement | 3 | LM *strong modal*, plus a few verbs | {chips(hedges.HIGH, lim)} |
""")
st.markdown("Hedge density counts **low and moderate** terms per word. Modal intensity averages the 1-2-3 scores. "
            "A word in more than one tier is counted once, in the lower-certainty tier.")

st.subheader("How tone is scored")
st.markdown("Tone = (positive − negative words) ÷ total words, scaled to about −1 to +1. "
            + ("Positive and negative come from the full dictionary. A positive word with *no, not, none, neither, "
               "never* or *nobody* in the three words before it counts as negative, following the usual convention "
               "for this dictionary." if d else "Until the dictionary is installed, a short starter list is used."))
if not d:
    c1, c2 = st.columns(2)
    c1.markdown("**Positive (starter)**  \n" + chips(tone.POSITIVE))
    c2.markdown("**Negative (starter)**  \n" + chips(tone.NEGATIVE))

st.subheader("Financial direction and materiality")
st.markdown("These are rules written for this project, not part of the dictionary.")
c1, c2, c3 = st.columns(3)
c1.markdown("**Negative-fact terms**  \n" + chips(classify.NEGATIVE_FACT))
c2.markdown("**Positive-fact terms**  \n" + chips(w.strip() for w in classify.POSITIVE_FACT))
c3.markdown("**Severe terms (make a negative material)**  \n" + chips(classify.SEVERE))

if d:
    st.subheader("Explore the dictionary")
    q = st.text_input("Look up a word", placeholder="e.g. impairment")
    if q.strip():
        r = lexicon.lookup(q)
        st.write({k: f"added {v}" for k, v in r.items()} if r else "Not in any sentiment category.")
    for c in lexicon.CATEGORIES:
        with st.expander(f"{lexicon.LABELS[c]} ({len(d['cats'][c]):,} words)"):
            st.markdown(chips(d["cats"][c]))

st.subheader("Known limits")
st.markdown("- Words are counted without context; only positive words get negation handling.\n"
            "- Dictionary categories were built from annual-report language and may fit press releases and calls less well.\n"
            "- Financial direction is rule-based and not yet validated against hand-labeled sentences.")
