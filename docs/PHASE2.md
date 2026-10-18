# Phase 2 - model adapters and local/cloud smoke comparison

Code: `src/lab/models/` (`config.py`, `adapter.py`, `advisor.py`, `smoke.py`), `configs/models.yaml`. Tests: `tests/models/`.
No new dependencies (stdlib `urllib`). Phase 0 contracts are reused unchanged: `RunConfig` (its `fingerprint()` is the configuration hash), `RunMetrics`, `RunRecord`, `DecisionReport`, `validate_evidence`, `apply_approval_policy`, `sanitize_output`, security profiles.

## Design

    analysis (Phase 1 metrics) -> build_messages (aggregates only) -> adapter.complete -> sanitize -> parse JSON
        -> DecisionReport (+ system-owned traceability) -> validate_evidence vs Phase 1 metrics -> apply_approval_policy

* `OpenAICompatAdapter` speaks `POST {base_url}/chat/completions`. It serves LM Studio and any OpenAI-compatible HTTPS provider; both satisfy the `ModelAdapter` protocol, so one orchestrator drives either.
* `advise()` returns an `AdvisorResult`. Only a response that parses, satisfies `DecisionReport` **and** whose evidence matches the deterministic metrics (same calc id, metric id, value, period) becomes a report. Anything else gives `report=None` plus a `failure_kind`. A report is never fabricated or "repaired".
* The model writes content only. `schema_version` and `traceability` are filled in by the system; if the model supplies them they are discarded.
* `to_run_record()` builds a Phase 0 `RunRecord`. It **refuses** to create a COMPLETED record without a verdict from an evaluator (a later phase), so run status, agent status, test verdict and aggregate status remain independent. Timeouts give `TIMEOUT`, other failures `ERROR`, both with verdict `ERROR`, no agent status and no report.

### Failure kinds
`TRANSFER_BLOCKED`, `CONFIG`, `CONNECTION`, `TIMEOUT`, `HTTP_ERROR`, `BAD_RESPONSE` (provider payload unusable), `MALFORMED_OUTPUT` (not a JSON object, or the provider reported `finish_reason=length`: output cut off at `max_tokens`), `SCHEMA_INVALID`, `EVIDENCE_MISMATCH`.
Error details are built from types and codes only, never from response bodies, exception text, prompts or keys. Schema errors list field locations and error types, not values.

## Safety rules (all enforced in code and tested)

| Rule | Where |
|---|---|
| CLOUD needs `external_data_transfer: true` in the profile (default profile: false) | `enforce_transfer_policy` |
| CLOUD only receives `DataOrigin.SYNTHETIC_DEMO`; the default origin everywhere is `USER_DATA` | same |
| Outbound text matching the profile's secret patterns (or a protected canary) is never sent to the cloud | same |
| A `LOCAL` endpoint must be a loopback host, so a remote server cannot be labelled local | `ModelEndpoint` |
| Prompt contains aggregates only: no rows, no per-day data | `build_messages` |
| API key: only the env var NAME is configured; read per call; sent only in the Authorization header; not stored, logged or put in errors | adapter |
| No redirects followed (key cannot be forwarded to another host) | `urllib_transport` |
| Model text is sanitized (secrets, canaries) before it is parsed; the only text returned is `SanitizedOutput`; nothing is written to disk by this package | `advise` |
| No tools are sent to the model; actions in the plan are text. `apply_approval_policy` sets `requires_approval_effective` from the profile, overriding the model's claim | `advise` |
| Logs are one JSON object per call on logger `lab.models`: ids, hashes, latency, tokens, cost, failure kind. Never prompts, responses or keys | adapter |

`smoke.data_origin_for` treats a dataset as synthetic only if it is under `datasets/demo/`.

## Configuration

`configs/models.yaml` (no secrets). Environment overrides: `LM_STUDIO_BASE_URL`, `LM_STUDIO_MODEL_ID`, `CLOUD_MODEL_BASE_URL`, `CLOUD_MODEL_ID`. Secret: `CLOUD_MODEL_API_KEY`. Copy `.env.example` to `.env` (git-ignored) and export the variables yourself; nothing here loads `.env` automatically.

