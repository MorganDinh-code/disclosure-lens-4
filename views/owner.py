import datetime
import hmac

import streamlit as st

import ui
from disclosure_lens.checks import check_document, strip_boilerplate
from disclosure_lens.store import build_record, delete_record, list_entries, publish_record, update_record
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

add_tab, manage_tab = st.tabs(["Add a document", "Manage entries"])

with add_tab:
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
                rows = ui.stored_rows(rec["sentences"])
                ui.diagnostic([x["d"] for x in rec["sentences"]], [x["m"] for x in rec["sentences"]])
                ui.strip([x["d"] for x in rec["sentences"]], [x["m"] for x in rec["sentences"]])
                st.subheader("Disclosure Map (saved with this document)")
                ui.disclosure_map(rows)

with manage_tab:
    entries = list_entries()
    st.caption("Fix wrong details, replace or edit the document text, or remove an entry. Changes reach the public "
               "site about a minute after saving.")
    if not entries:
        st.info("There are no entries yet.")
    else:
        name = st.selectbox("Entry", [n for n, _ in entries], format_func=lambda n: n.replace(".json", ""))
        rec = dict(entries)[name]
        k = name
        has_map = bool(rec["sentences"]) and "t" in rec["sentences"][0]
        current = rec.get("source_text") or ("\n\n".join(x["t"] for x in rec["sentences"]) if has_map else "")
        if has_map and not rec.get("source_text"):
            st.info("This entry was saved before the original text was kept, so the text below is rebuilt from the "
                    "analyzed sentences (paragraph breaks and the removed legal disclaimer are not included). For the "
                    "best result, paste the original text.")
        if has_map:
            with st.expander("Current Disclosure Map for this entry"):
                ui.disclosure_map(ui.stored_rows(rec["sentences"]))
        with st.form("edit"):
            a, b, c = st.columns(3)
            company = a.text_input("Company name", rec["company"], key=f"c{k}")
            ticker = b.text_input("Ticker", rec["ticker"], key=f"t{k}")
            period = c.text_input("Period", rec["period"], key=f"p{k}")
            d, e, f = st.columns(3)
            sector = d.selectbox("Sector", SECTORS, index=SECTORS.index(rec["sector"]) if rec["sector"] in SECTORS else 0, key=f"s{k}")
            ftype = e.selectbox("Document type", FILING_TYPES, index=FILING_TYPES.index(rec["filing_type"]) if rec["filing_type"] in FILING_TYPES else 0, key=f"f{k}")
            try:
                dv = datetime.date.fromisoformat(rec.get("date", ""))
            except ValueError:
                dv = datetime.date.today()
            fdate = f.date_input("Document date", dv, key=f"d{k}")
            url = st.text_input("Source URL", rec.get("source_url", ""), key=f"u{k}")
            st.markdown("**Document text** (edit it below, or upload a file to replace it)")
            up_new = st.file_uploader("Replace with a .txt file", type=["txt"], key=f"up{k}")
            new_text = st.text_area("Text that was analyzed", current, height=380, key=f"tx{k}")
            s1, s2 = st.columns(2)
            save = s1.form_submit_button("Save details only (keep the analysis)")
            reanalyze = s2.form_submit_button("Save and re-analyze the text", type="primary")
        if save or reanalyze:
            meta = {"company": company.strip(), "ticker": ticker.strip().upper(), "sector": sector,
                    "filing_type": ftype, "period": period.strip(), "date": str(fdate), "source_url": url.strip()}
            text = up_new.read().decode("utf-8", errors="ignore") if up_new is not None else new_text
            if not (meta["company"] and meta["ticker"] and meta["period"]):
                st.error("Company name, ticker and period cannot be empty.")
            elif reanalyze and not text.strip():
                st.error("The document text is empty.")
            else:
                if reanalyze:
                    for w in check_document(strip_boilerplate(text)[0]):
                        st.warning(w)
                    new = build_record(text, meta)
                    new["demo"] = rec.get("demo", False)
                else:
                    new = {**rec, **meta}
                try:
                    update_record(name, new, cfg)
                except FileExistsError:
                    st.error("Another entry already has that ticker, period and document type.")
                except Exception as err:
                    st.error(f"Could not save: {err}")
                else:
                    st.success("Saved. The public site updates in about a minute (this page shows the old version until then).")
                    if reanalyze:
                        ui.profile(new["summary"])
                        ui.diagnostic([x["d"] for x in new["sentences"]], [x["m"] for x in new["sentences"]])
                        st.subheader("New Disclosure Map")
                        ui.disclosure_map(ui.stored_rows(new["sentences"]))
        st.divider()
        st.subheader("Remove this entry")
        sure = st.checkbox(f"Yes, permanently remove {name.replace('.json', '')}", key=f"x{k}")
        if st.button("Remove entry", disabled=not sure):
            try:
                delete_record(name, cfg)
            except Exception as err:
                st.error(f"Could not remove: {err}")
            else:
                st.success("Removed. The public site updates in about a minute.")
