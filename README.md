# KirAI — Your Kirana Store, Operated by AI

KirAI is an AI-powered autonomous kirana (grocery) store operator. A customer sends a request in English or
Hinglish, and KirAI understands it, matches products, looks up **live** inventory and prices in the database,
creates a real order, deducts stock atomically, and confirms — with every step visible in the UI.

> *"Bhaiya 2 packets Aashirvaad atta, 1 Fortune oil aur 3 Maggi bhej do. Ghar pe deliver kar dena."*
> → Order **#1042**, ₹707 + ₹30 delivery = **₹737**, atta 39→37, oil 29→28, Maggi 56→53.

Built for SlowBros Labs **HACK IT BROS '26**.

## What is real (and what the AI is *not* trusted with)

```
Customer request → EURI understands language → products matched in DB → live stock check
→ prices from DB → ONE transaction (order + items + stock deduction + logs) → confirmation
```

- The AI **only understands the message** (intent, product names, quantities, delivery).
- Price, stock, order ids and totals come **only from the database**. The AI never runs SQL; it can only trigger the
  allow-listed tools in `backend/app/ai/tools.py` (`GET /api/agent/tools`).
- Order creation, inventory deduction, inventory logs and activity logs are **one atomic transaction**. Stock can never go
  negative (a conditional `UPDATE … WHERE stock >= qty` guards even concurrent requests). Any failure rolls everything back.
- The timeline in the UI is the backend's actual step list (with real timestamps, durations and the tools each step called).
- **EURI fallback (transparent):** if EURI is not configured, unreachable, slower than `EURI_TIMEOUT_SECONDS` (default 8s),
  or returns invalid output, KirAI falls back to a deterministic Hinglish rule parser so the store keeps working. The UI
  and API always say which parser ran (`parser.provider` = `euri` | `local`, with the reason).

## Features

- **AI Operator** (main demo screen): chat + live execution timeline + order confirmation card + inventory-update badges.
- **Voice:** tap the mic (or "Speak an order") and say the request in English/Hinglish. The live transcript appears in the
  input and is sent automatically when you stop talking; KirAI reads its reply aloud (mute with the speaker icon). Uses the
  browser's built-in Web Speech API (Chrome/Edge/Safari; needs microphone permission and internet) — no extra services.
- Handles: multi-item orders, unknown products (with suggestions), insufficient / out-of-stock, **ambiguous products**
  (asks "Which oil?" with tappable options and never guesses), empty requests, invalid quantities, stock questions
  ("atta khatam ho gaya kya?"), low-stock report, greetings.
- Dashboard (real KPIs, 7-day revenue, recent orders, low stock, AI activity, quick AI command), Orders (drawer with
  AI processing + inventory changes), Inventory (filters, stock bars, product drawer with stock movements), Customers
  (order history), Activity (live log), Settings (AI status/test, **Reset Demo Data**).
- Responsive (sidebar → mobile menu + bottom tabs, tables → cards), skeleton loading states, friendly error states
  with *Try Again*, toasts.

## Tech stack

Next.js 16 (App Router) · TypeScript · Tailwind CSS v4 · shadcn/ui · Lucide · Framer Motion ·
FastAPI · Pydantic · SQLAlchemy · SQLite · EURI (OpenAI-compatible API, via `httpx`).

## Folder structure

```
kirai/
├── README.md  .gitignore  .env.example
├── backend/
│   ├── requirements.txt  .env.example
│   ├── app/
│   │   ├── main.py  config.py  database.py  models.py  schemas.py  errors.py  utils.py  seed.py
│   │   ├── auth.py  auth_setup.py  ledger_models.py  ledger_schemas.py
│   │   ├── ai/         euri_client.py  prompts.py  parser.py  tools.py  agent.py
│   │   ├── services/   inventory_service.py  order_service.py  customer_service.py  activity_service.py  ledger_service.py
│   │   └── api/        routes.py  agent_routes.py  auth_routes.py  ledger_routes.py
│   └── tests/          conftest.py  test_kirai.py  test_ledger.py  test_idempotency.py  test_auth.py  test_safeguards.py   (89 tests)
└── frontend/
    ├── app/        (/, /login, /operator, /orders, /inventory, /customers, /ledger, /activity, /settings)
    ├── components/ (app-shell, shared, operator/*, orders/*, inventory/*, ui/* = shadcn)
    ├── lib/  hooks/  types/  public/
```

## Setup

Prerequisites: Python 3.11+ and Node 20+.

### 1. Backend

```powershell
cd backend
python -m venv venv
venv\Scripts\activate            # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env           # macOS/Linux: cp .env.example .env
#   then in .env: set EURI_API_KEY=...  and  DEMO_MODE=true   (DEMO_MODE seeds sample data + enables Reset Demo Data)
uvicorn app.main:app --reload    # with DEMO_MODE=true the empty database is seeded automatically
```

