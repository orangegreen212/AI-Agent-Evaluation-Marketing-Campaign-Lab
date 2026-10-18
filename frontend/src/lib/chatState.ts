/**
 * Pure state for the Agent Chat page. No React and no network here, so it can be tested directly.
 *
 * Rules:
 *  - Messages exist only if they came from the user or from the model. No fixture or canned replies.
 *  - A failed send removes the unanswered user message and returns its text so the user can edit and retry.
 *    This keeps the history strictly alternating user / assistant.
 *  - History sent to the backend contains only completed turns and is bounded by turn count and by characters.
 *    The oldest user/assistant pair is dropped whole, so roles keep alternating and start with "user".
 */

import type { ChatReplyDto } from '@/types/backend';

export const MAX_MESSAGE_CHARS = 4000;
export const MAX_HISTORY_TURNS = 20;
/** Keeps requests well inside the backend limit (60000) and a small local model's context window. */
export const MAX_HISTORY_CHARS = 24000;

export interface ChatMessage {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  meta?: { provider: string; modelId: string; servedModel: string | null; latencyMs: number };
}

export interface ChatState {
  messages: ChatMessage[];
  pending: boolean;
  error: string | null;
  nextId: number;
}

export function initialChatState(): ChatState {
  return { messages: [], pending: false, error: null, nextId: 1 };
}

export type DraftCheck = { ok: true; text: string } | { ok: false; reason: string };

export function checkDraft(raw: string): DraftCheck {
  const text = raw.trim();
  if (text.length === 0) return { ok: false, reason: 'Type a message first.' };
  if (text.length > MAX_MESSAGE_CHARS) {
    return { ok: false, reason: `Messages are limited to ${MAX_MESSAGE_CHARS} characters.` };
  }
  return { ok: true, text };
}

/** Adds the user's message and marks a request as in flight. Caller must check the draft first. */
export function beginSend(state: ChatState, text: string): ChatState {
  return {
    ...state,
    messages: [...state.messages, { id: state.nextId, role: 'user', content: text }],
    nextId: state.nextId + 1,
    pending: true,
    error: null,
  };
}

/** The completed turns to send with the next request (excludes the message being sent). */
export function historyFor(state: ChatState): { role: 'user' | 'assistant'; content: string }[] {
  let turns = state.messages.map((m) => ({ role: m.role, content: m.content })).slice(-MAX_HISTORY_TURNS);
  if (turns.length > 0 && turns[0].role === 'assistant') turns = turns.slice(1);
  const chars = () => turns.reduce((n, t) => n + t.content.length, 0);
  while (turns.length >= 2 && chars() > MAX_HISTORY_CHARS) turns = turns.slice(2);
  return turns.length === 1 ? [] : turns;
}

export function receiveReply(state: ChatState, reply: ChatReplyDto): ChatState {
  return {
    ...state,
    messages: [
      ...state.messages,
      {
        id: state.nextId,
        role: 'assistant',
        content: reply.reply,
        meta: {
          provider: reply.provider,
          modelId: reply.model_id,
          servedModel: reply.served_model,
          latencyMs: reply.latency_ms,
        },
      },
    ],
    nextId: state.nextId + 1,
    pending: false,
    error: null,
  };
}

/** Removes the unanswered user message and returns its text so it can be restored in the input. */
export function failSend(state: ChatState, message: string): { state: ChatState; restoreDraft: string } {
  const last = state.messages[state.messages.length - 1];
  const restoreDraft = last && last.role === 'user' ? last.content : '';
  const messages = last && last.role === 'user' ? state.messages.slice(0, -1) : state.messages;
  return { state: { ...state, messages, pending: false, error: message }, restoreDraft };
}

export function newConversation(state: ChatState): ChatState {
  return { ...initialChatState(), nextId: state.nextId };
}
