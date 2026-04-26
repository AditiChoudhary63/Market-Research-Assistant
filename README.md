# Market Intelligence Platform

A lightweight web application that helps Product and GTM teams stay current on competitor activity and market trends by collecting, analysing, and summarising intelligence from multiple public sources.

---

## Problem Statement

Product and GTM teams struggle to stay current on competitor activity and market trends because relevant information is scattered across blogs, websites, announcements, and articles. This platform automates the collection and analysis of that information, producing structured, source-grounded intelligence reports with built-in hallucination detection.

---

## Architecture & Tech Stack

```
┌─────────────────────────────────────────────────────────────┐
│                        Browser (UI)                         │
│              HTML/JS served from ui.py via FastAPI          │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP (JWT Bearer)
┌────────────────────────▼────────────────────────────────────┐
│                      api.py  (FastAPI)                       │
│  POST /research          → full pipeline (JSON response)    │
│  POST /research/stream   → SSE streaming (tokens + status)  │
│  GET  /history           → previous runs                    │
│  POST /auth/login        → JWT token                        │
│  GET  /                  → HTML UI                          │
└──────────┬──────────────────────────────┬───────────────────┘
           │                              │
┌──────────▼──────────┐       ┌───────────▼──────────┐
│     graph.py        │       │      MongoDB           │
│   LangGraph DAG     │       │  (research_runs)       │
│                     │       └───────────────────────┘
│  1. tavily_search   │
│  2. html_loader     │
│  3. embedding       │──────► Pinecone (vector store)
│  4. llm_invoke      │◄────── OpenAI (configurable model)
│  5. validation ─────┼──────► OpenAI (configurable judge)
│     └─ retry loop   │
└─────────────────────┘
```

### Tech Stack

| Layer | Technology |
|---|---|
| **Web framework** | FastAPI + Uvicorn |
| **Frontend** | Vanilla JS + Tailwind CSS (CDN) + Marked.js |
| **Orchestration** | LangGraph (stateful DAG with conditional retry edge) |
| **LLM** | OpenAI (model configurable via `LLM_MODEL` env var, default `gpt-4o-mini`) |
| **Judge LLM** | OpenAI (model configurable via `JUDGE_MODEL` env var, default `gpt-4o`) |
| **Embeddings** | OpenAI `text-embedding-ada-002` |
| **Vector store** | Pinecone (serverless, per-run namespace isolation) |
| **Web search** | Tavily Search API (`langchain-tavily`) |
| **HTML parsing** | AsyncHtmlLoader + Html2TextTransformer (LangChain Community) |
| **Chunking** | LangChain `SemanticChunker` (langchain-experimental) |
| **Persistence** | MongoDB via Motor (async driver) |
| **Auth** | JWT (python-jose) with OAuth2 password flow |
| **Observability** | LangSmith tracing |
| **Package manager** | uv |
| **Python** | 3.14 |

---

## Project Structure

```
ai-assessment/
├── main.py          # Entry point — starts uvicorn
├── api.py           # FastAPI app: endpoints, auth, MongoDB logic
├── ui.py            # Embedded single-page HTML/JS frontend
├── graph.py         # LangGraph 5-node pipeline
├── prompts.py       # All LLM prompts (analyst + judge)
├── config.py        # Pydantic settings loaded from .env
├── requirements.txt # Python dependencies
├── Dockerfile       # Container build definition
├── .env             # Local secrets (not committed)
├── .env.example     # Template for required env vars
└── .gitignore
```

---

## Pipeline — Node by Node

The research pipeline is a LangGraph directed acyclic graph (DAG) with a conditional retry loop.

```
tavily_search → html_loader → embedding → llm_invoke → validation
                                               ▲              │
                                               └── (retry) ───┘
                                                              │
                                                           [END]
```

### Node 1 — `tavily_search`
Queries the Tavily Search API for each competitor with a prompt focused on latest news, product launches, and market strategy. Extracts and deduplicates URLs from the response and stores them as `tavily_urls` in state.

### Node 2 — `html_loader`
Merges Tavily-discovered URLs with the user-supplied source URLs, fetches HTML concurrently using `AsyncHtmlLoader`, and converts the raw HTML to plain text via `Html2TextTransformer`.

