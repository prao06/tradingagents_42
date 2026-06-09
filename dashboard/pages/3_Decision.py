"""Decision Detail — watch the firm reason through a ticker.

Renders a saved propagate() run as the agent pipeline, with investor-persona
framing, ending in the Portfolio Manager's decision card.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root on path

import streamlit as st

from dashboard import data

st.set_page_config(page_title="Decision · TradingAgents", layout="wide", page_icon="🧠")
st.title("🧠 Decision detail")
st.caption("The multi-agent pipeline reasoning through one ticker — analysts, a bull/bear debate, the trader, and the risk committee.")

_RATING_COLOR = {
    "Buy": "green", "Overweight": "green",
    "Hold": "gray",
    "Underweight": "red", "Sell": "red",
}

runs = data.list_decision_runs(data.decisions_root())
if not runs:
    st.info(
        "No saved runs yet. Each `propagate(ticker, date)` writes one to "
        "`<results_dir>/<ticker>/TradingAgentsStrategy_logs/`."
    )
    st.stop()

# Honor the shared command-bar ticker filter from Home, if set.
ticker = st.session_state.get("ticker", "")
view = [r for r in runs if not ticker or r["ticker"].upper() == ticker] or runs
if ticker and not any(r["ticker"].upper() == ticker for r in runs):
    st.caption(f"No runs for {ticker}; showing all.")

choice = st.selectbox(
    "Run", view, format_func=lambda r: f"{r['ticker']} · {r['date']}",
)
raw = data.load_decision_run(choice["path"])
rating = data.decision_rating(raw)

# --- decision card -------------------------------------------------------
head = st.columns([1, 3])
with head[0]:
    st.metric("Final rating", rating)
    st.markdown(f":{_RATING_COLOR.get(rating, 'gray')}[**{choice['ticker']}** · {choice['date']}]")
with head[1]:
    final = (raw.get("final_trade_decision") or "").strip()
    with st.container(border=True):
        st.markdown("**Portfolio Manager decision**")
        st.markdown(final or "_(no decision text)_")

st.divider()

# --- pipeline ------------------------------------------------------------
stages = data.decision_stages(raw)
groups = []
for s in stages:
    if not groups or groups[-1][0] != s["group"]:
        groups.append((s["group"], []))
    groups[-1][1].append(s)


def _render(stage, expanded=False):
    title = f"{stage['icon']} {stage['label']} — {stage['persona']}"
    with st.expander(title, expanded=expanded):
        if stage["content"]:
            st.markdown(stage["content"])
        else:
            st.caption("(no output recorded)")


for group, items in groups:
    st.subheader(group)
    if group == "Research debate" and len(items) >= 2:
        # Bull vs Bear side by side; manager (and any extra) full width below.
        bull, bear = st.columns(2)
        with bull:
            _render(items[0], expanded=True)
        with bear:
            _render(items[1], expanded=True)
        for extra in items[2:]:
            _render(extra, expanded=True)
    elif group == "Risk committee":
        cols = st.columns(len(items))
        for col, stage in zip(cols, items):
            with col:
                _render(stage)
    else:
        for stage in items:
            _render(stage, expanded=(group == "Analysts"))
