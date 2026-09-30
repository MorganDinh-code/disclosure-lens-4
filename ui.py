"""Shared look-and-feel: black / deep navy / gold, serif type."""
import streamlit as st

GOLD, GREEN, RED, GREY, MUTED = "#C9A24B", "#4C9F70", "#C8534F", "#5B6577", "#8C93A3"
FACT = {1: GREEN, -1: RED, 0: GREY}


def tone_color(t):
    return GREEN if t > 0.05 else RED if t < -0.05 else GREY


def pct(x):
    return "n/a" if x is None else f"{x * 100:.0f}%"


def apply_theme():
    st.markdown(f"""<style>
    h1,h2,h3 {{ font-weight:600; letter-spacing:.01em; }}
    h2 {{ border-bottom:1px solid {GOLD}55; padding-bottom:.35rem; margin-top:2rem; }}
    .eyebrow {{ color:{GOLD}; text-transform:uppercase; letter-spacing:.18em; font-size:.72rem; font-weight:600; }}
    .tagline {{ font-size:2.1rem; font-weight:600; margin:.2rem 0 .3rem; }}
    .lede {{ color:{MUTED}; font-size:1.02rem; max-width:52rem; line-height:1.55; }}
    div[data-testid="stMetricLabel"] p {{ color:{MUTED}; text-transform:uppercase; letter-spacing:.08em; font-size:.7rem; }}
    div[data-testid="stMetricValue"] {{ font-variant-numeric:tabular-nums; }}
    .card {{ border:1px solid #1E2C48; border-top:2px solid {GOLD}; background:#0E1A30; padding:1rem 1.2rem; border-radius:2px; height:100%; }}
    .card b {{ color:{GOLD}; text-transform:uppercase; letter-spacing:.1em; font-size:.7rem; }}
    .badge {{ background:{GOLD}22; color:{GOLD}; padding:1px 8px; font-size:.7rem; letter-spacing:.06em; text-transform:uppercase; }}
    </style>""", unsafe_allow_html=True)


def header():
    st.markdown('<div class="eyebrow">Disclosure Lens</div>'
                '<div class="tagline">Position. Hedging. Tone.</div>'
                '<div class="lede">An open research tool that maps the structure of corporate disclosures: '
                'where information appears, how it is qualified, and how it is framed.</div>',
                unsafe_allow_html=True)


def strip(dirs, mats):
    """Position strip: one block per sentence, coloured by financial direction."""
    b = "".join(f'<div title="Sentence {i + 1}" style="flex:1;height:26px;background:{FACT[d]};'
                f'border-right:1px solid #070B14;{"outline:2px solid #E9E6DC;outline-offset:-2px;" if m else ""}"></div>'
                for i, (d, m) in enumerate(zip(dirs, mats)))
    st.markdown(f'<div style="display:flex;width:100%">{b}</div>'
                f'<div style="display:flex;justify-content:space-between;font-size:.75rem;color:{MUTED}">'
                f'<span>Start of document</span><span>End of document</span></div>', unsafe_allow_html=True)
    st.caption("One block per sentence: green = positive fact, red = negative fact, grey = neutral. "
               "White outline = material negative.")


def profile(s):
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown('<span class="eyebrow">Information order</span>', unsafe_allow_html=True)
        st.metric("Avg position, negatives", pct(s.get("mean_pos_negative")))
        st.metric("Avg position, positives", pct(s.get("mean_pos_positive")))
        st.metric("Placement asymmetry", pct(s.get("placement_asymmetry")),
                  help="Positive = bad news appears later than good news.")
        d = s.get("distance_from_headline")
        st.metric("Distance from headline", "n/a" if d is None else f"{d} sentences")
    with c2:
        st.markdown('<span class="eyebrow">Hedging</span>', unsafe_allow_html=True)
        st.metric("Hedge density near negatives", pct(s.get("hedge_near_negative")))
        st.metric("Hedge density near positives", pct(s.get("hedge_near_positive")))
        ha = s.get("hedging_asymmetry")
        st.metric("Hedging asymmetry", f"{ha:.1f}x" if ha is not None else
                  ("undefined" if s.get("hedge_near_negative") else "n/a"),
                  help="Undefined = no hedging near positives at all.")
    with c3:
        st.markdown('<span class="eyebrow">Tone vs. facts</span>', unsafe_allow_html=True)
        st.metric("Negative facts in positive language", pct(s.get("framing_ratio")))
        g = s.get("mean_tone_gap_on_negatives")
        st.metric("Mean tone gap on negatives", "n/a" if g is None else f"{g:.2f}",
                  help="Higher = more positive wording around negative facts.")


