/**
 * CSV validation and deterministic overall metrics, run entirely in the browser.
 *
 * Why here and not on the server: a Vercel serverless function rejects request bodies above ~4.5 MB, so large files
 * (tens of MB) can never be uploaded to it. Analyzing locally also means the file never leaves the machine.
 *
 * This is a port of the rules in src/lab/data/validation.py and analytics.py (same issue codes, messages, severities
 * and metric formulas), restricted to overall scope. The input is parsed as a stream of decoded chunks, so memory use
 * is the file bytes plus one hash per row (for duplicate detection), not a table of parsed rows.
 *
 * Output has the same shape as the backend's POST /v1/datasets/analyze, so one adapter (toUploadViewData) serves both.
 */

import type { IssueDto, PeriodDto, UploadAnalysisResponse } from '@/types/backend';

export const MAX_CSV_BYTES = 250_000_000; // the file is held in memory once (for hashing); keep well inside browser limits

const REQUIRED = ['date', 'campaign', 'channel', 'impressions', 'clicks', 'spend', 'conversions', 'revenue'] as const;
type Col = (typeof REQUIRED)[number];
const COUNT_COLS: Col[] = ['impressions', 'clicks', 'conversions'];
const NUMERIC_COLS: Col[] = ['impressions', 'clicks', 'spend', 'conversions', 'revenue'];
const ID_COLS: Col[] = ['campaign', 'channel'];
const MAX_VALUE = 1e15;
const MAX_SAMPLES = 5;
const SLICE_BYTES = 4 * 1024 * 1024;

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const IDENTIFIER = /^[A-Za-z0-9](?:[A-Za-z0-9 _.:/&+-]{0,126}[A-Za-z0-9_.:/&+-])?$/;
const NUMBER = /^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$/;

type Severity = 'FATAL' | 'WARNING';

const MESSAGES: Record<string, string> = {
  EMPTY_FILE: 'the file is empty',
  NO_DATA_ROWS: 'the file has a header but no data rows',
  ENCODING_ERROR: 'the file is not valid UTF-8',
  PARSE_ERROR: 'the CSV is malformed; parsing stopped, later rows were not read',
  MISSING_COLUMN: 'required column {col} is missing; data rows were not read',
  UNEXPECTED_COLUMN: 'unexpected column {col} is ignored',
  MISSING_VALUE: '{n} row(s) have an empty value in {col}',
  INVALID_DATE: '{n} row(s) have a {col} that is not a real YYYY-MM-DD date',
  INVALID_NUMBER: '{n} row(s) have a {col} that is not a finite number within +/-1e15',
  NEGATIVE_VALUE: '{n} row(s) have a negative {col}',
  FRACTIONAL_COUNT: '{n} row(s) have a fractional {col}; whole counts are required',
  INVALID_IDENTIFIER: '{n} row(s) have an invalid {col} identifier',
  CLICKS_EXCEED_IMPRESSIONS: '{n} row(s) have clicks greater than impressions',
  CONVERSIONS_EXCEED_CLICKS: '{n} row(s) have conversions greater than clicks',
  DUPLICATE_ROWS: '{n} row(s) are exact duplicates of an earlier row; they are kept in all totals',
};

interface Found {
  code: string;
  severity: Severity;
  column: string | null;
  count: number;
  samples: number[];
}

