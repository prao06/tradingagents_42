"""Backtest analytics — Gate A equity curve, metrics, folds, significance, trades."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root on path

import pandas as pd
import streamlit as st

from dashboard import data

st.set_page_config(page_title="Backtest · TradingAgents", layout="wide", page_icon="📊")
st.title("📊 Gate A backtest")

runs = data.list_backtest_runs(data.backtests_root())
if not runs:
    st.info("No backtests found. Generate one with `scripts/run_backtest.py`.")
    st.stop()

choice = st.selectbox("Run", runs, format_func=lambda p: p.name)
bt = data.load_backtest(choice)
s = bt["summary"]

verdict = s.get("verdict", "—")
(st.success if verdict == "PASS" else st.error)(f"Verdict: **{verdict}**")
if not s.get("pit", True):
    st.warning("⚠️ NON-POINT-IN-TIME — includes news/social/fundamentals, so results leak future data.")

# --- metric tiles ---
row1 = st.columns(4)
row1[0].metric("Total return (net)", f"{s.get('total_return', 0):+.2%}")
row1[1].metric("Annualized", f"{s.get('annualized_return', 0):+.2%}")
row1[2].metric("Sharpe", f"{s.get('sharpe', 0):.2f}")
row1[3].metric("Max drawdown", f"{s.get('max_drawdown', 0):.2%}")
row2 = st.columns(4)
row2[0].metric("Hit rate", f"{s.get('hit_rate', 0):.0%}")
row2[1].metric("p-value", f"{s.get('p_value', 1):.3f}",
               help="One-sided bootstrap; significant when < 0.05")
row2[2].metric("Fold win rate", f"{s.get('fold_win_rate', 0):.0%}")
row2[3].metric(f"Baseline ({s.get('baseline_ticker', 'SPY')})",
               f"{s.get('baseline_return', 0):+.2%}")

# --- equity curve ---
st.subheader("Equity curve (growth of $1, net)")
eq = bt["equity"]
if not eq.empty:
    st.line_chart(eq.set_index(eq.columns[0])[eq.columns[1]])
else:
    st.caption("No equity series for this run.")

# --- walk-forward folds ---
folds = s.get("folds") or []
if folds:
    st.subheader("Walk-forward folds")
    st.dataframe(pd.DataFrame(folds), use_container_width=True, hide_index=True)

# --- trades (ticker filter from the command bar) ---
st.subheader("Trades")
trades = bt["trades"]
ticker = st.session_state.get("ticker", "")
if ticker and not trades.empty and "ticker" in trades:
    trades = trades[trades["ticker"].str.upper() == ticker]
    st.caption(f"Filtered to {ticker}")
st.dataframe(trades, use_container_width=True, hide_index=True)
