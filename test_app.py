import math

import pytest


# Copied from app.BinanceFutures to be tested in isolation
def round_value(value: float, step: float) -> float:
    if step == 0:
        return value
    # The original function used math.log10, so we need to import math
    precision = max(0, int(round(-math.log10(step))))
    return round(math.floor(value / step) * step, precision)


@pytest.mark.parametrize(
    "value, step, expected",
    [
        (123.456, 0.01, 123.45),  # Standard rounding
        (123.45, 0.01, 123.45),  # Already a multiple
        (123.456, 0.001, 123.456),  # Higher precision
        (99.99, 1.0, 99.0),  # Rounding to whole number
        (0.12345678, 0.0000001, 0.1234567),  # High precision step
        (100, 0, 100),  # Step is zero
    ],
)
def test_round_value(value, step, expected):
    # Now calls the local version of the function
    assert round_value(value, step) == expected
