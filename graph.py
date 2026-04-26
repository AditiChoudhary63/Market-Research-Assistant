"""
Market Intelligence LangGraph Pipeline
Nodes:
  1. tavily_search  - Research competitor activity and market trends via Tavily
  2. html_loader    - Fetch and parse HTML content from user-supplied source URLs
  3. embedding      - Chunk + embed all documents into Pinecone
  4. llm_invoke     - Generate a structured market intelligence summary from context
  5. validation     - LLM-as-judge checks for hallucinations and verifies claims
"""

import asyncio
import json
import logging
import os
import re
import sys
import uuid
from typing import Any

from prompts import (
    JUDGE_SYSTEM,
    analyst_human_message,
    analyst_system_prompt,
    judge_human_message,
    retry_instruction,
    tavily_search_query,
)
from langchain_community.document_loaders import AsyncHtmlLoader
from langchain_community.document_transformers import Html2TextTransformer
from langchain_tavily import TavilySearch
from langchain_pinecone import PineconeVectorStore
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_experimental.text_splitter import SemanticChunker
from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from config import settings

PINECONE_API_KEY   = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX     = os.getenv("PINECONE_INDEX", "market-intelligence")
PINECONE_CLOUD     = os.getenv("PINECONE_CLOUD", "aws")
PINECONE_REGION    = os.getenv("PINECONE_REGION", "us-east-1")
EMBEDDING_DIM      = int(os.getenv("EMBEDDING_DIM", "1536"))  # text-embedding-ada-002
LLM_MODEL          = os.getenv("LLM_MODEL", "gpt-4o-mini")
JUDGE_MODEL        = os.getenv("JUDGE_MODEL", "gpt-4o")

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("pipeline.log", mode="w", encoding="utf-8"),
    ],
)
logger = logging.getLogger("market_intelligence")

# ---------------------------------------------------------------------------
# LangSmith tracing
# LangChain reads LANGSMITH_TRACING, LANGSMITH_API_KEY, LANGSMITH_ENDPOINT,
# and LANGSMITH_PROJECT automatically from the environment.
# We surface the active config at startup so it's easy to confirm in logs.
# ---------------------------------------------------------------------------

LANGSMITH_ENABLED = os.getenv("LANGSMITH_TRACING", "false").lower() == "true"
LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT", "market-intelligence")

if LANGSMITH_ENABLED:
    logger.info(
        "LangSmith tracing ENABLED | project=%s | endpoint=%s",
        LANGSMITH_PROJECT,
        os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com"),
    )
else:
    logger.info("LangSmith tracing DISABLED")

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

MAX_RETRIES = int(os.getenv("MAX_RETRIES", "2"))


class GraphState(TypedDict):
    competitors: list[str]
    urls: list[str]             # user-supplied source URLs (blogs, articles, announcements)
    tavily_urls: list[str]      # URLs extracted from Tavily search results
    loaded_documents: list[Document]
    vectorstore: Any            # PineconeVectorStore instance passed through in-memory
    pinecone_namespace: str     # Tracked so we can delete it in api.py
    context: str                # retrieved source context forwarded to validation for grounding
    source_url_map: list[str]   # ordered list of unique source URLs (index+1 = citation number)
    llm_response: str
    validation_result: dict
    is_valid: bool
    retry_count: int            # tracks how many times llm_invoke has been retried


# ---------------------------------------------------------------------------
# Node 1 — Tavily Search
# ---------------------------------------------------------------------------

async def tavily_search_node(state: GraphState) -> GraphState:
    """Search Tavily and extract result URLs; content will be fetched by the HTML loader."""
    logger.info("Node 1 [tavily_search] started | competitors=%s", state["competitors"])
    tool = TavilySearch(max_results=6)
    tavily_urls: list[str] = []

    for competitor in state["competitors"]:
        try:
            logger.debug("Querying Tavily for competitor: %s", competitor)
            raw = await tool.ainvoke(tavily_search_query(competitor))
            logger.debug("Tavily raw response for '%s': %s", competitor, raw)

            # TavilySearch returns a dict with a "results" key containing list[dict]
            if isinstance(raw, dict):
                hits = raw.get("results", [])
            elif isinstance(raw, str):
                parsed = json.loads(raw)
                hits = parsed.get("results", []) if isinstance(parsed, dict) else parsed
            elif isinstance(raw, list):
                hits = raw
            else:
                hits = []

            urls = [h["url"] for h in hits if isinstance(h, dict) and h.get("url")]
            logger.info("Tavily returned %d URLs for '%s': %s", len(urls), competitor, urls)
            tavily_urls.extend(urls)
        except Exception:
            logger.exception("Tavily search failed for competitor '%s' — skipping", competitor)

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_tavily_urls = [u for u in tavily_urls if not (u in seen or seen.add(u))]

    if not unique_tavily_urls:
        logger.warning("No Tavily URLs collected across all competitors")

    logger.info("Node 1 [tavily_search] complete | tavily_urls=%d", len(unique_tavily_urls))
    return {**state, "tavily_urls": unique_tavily_urls}