API: http://localhost:8000 · interactive docs: http://localhost:8000/docs
`python -m app.seed` seeds sample data explicitly (22 products, 4 customers, 8 sample orders) and
`python -m app.seed --reset` wipes and re-seeds; the reset only runs with `DEMO_MODE=true`.

### 2. Frontend

```powershell
cd frontend
npm install
copy .env.example .env.local     # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```

Open http://localhost:3000.

### 3. Tests

```powershell
cd backend
python -m pytest tests -q        # 89 tests; never calls the real EURI API
```

## Environment variables

| File | Variable | Purpose |
|---|---|---|
| `backend/.env` | `EURI_API_KEY` | EURI key. **Server-side only**, never sent to the browser, git-ignored. |
| | `EURI_BASE_URL` | Default `https://api.euron.one/api/v1/euri` (documented EURI base URL) |
| | `EURI_MODEL` | e.g. `gpt-4.1-nano` |
| | `EURI_TIMEOUT_SECONDS` | Hard wall-clock cap per EURI call (default `8`); slower → local parser fallback |
| | `FRONTEND_URL`, `EXTRA_ORIGINS` | Exact browser origins allowed for CORS and cookies (no wildcards) |
| | `DEMO_MODE` | `true` = sample data + Reset Demo Data (deletes everything). Default `false`. |
| | `OWNER_PASSWORD_HASH` | Owner login hash from `python -m app.auth_setup` (`OWNER_PASSWORD` = plain, demos only) |
| | `SESSION_TTL_HOURS`, `COOKIE_SAMESITE`, `COOKIE_SECURE` | Session lifetime and cookie flags (cross-site deploys: `none` + `true`) |
| | `DATABASE_URL`, `STORE_NAME`, `STORE_LOCATION`, `DELIVERY_CHARGE`, `FREE_DELIVERY_ABOVE` | Optional |
| `frontend/.env.local` | `NEXT_PUBLIC_API_URL` | Backend URL |

## EURI integration

Implemented from the EURI docs (OpenAI-compatible): `POST {EURI_BASE_URL}/chat/completions`, `Authorization: Bearer <key>`,
body `{model, messages, temperature, max_tokens}`. Function-calling / JSON-mode are **not documented** for EURI, so they are
not used: `EuriClient.structured_output()` prompts for JSON and validates it strictly with Pydantic (one corrective retry
for invalid JSON; timeouts are never retried). `EuriClient.tool_call()` lets the model pick from an allow-list, validated by
the backend. All EURI code is isolated in `backend/app/ai/`. Identical messages reuse a cached temperature-0 parse.

## Security and operating modes

| | `DEMO_MODE=true` (demo) | `DEMO_MODE=false` (real store, the default) |
|---|---|---|
| Sample data | seeded on startup | never created |
| Reset / seed | allowed | refused with 403 (even from the CLI) |
| No owner password set | API is open (local demo) | private API answers 503, it never opens by accident |
| Owner password set | sign-in required | sign-in required |

- **Owner login:** run `python -m app.auth_setup` and put the printed `OWNER_PASSWORD_HASH=` line in `backend/.env`
  (only a salted scrypt hash is stored). Sign-in creates a server-side session in an `HttpOnly` cookie; the token is
  stored hashed, expires after `SESSION_TTL_HOURS`, and sign-out (top right) ends it and clears locally saved drafts.
- Everything except `GET /api/health` and `/api/auth/*` needs the session: orders, inventory, customers, the ledger,
  settings and the AI endpoints (so anonymous callers cannot read data or spend EURI credits).
- Failed logins are limited (5 attempts, then a 5-minute lock per client address). State-changing browser requests must
  come from the configured `FRONTEND_URL` (CSRF), and CORS allows only exact configured origins, no wildcards.
- **Retries are safe:** `POST /api/orders` and `POST /api/agent/process` accept an `Idempotency-Key` header (the UI
  sends one per action and reuses it when you press *Try Again*). The same key + request returns the first result: no
  second order and no second stock deduction. The same key with different details is rejected (409).
- Deploying across sites (Vercel + separate API host) needs `COOKIE_SAMESITE=none`, `COOKIE_SECURE=true` and HTTPS.

## Demo reset

`DEMO_MODE=true` only.

- UI: **Settings → Reset Demo Data**, or
- API: `POST /api/demo/reset` (signed in), or
- CLI: `python -m app.seed --reset`

Reset keeps your login session, then drops and rebuilds all data tables (including the financial ledger): orders, items and logs are wiped, stock is restored, demo customers are recreated,
and the order counter is set so the next live order is **#1042**.

