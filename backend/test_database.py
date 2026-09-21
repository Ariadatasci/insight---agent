"""Standard-library tests; temporary fixture records are not portfolio data."""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import database


QUERIES = [
    ("A. Count all customers", "SELECT COUNT(*) AS customer_count FROM Customers",
     {"columns": ["customer_count"], "rows": [[3]]}),
    ("B. City with the most customers",
     "SELECT city, COUNT(*) AS customer_count FROM Customers "
     "GROUP BY city ORDER BY customer_count DESC, city LIMIT 1",
     {"columns": ["city", "customer_count"], "rows": [["Durban", 2]]}),
    ("C. Average claim amount", "SELECT AVG(claim_amount) AS average_claim_amount FROM Claims",
     {"columns": ["average_claim_amount"], "rows": [[200.0]]}),
    ("D. Total claim amount by claim type",
     "SELECT claim_type, SUM(claim_amount) AS total_claim_amount FROM Claims "
     "GROUP BY claim_type ORDER BY claim_type",
     {"columns": ["claim_type", "total_claim_amount"],
      "rows": [["Accident", 400.0], ["Theft", 200.0]]}),
    ("E. Total claim amount by province",
     "SELECT c.province, SUM(cl.claim_amount) AS total_claim_amount "
     "FROM Customers AS c JOIN Claims AS cl ON c.customer_id = cl.customer_id "
     "GROUP BY c.province ORDER BY c.province",
     {"columns": ["province", "total_claim_amount"],
      "rows": [["Gauteng", 300.0], ["KwaZulu-Natal", 300.0]]}),
]


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_directory.cleanup)
        path = Path(self.temp_directory.name) / "insurance.db"
        connection = sqlite3.connect(path)
        try:
            connection.executescript("""
                CREATE TABLE Customers (
                    customer_id INTEGER PRIMARY KEY, first_name TEXT, last_name TEXT,
                    age INTEGER, gender TEXT, city TEXT, province TEXT
                );
                CREATE TABLE Policies (
                    policy_id INTEGER PRIMARY KEY,
                    customer_id INTEGER REFERENCES Customers(customer_id),
                    policy_type TEXT, premium REAL, coverage_amount REAL,
                    start_date TEXT, end_date TEXT
                );
                CREATE TABLE Claims (
                    claim_id INTEGER PRIMARY KEY,
                    policy_id INTEGER REFERENCES Policies(policy_id),
                    customer_id INTEGER REFERENCES Customers(customer_id),
                    claim_type TEXT, claim_amount REAL, claim_date TEXT, claim_status TEXT
                );
                INSERT INTO Customers VALUES
                    (1, 'Demo', 'One', 30, 'F', 'Durban', 'KwaZulu-Natal'),
                    (2, 'Demo', 'Two', 40, 'M', 'Durban', 'KwaZulu-Natal'),
                    (3, 'Demo', 'Three', 25, 'F', 'Johannesburg', 'Gauteng');
                INSERT INTO Policies VALUES
                    (1, 1, 'Motor', 100, 10000, '2025-01-01', '2026-01-01'),
                    (2, 3, 'Motor', 100, 10000, '2025-01-01', '2026-01-01');
                INSERT INTO Claims VALUES
                    (1, 1, 1, 'Accident', 100, '2025-02-01', 'Approved'),
                    (2, 1, 1, 'Theft', 200, '2025-03-01', 'Approved'),
                    (3, 2, 3, 'Accident', 300, '2025-04-01', 'Approved');
            """)
        finally:
            connection.close()
        self.path_patch = patch.object(database, "DATABASE_PATH", path)
        self.path_patch.start()
        self.addCleanup(self.path_patch.stop)

    def test_requested_queries(self):
        for label, sql, expected in QUERIES:
            with self.subTest(query=label):
                result = database.query_database(sql)
                self.assertEqual(result, expected)
                print(f"\n{label} (temporary fixture): {json.dumps(result)}")

    def test_delete_is_rejected(self):
        result = database.query_database("DELETE FROM Customers;")
        self.assertIn("error", result)
        self.assertEqual(database.query_database(QUERIES[0][1]), QUERIES[0][2])
        print(f"\nDELETE rejection: {json.dumps(result)}")

    def test_write_keywords_and_multiple_statements_are_rejected(self):
        for keyword in database.BLOCKED_KEYWORDS:
            with self.subTest(keyword=keyword):
                self.assertIn("error", database.query_database(f"SELECT 1; {keyword} Customers;"))
        self.assertIn("error", database.query_database("SELECT 1; SELECT 2;"))

    def test_comments_literals_and_empty_results(self):
        self.assertEqual(database.query_database("/* comment */ SELECT 'DELETE' AS word;"),
                         {"columns": ["word"], "rows": [["DELETE"]]})
        self.assertEqual(database.query_database("SELECT city FROM Customers WHERE 1 = 0"),
                         {"columns": ["city"], "rows": []})

    def test_errors_are_understandable(self):
        for sql in ("", "-- comment only", "SELECT missing FROM Customers", "SELECT FROM"):
            with self.subTest(sql=sql):
                self.assertIn("error", database.query_database(sql))
        missing = Path(self.temp_directory.name) / "missing.db"
        with patch.object(database, "DATABASE_PATH", missing):
            self.assertIn("Database not found", database.query_database("SELECT 1")["error"])
        self.assertFalse(missing.exists())

    def test_sqlite_guards_independently_block_writes(self):
        # Bypass text validation to verify the SQLite authorizer still blocks DELETE.
        with patch.object(database, "validate_sql"):
            self.assertIn("error", database.query_database("DELETE FROM Customers"))
        connection = sqlite3.connect(database.DATABASE_PATH.as_uri() + "?mode=ro", uri=True)
        try:
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute("DELETE FROM Customers")
        finally:
            connection.close()


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(DatabaseTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
    if database.DATABASE_PATH.is_file():
        print("\nResults from your insurance.db:")
        for label, sql, _ in QUERIES:
            output = database.query_database(sql)
            print(f"{label}: {json.dumps(output)}")
            if "error" in output:
                raise SystemExit(1)
    else:
        print(f"\nYour insurance.db was not found at {database.DATABASE_PATH}.")
        print("All tests above used a temporary synthetic fixture, removed after testing.")
