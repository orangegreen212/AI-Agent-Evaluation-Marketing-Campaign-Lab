import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  MAX_HISTORY_CHARS,
  MAX_HISTORY_TURNS,
  MAX_MESSAGE_CHARS,
  beginSend,
  checkDraft,
  failSend,
  historyFor,
  initialChatState,
  newConversation,
  receiveReply,
} from '@/lib/chatState';
import type { ChatReplyDto } from '@/types/backend';

const reply = (text: string): ChatReplyDto => ({
  reply: text, reply_is: 'untrusted model output', endpoint: 'local_lmstudio', provider: 'LOCAL',
  model_id: 'qwen-local', served_model: 'qwen-local-served', latency_ms: 12.3, tokens_in: 5, tokens_out: 4,
  cost_usd: null, finish_reason: 'stop',
});

test('empty and oversized drafts are rejected before any request', () => {
  assert.equal(checkDraft('   ').ok, false);
  assert.equal(checkDraft('x'.repeat(MAX_MESSAGE_CHARS + 1)).ok, false);
  const ok = checkDraft('  hello  ');
  assert.deepEqual(ok, { ok: true, text: 'hello' });
});

test('a successful turn appends the user message, then the model reply with its provider and model', () => {
  let s = beginSend(initialChatState(), 'hi');
  assert.equal(s.pending, true);
  assert.equal(s.messages.length, 1);
  s = receiveReply(s, reply('Hello!'));
  assert.equal(s.pending, false);
  assert.deepEqual(s.messages.map((m) => m.role), ['user', 'assistant']);
  assert.equal(s.messages[1].content, 'Hello!');
  assert.equal(s.messages[1].meta?.provider, 'LOCAL');
  assert.equal(s.messages[1].meta?.modelId, 'qwen-local');
  assert.equal(s.messages[1].meta?.servedModel, 'qwen-local-served');
});

test('a failed send removes the unanswered user message and returns its text for editing', () => {
  const s = beginSend(initialChatState(), 'question');
  const out = failSend(s, 'Rate limit reached');
  assert.equal(out.restoreDraft, 'question');
  assert.equal(out.state.messages.length, 0);
  assert.equal(out.state.pending, false);
  assert.equal(out.state.error, 'Rate limit reached');
});

test('history is only completed turns and is bounded', () => {
  let s = initialChatState();
  for (let i = 0; i < 15; i++) {
    s = beginSend(s, `u${i}`);
    s = receiveReply(s, reply(`a${i}`));
  }
  const h = historyFor(s);
  assert.equal(h.length, MAX_HISTORY_TURNS);
  assert.equal(h[h.length - 1].content, 'a14');
  assert.ok(h.every((m) => m.role === 'user' || m.role === 'assistant'));
});

test('a pending message is not included in its own history', () => {
  const s = beginSend(initialChatState(), 'first');
  assert.equal(historyFor(initialChatState()).length, 0);
  assert.equal(s.messages.length, 1);
});

test('new conversation clears messages and error but keeps ids increasing', () => {
  let s = beginSend(initialChatState(), 'a');
  s = receiveReply(s, reply('b'));
  const fresh = newConversation(s);
  assert.equal(fresh.messages.length, 0);
  assert.equal(fresh.error, null);
  assert.ok(fresh.nextId > s.messages[1].id);
});

test('history drops the oldest whole pairs when over the character budget and keeps alternating from user', () => {
  let s = initialChatState();
  const big = 'x'.repeat(9000);
  for (let i = 0; i < 4; i++) {
    s = beginSend(s, `u${i}`);
    s = receiveReply(s, reply(big));
  }
  const h = historyFor(s);
  assert.ok(h.reduce((n, t) => n + t.content.length, 0) <= MAX_HISTORY_CHARS);
  assert.equal(h[0].role, 'user');
  assert.deepEqual(h.map((t) => t.role), h.map((_, i) => (i % 2 === 0 ? 'user' : 'assistant')));
  assert.equal(h[h.length - 1].role, 'assistant');
  assert.ok(h.length < 8);
});

test('a single pair larger than the budget is dropped rather than sent half-cut', () => {
  let s = beginSend(initialChatState(), 'u');
  s = receiveReply(s, reply('y'.repeat(MAX_HISTORY_CHARS + 1)));
  assert.deepEqual(historyFor(s), []);
});
