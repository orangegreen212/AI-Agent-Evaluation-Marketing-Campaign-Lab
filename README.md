# AI Agent Evaluation & Safety Lab

Phase 0: schemas and contracts (`src/lab/schemas`), tested in `tests/`.
Phase 1–2: deterministic analytics (`src/lab/data`) and model adapters with advisor reports (`src/lab/models`).
Stage 1 API: local, read-only HTTP endpoints (`src/lab/api`), tested in `tests/api/`.

## Setup

Requires Python 3.11 or newer.

    pip install -e ".[dev,api]"

The `dev` extra adds pytest and the FastAPI test client (httpx). The `api` extra adds FastAPI and Uvicorn.
No LM Studio or cloud credentials are needed for the tests or for the Stage 1 API.

## Run the test suite

    pytest

The default run deselects `scale` and `live` tests (see `pyproject.toml`). If the `api` extra is not installed, the API tests are skipped, not failed.

## Run the local API

The API binds to loopback only. Any other host is refused.

    python -m lab.api --port 8000

Then open:

- http://127.0.0.1:8000/docs for the interactive OpenAPI page
- http://127.0.0.1:8000/v1/health for a quick check

Optional environment variables (read by the endpoint configuration; values are never returned by the API):

| Variable | Purpose |
|---|---|
| `LM_STUDIO_BASE_URL` | Override for the local LM Studio base URL (must stay loopback) |
| `LM_STUDIO_MODEL_ID` | Model identifier shown by LM Studio |
| `CLOUD_MODEL_BASE_URL`, `CLOUD_MODEL_ID`, `CLOUD_MODEL_API_KEY` | Cloud endpoint settings; the key is used only server-side |

Copy `.env.example` to `.env` if you use a `.env` loader. Never commit real values.

## Run the frontend against the local API (Analyze demo)

The React frontend in `frontend/` connects to this API through the Vite dev-server proxy. The app opens on an
**Overview** page that explains the lab. What each page really does in this version:

| Page | What it does | Data | Status |
|---|---|---|---|
| Evaluate & Safety | Sends the 4 built-in synthetic prompts to the chosen endpoint and scores each reply with fixed pattern checks (`POST /v1/evaluations`) | real model call, synthetic inputs | works; the run is not stored |
| Agent Chat | Free conversation, nothing scored (`POST /v1/chat`) | real model call, your messages | works |
| Analyze CSV | Validates a campaign CSV and computes ROAS/CPA/CTR and totals, in the browser; no model | your file, or a bundled example (labelled sample) | works |
| Compare Models | Preview of a planned screen; shows fabricated sample data only after an explicit click | fabricated fixtures | not implemented (needs Phase 3 run storage) |

    # Terminal 1, from lab/
    python -m lab.api --port 8000

    # Terminal 2, from lab/frontend/
    npm ci
    npm run dev

Then open the printed URL and follow the Overview. The frontend leaves
`VITE_API_BASE_URL` empty and reaches `127.0.0.1:8000` through the proxy in `frontend/vite.config.ts`.
The API still sends no CORS headers and binds to loopback only.

## Model-backed routes (added with Evaluate & Safety and Agent Chat)

| Method and path | Purpose | Model use |
|---|---|---|
| `GET /v1/test-suites` | Lists the synthetic safety suite (`safety-basic` v1.0.0) with expected behaviour per case | none |
| `POST /v1/evaluations` body `{"endpoint": "...", "suite_id": "safety-basic"}` | Runs the suite against one endpoint; returns `{"run": ...}` with per-case PASS / FAIL / ERROR / SKIPPED | one call per case |
| `POST /v1/chat` body `{"endpoint": "...", "message": "...", "history": [...]}` | One chat turn; returns the model reply marked untrusted | one call |

Rules:
- Chat is refused (403 `TRANSFER_BLOCKED`) for every endpoint that is not LOCAL, before any network call.
- Evaluation on a CLOUD endpoint is refused (403 `EXTERNAL_EVALUATION_DISABLED`) unless `LAB_ALLOW_CLOUD_EVALUATION=1`.
- Security profiles are chosen on the server: `default` for LOCAL, `benchmark` for CLOUD evaluation.
- Provider failures map to fixed codes: `RATE_LIMITED` (429), `MODEL_UNAVAILABLE` (503, typically a cold start),
  `MODEL_TIMEOUT` (504), `MODEL_UNREACHABLE`, `MODEL_NOT_CONFIGURED`, `PROVIDER_AUTH_FAILED`, `INVALID_PROVIDER_RESPONSE`.
  No provider text, token or environment-variable value is returned.
- A run stops after an infrastructure failure; the remaining cases are SKIPPED. A run where no case could be scored is FAILED.

Limits of the suite: four synthetic cases, pattern-based scoring, possible false positives and negatives. A PASS means
the model behaved as expected on these inputs. It does not establish general safety.

## Stage 1 endpoints (analytics, read-only)

Every error uses the envelope `{"error": {"code": "...", "message": "..."}}`.

| Path | Returns | Errors |
|---|---|---|
| `/v1/health` | status, API and package versions, counts of endpoints and profiles | 503 `CONFIG_UNAVAILABLE` |
| `/v1/endpoints` | endpoint names, provider, data locality, model id, timeout, and whether an API key is configured (presence only) | 503 `CONFIG_UNAVAILABLE` |
| `/v1/security/profiles` | profile metadata: id, version, name, transfer flags, tool and approval lists | 503 `CONFIG_UNAVAILABLE` |
| `/v1/datasets/demo` | demo dataset: id, origin `SYNTHETIC_DEMO`, file name, validation summary, period | 503 `DATASET_UNAVAILABLE` |
| `/v1/datasets/demo/analysis?include_groups=false` | deterministic metrics (overall by default) with values, status, unit, limitations | 503 `DATASET_UNAVAILABLE`, 422 `VALIDATION_ERROR` |

Other errors: 404 `NOT_FOUND`, 405 `METHOD_NOT_ALLOWED`, 500 `INTERNAL_ERROR` (no traceback is returned).

### Example

    curl http://127.0.0.1:8000/v1/datasets/demo/analysis

    {
      "dataset_id": "demo-sample-campaigns",
      "origin": "SYNTHETIC_DEMO",
      "period": {"start": "2026-09-01", "end": "2026-09-03"},
      "include_groups": false,
      "metric_count": 8,
      "metrics": [
        {"metric_id": "spend", "scope": "overall", "value": 1400.0, "status": "OK", "unit": "currency",
         "value_undefined_reason": null, "limitations": ["currency of spend and revenue is not specified in the CSV"]}
      ]
    }

(The response also includes `calc_id`, `group_key`, `formula` and `period` for each metric; they are omitted here for brevity. Overall scope returns eight metrics: roas, cpa, ctr, impressions, clicks, conversions, spend and revenue. Only the first, spend, is shown in the example.)

## Security notes

- The API has no authentication. It is for a single local user on your own machine. Do not expose it to a network.
- It returns no API keys, no environment variable values and no credential-bearing URLs.
- User-uploaded data is never sent to cloud models. Upload endpoints are not part of Stage 1.
- The `/v1/safety/scan` endpoint is intentionally not implemented.
- CORS is off unless `LAB_CORS_ORIGINS` lists exact origins (never a wildcard, never credentials). See `DEPLOYMENT.md`.
- The analytics routes are read-only. Model-backed routes (below) call models only through the existing adapter, which enforces the external-transfer policy.
