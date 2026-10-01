"""Key financial facts: sentences from the document that state figures, grouped by topic. Nothing is rewritten."""
import re

FIG = re.compile(r"\$\s?\d|\d[\d,.]*\s?%|\d[\d,.]*\s?(?:billion|million|bn|mn)\b", re.I)
# (topic, pattern). A sentence goes to the FIRST matching topic in this priority order.
PRIORITY = [("Outlook and guidance", r"outlook|guidance|forecast|expects?\b|expected|anticipat|next quarter|full[- ]year"),
            ("Capital returns", r"dividend|repurchase|buyback"),
            ("Cash flow and balance sheet", r"cash flow|free cash|cash and|liquidity|debt|capital expenditure|capex|inventory"),
            ("Profitability", r"income|profit|margin|earnings per|\beps\b|ebitda"),
            ("Revenue and growth", r"revenue|sales|bookings|subscribers?|memberships?|orders|customers"),
            ("Costs, charges and risks", r"expenses?|impairment|restructuring|charge|litigation|tariff|export|headwind|supply|regulat")]
DISPLAY = ["Revenue and growth", "Profitability", "Cash flow and balance sheet", "Capital returns",
           "Outlook and guidance", "Costs, charges and risks"]


def key_facts(rows, per_topic=5):
    pools = {name: [] for name, _ in PRIORITY}
    for r in rows:
        t = " ".join(r["text"].split())
        n = len(FIG.findall(t))
        if not n or len(t) > 400:
            continue
        for name, rx in PRIORITY:
            if re.search(rx, t, re.I):
                pools[name].append((n, r["index"], t))
                break
    out = {}
    for name in DISPLAY:
        top = sorted(sorted(pools[name], key=lambda x: -x[0])[:per_topic], key=lambda x: x[1])
        if top:
            out[name] = [{"index": i, "text": t} for _, i, t in top]
    return out
