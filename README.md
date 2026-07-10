# Seller Operations Agent (REAL opperation driven commercial product, with users. Not a portfolios)

An autonomous, multi-tenant operational agent for e-commerce sellers. Built on a platform adapter architecture, it is designed to work across multiple marketplaces — Amazon, Shopify, Lazada, Tiki, and others — where each platform is a pluggable adapter that translates platform-specific events and APIs into the agent's internal model. Amazon SP API is the first adapter implemented.

The agent monitors seller activity in real time, classifies operational signals, and runs them through a per-seller policy engine to determine risk. Low-risk decisions are executed automatically against the platform's API. High-risk decisions are escalated to the seller via Slack with one-click Approve/Reject. Every event, decision, and outcome is persisted for full auditability. Multiple sellers are fully isolated: separate policies, separate platform credentials, separate Slack channels, one deployment.

---

## Vision

Amazon sellers generate a constant stream of operational signals — low inventory, unusual order spikes, abnormal refund rates. Today these are handled manually: sellers log into Seller Central, check dashboards, place restock orders, and investigate anomalies themselves. This is slow, reactive, and does not scale.

This agent sits between the platform and the seller, acting as an autonomous ops engineer:

- **Reacts** to operational events in real time
- **Decides** autonomously based on seller-defined policy thresholds
- **Executes** low-risk actions without human input
- **Escalates** high-risk decisions to the seller via Slack, waits for approval, then executes
- **Anticipates** problems and opportunities before they surface — powered by AI-driven insight signals

The end state: a seller connects their Slack and platform credentials once. From that point, the agent manages their day-to-day operations — only pinging them when something genuinely requires a human decision, and proactively surfacing what they would never have caught themselves.

---

## Architecture Overview

```
Platform Webhooks (Amazon SP API, Shopify, Lazada, ...)
        |
        v
POST /webhooks/{platform}      <- Layer 1: domain facts (orders, shipments)
POST /events                   <- Layer 2: monitoring signals (low inventory, spikes, refunds)
[Scheduled AI jobs]            <- Layer 3: business insight & proactive signals
        |
        v
  BackgroundTask
        |
        v
+------------------------------------------+
|              Pipeline                    |
|  1. classifier  -> Intent                |
|  2. policy      -> PolicyResult (risk)   |
|  3. executor    -> ExecutionStatus       |
|                                          |
|  LOW risk  -> Platform API (auto-exec)   |
|  HIGH risk -> AI agent analyst   + Slack |
+------------------------------------------+
        |                    |
        v                    v
  API Result            Slack message
  saved to DB           with Approve/Reject buttons
                             |
                             v
                    POST /slack/interactions
                    (seller clicks button)
                             |
                             v
                    Approval resolved in DB
                    Platform API call executed
```

---

## Three-Layer Event Model

Events are split into three layers with different origins and semantics:

| Layer | Source | Event Types | Pipeline behavior |
|---|---|---|---|
| **Domain (L1)** | Platform webhooks | `order_created`, `order_paid`, `order_shipped`, `order_canceled` | Record only — no decision |
| **Monitoring (L2)** | Platform webhooks | `inventory_low`, `order_spike_detected`, `high_refund_rate_detected` | Full decision pipeline |
| **Insight (L3)** | Internal AI jobs | Predictive & strategic signals | Full decision pipeline |

### Layer 1 — Domain Events
Raw facts from the platform. Stored for audit and history. No decision is made — these are the ground truth record of what happened.

### Layer 2 — Monitoring Events
Derived operational signals that require a response right now. Triggered by a single platform event crossing a threshold. Runs the full decision pipeline immediately.

### Layer 3 — Business Insight & Proactive Signals
AI-generated signals that emerge from patterns over time, not from a single event. These are the most creative and highest-value signals — things the seller would never catch manually. (DELAYED)

**Risk signals:**
- Refund rate climbing 2% per week for 3 consecutive weeks — flag before it hits the threshold
- Top SKU has had zero reorders in 60 days but order volume is trending up — stockout incoming
- Competitor pricing dropped significantly in the same category — seller conversion will be affected

