import pandas as pd
import streamlit as st

import ui
from disclosure_lens.store import load_records
from taxonomy import FILING_TYPES, SECTORS

st.header("Database statistics")
recs = [r for r in load_records() if not r.get("demo")]
ui.counters([("Documents analyzed", len(recs)), ("Companies", len({r["ticker"] for r in recs})),
             (f"Sectors covered (of {len(SECTORS)})", len({r["sector"] for r in recs})),
             (f"Document types (of {len(FILING_TYPES)})", len({r["filing_type"] for r in recs}))])
st.caption("Counts update automatically as documents are added. Illustrative entries are not counted.")
if not recs:
    st.info("No real documents yet. Numbers will appear once the first filing is added.")
    st.stop()
c1, c2 = st.columns(2)
with c1:
    st.subheader("Documents by sector")
    st.bar_chart(pd.Series({s: sum(r["sector"] == s for r in recs) for s in SECTORS}), color=ui.GOLD, horizontal=True)
with c2:
    st.subheader("Documents by type")
    st.bar_chart(pd.Series({t: sum(r["filing_type"] == t for r in recs) for t in FILING_TYPES}), color=ui.GOLD, horizontal=True)
st.subheader("Recently added")
st.dataframe(pd.DataFrame([{"Date": r["date"], "Company": r["company"], "Ticker": r["ticker"], "Sector": r["sector"],
                            "Document type": r["filing_type"], "Period": r["period"]}
                           for r in sorted(recs, key=lambda r: r["date"], reverse=True)[:8]]),
             hide_index=True, width="stretch")
