# Insight Agent

An AI insurance data assistant that connects business questions to structured
records and supporting policy documents.

## Problem

Business users often need SQL knowledge to retrieve information from relational
databases, while interpreting that data can require business-specific knowledge
stored in separate documents.

## Solution

Insight Agent allows users to ask natural-language questions and combines LLM
tool calling, SQL querying and retrieval-augmented generation to answer using
both structured insurance data and business documentation.

The agent uses SQL for data questions, retrieval for business rules, and both
when a calculation depends on a document-defined term. The interface shows the
answer, the SQL used, and retrieved source filenames.

## Architecture

```text
             User
               ↓
             React
               ↓
            FastAPI
               ↓
           LLM Agent
           ↙       ↘
         RAG      SQL Tool
          ↓          ↓
         PDFs     SQLite
```

FastAPI calls the existing Python agent through `POST /ask`. Groq's native
function calling selects between `retrieve_context` and `query_database`.
Sentence Transformers embeds PDF text locally, and FAISS retrieves relevant
chunks. SQLite executes permitted queries. Tool results return to the LLM to
produce the final answer; no orchestration framework is required.

## Features

- Natural-language querying
- Native LLM tool calling
- Read-only SQL execution
- RAG over insurance documents
- Combined RAG + SQL reasoning
- Source transparency
- SQL transparency
- Responsive React interface

## Example

**Question:** How many high-value claims are in the database?

1. RAG retrieves the business definition: high-value means a claim amount
   **above R50,000**.
2. The agent uses the SQL tool with that definition.
3. SQL queries `Claims WHERE claim_amount > 50000`:

   ```sql
   SELECT COUNT(*) AS high_value_claims
   FROM Claims
   WHERE claim_amount > 50000;
   ```

4. SQLite returns **487** for the supplied demonstration dataset.
5. The LLM produces the final answer, explaining the count and the supporting
   rule. The interface exposes the SQL and retrieved PDF filenames.

## Tech Stack

- Python
- FastAPI
- SQLite
- Groq
- LLM tool/function calling
- Sentence Transformers
- FAISS
- pypdf
- React
- Vite

## Data

All insurance data and business documents are **synthetic and created solely
for demonstration**. They are not real customer records or actual insurance
policies.

The included `backend/data/insurance.db` contains 500 customers, 750 policies,
and 1,500 claims. The four PDFs in `knowledge/` cover claims policy,
underwriting guidelines, products, and claims procedures. Sidebar record counts
describe this supplied dataset.

## Running Locally

Use Python 3.11 and Node.js 22 or newer with npm. Run the following commands in
PowerShell from the `insight-agent` project folder.

**Backend setup**

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

For an existing installation, keep your current environment and `.env`; do not
overwrite them. Set `GROQ_API_KEY` privately in `.env`. Keep `GROQ_MODEL` set to
a tool-calling model available in your Groq account. The example file includes
a model setting and an empty key field. Existing environment variables take
priority over `.env`.

The application resolves the database, documents, and backend `.env` relative
to the project files, rather than a machine-specific absolute path. The first
RAG request may download `all-MiniLM-L6-v2`; allow internet access for that initial
download. Its weights are cached in `.cache/sentence_transformers/`, and the
generated index is stored in `backend/data/rag_index/`. Retain these caches for
offline retrieval. PDFs must contain extractable text; OCR is not included.

Start FastAPI:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

In another terminal, verify readiness without calling Groq:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Expected response: `{"status":"online"}`. This checks the API process, not
provider availability. `POST /ask` accepts `{"question":"Your question"}` and
returns `answer`, `sql` (null when unused), and `sources` (empty when unused).

**Frontend setup**

In a second PowerShell terminal, from `insight-agent`:

```powershell
cd frontend
Copy-Item .env.example .env
npm.cmd ci
npm.cmd run dev
```

The frontend `.env` contains:

```dotenv
VITE_API_URL=http://localhost:8000
```

Open **http://127.0.0.1:5173**. Restart Vite after changing the API URL. Both
`http://localhost:5173` and `http://127.0.0.1:5173` are allowed by the existing
backend CORS configuration. Vite variables are public build-time settings;
never place an API key in them.

Build the frontend from `frontend`:

```powershell
npm.cmd run build
```

Output is generated in `frontend/dist/`. Dependencies and build output are
ignored; `package-lock.json` is retained for reproducible frontend installation.
Portable Node files in `.cache/` are local development tools and are not required
when Node is installed normally.

**Offline verification**

From `insight-agent`, with the embedding model already cached:

```powershell
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
.\.venv\Scripts\python.exe -m unittest backend.test_database backend.test_agent backend.test_integration backend.test_api -v
.\.venv\Scripts\python.exe -m backend.test_rag
Remove-Item Env:HF_HUB_OFFLINE, Env:TRANSFORMERS_OFFLINE
```

These commands test SQL safety, scripted agent replies, real local retrieval,
integration, and the API without Groq requests. The separate `backend.test_llm`
script and direct execution of `backend.test_agent` or `backend.test_integration`
include live Groq calls; they are not needed for routine offline checks.

## Security

- **Environment variables:** backend credentials stay in the local environment
  or ignored `.env` files. `.env.*` variants are also ignored; only the safe
  `.env.example` templates are included. Keys are not sent to the frontend or
  intentionally logged.
- **Read-only SQL controls:** queries must be single `SELECT` statements. SQLite
  opens the database with `mode=ro`, and an authorizer permits reads while
  blocking write operations and extension loading. `WITH` statements are outside
  this demo's supported query syntax.
- **Destructive statement rejection:** operations such as `INSERT`, `UPDATE`,
  `DELETE`, `DROP`, and `ALTER` are rejected. SQLite provides independent
  protection even if SQL text validation is bypassed.
- **API error handling:** blank questions receive HTTP 422. Agent execution
  exceptions receive a fixed HTTP 500 message without stack traces, credentials,
  or raw exception details. The frontend also uses safe error messages and
  renders answer text without interpreting arbitrary HTML.
- **Synthetic data:** only demonstration records and documents are included.
  Relevant retrieved text and SQL results are sent to Groq as tool evidence.

This is a local portfolio demonstration. Authentication and deployment controls
are outside its scope. Git ignore rules do not remove secrets from earlier
commits; repository history must be checked separately before publication.
