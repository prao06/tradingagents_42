"""Decision journal — the track record: ratings vs realized return/alpha."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root on path

import streamlit as st

from dashboard import data

st.set_page_config(page_title="Journal · TradingAgents", layout="wide", page_icon="📒")
st.title("📒 Decision journal")
st.caption("Every propagate() run is recorded here; the reflection loop fills in the realized outcome.")

df = data.load_journal()
if df.empty:
    st.info("No decisions logged yet. They appear here after `propagate()` runs.")
    st.stop()

# --- track-record tiles ---
js = data.journal_summary(df)
c = st.columns(5)
c[0].metric("Win rate", f"{js['win_rate']:.0%}")
c[1].metric("Mean return", f"{js['mean_return']:+.2%}")
c[2].metric("Mean alpha", f"{js['mean_alpha']:+.2%}")
c[3].metric("Resolved", js["n_resolved"])
c[4].metric("Pending", js["n_pending"])

# --- filters (ticker comes from the shared command bar on Home) ---
f1, f2 = st.columns(2)
ratings = sorted(r for r in df["rating"].dropna().unique())
rating_sel = f1.multiselect("Rating", ratings, default=ratings)
status_sel = f2.multiselect("Status", ["resolved", "pending"], default=["resolved", "pending"])

view = df[df["rating"].isin(rating_sel) & df["status"].isin(status_sel)]
ticker = st.session_state.get("ticker", "")
if ticker:
    view = view[view["ticker"].str.upper() == ticker]
    st.caption(f"Filtered to {ticker}")

display = view.copy()
display["raw_return"] = display["raw_return"] * 100  # fractions -> percent for display
display["alpha_return"] = display["alpha_return"] * 100
st.dataframe(
    display[["date", "ticker", "rating", "status", "raw_return", "alpha_return", "holding"]],
    use_container_width=True, hide_index=True,
    column_config={
        "raw_return": st.column_config.NumberColumn("raw return %", format="%.2f"),
        "alpha_return": st.column_config.NumberColumn("alpha %", format="%.2f"),
    },
)

# --- drill-down into a single decision ---
st.subheader("Decision detail")
if not view.empty:
    options = view.index.tolist()
    idx = st.selectbox(
        "Entry", options,
        format_func=lambda i: f"{view.loc[i, 'date']} · {view.loc[i, 'ticker']} · {view.loc[i, 'rating']}",
    )
    row = view.loc[idx]
    if row["reflection"]:
        st.markdown("**Reflection (post-outcome):**")
        st.info(row["reflection"])
    if row["decision"]:
        with st.expander("Full decision text"):
            st.markdown(row["decision"])
