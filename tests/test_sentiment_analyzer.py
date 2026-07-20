import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import sqlite3

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sentiment_analyzer

class TestSentimentAnalyzer(unittest.TestCase):
    def test_analyze_text_sentiment(self):
        # positive text
        pos_text = "Market is experiencing a massive surge and high profit growth."
        pos_score = sentiment_analyzer.analyze_text_sentiment(pos_text)
        self.assertGreater(pos_score, 0.0)

        # negative text
        neg_text = "Crash and collapse warning: massive dump and hack occurred."
        neg_score = sentiment_analyzer.analyze_text_sentiment(neg_text)
        self.assertLess(neg_score, 0.0)

        # neutral text
        neu_text = "The quick brown fox jumps over the lazy dog."
        neu_score = sentiment_analyzer.analyze_text_sentiment(neu_text)
        self.assertEqual(neu_score, 0.0)

    @patch('urllib.request.urlopen')
    @patch('database.load_setting')
    def test_fetch_ticker_sentiment(self, mock_load, mock_urlopen):
        mock_load.return_value = "1.5" # custom weight
        
        # Mock XML response with a match for BTC keyword
        rss_content = b"""<rss version="2.0">
            <channel>
                <item>
                    <title>Bitcoin rally continues as institutional demand surges</title>
                    <description>Institutional interest pushes BTC to new highs.</description>
                </item>
            </channel>
        </rss>"""
        
        mock_response = MagicMock()
        mock_response.read.return_value = rss_content
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        score, breakdown = sentiment_analyzer.fetch_ticker_sentiment("BTC-USD")
        self.assertGreater(score, 0.0)
        self.assertTrue("cointelegraph" in breakdown)
        self.assertGreater(breakdown["cointelegraph"], 0.0)

if __name__ == "__main__":
    unittest.main()