# ---------------------------------------------------------------------------
# Node 2 — HTML Loader
# ---------------------------------------------------------------------------

async def html_loader_node(state: GraphState) -> GraphState:
    """Fetch HTML from all URLs (Tavily-discovered + user-supplied) and convert to plain text."""
    tavily_urls = set(state.get("tavily_urls", []))
    user_urls = set(state.get("urls", []))
    all_urls = list(tavily_urls | user_urls)

    logger.info(
        "Node 2 [html_loader] started | total_urls=%d (tavily=%d, user=%d)",
        len(all_urls), len(tavily_urls), len(user_urls),
    )
    logger.info("URLs to fetch: %s", all_urls)

    raw_docs: list = []

    async def fetch_single(u: str):
        loader = AsyncHtmlLoader([u], ignore_load_errors=True)
        try:
            logger.debug("Fetching content for: %s", u)
            docs = await loader.aload()
            return docs
        except Exception as e:
            logger.warning("Failed to load %s: %s", u, e)
            return []

    results = await asyncio.gather(*(fetch_single(u) for u in all_urls), return_exceptions=True)
    for res in results:
        if isinstance(res, list):
            raw_docs.extend(res)
        elif isinstance(res, Exception):
            logger.warning("Task raised exception: %s", res)

    logger.info("Fetched %d raw HTML documents", len(raw_docs))

    if not raw_docs:
        logger.warning("No HTML documents were successfully loaded")
        return {**state, "loaded_documents": []}

    try:
        transformer = Html2TextTransformer()
        docs = list(transformer.transform_documents(raw_docs))
        # logger.info("Transformed documents to plain text: %s", docs)
    except Exception:
        logger.exception("HTML-to-text transformation failed — returning empty document list")
        return {**state, "loaded_documents": []}

    logger.info("Node 2 [html_loader] complete | docs_loaded=%d", len(docs))
    return {**state, "loaded_documents": docs}


# ---------------------------------------------------------------------------
# Node 3 — Embedding into Pinecone
# ---------------------------------------------------------------------------

async def embedding_node(state: GraphState) -> GraphState:
    """Chunk and embed all loaded HTML documents into Pinecone."""
    all_docs = state.get("loaded_documents", [])
    logger.info("Node 3 [embedding] started | loaded_documents=%d", len(all_docs))

    if not all_docs:
        logger.error(
            "No documents available for embedding — "
            "tavily_urls=%d, user_urls=%d, loaded_documents=0",
            len(state.get("tavily_urls", [])),
            len(state.get("urls", [])),
        )
        raise RuntimeError(
            "No documents available for embedding. "
            "Check that the HTML loader successfully fetched content from the provided URLs."
        )

    try:
        splitter = SemanticChunker(
            embeddings=OpenAIEmbeddings(),
            breakpoint_threshold_type="percentile",
            breakpoint_threshold_amount=95.0,
        )
        chunks = splitter.split_documents(all_docs)
        logger.info("Semantic chunking complete | chunks=%d", len(chunks))
    except Exception:
        logger.exception("Document splitting failed")
        raise

    try:
        # Use a unique namespace per pipeline run so concurrent runs don't mix data
        namespace = f"run-{uuid.uuid4().hex[:12]}"
        vectorstore = await PineconeVectorStore.afrom_documents(
            documents=chunks,
            embedding=OpenAIEmbeddings(),
            index_name=PINECONE_INDEX,
            namespace=namespace,
        )
        logger.info(
            "Pinecone index '%s' populated | namespace=%s | chunks=%d",
            PINECONE_INDEX, namespace, len(chunks),
        )
    except Exception:
        logger.exception("Pinecone embedding failed")
        raise

    logger.info("Node 3 [embedding] complete")
    return {**state, "vectorstore": vectorstore, "pinecone_namespace": namespace}


# ---------------------------------------------------------------------------
# Node 4 — LLM Invocation
# ---------------------------------------------------------------------------