**Opportunity signals:**
- Same week last year this seller's orders spiked 4x — pre-position inventory now before peak
- SKU has 94% positive reviews and low inventory — strong candidate for ad spend increase
- Two SKUs have high individual refund rates but strong co-purchase signals — bundle opportunity

**How Layer 3 fits the architecture:**
A scheduled AI job reads from the `events` table and broader seller data, runs analysis (LLM + statistical models), and emits a Layer 3 signal back into the same pipeline. The classify → policy → execute → escalate flow handles it identically to Layer 2. The only difference is the signal origin — internal intelligence, not an external webhook. The LLM is not making the final decision; it is generating the insight that the policy engine then evaluates.

---

## Decision Pipeline

Every Layer 2 and Layer 3 event runs through a four-stage pipeline:

### 1. Classifier (`app/engine/classifier.py`)
Maps `EventType` → `Intent`. Currently rule-based for Layer 2. Layer 3 signals carry their intent directly from the AI job that generated them. Planned extension: LLM-based classification for conversational/unstructured inputs.

| Event Type | Intent |
|---|---|
| `inventory_low` | `reorder` |
| `order_spike_detected` | `flag_order_spike` |
| `high_refund_rate_detected` | `flag_refund_rate` |

### 2. Policy Engine (`app/engine/policy.py`)
Evaluates intent + seller policies + event payload → `PolicyResult` with a `RiskLevel`. Each seller defines their own thresholds:

```
InventoryPolicy:
  reorder_point             - trigger threshold (units)
  reorder_quantity          - how many units to reorder
  auto_approve_max_units    - max units before requiring approval
  auto_approve_max_spend    - max spend before requiring approval
  unit_cost                 - cost per unit

OrderSpikePolicy:
  auto_approve_max_multiplier - max spike ratio before escalation

RefundRatePolicy:
  auto_approve_max_rate     - max refund rate fraction before escalation
```

Risk logic:
- `LOW` — all thresholds satisfied → auto-execute
- `HIGH` — any threshold exceeded → escalate for approval

### 3. Executor (`app/engine/executor.py`)
Stateless. Maps `RiskLevel` → `ExecutionStatus`.
- `LOW` → `EXECUTED`
- `HIGH` → `ESCALATED`

The executor does not call any external service. All side effects are owned by the pipeline.

### 4. Pipeline (`app/engine/pipeline.py`)
Orchestrates all side effects:
- `EXECUTED` → calls platform API → saves result to DB
- `ESCALATED` → creates `PendingApproval` → sends Slack message → saves `approval_id` to DB
- On approval → calls platform API → saves execution result to DB

---

## Platform Adapter Pattern

The core pipeline is platform-agnostic. Each e-commerce platform is a pluggable adapter responsible for:

- Receiving platform-specific webhook payloads and normalizing them to internal `EventInput`
- Executing actions against the platform's API (restock orders, shipment plans, flagging)
- Handling platform-specific authentication (LWA for Amazon, OAuth for Shopify, etc.)

**Current adapters:**
- Amazon SP API (implemented — mock mode, production structure ready)

**Planned adapters:**
- Shopify
- Lazada
- Tiki

Adding a new platform requires: a new webhook router, a new API client under `app/{platform}/`, and credentials stored per-seller in the DB. The pipeline, policy engine, and Slack integration are untouched.

---

## API Endpoints

### Events
| Method | Path | Description |
|---|---|---|
| `POST` | `/webhooks/sp-api` | Receive Layer 1 domain events from Amazon |
| `POST` | `/events` | Ingest Layer 2 monitoring events |
| `GET` | `/events/{event_id}` | Get event status and result |

### Approvals
| Method | Path | Description |
|---|---|---|
| `GET` | `/approvals/{id}` | Inspect a pending approval |
| `POST` | `/approvals/{id}/approve` | Approve via REST |
| `POST` | `/approvals/{id}/reject` | Reject via REST |

### Slack
| Method | Path | Description |
|---|---|---|
| `POST` | `/slack/interactions` | Handle Approve/Reject button clicks |
| `GET` | `/slack/install` | Begin Slack OAuth install flow (planned) |
| `GET` | `/slack/oauth/callback` | Receive OAuth token from Slack (planned) |

### System
| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check |

---

## Slack Integration

