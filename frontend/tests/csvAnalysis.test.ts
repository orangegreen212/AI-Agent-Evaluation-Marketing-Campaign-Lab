import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { test } from 'node:test';
import { analyzeCsvBytes, analyzeCsvText, CsvAnalyzer } from '@/lib/csvAnalysis';

const HEADER = 'date,campaign,channel,impressions,clicks,spend,conversions,revenue';
const analyze = (text: string) => analyzeCsvText(text, { filename: 't.csv' });
const codes = (r: Awaited<ReturnType<typeof analyze>>) => r.issues.map((i) => `${i.severity}:${i.code}:${i.column ?? ''}`);
const metric = (r: Awaited<ReturnType<typeof analyze>>, id: string) => r.analysis!.metrics.find((m) => m.metric_id === id)!;

test('the bundled demo CSV gives the same numbers as the pandas reference', async () => {
  const demo = readFileSync(join(process.cwd(), '..', 'datasets', 'demo', 'sample_campaigns.csv'), 'utf8');
  const r = await analyzeCsvText(demo, { filename: 'sample_campaigns.csv', origin: 'SYNTHETIC_DEMO', datasetId: 'demo-sample-campaigns' });
  assert.equal(r.dataset.validation.status, 'VALID');
  assert.equal(r.dataset.validation.rows_read, 6);
  assert.deepEqual(r.dataset.period, { start: '2026-09-01', end: '2026-09-03' });
  assert.equal(metric(r, 'roas').value, 3.25);
  assert.ok(Math.abs(metric(r, 'cpa').value! - 15.384615384615385) < 1e-12);
  assert.ok(Math.abs(metric(r, 'ctr').value! - 1.8320610687022902) < 1e-12);
  assert.equal(metric(r, 'impressions').value, 131000);
  assert.equal(metric(r, 'spend').value, 1400);
  assert.match(r.dataset.validation.dataset_sha256, /^[0-9a-f]{64}$/);
});

test('result does not depend on how the text is split into chunks (quotes, CRLF, BOM-free)', () => {
  const text =
    HEADER + '\r\n' +
    '2026-09-01,"brand, search",search,1000,50,25.5,5,100\r\n' +
    '2026-09-02,"say ""hi""",social,2000,60,30,6,120\r\n' +
    '\r\n' +
    '2026-09-03,plain,search,3000,70,35,7,140';
  const run = (chunks: string[]) => {
    const a = new CsvAnalyzer();
    chunks.forEach((c) => a.feed(c));
    a.end();
    return JSON.stringify(a.result('a'.repeat(64), 't.csv', 'USER_DATA', null));
  };
  const whole = run([text]);
  const byChar = run(text.split(''));
  assert.equal(whole, byChar);
  const parsed = JSON.parse(whole);
  assert.equal(parsed.dataset.validation.rows_read, 3);
  // "say ""hi""" contains quotes and spaces: not a valid identifier, so it is reported (and the comma name too)
  assert.deepEqual(parsed.issues.map((i: { code: string }) => i.code), ['INVALID_IDENTIFIER']);
  assert.equal(parsed.issues[0].count, 2);
});

test('a UTF-8 BOM and CRLF line endings are accepted', async () => {
  const bytes = new TextEncoder().encode('\uFEFF' + HEADER + '\r\n2026-09-01,a,b,10,5,1,1,2\r\n');
  const r = await analyzeCsvBytes(bytes.buffer as ArrayBuffer, { filename: 'bom.csv' });
  assert.equal(r.dataset.validation.status, 'VALID');
  assert.equal(r.dataset.validation.rows_accepted, 1);
});

test('fatal value problems are reported with sample rows and block the analysis', async () => {
  const r = await analyze([HEADER, '2026-02-30,a,b,10,5,1,1,2', '2026-09-01,a,b,-1,5,1,1,2', '2026-09-01,a,b,10.5,5,1,1,2', '2026-09-01,a,b,10,50,1,1,2', '2026-09-01,a,b,x,5,1,1,2', '2026-09-01,,b,10,5,1,1,2'].join('\n'));
  assert.equal(r.dataset.validation.status, 'INVALID');
  assert.equal(r.analysis, null);
  assert.deepEqual(codes(r), [
    'FATAL:CLICKS_EXCEED_IMPRESSIONS:',
    'FATAL:FRACTIONAL_COUNT:impressions',
    'FATAL:INVALID_DATE:date',
    'FATAL:INVALID_NUMBER:impressions',
    'FATAL:MISSING_VALUE:campaign',
    'FATAL:NEGATIVE_VALUE:impressions',
  ]);
  assert.deepEqual(r.issues.find((i) => i.code === 'INVALID_DATE')!.sample_rows, [1]);
});

test('warnings do not block: duplicates, conversions above clicks, an unexpected column', async () => {
  const r = await analyze([HEADER + ',notes', '2026-09-01,a,b,100,10,5,20,9,x', '2026-09-01,a,b,100,10,5,20,9,x'].join('\n'));
  assert.equal(r.dataset.validation.status, 'VALID_WITH_WARNINGS');
  assert.equal(r.dataset.validation.duplicate_row_count, 1);
  assert.deepEqual(codes(r), ['WARNING:CONVERSIONS_EXCEED_CLICKS:', 'WARNING:DUPLICATE_ROWS:', "WARNING:UNEXPECTED_COLUMN:'notes'"]);
  assert.equal(metric(r, 'spend').value, 10); // duplicates stay in the totals
  assert.ok(metric(r, 'roas').limitations.includes('1 duplicate row(s) are included in the totals'));
});

test('a zero denominator is UNDEFINED, never 0 or Infinity', async () => {
  const r = await analyze([HEADER, '2026-09-01,a,b,0,0,0,0,0'].join('\n'));
  for (const id of ['roas', 'cpa', 'ctr']) {
    assert.equal(metric(r, id).value, null);
    assert.equal(metric(r, id).status, 'UNDEFINED');
    assert.match(metric(r, id).value_undefined_reason!, /undefined/);
  }
});

test('file-level problems: empty, header only, missing column, extra fields, bad encoding', async () => {
  assert.deepEqual(codes(await analyze('')), ['FATAL:EMPTY_FILE:']);
  assert.deepEqual(codes(await analyze('\n\n')), ['FATAL:EMPTY_FILE:']);
  assert.deepEqual(codes(await analyze(HEADER + '\n')), ['FATAL:NO_DATA_ROWS:']);
  const missing = await analyze('date,campaign\n2026-09-01,a\n');
  assert.ok(codes(missing).includes('FATAL:MISSING_COLUMN:spend'));
  assert.equal(missing.dataset.validation.rows_read, 0);
  assert.deepEqual(codes(await analyze(HEADER + '\n2026-09-01,a,b,1,1,1,1,1,EXTRA\n')), ['FATAL:PARSE_ERROR:']);
  assert.deepEqual(codes(await analyze(HEADER + '\n2026-09-01,"unclosed,b,1,1,1,1,1\n')), ['FATAL:PARSE_ERROR:']);
  const bad = await analyzeCsvBytes(new Uint8Array([0xff, 0xfe, 0x41]).buffer, { filename: 'x.csv' });
  assert.deepEqual(codes(bad), ['FATAL:ENCODING_ERROR:']);
});

test('short rows count as missing values (like pandas), not as a crash', async () => {
  const r = await analyze(HEADER + '\n2026-09-01,a,b,10,5\n');
  assert.ok(codes(r).includes('FATAL:MISSING_VALUE:spend'));
});
