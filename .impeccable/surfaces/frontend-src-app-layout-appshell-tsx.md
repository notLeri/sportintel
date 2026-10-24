---
version: 1
slug: "frontend-src-app-layout-appshell-tsx"
primary_target: "frontend/src/app/layout/AppShell.tsx"
related_targets: ["frontend/src/pages/dashboard/DashboardPage.tsx","frontend/src/styles.css"]
---

Scope: the whole SportIntel web app (shell + dashboard first; feed, event page, articles, analytics, admin, login inherit). Mode: Operate.
Audience: sports news editor in the flow, desktop all day, keyboard-first; also phone for approving posts.
Constraints: high density in event list; light + dark following OS with manual switch; hints on every badge/score/action; en/ru/pt-BR.

## Direction contract

THESIS: The editorial desk built like a Brazilian concrete-art poster: flat fields of flag green, a strict grid, and trust drawn as geometry. Refuses the grey SaaS dashboard with a lone accent button.

OWN-WORLD: Flag green #009C3B owns the navigation rail and the selected state as a full flat field; ground is a cool green-tinted off-white (dark: deep green-black); ink near-black. Flag yellow marks attention (new events, high-importance tick); flag blue marks AI and primary editorial approval. Square corners everywhere (radius 0–2px), 1.5px hard borders, no shadows, no gradients. Losango (rotated square) only in the brand mark. Onest (UI, Cyrillic, tabular numerals) on a strict size ladder; Unbounded (wide geometric) only for page titles, the event title and the wordmark. Archivo was dropped: no Cyrillic.

STORY: The editor sees which events matter, how many independent outlets confirm each one (counted in squares), selects one, reads the confirmation composition and brief, and ships the Telegram post without leaving the screen.

FIRST VIEWPORT: Left 72px green rail with mark and nav; filters column; dense event list with search on top, yellow "new events" bar, rows with a left importance bar, title, square-count confirmation strip, relative time right-aligned; selected row is a full green field. Right: event detail with kicker chips, condensed bold title, the confirmation composition (one block per source, filled = independent, outlined = reprint), lead, actions.

FORM: Concreto (Brazilian concretismo graphic design), position 4 of my ordered list, seed key b2035dd7. Signature move: the confirmation squares — small in the row, a full composition in the detail; new events slide in as a yellow block.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