**Multi-workspace.** Each seller installs the bot into their own Slack workspace via OAuth. The bot token is stored per-seller in the DB — no shared token. All sellers operate independently in their own workspace.

**Approval flow:**
1. Pipeline detects HIGH risk → creates `PendingApproval` → sends Block Kit message to seller's channel
2. Message contains action details, reasoning, estimated spend, and Approve/Reject buttons
3. Seller clicks a button → Slack POSTs to `/slack/interactions`
4. Agent verifies HMAC-SHA256 signature (5-minute replay window) → resolves approval in DB → calls platform API → updates the Slack message

**Security:** All interactions verified using `SLACK_SIGNING_SECRET` via HMAC-SHA256. Requests older than 5 minutes are rejected.

**Conversational mode (in progress):** Sellers can message the bot directly in natural language:
- "Reorder 50 units of WIDGET-42"
- "Show my pending approvals"
- "What is my current refund rate?"
- "Report during XXX period"

**Design decision — tool calling, not intent parsing:**
The conversational layer uses Claude's native tool/function calling rather than an ad-hoc parse-then-route pattern. Actions (`reorder_sku`, `check_inventory`, `list_approvals`,`get_store_summary`) are defined as typed tools exposed to the LLM. The LLM selects which tool to call and extracts parameters directly — no separate intent classifier, no regex parsing of LLM output. The tool implementation then validates against the policy engine before executing. This keeps routing implicit, parameters structured, and the policy layer deterministic regardless of how the input arrived.

**Configuration:**
```env
SLACK_BOT_TOKEN=xoxb-...          # global fallback (single workspace dev mode)
SLACK_SIGNING_SECRET=...
SLACK_ENABLED=true
```

---

## Amazon SP API Integration

**Credentials are per-seller, stored in the database.** No shared SP API credentials in `.env`.

Each seller record contains:
```
lwa_client_id       - Login With Amazon OAuth client
lwa_client_secret
lwa_refresh_token   - seller's LWA refresh token
marketplace_id      - Amazon marketplace ID
endpoint            - regional SP API base URL
```

**Auth flow:** LWA refresh token → `POST https://api.amazon.com/auth/o2/token` → access token → SP API request headers.

**Current execution mapping:**

| Intent | SP API action |
|---|---|
| `reorder` | `POST /vendor/orders/v1/purchaseOrders` |
| `flag_order_spike` | Acknowledged |
| `flag_refund_rate` | Acknowledged |

**Mock mode** (`SP_API_ENABLED=false`): returns `MOCK-PO-XXXXXXXX` order IDs without calling Amazon.

---

## LLM Integration

LLM is a **reasoning, tool selecting, and extraction layer**, not a final decision layer. The policy engine remains deterministic and auditable.

| Role | Where | Status |
|---|---|---|
| Layer 3 signal generation | Scheduled AI jobs → insight events | halt indefinitely |
| Intent classification, tool selection | Conversational Slack messages | In Progress |
| Structured extraction | Parse free-text commands | Planned |
| Escalation enrichment | Plain-English context in Slack approval messages | Planned |
| Decision assistance | Historical context alongside escalations | Planned |

**What LLM will NOT do:**
- Make final execution decisions
- Replace the policy engine
- Act without a deterministic rule validating the action first



## Database

**PostgreSQL** (production/dev), **SQLite in-memory** (tests).

### Schema

**`sellers`** — tenant registry
```
id, name, status, slack_channel_id, slack_bot_token,
policies (JSONB), sp_api_credentials (JSONB)
```

**`events`** — full audit log
```
id, seller_id, event_type, payload (JSONB),
status, result (JSONB), error, created_at, updated_at
```

**`approvals`** — human-in-the-loop decisions
```
id, event_id, seller_id, intent, policy_result (JSONB),
status, created_at, resolved_at, resolved_by,
slack_channel_id, slack_ts
```

---

## Deployment Plan (AWS)

| Component | Local (now) | AWS (planned) |
|---|---|---|
| API server | FastAPI + uvicorn | ECS Fargate |
| Database | PostgreSQL (Docker) | RDS PostgreSQL |
| Secrets | `.env` file | Secrets Manager |
| Async processing | FastAPI BackgroundTasks | SQS + Lambda |
| Public endpoint | ngrok | Application Load Balancer |
| Container registry | Local Docker | ECR |


