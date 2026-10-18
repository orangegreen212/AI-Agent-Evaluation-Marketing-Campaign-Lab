# Running and deploying the lab

Status words used below: **verified** = executed in this project's checks, **not verified** = written from reading the
code or documentation, never executed. See "What has and has not been verified" at the end.

## What can work where

| Setup | Analyze | Evaluate & Safety | Agent Chat (LM Studio) |
|---|---|---|---|
| A. Everything on your PC (Vite dev server + local backend) | yes | yes (local model; hosted only if enabled) | **yes** |
| B. Vercel-hosted frontend, backend still on your PC | yes | yes | **yes, from your own browser only** (see B) |
| C. Vercel-hosted frontend + backend on a remote server | yes | hosted-model runs only (synthetic suite) | **no** |

Why C cannot chat: chat messages may be sent only to LOCAL endpoints, and a LOCAL endpoint must be a loopback address
(enforced in `configs`/`ModelEndpoint`). A remote server therefore cannot reach your LM Studio, and sending chat text to
Hugging Face or OpenRouter is blocked by the transfer policy. This repository does not weaken that.

With the old frontend-only setup Vercel served just the static page (so `/v1/*` returned 404). Section D below runs the
Python API on Vercel as well. A page served by Vercel still cannot reach a service listening on someone's `localhost`.

## D. Everything on Vercel (frontend + Python API + hosted chat)

The repository root now contains `vercel.json`, `api/index.py` and `requirements.txt`. Vercel builds the Vite frontend
and runs the FastAPI app as a serverless function; `/v1/*` is rewritten to it, so the browser talks to its own origin
(no CORS, `VITE_API_BASE_URL` stays empty). Analyze (demo + CSV upload) and Evaluate work out of the box. Chat needs a
hosted model, because a serverless function cannot reach LM Studio on your PC.

1. Vercel project settings: **Root Directory = repository root** (empty, not `frontend`), Framework Preset: Other.
   The build/output commands come from `vercel.json`.
2. Environment variables (Project Settings, Environment Variables), then redeploy:

| Name | Value |
|---|---|
| `LAB_ALLOW_CLOUD_CHAT` | `1` (explicit opt-in: chat text is sent to the provider below) |
| `CLOUD_MODEL_API_KEY` | your provider key (server-side only; never a `VITE_*` variable) |
| `CLOUD_MODEL_BASE_URL` | OpenAI-compatible HTTPS base URL, e.g. `https://api.openai.com/v1` or `https://openrouter.ai/api/v1` |
| `CLOUD_MODEL_ID` | a chat model id that provider offers |

   Hugging Face works the same way with `HF_TOKEN` and `HF_MODEL_ID` (endpoint `hf_inference`).
3. On Vercel the loopback `local_lmstudio` endpoint is hidden. Messages containing secret patterns (API keys, bearer
   tokens, ...) are still refused before leaving the server. The API has no authentication, so anyone who finds the URL
   can spend your key: set a spend limit at the provider, or put Vercel Deployment Protection in front of the site.
4. Limits: request bodies up to about 4 MB (CSV upload is capped at 4 MB), function time 60 s (`maxDuration`).
   Uploaded CSVs are processed in memory/temp storage for one request and are not stored.

## A. Local: PowerShell

Start LM Studio, load a chat model, and start its local server (default `http://127.0.0.1:1234/v1`).

Backend (window 1), from the `lab` folder:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev,api]"
$env:LM_STUDIO_BASE_URL = "http://127.0.0.1:1234/v1"
$env:LM_STUDIO_MODEL_ID = "qwen3.5-4b:2"     # the identifier LM Studio shows for the loaded model
python -m lab.api --port 8000
```

Frontend (window 2), from `lab\frontend`:

```powershell
npm ci
npm run dev
```

Open the printed URL (usually http://localhost:5173), choose **Agent Chat**, and send a message. Leave
`VITE_API_BASE_URL` empty: the dev server forwards `/v1` to `127.0.0.1:8000`, so the browser never needs CORS.

If chat shows an error:
- "cannot reach the model server": LM Studio's server is not running, or `LM_STUDIO_BASE_URL` is wrong.
- "unusable response": the model returned empty text. Reasoning models can spend the whole output budget
  (`max_output_tokens: 1500` in `configs/models.yaml`) on hidden reasoning. Check LM Studio's reasoning settings.
- Replies that start with a reasoning block (`<think>`…) come from the model and are shown as-is; this app does not strip them.

## B. Vercel frontend + backend on your own PC (not verified in a browser)

This is the only way a Vercel-hosted page can talk to LM Studio: your browser, on your PC, calls the backend that runs
on your PC. It works only on that PC.

1. Run the backend as in A, with the Vercel origin allowed:
   ```powershell
   $env:LAB_CORS_ORIGINS = "https://<your-project>.vercel.app"
   python -m lab.api --port 8000
   ```
2. In Vercel set `VITE_API_BASE_URL=http://127.0.0.1:8000` and redeploy (Vite embeds it at build time).
3. Open the Vercel site in a browser on the same PC.

