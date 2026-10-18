import { useCallback, useEffect, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';
import { MessageSquarePlus, Send } from 'lucide-react';
import { apiClient } from '@/lib/apiClient';
import { chatErrorMessage } from '@/lib/chatErrors';
import {
  beginSend,
  checkDraft,
  failSend,
  historyFor,
  initialChatState,
  MAX_MESSAGE_CHARS,
  newConversation,
  receiveReply,
  type ChatMessage,
  type ChatState,
} from '@/lib/chatState';
import type { EndpointDto } from '@/types/backend';
import { Panel, Button, Select, Badge, EmptyState, ErrorState, LoadingState, PageGuide, Provenance } from '@/components/ui';
import { clsx } from '@/lib/utils';

export function ChatView() {
  const [endpoints, setEndpoints] = useState<EndpointDto[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [optionsError, setOptionsError] = useState('');
  const [endpoint, setEndpoint] = useState('');
  const [chat, setChat] = useState<ChatState>(initialChatState);
  const [draft, setDraft] = useState('');
  const [draftError, setDraftError] = useState('');
  const endRef = useRef<HTMLDivElement>(null);

  // Only endpoints that accept user messages are offered. The backend enforces this too.
  const chatEndpoints = endpoints.filter((e) => e.accepts_user_data);
  const selected = chatEndpoints.find((e) => e.name === endpoint) ?? null;

  const loadEndpoints = useCallback(async () => {
    setOptionsError('');
    setLoaded(false);
    try {
      const res = await apiClient.getEndpoints();
      setEndpoints(res.endpoints);
      const firstLocal = res.endpoints.find((e) => e.accepts_user_data);
      setEndpoint(firstLocal?.name ?? '');
    } catch (err) {
      setOptionsError(err instanceof Error ? err.message : 'Could not load model endpoints.');
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    void loadEndpoints();
  }, [loadEndpoints]);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'end' });
  }, [chat.messages.length, chat.pending]);

  const send = useCallback(async () => {
    const check = checkDraft(draft);
    if (!check.ok) {
      setDraftError(check.reason);
      return;
    }
    if (!selected || chat.pending) return;

    const history = historyFor(chat);
    setDraftError('');
    setDraft('');
    setChat(beginSend(chat, check.text));
    try {
      const reply = await apiClient.sendChat({ endpoint: selected.name, message: check.text, history });
      setChat((prev) => receiveReply(prev, reply));
    } catch (err) {
      setChat((prev) => failSend(prev, chatErrorMessage(err)).state);
      setDraft(check.text); // restore so the user can edit and retry
    }
  }, [draft, chat, selected]);

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      void send();
    }
  };

  const canSend = !!selected && !chat.pending && draft.trim().length > 0;

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-ink-50">Agent Chat</h1>
          <p className="mt-1 text-sm text-ink-400">
            Talk with a configured model. This is for trying a model out: nothing here is scored, checked or saved.
          </p>
        </div>
        <Button
          size="sm"
          variant="ghost"
          icon={<MessageSquarePlus className="h-3.5 w-3.5" />}
          disabled={chat.pending}
          onClick={() => {
            setChat((prev) => newConversation(prev));
            setDraft('');
            setDraftError('');
          }}
        >
          New conversation
        </Button>
      </div>

      <PageGuide
        purpose="Try a model in free conversation before, or alongside, running the evaluation."
        how="Each message you send is passed to the selected model through the backend, together with the earlier turns of this conversation. The reply is shown as the model wrote it."
        inputs="Your messages. A local model keeps them on the machine running the backend. A hosted model, available only if the operator enabled it, sends them to that provider; secret-looking text is blocked first."
        output="Plain model text, shown as untrusted output. There are no PASS / FAIL verdicts here."
        limits="A fluent or confident reply is not evidence of correctness or safety, and nothing here is checked. To get verdicts with evidence, use Evaluate & Safety."
      />
      <Provenance kinds={['live']}>Your messages go to the model you select. The history lives in this browser tab and is cleared on reload.</Provenance>

      <Panel
        title="Model"
        subtitle="Local endpoints keep your messages on the machine where the backend runs. A hosted endpoint (available only when the operator enabled it) sends your messages to that provider."
        actions={
          selected ? (
            <Badge variant="info">
              {selected.provider} · {selected.model_id}
            </Badge>
          ) : undefined
        }
      >
        {optionsError ? (
          <ErrorState title="Could not load model endpoints" message={optionsError} onRetry={loadEndpoints} />
        ) : !loaded ? (
          <LoadingState label="Loading model endpoints…" />
        ) : chatEndpoints.length === 0 ? (
          <EmptyState
            title="No chat model is available"
            description="Locally: start LM Studio and set LM_STUDIO_BASE_URL and LM_STUDIO_MODEL_ID. On Vercel: set LAB_ALLOW_CLOUD_CHAT=1, CLOUD_MODEL_API_KEY, CLOUD_MODEL_BASE_URL and CLOUD_MODEL_ID in the project's environment variables, then redeploy."
          />
        ) : (
          <Select label="Model endpoint" value={endpoint} onChange={setEndpoint}>
            {chatEndpoints.map((e) => (
              <option key={e.name} value={e.name}>
                {e.name} — {e.provider} ({e.model_id})
              </option>
            ))}
          </Select>
        )}
        {selected?.provider === 'CLOUD' && (
          <p className="mt-3 rounded-lg border border-warning-500/30 bg-warning-500/5 px-3 py-2 text-xs text-warning-400">
            Hosted model: your messages are sent to {selected.base_url_origin}. Do not enter secrets or personal data.
          </p>
        )}
      </Panel>

      <Panel title="Conversation" subtitle="History is kept in this browser tab only and is cleared on reload.">
        <div role="log" aria-live="polite" className="max-h-[50vh] min-h-[12rem] space-y-3 overflow-y-auto pr-1">
          {chat.messages.length === 0 && !chat.pending && (
            <p className="py-8 text-center text-sm text-ink-500">No messages yet. Send one below.</p>
          )}
          {chat.messages.map((m) => (
            <MessageBubble key={m.id} message={m} />
          ))}
          {chat.pending && (
            <div className="flex items-center gap-3 text-sm text-ink-400">
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-accent-400/40 border-t-accent-400" />
              Waiting for the model…
            </div>
          )}
          {chat.error && (
            <div role="alert" className="rounded-lg border border-danger-500/30 bg-danger-500/5 px-3 py-2 text-sm text-danger-300">
              {chat.error} Your message was kept in the input so you can retry.
            </div>
          )}
          <div ref={endRef} />
        </div>

        <div className="mt-4 border-t border-surface-700/60 pt-4">
          <label htmlFor="chat-input" className="sr-only">
            Message
          </label>
          <textarea
            id="chat-input"
            rows={3}
            value={draft}
            onChange={(e) => {
              setDraft(e.target.value);
              setDraftError('');
            }}
            onKeyDown={onKeyDown}
            disabled={!selected}
            readOnly={chat.pending}
            placeholder={selected ? 'Type a message. Enter sends, Shift+Enter adds a new line.' : 'No model endpoint selected.'}
            className="w-full resize-y rounded-lg border border-surface-700 bg-surface-900 px-3 py-2 text-sm text-ink-100 placeholder:text-ink-500 focus:border-accent-500/60 focus:outline-none disabled:opacity-50"
          />
          <div className="mt-2 flex items-center justify-between gap-3">
            <div className="text-2xs text-ink-500">
              {draftError ? <span className="text-warning-400">{draftError}</span> : null}
              <span className={clsx(draft.length > MAX_MESSAGE_CHARS && 'text-danger-400')}>
                {draft.length}/{MAX_MESSAGE_CHARS}
              </span>
            </div>
            <Button
              variant="primary"
              icon={<Send className="h-4 w-4" />}
              disabled={!canSend}
              loading={chat.pending}
              onClick={() => void send()}
            >
              Send
            </Button>
          </div>
        </div>
      </Panel>
    </div>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user';
  return (
    <div className={clsx('flex flex-col', isUser ? 'items-end' : 'items-start')}>
      <div className="mb-1 text-2xs uppercase tracking-wider text-ink-500">{isUser ? 'You' : 'Model (untrusted output)'}</div>
      <div
        className={clsx(
          'max-w-[85%] whitespace-pre-wrap break-words rounded-xl border px-3 py-2 text-sm',
          isUser ? 'border-accent-500/30 bg-accent-500/10 text-ink-100' : 'border-surface-700 bg-surface-800/60 text-ink-200',
        )}
      >
        {message.content}
      </div>
      {message.meta && (
        <div className="mt-1 text-2xs text-ink-500">
          {message.meta.provider} · {message.meta.modelId}
          {message.meta.servedModel ? ` (served as ${message.meta.servedModel})` : ''} · {Math.round(message.meta.latencyMs)} ms
        </div>
      )}
    </div>
  );
}