def guidelines():
    """What Disclosure Lens is (and is not) built for."""
    c1, c2 = st.columns(2)
    c1.markdown('<div class="card"><b>Built for</b><ul style="margin:.5rem 0 0 1rem;padding:0">'
                '<li><strong>Earnings press releases</strong> (best starting point)</li>'
                '<li>Earnings call transcripts, prepared remarks</li>'
                '<li>MD&amp;A sections of 10-Q and 10-K filings</li>'
                '<li>Shareholder letters and other management commentary</li></ul></div>',
                unsafe_allow_html=True)
    c2.markdown('<div class="card"><b>Not built for</b><ul style="margin:.5rem 0 0 1rem;padding:0">'
                '<li>Financial statement tables (cash flow, balance sheet, income statement)</li>'
                '<li>PDFs and scanned images (copy the text out first)</li>'
                '<li>Complete 10-Ks (too long and mostly boilerplate)</li>'
                '<li>Text in languages other than English</li></ul></div>', unsafe_allow_html=True)
    st.markdown("""
**How to prepare a document**
1. **Find it.** Company websites list press releases under *Investors* or *Investor Relations*. The free official source is
   [SEC EDGAR](https://www.sec.gov/edgar): search the company, open an **8-K** filing, then **Exhibit 99.1**.
2. **Copy the written text only.** Skip the tables of numbers at the end.
3. **Paste it or save it as a `.txt` file,** with a blank line between paragraphs.
4. The tool removes the legal *forward-looking statements* disclaimer for you if it finds one, since it is almost entirely hedging.
""")


# ---------- motion, background and landing ----------
import random

import streamlit.components.v1 as components


def _walk(seed, n=48, amp=0.22):
    rnd = random.Random(seed)
    y = [0.0]
    for _ in range(n):
        y.append(y[-1] + rnd.uniform(-1, 1) * amp)
    y = [v - (y[-1] / n) * i for i, v in enumerate(y)]  # ends where it starts, so the loop is seamless
    lo, hi = min(y), max(y)
    return [(v - lo) / (hi - lo) for v in y]


def _path(ys, x0, top, height):
    pts = [f"{x0 + 1000 * i / (len(ys) - 1):.1f},{top + height * (1 - v):.1f}" for i, v in enumerate(ys)]
    return "M" + " L".join(pts)


