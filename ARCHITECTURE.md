# ARCHITECTURE.md

Revenue Manager Agent for the Grand Harbour Hotel GM. Pipeline:
**Playwright ETL → Supabase Postgres (facts + lookups + 2 views) → 5 typed tools →
Deep Agent (skills, subagent, planning, memory, HITL) → FastAPI streaming chat.**

## 1. ETL boundary
- **Extract** (`etl/scrape.py`): Playwright drives the client-rendered site. Paginate
  `/reservations` (100/page, client-side pagination → wait on the "Page X of N"
  indicator + a stabilised row-count read; ids are format-agnostic, not sequential),
  drill into each `/reservations/<id>` for detail-only fields and the per-night stay
  rows, and read the 5 reference tabs + `/verify` JSON.
- **Transform** (`etl/transform.py`): expand to one row per `reservation × stay_date`;
  reservation-level fields broadcast to each night, `financial_status` is per stay row;
  type coercion; `—` → NULL.
- **Load** (`etl/load.py`): idempotent truncate-and-reload in one transaction (FK-safe
  order), one `load_manifest` row per run, `row_hash` = sorted
  `reservation_id|stay_date|financial_status` sha256.
- **Verify**: `compute_load_fingerprint.py` → `etl/LOAD_PROOF.json`; `row_hash` matches
  `/verify` `reservation_stay_status_sha256` exactly; `SCRAPE_MANIFEST.json` reconciles
  ids/count. Anchor date recorded (regenerates daily → reconcile on scrape day).
- **Data-quality decision:** bookings carry granular rate codes beyond the 8-row
  `rate_plan_lookup`, so the brief's `rate_plan_code` FK is unsatisfiable — dropped via
  `sql/relax_fk.sql` (other dims verified clean by `integrity_report`). See
  `etl/SITE_NOTES.md`.

## 2. Database and views
Supabase Postgres (hosted; dev = prod). `sql/views.sql` sits between tools and raw
tables — agent-facing tools read **only** these views, never `reservations_hackathon`:

- **`vw_stay_night_base`** — the default OTB universe: `financial_status = 'Posted'`
  **and** `reservation_status <> 'Cancelled'`. Backs `get_otb_summary` (default),
  `get_pickup_delta`, `get_block_vs_transient_mix`.
- **`vw_stay_night_posted`** — Posted only, *cancelled rows retained*. Backs the
  include-cancelled path (`get_otb_summary(exclude_cancelled=False)`) and the
  point-in-time rebuild (`get_as_of_otb`), which need cancelled rows and
  `cancellation_datetime`. Exists so those tools never touch the raw table.
- **`vw_stay_night_with_provisional`** — `financial_status in ('Posted',
  'Provisional')`, all statuses. Backs the explicit include-provisional path
  (`get_otb_summary(include_provisional=True)`); the tool applies the cancelled
  filter on top. Provisional stays excluded everywhere else.
- **`vw_segment_stay_night`** — `vw_stay_night_base` plus `market_name` and
  `effective_macro_group`, computed by a lateral join on `market_macro_group_history`
  over `stay_date ∈ [valid_from, valid_to)` so a reclassified market rolls up to the
  macro group that was effective on the stay date (not the static lookup value).

## 3. Tool layer (`tools/rm_tools.py`)
Five typed tools, parameterised SQL, no raw-SQL parameter, grain in every docstring:
`get_otb_summary`, `get_segment_mix`, `get_pickup_delta`, `get_as_of_otb`,
`get_block_vs_transient_mix`. Default OTB = exclude Cancelled + Provisional; room
nights = `sum(number_of_spaces)`; reservations = `count(distinct reservation_id)`;
pickup window = Europe/London midnight boundaries in UTC. Definitions in
`tools/METRIC_DEFINITIONS.md`. Arbitrary SQL is never exposed so the model cannot get
grain, cancellation, or date/revenue fields wrong.

**Documented exception:** two universes lie *outside* the OTB-filtered views by
definition and read the raw fact table directly — `get_otb_summary(exclude_cancelled
=False)` (needs cancelled rows the view strips) and `get_as_of_otb` (the brief's own
spec requires `reservation_status <> 'Cancelled' OR cancellation_datetime > as_of`).
These remain fully owned: parameterized SQL, no model-supplied SQL, business rules
baked in.

## 4. Deep Agents wiring (`agent/build_agent.py`)
| Building block | Use |
|---|---|
| Tools | Five named tools — no `run_sql` |
| Skills | `skills=["skills"]` via `FilesystemBackend` — 8 `SKILL.md`, progressive disclosure |
| Subagents | **segment-analyst** (task tool) — only `get_segment_mix` + `get_block_vs_transient_mix` |
| Planning | `TodoListMiddleware` decomposes multi-part questions |
| Memory / filesystem | `InMemorySaver` checkpointer + `InMemoryStore` → multi-turn |
| Human-in-the-loop | `interrupt_on={"get_as_of_otb": True}` — approval before point-in-time rebuild |
| Model & system prompt | `MODEL_ID` (Gemini default, swappable); sharp RM persona, brief §12 answer style |

## 5. Skill → tool routing matrix
| Skill | Primary tool(s) | Judgment? |
|---|---|---|
| otb-summary | get_otb_summary | N |
| segment-mix | get_segment_mix (subagent) | N |
| ota-dependency | get_segment_mix | **Y** (OTA share >35% → shift direct) |
| pickup-pace | get_pickup_delta, get_otb_summary | **Y** (7d <25% of 14d pickup → stimulate) |
| block-concentration | get_block_vs_transient_mix | **Y** (top-3 >30% / block >40% → de-risk) |
| pricing-adr | get_otb_summary, get_segment_mix | **Y** (ADR gap >10% / ADR<120 → hold/close) |
| cancellation-watch | get_otb_summary, get_as_of_otb | **Y** (cancel rate >15% → reprice risk) |
| data-guardrails | any | N (adversarial: grain / property_date / cancelled+provisional) |

## 6. Tests
- `tests/test_etl.py` (4): lookup counts, grain uniqueness, manifest reconciliation, expansion.
- `tests/test_tools.py` (14): scenarios 1–6, 8–12 against loaded DB.
- `tests/test_skills.py` (7): pack pin, count, judgment thresholds, tool routing, distinctness, guardrail, concentration — no LLM.
- `tests/test_agent.py` (10): fixed 5-tool surface, HITL on `get_as_of_otb`, isolated subagent, on-demand skills, memory configured, planning, coverage ranges — graph introspection, no LLM.
- `tests/test_auth.py` (8): token verification, `require_auth` (missing/invalid/valid bearer), `/config`, per-user thread namespacing — GoTrue mocked, no network.

## 7. Deployment topology
Supabase Postgres ← FastAPI agent container (always-on) → browser chat. UI streams
tool/skill events (skill load = a file-read tool call). `GET /health` returns
`db_fingerprint`, `dataset_revision`, `row_hash`, `financial_status_posted_only_rows`
from `LOAD_PROOF`/live DB. Auth is Supabase (username+password, invite-only); the
backend verifies each request's access token via GoTrue and namespaces conversations
per user. API keys via env, never committed.

## 8. Out of scope (deliberate)
Daily scrape cron (once-per-build + same-day reconcile is sufficient); UI polish
(streaming visibility matters, not styling); MCP servers (optional bonus); multi-hotel.
