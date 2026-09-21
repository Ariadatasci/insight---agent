"""Run read-only SELECT queries against the portfolio database."""

import re
import sqlite3
from pathlib import Path


DATABASE_PATH = Path(__file__).resolve().parent / "data" / "insurance.db"

BLOCKED_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "REPLACE",
    "TRUNCATE", "ATTACH", "DETACH", "PRAGMA",
}

# Match comments and quoted values/identifiers before matching SQL words.
# This avoids treating text such as 'Please DELETE this' as a SQL operation.
SQL_TOKENS = re.compile(
    r"--[^\n]*|/\*[\s\S]*?\*/|'(?:''|[^'])*'|"
    r'"(?:""|[^"])*"|`(?:``|[^`])*`|\[[^\]]*\]|'
    r"[A-Za-z_][A-Za-z_0-9]*|[^\s]"
)


def validate_sql(sql: str) -> None:
    """Reject empty SQL, non-SELECT statements, and write-related keywords."""
    if not isinstance(sql, str) or not sql.strip():
        raise ValueError("Provide a non-empty SQL SELECT query.")

    tokens = [
        token for token in SQL_TOKENS.findall(sql)
        if not token.startswith(("--", "/*"))
    ]
    if not tokens or tokens[0].upper() != "SELECT":
        raise ValueError("Only SELECT statements are permitted.")

    for token in tokens:
        if token.upper() in BLOCKED_KEYWORDS:
            raise ValueError(f"SQL operation {token.upper()} is not permitted.")


def authorize_read_only(action, argument1, argument2, database_name, trigger_name):
    """Let SQLite allow only SELECT, table reads, and ordinary functions."""
    if action == sqlite3.SQLITE_FUNCTION:
        if (argument2 or "").lower() == "load_extension":
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ):
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def query_database(sql: str) -> dict:
    """Return {columns, rows} on success or {error} on failure.

    Accept one SELECT statement. SQLite's execute() rejects multiple statements.
    WITH queries are intentionally outside this small demo's supported SQL.
    """
    try:
        validate_sql(sql)
        if not DATABASE_PATH.is_file():
            return {"error": f"Database not found. Place insurance.db at: {DATABASE_PATH}"}

        # A URI handles spaces in paths; mode=ro prevents writes and file creation.
        connection = sqlite3.connect(DATABASE_PATH.as_uri() + "?mode=ro", uri=True)
        try:
            connection.set_authorizer(authorize_read_only)
            cursor = connection.execute(sql)
            return {
                "columns": [column[0] for column in cursor.description],
                "rows": [list(row) for row in cursor.fetchall()],
            }
        finally:
            # A sqlite3 connection context manager alone does not close it.
            connection.close()
    except ValueError as error:
        return {"error": str(error)}
    except sqlite3.Error as error:
        return {"error": f"Database query failed: {error}"}
