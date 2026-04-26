# User Manual — Market Intelligence Platform

> **Live application:** [http://20.204.113.165:8000](http://20.204.113.165:8000)
> **Source code:** [github.com/AditiChoudhary63/Market-Research-Assistant](https://github.com/AditiChoudhary63/Market-Research-Assistant)

---

## Table of Contents

1. [What the platform does](#1-what-the-platform-does)
2. [Accessing the application](#2-accessing-the-application)
3. [Signing in](#3-signing-in)
4. [Running your first research report](#4-running-your-first-research-report)
5. [Understanding the pipeline progress](#5-understanding-the-pipeline-progress)
6. [Reading the results](#6-reading-the-results)
7. [Validation quality scores explained](#7-validation-quality-scores-explained)
8. [Using run history](#8-using-run-history)
9. [API access](#9-api-access)
10. [Tips for best results](#10-tips-for-best-results)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. What the platform does

The Market Intelligence Platform automates competitor research. You provide:

- A list of **competitor names or topics** (e.g. `OpenAI`, `Anthropic`)
- A list of **source URLs** (blogs, product pages, news articles)

The platform then:

1. Searches the web for recent competitor news via Tavily
2. Fetches and parses all source pages
3. Embeds the content into a temporary vector index
4. Generates a structured, cited intelligence report using GPT-4o-mini
5. Validates every claim against the source evidence using GPT-4o as a judge
6. Retries and corrects the report if hallucinations are found

The entire process streams live to your browser — you see each step complete in real time and watch the report appear word by word.

---

## 2. Accessing the application

Open your browser and navigate to:

**[http://20.204.113.165:8000](http://20.204.113.165:8000)**

No installation or setup is required. The application runs fully in the browser.

---

## 3. Signing in

You will be presented with a login screen on first visit.

| Field | Value |
|---|---|
| **Username** | `admin` |
| **Password** | `admin123` |

Click **Sign In**. Your session is stored in the browser and persists until you click **Sign out** in the bottom-left corner.

> Your session token expires after 7 days. If you see "Invalid or expired token", simply sign in again.

---

## 4. Running your first research report

Once signed in, the **New Research Run** form is shown.

### Step 1 — Enter competitors or topics

In the **Competitors / Topics** box, type one name per line. Examples:

```
OpenAI
Anthropic
Google DeepMind
```

You can enter company names, product names, or any topic you want to research.

### Step 2 — Enter source URLs

In the **Source URLs** box, paste one URL per line. These are the pages you want the platform to read and analyse. Good sources include:

- Company blogs (e.g. `https://openai.com/blog`)
- Official news / announcements pages (e.g. `https://www.anthropic.com/news`)
- Product release pages
- News articles about the competitors

```
https://openai.com/blog
https://www.anthropic.com/news
https://deepmind.google/discover/blog/
```

> The platform also automatically discovers additional URLs via web search — your source URLs supplement but do not limit the research.

### Step 3 — Generate the report

Click **Generate Report**. The button will show a spinner while the pipeline runs.

---

## 5. Understanding the pipeline progress

While the report is being generated, a **Pipeline Progress** panel appears showing five steps:

| Step | What it does |
|---|---|
| 🔍 **Competitor Research** | Searches the web for recent news and activity for each competitor |
| 📄 **Content Fetching** | Downloads and parses the content from all discovered and user-supplied URLs |
| 🧠 **Vector Indexing** | Splits content into semantic chunks and indexes them for retrieval |
| ✍️ **Report Generation** | Retrieves the most relevant content and generates the structured report |
| ✓ **Quality Validation** | Checks every claim in the report against the source evidence |

Each step shows a **spinning indicator** while running and a **green tick** when complete.

Below the steps, a **Live Report** panel streams the report word by word as it is written by the AI — you don't have to wait for the full pipeline to finish to start reading.

### Retry banner

If the validator finds unsupported claims, an amber banner appears:

> 🔄 Generating improved response (attempt 2)...

The report is then regenerated with the flagged claims corrected. This happens automatically — no action is needed from you.

---

## 6. Reading the results

Once the pipeline completes, three result cards appear.

### Intelligence Report

The main output — a structured Markdown report with two sections:

- **Key Themes & Market Trends** — cross-competitor insights grouped by theme
- **Notable Competitor Activities** — per-competitor breakdown of recent actions

Every sentence includes an inline citation like `[1]` or `[3]`. These numbers correspond to the **References** list at the bottom of the report. All cited information comes directly from the fetched source content.

### Sources Analysed

A list of every URL that contributed to the report — both your supplied URLs and those discovered via web search. Each URL is a clickable link.

### Validation

Shows the quality assessment from the GPT-4o judge.

**Header area:**

- **Badge** — `✓ Verified`, `⚠ Partial`, or `✗ Invalid` (see [Section 7](#7-validation-quality-scores-explained))
- **Quality score** — `VERY HIGH`, `HIGH`, `MEDIUM`, or `LOW`
- **Summary** — a short sentence describing the validation outcome

**Claim Analysis** (expandable) — a card for each factual claim in the report showing:

- `SUPPORTED` (green) — claim is directly backed by source evidence
- `PARTIALLY SUPPORTED` (amber) — claim has some but not complete evidence
- `NOT SUPPORTED` (red) — no matching evidence found in the source context

**⚠ Flagged Claims** — the exact text of any claims that could not be verified. These are the claims the retry mechanism attempted to fix.

**💡 Suggested Improvements** — the judge's recommendations for what could be strengthened in a follow-up run.

---

## 7. Validation quality scores explained

| Score | Badge | Meaning |
|---|---|---|
| **VERY HIGH** | ✓ Verified (green) | Every single claim is fully supported by the source context |
| **HIGH** | ✓ Verified (green) | Most claims are supported; 1–2 are not directly evidenced |
| **MEDIUM** | ⚠ Partial (amber) | Several claims are partially or not supported — report is usable but review flagged claims before sharing |
| **LOW** | ✗ Invalid (red) | Most claims could not be verified — treat the report with significant caution |

> **Medium quality** means most claims are supported by the source context, but a few are only partially backed or lack direct evidence. The report is usable but treat highlighted claims with caution.

---

## 8. Using run history

Previous research runs are saved and listed in the **Recent Runs** sidebar on the left.

Each entry shows:

- The competitors analysed (up to 2 names, e.g. `OpenAI, Anthropic +1`)
- The quality score (e.g. `VERY HIGH` in green, `LOW` in red)
- The date and time the run was completed

**To reload a past run:**

Click any entry in the sidebar. The competitors and source URLs will be restored in the form and the full results will reappear — without re-running the pipeline.

**To refresh the history list:**

Click **↺ Refresh** next to "Recent Runs".

---

## 9. API access

The platform exposes a REST API. Interactive documentation is available at:

**[http://20.204.113.165:8000/docs](http://20.204.113.165:8000/docs)**

### Authentication

All research and history endpoints require a JWT bearer token. Obtain one first:

```bash
curl -X POST http://20.204.113.165:8000/auth/login \
  -d "username=admin&password=admin123"
```

Response:
```json
{ "access_token": "<token>", "token_type": "bearer" }
```

### Run a research pipeline (JSON response)

```bash
curl -X POST http://20.204.113.165:8000/research \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "competitors": ["OpenAI", "Anthropic"],
    "urls": ["https://openai.com/blog", "https://www.anthropic.com/news"]
  }'
```

### List previous runs

```bash
curl http://20.204.113.165:8000/history \
  -H "Authorization: Bearer <token>"
```

### Get a specific run

```bash
curl http://20.204.113.165:8000/history/<run_id> \
  -H "Authorization: Bearer <token>"
```

### Endpoint summary

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/` | — | Serves the web UI |
| `POST` | `/auth/login` | — | Returns a JWT bearer token |
| `POST` | `/research` | Bearer | Full pipeline, returns JSON when complete |
| `POST` | `/research/stream` | Bearer | Full pipeline, streams SSE events in real time |
| `GET` | `/history` | Bearer | Lists the 20 most recent runs |
| `GET` | `/history/{id}` | Bearer | Full detail of a single run |
| `GET` | `/docs` | — | Interactive Swagger UI |

---

## 10. Tips for best results

**Use specific, content-rich URLs**
The platform works best with URLs that contain full article or blog post text — not homepages or index pages. Prefer URLs like `https://openai.com/blog/gpt-4o` over `https://openai.com`.

**Supply multiple sources per competitor**
More source URLs means more evidence for the report to draw from. Aim for 2–4 URLs per competitor.

**Include recent content**
The Tavily web search discovers recent content automatically, but your supplied URLs anchor the analysis. Use recently published pages to ensure the report reflects current activity.

**Review flagged claims before sharing**
Even at `HIGH` or `MEDIUM` quality, scroll through the Claim Analysis section and verify any `PARTIALLY SUPPORTED` items against the original sources before distributing the report externally.

**Use descriptive competitor names**
The Tavily search uses the competitor name as a search query. `OpenAI` works better than `OAI`; `Google DeepMind` works better than `GDM`.

---

## 11. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| "Invalid or expired token" on page load | Session expired after 7 days | Sign in again |
| Report generation stalls at **Content Fetching** | A source URL is unreachable or returns no content | Remove the problematic URL and retry; the platform will still use Tavily-discovered sources |
| Report quality is `LOW` despite good sources | Source pages use heavy JavaScript rendering and the plain-text extraction was poor | Try linking to a print-friendly or RSS/Atom version of the page |
| Blank **Sources Analysed** list | No URLs were successfully loaded | Check that the URLs are publicly accessible and not behind a login or paywall |
| History sidebar shows "No runs yet" after a run | History failed to refresh | Click **↺ Refresh** in the sidebar |
