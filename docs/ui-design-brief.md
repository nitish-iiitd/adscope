# AdScope — UI/UX Design Brief (prompt for Claude design)

> **How to use:** paste the block below into Claude (design/artifact mode). If the
> tool asks to narrow scope, have it deliver **design system + components first**,
> then the screens — starting with the **Query Review editor** and **Campaign
> Results**, the two signature screens. Bring the output back here and it will be
> ported into the FastAPI + Jinja2 templates (replacing Bootstrap) with all current
> behavior preserved.

---

```
You are a senior product designer. Design a complete, professional UI/UX and a
reusable design system for an internal B2B web app called AdScope. Deliver
production-quality visual design I can implement directly.

## What AdScope is
AdScope is an internal media-planning tool for advertising teams. Given a campaign
brief, it predicts the questions a target audience would ask AI assistants (ChatGPT,
Gemini, etc.), then discovers which websites those assistants would cite to answer —
producing a ranked list of publishers where the brand should advertise. It queries
several AI models at once and combines their answers by consensus. There is a
deliberate human-review step in the middle of the pipeline.

The pipeline has five stages:
  Brief → AI drafts audience questions → HUMAN reviews/edits questions → AI finds
  websites per question → single ranked list of publishers.

## Users & tone
Media planners and account managers at an agency. Professional, data-forward, calm,
trustworthy, premium. Not playful, not flashy. This is a tool people operate daily,
so clarity and scannability beat decoration. It must feel like considered enterprise
software, not a generic Bootstrap admin template.

## Core UX challenge to solve well
The pipeline is asynchronous with a human gate, so the app moves through PHASES and
several screens have LOADING/POLLING states. Design these states as first-class, not
afterthoughts:
  - "Generating questions" (AI working, page auto-refreshes)
  - "Awaiting review" (human editing questions)
  - "Discovering websites" (AI working, page auto-refreshes)
  - "Completed", "Completed with warnings", "Failed", and "Empty (no results)"
Make phase/progress legible at a glance. A subtle phase indicator/stepper reflecting
the five stages would help users always know where a campaign is.

## Screens to design (use REAL content shown below, never lorem ipsum)

1. LOGIN — minimal username/password card. App name/logo. One clean, confident screen.

2. DASHBOARD — top: three stat tiles (Total campaigns, Completed, Failed). Below: a
   table/list of recent campaigns with columns: Campaign name, Client, Status (as a
   colored pill: Processing / Awaiting review / Completed / Completed with warnings /
   Failed), Created date, and a link to open. Include an empty state ("No campaigns
   yet"). Primary action: "New campaign".

3. NEW CAMPAIGN FORM — fields: Client name, Campaign name, Client briefing (large
   textarea), Target country, Objective (optional), Budget (optional). Plus a
   collapsible "Advanced: pipeline sizes (optional)" section with three small number
   inputs: Queries per model (default 10), Websites per query (default 10), Final list
   size (default 50), each showing its default as placeholder. Primary button:
   "Generate audience queries". Include inline validation error styling and a submit/
   loading state.

4. QUERY REVIEW — GENERATING STATE — shown while AI drafts questions. A clear,
   reassuring "Generating audience queries" progress screen (spinner/animation +
   explanatory copy). Auto-refreshes.

5. QUERY REVIEW — EDITOR STATE — the human-in-the-loop screen. A list of ~30 draft
   questions. Each row has: a select checkbox, an editable multi-line text field, a
   small source label (e.g. "from gemini" / "Custom"), and a remove button. Controls
   to "Add query" (adds a blank custom row) and submit ("Find websites for selected
   queries"). This is the signature screen — make editing feel effortless and the bulk
   list easy to scan and act on. Show a helpful instruction banner.
   Example questions:
     "What are the best premium organic skincare brands in India right now?"
     "Which face serums work well for humid monsoon weather?"
     "Where do beauty editors recommend shopping for skincare online?"

6. CAMPAIGN RESULTS — PROCESSING STATE — shown while AI discovers websites. Progress
   screen ("Discovering websites") plus a read-only list of the queries being analysed
   so the user can review them while waiting. Auto-refreshes.

7. CAMPAIGN RESULTS — COMPLETED — the payoff screen. Layout:
   - Header with campaign name + client + breadcrumb.
   - Optional alert banner for "Completed with warnings" or "Failed".
   - A "Campaign briefing" card and a "Queries analysed" list.
   - An "Analysis summary" panel: Target country, Objective, Budget, Queries analysed,
     Unique websites, Analysis date, Successful providers (green pills), Failed
     providers (red pills).
   - THE MAIN TABLE: "Recommended publishers" with columns: Rank, Website, Domain,
     Category, Final score (0–100, visualized as a score pill/meter), Queries (breadth
     count), Models (agreement count), Breadth (High/Medium/Low badge), Main reason,
     and a "Details" action. Design the two ranking signals — BREADTH (how many
     questions surfaced the site) and AGREEMENT (how many AI models named it) — as a
     clear visual motif; they are the heart of the product.
   - A "Export CSV" button and an advisory disclaimer note.
   Example rows:
     1 · Vogue India · vogue.in · Fashion & Lifestyle · score 90 · Queries 4 · Models 3 · Breadth High
     2 · Nykaa · nykaa.com · Beauty & Commerce · score 88 · Queries 4 · Models 3 · Breadth High
     3 · Femina · femina.in · Women's Lifestyle · score 82 · Queries 3 · Models 2 · Breadth Medium

8. WEBSITE DETAIL DRILL-DOWN (modal or side panel) — for one publisher, show its final
   score, breadth, agreement, and a per-query breakdown: which audience questions
   surfaced this site and which models named it. This is the "transparency / no black
   box" moment.

9. EMPTY & ERROR STATES — "No recommendations available" empty state, and a generic
   error page. Make them on-brand, not default browser errors.

## Design system to deliver
- Color: a deliberate palette (primary accent + chosen neutrals, not default grey) and
  SEPARATE semantic colors for status (success / warning / critical / info / neutral)
  used for the status pills and provider badges. Define everything as design tokens.
- Typography: a clear type scale with distinct roles (display/heading, body, and a
  mono/tabular face for data, scores, and counts — tabular numerals for the table).
- Components: buttons (primary/secondary/ghost), inputs & textareas (+ error state),
  cards/panels, the recommendations table, status pills, score pill/meter, breadth &
  agreement badges, phase stepper/progress, modal/side panel, alert banners, loading/
  spinner states, empty states, navbar.
- Spacing scale, radii, elevation/shadow, and focus-visible styles.
- Full LIGHT and DARK themes with equal care.
- Responsive down to mobile (tables should scroll horizontally in their own container,
  never break the page layout). Accessible: WCAG AA contrast, visible keyboard focus,
  reduced-motion support.

## Recommended brand direction (you may refine, but keep it cohesive)
"Analyst's ink & signal": chosen green-biased neutrals (not flat grey), a single
confident deep TEAL as the primary accent/brand color, and a restrained AMBER as a
SECONDARY signal used specifically for the Breadth vs. Agreement ranking motif (two
genuine measures, two hues). Editorial serif for headings, clean sans for body, mono
for data/scores. The identity should evoke a precise instrument that reveals where
audience attention sits — calm, premium, trustworthy. Avoid: generic Bootstrap looks,
purple/blue gradients, cream+terracotta, neon, emoji as UI, everything-centered, and
rounded-card-with-left-accent-bar clichés.

## Output & technical constraints (important — this ships into a real codebase)
- The app is server-rendered (Python FastAPI + Jinja2 templates), currently styled
  with Bootstrap which I will REPLACE with your system. So:
  - Deliver STATIC HTML for each screen using ONE shared, self-contained CSS design
    system: design tokens as CSS custom properties on :root, plus plain CSS component
    classes. NO Tailwind, NO utility-class soup, NO React or any JS framework, NO build
    step. Vanilla JS only for interactions (e.g. add/remove query rows, open modal).
  - Structure the CSS so it maps to reusable components/partials (navbar, card, table,
    pill, badge, form-field, modal, alert, empty-state, loading-state).
  - Light/dark via CSS variables and prefers-color-scheme + a [data-theme] override.
- Provide: (1) the design tokens/system, (2) a component reference sheet, and (3) each
  screen rendered with the real example content above, in both themes.
```

---

## After you receive the design

Bring the output back (HTML/CSS, token values, or screenshots) and it will be
incorporated as follows:

1. Extract the design system into `app/static/css/app.css` as CSS custom properties +
   component classes (replacing Bootstrap).
2. Re-skin every Jinja template — `base`, `login`, `dashboard`, `new_campaign`,
   `review`, `campaign_detail`, `results`, `error` — to the new components.
3. Preserve all current behavior: phase polling, the JS query-row editor, the details
   modal, form validation, and CSV export.
4. Run the test suite and a live demo pass to confirm nothing broke.
