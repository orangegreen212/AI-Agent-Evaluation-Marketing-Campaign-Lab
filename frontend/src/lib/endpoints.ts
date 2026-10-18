/** Which model endpoints can actually be run, and which one to preselect. Pure, so it is tested. */
import type { EndpointDto } from '@/types/backend';

/** A hosted endpoint whose API key is missing on the server cannot work. Local endpoints and keyed ones can be tried. */
export function isRunnable(e: Pick<EndpointDto, 'api_key_configured'>): boolean {
  return e.api_key_configured !== false;
}

/**
 * The endpoint to preselect: the first one that can run, preferring a local one (it sends nothing off the machine).
 * Alphabetical order must not decide this: a placeholder such as `cloud_default` sorts first and never works.
 */
export function defaultEndpointName(endpoints: readonly EndpointDto[]): string {
  const runnable = endpoints.filter(isRunnable);
  return (runnable.find((e) => e.provider === 'LOCAL') ?? runnable[0])?.name ?? '';
}

/** Dropdown text that says what the endpoint is and whether it is usable. */
export function endpointOptionLabel(e: Pick<EndpointDto, 'name' | 'provider' | 'model_id' | 'api_key_configured'>): string {
  const where = e.provider === 'LOCAL' ? 'local' : 'hosted';
  return isRunnable(e) ? `${e.name} — ${where} (${e.model_id})` : `${e.name} — ${where}, not configured (no API key on the server)`;
}
