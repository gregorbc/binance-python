import unittest
from unittest.mock import MagicMock, patch
import time
import os
import sys

# Add the root directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import CapitalManager, app_state

class TestCapitalManager(unittest.TestCase):

    def setUp(self):
        """Set up a test environment before each test."""
        self.mock_api = MagicMock()
        self.capital_manager = CapitalManager(self.mock_api)

        # Reset app_state for each test
        app_state["balance"] = 0.0
        app_state["performance_stats"]["max_drawdown"] = 0.0

    def test_initial_state(self):
        """Test the initial state of the CapitalManager."""
        self.assertEqual(self.capital_manager.current_balance, 0.0)
        self.assertEqual(self.capital_manager.initial_balance, 0.0)
        self.assertEqual(self.capital_manager.peak_balance, 0.0)
        self.assertEqual(self.capital_manager.last_update, 0)

    def test_get_real_balance_success(self):
        """Test getting the real balance with a successful API call."""
        self.mock_api.client.futures_account.return_value = {
            'assets': [{'asset': 'USDT', 'walletBalance': '1000.00'}]
        }
        self.mock_api._safe_api_call.return_value = self.mock_api.client.futures_account.return_value

        balance = self.capital_manager.get_real_balance()
        self.assertEqual(balance, 1000.0)

    def test_get_real_balance_failure(self):
        """Test getting the real balance with a failed API call."""
        self.mock_api._safe_api_call.return_value = None
        balance = self.capital_manager.get_real_balance()
        self.assertEqual(balance, 0.0)

    def test_update_balance_initial(self):
        """Test the first successful balance update."""
        self.mock_api.client.futures_account.return_value = {
            'assets': [{'asset': 'USDT', 'walletBalance': '1000.00'}]
        }
        self.mock_api._safe_api_call.return_value = self.mock_api.client.futures_account.return_value

        updated = self.capital_manager.update_balance(force=True)

        self.assertTrue(updated)
        self.assertEqual(self.capital_manager.current_balance, 1000.0)
        self.assertEqual(self.capital_manager.initial_balance, 1000.0)
        self.assertEqual(self.capital_manager.peak_balance, 1000.0)
        self.assertNotEqual(self.capital_manager.last_update, 0)
        self.assertEqual(app_state["balance"], 1000.0)

    def test_update_balance_no_force_and_throttled(self):
        """Test that balance is not updated if called too soon without force."""
        self.capital_manager.last_update = time.time()
        updated = self.capital_manager.update_balance()
        self.assertFalse(updated)

    def test_update_balance_with_force(self):
        """Test that balance is updated with force=True even if throttled."""
        self.capital_manager.last_update = time.time()
        self.mock_api.client.futures_account.return_value = {
            'assets': [{'asset': 'USDT', 'walletBalance': '1200.00'}]
        }
        self.mock_api._safe_api_call.return_value = self.mock_api.client.futures_account.return_value

        updated = self.capital_manager.update_balance(force=True)
        self.assertTrue(updated)
        self.assertEqual(self.capital_manager.current_balance, 1200.0)

    def test_drawdown_calculation(self):
        """Test the max drawdown calculation."""
        # Initial balance
        self.mock_api.client.futures_account.return_value = {'assets': [{'asset': 'USDT', 'walletBalance': '1000.00'}]}
        self.mock_api._safe_api_call.return_value = self.mock_api.client.futures_account.return_value
        self.capital_manager.update_balance(force=True)
        self.assertEqual(app_state["performance_stats"]["max_drawdown"], 0.0)

        # Balance drops
        self.mock_api.client.futures_account.return_value = {'assets': [{'asset': 'USDT', 'walletBalance': '800.00'}]}
        self.mock_api._safe_api_call.return_value = self.mock_api.client.futures_account.return_value
        self.capital_manager.update_balance(force=True)
        self.assertEqual(self.capital_manager.peak_balance, 1000.0)
        self.assertEqual(self.capital_manager.current_balance, 800.0)
        self.assertAlmostEqual(app_state["performance_stats"]["max_drawdown"], 20.0)

        # Balance recovers to new peak
        self.mock_api.client.futures_account.return_value = {'assets': [{'asset': 'USDT', 'walletBalance': '1200.00'}]}
        self.mock_api._safe_api_call.return_value = self.mock_api.client.futures_account.return_value
        self.capital_manager.update_balance(force=True)
        self.assertEqual(self.capital_manager.peak_balance, 1200.0)
        self.assertEqual(self.capital_manager.current_balance, 1200.0)
        self.assertAlmostEqual(app_state["performance_stats"]["max_drawdown"], 20.0) # Should not decrease

if __name__ == '__main__':
    unittest.main()