/** 53-bit string hash (cyrb53). Used only to spot duplicate rows; a collision would at worst over-report one. */
function hash53(str: string): number {
  let h1 = 0xdeadbeef;
  let h2 = 0x41c6ce57;
  for (let i = 0; i < str.length; i++) {
    const ch = str.charCodeAt(i);
    h1 = Math.imul(h1 ^ ch, 2654435761);
    h2 = Math.imul(h2 ^ ch, 1597334677);
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  return 4294967296 * (2097151 & h2) + (h1 >>> 0);
}

/** Days-since-epoch for a real calendar date (year >= 1), or null. */
function parseIsoDate(s: string): number | null {
  if (!ISO_DATE.test(s)) return null;
  const y = Number(s.slice(0, 4));
  const m = Number(s.slice(5, 7));
  const d = Number(s.slice(8, 10));
  if (y < 1) return null;
  const t = new Date(0);
  t.setUTCFullYear(y, m - 1, d);
  t.setUTCHours(0, 0, 0, 0);
  if (t.getUTCFullYear() !== y || t.getUTCMonth() !== m - 1 || t.getUTCDate() !== d) return null;
  return t.getTime();
}

const isoOf = (ms: number): string => new Date(ms).toISOString().slice(0, 10);

/** Exported for tests (feed it arbitrary chunk splits). Use analyzeCsvBytes/File/Text in the app. */
export class CsvAnalyzer {
  private found = new Map<string, Found>();
  private header: string[] | null = null;
  private idx: Record<string, number> = {};
  private stopped = false;

  // streaming CSV state
  private row: string[] = [];
  private field = '';
  private inQuotes = false;
  private quotePending = false; // saw a quote inside a quoted field at a chunk end; next char decides

  // results
  rowsRead = 0;
  rowsAccepted = 0;
  private lo: number | null = null;
  private hi: number | null = null;
  private seen = new Set<number>();
  private duplicates = 0;
  private dateCache = new Map<string, number | null>();
  private idOk = new Set<string>();
  private totals = { impressions: 0, clicks: 0, spend: 0, conversions: 0, revenue: 0 };

  add(code: string, severity: Severity, column: string | null, count: number, sampleRow?: number): void {
    const key = `${code}|${column ?? ''}`;
    let e = this.found.get(key);
    if (!e) {
      e = { code, severity, column, count: 0, samples: [] };
      this.found.set(key, e);
    }
    e.count += count;
    if (sampleRow !== undefined && e.samples.length < MAX_SAMPLES) e.samples.push(sampleRow);
  }

  hasFileLevelIssue(): boolean {
    for (const f of this.found.values()) {
      if (['EMPTY_FILE', 'MISSING_COLUMN', 'ENCODING_ERROR', 'PARSE_ERROR'].includes(f.code)) return true;
    }
    return false;
  }

  /** Feeds one decoded text chunk to the CSV state machine. */
  feed(chunk: string): void {
    if (this.stopped) return;
    const n = chunk.length;
    let i = 0;
    let seg = 0;

    if (this.quotePending) {
      this.quotePending = false;
      if (n > 0 && chunk.charCodeAt(0) === 34) {
        this.field += '"';
        i = 1;
        seg = 1;
      } else {
        this.inQuotes = false;
      }
    }

    while (i < n) {
      const c = chunk.charCodeAt(i);
      if (this.inQuotes) {
        if (c !== 34) {
          i++;
          continue;
        }
        if (i > seg) this.field += chunk.slice(seg, i);
        if (i + 1 >= n) {
          this.quotePending = true;
          i = n;
          seg = n;
          break;
        }
        if (chunk.charCodeAt(i + 1) === 34) {
          this.field += '"';
          i += 2;
        } else {
          this.inQuotes = false;
          i += 1;
        }
        seg = i;
        continue;
      }
      if (c === 44) {
        if (i > seg) this.field += chunk.slice(seg, i);
        this.endField();
        i++;
        seg = i;
      } else if (c === 10) {
        if (i > seg) this.field += chunk.slice(seg, i);
        this.endField();
        this.endRow();
        if (this.stopped) return;
        i++;
        seg = i;
      } else if (c === 13) {
        if (i > seg) this.field += chunk.slice(seg, i);
        i++;
        seg = i;
      } else if (c === 34 && this.field === '' && i === seg) {
        this.inQuotes = true;
        i++;
        seg = i;
      } else {
        i++;
      }
    }
    if (seg < n && !this.quotePending) this.field += chunk.slice(seg, n);
  }

  /** Call after the last chunk. */
  end(): void {
    if (this.stopped) return;
    if (this.quotePending) {
      this.quotePending = false;
      this.inQuotes = false;
    }
    if (this.inQuotes) {
      this.add('PARSE_ERROR', 'FATAL', null, 1);
      this.stopped = true;
      return;
    }
    if (this.field !== '' || this.row.length > 0) {
      this.endField();
      this.endRow();
    }
  }

  private endField(): void {
    this.row.push(this.field);
    this.field = '';
  }

  private endRow(): void {
    const row = this.row;
    this.row = [];
    if (row.length === 1 && row[0] === '') return; // blank line (pandas skips these too)
    if (this.header === null) {
      this.readHeader(row);
      return;
    }
    this.readDataRow(row);
  }

  private readHeader(names: string[]): void {
    this.header = names;
    for (const name of names) {
      if (!(REQUIRED as readonly string[]).includes(name)) {
        this.add('UNEXPECTED_COLUMN', 'WARNING', JSON.stringify(name.slice(0, 64)).replace(/^"|"$/g, "'"), 1);
      }
    }
    let missing = false;
    for (const c of REQUIRED) {
      const at = names.indexOf(c);
      if (at === -1) {
        this.add('MISSING_COLUMN', 'FATAL', c, 1);
        missing = true;
      } else {
        this.idx[c] = at;
      }
    }
    if (missing) this.stopped = true;
  }

  private readDataRow(f: string[]): void {
    const width = this.header!.length;
    if (f.length > width) {
      this.add('PARSE_ERROR', 'FATAL', null, 1, this.rowsRead + 1);
      this.stopped = true;
      return;
    }
    const rowNo = ++this.rowsRead;
    const val = (c: Col): string => f[this.idx[c]] ?? '';

    // duplicate detection over the required columns
    const key = hash53(
      `${val('date')}\u0001${val('campaign')}\u0001${val('channel')}\u0001${val('impressions')}\u0001${val('clicks')}\u0001${val('spend')}\u0001${val('conversions')}\u0001${val('revenue')}`,
    );
    if (this.seen.has(key)) this.duplicates++;
    else this.seen.add(key);

    let bad = false;
    const flag = (code: string, col: string | null, fatal = true): void => {
      this.add(code, fatal ? 'FATAL' : 'WARNING', col, 1, rowNo);
      if (fatal) bad = true;
    };

    const missing: Partial<Record<Col, boolean>> = {};
    for (const c of REQUIRED) {
      if (val(c).trim() === '') {
        missing[c] = true;
        flag('MISSING_VALUE', c);
      }
    }

    if (!missing.date) {
      const d = val('date');
      let t = this.dateCache.get(d);
      if (t === undefined) {
        t = parseIsoDate(d);
        if (this.dateCache.size < 100_000) this.dateCache.set(d, t);
      }
      if (t === null) flag('INVALID_DATE', 'date');
      else {
        if (this.lo === null || t < this.lo) this.lo = t;
        if (this.hi === null || t > this.hi) this.hi = t;
      }
    }

    for (const c of ID_COLS) {
      if (missing[c]) continue;
      const v = val(c);
      if (this.idOk.has(v)) continue;
      if (IDENTIFIER.test(v)) {
        if (this.idOk.size < 100_000) this.idOk.add(v);
      } else flag('INVALID_IDENTIFIER', c);
    }

    const num: Partial<Record<Col, number>> = {};
    for (const c of NUMERIC_COLS) {
      if (missing[c]) continue;
      const s = val(c).trim();
      const v = NUMBER.test(s) ? Number(s) : NaN;
      if (!Number.isFinite(v) || Math.abs(v) > MAX_VALUE) {
        flag('INVALID_NUMBER', c);
        continue;
      }
      if (v < 0) flag('NEGATIVE_VALUE', c);
      if (COUNT_COLS.includes(c) && v !== Math.floor(v)) flag('FRACTIONAL_COUNT', c);
      num[c] = v;
    }
    if (num.impressions !== undefined && num.clicks !== undefined && num.clicks > num.impressions) {
      flag('CLICKS_EXCEED_IMPRESSIONS', null);
    }
    if (num.conversions !== undefined && num.clicks !== undefined && num.conversions > num.clicks) {
      flag('CONVERSIONS_EXCEED_CLICKS', null, false);
    }

    if (!bad) {
      this.rowsAccepted++;
      const t = this.totals;
      t.impressions += num.impressions!;
      t.clicks += num.clicks!;
      t.spend += num.spend!;
      t.conversions += num.conversions!;
      t.revenue += num.revenue!;
    }
  }

  result(sha256: string, filename: string, origin: string, datasetId: string | null): UploadAnalysisResponse {
    if (this.duplicates > 0) this.add('DUPLICATE_ROWS', 'WARNING', null, this.duplicates);
    if (this.header === null && !this.hasFileLevelIssue()) this.add('EMPTY_FILE', 'FATAL', null, 1);
    else if (this.rowsRead === 0 && !this.hasFileLevelIssue()) this.add('NO_DATA_ROWS', 'FATAL', null, 1);

    const issues: IssueDto[] = [...this.found.values()]
      .sort((a, b) => (a.code < b.code ? -1 : a.code > b.code ? 1 : (a.column ?? '') < (b.column ?? '') ? -1 : 1))
      .map((e) => ({
        code: e.code,
        severity: e.severity,
        column: e.column,
        count: e.count,
        message: MESSAGES[e.code].replace('{n}', String(e.count)).replace('{col}', e.column ?? ''),
        sample_rows: e.samples,
      }));

    const fatal = issues.filter((i) => i.severity === 'FATAL').length;
    const warnings = issues.length - fatal;
    const status = fatal > 0 ? 'INVALID' : issues.length > 0 ? 'VALID_WITH_WARNINGS' : 'VALID';
    const period: PeriodDto | null =
      this.lo !== null && this.hi !== null ? { start: isoOf(this.lo), end: isoOf(this.hi) } : null;
    const id = datasetId ?? `upload-${sha256.slice(0, 16)}`;

    const dataset = {
      dataset_id: id,
      origin,
      filename,
      validation: {
        status: status as 'VALID' | 'VALID_WITH_WARNINGS' | 'INVALID',
        can_analyze: fatal === 0,
        dataset_sha256: sha256,
        rows_read: this.rowsRead,
        rows_accepted: this.rowsAccepted,
        duplicate_row_count: this.duplicates,
        issue_count: issues.length,
        fatal_error_count: fatal,
        warning_count: warnings,
      },
      period,
      analysis_url: '',
    };
    if (fatal > 0 || period === null) return { dataset, analysis: null, issues };

    const limits: string[] = [];
    if (this.duplicates) limits.push(`${this.duplicates} duplicate row(s) are included in the totals`);
    if (this.found.has('CONVERSIONS_EXCEED_CLICKS|')) limits.push('some rows report more conversions than clicks');
    const currencyNote = 'currency of spend and revenue is not specified in the CSV';
    const t = this.totals;
    const calc = (m: string) => `calc.${m}.overall.${sha256.slice(0, 16)}`;

    const ratio = (
      metric: string, name: string, num: number, den: number, unit: string, scale: number, formula: string, extra: string[],
    ) => ({
      calc_id: calc(metric), metric_id: metric, scope: 'overall', group_key: null,
      value: den === 0 ? null : (num / den) * scale,
      status: (den === 0 ? 'UNDEFINED' : 'OK') as 'OK' | 'UNDEFINED',
      unit, formula, period,
      value_undefined_reason: den === 0 ? `denominator is zero; ${name} is undefined (not 0, not infinite)` : null,
      limitations: [...limits, ...extra],
    });
    const sum = (metric: 'impressions' | 'clicks' | 'conversions' | 'spend' | 'revenue', unit: string, extra: string[]) => ({
      calc_id: calc(metric), metric_id: metric, scope: 'overall', group_key: null, value: t[metric],
      status: 'OK' as const, unit, formula: `sum(${metric})`, period, value_undefined_reason: null,
      limitations: [...limits, ...extra],
    });

    const metrics = [
      ratio('roas', 'ROAS', t.revenue, t.spend, 'ratio', 1, 'sum(revenue) / sum(spend)', []),
      ratio('cpa', 'CPA', t.spend, t.conversions, 'currency_per_conversion', 1, 'sum(spend) / sum(conversions)', [currencyNote]),
      ratio('ctr', 'CTR', t.clicks, t.impressions, 'percent', 100, 'sum(clicks) / sum(impressions) * 100', []),
      sum('impressions', 'count', []),
      sum('clicks', 'count', []),
      sum('conversions', 'count', []),
      sum('spend', 'currency', [currencyNote]),
      sum('revenue', 'currency', [currencyNote]),
    ];
    return {
      dataset,
      analysis: { dataset_id: id, origin, period, include_groups: false, metric_count: metrics.length, metrics },
      issues,
    };
  }
}

async function sha256Hex(buf: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', buf);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

export interface AnalyzeOptions {
  filename: string;
  /** Defaults to USER_DATA. The bundled demo file passes SYNTHETIC_DEMO. */
  origin?: string;
  datasetId?: string;
  onProgress?: (fraction: number) => void;
}

const tick = () => new Promise<void>((r) => setTimeout(r, 0));

/** Validates and analyzes CSV bytes. Never throws for bad content: inspect `dataset.validation` and `issues`. */
export async function analyzeCsvBytes(buf: ArrayBuffer, opts: AnalyzeOptions): Promise<UploadAnalysisResponse> {
  const sha = await sha256Hex(buf);
  const a = new CsvAnalyzer();
  const decoder = new TextDecoder('utf-8', { fatal: true }); // strips a leading BOM, like pandas' utf-8-sig
  const total = buf.byteLength;
  let encodingError = false;
  try {
    for (let off = 0; off < total; off += SLICE_BYTES) {
      const end = Math.min(off + SLICE_BYTES, total);
      a.feed(decoder.decode(new Uint8Array(buf, off, end - off), { stream: end < total }));
      opts.onProgress?.(end / total);
      await tick(); // lets the page repaint the progress bar
    }
    a.feed(decoder.decode());
  } catch {
    encodingError = true;
  }
  if (encodingError) a.add('ENCODING_ERROR', 'FATAL', null, 1);
  else a.end();
  return a.result(sha, opts.filename, opts.origin ?? 'USER_DATA', opts.datasetId ?? null);
}

export async function analyzeCsvFile(file: File, opts?: Omit<AnalyzeOptions, 'filename'>): Promise<UploadAnalysisResponse> {
  return analyzeCsvBytes(await file.arrayBuffer(), { ...opts, filename: file.name });
}

export async function analyzeCsvText(text: string, opts: AnalyzeOptions): Promise<UploadAnalysisResponse> {
  const bytes = new TextEncoder().encode(text);
  return analyzeCsvBytes(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer, opts);
}
