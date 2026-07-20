import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import sqlite3
import pandas as pd
import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import quant_utils

class TestQuantUtils(unittest.TestCase):
    def test_kalman_filter_price(self):
        kf = quant_utils.KalmanFilterPrice(process_variance=1e-4, measurement_variance=1e-2)
        # Initial update
        val = kf.update(100.0)
        self.assertEqual(val, 100.0)
        
        # Subsequent updates should filter noise
        val2 = kf.update(105.0)
        self.assertLess(val2, 105.0)
        self.assertGreater(val2, 100.0)

    def test_estimate_ou_process(self):
        # Trending prices (not mean reverting)
        trending_prices = [100.0 + i for i in range(30)]
        theta, mu, is_mr = quant_utils.estimate_ou_process(trending_prices)
        self.assertFalse(is_mr)
        
        # Mean reverting series
        mr_prices = [100.0 + np.sin(i * 0.5) for i in range(40)]
        theta, mu, is_mr = quant_utils.estimate_ou_process(mr_prices)
        # It may or may not be strictly fitted as MR depending on sample size, but shouldn't throw error
        self.assertIsInstance(theta, float)
        self.assertIsInstance(mu, float)

    def test_detect_psychological_sweep(self):
        # Create a mock df
        data = {
            'high': [102.0]*25,
            'low': [98.0]*25,
            'close': [100.0]*25,
            'open': [100.0]*25
        }
        df = pd.DataFrame(data)
        
        # Baseline: no sweep
        score = quant_utils.detect_psychological_sweep(df)
        self.assertEqual(score, 0.0)
        
        # Support sweep: current low goes below support (98.0), but close is above (99.0)
        df.loc[df.index[-1], 'low'] = 97.0
        df.loc[df.index[-1], 'close'] = 99.0
        score = quant_utils.detect_psychological_sweep(df)
        self.assertGreater(score, 0.0)

    @patch('urllib.request.urlopen')
    def test_query_gemini_robust_provider(self, mock_urlopen):
        import urllib.error
        # Mock successful Gemini API response
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"candidates": [{"content": {"parts": [{"text": "mock LLM output"}]}}]}'
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.side_effect = [urllib.error.URLError("health check fail"), mock_response]
        
        # We temporarily mock the db path
        test_db = "test_nexustrader_utils.db"
        with patch('os.path.expanduser', return_value=test_db):
            res = quant_utils.query_gemini_robust(api_key="test-api-key", prompt="test prompt")
            self.assertEqual(res, "mock LLM output")
            
            # Clean up DB if created
            if os.path.exists(test_db):
                os.remove(test_db)

if __name__ == "__main__":
    unittest.main()
