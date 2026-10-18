/** Plain-language messages for chat failures. Pure, so it can be tested without React. */
import { ApiError } from '@/lib/apiClient';

export function chatErrorMessage(err: unknown): string {
  if (!(err instanceof ApiError)) return 'The request failed unexpectedly. Check the backend and try again.';
  switch (err.code) {
    case 'TRANSFER_BLOCKED':
      return 'Blocked by policy: messages can only be sent to a local model endpoint.';
    case 'RATE_LIMITED':
      return 'The provider is rate-limiting requests. Wait a moment, then try again.';
    case 'MODEL_TIMEOUT':
      return 'The model did not respond in time. Try again, or use a shorter message.';
    case 'MODEL_UNAVAILABLE':
      return 'The model is unavailable or still starting. Try again shortly.';
    case 'MODEL_UNREACHABLE':
      return 'The backend cannot reach the model server. Check that LM Studio is running on the machine where the backend runs, with its local server started.';
    case 'MODEL_NOT_CONFIGURED':
      return 'This model endpoint is not configured on the server.';
    case 'INVALID_PROVIDER_RESPONSE':
      return 'The model returned an unusable response (empty or malformed). No reply is shown.';
    case 'VALIDATION_ERROR':
      return 'The server rejected the message (too long or malformed).';
    default:
      return err.message;
  }
}
