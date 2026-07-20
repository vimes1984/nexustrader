import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import pandas as pd
import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_ingestion import DataIngestion

class TestDataIngestion(unittest.TestCase):
    def setUp(self):
        self.ingestion = DataIngestion(ticker="BTC-USD", interval="1h", period="5d")

    @patch('yfinance.download')
    def test_fetch_historical_data_success(self, mock_download):
        # Create a mock dataframe
        dates = pd.date_range(start="2026-07-01", periods=60, freq="h")
        mock_df = pd.DataFrame({
            'Open': [100.0 + i for i in range(60)],
            'High': [102.0 + i for i in range(60)],
            'Low': [98.0 + i for i in range(60)],
            'Close': [101.0 + i for i in range(60)],
            'Volume': [1000.0 + i for i in range(60)]
        }, index=dates)
        mock_df.index.name = 'Datetime'
        mock_download.return_value = mock_df

        df = self.ingestion.fetch_historical_data()
        self.assertFalse(df.empty)
        self.assertEqual(len(df), 60)
        self.assertIn('sma_20', df.columns)
        self.assertIn('rsi', df.columns)
        self.assertIn('atr', df.columns)

    def test_compute_technical_indicators_empty(self):
        self.ingestion.data = pd.DataFrame()
        self.ingestion.compute_technical_indicators()
        self.assertTrue(self.ingestion.data.empty)

    def test_streaming_subscriptions(self):
        callback_mock = MagicMock()
        self.ingestion.subscribe(callback_mock)
        
        # Simulate a live tick
        tick = {
            "timestamp": 1234567,
            "open": 100.0,
            "high": 102.0,
            "low": 98.0,
            "close": 101.0,
            "volume": 1000.0
        }
        self.ingestion.data = pd.DataFrame([tick])
        self.ingestion.live_price = 101.0
        for callback in self.ingestion.subscribers:
            callback(tick)
        
        callback_mock.assert_called_once_with(tick)

if __name__ == "__main__":
    unittest.main()