Metadata per run: model id (config), model version (config, `unspecified` if not set), served model (from the response, if present), configuration hash (`RunConfig.fingerprint()`: provider, model, version, prompt version, temperature, max tokens, timeout, seed, structured-output mode), prompt version (`advisor-v2.1`, changed in Phase 2.1: see `PHASE2_1.md`; `advisor-v2` failed live and is archived), input hash (hash of the prompt, not the data), latency, tokens in/out if the provider reports them, cost if tokens and both prices are configured (`None` otherwise; local cost is `None`, not applicable).
`base_url` is not part of the configuration hash.

## LM Studio (local)

1. Install LM Studio, download a model, load it.
2. In the Developer tab, start the local server (default `http://localhost:1234`).
3. Set the model identifier LM Studio shows: `export LM_STUDIO_MODEL_ID="<identifier>"` (optional: `LM_STUDIO_BASE_URL`).
4. Optionally put the quantization in `model_version` in `configs/models.yaml` for traceability.

LM Studio accepts only `json_schema` response formats, not `json_object`, so the local entry uses `structured_output_mode: NONE` and relies on the prompt plus strict validation. Small local models may well fail the schema; that is reported as `MALFORMED_OUTPUT` / `SCHEMA_INVALID`, not hidden.
The parser takes the text between the first `{` and the last `}` (to tolerate code fences or a sentence around the JSON); the result still has to pass the full validation.

## Cloud provider

1. Any OpenAI-compatible HTTPS API: set `CLOUD_MODEL_BASE_URL` (or edit `base_url`) and `CLOUD_MODEL_ID`. `model_id` ships as the placeholder `your-cloud-model-id`.
2. `export CLOUD_MODEL_API_KEY=...` in your shell. Never write it into a file in the repo, a config, or a test.
3. Optionally fill `price_per_1m_input_usd` / `price_per_1m_output_usd` for cost estimates.
4. Cloud calls work **only** with the `benchmark` profile and a dataset under `datasets/demo/`. Anything else returns `TRANSFER_BLOCKED` without touching the network.

Providers with a non-OpenAI wire format (e.g. Anthropic's native Messages API) are not covered; use their OpenAI-compatible endpoint if they offer one, or add an adapter.

## Smoke comparison (not the evaluation benchmark)

    python -m lab.models.smoke                                  # local + cloud; cloud shows TRANSFER_BLOCKED (default profile)
    python -m lab.models.smoke --cloud-profile benchmark        # explicit opt-in: synthetic demo aggregates go to the cloud
    python -m lab.models.smoke --endpoints local_lmstudio --json
    python -m lab.models.smoke --dataset datasets/demo/sample_campaigns.csv

Prints, per endpoint: run status, report validity, agent status, latency, tokens, cost, served model, profile, failure kind, and which metadata fields are missing. Exit code 0 only if every endpoint produced a valid report. Single runs; no repeats, no evaluator, no aggregation.

Optional live tests (excluded from the normal run): `LAB_LIVE_LOCAL=1 pytest -m live -s`, `LAB_LIVE_CLOUD=1 CLOUD_MODEL_API_KEY=... pytest -m live -s`.

## Tests

    pytest                  # everything except scale and live; warnings are errors
    pytest -m live -s       # optional real endpoints
    pytest -m scale -s      # Phase 1 1M-row test

`tests/models/` uses a real loopback HTTP server as a stand-in for LM Studio (success, connection refused, timeout, redirect) and an injected transport for the cloud. No live API is needed.

## Known limitations

* Timeouts are socket-level (connect and each read), not a hard total deadline: a server trickling bytes can exceed `timeout_s`.
* No retries and no streaming, deliberately: repeats and flakiness belong to the later aggregation phase.
* `structured_output_mode: SCHEMA` is rejected as unsupported; only NONE and JSON_MODE exist.
* Synthetic origin = path under `datasets/demo/`; copying a private file there defeats it. A hash allow-list would be stricter.
* Secret/canary outbound scan is regex- and verbatim-based; it catches known patterns, not paraphrases.
* Token counts and cost come from the provider's `usage` field and your configured prices; unverified.
* Not run here: any real LM Studio or cloud endpoint. Only mocks and a loopback stand-in server were exercised.
