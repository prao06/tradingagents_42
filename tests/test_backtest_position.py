"""Rating -> position mapping for the Gate A backtester."""

import pytest

from tradingagents.agents.utils.rating import RATINGS_5_TIER
from tradingagents.backtest.position import rating_to_position


@pytest.mark.parametrize(
    "rating,expected",
    [
        ("Buy", 1.0), ("Overweight", 0.5), ("Hold", 0.0),
        ("Underweight", -0.5), ("Sell", -1.0),
    ],
)
def test_long_short_mapping(rating, expected):
    assert rating_to_position(rating) == expected


@pytest.mark.parametrize(
    "rating,expected",
    [("Buy", 1.0), ("Overweight", 0.5), ("Hold", 0.0),
     ("Underweight", 0.0), ("Sell", 0.0)],
)
def test_long_only_clamps_shorts(rating, expected):
    assert rating_to_position(rating, long_only=True) == expected


def test_parses_rating_from_free_text():
    # A full PM decision string carries a "Rating: X" header.
    text = "Executive summary...\n\n**Rating**: Sell\n\nThesis..."
    assert rating_to_position(text) == -1.0


def test_unknown_text_defaults_to_hold():
    assert rating_to_position("no rating word here") == 0.0


def test_every_canonical_rating_is_mapped():
    for r in RATINGS_5_TIER:
        assert isinstance(rating_to_position(r), float)
