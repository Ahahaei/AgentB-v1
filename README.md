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
|  HIGH risk -> PendingApproval + Slack    |
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
AI-generated signals that emerge from patterns over time, not from a single event. These are the most creative and highest-value signals — things the seller would never catch manually.

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

**Production event flow:**
```
Webhook -> ALB -> ECS (FastAPI) -> SQS -> Lambda -> run_pipeline() -> RDS
```

SQS decouples ingestion from processing. Lambda scales independently from the API tier. Secrets Manager holds all credentials — nothing sensitive in environment variables or code.

---

## Running Locally

```bash
# Start PostgreSQL
docker run -d --name ops-postgres \
  -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 postgres:16

# Install dependencies
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run
uvicorn main:app --reload

# Test
pytest
```

Tests use SQLite in-memory. `SLACK_ENABLED=false` and `SP_API_ENABLED=false` are pinned in `conftest.py` — no real external calls during testing.

---

## Environment Variables

| Variable | Description |
|---|---|
| `DATABASE_URL` | SQLAlchemy connection string |
| `SLACK_BOT_TOKEN` | Slack bot token (global fallback) |
| `SLACK_SIGNING_SECRET` | Slack app signing secret |
| `SLACK_ENABLED` | Enable real Slack API calls |
| `SP_API_ENABLED` | Enable real Amazon SP API calls |

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
│   │   ├── seller.py          # Seller, SellerPolicies, SpApiCredentials
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
│   │   └── slack.py           # POST /slack/interactions
│   │
│   ├── sp_api/
│   │   ├── auth.py            # LWA token exchange
│   │   └── client.py          # execute_intent() -> SP API or mock
│   │
│   ├── slack/
│   │   └── client.py          # send_approval_request(), update_message()
│   │
│   ├── db/
│   │   ├── engine.py          # SQLAlchemy engine, SessionLocal, create_tables()
│   │   ├── models.py          # ORM: SellerRow, EventRow, ApprovalRow
│   │   └── seed.py            # Seed mock sellers on startup
│   │
│   └── mock/
│       └── sellers.py         # MOCK_SELLERS for dev/test
│
└── test_*.py                  # 69 tests across all layers
```

---

## Current Status

| Feature | Status |
|---|---|
| Two-layer event ingestion (L1 + L2) | Done |
| Decision pipeline (classify -> policy -> execute) | Done |
| Per-seller policy evaluation | Done |
| PendingApproval entity + REST approve/reject | Done |
| Slack escalation (Block Kit messages) | Done |
| Slack interaction handler (button clicks) | Done |
| PostgreSQL persistence | Done |
| SP API auth (LWA token exchange) | In progress |
| SP API execution (mock + real structure) | Done (mock only) |
| Post-approval SP API execution | Not built |
| Slack OAuth (multi-workspace onboarding) | Not built |
| Seller onboarding API | Not built |
| Layer 3 —  insight signal generation | Not built |
| Conversational Slack mode | In progress |
| LLM integration | Not built |
| Additional platform adapters (Shopify, Lazada) | Not built |
| AWS deployment | Not built |

---

## What's Next

1. **Post-approval SP API execution** — close the full loop: approve in Slack → execute via platform API (done)
2. **Slack OAuth + multi-workspace** — each seller installs the bot into their own workspace
3. **Seller onboarding API** — `POST /sellers`, credential registration, Slack user linking
4. **Layer 3 signal generation** — scheduled AI jobs that emit proactive insight events into the pipeline ( this part delayed indefintely)
5. **LLM integration** — enriched escalation messages, conversational Slack commands, retrieving information. (in progress)
6. **Additional platform adapters** — Shopify, Lazada, Tiki
7. **AWS deployment** — ECS + RDS + SQS + Lambda + Secrets Manager (inprogress)


Deployment steps
NOW: Step 1 — ECR (push your image) (DONE)

AWS Console → ECR → Create repository → name: seller-ops-api

Click "View push commands" — AWS gives you 4 commands to run locally. These are the only terminal commands in the whole process:


aws ecr get-login-password ... | docker login ...
docker build -t seller-ops-api .
docker tag seller-ops-api:latest <your-ecr-url>
docker push <your-ecr-url>
Step 2 — RDS PostgreSQL (DONE)

RDS → Create database → PostgreSQL → Free tier

Instance: db.t3.micro
Username: postgres, set a password
VPC: default VPC (important — ECS will use same VPC)
Public access: No
Note the endpoint URL when created
Step 3 — SSM Parameter Store (secrets) (DONE)

Systems Manager → Parameter Store → Create parameter, repeat for each:

Name	Value	Type
/seller-ops/DATABASE_URL	postgresql://postgres:password@rds-endpoint:5432/postgres	SecureString
/seller-ops/SLACK_BOT_TOKEN	xoxb-...	SecureString
/seller-ops/SLACK_SIGNING_SECRET	...	SecureString
/seller-ops/SLACK_ENABLED	true	String
/seller-ops/SP_API_ENABLED	false	String
Step 4 — Security Groups

EC2 → Security Groups → Create 3 groups: (DONE)

alb-sg: inbound 80 + 443 from 0.0.0.0/0
ecs-sg: inbound 8000 from alb-sg only
rds-sg: inbound 5432 from ecs-sg only
Attach rds-sg to your RDS instance (Modify → Security group).

Step 5 — IAM Role for ECS

IAM → Roles → Create role → ECS Task use case

Attach these policies:

AmazonECSTaskExecutionRolePolicy (pull from ECR, write logs)
AmazonSSMReadOnlyAccess (read Parameter Store secrets)
Name it seller-ops-task-execution-role.

Step 6 — ECS Cluster

ECS → Clusters → Create cluster

Name: seller-ops-cluster
Infrastructure: AWS Fargate
Step 7 — Task Definition

ECS → Task Definitions → Create new

Launch type: Fargate
CPU: 0.25 vCPU, Memory: 0.5 GB
Task execution role: seller-ops-task-execution-role
Container:
Image: your ECR URL
Port: 8000
Log collection: CloudWatch (auto-creates log group)
Environment variables → ValueFrom (SSM) for each parameter:
DATABASE_URL → arn:aws:ssm:region:account:parameter/seller-ops/DATABASE_URL
repeat for all 5
Step 8 — ALB

EC2 → Load Balancers → Create → Application Load Balancer

Internet-facing
VPC: default, select all availability zones
Security group: alb-sg
Listener: HTTP port 80
Target group:
Type: IP (required for Fargate)
Protocol: HTTP, Port 8000
Health check path: /health
Step 9 — ECS Service

ECS → your cluster → Services → Create

Task definition: what you created in Step 7
Service type: Replica, count: 1
VPC: default, select subnets
Security group: ecs-sg
Load balancer: attach the ALB → select the target group from Step 8
Deploy. ECS pulls the image, starts the container, ALB starts routing.

Step 10 — Get URL, update Slack

EC2 → Load Balancers → copy the DNS name (e.g. seller-ops-xxxx.us-east-1.elb.amazonaws.com)

Slack app dashboard → Interactivity & Shortcuts → Request URL:


http://seller-ops-xxxx.us-east-1.elb.amazonaws.com/slack/interactions


LLM integration steps - DONE
Phase 1 — Seller identity (unchanged)
Alembic migration: add slack_user_id to sellers
Update SellerRow ORM + Seller Pydantic model
Add get_seller_by_slack_user_id(db, user_id) to store.py
Update MOCK_SELLERS with mock user IDs
Tests
Phase 2 — Slack Events API endpoint (unchanged)
POST /slack/events — URL verification challenge + HMAC (reuse existing verification code)
Filter bot's own messages (user == bot user ID)
Look up seller via slack_user_id
Return 200 immediately, process in BackgroundTask
Phase 3 — Tool definitions + Claude integration (replaces the old intent extractor)
Add anthropic to requirements.txt
Add ANTHROPIC_API_KEY to .env
Create app/llm/tools.py — tool schemas as typed dicts:

TOOLS = [
  {
    "name": "reorder_sku",
    "description": "Reorder stock for a given SKU.",
    "input_schema": {
      "type": "object",
      "properties": {
        "sku":      {"type": "string"},
        "quantity": {"type": "integer"}
      },
      "required": ["sku", "quantity"]
    }
  },
  {
    "name": "list_approvals",
    "description": "List the seller's pending approvals.",
    "input_schema": {"type": "object", "properties": {}}
  },
  {
    "name": "get_refund_rate",
    "description": "Return the seller's current refund rate.",
    "input_schema": {"type": "object", "properties": {}}
  }
]
Create app/llm/agent.py:
Takes (message_text, seller, db)
Calls Claude with the TOOLS list and a system prompt that gives it seller context
Receives a tool_use block in the response
Dispatches to the tool implementation (Phase 4)
Sends the result back to the seller's Slack channel
No JSON parsing, no regex, no intent router. The tool_use.name + tool_use.input come out structured.

Phase 4 — Tool implementations
Each tool is a function that contains its own policy guard:

reorder_sku(sku, quantity, seller, db)

Construct a synthetic EventInput (new event type MANUAL_REORDER or reuse inventory_low — you've already decided, but either works cleanly here)
Call run_pipeline() — the existing policy engine runs, so a 10,000-unit request still gets escalated if it exceeds auto_approve_max_units
Return "Reorder approved and submitted" or "Escalated for your approval — check Slack"
list_approvals(seller, db)

store.get_pending_approvals_for_seller(seller_id)
Format as a readable Slack message listing pending items
get_refund_rate(seller, db)

Query events table for high_refund_rate_detected events for this seller
Format and return the most recent rate
The policy engine is not bypassed — it's the guard inside reorder_sku. The LLM never touches execution decisions.

Phase 5 — Wire and test
Connect /slack/events → agent.handle_message()
Deduplication: track event_id to avoid processing Slack retries twice (simple in-memory set or DB column)
Tests:
Unit tests for each tool implementation (mock DB, mock pipeline)
Agent tests with mocked Anthropic client — verify correct tool dispatch for known inputs
Endpoint tests for /slack/events (challenge handshake, HMAC rejection, unknown seller)


Multitenant set up steps
Seller management API production steps

Sellers currently exist only via seed data. A real product needs a management API to onboard and configure sellers without touching code.

| Method | Path | Description |
|---|---|---|
| `POST` | `/sellers` | Onboard a new seller (name, policies, Slack channel) |
| `GET` | `/sellers/{id}` | Fetch seller details |
| `PATCH` | `/sellers/{id}` | Update policies, Slack config, or status |

Zero SP API dependency. Pure DB + REST. This is what makes the system actually multi-tenant rather than hardcoded seed data — each seller is a first-class entity managed through the API, not a fixture.

---

Amazon OAUth onboarding steps

When a seller wants to connect their Amazon account, they go through Login With Amazon (LWA) OAuth. The application credentials (`lwa_client_id`, `lwa_client_secret`) are registered once by the developer. Each seller then authorizes the app independently to produce their own `lwa_refresh_token`, which is stored per-seller in the DB.

| Method | Path | Description |
|---|---|---|
| `GET` | `/oauth/authorize` | Redirect seller to Amazon's LWA authorization URL |
| `GET` | `/oauth/callback` | Receive authorization code → exchange for refresh token → store in `sp_api_credentials` |

The token exchange hits `https://api.amazon.com/auth/o2/token`. Once stored, the seller's refresh token is used by `app/sp_api/auth.py` on every SP API call — no further OAuth interaction required until the token is revoked.

The callback endpoint can be built and tested structurally without production SP API credentials. Real token exchange requires a registered SP API application (Seller Central → Apps & Services → Develop Apps).

---