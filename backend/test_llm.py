"""Run explicitly with python -m backend.test_llm to make one live API request."""

from backend.llm import ask_llm


def main() -> int:
    """Print the response and report whether it matches the requested phrase."""
    try:
        response = ask_llm("Reply with exactly: Insight Agent connected")
    except (ValueError, RuntimeError) as error:
        print(f"LLM test could not complete: {error}")
        return 1

    print(response)
    if response.strip() != "Insight Agent connected":
        print("FAIL: The response did not match the requested phrase.")
        return 1
    print("PASS: Groq connection verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
