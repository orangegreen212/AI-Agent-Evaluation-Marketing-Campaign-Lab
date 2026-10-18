import assert from 'node:assert/strict';
import { test } from 'node:test';
import { toAnalyzeViewData } from '@/lib/analysisAdapter';
import type { DemoAnalysisResponse, DemoDatasetResponse } from '@/types/backend';

// Shapes follow src/lab/api/app.py handlers (hand-written: no live server in the test).
const period = { start: '2026-09-01', end: '2026-09-03' };
const dataset: DemoDatasetResponse = {
  dataset_id: 'demo-sample-campaigns', origin: 'SYNTHETIC_DEMO', filename: 'sample_campaigns.csv',
  validation: { status: 'VALID_WITH_WARNINGS', can_analyze: true, dataset_sha256: 'a'.repeat(64),
    rows_read: 9, rows_accepted: 9, duplicate_row_count: 0, issue_count: 2, fatal_error_count: 0, warning_count: 2 },
  period, analysis_url: '/v1/datasets/demo/analysis',
};
const lim = 'currency of spend and revenue is not specified in the CSV';
const m = (id: string, unit: string, value: number | null, extra: Record<string, unknown> = {}) => ({
  calc_id: `${id}-x`, metric_id: id, scope: 'overall', group_key: null, value,
  status: value === null ? 'UNDEFINED' : 'OK', unit, formula: `f(${id})`, period,
  value_undefined_reason: value === null ? 'denominator is zero' : null,
  limitations: ['spend', 'revenue', 'cpa'].includes(id) ? [lim] : [], ...extra,
}) as DemoAnalysisResponse['metrics'][number];
const analysis: DemoAnalysisResponse = {
  dataset_id: 'demo-sample-campaigns', origin: 'SYNTHETIC_DEMO', period, include_groups: false, metric_count: 9,
  metrics: [
    m('spend', 'currency', 1400), m('roas', 'ratio', 3.25), m('cpa', 'currency_per_conversion', 1400 / 91),
    m('ctr', 'percent', 2.5), m('revenue', 'currency', 4550), m('conversions', 'count', 91),
    m('impressions', 'count', 1234567), m('clicks', 'count', 4321),
    { ...m('spend', 'currency', 100), scope: 'channel', group_key: 'search' },
  ],
};

test('maps overall metrics with unit-aware display and no invented values', () => {
  const v = toAnalyzeViewData(dataset, analysis);
  assert.equal(v.metrics.length, 8);
  const by = Object.fromEntries(v.metrics.map((x) => [x.id, x]));
  assert.equal(by.roas.display, '3.25x');
  assert.equal(by.ctr.display, '2.50%');
  assert.equal(by.spend.display, '1,400.00');
  assert.equal(by.impressions.display, '1,234,567');
  assert.equal(v.limitations.length, 1);
});

test('undefined metrics show a dash and the backend reason', () => {
  const v = toAnalyzeViewData(dataset, { ...analysis, metrics: [m('roas', 'ratio', null)] });
  assert.equal(v.metrics[0].display, '—');
  assert.equal(v.metrics[0].undefinedReason, 'denominator is zero');
});

test('mismatched dataset and analysis are rejected', () => {
  assert.throws(() => toAnalyzeViewData(dataset, { ...analysis, dataset_id: 'other' }), /mismatched/);
});
