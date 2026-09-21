"""Send a single message to Groq, without SQL tools or conversation history."""

import os
from pathlib import Path

from dotenv import load_dotenv
from groq import APIConnectionError, APIError, AuthenticationError, Groq, RateLimitError


ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def ask_llm(message: str) -> str:
    """Return Groq's text response, or raise an understandable, safe error."""
    if not isinstance(message, str) or not message.strip():
        raise ValueError("Provide a non-empty message.")

    # Resolve .env relative to this file, not the terminal's working directory.
    # Existing environment variables take priority over values in .env.
    load_dotenv(ENV_PATH)
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    model = os.getenv("GROQ_MODEL", "").strip()
    if not api_key:
        raise ValueError("Missing GROQ_API_KEY. Set it in insight-agent/.env.")
    if not model:
        raise ValueError("Missing GROQ_MODEL. Set it in insight-agent/.env; see .env.example.")

    try:
        # The context manager closes the client's network connections.
        with Groq(api_key=api_key, timeout=30.0, max_retries=0) as client:
            completion = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": message}],
            )
    except AuthenticationError:
        raise RuntimeError("Groq authentication failed. Check GROQ_API_KEY.") from None
    except RateLimitError:
        raise RuntimeError("Groq rate limit reached. Try again later.") from None
    except APIConnectionError:
        raise RuntimeError("Could not connect to Groq. Check your network and try again.") from None
    except APIError:
        # Never include the raw SDK exception or response body in our error.
        raise RuntimeError("Groq request failed. Check GROQ_MODEL and your Groq account.") from None
    except Exception:
        raise RuntimeError("Unable to initialize or use Groq. Check your configuration.") from None

    if not completion.choices or not completion.choices[0].message.content:
        raise RuntimeError("Groq returned no text response. Try again.")
    return completion.choices[0].message.content
