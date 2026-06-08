"""Map a 5-tier rating to a target position weight.

The mapping is the bridge between the framework's qualitative output and a
quantitative backtest. Long/short is the default because it tests both halves of
the signal (bullish and bearish calls); ``long_only`` clamps shorts to flat for
users who will not (or cannot) short on their broker.
"""

from __future__ import annotations

from tradingagents.agents.utils.rating import RATINGS_5_TIER, parse_rating

# Most-bullish to most-bearish, evenly spaced over [-1, +1] following the
# canonical 5-tier order in ``RATINGS_5_TIER``.
_POSITION_BY_RATING = {
    "Buy": 1.0,
    "Overweight": 0.5,
    "Hold": 0.0,
    "Underweight": -0.5,
    "Sell": -1.0,
}

# Guard against drift if the canonical scale ever changes.
assert set(_POSITION_BY_RATING) == set(RATINGS_5_TIER)


def rating_to_position(rating: str, long_only: bool = False) -> float:
    """Return the target position weight in [-1, 1] for a 5-tier ``rating``.

    Accepts either a clean rating word ("Buy") or free-text the rating is
    embedded in — the latter is parsed via :func:`parse_rating`, so a full
    Portfolio Manager decision string works directly. Unrecognised input falls
    back to the parser's default ("Hold" -> 0.0). When ``long_only`` is set,
    negative (short) weights are clamped to 0.
    """
    weight = _POSITION_BY_RATING.get(rating)
    if weight is None:
        weight = _POSITION_BY_RATING[parse_rating(rating)]
    if long_only and weight < 0:
        return 0.0
    return weight