Caveats (browser behaviour, not tested here): some browsers block or prompt for requests from a public HTTPS page to
`http://127.0.0.1` (Safari blocks it; recent Chrome/Edge may ask for local-network permission). Only the exact origin in
`LAB_CORS_ORIGINS` is allowed. Vercel preview deployments have different URLs and are not allowed unless listed,
because wildcards are rejected on purpose. Do not expose the backend through a public tunnel: the API has no authentication.

## Vercel steps (frontend only)

1. Import the Git repository in Vercel.
2. Root Directory: the folder that holds `package.json`, for example `lab/frontend`.
3. Framework Preset: Vite. Install Command: `npm ci`. Build Command: `npm run build`. Output Directory: `dist`.
4. Environment variable: `VITE_API_BASE_URL` (see B). With it empty, the site loads but every backend call fails, and the
   UI says the server did not return an API response.
5. Deploy. No `vercel.json` is needed: the app is one static page with no client-side routes.

Never put `HF_TOKEN` or any other secret in Vercel's frontend variables or in a `VITE_*` variable.

## Environment variables

Backend (server environment only):

| Name | Purpose |
|---|---|
| `LM_STUDIO_BASE_URL`, `LM_STUDIO_MODEL_ID` | local model endpoint (loopback only) |
| `LAB_CORS_ORIGINS` | comma-separated exact origins allowed to call the API; empty = no CORS headers |
| `LAB_ALLOW_CLOUD_EVALUATION` | `1` allows hosted-model **evaluation** of the synthetic suite; chat is never allowed |
| `HF_TOKEN`, `HF_MODEL_ID`, `HF_BASE_URL` | Hugging Face endpoint (evaluation only); `HF_TOKEN` is secret |
| `CLOUD_MODEL_API_KEY`, `CLOUD_MODEL_BASE_URL`, `CLOUD_MODEL_ID` | generic OpenAI-compatible hosted endpoint (evaluation only) |

Frontend (public, build time): `VITE_API_BASE_URL`.

## Hosted-model evaluation (optional, not verified against a live provider)

Only synthetic suite inputs are sent, only when `LAB_ALLOW_CLOUD_EVALUATION=1`, and never chat text.
1. Hugging Face: Settings, Access Tokens, create a token that may call Inference Providers (check the current UI for the
   permission name). Set it only in the backend's environment.
2. Choose a model that supports OpenAI-style chat completions for your account and verify it on the Hugging Face site.
   The default base URL in `configs/models.yaml` (`https://router.huggingface.co/v1`) is **not verified**; override with
   `HF_BASE_URL` if the current documentation differs. Free tiers can be rate-limited, have quotas and cold starts, and can change.

A remote host for the backend is outside this repository. `python -m lab.api` refuses non-loopback hosts. A starting point
(not tested, and only acceptable behind TLS and an authentication layer you provide):
`uvicorn lab.api.app:create_app --factory --host 0.0.0.0 --port 8000`.

## Tests

```powershell
# backend, from lab\
pytest -q
# frontend, from lab\frontend\
npm test
npm run typecheck
npm run lint
npm run build
```

Backend tests use fake transports: no LM Studio, no token, no network. `npm test` runs through `npx --yes tsx`, which is
downloaded on first use and is not pinned as a dependency.

## What has and has not been verified

Verified in this project's checks: the scoring rules (executed), the frontend client, chat state and chat journey logic
(25 Node tests), a strict TypeScript check of all frontend source and tests using stand-in React typings, and syntax
of every Python file.
Not verified: pytest (the backend web stack was not installed), `npm ci`/`lint`/`build`, any real browser run, LM Studio
and Hugging Face calls, and any Vercel deployment.

## Known limitations

- No React component or browser test exists; the journey tests cover the client and state logic, not rendering.
- Chat history lives in the browser tab only. Reloading clears it.
- The API has no authentication. It is designed for a single local user.
- Compare Models is a labelled demo. CSV upload (Analyze) is implemented: up to 4 MB, analyzed in memory, nothing stored.
- Hosted chat is opt-in (`LAB_ALLOW_CLOUD_CHAT=1`) and sends messages to the configured provider; the default stays local-only.
