import hmac

import streamlit as st

import ui
from disclosure_lens.checks import check_document, strip_boilerplate
from disclosure_lens.store import build_record, publish_record
from taxonomy import FILING_TYPES, SECTORS

st.header("Owner portal")
try:
    cfg = dict(st.secrets)
except Exception:
    cfg = {}
pw = cfg.get("ADMIN_PASSWORD")
if not pw:
    st.warning("The owner portal is not set up yet. Add ADMIN_PASSWORD (and GITHUB_TOKEN, GITHUB_REPO) to the "
               "app's secrets. See the setup steps in the project README.")
    st.stop()

if not st.session_state.get("owner"):
    with st.form("login"):
        entered = st.text_input("Password", type="password")
        ok = st.form_submit_button("Log in", type="primary")
    if ok:
        if hmac.compare_digest(entered.encode(), pw.encode()):
            st.session_state["owner"] = True
            st.rerun()
        st.error("Incorrect password.")
    st.stop()

if st.button("Log out"):
    st.session_state["owner"] = False
    st.rerun()
st.subheader("Add a document to the public database")
st.caption("Paste the written text only (no tables). The analysis is saved and becomes visible to everyone "
           "about a minute after publishing.")
with st.form("add"):
    a, b, c = st.columns(3)
    company = a.text_input("Company name", placeholder="NVIDIA Corporation")
    ticker = b.text_input("Ticker", placeholder="NVDA")
    period = c.text_input("Period", placeholder="Q2 FY2027")
    d, e, f = st.columns(3)
    sector = d.selectbox("Sector", SECTORS)
    ftype = e.selectbox("Document type", FILING_TYPES)
    fdate = f.date_input("Document date")
    url = st.text_input("Source URL (link to the original)")
    up = st.file_uploader("Upload a .txt file", type=["txt"])
    pasted = st.text_area("...or paste the text", height=240)
    overwrite = st.checkbox("Replace this document if it is already in the database")
    submit = st.form_submit_button("Analyze and publish", type="primary")

if submit:
    text = up.read().decode("utf-8", errors="ignore") if up is not None else pasted
    if not (company.strip() and ticker.strip() and period.strip()):
        st.error("Please fill in company name, ticker and period.")
    elif not text.strip():
        st.error("Upload a file or paste the text.")
    else:
        for w in check_document(strip_boilerplate(text)[0]):
            st.warning(w)
        rec = build_record(text, {"company": company.strip(), "ticker": ticker.strip().upper(), "sector": sector,
                                  "filing_type": ftype, "period": period.strip(), "date": str(fdate),
                                  "source_url": url.strip()})
        try:
            where, name = publish_record(rec, overwrite, cfg)
        except FileExistsError:
            st.error("That document is already in the database. Tick 'Replace' to overwrite it.")
        except Exception as err:
            st.error(f"Could not publish: {err}")
        else:
            st.success(f"Published {name} ({'to GitHub; the site refreshes in about a minute' if where == 'github' else 'saved locally'}).")
            ui.profile(rec["summary"])
            ui.strip([x["d"] for x in rec["sentences"]], [x["m"] for x in rec["sentences"]])
            st.subheader("Disclosure Map (saved with this document)")
            ui.disclosure_map(ui.stored_rows(rec["sentences"]))
