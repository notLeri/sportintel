# ADR-004. Rules and templates first; a local LLM is an optional booster

- **Status:** accepted
- **Date:** 2026-10-07
- **Affects:** product requirements, ARCHITECTURE §1.3 / §19, the AI-related parts of the pipeline (table below), the "fake Telegram" feed

## Context

The project must work **without spending money**. In the original design every "smart" operation depended on paid APIs: Claude (enrichment, the clustering grey zone, summary, draft, conflicts) and Voyage (embeddings). It is not yet known whether the editorial team needs AI at all: unique events and neatly formatted post templates that a person picks and finishes may be enough.

## Decision

1. **The base mode is `rules`: free and fully deterministic.** Every pipeline step that used AI gets a rule-based implementation:

   | Step | `rules` mode (default) | `llm` mode (optional) |
   |---|---|---|
   | Article enrichment (`enrich_article`) | `RuleEnricher`: sport by URL section, RSS categories and a dictionary; entities and competition by reference-data aliases; rumour and clickbait markers by dictionaries; relevance by the weighted `enrich_rules` | Prompt `enrich_article/v1` |
   | Embeddings | None (`embedding = NULL`) | A local model via Ollama (`bge-m3`, 1024) |
   | Clustering candidates and scoring | Lexical title similarity (pg_trgm) + shared entities + competition + time window; syndication detection | + cosine against the centroid |
   | Clustering grey zone | A new event is created with a `possible_duplicate` link to the best candidate; a person merges | Prompt `cluster_adjudicate/v1` |
   | Event summary and neutral title | Extractive: title and lead of the **main article** (OFFICIAL → earliest tier A → earliest), `TextOrigin=source` | Prompt `event_summary/v1` + grounding |
   | Telegram draft | **Template** (`TemplateDrafter` → the same `DraftOutput` → the same `assemble`), `TextOrigin=template` | Prompt `telegram_draft/v1` + grounding |
   | Source conflicts | Off (claims are not extracted in rules mode) | Job `events.detect_conflicts` |

2. **A "fake Telegram" feed.** For every unique event with relevance ≥ `drafts.auto_min_relevance` the system prepares a template draft **by itself**. Drafts are shown on the `/feed` page as Telegram channel messages. The **"Suggestions"** tab holds events nobody has picked yet. The **"Channel"** tab shows `READY`/`PUBLISHED` posts as the channel would look to a reader. A user takes a message, edits it, copies it and marks it as published, or rejects it. An automatic draft **does not change the event's status**: it is a suggestion, not a decision.

3. **A local LLM is turned on with one switch, without changing module code.**
   - **Where the LLM runs (infrastructure, env).** `AI_PROVIDER=ollama`, `OLLAMA_URL` points at any machine running [Ollama](https://ollama.com): the same VM, a separate local VM or server, a developer's laptop (over a tunnel such as Tailscale). The default model was `qwen2.5:7b-instruct` (good Portuguese; the current default is `qwen3:14b`), embeddings `bge-m3` (dimension 1024 matches the schema).
   - **Which steps use it (business, `app_settings.ai_routing`).** Each step is `rules|llm`, the draft is `template|llm`. An admin switches steps in the UI without a redeploy. This allows turning the LLM on gradually, starting with the most useful step, and comparing quality.
   - **Maximum mode.** With the LLM on for every step (`drafts.auto_mode=llm`), the feed receives posts already written by the model with `[n]` citations, and a person only has to review them and click "Copy".
   - **Degradation.** If the LLM is unavailable (timeout, circuit breaker, an invalid answer after repair), the step **falls back to rules or a template automatically** instead of failing. `/me.system_status` shows "LLM offline, running on rules".

4. **Paid providers stay as ports but are not implemented in the MVP.** The Anthropic and Voyage adapters, a dollar budget and prices (`ai_pricing`) are postponed until there is a budget. The `LlmClient` and `EmbeddingClient` ports do not change, so adding them later means only a new adapter. (The Anthropic adapter has since been implemented.)

5. **Order of work.** The `rules` path is built first, giving a working product without an LLM. The LLM branches of every step are grouped into an optional phase that runs afterwards, or in parallel if needed.

## Why

- **Zero cost at the start.** No API keys. The LLM, if needed, is free because it runs on your own hardware.
- **A cheap hypothesis test.** If templates and rules are enough, AI is not needed at all. If not, it becomes clear at which step it pays off: analytics show the share of edited drafts and HIGH precision per mode.
- **Predictability.** Rules are explainable (rationale = the list of rules that fired) and easy to edit in the admin. No hallucinations: a template quotes the source verbatim.
- **The architecture barely changes.** The contracts `EnrichOutput`, `DraftOutput`, `assemble`, `clustering.score` (the mode without embeddings already existed) stay the same. Only implementations and routing change.

## Alternatives

- **Claude from day one with a hard budget.** Costs money, and it is unknown whether it is needed.
- **Only a local LLM, no rules.** Needs hardware (a 7B model on CPU takes tens of seconds per article) and gives unpredictable quality. Without rules there is no fallback, and the pipeline stops when the LLM goes down.
- **Local embeddings without an LLM (sentence-transformers in the worker).** Possible, but pulls torch into the image (~1–2 GB) and loads the worker CPU. Ollama isolates models in a separate process or machine. This option can be revisited later through the same `EmbeddingClient` port.

## Trade-offs and risks

- **Clustering without embeddings** is worse at merging articles about one fact with different titles. Mitigation: `possible_duplicate` links, manual merge, threshold calibration (ADR-003) on real data.
- **Rule-based relevance** is coarser than a model. Mitigation: an admin edits the weights in `app_settings`, an override in the UI, measuring HIGH precision.
- **A template draft** is a starting point, not a finished post. A person finishes it. The "share of edited drafts" metric shows whether `telegram_draft=llm` is worth turning on.
- **Source conflicts** are not detected in `rules` mode; this works only with the LLM on. A deliberate narrowing of the MVP: reliability still limits trust in single and rumour sources.
- **A local LLM is slow on CPU.** The `ai` queue for Ollama runs with concurrency 1 (`OLLAMA_CONCURRENCY`). Interactive generation may take a minute; the frontend shows progress, and the template version is available immediately.

## When to revisit

- In a pilot, more than 80 % of template drafts get edited or HIGH precision is below 60 %: turn the LLM on for that step.
- A budget appears and quality above a local model is needed: implement the paid adapters and a budget.
