# TradingAgents dashboard (Streamlit)

A lightweight dashboard over artifacts the framework already produces. The first
two views run with **no API keys and no live LLM calls** — they read files on
disk:

- **Backtest** — Gate A equity curve, metrics, walk-forward folds, significance,
  and the trades table (`<results_dir>/backtests/<run-id>/`).
- **Journal** — the decision/reflection log as a track record: ratings vs.
  realized return and alpha (`~/.tradingagents/memory/trading_memory.md`).
- **Home** — a ticker command bar (filters the other pages) + overview tiles.

## Run

```bash
uv run --with streamlit streamlit run dashboard/Home.py
# or, if you installed the extra:  pip install -e '.[dashboard]'  &&  streamlit run dashboard/Home.py
```

## Design notes
- `dashboard/data.py` holds all file parsing as pure functions (no streamlit
  import) and is unit-tested in `tests/test_dashboard_data.py`. The page scripts
  only do layout.
- Journal parsing reuses `TradingMemoryLog.load_entries()` so the dashboard and
  the agent runtime never disagree on the log format.
- Next planned view: **Decision Detail** — render the agent pipeline reasoning
  through a single ticker, with named investor-persona framing.
