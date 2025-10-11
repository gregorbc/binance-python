import os
import sys
import unittest

from app import CandlePatterns

# Add the root directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class TestCandlePatterns(unittest.TestCase):
    def setUp(self):
        """Set up a test environment before each test."""
        self.patterns = CandlePatterns()

    def test_bullish_engulfing(self):
        """Test the bullish engulfing pattern detection."""
        # Positive case
        prev_candle = {"open": 105, "close": 100, "high": 106, "low": 99}
        curr_candle = {"open": 99, "close": 106, "high": 107, "low": 98}
        self.assertTrue(self.patterns.is_bullish_engulfing(
            curr_candle, prev_candle))

        # Negative case: previous candle is not bearish
        prev_candle = {"open": 100, "close": 105, "high": 106, "low": 99}
        self.assertFalse(self.patterns.is_bullish_engulfing(
            curr_candle, prev_candle))

    def test_bearish_engulfing(self):
        """Test the bearish engulfing pattern detection."""
        # Positive case
        prev_candle = {"open": 100, "close": 105, "high": 106, "low": 99}
        curr_candle = {"open": 106, "close": 99, "high": 107, "low": 98}
        self.assertTrue(self.patterns.is_bearish_engulfing(
            curr_candle, prev_candle))

        # Negative case: previous candle is not bullish
        prev_candle = {"open": 105, "close": 100, "high": 106, "low": 99}
        self.assertFalse(self.patterns.is_bearish_engulfing(
            curr_candle, prev_candle))

    def test_hammer(self):
        """Test the hammer pattern detection."""
        # Classic hammer (bullish, long lower wick, short upper wick)
        candle = {"open": 102, "close": 104, "high": 104.5, "low": 95}
        self.assertTrue(self.patterns.is_hammer(candle))

        # Not a hammer (bearish)
        candle = {"open": 104, "close": 102, "high": 104.5, "low": 95}
        self.assertFalse(self.patterns.is_hammer(candle))

        # Not a hammer (upper wick too long)
        candle = {"open": 102, "close": 104, "high": 106, "low": 95}
        self.assertFalse(self.patterns.is_hammer(candle))

    def test_shooting_star(self):
        """Test the shooting star pattern detection."""
        # Classic shooting star (bearish, long upper wick, short lower wick)
        candle = {"open": 104, "close": 102, "high": 110, "low": 101.5}
        self.assertTrue(self.patterns.is_shooting_star(candle))

        # Not a shooting star (bullish)
        candle = {"open": 102, "close": 104, "high": 110, "low": 101.5}
        self.assertFalse(self.patterns.is_shooting_star(candle))

        # Not a shooting star (lower wick too long)
        candle = {"open": 104, "close": 102, "high": 110, "low": 100}
        self.assertFalse(self.patterns.is_shooting_star(candle))

    def test_pin_bar_bullish(self):
        """Test the bullish pin bar pattern detection."""
        candle = {"open": 101, "close": 102, "high": 103, "low": 90}
        self.assertTrue(self.patterns.is_pin_bar_bullish(candle))

        # Not a bullish pin bar (small lower wick)
        candle = {"open": 101, "close": 102, "high": 103, "low": 100}
        self.assertFalse(self.patterns.is_pin_bar_bullish(candle))

    def test_pin_bar_bearish(self):
        """Test the bearish pin bar pattern detection."""
        candle = {"open": 102, "close": 101, "high": 110, "low": 100}
        self.assertTrue(self.patterns.is_pin_bar_bearish(candle))

        # Not a bearish pin bar (small upper wick)
        candle = {"open": 102, "close": 101, "high": 103, "low": 100}
        self.assertFalse(self.patterns.is_pin_bar_bearish(candle))


if __name__ == "__main__":
    unittest.main()
