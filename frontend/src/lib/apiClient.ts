/**
 * API client for the AI Agent Evaluation & Safety Lab.
 *
 * LIVE (FastAPI backend):
 *   health, getDemoDataset, getDemoAnalysis         Analyze (read-only demo dataset)
 *   getEndpoints, getTestSuites, runEvaluation      Evaluate & Safety (synthetic suite, one model per run)
 *   sendChat                                        Agent Chat (local endpoints only; see backend policy)
 *
 * DEMO ONLY (fixtures in src/demo, no network call):
 *   listModels, listDemoTestSuites, compare         Compare Models
 *
 * NOT IMPLEMENTED: CSV upload. Nothing is sent.
 *
 * Base URL: VITE_API_BASE_URL (read at build time).
 *   - empty: requests are relative (/v1/...). Works only where something serves /v1: the Vite dev server (proxy to
 *     127.0.0.1:8000) or `vite preview`. On a static host such as Vercel nothing answers /v1, and the UI says so.
 *   - set: requests go to that origin; the backend must allow this site's origin in LAB_CORS_ORIGINS.
 * Secrets never appear in this file or in any VITE_* variable (Vite embeds those in the browser bundle).
 */

import type {
  ChatReplyDto,
  DemoAnalysisResponse,
  DemoDatasetResponse,
  EndpointsResponse,
  ErrorEnvelope,
  EvaluationResponse,
  HealthResponse,
  TestSuitesResponse,
} from '@/types/backend';
import type {
  CompareResponse,
  ModelsResponse,
  TestSuitesResponse as DemoTestSuitesResponse,
} from '@/types/api';

export function normalizeBaseUrl(raw: string | undefined): string {
  return (raw ?? '').trim().replace(/\/+$/, '');
}

// import.meta.env is provided by Vite; it is undefined when this module runs under plain Node (unit tests).
const API_BASE_URL = normalizeBaseUrl(import.meta.env?.VITE_API_BASE_URL as string | undefined);

/** Which data source each view uses. Keep in sync with the views and the README. */
export const dataSourceByView = {
  analyze: 'live',
  evaluate: 'live',
  chat: 'live',
  compare: 'demo',
} as const;

export const apiConfig = {
  baseUrl: API_BASE_URL,
  dataSourceByView,
};

export class ApiError extends Error {
  status: number;
  code: string | null;
  constructor(message: string, status: number, code: string | null = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

const defaultFetch: FetchLike = (input, init) => fetch(input, init);

/** The live (backend) calls, bound to a base URL and a fetch implementation. Tests pass a fake fetch. */
export function createLiveClient(baseUrl: string, fetchImpl: FetchLike = defaultFetch) {
  const where = baseUrl === '' ? 'this site' : baseUrl;

  async function request<T>(path: string, init?: RequestInit): Promise<T> {
    let res: Response;
    try {
      res = await fetchImpl(`${baseUrl}${path}`, init);
    } catch {
      // A browser reports network failures and CORS rejections the same way, so both are named.
      throw new ApiError(
        `Could not reach the backend at ${where}. Check that it is running (locally: python -m lab.api --port 8000). ` +
          'For a hosted frontend, check VITE_API_BASE_URL and that the backend lists this site in LAB_CORS_ORIGINS.',
        0,
        'NETWORK_ERROR',
      );
    }

    const text = await res.text().catch(() => '');
    let body: unknown = null;
    try {
      body = text === '' ? null : JSON.parse(text);
    } catch {
      body = null; // not JSON: handled below
    }

    if (!res.ok) {
      const envelope = body as Partial<ErrorEnvelope> | null;
      if (envelope?.error?.message) {
        throw new ApiError(envelope.error.message, res.status, envelope.error.code ?? null);
      }
      throw new ApiError(
        `The server at ${where} did not return an API response (HTTP ${res.status}). ` +
          'Check that the backend is running and that VITE_API_BASE_URL points to it.',
        res.status,
        'NOT_AN_API_RESPONSE',
      );
    }
    if (body === null || typeof body !== 'object') {
      throw new ApiError(
        `The server at ${where} answered with something that is not JSON. ` +
          'Check that VITE_API_BASE_URL points to the backend and not to a web page.',
        res.status,
        'INVALID_RESPONSE',
      );
    }
    return body as T;
  }

  const getJson = <T>(path: string) => request<T>(path, { headers: { Accept: 'application/json' } });
  const postJson = <T>(path: string, payload: unknown) =>
    request<T>(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(payload),
    });

  return {
    // ---- analyze ---------------------------------------------------------------------------------------------
    health: () => getJson<HealthResponse>('/v1/health'),
    getDemoDataset: () => getJson<DemoDatasetResponse>('/v1/datasets/demo'),
    getDemoAnalysis: () => getJson<DemoAnalysisResponse>('/v1/datasets/demo/analysis'),

    // ---- evaluate ----------------------------------------------------------------------------------------------
    getEndpoints: () => getJson<EndpointsResponse>('/v1/endpoints'),
    getTestSuites: () => getJson<TestSuitesResponse>('/v1/test-suites'),
    runEvaluation: (endpoint: string, suiteId: string) =>
      postJson<EvaluationResponse>('/v1/evaluations', { endpoint, suite_id: suiteId }),

    // ---- chat --------------------------------------------------------------------------------------------------
    async sendChat(args: {
      endpoint: string;
      message: string;
      history: { role: 'user' | 'assistant'; content: string }[];
    }): Promise<ChatReplyDto> {
      const reply = await postJson<ChatReplyDto>('/v1/chat', args);
      if (typeof reply.reply !== 'string') {
        throw new ApiError('The backend answered without a model reply.', 200, 'INVALID_RESPONSE');
      }
      return reply;
    },
  };
}

export const apiClient = {
  config: apiConfig,
  ...createLiveClient(API_BASE_URL),

  // ---- demo only ---------------------------------------------------------------------------------------------

  /** DEMO ONLY: fixture model list for Compare Models. */
  async listModels(): Promise<ModelsResponse> {
    return demoProxy('models');
  },

  /** DEMO ONLY: fixture test suites for Compare Models. */
  async listDemoTestSuites(): Promise<DemoTestSuitesResponse> {
    return demoProxy('test-suites');
  },

  /** DEMO ONLY: fixture comparison. Does not call any model. */
  async compare(modelIds: string[], testSuiteId: string): Promise<CompareResponse> {
    return demoProxy('compare', { modelIds, testSuiteId });
  },
};

// ---------------------------------------------------------------------------------------------------------------
// Demo proxy: lazily imports fixtures. Used only by the demo-only Compare Models view.
// ---------------------------------------------------------------------------------------------------------------

function demoProxy(kind: 'models'): Promise<ModelsResponse>;
function demoProxy(kind: 'test-suites'): Promise<DemoTestSuitesResponse>;
function demoProxy(kind: 'compare', args: { modelIds: string[]; testSuiteId: string }): Promise<CompareResponse>;
async function demoProxy(
  kind: 'models' | 'test-suites' | 'compare',
  args?: Record<string, unknown>,
): Promise<unknown> {
  const demo = await import('@/demo');
  await new Promise((r) => setTimeout(r, 700 + Math.random() * 600));
  switch (kind) {
    case 'models':
      return { models: demo.demoModels };
    case 'test-suites':
      return { testSuites: demo.demoTestSuites };
    case 'compare':
      return demo.demoCompare(args!.modelIds as string[], args!.testSuiteId as string);
  }
}