def apply_motion():
    grid = "".join(f'<line x1="0" x2="2000" y1="{y}" y2="{y}" stroke="#1E2C48" stroke-width="1" '
                   f'vector-effect="non-scaling-stroke"/>' for y in range(60, 600, 90))
    lines = ""
    for seed, color, w, top, h in [(11, GOLD, 2, 120, 340), (5, "#3B5B92", 1.5, 200, 300)]:
        ys = _walk(seed)
        d = _path(ys, 0, top, h) + " " + _path(ys, 1000, top, h)
        lines += f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{w}" vector-effect="non-scaling-stroke"/>'
    st.markdown(f'<div class="bgchart"><svg viewBox="0 0 2000 600" preserveAspectRatio="none">{grid}{lines}</svg></div>',
                unsafe_allow_html=True)
    css = """<style>
    [data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"]{display:none}
    .bgchart{position:fixed;inset:0;z-index:0;opacity:.11;pointer-events:none;overflow:hidden}
    .bgchart svg{width:200%;height:100%;animation:drift 80s linear infinite}
    @keyframes drift{to{transform:translateX(-50%)}}
    .hero{min-height:74vh;display:flex;flex-direction:column;justify-content:center;position:relative;z-index:1}
    .hero .name,.hero .tag,.hero .lede{transform-origin:left center}
    .hero .name{font-size:clamp(3.2rem,9vw,7.5rem);font-weight:600;line-height:1;letter-spacing:-.01em}
    .hero .tag{font-size:clamp(1.3rem,3vw,2.3rem);color:__GOLD__;margin:.6rem 0 1rem}
    .cue{margin-top:3rem;color:__MUTED__;letter-spacing:.3em;text-transform:uppercase;font-size:.7rem;animation:bob 2s ease-in-out infinite}
    @keyframes bob{50%{transform:translateY(8px)}}
    .brandbar{position:fixed;top:3.75rem;left:0;right:0;z-index:5;padding:.35rem 2rem;background:#070B14ee;
      border-bottom:1px solid __GOLD__44;display:flex;gap:1rem;align-items:baseline}
    .brandbar .t{color:__MUTED__;font-size:.9rem}
    .block-container{padding-top:6rem}
    @supports (animation-timeline: scroll()){
      .brandbar.fade{opacity:0;animation:appear linear both;animation-timeline:scroll(nearest);animation-range:180px 380px}
      @keyframes appear{to{opacity:1}}
      .hero .name,.hero .tag,.hero .lede,.hero .cue{animation:recede linear both;animation-timeline:scroll(nearest);animation-range:0 50vh}
      @keyframes recede{to{transform:translateY(-36px) scale(.8);opacity:.1}}
      .card,h2{animation:rise linear both;animation-timeline:view();animation-range:entry 0% entry 35%}
      @keyframes rise{from{opacity:0;transform:translateY(26px)}}
    }</style>"""
    st.markdown(css.replace("__GOLD__", GOLD).replace("__MUTED__", MUTED), unsafe_allow_html=True)


def brandbar(fade=False):
    st.markdown(f'<div class="brandbar{" fade" if fade else ""}"><span class="eyebrow">Disclosure Lens</span>'
                f'<span class="t">Position. Hedging. Tone.</span></div>', unsafe_allow_html=True)


def hero():
    st.markdown('<div class="hero"><div class="eyebrow">Open research tool</div><div class="name">Disclosure Lens</div>'
                '<div class="tag">Position. Hedging. Tone.</div>'
                '<div class="lede">An open research tool that maps the structure of corporate disclosures: where '
                'information appears, how it is qualified, and how it is framed.</div>'
                '<div class="cue">Scroll ↓</div></div>', unsafe_allow_html=True)


def counters(items):
    cells = "".join(f'<div class="c"><div class="n" data-t="{v}">0</div><div class="l">{l}</div></div>' for l, v in items)
    components.html(f"""<style>body{{margin:0;font-family:'Source Serif 4',Georgia,serif;color:#E9E6DC}}
    .row{{display:flex;gap:1rem}}.c{{flex:1;border-top:2px solid {GOLD};background:#0E1A30;padding:1rem 1.2rem}}
    .n{{font-size:3.2rem;font-weight:600;color:{GOLD};font-variant-numeric:tabular-nums}}
    .l{{color:{MUTED};text-transform:uppercase;letter-spacing:.12em;font-size:.72rem}}</style>
    <div class="row">{cells}</div><script>document.querySelectorAll('.n').forEach(e=>{{const t=+e.dataset.t,s=performance.now();
    (function f(n){{const p=Math.min(1,(n-s)/1600);e.textContent=Math.round(t*(1-Math.pow(1-p,3)));if(p<1)requestAnimationFrame(f)}})(s)}});</script>""",
                    height=140)


def lexicon_profile(prof):
    """Loughran-McDonald category rates per 1,000 words (only when the dictionary is installed)."""
    if not prof:
        return
    import pandas as pd
    st.subheader("Lexicon profile")
    st.bar_chart(pd.Series(prof["per_1000"]), color=GOLD, horizontal=True)
    st.caption(f'Loughran-McDonald category words per 1,000 words ({prof["words"]:,} words analyzed).')
