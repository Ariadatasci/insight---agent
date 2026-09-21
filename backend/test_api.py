"""Test the HTTP boundary without making provider requests."""

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.main import app


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "online"})

    def test_agent_response_for_all_three_paths(self):
        for sql, sources in [("SELECT 1", []), (None, ["policy.pdf"]),
                             ("SELECT 1", ["policy.pdf"])]:
            with self.subTest(sql=sql, sources=sources), patch("backend.main.ask_agent") as agent:
                agent.return_value = {
                    "answer": "An answer", "sql": sql, "sources": sources,
                    "tool_results": [{"internal": "not part of the API"}],
                }
                response = self.client.post("/ask", json={"question": " A question? "})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {
                    "answer": "An answer", "sql": sql, "sources": sources,
                })
                agent.assert_called_once_with("A question?")

    def test_invalid_questions_do_not_call_agent(self):
        with patch("backend.main.ask_agent") as agent:
            for body in [{}, {"question": ""}, {"question": " \n\t "},
                         {"question": None}, {"question": 123}]:
                with self.subTest(body=body):
                    self.assertEqual(self.client.post("/ask", json=body).status_code, 422)
            agent.assert_not_called()

    def test_execution_errors_do_not_expose_secrets(self):
        with patch("backend.main.ask_agent", side_effect=RuntimeError("GROQ_API_KEY=secret-test-value")):
            response = self.client.post("/ask", json={"question": "A question?"})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {
            "detail": "The agent could not complete your question. Please try again later.",
        })

    def test_local_react_cors(self):
        for origin in ["http://localhost:5173", "http://127.0.0.1:5173"]:
            response = self.client.options("/ask", headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["access-control-allow-origin"], origin)


if __name__ == "__main__":
    unittest.main(verbosity=2)
