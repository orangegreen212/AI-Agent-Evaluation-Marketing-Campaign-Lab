import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { test } from 'node:test';
import { ApiError, createLiveClient, normalizeBaseUrl, type FetchLike } from '@/lib/apiClient';

interface Call {
  url: string;
  init?: RequestInit;
}

function fakeFetch(responder: (call: Call) => Response): { fetch: FetchLike; calls: Call[] } {
  const calls: Call[] = [];
  const fetchImpl: FetchLike = async (url, init) => {
    const call = { url, init };
    calls.push(call);
    return responder(call);
  };
  return { fetch: fetchImpl, calls };
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

const CHAT_REPLY = {
  reply: 'Hello', reply_is: 'untrusted model output', endpoint: 'local_lmstudio', provider: 'LOCAL',
  model_id: 'qwen-local', served_model: null, latency_ms: 5, tokens_in: null, tokens_out: null,
  cost_usd: null, finish_reason: 'stop',
};
const ARGS = { endpoint: 'local_lmstudio', message: 'hi', history: [] };

async function rejection(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (err) {
    assert.ok(err instanceof ApiError, 'expected an ApiError');
    return err;
  }
  throw new Error('expected the promise to reject');
}

test('base URL is normalised', () => {
  assert.equal(normalizeBaseUrl(undefined), '');
  assert.equal(normalizeBaseUrl('  https://api.example.com/// '), 'https://api.example.com');
});

test('empty base URL: chat is a relative POST /v1/chat with only content headers and a JSON body', async () => {
  const f = fakeFetch(() => json(CHAT_REPLY));
  const reply = await createLiveClient('', f.fetch).sendChat({ ...ARGS, message: 'hello there' });
  assert.equal(reply.reply, 'Hello');
  assert.equal(f.calls[0].url, '/v1/chat');
  assert.equal(f.calls[0].init?.method, 'POST');
  assert.deepEqual(JSON.parse(String(f.calls[0].init?.body)), { ...ARGS, message: 'hello there' });
  assert.deepEqual(Object.keys(f.calls[0].init?.headers as Record<string, string>).sort(), ['Accept', 'Content-Type']);
});

test('configured base URL is used for every live call and no call is hard-wired to localhost', async () => {
  const f = fakeFetch(() => json({ endpoints: [], test_suites: [] }));
  const client = createLiveClient('https://api.example.com', f.fetch);
  await client.getEndpoints();
  await client.getTestSuites();
  assert.deepEqual(f.calls.map((c) => c.url), ['https://api.example.com/v1/endpoints', 'https://api.example.com/v1/test-suites']);
  const rel = fakeFetch(() => json({ endpoints: [] }));
  await createLiveClient('', rel.fetch).getEndpoints();
  assert.ok(rel.calls.every((c) => c.url.startsWith('/v1/')));
});

test('a backend error envelope becomes an ApiError with its code, message and status', async () => {
  const f = fakeFetch(() => json({ error: { code: 'RATE_LIMITED', message: 'provider rate limit reached' } }, 429));
  const err = await rejection(createLiveClient('', f.fetch).sendChat(ARGS));
  assert.equal(err.code, 'RATE_LIMITED');
  assert.equal(err.status, 429);
  assert.equal(err.message, 'provider rate limit reached');
});

test('an HTML 404 (no backend behind the site) is explained, and does not tell a hosted user to run the local command', async () => {
  const f = fakeFetch(() => new Response('<html>404</html>', { status: 404 }));
  const err = await rejection(createLiveClient('', f.fetch).getEndpoints());
  assert.equal(err.code, 'NOT_AN_API_RESPONSE');
  assert.match(err.message, /HTTP 404/);
  assert.match(err.message, /VITE_API_BASE_URL/);
  assert.doesNotMatch(err.message, /python -m lab\.api/);
});

test("a static host's JSON 404 (numeric code) is reported as a missing backend, not shown as a backend error", async () => {
  const f = fakeFetch(() => json({ error: { code: '404', message: 'The page could not be found' } }, 404));
  const err = await rejection(createLiveClient('', f.fetch).getDemoDataset());
  assert.equal(err.code, 'NOT_AN_API_RESPONSE');
  assert.match(err.message, /VITE_API_BASE_URL/);
});

test('a 200 response that is not JSON is rejected instead of crashing the parser', async () => {
  const f = fakeFetch(() => new Response('<!doctype html><html></html>', { status: 200 }));
  const err = await rejection(createLiveClient('', f.fetch).getEndpoints());
  assert.equal(err.code, 'INVALID_RESPONSE');
});

test('a network or CORS failure names both likely causes', async () => {
  const failing: FetchLike = async () => {
    throw new TypeError('Failed to fetch');
  };
  const err = await rejection(createLiveClient('https://api.example.com', failing).sendChat(ARGS));
  assert.equal(err.code, 'NETWORK_ERROR');
  assert.equal(err.status, 0);
  assert.match(err.message, /https:\/\/api\.example\.com/);
  assert.match(err.message, /LAB_CORS_ORIGINS/);
});

test('a chat response without a reply is rejected, so an empty assistant bubble is never shown', async () => {
  const f = fakeFetch(() => json({ endpoint: 'local_lmstudio' }));
  const err = await rejection(createLiveClient('', f.fetch).sendChat(ARGS));
  assert.equal(err.code, 'INVALID_RESPONSE');
});

test('analyzeCsv posts the raw CSV text with a text/csv content type and the encoded filename', async () => {
  const f = fakeFetch(() => json({ dataset: {}, analysis: null, issues: [] }));
  await createLiveClient('', f.fetch).analyzeCsv('date,campaign\n', 'my file.csv');
  assert.equal(f.calls[0].url, '/v1/datasets/analyze?filename=my%20file.csv');
  assert.equal(f.calls[0].init?.method, 'POST');
  assert.equal(f.calls[0].init?.body, 'date,campaign\n');
  assert.match(String((f.calls[0].init?.headers as Record<string, string>)['Content-Type']), /^text\/csv/);
});

test('no credential-like strings exist anywhere in the frontend source', () => {
  const root = join(process.cwd(), 'src');
  const forbidden = [/HF_TOKEN/, /\bhf_[A-Za-z0-9]{10,}/, /\bsk-[A-Za-z0-9_-]{20,}/, /Bearer\s/, /Authorization/i];
  const offenders: string[] = [];
  for (const rel of readdirSync(root, { recursive: true }) as string[]) {
    if (!/\.(ts|tsx)$/.test(rel)) continue;
    const text = readFileSync(join(root, rel), 'utf8');
    for (const re of forbidden) if (re.test(text)) offenders.push(`${rel}: ${re}`);
  }
  assert.deepEqual(offenders, []);
});