### Node 3 — `embedding`
Chunks all loaded documents using LangChain's `SemanticChunker` (`langchain-experimental`), which groups sentences by semantic similarity rather than fixed character counts. Embeddings are generated via OpenAI and upserted into Pinecone under a unique per-run namespace to prevent data mixing between concurrent requests. Raises a `RuntimeError` only if HTML content is empty.

### Node 4 — `llm_invoke`
Uses **multi-query retrieval** — four intent-specific queries are issued against Pinecone (k=3 each), and results are deduplicated by content fingerprint, yielding up to 12 unique chunks covering:
- Product launches, updates, announcements
- Partnerships, acquisitions, collaborations
- Strategy, market positioning, growth plans
- Industry trends, competitor analysis, innovation

This replaces the previous single generic query and provides broader, more semantically diverse context. The LLM (configurable via `LLM_MODEL`) then produces a structured report with three mandatory sections:

- **Key Themes & Market Trends**
- **Notable Competitor Activities**
- **Source References**

On retries, the prompt is augmented with the list of hallucinated claims flagged in the previous validation pass.

### Node 5 — `validation` (LLM-as-Judge)
Sends the generated report to the judge LLM (configurable via `JUDGE_MODEL`) for hallucination detection. The judge evaluates grounding, citation accuracy, and completeness, returning a JSON verdict with `is_valid`, `score` (1–10), `reasoning`, `hallucinated_claims`, and `improvements`.

### Conditional Retry Edge
After validation, a routing function reads `retry_count` (incremented inside `validation_node`) and routes back to `llm_invoke` if hallucinations are found and `retry_count ≤ MAX_RETRIES`. Otherwise routes to `END`. `MAX_RETRIES` defaults to `2` and is configurable via `.env`.

---

## Streaming

The platform supports real-time SSE (Server-Sent Events) streaming via `POST /research/stream`. The UI uses this endpoint by default and shows:

- **Per-node status rows** — each pipeline step appears with a spinner while running and a green tick on completion, with a contextual message (e.g. "Found 12 source URLs from competitor research").
- **Live report panel** — LLM output tokens stream word-by-word into the UI as the report is generated, before the final formatted card is shown.
- **Retry banners** — when the validator rejects a response and triggers a retry, an amber "Generating improved response (attempt N)..." banner appears.

### SSE Event Types

| Event type | When emitted | Payload |
|---|---|---|
| `status` | Node starts or finishes | `node`, `phase` (`start`\|`end`), `message` |
| `token` | Each LLM output token | `content` |
| `retry` | `llm_invoke` re-runs after failed validation | `attempt`, `message` |
| `complete` | Pipeline finished and saved | `result` (full response object) |
| `error` | Any exception | `message` |

---

## Local Build & Run Instructions

