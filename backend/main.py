"""A small HTTP API for the existing Insight Agent."""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from backend.agent import ask_agent


app = FastAPI(title="Insight Agent")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://insight-agent-seven.vercel.app",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
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
        # Never send exception text, configuration, or tool traces to the client.
        raise HTTPException(
            status_code=500,
            detail="The agent could not complete your question. Please try again later.",
        ) from None
