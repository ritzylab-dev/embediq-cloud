# UI design system — contributor reference

The admin UI is server-rendered Jinja2 with a hand-authored design system in
`app/static/design-system.css` and vanilla ES modules. There is no build step and no CSS
framework. The binding visual contract is `pm/knowledge/UI_DESIGN_SPEC.md`; this page is the
short how-to for working inside the system.

## Tokens

All design values are CSS custom properties on `:root`, with a dark override under
`[data-theme="dark"]`. Read them; never hard-code a hex value in a component.

- Color: `--blue`, `--blue2`, `--lime`, `--lime2`, `--ink`, `--text`, `--muted`, `--bg`, `--card`, `--line`.
- Semantic: `--ok`, `--warn`, `--danger`, `--info`, plus tint variants (`--tint-ok`, `--tint-warn`, `--tint-danger`, `--tint-info`).
- Type: `--sans` (Nunito), `--mono` (JetBrains Mono).
- Space: `--s1`…`--s7` (4 / 8 / 12 / 16 / 24 / 32 / 48 px).
- Radius: `--r-card` (13px), `--r-pill` (999px), `--r-tile` (12px).
- Elevation: `--e1`, `--e2` (cards), `--e3` (popovers). Motion: `--motion` (160ms ease).

## Theme

The theme is `data-theme="light|dark"` on `<html>`. A pre-paint script in `base.html` sets it
from `localStorage` (key `embediq-theme`) before first paint to avoid a flash. The sidebar
toggle flips it and persists the choice. Anything theme-dependent must come from tokens so it
recolors for free.

## Component classes

Use these instead of writing ad-hoc styles.

- Buttons: `.btn` with `.btn-primary` (gradient), `.btn-ghost`, `.btn-danger`; add `.btn-sm` for the compact size.
- Status pills: `.pill` plus `.pill-online`, `.pill-offline`, `.pill-warn`, `.pill-danger`.
- Cards: `.card` with `.card-head` and `.card-body`.
- KPI stat: `.stat` with `.stat-label`, `.stat-value`, and an optional `.stat-trend` chip.
- Tables: `.table-wrap` around `table.table` (uppercase headers, hover row tint, sticky head).
- Forms: `.label`, `.input`, `.select`, `.textarea` (add `.mono` for code).
- Key/value lists: `<dl class="kv">` for status and health panels.
- Empty state: `.empty` (icon tile, one line of copy, optional call to action).
- Skeleton: `.skeleton` with `.skeleton-line` or `.skeleton-stat` while loading.
- Console accent: `.console` for log and activity surfaces.
- Toast: created at runtime by `toast(message, variant)` in `app.js`.
- Modal: markup is `.modal` > `.modal-card` > `.modal-head` / `.modal-body` / `.modal-foot`; wire it with `createModal(el)`.

## Layout and shell

`base.html` is the app shell: a fixed left sidebar (brand wordmark, nav, theme toggle and
sign-out) and a slim top bar over the ambient background. Pages extend it and fill these blocks.

- `{% block page_title %}` — the top-bar title.
- `{% block actions %}` — top-bar contextual actions (refresh, filters).
- `{% block content %}` — the page body.
- `{% block scripts %}` — the page module, loaded with `defer` so it runs after `app.js`.

Each page route passes an `active` value so the sidebar highlights the current item. Under
960px the sidebar becomes an off-canvas drawer opened by the top-bar hamburger.

Use the 12-column grid for page layout: `.cols` with child span classes `.s3`, `.s4`, `.s5`,
`.s6`, `.s7`, `.s8`, `.s12`. Every span collapses to full width under 960px.

## Theming a chart

Charts use Chart.js (pinned with SRI in `base.html`). To keep a chart on-brand and
theme-aware, follow this pattern.

1. Read the live token values with `chartTokens()` from `app.js`.
2. Apply them to datasets (brand cyan or lime), ticks and grid (`--muted`, `--line`), and the Nunito font.
3. Re-render on theme change: listen for the `themechange` event and rebuild the chart with fresh tokens.
4. When there is no data, show the `.empty` component instead of an empty axis. Telemetry-backed charts must degrade to this under `scripts/dev.sh`, where no metrics stack is running.

See `app/static/overview.js` for a working example (the firmware-distribution bar chart).
