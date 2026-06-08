"""TradingAgents dashboard — home / overview.

Run:  uv run --with streamlit streamlit run dashboard/Home.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root on path

import streamlit as st

from dashboard import data

st.set_page_config(page_title="TradingAgents", layout="wide", page_icon="📈")


def command_bar() -> str:
    """A Bloomberg-style ticker filter shared across pages via session_state."""
    col_t, col_hint = st.columns([1, 4])
    with col_t:
        ticker = st.text_input(
            "Ticker", value=st.session_state.get("ticker", ""),
            placeholder="e.g. NVDA", key="ticker",
        ).strip().upper()
    with col_hint:
        st.caption(
            "Type a ticker to filter the Journal and Backtest views. "
            "Backtest + Journal run entirely on artifacts already on disk — "
            "no API keys or live LLM calls."
        )
    return ticker


st.title("📈 TradingAgents")
st.caption("Transparent multi-agent reasoning, and an honest record of whether it paid off.")
command_bar()

left, right = st.columns(2)

# --- latest backtest verdict ---
with left:
    st.subheader("Latest Gate A backtest")
    runs = data.list_backtest_runs(data.backtests_root())
    if not runs:
        st.info("No backtests yet. Run `scripts/run_backtest.py` to generate one.")
    else:
        bt = data.load_backtest(runs[0])
        s = bt["summary"]
        verdict = s.get("verdict", "—")
        st.metric("Verdict", verdict, help="PASS needs: beats baseline, Sharpe>0, point-in-time, p<0.05")
        c1, c2, c3 = st.columns(3)
        c1.metric("Total return", f"{s.get('total_return', 0):+.2%}")
        c2.metric("Sharpe", f"{s.get('sharpe', 0):.2f}")
        c3.metric("p-value", f"{s.get('p_value', 1):.3f}")
        if not s.get("pit", True):
            st.warning("⚠️ Not point-in-time — results carry look-ahead leakage.")
        st.caption(f"Run: {bt['name']} · open the **Backtest** page for detail.")

# --- journal track record ---
with right:
    st.subheader("Decision track record")
    df = data.load_journal()
    js = data.journal_summary(df)
    if js["n_resolved"] == 0 and js["n_pending"] == 0:
        st.info("No decisions logged yet. Each `propagate()` run records one here.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Win rate", f"{js['win_rate']:.0%}", help="Resolved decisions with positive realized return")
        c2.metric("Mean return", f"{js['mean_return']:+.2%}")
        c3.metric("Mean alpha", f"{js['mean_alpha']:+.2%}")
        st.caption(
            f"{js['n_resolved']} resolved · {js['n_pending']} pending · "
            "open the **Journal** page for detail."
        )

st.divider()
st.caption(
    "Built on data the framework already produces. Next view to add: "
    "**Decision Detail** — watch the agent pipeline (Market/Sentiment/News/"
    "Fundamentals → Bull/Bear → Trader → Risk → Portfolio Manager) reason through a ticker."
)
