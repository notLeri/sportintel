# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary: a sports news editor working "in the flow" — the app is open on a desktop all day; they triage clustered events, check source trust, generate AI briefs and approve Telegram posts, mostly from the keyboard (j/k, Enter). They also approve posts and glance at events from a phone, so mobile must work.

Secondary roles: researcher (reads, searches) and admin (sources, taxonomy, channels, settings).

## Product Purpose

SportIntel collects sports, iGaming and holiday news from RSS/HTML sources, clusters articles into events, rates relevance and source trust, writes grounded AI briefs (ru/en) and publishes posts to Telegram channels — with editor approval or automatically. Success: an editor understands what happened, how trustworthy it is, and ships a correct post in seconds.

## Positioning

Not a news reader: an editorial desk. Every event shows how many independent outlets confirm it and what the AI plausibility check says, and every brief links its claims back to source articles by code, not by model memory.

## Operating Context

Long desktop sessions, three-pane dashboard (filters · event list · event detail), keyboard hotkeys, live polling for new events. Telegram is the publishing destination; posts are previewed in Telegram formatting. UI languages offered in the switcher: en (default) and ru (product decision 2026-10-09). pt-BR is the base dictionary for tests and enum translations, not a user-facing choice.

## Capabilities and Constraints

- Roles: researcher → editor → admin.
- Rules-first, zero-budget: works without paid AI; LLM via local Ollama.
- High data density in the event list is required; no airy landing-page layouts in the app.
- Light and dark themes, following the OS, with a manual switch.
- Every element must be self-explanatory: hover hints on badges, scores, filters, buttons; on touch, visible labels instead of hover; en/ru copy must read naturally.

## Brand Commitments

- Name: **SportIntel** (keep).
- Logo: "Si" mark + SportIntel wordmark (white S, green i, dark navy). Green is the default accent; users may switch the accent palette (Pitch, Ocean, Violet, Graphite) — 2026-10-10 decision, away from the Brazil-flag style.

## Product Principles

1. Clarity before cleverness: the meaning of every badge, score and action is obvious or one hover away.
2. Trust is visible: confirmation, source trust and AI involvement are always marked, never implied.
3. Speed of the flow: keyboard-first, dense, no extra clicks between seeing an event and shipping a post.
4. Same product on a phone: approve and read without the desktop.

## Accessibility & Inclusion

Text contrast ≥ 4.5:1; levels are readable without color (icon + text, WCAG 1.4.1); full keyboard operation; respect prefers-reduced-motion.