## API

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | DB + AI-configured status |
| GET | `/api/products` `?q=&category=&status=` | Products |
| GET | `/api/products/search?q=` | Ranked, typo/Hinglish-tolerant search |
| GET | `/api/products/{id}` | Product + stock movement history |
| GET | `/api/inventory` | Products + summary + categories |
| GET | `/api/orders` · `/api/orders/{id}` | Orders · detail (customer, AI activity, inventory changes) |
| POST | `/api/orders` | Manual order `{customer_id, items:[{product_id, quantity}], delivery_address?}` (same atomic transaction) |
| PATCH | `/api/orders/{id}/status` | `out_for_delivery` / `delivered` |
| GET | `/api/customers` · `/api/customers/{id}` | Customers with spend, history, activity |
| GET | `/api/dashboard/stats` | KPIs, trends, 7-day series, top products |
| GET | `/api/activity` | Activity log |
| POST | **`/api/agent/process`** | The AI workflow (below) |
| GET | `/api/agent/tools` | Allow-listed AI tools |
| GET | `/api/ai/status?check=true` | EURI status (`check=true` pings EURI; key never returned) |
| POST | `/api/demo/reset` · `/api/seed` | Reset · idempotent seed |

`POST /api/agent/process` — request `{"message", "customer_id", "delivery_address", "draft"?}`; response:

```json
{
  "success": true, "intent": "place_order", "status": "confirmed",
  "steps": [{"name": "parse_request", "title": "Understanding request", "status": "completed",
             "message": "Request understood: 3 items · delivery requested", "timestamp": "…Z",
             "duration_ms": 3064, "tools": ["get_customer"]}, "… find_products, check_inventory, calculate_total, create_order, update_inventory, send_confirmation"],
  "order": {"id": 1042, "subtotal": 707, "delivery_charge": 30, "total": 737, "status": "confirmed", "items": ["…"], "inventory_changes": ["…"]},
  "message": "Order confirmed successfully.",
  "reply": "Order #1042 confirmed, Rahul! …",
  "parser": {"provider": "euri", "model": "gpt-4.1-nano"}
}
```

Other `status` values: `needs_clarification` (returns `clarification.options` + `draft` — send the draft back with the
customer's reply), `rejected` (unknown product / insufficient stock — no order created), `needs_input`, `info`, `error`.

## 90-second demo script

1. **Dashboard** — real KPIs, low stock (Pepsi out, Kurkure 4 left).
2. **Inventory** — note Aashirvaad Atta 39, Fortune Sunflower Oil 29, Maggi 56.
3. **AI Operator → "Use demo request" → Send.** Watch the timeline (each step lists the backend tool it called) →
   **Order Confirmed #1042 · ₹737** → inventory badges (39→37, 29→28, 56→53).
4. **Orders** → #1042 (drawer: customer request, AI processing, inventory changes).
5. **Inventory** → stock actually decreased.
6. Edge cases in the operator: `2 Oreo bhej do` (not found + suggestion), `10 Kurkure bhej do` (only 4 left),
   `1 oil bhejo` (asks which oil), `atta khatam ho gaya kya?` (stock answer).
7. **Settings → Reset Demo Data** before the next run.

## Hackathon requirements implemented

Real end-to-end workflow · SQLite + SQLAlchemy with the 6 required tables · atomic order transaction · 22 seeded products
+ demo customer · EURI client abstraction (`chat`, `structured_output`, `tool_call`) · the 9 required tools ·
Hinglish + English understanding · unknown / insufficient / ambiguous / empty / mixed edge cases · all required API
endpoints · polished responsive UI · loading, error and toast states · demo reset · tests · no secrets in the frontend.

## Known limitations

- EURI latency is outside our control (observed anywhere from ~3s to 40s+). Calls slower than `EURI_TIMEOUT_SECONDS`
  fall back to the local parser (clearly labelled) so the workflow stays reliable.
- The "confirmation" is generated for the customer in the app; no SMS/WhatsApp is actually sent.
- Voice recognition is English-India (Roman script), so Hinglish works but Devanagari Hindi does not; it is unavailable in Firefox
  (the mic button is hidden there and typing still works). A misheard sentence is sent as heard, so check the transcript.
- Single store-owner login only (no multiple users or roles); one store. SQLite on Render/Railway free tiers is
  ephemeral: use a persistent disk for real data (and keep `DEMO_MODE=false`).
- Quantities are counted in packs/units ("5 kg atta" is not converted to pack sizes).

## Future improvements

WhatsApp intake, Hindi (Devanagari) voice, UPI payments, supplier reorder automation for low stock, multi-store support, streaming
(SSE) execution timeline, customer memory ("my usual").

## Deployment

- **Frontend (Vercel):** import `frontend/`, set `NEXT_PUBLIC_API_URL` to the backend URL.
- **Backend (Render/Railway):** root `backend/`, build `pip install -r requirements.txt`, start
  `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, set `EURI_API_KEY`, `EURI_BASE_URL`, `EURI_MODEL`, `FRONTEND_URL`.
