"""Print actual PDF retrieval results without asking an LLM to answer."""

from backend.rag import retrieve_context


QUESTIONS = [
    "What is considered a high-value claim?",
    "When does a claim require high-risk review?",
    "How long does a customer normally have to submit a claim?",
    "What happens when a customer has three or more claims within 12 months?",
]

# These checks come from reading the supplied PDFs, not from an LLM answer.
EXPECTED_EVIDENCE = [
    ("01_claims_policy.pdf", ("above R50,000", "high-value")),
    ("02_underwriting_guidelines.pdf", ("above R100,000", "high-risk review")),
    ("01_claims_policy.pdf", ("within 30 calendar days",)),
    ("01_claims_policy.pdf", ("three or more claims", "12-month", "additional review")),
]


def main() -> int:
    failed = False
    for question, (expected_source, phrases) in zip(QUESTIONS, EXPECTED_EVIDENCE):
        print(f"\nQUESTION: {question}", flush=True)
        try:
            chunks = retrieve_context(question)
            if not chunks:
                raise ValueError("No chunks retrieved.")
            for number, chunk in enumerate(chunks, start=1):
                print(f"\nRETRIEVED TEXT {number}: {chunk['text']}")
                print(f"SOURCE DOCUMENT: {chunk['source']} (page {chunk['page']})", flush=True)
            relevant = any(
                chunk["source"] == expected_source
                and all(phrase.lower() in chunk["text"].lower() for phrase in phrases)
                for chunk in chunks
            )
            if not relevant:
                raise ValueError("Expected source and rule were not found together in the top three chunks.")
            print("PASS: Expected document rule appears in the retrieved chunks.", flush=True)
        except Exception as error:
            print(f"RETRIEVAL FAILED: {error}", flush=True)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
