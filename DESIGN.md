---
name: SportIntel
description: Editorial desk for sports, iGaming and holiday news — dark-navy brand rail, one accent colour chosen by the user
colors:
  navy: "#0b1220"
  pitch-brand: "#16a34a"
  pitch-brand-dark: "#22c55e"
  pitch-bright: "#4ade80"
  ocean-brand: "#2563eb"
  violet-brand: "#7c3aed"
  graphite-brand: "#27272a"
  ai: "#2563eb"
  attention: "#facc15"
  warn: "#b45309"
  destructive: "#dc2626"
typography:
  display:
    fontFamily: "Onest Variable, ui-sans-serif, system-ui, sans-serif"
    fontWeight: 700
    letterSpacing: "-0.02em"
  body:
    fontFamily: "Onest Variable, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.9375rem"
    lineHeight: 1.625
rounded:
  sm: "4px"
  md: "6px"
  lg: "8px"
---

# Design System: SportIntel

## Overview

A calm, dense editorial tool. The brand comes from the logo: a white slanted **S** and an accent **i** on dark navy. The navigation rail is always that navy field with the mark on top, so the product is recognisable in any theme. Everything else is neutral, and **one accent colour** (chosen by the user) does the "you are here / confirmed / primary action" job.

Layout (rail · filters · list · detail) is unchanged from the earlier "Concreto" design; only palette, shape and type changed.

## Palettes

The user picks a palette in the account menu (saved in the browser, applied before first paint by `public/theme-init.js`, attribute `data-palette` on `<html>`). Each works in light and dark.

| Palette | Accent (light / dark) | AI colour | Neutral tint |
| --- | --- | --- | --- |
| **Pitch** (default, logo) | green #16a34a / #22c55e | blue | navy (hue 265) |
| Ocean | blue #2563eb / #60a5fa | violet | navy |
| Violet | violet #7c3aed / #a78bfa | blue | violet-navy (285) |
| Graphite | #27272a / #e4e4e7 | blue | pure grey |

Neutrals are computed in OKLCH from `--nh` (hue) and `--nc` (chroma multiplier), so every palette keeps the same contrast: text ≥ 4.5:1, control borders ≥ 3:1. Text on the accent fill uses `--brand-foreground` (white or navy, whichever passes).

### Tokens
- `--brand` / `bg-primary`: primary buttons, high trust badge, independent source blocks, active switch.
- `--brand-text`: accent as text, links, checked filter chips, confirmation squares, focus ring.
- `--brand-bright`: accent on the dark rail and in the logo's **i**.
- `--ai`: AI marks and editorial approval (Select, Ready, Published).
- `--attention` (yellow): "look here" only — new-events bar, high importance, degraded-status banner.
- `--warn`: low trust, rumour, clickbait, stale.

### Named rules
**One accent.** The accent marks selection, confirmation and the primary action. Never decoration.
**Level without colour.** Every badge pairs an icon with text (WCAG 1.4.1).

## Logo

`shared/ui/brand-mark.tsx` holds the vectorised mark (paths traced from the original artwork). `BrandMark` = S in `currentColor` + i in a soft gradient of `--brand-bright`; `BrandLogo` adds the "Sport**Intel**" wordmark. Both follow the palette. `public/favicon.svg` is the mark on navy; `syncFavicon()` recolours it to the current palette.

## Typography

Onest Variable for everything. Titles (`.font-display`) use weight 700–800 with -0.02em tracking, close to the logo wordmark. Tabular numerals for times, counts and tables.

## Shape & elevation

Radius 6px on buttons and inputs, 4px on badges and chips, 8px on cards and dialogs. Floating layers (menus, popovers, selects, dialogs) get a 1px border plus `shadow-float`. The selected list row is an accent tint with a 3px accent bar on the left.

## Motion

Strong ease-out `cubic-bezier(0.23, 1, 0.32, 1)` for entrances, nothing on keyboard navigation (j/k), everything has a reduced-motion variant.
- **New events:** after clicking "N new events", existing rows slide down (240ms ease-out) and new rows fade in from -10px (240ms, 80ms delay, 45ms stagger), then an accent tint fades out over 1.8s. Reduced motion: only the tint.
- **Logo:** assembles once on mount (S slides in, i rises, dot drops; 520ms).
- **Palette/theme switch:** colours crossfade for 200ms.
- Button press scale 0.97 (140ms); source blocks compose in sequence (180ms, 30ms apart); autopost switch knob slides (200ms).

## Don'ts
- Don't use a Tailwind palette colour (`bg-green-500`) — use tokens, or palettes break.
- Don't put the brand mark on a light background — it is drawn for the navy field.
- Don't use emoji as icons; use lucide.
