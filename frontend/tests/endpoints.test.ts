import test from 'node:test';
import assert from 'node:assert/strict';
import { defaultEndpointName, endpointOptionLabel, isRunnable } from '../src/lib/endpoints';
import type { EndpointDto } from '../src/types/backend';

const ep = (name: string, provider: 'LOCAL' | 'CLOUD', key: boolean | null): EndpointDto => ({
  name, provider, data_locality: provider === 'LOCAL' ? 'LOCAL_MACHINE' : 'EXTERNAL_PROVIDER', accepts_user_data: provider === 'LOCAL',
  model_id: `${name}-model`, model_version: 'unspecified', base_url_origin: 'https://x.invalid', temperature: 0, max_output_tokens: 1,
  timeout_s: 1, structured_output_mode: 'NONE', api_key_configured: key,
});

test('an alphabetically first hosted endpoint without a key is never the default', () => {
  const list = [ep('cloud_default', 'CLOUD', false), ep('hf_inference', 'CLOUD', false), ep('openrouter', 'CLOUD', true)];
  assert.equal(defaultEndpointName(list), 'openrouter');
});

test('a local endpoint is preferred over a configured hosted one', () => {
  const list = [ep('cloud_default', 'CLOUD', true), ep('local_lmstudio', 'LOCAL', null)];
  assert.equal(defaultEndpointName(list), 'local_lmstudio');
});

test('nothing runnable gives an empty default instead of a broken choice', () => {
  assert.equal(defaultEndpointName([ep('cloud_default', 'CLOUD', false)]), '');
  assert.equal(defaultEndpointName([]), '');
});

test('unconfigured endpoints are labelled as such', () => {
  assert.equal(isRunnable(ep('a', 'CLOUD', false)), false);
  assert.match(endpointOptionLabel(ep('cloud_default', 'CLOUD', false)), /not configured/);
  assert.match(endpointOptionLabel(ep('local_lmstudio', 'LOCAL', null)), /local \(local_lmstudio-model\)/);
});