async def llm_invoke_node(state: GraphState) -> GraphState:
    """Retrieve top-k context chunks and generate a structured market intelligence summary."""
    retry_count = state.get("retry_count", 0)
    logger.info("Node 4 [llm_invoke] started | attempt=%d", retry_count + 1)

    base = ", ".join(state["competitors"])
    queries = [
        f"{base} product launches updates announcements",
        f"{base} partnerships acquisitions collaborations",
        f"{base} strategy market positioning growth plans",
        f"{base} industry trends competitor analysis innovation",
    ]

    try:
        seen: set[str] = set()
        relevant_docs = []
        for q in queries:
            for doc in await state["vectorstore"].asimilarity_search(q, k=15):
                key = doc.page_content
                if key not in seen:
                    seen.add(key)
                    relevant_docs.append(doc)
        logger.info(
            "Retrieved %d unique chunks via multi-query retrieval (%d queries x k=15)",
            len(relevant_docs), len(queries),
        )
    except Exception:
        logger.exception("Pinecone similarity search failed")
        raise

    # Build a stable numbered URL map from the retrieved source documents.
    # This is injected into the LLM prompt so it can cite [1], [2] directly.
    seen_urls: list[str] = []
    url_index: dict[str, int] = {}
    for doc in relevant_docs:
        url = doc.metadata.get("source", "unknown")
        if url not in url_index:
            url_index[url] = len(seen_urls) + 1
            seen_urls.append(url)

    url_map_lines = "\n".join(f"  [{i}]: {u}" for i, u in enumerate(seen_urls, start=1))
    url_map_block = f"Source URL Index (use ONLY these numbers for citations):\n{url_map_lines}"

    context = "\n\n---\n\n".join(
        f"[{url_index.get(doc.metadata.get('source', 'unknown'), '?')}] {doc.metadata.get('source', 'unknown')}\n{doc.page_content}"
        for doc in relevant_docs
    )
    logger.info("Built URL map with %d unique sources", len(seen_urls))

    llm = ChatOpenAI(model=LLM_MODEL, temperature=0.2, streaming=True, stream_chunk_timeout=None)
    logger.debug("Invoking LLM (%s) for market intelligence summary", LLM_MODEL)

    hallucinated_claims = state.get("validation_result", {}).get("hallucinated_claims", [])
    retry_instr = retry_instruction(retry_count, hallucinated_claims)
    if retry_instr:
        logger.info(
            "Retry prompt includes %d hallucinated claims to fix", len(hallucinated_claims)
        )

    messages = [
        SystemMessage(content=analyst_system_prompt(retry_instr)),
        HumanMessage(content=analyst_human_message(state["competitors"], context, url_map_block)),
    ]

    try:
        response = await llm.ainvoke(
            messages,
            config={
                "run_name": f"market_intelligence_summary_attempt_{retry_count + 1}",
                "tags": ["llm_invoke", "market-intelligence"],
                "metadata": {
                    "competitors": state["competitors"],
                    "retry_attempt": retry_count + 1,
                    "context_chunks": len(relevant_docs),
                },
            },
        )
        logger.info("LLM response received | length=%d chars", len(response.content))
    except Exception:
        logger.exception("LLM invocation failed")
        raise

    logger.info("Node 4 [llm_invoke] complete")
    return {**state, "llm_response": response.content, "context": context, "source_url_map": seen_urls}


# ---------------------------------------------------------------------------
# Node 5 — Validation (LLM-as-Judge)
# ---------------------------------------------------------------------------

