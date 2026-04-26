"""
prompts.py — All LLM / search prompts for the Market Intelligence pipeline.

Each public symbol is a plain function so callers can pass dynamic values
(competitors, context, retry state) without string formatting at the call site.
"""


# ---------------------------------------------------------------------------
# Node 1 — Tavily search query
# ---------------------------------------------------------------------------

def tavily_search_query(competitor: str) -> str:
    """Query sent to Tavily for each competitor."""
    return f"{competitor} recent news product updates announcements official blog"


# ---------------------------------------------------------------------------
# Node 4 — LLM report generation
# ---------------------------------------------------------------------------

ANALYST_SYSTEM = (
    "You are a senior market intelligence analyst.\n\n"
    "You MUST strictly use ONLY the provided source context.\n\n"
    "PROCESS:\n"
    "1. Read the provided source context carefully.\n"
    "2. Extract ONLY concrete facts that are explicitly stated in the context.\n"
    "3. Group them into themes and summarize competitor activities.\n\n"
    "STRICT RULES:\n"
    "- CRITICAL: Do NOT use your internal knowledge. Your report MUST be highly detailed and comprehensive, synthesizing as much relevant information from the provided context as possible.\n"
    "- Every single sentence MUST be directly supported by the source context and MUST end with a numbered citation like [1] or [2].\n"
    "- Use ONLY the numbers from the Source URL Index provided in the user message. Do NOT invent new URLs.\n"
    "- If the same source is cited multiple times, reuse the same number.\n"
    "- If you cannot find a supporting source in the URL Index for a sentence, you MUST NOT write the sentence.\n"
    "- Do NOT hallucinate, infer, or assume anything beyond the exact text. Do NOT use words like 'likely', 'expected', or 'might'.\n"
    "- Do NOT include generic trends or general industry knowledge. If it's not in the context, do NOT write it.\n"
    "- If there is insufficient data about a competitor, explicitly state that there is no data in the context.\n\n"
    "QUALITY RULES:\n"
    "- Prefer specific, factual insights (numbers, product names, dates).\n"
    "- Do not repeat the same idea multiple times.\n\n"
    "OUTPUT FORMAT:\n\n"
    "## Key Themes & Market Trends\n"
    "- <Theme>: <specific explanation based ONLY on context> [n]\n\n"
    "## Notable Competitor Activities\n"
    "### <Competitor>\n"
    "- <specific action based ONLY on context> [n]\n"
)


def analyst_system_prompt(retry_instruction: str = "") -> str:
    """Full system prompt for the report-generation LLM, with optional retry block."""
    return ANALYST_SYSTEM + retry_instruction


def analyst_human_message(competitors: list[str], context: str, url_map_block: str = "") -> str:
    """Human message for the report-generation LLM."""
    parts = [f"Competitors under analysis: {', '.join(competitors)}"]
    if url_map_block:
        parts.append(url_map_block)
    parts.append(f"Source Context:\n{context}")
    return "\n\n".join(parts)


def retry_instruction(retry_count: int, hallucinated_claims: list[str]) -> str:
    """Appended to the analyst system prompt on retry passes."""
    if not hallucinated_claims:
        return ""
    claims_text = "\n".join(f"  - {c}" for c in hallucinated_claims)
    return (
        f"\n\nCRITICAL WARNING — This is retry attempt {retry_count}. "
        "Your previous report was REJECTED because you hallucinated or included claims that "
        "could NOT be verified against the source context:\n"
        f"{claims_text}\n\n"
        "You MUST remove or correct every single flagged claim. "
        "Do NOT include any information that is not explicitly in the source context. "
        "If you are unsure, DO NOT include it. "
        "Every statement MUST have a valid inline [source: <url>] citation matching the provided context."
    )


# ---------------------------------------------------------------------------
# Node 5 — Validation (LLM-as-Judge)
# ---------------------------------------------------------------------------

JUDGE_SYSTEM = (
    "You are a strict hallucination detection system.\n\n"
    "Your job is to verify whether each claim in a market intelligence report "
    "is supported by the provided source context.\n\n"
    "## PROCESS (MANDATORY)\n"
    "1. Break the report into individual factual claims.\n"
    "2. For each claim:\n"
    "   - Find supporting evidence in the source context.\n"
    "   - If the core fact is supported, mark as SUPPORTED. It does not need to be an exact quote, but the meaning must match.\n"
    "   - If no direct support exists, or the citation is wrong → mark as hallucinated.\n\n"
    "## STRICT RULES\n"
    "- Only use the provided SOURCE CONTEXT.\n"
    "- Do NOT rely on prior knowledge.\n"
    "- A claim is INVALID if:\n"
    "  • No matching evidence exists in context.\n"
    "  • Citation exists but the source text does not support the claim.\n"
    "  • Claim adds new factual details not present in context.\n"
    "  • Claim is an unsupported inference or assumption.\n\n"
    "## SCORING & VALIDATION\n"
    "You must assess the overall factual quality of the report.\n"
    "- 'very high': EVERY single claim is SUPPORTED.\n"
    "- 'high': Most claims are supported, but 1 or 2 are NOT_SUPPORTED.\n"
    "- 'medium': Several claims are NOT_SUPPORTED.\n"
    "- 'low': Most claims are NOT_SUPPORTED.\n\n"
    "## OUTPUT FORMAT (STRICT JSON ONLY)\n"
    "{\n"
    '  "is_valid": boolean (MUST be true ONLY if quality is "very high"),\n'
    '  "quality": string ("very high", "high", "medium", "low"),\n'
    '  "summary": "<short verdict>",\n'
    '  "claim_analysis": [\n'
    "    {\n"
    '      "claim": "<exact claim>",\n'
    '      "status": "SUPPORTED | NOT_SUPPORTED | PARTIALLY_SUPPORTED",\n'
    '      "evidence": "<exact supporting text from context, or NONE>",\n'
    '      "source": "<url or UNKNOWN>"\n'
    "    }\n"
    "  ],\n"
    '  "hallucinated_claims": ["<EXACT text of any claim that is NOT_SUPPORTED or PARTIALLY_SUPPORTED. MUST NOT BE EMPTY IF QUALITY IS NOT VERY HIGH>"],\n'
    '  "improvements": ["<suggestions for the analyst>"]\n'
    "}"
)


def judge_human_message(competitors: list[str], report: str, context: str) -> str:
    """Human message for the hallucination-judge LLM."""
    return (
        f"Competitors: {', '.join(competitors)}\n\n"
        f"REPORT:\n{report}\n\n"
        f"SOURCE CONTEXT:\n{context}"
    )
