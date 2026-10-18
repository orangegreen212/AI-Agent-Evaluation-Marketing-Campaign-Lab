/** Plain-language messages for chat failures. Pure, so it can be tested without React. */
import { ApiError } from '@/lib/apiClient';

export function chatErrorMessage(err: unknown): string {
  if (!(err instanceof ApiError)) return 'The request failed unexpectedly. Check the backend and try again.';
  switch (err.code) {
    case 'TRANSFER_BLOCKED':
      return 'Blocked by policy: this server does not allow sending messages to that model endpoint. For a hosted deployment the operator must enable cloud chat (LAB_ALLOW_CLOUD_CHAT=1).';
    case 'RATE_LIMITED':
      return 'The provider is rate-limiting requests. Wait a moment, then try again.';
    case 'MODEL_TIMEOUT':
      return 'The model did not respond in time. Try again, or use a shorter message.';
    case 'MODEL_UNAVAILABLE':
      return 'The model is unavailable or still starting. Try again shortly.';
    case 'MODEL_UNREACHABLE':
      return 'The backend cannot reach the model server. Locally: check that LM Studio is running with its server started. Hosted: check the model base URL.';
    case 'MODEL_NOT_CONFIGURED':
      return 'This model endpoint is not configured on the server (for a hosted model: API key and model id are missing).';
    case 'INVALID_PROVIDER_RESPONSE':
      return `The model returned an unusable response: ${err.message.replace(/\.$/, '')}. No reply is shown.`;
    case 'PROVIDER_AUTH_FAILED':
      return 'The model provider rejected the server\'s API key. Check the key and model id in the server environment.';
    case 'VALIDATION_ERROR':
      return 'The server rejected the message (too long or malformed).';
    default:
      return err.message;
  }
}
