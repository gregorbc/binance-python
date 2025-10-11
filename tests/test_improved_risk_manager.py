import os
import sys
import unittest

from app import CONFIG, ImprovedRiskManager

# Add the root directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class TestImprovedRiskManager(unittest.TestCase):
    def setUp(self):
        """Set up a test environment before each test."""
        self.risk_manager = ImprovedRiskManager()
        self.config = CONFIG()

    def test_calculate_position_size_kelly(self):
        """Test the Kelly Criterion position size calculation."""
        # Test case 1: Normal conditions
        balance = 1000
        signal_strength = 0.8
        win_rate = 0.6
        avg_rr = 2.0
        risk_amount = self.risk_manager.calculate_position_size_kelly(
            balance, signal_strength, win_rate, avg_rr
        )
        self.assertGreater(risk_amount, 0)

        # Test case 2: Zero win rate
        risk_amount = self.risk_manager.calculate_position_size_kelly(
            balance, signal_strength, 0, avg_rr
        )
        self.assertAlmostEqual(
            risk_amount, balance * (self.config.RISK_PER_TRADE_PERCENT / 100)
        )

    def test_calculate_sl_tp_levels_long(self):
        """Test SL/TP level calculation for a LONG signal."""
        signal = {"type": "LONG", "atr": 10, "strength": 0.8}
        price = 100
        levels = self.risk_manager.calculate_sl_tp_levels(signal, price)

        self.assertEqual(levels["sl"], 80.0)  # 100 - (10 * 2.0)
        self.assertGreater(levels["tp1"], price)
        self.assertGreater(levels["tp2"], levels["tp1"])
        self.assertGreater(levels["tp3"], levels["tp2"])

    def test_calculate_sl_tp_levels_short(self):
        """Test SL/TP level calculation for a SHORT signal."""
        signal = {"type": "SHORT", "atr": 10, "strength": 0.8}
        price = 100
        levels = self.risk_manager.calculate_sl_tp_levels(signal, price)

        self.assertEqual(levels["sl"], 120.0)  # 100 + (10 * 2.0)
        self.assertLess(levels["tp1"], price)
        self.assertLess(levels["tp2"], levels["tp1"])
        self.assertLess(levels["tp3"], levels["tp2"])


if __name__ == "__main__":
    unittest.main()
