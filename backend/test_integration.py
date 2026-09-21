"""Real local data + scripted SDK tests, followed by separate live Groq tests."""

import json
import os
import re
import sys
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from groq.types.chat import ChatCompletionMessage

from backend.agent import ask_agent
from backend.database import query_database


CASES = [
    {
        "question": "Which city has the most customers?",
        "rule": None,
        "sql": "SELECT city, COUNT(*) AS customer_count FROM Customers GROUP BY city ORDER BY customer_count DESC, city LIMIT 1",
        "why": "SQL only: customer counts are stored data; no business definition is needed.",
    },
    {
        "question": "What is considered a high-value claim?",
        "rule": "above R50,000",
        "sql": None,
        "why": "RAG only: this asks for a policy definition, not a count of records.",
    },
    {
        "question": "How many high-value claims are in the database?",
        "rule": "above R50,000",
        "sql": "SELECT COUNT(*) AS claim_count FROM Claims WHERE claim_amount > 50000",
        "why": "RAG + SQL: retrieve the high-value rule, then count matching database claims.",
    },
    {
        "question": "How many claims require high-risk review because of their value?",
        "rule": "above R100,000",
        "sql": "SELECT COUNT(*) AS claim_count FROM Claims WHERE claim_amount > 100000",
        "why": "RAG + SQL: retrieve the value-based high-risk rule, then count matching claims.",
    },
    {
        "question": "What happens if a customer has three or more claims within 12 months?",
        "rule": "additional review",
        "sql": None,
        "why": "RAG only: this asks about the repeat-claim procedure, not affected customer records.",
    },
]


