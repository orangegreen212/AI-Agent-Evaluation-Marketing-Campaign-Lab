# AI Agent Evaluation & Safety Lab: frontend

React + TypeScript + Vite + Tailwind. Lives in the same repository as the FastAPI backend (`../src/lab/api`).
Local prototype. Setup for both local and hosted use is in `../DEPLOYMENT.md`.

## Data sources by view

| View | Source | Notes |
|---|---|---|
| **Analyze** | Backend | Bundled synthetic demo dataset: validation and overall metrics. CSV upload is not implemented. |
| **Evaluate & Safety** | Backend | Runs the synthetic safety suite on one configured model. Shows each model's reported identity and per-case results. |
| **Agent Chat** | Backend | One chat turn per send. Replies are untrusted model output. Local endpoints only (policy). |
| **Compare Models** | Demo only | Fixtures in `src/demo`. Labelled demo. No model is called. |

## Run locally

Terminal 1 (backend, from `lab/`): `python -m lab.api --port 8000`
Terminal 2 (frontend, from `lab/frontend/`): `npm ci` then `npm run dev`

Keep `VITE_API_BASE_URL` empty locally. The Vite dev server forwards `/v1` to `127.0.0.1:8000`.
On a static host (Vercel) nothing answers `/v1`, so `VITE_API_BASE_URL` must be set; see `../DEPLOYMENT.md`.

## Hosted frontend

Set `VITE_API_BASE_URL` to the backend's public HTTPS origin, and add the frontend origin to the backend's
`LAB_CORS_ORIGINS`. Never add a token or other secret to a `VITE_*` variable: Vite embeds those values in the browser
bundle. Rebuild after changing the variable.

## Scripts

```
npm run dev         dev server with the /v1 proxy
npm run typecheck   tsc --noEmit -p tsconfig.app.json
npm run lint        eslint .
npm run build       production build to dist/ (static; deployable to Vercel)
npm run preview     serve dist/ with the same proxy
npm test            client, chat state/journey and adapter tests (uses npx tsx)
```

## Code map

- `src/lib/apiClient.ts`: the only module that makes network requests. Lists which calls are live and which are demo.
- `src/types/backend.ts`: backend response types, exactly as returned (snake_case).
- `src/lib/analysisAdapter.ts`: maps Analyze responses to the view model.
- `src/lib/chatState.ts`, `src/lib/chatErrors.ts`: pure chat state and error messages, tested in `tests/`.
- `src/views/`: `AnalyzeView`, `EvaluateView`, `ChatView`, `CompareView` (demo).
- `src/demo/`: fabricated fixtures for the demo-only Compare view.
