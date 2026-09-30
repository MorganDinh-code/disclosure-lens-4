from collections import Counter

import pandas as pd
import streamlit as st

import ui
from disclosure_lens.store import load_records
from taxonomy import FILING_TYPES, SECTORS

st.header("Database")
st.caption("Browse analyzed documents by sector, then company, then document type.")
recs = load_records()
if not recs:
    st.info("No documents have been added yet.")
    st.stop()

ALL_S, ALL_C, ALL_T = "All sectors", "All companies", "All document types"
sc = Counter(r["sector"] for r in recs)
c1, c2, c3 = st.columns(3)
sector = c1.selectbox("Sector", [ALL_S] + SECTORS, format_func=lambda s: s if s == ALL_S else f"{s} ({sc.get(s, 0)})")
pool = [r for r in recs if sector == ALL_S or r["sector"] == sector]
names = {r["ticker"]: r["company"] for r in pool}
company = c2.selectbox("Company / ticker", [ALL_C] + sorted(names),
                       format_func=lambda t: t if t == ALL_C else f"{names[t]} ({t})")
pool = [r for r in pool if company == ALL_C or r["ticker"] == company]
tc = Counter(r["filing_type"] for r in pool)
ftype = c3.selectbox("Document type", [ALL_T] + FILING_TYPES,
                     format_func=lambda t: t if t == ALL_T else f"{t} ({tc.get(t, 0)})")
pool = [r for r in pool if ftype == ALL_T or r["filing_type"] == ftype]
if not pool:
    st.info("Nothing here yet. Try a different sector, company or document type.")
    st.stop()

pool.sort(key=lambda r: (SECTORS.index(r["sector"]) if r["sector"] in SECTORS else 99, r["ticker"], r["date"]))
st.dataframe(pd.DataFrame([{
    "Company": r["company"], "Ticker": r["ticker"], "Sector": r["sector"], "Document type": r["filing_type"],
    "Period": r["period"], "Neg. position": ui.pct(r["summary"].get("mean_pos_negative")),
    "Placement asym.": ui.pct(r["summary"].get("placement_asymmetry")),
    "Framing ratio": ui.pct(r["summary"].get("framing_ratio"))} for r in pool]), hide_index=True, width="stretch")

st.header("Document analysis")
i = st.selectbox("Open a document", range(len(pool)), format_func=lambda i:
                 f'{pool[i]["company"]} ({pool[i]["ticker"]}) · {pool[i]["filing_type"]} · {pool[i]["period"]}')
r = pool[i]
if r.get("demo"):
    st.markdown('<span class="badge">Illustrative: fictional company</span>', unsafe_allow_html=True)
if r.get("source_url"):
    st.markdown(f"[Source document]({r['source_url']})")
ui.profile(r["summary"])
ui.lexicon_profile(r.get("lexicon"))
st.subheader("Where the information sits")
ui.strip([x["d"] for x in r["sentences"]], [x["m"] for x in r["sentences"]])