def completion(message):
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def tool_request(name, arguments):
    return completion(ChatCompletionMessage(role="assistant", tool_calls=[{
        "id": f"call_{name}", "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }]))


def print_result(case, result):
    print(f"\nQUESTION: {case['question']}")
    print(f"RAG SOURCE: {', '.join(result['sources']) or 'none'}")
    print(f"SQL: {result['sql'] or 'none'}")
    for entry in result["tool_results"]:
        print(f"DATABASE RESULT: {json.dumps(entry['result'])}")
    if not result["tool_results"]:
        print("DATABASE RESULT: none")
    print(f"FINAL ANSWER: {result['answer']}")
    print(f"WHY: {case['why']}", flush=True)


class IntegrationTests(unittest.TestCase):
    def test_five_paths_with_real_retrieval_and_database(self):
        """Script only the SDK; execute the real PDF and SQL tools."""
        print("\nOFFLINE INTEGRATION: scripted provider replies, real PDF retrieval and SQLite results.", flush=True)
        for case in CASES:
            with self.subTest(question=case["question"]):
                seen_tools = []
                def scripted_provider(**kwargs):
                    messages = kwargs["messages"]
                    last = messages[-1]
                    if last["role"] == "user":
                        if case["rule"]:
                            return tool_request("retrieve_context", {"question": case["question"]})
                        return tool_request("query_database", {"sql": case["sql"]})
                    payload = json.loads(last["content"])
                    self.assertNotIn("error", payload)
                    if "chunks" in payload:
                        seen_tools.append("retrieve_context")
                        self.assertTrue(any(case["rule"].lower() in c["text"].lower() for c in payload["chunks"]))
                        if case["sql"]:
                            return tool_request("query_database", {"sql": case["sql"]})
                        # This is deliberately a quoted source, not a claimed live LLM answer.
                        relevant = next(c for c in payload["chunks"] if case["rule"].lower() in c["text"].lower())
                        answer = f"[Scripted test response] Source excerpt: {relevant['text']}"
                    else:
                        seen_tools.append("query_database")
                        self.assertEqual(payload["rows"], query_database(case["sql"])["rows"])
                        answer = f"[Scripted test response] Database rows: {json.dumps(payload['rows'])}"
                    return completion(ChatCompletionMessage(role="assistant", content=answer))

                with patch("backend.agent.load_dotenv"), patch.dict(os.environ, {
                    "GROQ_API_KEY": "test-placeholder", "GROQ_MODEL": "test-model"
                }), patch("backend.agent.Groq") as client:
                    client.return_value.__enter__.return_value.chat.completions.create.side_effect = scripted_provider
                    result = ask_agent(case["question"])
                expected_tools = (["retrieve_context"] if case["rule"] else []) + (["query_database"] if case["sql"] else [])
                self.assertEqual(seen_tools, expected_tools)
                self.assertEqual(bool(result["sources"]), bool(case["rule"]))
                self.assertEqual(len(result["sources"]), len(set(result["sources"])))
                self.assertEqual(result["sql"], case["sql"])
                print_result(case, result)

    def test_failed_retrieval_does_not_produce_an_unsupported_answer(self):
        with patch("backend.agent.load_dotenv"), patch.dict(os.environ, {
            "GROQ_API_KEY": "test-placeholder", "GROQ_MODEL": "test-model"
        }), patch("backend.agent.Groq") as client, patch("backend.agent.retrieve_context", side_effect=RuntimeError("unavailable")):
            client.return_value.__enter__.return_value.chat.completions.create.side_effect = [
                tool_request("retrieve_context", {"question": "Define high-value claims"}),
                completion(ChatCompletionMessage(role="assistant", content="Unsupported answer.")),
            ]
            result = ask_agent("Define high-value claims")
            self.assertIn("could not verify", result["answer"])
            self.assertEqual(result["sources"], [])
            self.assertIsNone(result["sql"])

    def test_answer_without_any_evidence_is_not_accepted(self):
        with patch("backend.agent.load_dotenv"), patch.dict(os.environ, {
            "GROQ_API_KEY": "test-placeholder", "GROQ_MODEL": "test-model"
        }), patch("backend.agent.Groq") as client:
            client.return_value.__enter__.return_value.chat.completions.create.return_value = completion(
                ChatCompletionMessage(role="assistant", content="There are 999999 claims.")
            )
            result = ask_agent("How many claims are there?")
            self.assertIn("could not verify", result["answer"])
            self.assertNotIn("999999", result["answer"])

    def test_failed_rule_lookup_blocks_a_guessed_sql_threshold(self):
        with patch("backend.agent.load_dotenv"), patch.dict(os.environ, {
            "GROQ_API_KEY": "test-placeholder", "GROQ_MODEL": "test-model"
        }), patch("backend.agent.Groq") as client, patch("backend.agent.retrieve_context", return_value=[]), patch("backend.agent.query_database") as query:
            client.return_value.__enter__.return_value.chat.completions.create.side_effect = [
                tool_request("retrieve_context", {"question": "Define high-value claims"}),
                tool_request("query_database", {"sql": "SELECT COUNT(*) FROM Claims WHERE claim_amount > 1"}),
                completion(ChatCompletionMessage(role="assistant", content="A guessed answer.")),
            ]
            result = ask_agent("How many high-value claims are there?")
            query.assert_not_called()
            self.assertIn("could not verify", result["answer"])


def run_live_tests() -> bool:
    """Verify actual provider routing separately from the scripted local tests."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print("\nLIVE GROQ INTEGRATION", flush=True)
    passed = True
    for case in CASES:
        try:
            for attempt in range(3):
                try:
                    result = ask_agent(case["question"])
                    break
                except RuntimeError as error:
                    if "rate limit" not in str(error).lower() or attempt == 2:
                        raise
                    print("Groq rate limit reached; retrying this test in 30 seconds.", flush=True)
                    time.sleep(30)
            print_result(case, result)
            matches = bool(result["sources"]) == bool(case["rule"])
            if case["sql"]:
                matches = matches and bool(result["tool_results"])
                if result["tool_results"]:
                    expected = query_database(case["sql"])["rows"]
                    matches = matches and result["tool_results"][-1]["result"].get("rows") == expected
                    normalized_answer = re.sub(r"(?<=\d)[,\s]+(?=\d)", "", result["answer"])
                    matches = matches and all(
                        re.search(rf"\b{re.escape(str(value))}\b", normalized_answer, re.IGNORECASE)
                        for value in expected[0]
                    )
            else:
                matches = matches and result["sql"] is None and not result["tool_results"]
                answer = re.sub(r"(?<=\d)[,\s]+(?=\d)", "", result["answer"].lower())
                if case["rule"] == "above R50,000":
                    matches = matches and "50000" in answer and any(word in answer for word in ("above", "over", "exceed", "greater", "more than"))
                else:
                    matches = matches and "additional review" in answer and "fraud" in answer
                    matches = matches and not any(phrase in answer for phrase in (
                        "before any claim", "before approval", "before payment", "automatic rejection"
                    ))
            matches = matches and "could not verify" not in result["answer"].lower()
            print("PASS" if matches else "FAIL: Tool usage or database result did not match the expected path.", flush=True)
            passed = passed and matches
        except (ValueError, RuntimeError) as error:
            print(f"\nQUESTION: {case['question']}\nLIVE TEST UNAVAILABLE: {error}", flush=True)
            passed = False
    return passed


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(IntegrationTests)
    )
    if not result.wasSuccessful():
        raise SystemExit(1)
    raise SystemExit(0 if run_live_tests() else 1)
