import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import antigravity_proxy
from fastapi.testclient import TestClient

class TestAntigravityProxy(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(antigravity_proxy.app)

    def test_health_check(self):
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"status": "ok", "provider": "antigravity"})

    @patch('antigravity_proxy.Agent')
    def test_generate_content_success(self, mock_agent_cls):
        # Setup mock Agent async context manager and async iterator for response chat
        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent
        
        # Async context manager mock
        mock_agent.__aenter__ = AsyncMock(return_value=mock_agent)
        mock_agent.__aexit__ = AsyncMock(return_value=None)
        
        async def mock_async_iter():
            yield "token1"
            yield "token2"
        mock_agent.chat = AsyncMock(return_value=mock_async_iter())
        
        req_payload = {
            "contents": [
                {
                    "parts": [{"text": "Hello bot"}]
                }
            ]
        }
        
        res = self.client.post("/v1beta/models/gemini-flash-latest:generateContent", json=req_payload, headers={"x-goog-api-key": "fake-key"})
        self.assertEqual(res.status_code, 200)
        res_json = res.json()
        self.assertIn("candidates", res_json)
        text_out = res_json["candidates"][0]["content"]["parts"][0]["text"]
        self.assertEqual(text_out, "token1token2")

if __name__ == "__main__":
    unittest.main()