async def validation_node(state: GraphState) -> GraphState:
    """Use GPT-4o as a hallucination judge to verify every claim in the intelligence report."""
    logger.info("Node 5 [validation] started")

    judge = ChatOpenAI(model=JUDGE_MODEL, temperature=0, stream_chunk_timeout=None)
    logger.debug("Invoking judge LLM (%s) for hallucination detection", JUDGE_MODEL)

    messages = [
        SystemMessage(content=JUDGE_SYSTEM),
        HumanMessage(content=judge_human_message(
            state["competitors"],
            state["llm_response"],
            state.get("context", ""),
        )),
    ]

    try:
        raw = await judge.ainvoke(
            messages,
            config={
                "run_name": f"hallucination_judge_attempt_{state.get('retry_count', 0) + 1}",
                "tags": ["validation", "llm-as-judge", "market-intelligence"],
                "metadata": {
                    "competitors": state["competitors"],
                    "retry_attempt": state.get("retry_count", 0) + 1,
                    "report_length": len(state["llm_response"]),
                },
            },
        )
        logger.debug("Judge raw response received | length=%d chars", len(raw.content))
    except Exception:
        logger.exception("Judge LLM invocation failed")
        raise

    match = re.search(r"\{.*\}", raw.content, re.DOTALL)
    if match:
        try:
            validation_result = json.loads(match.group())
            logger.info(
                "Validation complete | is_valid=%s | quality=%s | summary=%s | claims_analysed=%d | hallucinated=%d",
                validation_result.get("is_valid"),
                validation_result.get("quality"),
                validation_result.get("summary", "")[:80],
                len(validation_result.get("claim_analysis", [])),
                len(validation_result.get("hallucinated_claims", [])),
            )
        except json.JSONDecodeError:
            logger.warning("Failed to parse judge JSON — treating as invalid response")
            validation_result = {
                "is_valid": False,
                "quality": "low",
                "summary": "Judge response could not be parsed.",
                "claim_analysis": [],
                "hallucinated_claims": [],
                "improvements": [],
            }
    else:
        logger.warning("No JSON block found in judge response — treating as invalid")
        validation_result = {
            "is_valid": False,
            "quality": "low",
            "summary": raw.content,
            "claim_analysis": [],
            "hallucinated_claims": [],
            "improvements": [],
        }

    # Programmatic safeguard: if the LLM marked all claims as SUPPORTED but
    # gave a failing score (LLM prompt non-compliance), we force it to pass.
    claim_analysis = validation_result.get("claim_analysis", [])
    if claim_analysis:
        all_supported = all(
            c.get("status", "").upper() == "SUPPORTED"
            for c in claim_analysis
        )
        if all_supported:
            validation_result["is_valid"] = True
            validation_result["quality"] = "very high"
            validation_result["hallucinated_claims"] = []
            validation_result["improvements"] = []

    is_valid = bool(validation_result.get("is_valid", False))
    has_hallucinations = (
        bool(validation_result.get("hallucinated_claims")) or not is_valid
    )

    # Increment retry_count here (inside the node) so the state update is
    # persisted by LangGraph. Routing functions are read-only and cannot
    # mutate state.
    new_retry_count = state.get("retry_count", 0) + (1 if has_hallucinations else 0)
    logger.info(
        "Node 5 [validation] complete | is_valid=%s | retry_count=%d→%d",
        is_valid, state.get("retry_count", 0), new_retry_count,
    )
    # Append a guaranteed References section from the pre-built URL map.
    # This is deterministic — no regex, no LLM format guessing.
    report = state.get("llm_response", "")
    # Strip any LLM-generated References block (empty or otherwise) to avoid duplication
    report = re.sub(r"\n+#{1,3}\s*References.*$", "", report, flags=re.IGNORECASE | re.DOTALL).rstrip()

    source_url_map = state.get("source_url_map", [])
    logger.info("Appending References section | url_count=%d", len(source_url_map))
    if source_url_map:
        refs = "\n\n## References\n" + "".join(
            f"- **[{i}]** {url}\n" for i, url in enumerate(source_url_map, start=1)
        )
        report = report + refs
    else:
        logger.warning("source_url_map is empty — References section will be omitted")

    return {
        **state,
        "llm_response": report,
        "validation_result": validation_result,
        "is_valid": is_valid,
        "retry_count": new_retry_count,
    }


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def route_after_validation(state: GraphState) -> str:
    """Read-only routing function: directs to llm_invoke on hallucinations, else END.

    NOTE: retry_count is incremented inside validation_node (a proper state-returning
    node). Routing functions in LangGraph are pure → they cannot persist state changes.
    """
    # retry_count was already incremented by validation_node before this is called
    retry_count = state.get("retry_count", 0)
    hallucinated_claims = state.get("validation_result", {}).get("hallucinated_claims", [])
    has_hallucinations = bool(hallucinated_claims) or not state.get("is_valid", True)

    logger.info(
        "Routing | has_hallucinations=%s | retry_count=%d | max_retries=%d",
        has_hallucinations, retry_count, MAX_RETRIES,
    )

    if has_hallucinations and retry_count <= MAX_RETRIES:
        logger.info(
            "Routing → llm_invoke for retry %d/%d | hallucinated_claims=%d",
            retry_count, MAX_RETRIES, len(hallucinated_claims),
        )
        return "llm_invoke"

    if has_hallucinations:
        logger.warning(
            "Max retries (%d) reached with hallucinations still present — routing → END",
            MAX_RETRIES,
        )
    else:
        logger.info("Validation passed — routing → END")

    return END


# ---------------------------------------------------------------------------
# Graph Assembly
# ---------------------------------------------------------------------------

def build_graph():
    logger.info("Building market intelligence graph")
    graph = StateGraph(GraphState)

    graph.add_node("tavily_search", tavily_search_node)
    graph.add_node("html_loader", html_loader_node)
    graph.add_node("embedding", embedding_node)
    graph.add_node("llm_invoke", llm_invoke_node)
    graph.add_node("validation", validation_node)

    graph.set_entry_point("tavily_search")
    graph.add_edge("tavily_search", "html_loader")
    graph.add_edge("html_loader", "embedding")
    graph.add_edge("embedding", "llm_invoke")
    graph.add_edge("llm_invoke", "validation")
    graph.add_conditional_edges(
        "validation",
        route_after_validation,
        {"llm_invoke": "llm_invoke", END: END},
    )

    compiled_graph = graph.compile()
    logger.info("Graph compiled successfully")
    return compiled_graph



