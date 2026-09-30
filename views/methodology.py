import streamlit as st

import ui

st.header("Methodology")
st.markdown("Every sentence receives **two independent labels**: a *financial direction* (does the fact help or "
            "hurt the company?) and a *linguistic tone* (does the wording sound positive or negative?). "
            "Every metric below is built from those labels. Results describe patterns, not intent.")

FEATURES = [
 ("Information order", "Sentence position & placement asymmetry",
  "Where a company puts information is a choice. Readers give more weight to what comes first.",
  "Position = sentence number ÷ total sentences. Placement asymmetry = average position of material negatives minus average position of positives.",
  "Whether bad news systematically arrives after good news. Positive values mean it does.",
  "Positives average the 39th percentile and material negatives the 96th, giving an asymmetry of +57 points."),
 ("Information order", "Distance from headline",
  "The further the first bad news sits from the headline, the more a skimming reader passes before meeting it.",
  "Number of sentences between the headline paragraph and the first material negative.",
  "How much favorable content precedes the first material risk.",
  "The first material negative is the 11th sentence; the headline is 1 sentence, so the distance is 9."),
 ("Hedging", "Hedge density",
  "Words like may, could and subject to signal how firmly a claim is being made.",
  "Hedge terms ÷ total words, using a published three-tier lexicon (low, moderate, high certainty).",
  "How qualified a passage is, independent of what it says.",
  "'The company may potentially record...' contains 2 low-certainty terms in 15 words, a density of 13%."),
 ("Hedging", "Hedging asymmetry",
  "Uncertain language is normal. Uncertain language only around bad news is a pattern.",
  "Hedge density within one sentence either side of each material negative ÷ the same measure around positives.",
  "Whether bad news is wrapped in more qualification than good news. Above 1× means it is.",
  "11% near negatives against 0% near positives is undefined: no hedging at all near the good news."),
 ("Tone vs. facts", "Tone-outcome gap & framing ratio",
  "A firm can report a bad number in cheerful words. Separating fact from wording exposes that.",
  "Tone (Loughran-McDonald-style word counts) minus financial direction, per sentence. Framing ratio = share of negative facts with positive tone.",
  "Whether unfavorable facts are surrounded by favorable language.",
  "'Demand declined 18%, but we remain excited about our strong foundation' is a red fact in green wording."),
 ("Materiality", "Material negative",
  "Not every negative sentence matters. The Order metrics should track the ones that do.",
  "A negative sentence is material if it contains a figure or a severe term (impairment, litigation, restatement, guidance cut...).",
  "Which bad news counts for the placement and hedging measures.",
  "'A $240 million impairment charge' is material; 'results were softer' is not."),
]

for module in dict.fromkeys(f[0] for f in FEATURES):
    st.subheader(module)
    for _, name, why, how, tells, ex in [f for f in FEATURES if f[0] == module]:
        st.markdown(f"**{name}**")
        cols = st.columns(3)
        for col, label, body in zip(cols, ["Why it is included", "How it is measured", "What it tells you"],
                                    [why, how, tells]):
            col.markdown(f'<div class="card"><b>{label}</b><br>{body}</div>', unsafe_allow_html=True)
        st.caption(f"Example: {ex}")

st.subheader("The Disclosure Map")
st.markdown("The map combines all of the above on one page: one row per sentence in document order, a left strip "
            "for the fact, a right strip for the wording, and a hedge percentage. Rows where the two strips "
            "disagree on a negative fact are flagged as possible spin.")
st.subheader("Limitations")
st.markdown("- Financial direction is rule-based and not yet validated against hand-labeled sentences.\n"
            "- Some sections sit late by convention, so results are best compared across peers and quarters.\n"
            "- Flags are prompts for a closer reading, not conclusions about a company's intent.")

st.subheader("Which documents to use")
ui.guidelines()
