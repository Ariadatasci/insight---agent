"""A small HTTP API for the existing Insight Agent."""

import logging
import os
import re

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from backend.agent import ask_agent


class _RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        # Redact after formatting so exception chains and traceback text are covered.
        values = {
            value for name, value in os.environ.items()
            if len(value) >= 4 or re.search(
                r"(?i)key|token|secret|password|credential", name
            )
        }
        for value in sorted(values, key=len, reverse=True):
            if value:
                text = text.replace(value, "[REDACTED]")
        text = re.sub(
            r"(?im)(\b[\w-]*(?:api[_-]?key|token|secret|password|credential|authorization|cookie)"
            r"[\w-]*[\"']?\s*[:=]\s*).*$",
            r"\1[REDACTED]", text,
        )
        text = re.sub(r"(?i)\b(Bearer|Basic)\s+\S+", r"\1 [REDACTED]", text)
        return re.sub(r"(https?://)[^\s/@]+:[^\s/@]+@", r"\1[REDACTED]@", text)


logger = logging.getLogger(__name__)
_log_handler = logging.StreamHandler()
_log_handler.setFormatter(_RedactingFormatter("%(levelname)s %(name)s: %(message)s"))
logger.addHandler(_log_handler)
logger.setLevel(logging.ERROR)
# Prevent ancestor handlers from emitting an unredacted copy of the exception.
logger.propagate = False


app = FastAPI(title="Insight Agent")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://insight-agent-seven.vercel.app",
    ],
    allow_origin_regex=r"^https://insight-agent-[a-z0-9]+(?:-[a-z0-9]+)*-aria-fab5\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str = Field(min_length=1)

    @field_validator("question")
    @classmethod
    def reject_empty_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Please enter a non-empty question.")
        return value


class AskResponse(BaseModel):
    answer: str
    sql: str | None = None
    sources: list[str] = Field(default_factory=list)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "online"}


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    # A synchronous endpoint lets FastAPI run the blocking agent in a worker thread.
    try:
        result = ask_agent(request.question)
        return AskResponse(
            answer=result["answer"],
            sql=result.get("sql"),
            sources=result.get("sources", []),
        )
    except Exception:
        logger.exception("Failed to process /ask request")
        # Never send exception text, configuration, or tool traces to the client.
        raise HTTPException(
            status_code=500,
            detail="The agent could not complete your question. Please try again later.",
        ) from None
