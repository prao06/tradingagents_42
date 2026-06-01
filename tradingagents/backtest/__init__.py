"""Gate A backtester: an honest, point-in-time edge test for TradingAgents.

The package answers one question before any execution/live work is justified:
does the framework's 5-tier rating beat buy-and-hold SPY, out-of-sample, net of
costs, with no look-ahead leakage? See :mod:`tradingagents.backtest.engine`.
"""

from tradingagents.backtest.position import rating_to_position
from tradingagents.backtest.engine import run_backtest

__all__ = ["rating_to_position", "run_backtest"]
