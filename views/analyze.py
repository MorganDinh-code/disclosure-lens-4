import html

import streamlit as st

import ui
from disclosure_lens import lexicon
from disclosure_lens.checks import check_document, strip_boilerplate
from disclosure_lens.metrics import annotate, summarize
from disclosure_lens.preprocess import parse_document

SAMPLE = "data/sample_release.txt"
ui.hero()
st.header("Analyze a document")
left, right = st.columns([3, 2])
with left:
    with st.form("input_form"):
        uploaded = st.file_uploader("Upload a .txt file", type=["txt"],
                                    help="Plain text only. PDFs are not supported yet: copy the text out first.")
        pasted = st.text_area("...or paste text here", height=180,
                              placeholder="Paste the press release text here. Put a blank line between paragraphs.")
        go = st.form_submit_button("Analyze", type="primary")
with right:
    st.markdown('<div class="card"><b>Use the written text</b><br>Earnings press releases, call transcripts, '
                'MD&amp;A sections and shareholder letters. Not tables of numbers.</div>', unsafe_allow_html=True)
    if st.button("Use sample press release"):
        st.session_state["text"] = open(SAMPLE, encoding="utf-8").read()
if go:
    if uploaded is not None:
        st.session_state["text"] = uploaded.read().decode("utf-8", errors="ignore")
    elif pasted.strip():
        st.session_state["text"] = pasted
    else:
        st.warning("Upload a file or paste some text first.")
text = st.session_state.get("text")

if not text:
    st.subheader("What to analyze")
    st.markdown("Disclosure Lens studies the **written narrative** companies place around their numbers. "
                "It does not read financial statements.")
    ui.guidelines()
    st.info("Ready? Upload a file or paste text and click **Analyze**, or click **Use sample press release**.")
    st.stop()

cleaned, n_removed = strip_boilerplate(text)
if n_removed:
    with st.container():
        drop = st.checkbox(f"Remove forward-looking statements disclaimer ({n_removed} paragraph"
                           f"{'s' if n_removed > 1 else ''} found)", value=True)
    if drop:
        text = cleaned
for w in check_document(text):
    st.warning(w)
with st.expander("What kind of document is this tool for?"):
    ui.guidelines()

records = annotate(parse_document(text))
s = summarize(records)
if s["n_material_neg"] == 0:
    st.info("No material negative sentences were detected, so placement and hedging comparisons are limited. "
            "This can mean the document is genuinely positive, or that the rule-based classifier missed something "
            "(see Limitations on the Methodology page).")

st.header("Disclosure Profile")
ui.profile(s)

ui.lexicon_profile(lexicon.density_profile(text))
ui.lexicon_words([{"index": r["index"], "text": r["text"], "hits": r["hits"]} for r in records])

st.header("Where the information sits")
ui.strip([r["direction"] for r in records], [r["material_neg"] for r in records])

st.header("Disclosure Map")
st.caption("Left strip = what the FACT says. Right strip = how the WORDING sounds. "
           "When they disagree on a negative fact, the row is flagged.")
ui.disclosure_map(records)
ui.download_button(records)
st.divider()
st.caption("These are patterns to examine, not verdicts. Late placement or heavy hedging can have innocent "
           "explanations. The tone word list is a placeholder pending the Loughran-McDonald dictionary.")
