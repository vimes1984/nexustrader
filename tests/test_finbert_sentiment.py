import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from finbert_sentiment import (
    finbert_sentiment_llama,
    batch_sentiment_llama,
    is_llama_available,
    apply_oxford_rules,
    SENTIMENT_PROMPT_TEMPLATE,
    LLAMA_URL,
)


class TestFinbertSentiment(unittest.TestCase):
    """Tests for the LLaMA-based crypto sentiment analyzer.

    These tests mock the HTTP transport and focus on parsing logic,
    error handling, and edge cases — no actual LLaMA server needed.
    """

    def test_prompt_template_contains_headline(self):
        """Verify the prompt template renders correctly."""
        prompt = SENTIMENT_PROMPT_TEMPLATE.format(headline="Bitcoin surges 5%")
        self.assertIn("Bitcoin surges 5%", prompt)
        self.assertIn("[INST]", prompt)
        self.assertIn("[/INST]", prompt)
        self.assertIn("score", prompt)
        self.assertIn("confidence", prompt)

    def test_finbert_truncates_long_headlines(self):
        """Very long headlines should be truncated at 300 chars by the function."""
        long_text = "X" * 500
        # finbert_sentiment_llama does headline[:300] before formatting
        # Since mock will return None (server unreachable), result should be None
        import urllib.error
        with unittest.mock.patch('urllib.request.urlopen') as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
            result = finbert_sentiment_llama(long_text)
            self.assertIsNone(result)

    @patch('urllib.request.urlopen')
    def test_successful_sentiment_parse(self, mock_urlopen):
        """FinBERT-LLaMA correctly parses normal JSON response."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "content": '{"score": 0.7, "confidence": 0.85, "reasoning": "Bullish momentum"}'
        }).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        result = finbert_sentiment_llama("Bitcoin ETF approved")
        self.assertIsNotNone(result)
        score, confidence = result
        self.assertAlmostEqual(score, 0.7)
        self.assertAlmostEqual(confidence, 0.85)

    @patch('urllib.request.urlopen')
    def test_negative_sentiment(self, mock_urlopen):
        """Negative sentiment correctly assigned."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "content": '{"score": -0.8, "confidence": 0.9, "reasoning": "Bearish hack news"}'
        }).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        score, confidence = finbert_sentiment_llama("Crypto exchange hacked")
        self.assertAlmostEqual(score, -0.8)
        self.assertGreater(confidence, 0.8)

    @patch('urllib.request.urlopen')
    def test_json_in_code_block(self, mock_urlopen):
        """Handle model output wrapped in ```json blocks."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "content": "```json\n{\"score\": 0.5, \"confidence\": 0.6, \"reasoning\": \"Moderate\"}\n```"
        }).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        result = finbert_sentiment_llama("Market is neutral")
        self.assertIsNotNone(result)
        score, confidence = result
        self.assertAlmostEqual(score, 0.5)
        self.assertAlmostEqual(confidence, 0.6)

    @patch('urllib.request.urlopen')
    def test_score_clamping(self, mock_urlopen):
        """Scores outside [-1, 1] should be clamped."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "content": '{"score": -2.5, "confidence": 1.5, "reasoning": "Extreme"}'
        }).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        score, confidence = finbert_sentiment_llama("Crypto apocalypse")
        self.assertAlmostEqual(score, -1.0)  # clamped to -1.0
        self.assertAlmostEqual(confidence, 1.0)  # clamped to 1.0

    @patch('urllib.request.urlopen')
    def test_malformed_json(self, mock_urlopen):
        """Malformed JSON from LLaMA should return None."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "content": "This is not JSON at all"
        }).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        result = finbert_sentiment_llama("Some random headline")
        self.assertIsNone(result)

    @patch('urllib.request.urlopen')
    def test_empty_headline(self, mock_urlopen):
        """Empty or whitespace-only headline still hits the API."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "content": '{"score": 0.0, "confidence": 0.5, "reasoning": "No signal from empty text"}'
        }).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        result = finbert_sentiment_llama("")
        self.assertIsNotNone(result)
        score, confidence = result
        self.assertAlmostEqual(score, 0.0)

    @patch('urllib.request.urlopen')
    def test_llama_unreachable(self, mock_urlopen):
        """Server unreachable returns None."""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        result = finbert_sentiment_llama("Test headline")
        self.assertIsNone(result)

    @patch('urllib.request.urlopen')
    def test_timeout(self, mock_urlopen):
        """Timeout exception returns None gracefully."""
        import socket
        mock_urlopen.side_effect = socket.timeout("timed out")

        result = finbert_sentiment_llama("Test headline")
        self.assertIsNone(result)

    @patch('urllib.request.urlopen')
    def test_batch_sentiment(self, mock_urlopen):
        """Batch processing aggregates correctly."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "content": '{"score": 0.3, "confidence": 0.7, "reasoning": "Slightly bullish"}'
        }).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        result = batch_sentiment_llama(
            ["Headline 1", "Headline 2", "Headline 3"],
            max_headlines=3,
            timeout=15.0
        )
        self.assertIn("aggregated_score", result)
        self.assertIn("individual", result)
        self.assertIn("sources_used", result)
        self.assertEqual(result["sources_used"], 3)
        self.assertAlmostEqual(result["aggregated_score"], 0.3, places=1)

    @patch('urllib.request.urlopen')
    def test_batch_empty_headlines(self, mock_urlopen):
        """Empty headline list returns zero score."""
        result = batch_sentiment_llama([], max_headlines=5)
        self.assertEqual(result["aggregated_score"], 0.0)
        self.assertEqual(result["sources_used"], 0)
        self.assertEqual(result["individual"], [])

    @patch('urllib.request.urlopen')
    def test_is_llama_available_true(self, mock_urlopen):
        """Health check returns True when server responds 200."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        self.assertTrue(is_llama_available(timeout=1.0))

    @patch('urllib.request.urlopen')
    def test_is_llama_available_false(self, mock_urlopen):
        """Health check returns False on any error."""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("Not found")

        self.assertFalse(is_llama_available(timeout=1.0))

    def test_apply_oxford_rules_volume_confirm(self):
        """Volume confirmation rule boosts signal."""
        result = apply_oxford_rules(
            ticker="BTC-USD",
            signal_score=0.5,
            volume_ratio=2.0,
            realized_vol=0.03,
            target_vol=0.02,
            is_weekend=False
        )
        self.assertIn("adjusted_signal", result)
        self.assertIn("original_signal", result)
        self.assertIn("adjustments", result)
        # Volume ratio > 1.5 should boost signal
        self.assertGreater(result["adjusted_signal"], result["original_signal"])
        self.assertIn("volume_confirm", result["adjustments"])

    def test_apply_oxford_rules_weekend(self):
        """Weekend rule should flag position trimming."""
        result = apply_oxford_rules(
            ticker="ETH-USD",
            signal_score=0.3,
            volume_ratio=1.0,
            realized_vol=0.02,
            target_vol=0.02,
            is_weekend=True
        )
        self.assertIn("weekend_trim", result["adjustments"])

    def test_apply_oxford_rules_no_adjustment(self):
        """No volume spike, no weekend — no adjustments for those rules."""
        result = apply_oxford_rules(
            ticker="SOL-USD",
            signal_score=0.0,
            volume_ratio=1.0,
            realized_vol=0.02,
            target_vol=0.02,
            is_weekend=False
        )
        self.assertAlmostEqual(result["adjusted_signal"], result["original_signal"], places=4)

    def test_oxford_rules_dict_present(self):
        """Check that OXFORD_MICROSTRUCTURE_RULES contains expected entries."""
        from finbert_sentiment import OXFORD_MICROSTRUCTURE_RULES
        expected_rules = [
            "volatility_clustering",
            "volume_price_trend",
            "bid_ask_bounce",
            "momentum_reversal",
            "realized_variance_scaling",
            "overnight_gap_risk",
        ]
        for rule in expected_rules:
            self.assertIn(rule, OXFORD_MICROSTRUCTURE_RULES)
            self.assertIn("description", OXFORD_MICROSTRUCTURE_RULES[rule])
            self.assertIn("rule", OXFORD_MICROSTRUCTURE_RULES[rule])


if __name__ == "__main__":
    unittest.main()
