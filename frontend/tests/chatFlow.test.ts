/**
 * The chat user journey (type, send, receive, fail) using the real API client and chat state with a fake fetch.
 * sendTurn mirrors the logic in ChatView.send. This is not a React render test.
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createLiveClient, type FetchLike } from '@/lib/apiClient';
import { chatErrorMessage } from '@/lib/chatErrors';
import {
  beginSend,
  checkDraft,
  failSend,
  historyFor,
  initialChatState,
  receiveReply,
  type ChatState,
} from '@/lib/chatState';

type Client = ReturnType<typeof createLiveClient>;

async function sendTurn(state: ChatState, draft: string, client: Client) {
  const check = checkDraft(draft);
  if (!check.ok) return { state, restoreDraft: draft };
  const history = historyFor(state);
  const pending = beginSend(state, check.text);
  try {
    const reply = await client.sendChat({ endpoint: 'local_lmstudio', message: check.text, history });
    return { state: receiveReply(pending, reply), restoreDraft: '' };
  } catch (err) {
    const out = failSend(pending, chatErrorMessage(err));
    return { state: out.state, restoreDraft: out.restoreDraft };
  }
}

const replyBody = (text: string) => ({
  reply: text, reply_is: 'untrusted model output', endpoint: 'local_lmstudio', provider: 'LOCAL',
  model_id: 'qwen-local', served_model: 'qwen-served', latency_ms: 9, tokens_in: 3, tokens_out: 2,
  cost_usd: null, finish_reason: 'stop',
});

function scripted(...answers: (Response | Error)[]): { fetch: FetchLike; bodies: unknown[] } {
  const bodies: unknown[] = [];
  const queue = [...answers];
  const fetchImpl: FetchLike = async (_url, init) => {
    bodies.push(JSON.parse(String(init?.body)));
    const next = queue.shift();
    if (!next) throw new Error('no scripted answer left');
    if (next instanceof Error) throw next;
    return next;
  };
  return { fetch: fetchImpl, bodies };
}

const ok = (text: string) => new Response(JSON.stringify(replyBody(text)), { status: 200 });
const err = (status: number, code: string, message: string) =>
  new Response(JSON.stringify({ error: { code, message } }), { status });

test('two turns: the reply shows provider and model, and the second request carries the first turn as history', async () => {
  const s = scripted(ok('first answer'), ok('second answer'));
  const client = createLiveClient('', s.fetch);
  let state = initialChatState();
  ({ state } = await sendTurn(state, '  question one  ', client));
  ({ state } = await sendTurn(state, 'question two', client));

  assert.deepEqual(state.messages.map((m) => [m.role, m.content]), [
    ['user', 'question one'], ['assistant', 'first answer'], ['user', 'question two'], ['assistant', 'second answer'],
  ]);
  assert.equal(state.messages[1].meta?.provider, 'LOCAL');
  assert.equal(state.messages[1].meta?.modelId, 'qwen-local');
  assert.deepEqual((s.bodies[0] as { history: unknown[] }).history, []);
  assert.deepEqual((s.bodies[1] as { history: unknown[] }).history, [
    { role: 'user', content: 'question one' }, { role: 'assistant', content: 'first answer' },
  ]);
  assert.equal(state.pending, false);
  assert.equal(state.error, null);
});

test('rate limit: a clear message, no fabricated reply, and the draft is returned for retry', async () => {
  const client = createLiveClient('', scripted(err(429, 'RATE_LIMITED', 'provider rate limit reached')).fetch);
  const out = await sendTurn(initialChatState(), 'please answer', client);
  assert.match(out.state.error ?? '', /rate-limiting/);
  assert.equal(out.state.messages.length, 0);
  assert.equal(out.restoreDraft, 'please answer');
  assert.equal(out.state.pending, false);
});

test('policy block, timeout, unreachable model and a bad provider response each give their own message', async () => {
  const cases: [Response, RegExp][] = [
    [err(403, 'TRANSFER_BLOCKED', 'x'), /Blocked by policy/],
    [err(504, 'MODEL_TIMEOUT', 'x'), /did not respond in time/],
    [err(503, 'MODEL_UNREACHABLE', 'x'), /LM Studio is running/],
    [err(502, 'INVALID_PROVIDER_RESPONSE', 'x'), /unusable response/],
  ];
  for (const [response, pattern] of cases) {
    const out = await sendTurn(initialChatState(), 'hi', createLiveClient('', scripted(response).fetch));
    assert.match(out.state.error ?? '', pattern);
    assert.equal(out.state.messages.length, 0); // nothing fabricated, the unanswered message was removed
  }
});

test('backend unreachable: the user sees that the backend could not be reached', async () => {
  const client = createLiveClient('https://api.example.com', scripted(new TypeError('Failed to fetch')).fetch);
  const out = await sendTurn(initialChatState(), 'hi', client);
  assert.match(out.state.error ?? '', /Could not reach the backend/);
  assert.equal(out.state.messages.length, 0);
});

test('an invalid draft never reaches the network', async () => {
  const s = scripted();
  const out = await sendTurn(initialChatState(), '   ', createLiveClient('', s.fetch));
  assert.equal(s.bodies.length, 0);
  assert.equal(out.state.messages.length, 0);
});
