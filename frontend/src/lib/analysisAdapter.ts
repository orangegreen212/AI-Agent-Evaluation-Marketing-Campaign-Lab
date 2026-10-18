/**
 * Explicit adapter: backend Stage 1 responses -> view model for the Analyze page.
 *
 * Rules:
 *  - Only fields the backend returns are mapped. Nothing is invented or defaulted.
 *  - Currency is not formatted with a symbol: the backend states the CSV does not specify one
 *    (limitation "currency of spend and revenue is not specified in the CSV").
 *  - `ctr` is returned already multiplied by 100 (unit "percent"), so it is shown as-is.
 *  - Metrics the backend marks as not OK have value null; they are shown as "—" with the reason.
 */

import type { DemoAnalysisResponse, DemoDatasetResponse, DemoMetricDto, PeriodDto } from '@/types/backend';
import { formatNumber } from '@/lib/utils';

export interface ViewMetric {
  id: string;
  label: string;
  display: string; // formatted value, or "—"
  formula: string;
  undefinedReason: string | null;
}

export interface AnalyzeViewData {
  datasetId: string;
  origin: string;
  filename: string;
  period: PeriodDto;
  validation: {
    status: DemoDatasetResponse['validation']['status'];
    canAnalyze: boolean;
    sha256: string;
    rowsRead: number;
    rowsAccepted: number;
    duplicateRows: number;
    issueCount: number;
    fatalErrorCount: number;
    warningCount: number;
  };
  metrics: ViewMetric[];
  limitations: string[]; // unique, in backend order
}

const LABELS: Record<string, string> = {
  roas: 'ROAS',
  cpa: 'CPA',
  ctr: 'CTR',
  spend: 'Spend',
  revenue: 'Revenue',
  conversions: 'Conversions',
  impressions: 'Impressions',
  clicks: 'Clicks',
};

// Display order for the cards that the backend actually returns; unknown ids go last.
const ORDER = ['roas', 'cpa', 'ctr', 'spend', 'revenue', 'conversions', 'impressions', 'clicks'];

function formatValue(metric: DemoMetricDto): string {
  const v = metric.value;
  if (v === null || v === undefined || metric.status !== 'OK') return '—';
  switch (metric.unit) {
    case 'ratio':
      return `${v.toFixed(2)}x`;
    case 'percent':
      return `${v.toFixed(2)}%`;
    case 'count':
      return formatNumber(v, 0);
    case 'currency':
    case 'currency_per_conversion':
      return formatNumber(v, 2); // no currency symbol: currency is unspecified in the source data
    default:
      return formatNumber(v, 2);
  }
}

function toViewMetric(metric: DemoMetricDto): ViewMetric {
  return {
    id: metric.metric_id,
    label: LABELS[metric.metric_id] ?? metric.metric_id,
    display: formatValue(metric),
    formula: metric.formula,
    undefinedReason: metric.value === null ? metric.value_undefined_reason ?? 'not available' : null,
  };
}

export function toAnalyzeViewData(
  dataset: DemoDatasetResponse,
  analysis: DemoAnalysisResponse,
): AnalyzeViewData {
  if (dataset.dataset_id !== analysis.dataset_id) {
    throw new Error(
      `Backend returned mismatched responses (dataset ${dataset.dataset_id} vs analysis ${analysis.dataset_id}).`,
    );
  }

  // The Analyze page shows overall scope only; group metrics are not requested.
  const overall = analysis.metrics.filter((m) => m.scope === 'overall');
  const rank = (id: string) => {
    const i = ORDER.indexOf(id);
    return i === -1 ? ORDER.length : i;
  };
  const metrics = [...overall].sort((a, b) => rank(a.metric_id) - rank(b.metric_id)).map(toViewMetric);

  const limitations: string[] = [];
  for (const m of overall) {
    for (const lim of m.limitations) {
      if (!limitations.includes(lim)) limitations.push(lim);
    }
  }

  const v = dataset.validation;
  return {
    datasetId: dataset.dataset_id,
    origin: dataset.origin,
    filename: dataset.filename,
    period: dataset.period,
    validation: {
      status: v.status,
      canAnalyze: v.can_analyze,
      sha256: v.dataset_sha256,
      rowsRead: v.rows_read,
      rowsAccepted: v.rows_accepted,
      duplicateRows: v.duplicate_row_count,
      issueCount: v.issue_count,
      fatalErrorCount: v.fatal_error_count,
      warningCount: v.warning_count,
    },
    metrics,
    limitations,
  };
}