### Prerequisites
- Python 3.14
- [uv](https://github.com/astral-sh/uv) package manager
- MongoDB running locally (`mongodb://localhost:27017`) or a MongoDB Atlas URI
- API keys for OpenAI, Tavily, Pinecone, and LangSmith (see `.env.example`)

### Step 1 — Clone the repository

```bash
git clone <repository-url>
cd ai-assessment
```

### Step 2 — Create and activate a virtual environment

```bash
uv venv --python 3.14
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

### Step 3 — Install dependencies

```bash
uv sync
```

> `uv sync` reads `pyproject.toml` (the source of truth for this project), resolves all dependencies, and installs them into the virtual environment. A `uv.lock` lockfile is created on first run and committed to pin exact versions. Use `uv sync --frozen` in CI/Docker to fail fast if the lockfile is out of date.

### Step 4 — Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in your API keys:

```env
# Required
OPENAI_API_KEY=sk-proj-...
TAVILY_API_KEY=tvly-...
PINECONE_API_KEY=pcsk_...

# Pinecone index config
PINECONE_INDEX=market-intelligence
PINECONE_CLOUD=aws
PINECONE_REGION=us-east-1
EMBEDDING_DIM=1536

# LLM models (optional — these are the defaults)
LLM_MODEL=gpt-4o-mini
JUDGE_MODEL=gpt-4o

# Pipeline config
MAX_RETRIES=2

# MongoDB
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB=market_research

# Auth
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-password
SECRET_KEY=a-long-random-secret
ACCESS_TOKEN_EXPIRE_MINUTES=60

# LangSmith (optional but recommended)
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_pt_...
LANGSMITH_PROJECT=market-intelligence
```

### Step 5 — Start the application

```bash
python main.py
```

The server starts at **http://localhost:8000**.

Alternatively, with auto-reload for development:

```bash
uvicorn api:app --reload
```

### Step 6 — Open the UI

Navigate to **http://localhost:8000** in your browser. You will be prompted to sign in with the credentials set in `ADMIN_USERNAME` / `ADMIN_PASSWORD`.

---

## Using the Application

1. **Sign in** using your configured admin credentials.
2. **Enter competitors** — one name or topic per line (e.g. `OpenAI`, `Anthropic`). Values with or without surrounding quotes are accepted.
3. **Enter source URLs** — one URL per line (blogs, announcement pages, news articles).
4. **Click "Generate Report"** — the pipeline runs and streams progress in real time:
   - Each node's status appears as it executes.
   - The report streams word-by-word while the LLM generates it.
   - If a retry is triggered, an amber banner appears.
5. **Review the results**:
   - Validation badge and score (colour-coded 1–10)
   - Flagged hallucinated claims (if any)
   - Suggested improvements
   - Full intelligence report (Key Themes, Competitor Activities, Source References)
   - All source URLs analysed
6. **History** — previous runs appear in the sidebar. Click any entry to reload its inputs and results.

---

## API Reference

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/` | — | Serves the HTML UI |
| `POST` | `/auth/login` | — | Returns a JWT bearer token |
| `POST` | `/research` | Bearer | Runs the full pipeline; returns JSON when complete |
| `POST` | `/research/stream` | Bearer | Runs the pipeline; streams SSE events (tokens + node status) |
| `GET` | `/history` | Bearer | Lists the 20 most recent runs |
| `GET` | `/history/{id}` | Bearer | Returns full detail of a single run |
| `GET` | `/docs` | — | Interactive Swagger UI |

### Authentication

All `/research` and `/history` endpoints require a `Bearer` token obtained from `/auth/login`:

```bash
# 1. Get a token
curl -X POST http://localhost:8000/auth/login \
  -d "username=admin&password=admin123"

# 2. Use the token
curl -X POST http://localhost:8000/research \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"competitors": ["OpenAI", "Anthropic"], "urls": ["https://openai.com/blog"]}'
```

---

## AI Tools / Models / Libraries Used

| Tool / Library | Role | Reference |
|---|---|---|
| **OpenAI GPT-4o-mini** | Market intelligence report generation (default, configurable) | [openai.com](https://openai.com) |
| **OpenAI GPT-4o** | LLM-as-judge hallucination detection (default, configurable) | [openai.com](https://openai.com) |
| **OpenAI text-embedding-ada-002** | Document embedding | [openai.com/docs/guides/embeddings](https://platform.openai.com/docs/guides/embeddings) |
| **LangGraph** | Stateful pipeline orchestration with conditional retry loop + `astream_events` for SSE streaming | [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) |
| **LangChain** | Document loaders, text splitters, prompt building, callback system | [python.langchain.com](https://python.langchain.com) |
| **langchain-tavily** | Tavily Search tool integration | [pypi: langchain-tavily](https://pypi.org/project/langchain-tavily/) |
| **langchain-pinecone** | Pinecone vector store integration | [pypi: langchain-pinecone](https://pypi.org/project/langchain-pinecone/) |
| **Pinecone** | Serverless vector database for semantic retrieval | [pinecone.io](https://www.pinecone.io) |
| **Tavily** | Real-time web search API | [tavily.com](https://tavily.com) |
| **LangSmith** | LLM observability and trace logging | [smith.langchain.com](https://smith.langchain.com) |
| **FastAPI** | REST API framework with `StreamingResponse` for SSE | [fastapi.tiangolo.com](https://fastapi.tiangolo.com) |
| **Motor** | Async MongoDB driver | [motor.readthedocs.io](https://motor.readthedocs.io) |
| **python-jose** | JWT token encoding / decoding | [pypi: python-jose](https://pypi.org/project/python-jose/) |
| **Marked.js** | Client-side Markdown rendering | [marked.js.org](https://marked.js.org) |
| **Tailwind CSS** | Utility-first CSS framework (CDN) | [tailwindcss.com](https://tailwindcss.com) |

---

## Design Decisions

### LangGraph over a simple chain
LangGraph's stateful graph model was chosen because the retry loop (re-invoking the LLM when hallucinations are detected) requires shared mutable state across nodes. A simple LangChain chain cannot loop back; LangGraph's conditional edges handle this cleanly.

### SSE streaming via `astream_events`
LangGraph's `astream_events` (v2) is used for the streaming endpoint. It emits fine-grained events for every node start/end and every LLM token without requiring any changes to the graph nodes themselves. The async generator is consumed directly by FastAPI's `StreamingResponse`, keeping the streaming path clean and lightweight.

### Semantic chunking over fixed-size splitting
Documents are chunked using LangChain's `SemanticChunker`, which groups sentences by embedding similarity rather than arbitrary character counts. This produces more coherent chunks that align with topic boundaries, improving retrieval quality in the vector store.

### Multi-query retrieval in Node 4
Instead of a single generic similarity query, Node 4 issues four intent-specific queries (product launches, partnerships, strategy, trends) and deduplicates results by content fingerprint. This improves semantic coverage and ensures the LLM receives diverse, relevant context across all dimensions of competitive intelligence.

### LLM and judge models in `.env`
Both `LLM_MODEL` (report generation) and `JUDGE_MODEL` (hallucination judge) are read from environment variables, defaulting to `gpt-4o-mini` and `gpt-4o` respectively. This allows model swapping without any code changes.

### LLM-as-Judge for hallucination detection
Rather than rule-based citation checking, a separate judge LLM evaluates every factual claim against its cited source. This catches subtle extrapolations and missing citations that pattern matching would miss. The judge's output is structured JSON, making it machine-readable for the retry routing function.

### Retry counter in state, not in the router
LangGraph routing functions are pure — they only return a node name and cannot persist state changes. The `retry_count` is therefore incremented inside `validation_node` (a proper state-returning node) before the router reads it.

### Per-run Pinecone namespaces
Each pipeline invocation writes to a unique UUID-based namespace in Pinecone. This prevents documents from different concurrent requests from polluting each other's retrieval context without requiring index deletion between runs.

### Input sanitisation at two layers
Surrounding quotes, commas, and whitespace are stripped from competitor names and URLs both in the JavaScript frontend (before the API call) and in the FastAPI `ResearchRequest` Pydantic validator (server-side). This prevents malformed inputs — such as values pasted from JSON — from reaching the pipeline.

### Embedded HTML in `ui.py`
No template engine or static file server is needed. The entire UI is a single HTML string exported from `ui.py` and served by FastAPI's `HTMLResponse`. This keeps deployment simple (one process, no static file directory to configure).

### MongoDB for persistence
Every completed research run is saved verbatim (inputs, summary, validation result, timestamps) so users can revisit and compare past analyses without re-running the expensive pipeline.

---

## Deployment (Azure — recommended)

1. **Containerise** — add a `Dockerfile` using a Python 3.14 slim base image.
2. **Azure Container Apps** — deploy the container image; set all `.env` variables as Application Settings.
3. **MongoDB** — use Azure Cosmos DB for MongoDB API or MongoDB Atlas.
4. **Pinecone** — the serverless index works across any cloud; no infrastructure changes needed.
5. **Domain / TLS** — Azure Container Apps provides a managed HTTPS endpoint automatically.

---

## Monitoring & Observability

- **LangSmith** — every pipeline run is traced with `run_name`, `tags`, and `metadata` (competitors, retry attempt, context chunk count). View traces at [smith.langchain.com](https://smith.langchain.com).
- **Pipeline log** — `pipeline.log` captures all `INFO`/`ERROR` events from every node at runtime.
- **FastAPI `/docs`** — interactive Swagger UI available at `/docs` for API exploration and manual testing.
