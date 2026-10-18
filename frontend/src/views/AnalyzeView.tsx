import { useCallback, useState } from 'react';
import { FileSpreadsheet, FileUp, RefreshCw } from 'lucide-react';
import { apiClient } from '@/lib/apiClient';
import { toAnalyzeViewData, type AnalyzeViewData } from '@/lib/analysisAdapter';
import type { HealthResponse } from '@/types/backend';
import {
  Panel,
  MetricCard,
  Button,
  Badge,
  DemoBanner,
  EmptyState,
  ErrorState,
  LoadingState,
} from '@/components/ui';
import { formatNumber } from '@/lib/utils';

type Phase = 'idle' | 'loading' | 'success' | 'error';

const REQUIRED_COLUMNS = 'date, campaign, channel, impressions, clicks, spend, conversions, revenue';

export function AnalyzeView() {
  const [phase, setPhase] = useState<Phase>('idle');
  const [data, setData] = useState<AnalyzeViewData | null>(null);
  const [backend, setBackend] = useState<HealthResponse | null>(null);
  const [error, setError] = useState('');

  // Health, dataset summary and overall analysis are loaded together. Any failure is shown, never swallowed.
  const load = useCallback(async () => {
    setPhase('loading');
    setError('');
    try {
      const [health, dataset, analysis] = await Promise.all([
        apiClient.health(),
        apiClient.getDemoDataset(),
        apiClient.getDemoAnalysis(),
      ]);
      setBackend(health);
      setData(toAnalyzeViewData(dataset, analysis));
      setPhase('success');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load the demo dataset analysis.');
      setPhase('error');
    }
  }, []);

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-ink-50">Analyze</h1>
          <p className="mt-1 text-sm text-ink-400">
            Validation and overall metrics for the bundled demo dataset, computed by the local backend.
          </p>
        </div>
        {phase === 'success' && (
          <Button
            size="sm"
            variant="ghost"
            icon={<RefreshCw className="h-3.5 w-3.5" />}
            onClick={load}
          >
            Reload
          </Button>
        )}
      </div>

      <DemoBanner message="Source: local backend, synthetic demo dataset (SYNTHETIC_DEMO). Nothing is uploaded. CSV upload is not implemented yet." />

      {/* Upload: visibly unavailable. No request is made from this control. */}
      <Panel title="Upload a CSV" subtitle="Not implemented yet" actions={<Badge variant="neutral">Unavailable</Badge>}>
        <p className="text-sm text-ink-300">
          The backend has no upload route, so a file cannot be analyzed or sent anywhere from this page.
        </p>
        <p className="mt-2 text-xs text-ink-500">
          When upload exists, the required columns will be: {REQUIRED_COLUMNS}.
        </p>
        <div className="mt-4">
          <Button variant="secondary" icon={<FileUp className="h-4 w-4" />} disabled>
            Upload (not implemented)
          </Button>
        </div>
      </Panel>

      {phase === 'idle' && (
        <EmptyState
          icon={<FileSpreadsheet className="h-8 w-8" />}
          title="Demo dataset not loaded"
          description="Load the bundled synthetic dataset from the local backend to see its validation status and overall metrics."
          action={
            <Button variant="primary" onClick={load}>
              Load demo dataset
            </Button>
          }
        />
      )}

      {phase === 'loading' && <LoadingState label="Loading the demo dataset analysis from the backend…" />}

      {phase === 'error' && (
        <ErrorState title="Could not load the demo analysis" message={error} onRetry={load} />
      )}

      {phase === 'success' && data && <AnalyzeResults data={data} backend={backend} />}
    </div>
  );
}

function AnalyzeResults({ data, backend }: { data: AnalyzeViewData; backend: HealthResponse | null }) {
  const v = data.validation;
  const statusBadge =
    v.status === 'VALID' ? (
      <Badge variant="success" dot>Valid</Badge>
    ) : v.status === 'VALID_WITH_WARNINGS' ? (
      <Badge variant="warning" dot>Valid with warnings</Badge>
    ) : (
      <Badge variant="danger" dot>Invalid</Badge>
    );

  return (
    <div className="space-y-5">
      <Panel
        title="Dataset validation"
        subtitle={`${data.filename} · ${data.period.start} → ${data.period.end} · ${data.origin}`}
        actions={statusBadge}
      >
        <div className="mb-4 flex flex-wrap gap-3">
          <Count label="Rows read" value={v.rowsRead} />
          <Count label="Rows accepted" value={v.rowsAccepted} />
          <Count label="Duplicate rows" value={v.duplicateRows} />
          <Count label="Warnings" value={v.warningCount} />
          <Count label="Fatal errors" value={v.fatalErrorCount} />
        </div>
        <dl className="space-y-2 text-sm">
          <div>
            <dt className="text-2xs font-medium uppercase tracking-wider text-ink-400">Analysis allowed</dt>
            <dd className="mt-0.5 text-ink-100">{v.canAnalyze ? 'Yes' : 'No'}</dd>
          </div>
          <div>
            <dt className="text-2xs font-medium uppercase tracking-wider text-ink-400">Dataset SHA-256</dt>
            <dd className="mt-0.5 break-all font-mono text-xs text-ink-100">{v.sha256}</dd>
          </div>
        </dl>
        <p className="mt-4 text-2xs text-ink-500">
          The backend returns issue counts only, not the individual issues, so none are listed here.
        </p>
      </Panel>

      <Panel title="Overall metrics" subtitle="Scope: overall (all rows in the dataset)">
        {data.metrics.length === 0 ? (
          <p className="text-sm text-ink-400">The backend returned no overall metrics.</p>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {data.metrics.map((m) => (
              <MetricCard
                key={m.id}
                label={m.label}
                value={m.display}
                sublabel={m.undefinedReason ?? m.formula}
                accent={m.id === 'roas'}
              />
            ))}
          </div>
        )}
      </Panel>

      {data.limitations.length > 0 && (
        <Panel title="Limitations reported by the backend">
          <ul className="list-disc space-y-1 pl-5 text-sm text-ink-300">
            {data.limitations.map((lim) => (
              <li key={lim}>{lim}</li>
            ))}
          </ul>
        </Panel>
      )}

      <p className="text-2xs text-ink-500">
        Source: GET /v1/datasets/demo and GET /v1/datasets/demo/analysis
        {backend ? ` · backend ${backend.package_version} (API ${backend.api_version})` : ''}.
      </p>
    </div>
  );
}

function Count({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-surface-700/60 bg-surface-800/40 px-3 py-2">
      <div>
        <div className="font-mono text-sm font-semibold text-ink-100">{formatNumber(value)}</div>
        <div className="text-2xs text-ink-400">{label}</div>
      </div>
    </div>
  );
}
