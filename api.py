"""
Market Intelligence — FastAPI Application
  - GET  /              → HTML UI (loaded from ui.py)
  - POST /auth/login    → JWT token
  - POST /research      → run pipeline + save to MongoDB  (auth required)
  - GET  /history       → list of previous runs           (auth required)
  - GET  /history/{id}  → full detail of a single run     (auth required)
"""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional

import motor.motor_asyncio
from bson import ObjectId
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel, field_validator

from graph import LANGSMITH_PROJECT, GraphState, build_graph
from ui import HTML_UI

logger = logging.getLogger("market_intelligence")

from config import settings

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SECRET_KEY = settings.JWT_SECRET
ALGORITHM = settings.JWT_ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES
MONGODB_URI = settings.MONGODB_URI
MONGODB_DB_NAME = "market_research"

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def _create_access_token(
    subject: str, expires_delta: Optional[timedelta] = None
) -> str:
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=15))
    return jwt.encode({"sub": subject, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if not username:
            raise exc
        return username
    except JWTError:
        raise exc


# ---------------------------------------------------------------------------
# Globals set in lifespan
# ---------------------------------------------------------------------------

_mongo_client: motor.motor_asyncio.AsyncIOMotorClient = None
_db = None
_graph = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _mongo_client, _db, _graph

    _mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URI)
    _db = _mongo_client[MONGODB_DB_NAME]
    logger.info("MongoDB connected | uri=%s db=%s", MONGODB_URI, MONGODB_DB_NAME)

    # Move Pinecone Index Creation here to avoid blocking requests
    try:
        from pinecone import PineconeAsyncio, ServerlessSpec

        pc = PineconeAsyncio(api_key=settings.PINECONE_API_KEY)
        indexes = await pc.list_indexes()
        index_names = [i["name"] for i in indexes.get("indexes", [])]
        if "market-intelligence" not in index_names:
            logger.info("Creating Pinecone index 'market-intelligence'...")
            await pc.create_index(
                name="market-intelligence",
                dimension=1536,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            )
            logger.info("Index created.")
    except Exception as e:
        logger.error("Failed to initialize Pinecone: %s", e)
        raise e

    _graph = build_graph()
    yield
    _mongo_client.close()
    logger.info("MongoDB connection closed")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Market Intelligence API",
    description="Collect, analyse, and summarise market intelligence from public sources.",
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class TokenResponse(BaseModel):
    access_token: str
    token_type: str


def _strip_quotes(value: str) -> str:
    return value.strip().strip("\"'")


class ResearchRequest(BaseModel):
    competitors: list[str]
    urls: list[str]

    @field_validator("competitors", "urls", mode="before")
    @classmethod
    def strip_surrounding_quotes(cls, values: list) -> list:
        return [_strip_quotes(str(v)) for v in values if str(v).strip().strip("\"'")]


class ClaimAnalysis(BaseModel):
    claim: str
    status: str  # SUPPORTED | NOT_SUPPORTED | PARTIALLY_SUPPORTED
    evidence: str
    source: str


class ValidationResult(BaseModel):
    is_valid: bool
    quality: str = "low"
    summary: str = ""
    reasoning: str = ""  # kept for backward compat with older MongoDB records
    claim_analysis: list[ClaimAnalysis] = []
    hallucinated_claims: list[str] = []
    improvements: list[str] = []


class ResearchResponse(BaseModel):
    id: str
    competitors: list[str]
    urls: list[str]
    tavily_urls: list[str]
    summary: str
    validation: ValidationResult
    is_valid: bool
    created_at: str


class HistoryItem(BaseModel):
    id: str
    competitors: list[str]
    is_valid: bool
    quality: str = "low"
    created_at: str


# ---------------------------------------------------------------------------
# Endpoints — UI
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def serve_ui():
    return HTMLResponse(content=HTML_UI)


# ---------------------------------------------------------------------------
# Endpoints — Auth
# ---------------------------------------------------------------------------


@app.post("/auth/login", response_model=TokenResponse, tags=["Auth"])
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Authenticate with username and password; returns a JWT bearer token."""
    if (
        form_data.username != settings.ADMIN_USERNAME
        or form_data.password != settings.ADMIN_PASSWORD
    ):
        logger.warning("Failed login attempt | user=%s", form_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = _create_access_token(
        subject=form_data.username,
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    logger.info("Login successful | user=%s", form_data.username)
    return TokenResponse(access_token=token, token_type="bearer")


# ---------------------------------------------------------------------------
# Endpoints — Research
# ---------------------------------------------------------------------------


@app.post("/research", response_model=ResearchResponse, tags=["Research"])
async def research(
    request: ResearchRequest,
    current_user: str = Depends(get_current_user),
):
    """
    Run the full market intelligence pipeline and persist the result to MongoDB.

    - **competitors**: list of competitor names or topics to research
    - **urls**: list of source URLs (blogs, announcement pages, articles)
    """
    logger.info("Research request received | request=%s", request)
    if not request.competitors:
        raise HTTPException(
            status_code=422, detail="At least one competitor is required."
        )

    initial_state: GraphState = {
        "competitors": request.competitors,
        "urls": request.urls,
        "tavily_urls": [],
        "loaded_documents": [],
        "vectorstore": None,
        "context": "",
        "llm_response": "",
        "validation_result": {},
        "is_valid": False,
        "retry_count": 0,
        "pinecone_namespace": "",
        "source_url_map": [],
    }

    trace_config = {
        "run_name": "market_intelligence_pipeline",
        "tags": ["api", "market-intelligence"],
        "metadata": {
            "competitors": request.competitors,
            "user_urls": request.urls,
            "langsmith_project": LANGSMITH_PROJECT,
            "user": current_user,
        },
    }

    try:
        result = await _graph.ainvoke(initial_state, config=trace_config)
    except Exception as exc:
        logger.exception("Pipeline failed | competitors=%s", request.competitors)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        # Cleanup Pinecone namespace after run (whether success or failure)
        namespace = result.get("pinecone_namespace") if "result" in locals() else None
        if namespace:
            try:
                from pinecone import Pinecone

                pc = Pinecone(api_key=settings.PINECONE_API_KEY)
                index = pc.Index("market-intelligence")
                index.delete(delete_all=True, namespace=namespace)
                logger.info("Cleaned up Pinecone namespace '%s'", namespace)
            except Exception as e:
                logger.error("Failed to clean up namespace '%s': %s", namespace, e)

    vr = result.get("validation_result", {})
    now = datetime.now(timezone.utc).isoformat()

    doc = {
        "user": current_user,
        "competitors": result["competitors"],
        "urls": result["urls"],
        "tavily_urls": result.get("tavily_urls", []),
        "summary": result["llm_response"],
        "validation": {
            "is_valid": bool(vr.get("is_valid", False)),
            "quality": str(vr.get("quality", "low")),
            "summary": vr.get("summary", ""),
            "claim_analysis": vr.get("claim_analysis", []),
            "hallucinated_claims": vr.get("hallucinated_claims", []),
            "improvements": vr.get("improvements", []),
        },
        "is_valid": result["is_valid"],
        "created_at": now,
    }
    insert_result = await _db.research_runs.insert_one(doc)
    run_id = str(insert_result.inserted_id)
    logger.info("Research run saved | id=%s user=%s", run_id, current_user)

    return ResearchResponse(
        id=run_id,
        competitors=result["competitors"],
        urls=result["urls"],
        tavily_urls=result.get("tavily_urls", []),
        summary=result["llm_response"],
        validation=ValidationResult(
            is_valid=bool(vr.get("is_valid", False)),
            quality=str(vr.get("quality", "low")),
            summary=vr.get("summary", ""),
            claim_analysis=vr.get("claim_analysis", []),
            hallucinated_claims=vr.get("hallucinated_claims", []),
            improvements=vr.get("improvements", []),
        ),
        is_valid=result["is_valid"],
        created_at=now,
    )


# ---------------------------------------------------------------------------
# Helpers — SSE streaming
# ---------------------------------------------------------------------------

_PIPELINE_NODES = {
    "tavily_search",
    "html_loader",
    "embedding",
    "llm_invoke",
    "validation",
}

_NODE_START_MSG: dict[str, str] = {
    "tavily_search": "Searching competitor intelligence across the web...",
    "html_loader": "Fetching content from source URLs...",
    "embedding": "Indexing content into vector store...",
    "llm_invoke": "Generating market intelligence report...",
    "validation": "Validating response quality...",
}


def _node_end_msg(node: str, update: dict) -> str:
    if node == "tavily_search":
        n = len(update.get("tavily_urls", []))
        return f"Found {n} source URL{'s' if n != 1 else ''} from competitor research"
    if node == "html_loader":
        n = len(update.get("loaded_documents", []))
        return f"Loaded content from {n} page{'s' if n != 1 else ''}"
    if node == "embedding":
        return "Content indexed — ready for analysis"
    if node == "llm_invoke":
        return "Report draft complete"
    if node == "validation":
        vr = update.get("validation_result", {})
        quality = vr.get("quality", "low").upper()
        valid = update.get("is_valid", False)
        return f"Quality: {quality} — {'passed' if valid else 'improving...'}"
    return f"{node} complete"


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


# ---------------------------------------------------------------------------
# Endpoints — Research (streaming)
# ---------------------------------------------------------------------------


@app.post("/research/stream", tags=["Research"])
async def research_stream(
    request: ResearchRequest,
    current_user: str = Depends(get_current_user),
):
    """
    Run the pipeline and stream progress + LLM tokens as Server-Sent Events.

    Event shapes:
      {"type": "status",   "node": str, "phase": "start"|"end", "message": str}
      {"type": "token",    "content": str}
      {"type": "retry",    "attempt": int, "message": str}
      {"type": "complete", "result": ResearchResponse-dict}
      {"type": "error",    "message": str}
    """
    if not request.competitors:
        raise HTTPException(
            status_code=422, detail="At least one competitor is required."
        )

    initial_state: GraphState = {
        "competitors": request.competitors,
        "urls": request.urls,
        "tavily_urls": [],
        "loaded_documents": [],
        "vectorstore": None,
        "context": "",
        "llm_response": "",
        "validation_result": {},
        "is_valid": False,
        "retry_count": 0,
        "pinecone_namespace": "",
        "source_url_map": [],
    }

    trace_config = {
        "run_name": "market_intelligence_pipeline_stream",
        "tags": ["api", "market-intelligence", "stream"],
        "metadata": {"competitors": request.competitors, "user": current_user},
    }

    async def generate():
        node_visits: dict[str, int] = {}
        final_state: dict = {}

        try:
            async for event in _graph.astream_events(
                initial_state, config=trace_config, version="v2"
            ):
                kind = event["event"]
                name = event.get("name", "")

                # ── Node starting ──────────────────────────────────────────
                if kind == "on_chain_start" and name in _PIPELINE_NODES:
                    visits = node_visits.get(name, 0) + 1
                    node_visits[name] = visits

                    if name == "llm_invoke" and visits > 1:
                        yield _sse(
                            {
                                "type": "retry",
                                "attempt": visits - 1,
                                "message": f"Generating improved response (attempt {visits})...",
                            }
                        )
                    else:
                        yield _sse(
                            {
                                "type": "status",
                                "node": name,
                                "phase": "start",
                                "message": _NODE_START_MSG[name],
                            }
                        )

                # ── Node finished ──────────────────────────────────────────
                elif kind == "on_chain_end" and name in _PIPELINE_NODES:
                    output = event.get("data", {}).get("output") or {}
                    final_state.update(output)
                    yield _sse(
                        {
                            "type": "status",
                            "node": name,
                            "phase": "end",
                            "message": _node_end_msg(name, output),
                        }
                    )

                # ── LLM token (report generation only, skip validation judge) ─
                elif kind == "on_chat_model_stream":
                    tags = event.get("tags", [])
                    if "llm_invoke" in tags and "validation" not in tags:
                        chunk = event.get("data", {}).get("chunk")
                        content = getattr(chunk, "content", "") if chunk else ""
                        if content:
                            yield _sse({"type": "token", "content": content})

        except Exception as exc:
            logger.exception(
                "Streaming pipeline failed | competitors=%s", request.competitors
            )
            yield _sse({"type": "error", "message": str(exc)})
            return

        # ── Pipeline complete: persist to MongoDB and emit result ──────────
        try:
            vr = final_state.get("validation_result") or {}
            now = datetime.now(timezone.utc).isoformat()
            doc = {
                "user": current_user,
                "competitors": final_state.get("competitors", request.competitors),
                "urls": final_state.get("urls", request.urls),
                "tavily_urls": final_state.get("tavily_urls", []),
                "summary": final_state.get("llm_response", ""),
                "validation": {
                    "is_valid": bool(vr.get("is_valid", False)),
                    "quality": str(vr.get("quality", "low")),
                    "summary": vr.get("summary", ""),
                    "claim_analysis": vr.get("claim_analysis", []),
                    "hallucinated_claims": vr.get("hallucinated_claims", []),
                    "improvements": vr.get("improvements", []),
                },
                "is_valid": bool(final_state.get("is_valid", False)),
                "created_at": now,
            }
            insert_result = await _db.research_runs.insert_one(doc)
            run_id = str(insert_result.inserted_id)
            logger.info("Streaming run saved | id=%s user=%s", run_id, current_user)

            r = ResearchResponse(
                id=run_id,
                competitors=doc["competitors"],
                urls=doc["urls"],
                tavily_urls=doc["tavily_urls"],
                summary=doc["summary"],
                validation=doc["validation"],
                is_valid=doc["is_valid"],
                created_at=now,
            )
            yield _sse({"type": "complete", "result": r.model_dump()})

        except asyncio.CancelledError:
            logger.warning("SSE stream cancelled by client disconnect")
        except Exception as exc:
            logger.exception("Streaming pipeline failed")
            yield _sse({"type": "error", "message": "Pipeline error occurred"})
        finally:
            namespace = final_state.get("pinecone_namespace")
            if namespace:
                try:
                    from pinecone import Pinecone

                    pc = Pinecone(api_key=settings.PINECONE_API_KEY)
                    index = pc.Index("market-intelligence")
                    index.delete(delete_all=True, namespace=namespace)
                    logger.info("Cleaned up Pinecone namespace '%s'", namespace)
                except Exception as e:
                    logger.error("Failed to clean up namespace '%s': %s", namespace, e)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disables nginx buffering
        },
    )


# ---------------------------------------------------------------------------
# Endpoints — History
# ---------------------------------------------------------------------------


@app.get("/history", response_model=list[HistoryItem], tags=["History"])
async def get_history(
    limit: int = 20,
    current_user: str = Depends(get_current_user),
):
    """Return the most recent research runs for the authenticated user."""
    cursor = (
        _db.research_runs.find(
            {"user": current_user},
            {"competitors": 1, "is_valid": 1, "validation.quality": 1, "created_at": 1},
        )
        .sort("created_at", -1)
        .limit(limit)
    )
    items: list[HistoryItem] = []
    async for doc in cursor:
        items.append(
            HistoryItem(
                id=str(doc["_id"]),
                competitors=doc.get("competitors", []),
                is_valid=doc.get("is_valid", False),
                quality=doc.get("validation", {}).get("quality", "low"),
                created_at=doc.get("created_at", ""),
            )
        )
    return items


@app.get("/history/{run_id}", response_model=ResearchResponse, tags=["History"])
async def get_history_item(
    run_id: str,
    current_user: str = Depends(get_current_user),
):
    """Return the full detail of a single research run."""
    try:
        doc = await _db.research_runs.find_one(
            {"_id": ObjectId(run_id), "user": current_user}
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid run ID format")
    if not doc:
        raise HTTPException(status_code=404, detail="Run not found")

    v = doc.get("validation", {})
    return ResearchResponse(
        id=str(doc["_id"]),
        competitors=doc["competitors"],
        urls=doc["urls"],
        tavily_urls=doc.get("tavily_urls", []),
        summary=doc["summary"],
        validation=ValidationResult(
            is_valid=v.get("is_valid", False),
            quality=v.get("quality", "low"),
            summary=v.get("summary", ""),
            claim_analysis=v.get("claim_analysis", []),
            hallucinated_claims=v.get("hallucinated_claims", []),
            improvements=v.get("improvements", []),
        ),
        is_valid=doc["is_valid"],
        created_at=doc["created_at"],
    )
