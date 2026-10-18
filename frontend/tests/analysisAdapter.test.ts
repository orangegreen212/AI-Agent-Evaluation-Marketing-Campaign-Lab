import assert from 'node:assert/strict';
import { test } from 'node:test';
import { toAnalyzeViewData, toUploadViewData } from '@/lib/analysisAdapter';
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

test('a rejected upload maps to a view model with no metrics and its issue list', () => {
  const view = toUploadViewData({
    dataset: { dataset_id: 'upload-abc', origin: 'USER_DATA', filename: 'x.csv', period: null, analysis_url: '',
      validation: { status: 'INVALID', can_analyze: false, dataset_sha256: 'b'.repeat(64), rows_read: 0, rows_accepted: 0,
        duplicate_row_count: 0, issue_count: 1, fatal_error_count: 1, warning_count: 0 } },
    analysis: null,
    issues: [{ code: 'MISSING_COLUMN', severity: 'FATAL', column: 'spend', count: 1, message: 'required column spend is missing', sample_rows: [] }],
  });
  assert.equal(view.period, null);
  assert.deepEqual(view.metrics, []);
  assert.equal(view.issues[0].code, 'MISSING_COLUMN');
  assert.equal(view.validation.canAnalyze, false);
});

test('an accepted upload keeps only overall metrics, sorted for display', () => {
  const m = (id: string, scope: string, value: number) => ({
    calc_id: `c.${id}.${scope}`, metric_id: id, scope, group_key: scope === 'overall' ? null : 'g', value, status: 'OK' as const,
    unit: 'count', formula: `sum(${id})`, period, value_undefined_reason: null, limitations: [],
  });
  const view = toUploadViewData({
    dataset: { ...dataset, dataset_id: 'upload-abc', origin: 'USER_DATA', period },
    analysis: { dataset_id: 'upload-abc', origin: 'USER_DATA', period, include_groups: false, metric_count: 3,
      metrics: [m('clicks', 'overall', 5), m('roas', 'channel', 2), m('roas', 'overall', 2)] },
    issues: [],
  });
  assert.deepEqual(view.metrics.map((x) => x.id), ['roas', 'clicks']);
});
