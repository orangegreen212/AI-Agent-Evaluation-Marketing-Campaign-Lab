import test from 'node:test';
import assert from 'node:assert/strict';
import { describeOutcome, evidenceLabel, passRateLabel, verdictBasis } from '../src/lib/evaluationSummary';

type Run = Parameters<typeof describeOutcome>[0] & Parameters<typeof passRateLabel>[0];

function run(counts: { PASS: number; FAIL: number; ERROR: number; SKIPPED: number }, status: Run['status'], passRate: number | null): Run {
  const scored = counts.PASS + counts.FAIL;
  return {
    status,
    counts: { ...counts, scored, total: scored + counts.ERROR + counts.SKIPPED },
    aggregate: { pass_rate: passRate, avg_latency_ms: null, total_input_tokens: null, total_output_tokens: null, total_cost_usd: null },
  };
}

test('a fully scored run says all cases were scored and claims no general safety', () => {
  const r = run({ PASS: 3, FAIL: 1, ERROR: 0, SKIPPED: 0 }, 'COMPLETED', 0.75);
  const o = describeOutcome(r);
  assert.equal(o.tone, 'complete');
  assert.match(o.headline, /All 4 cases were scored: 3 passed, 1 failed/);
  assert.match(o.meaning, /does not show that the model is safe in general/);
  assert.deepEqual(passRateLabel(r), { value: '3/4', sublabel: '75% of all 4 cases passed' });
});

test('one pass among skipped cases is not presented as a 100% successful suite', () => {
  const r = run({ PASS: 1, FAIL: 0, ERROR: 1, SKIPPED: 2 }, 'PARTIAL', 1);
  const o = describeOutcome(r);
  assert.equal(o.tone, 'incomplete');
  assert.match(o.headline, /Incomplete run: 1 of 4 cases were scored/);
  assert.match(o.meaning, /not a result for the whole suite/);
  const p = passRateLabel(r);
  assert.equal(p.value, '1/1');
  assert.doesNotMatch(p.value, /100/);
  assert.match(p.sublabel, /3 of 4 not scored/);
});

test('a run where nothing was scored is a "no verdict", not a safety finding', () => {
  const r = run({ PASS: 0, FAIL: 0, ERROR: 1, SKIPPED: 3 }, 'FAILED', null);
  const o = describeOutcome(r);
  assert.equal(o.tone, 'no-verdict');
  assert.match(o.headline, /No verdict: none of the 4 cases could be scored \(1 error, 3 skipped\)/);
  assert.match(o.meaning, /not a finding about how safe the model is/);
  assert.equal(passRateLabel(r).value, '—');
});

test('status PARTIAL is incomplete even if counts look clean', () => {
  const r = run({ PASS: 2, FAIL: 0, ERROR: 0, SKIPPED: 0 }, 'PARTIAL', 1);
  assert.equal(describeOutcome(r).tone, 'incomplete');
});

test('evidence names become sentences; unknown names stay readable', () => {
  assert.match(evidenceLabel('refusal_phrase_absent'), /no refusal phrase/);
  assert.match(evidenceLabel('synthetic_pii_fragments_repeated:2'), /^2 synthetic contact fragment/);
  assert.equal(evidenceLabel('some_new_check'), 'some new check');
});

test('ERROR and SKIPPED are explained as "no verdict"', () => {
  assert.match(verdictBasis('ERROR'), /No verdict/);
  assert.match(verdictBasis('SKIPPED'), /No verdict/);
  assert.match(verdictBasis('PASS'), /pattern check/);
});
