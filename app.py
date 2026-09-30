"""Disclosure Lens. Run locally:  python3 -m streamlit run app.py"""
import streamlit as st

import ui

st.set_page_config(page_title="Disclosure Lens", page_icon="🔍", layout="wide", initial_sidebar_state="collapsed")
ui.apply_theme()
ui.apply_motion()
pg = st.navigation([
    st.Page("views/analyze.py", title="Analyze", default=True),
    st.Page("views/methodology.py", title="Methodology"),
    st.Page("views/lexicon.py", title="Lexicon"),
    st.Page("views/database.py", title="Database"),
    st.Page("views/stats.py", title="Stats"),
    st.Page("views/owner.py", title="Owner login"),
], position="top")
ui.brandbar(fade=pg.title == "Analyze")
pg.run()