SQS decouples ingestion from processing. Lambda scales independently from the API tier. Secrets Manager holds all credentials — nothing sensitive in environment variables or code.



Tests use SQLite in-memory. `SLACK_ENABLED=false` and `SP_API_ENABLED=false` are pinned in `conftest.py` — no real external calls during testing.

---

## Environment Variables

| Variable | Description |
|---|---|
| `DATABASE_URL` | SQLAlchemy connection string |
| `SLACK_SIGNING_SECRET` | Slack app signing secret — verifies incoming Slack requests |
| `SLACK_CLIENT_ID` | Slack app client ID — used in multi-workspace OAuth flow |
| `SLACK_CLIENT_SECRET` | Slack app client secret — used in multi-workspace OAuth flow |
| `SLACK_REDIRECT_URI` | Slack OAuth redirect URI |
| `SP_API_ENABLED` | Enable real Amazon SP API calls (default: `false` → mock responses) |
| `LWA_CLIENT_ID` | Amazon LWA app client ID — used in SP API OAuth flow |
| `LWA_CLIENT_SECRET` | Amazon LWA app client secret — used in SP API OAuth flow |
| `OAUTH_REDIRECT_URI` | Amazon SP API OAuth redirect URI |
| `ANTHROPIC_API_KEY` | Anthropic API key — used by the conversational agent and LLM features |

---

## Project Structure

```
├── main.py                    # FastAPI app, lifespan, router registration
├── conftest.py                # Pytest fixtures (SQLite, env pins, table teardown)
├── requirements.txt
├── .env
│
├── app/
│   ├── store.py               # DB access layer
│   │
│   ├── models/
│   │   ├── event.py           # EventType, EventLayer, EventRecord
│   │   ├── intent.py          # Intent enum
│   │   ├── decision.py        # PolicyResult, ExecutionResult, DecisionResult
│   │   ├── seller.py          # Seller, SellerPolicies, SpApiCredentials, SlackCredentials
│   │   └── approval.py        # PendingApproval, ApprovalStatus
│   │
│   ├── engine/
│   │   ├── pipeline.py        # classify -> policy -> execute -> side effects
│   │   ├── classifier.py      # EventType -> Intent
│   │   ├── policy.py          # Intent + seller + payload -> PolicyResult
│   │   └── executor.py        # PolicyResult -> ExecutionResult (stateless)
│   │
│   ├── routers/
│   │   ├── events.py          # POST /events, GET /events/{id}
│   │   ├── webhooks.py        # POST /webhooks/sp-api
│   │   ├── approvals.py       # GET/POST /approvals/{id}
│   │   ├── sellers.py         # POST/GET/PATCH /sellers — seller management API
│   │   ├── slack.py           # POST /slack/interactions, POST /slack/events
│   │   ├── slack_oauth.py     # GET /slack/authorize, GET /slack/callback
│   │   └── oauth.py           # GET /oauth/authorize, GET /oauth/callback (Amazon LWA)
│   │
│   ├── sp_api/
│   │   ├── auth.py            # LWA token exchange (refresh_token -> access_token)
│   │   └── client.py          # execute_intent() -> SP API or mock
│   │
│   ├── slack/
│   │   ├── client.py          # send_approval_request(), update_message(), send_message()
│   │   └── message_handler.py # Route incoming Slack messages to LLM agent
│   │
│   ├── llm/
│   │   ├── agent.py           # Conversational agent — Anthropic tool-calling loop
│   │   ├── tools.py           # Tool definitions (reorder_sku, list_approvals, get_refund_rate)
│   │   └── tool_handlers.py   # Tool implementations — call pipeline or query store
│   │
│   ├── db/
│   │   ├── engine.py          # SQLAlchemy engine, SessionLocal
│   │   ├── models.py          # ORM: SellerRow, EventRow, ApprovalRow
│   │   └── seed.py            # Seed mock sellers on startup
│   │
│   └── mock/
│       └── sellers.py         # MOCK_SELLERS for dev/test
│
└── test_*.py                  # Tests across all layers
```

