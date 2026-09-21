"""Offline safety tests and an explicitly invoked live Groq demonstration."""

import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from groq.types.chat import ChatCompletionMessage

from backend.agent import ask_agent, execute_tool_call
from backend.database import query_database


QUESTIONS = [
    ("How many customers are in the database?",
     "SELECT COUNT(*) FROM Customers"),
    ("Which city has the most customers?",
     "SELECT city, COUNT(*) FROM Customers GROUP BY city ORDER BY COUNT(*) DESC, city LIMIT 1"),
    ("What is the average claim amount?",
     "SELECT AVG(claim_amount) FROM Claims"),
    ("Which province has the highest total claim amount?",
     "SELECT c.province, SUM(cl.claim_amount) FROM Customers c "
     "JOIN Claims cl ON c.customer_id = cl.customer_id GROUP BY c.province "
     "ORDER BY SUM(cl.claim_amount) DESC, c.province LIMIT 1"),
    ("Which policy type has the highest average premium?",
     "SELECT policy_type, AVG(premium) FROM Policies GROUP BY policy_type "
     "ORDER BY AVG(premium) DESC, policy_type LIMIT 1"),
    ("Hello", None),
]


def tool_message(arguments, name="query_database"):
    return ChatCompletionMessage(role="assistant", tool_calls=[{
        "id": "call_test", "type": "function",
        "function": {"name": name, "arguments": arguments},
    }])


class AgentTests(unittest.TestCase):
    def test_invalid_tools_and_arguments(self):
        for arguments, name in [("{}", "python"), ("not JSON", "query_database"),
                                ('{"sql": 1}', "query_database"), ("[]", "query_database")]:
            with self.subTest(arguments=arguments, name=name), patch("backend.agent.query_database") as query:
                result = execute_tool_call(tool_message(arguments, name).tool_calls[0])
                self.assertIn("error", result["result"])
                query.assert_not_called()

    def test_destructive_sql_rejected_by_database(self):
        for sql in ["DELETE FROM Customers", "DROP TABLE Customers",
                    "UPDATE Customers SET age = 0", "INSERT INTO Customers DEFAULT VALUES",
                    "ALTER TABLE Customers ADD COLUMN demo TEXT", "CREATE TABLE demo (id INTEGER)"]:
            with self.subTest(sql=sql):
                result = execute_tool_call(tool_message(json.dumps({"sql": sql})).tool_calls[0])
                self.assertIn("error", result["result"])

    def test_native_tool_result_round_trip_and_greeting(self):
        first = tool_message('{"sql": "SELECT COUNT(*) FROM Customers"}')
        final = ChatCompletionMessage(role="assistant", content="There are 2 customers.")
        with patch("backend.agent.load_dotenv"), patch.dict(os.environ, {
            "GROQ_API_KEY": "test-placeholder", "GROQ_MODEL": "test-model"
        }), patch("backend.agent.Groq") as client, patch("backend.agent.query_database") as query:
            query.return_value = {"columns": ["COUNT(*)"], "rows": [[2]]}
            create = client.return_value.__enter__.return_value.chat.completions.create
            create.side_effect = [SimpleNamespace(choices=[SimpleNamespace(message=m)]) for m in (first, final)]
            result = ask_agent("Count customers")
            self.assertEqual(result["answer"], "There are 2 customers.")
            self.assertEqual(result["tool_results"][0]["result"], query.return_value)
            sent = create.call_args.kwargs["messages"][-1]
            self.assertEqual(sent["tool_call_id"], "call_test")
            self.assertEqual(json.loads(sent["content"]), query.return_value)
            query.assert_called_once_with("SELECT COUNT(*) FROM Customers")
            query.reset_mock()
            create.side_effect = [SimpleNamespace(choices=[SimpleNamespace(
                message=ChatCompletionMessage(role="assistant", content="Hello!"))])]
            result = ask_agent("Hello")
            self.assertIsNone(result["sql"])
            self.assertEqual(result["tool_results"], [])
            query.assert_not_called()

    def test_tool_errors_are_returned_and_loop_is_bounded(self):
        message = tool_message('{"sql": "DELETE FROM Customers"}')
        with patch("backend.agent.load_dotenv"), patch.dict(os.environ, {
            "GROQ_API_KEY": "test-placeholder", "GROQ_MODEL": "test-model"
        }), patch("backend.agent.Groq") as client:
            create = client.return_value.__enter__.return_value.chat.completions.create
            create.return_value = SimpleNamespace(choices=[SimpleNamespace(message=message)])
            with self.assertRaisesRegex(RuntimeError, "tool-call limit"):
                ask_agent("Delete customers")
            self.assertEqual(create.call_count, 4)
            self.assertEqual(create.call_args.kwargs["tool_choice"], "none")
            tool_results = [m for m in create.call_args.kwargs["messages"] if m["role"] == "tool"]
            self.assertEqual(len(tool_results), 3)
            for entry in tool_results:
                self.assertIn("error", json.loads(entry["content"]))


def run_live_tests() -> bool:
    """Print actual model SQL, executed results, and answers for each question."""
    passed = True
    for question, reference_sql in QUESTIONS:
        print(f"\nQuestion: {question}", flush=True)
        try:
            result = ask_agent(question)
        except (ValueError, RuntimeError) as error:
            print(f"Could not complete live test: {error}", flush=True)
            passed = False
            continue
        for entry in result["tool_results"]:
            print(f"SQL: {entry['sql']}")
            print(f"Database result: {json.dumps(entry['result'])}")
        if not result["tool_results"]:
            print("SQL: null\nDatabase result: none (no tool call)")
        print(f"Answer: {result['answer']}", flush=True)
        if reference_sql is None:
            matches = result["sql"] is None and not result["tool_results"]
        else:
            expected = query_database(reference_sql)
            # Compare values, not aliases; allow rounding in model-generated SQL.
            actual = result["tool_results"][-1]["result"] if result["tool_results"] else {}
            matches = "rows" in expected and "rows" in actual
            if matches:
                expected_rows, actual_rows = expected["rows"], actual["rows"]
                matches = len(expected_rows) == len(actual_rows)
                for wanted, got in zip(expected_rows, actual_rows):
                    matches = matches and len(wanted) == len(got)
                    for a, b in zip(wanted, got):
                        matches = matches and (abs(a - b) <= 0.01 if isinstance(a, (int, float))
                                               and isinstance(b, (int, float)) else a == b)
        print("PASS" if matches else "FAIL: Query result did not match the reference check.", flush=True)
        passed = passed and matches
    return passed


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(AgentTests)
    offline = unittest.TextTestRunner(verbosity=2).run(suite)
    if not offline.wasSuccessful():
        raise SystemExit(1)
    raise SystemExit(0 if run_live_tests() else 1)
