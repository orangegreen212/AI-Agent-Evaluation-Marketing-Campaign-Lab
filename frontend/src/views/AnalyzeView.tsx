import { useCallback, useRef, useState } from 'react';
import type { ChangeEvent } from 'react';
import { FileSpreadsheet, FileUp, RefreshCw } from 'lucide-react';
import { apiClient } from '@/lib/apiClient';
import { toAnalyzeViewData, toUploadViewData, type AnalyzeViewData } from '@/lib/analysisAdapter';
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

const MAX_UPLOAD_BYTES = 4_000_000; // the server and Vercel both reject larger request bodies
const REQUIRED_COLUMNS = 'date, campaign, channel, impressions, clicks, spend, conversions, revenue';

export function AnalyzeView() {
  const [phase, setPhase] = useState<Phase>('idle');
  const [data, setData] = useState<AnalyzeViewData | null>(null);
  const [backend, setBackend] = useState<HealthResponse | null>(null);
  const [error, setError] = useState('');
  const [source, setSource] = useState<'demo' | 'upload'>('demo');
  const [uploadError, setUploadError] = useState('');
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const onFile = useCallback(async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ''; // lets the same file be chosen again after a fix
    if (!file) return;
    setUploadError('');
    if (!/\.csv$/i.test(file.name)) {
      setUploadError('Choose a .csv file.');
      return;
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      setUploadError(`The file is ${(file.size / 1e6).toFixed(1)} MB; the limit is ${MAX_UPLOAD_BYTES / 1e6} MB.`);
      return;
    }
    setUploading(true);
    try {
      const text = await file.text();
      const res = await apiClient.analyzeCsv(text, file.name);
      setData(toUploadViewData(res));
      setSource('upload');
      setPhase('success');
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'The file could not be analyzed.');
    } finally {
      setUploading(false);
    }
  }, []);

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
      setSource('demo');
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
            Validation and overall metrics for the bundled demo dataset or for a CSV you upload, computed by the backend.
          </p>
        </div>
        {phase === 'success' && source === 'demo' && (
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

      <DemoBanner
        message={
          source === 'upload' && phase === 'success'
            ? 'Source: your uploaded CSV (USER_DATA). It was validated and analyzed in memory by the backend and is not stored or sent to any model.'
            : 'Source: synthetic demo dataset (SYNTHETIC_DEMO), or upload your own CSV below.'
        }
      />

      <Panel
        title="Upload a CSV"
        subtitle={`Required columns: ${REQUIRED_COLUMNS}. Dates as YYYY-MM-DD. Up to ${MAX_UPLOAD_BYTES / 1e6} MB.`}
        actions={<Badge variant="info">Analyzed in memory, not stored</Badge>}
      >
        <input
          ref={fileRef}
          type="file"
          accept=".csv,text/csv"
          className="sr-only"
          aria-label="CSV file"
          onChange={(e) => void onFile(e)}
        />
        <Button
          variant="secondary"
          icon={<FileUp className="h-4 w-4" />}
          loading={uploading}
          onClick={() => fileRef.current?.click()}
        >
          Choose CSV file
        </Button>
        {uploadError && (
          <div role="alert" className="mt-3 rounded-lg border border-danger-500/30 bg-danger-500/5 px-3 py-2 text-sm text-danger-300">
            {uploadError}
          </div>
        )}
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

      {phase === 'success' && data && <AnalyzeResults data={data} backend={source === 'demo' ? backend : null} source={source} />}
    </div>
  );
}

function AnalyzeResults({
  data,
  backend,
  source,
}: {
  data: AnalyzeViewData;
  backend: HealthResponse | null;
  source: 'demo' | 'upload';
}) {
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
        subtitle={`${data.filename} · ${data.period ? `${data.period.start} → ${data.period.end}` : 'no valid dates'} · ${data.origin}`}
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
        {data.issues.length > 0 ? (
          <ul className="mt-4 space-y-1.5 text-sm">
            {data.issues.map((i) => (
              <li key={`${i.code}-${i.column ?? ''}`} className="flex items-start gap-2">
                <Badge variant={i.severity === 'FATAL' ? 'danger' : 'warning'}>{i.severity === 'FATAL' ? 'Error' : 'Warning'}</Badge>
                <span className="text-ink-200">
                  {i.message}
                  {i.sample_rows.length > 0 ? (
                    <span className="text-ink-500"> (e.g. data rows {i.sample_rows.join(', ')})</span>
                  ) : null}
                </span>
              </li>
            ))}
          </ul>
        ) : source === 'demo' ? (
          <p className="mt-4 text-2xs text-ink-500">
            The demo route returns issue counts only, not the individual issues, so none are listed here.
          </p>
        ) : (
          <p className="mt-4 text-sm text-ink-300">No validation issues found.</p>
        )}
      </Panel>

      <Panel title="Overall metrics" subtitle="Scope: overall (all rows in the dataset)">
        {data.metrics.length === 0 ? (
          <p className="text-sm text-ink-400">
            {data.validation.canAnalyze
              ? 'The backend returned no overall metrics.'
              : 'No metrics: the file has errors that must be fixed first (see the list above).'}
          </p>
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
        Source: {source === 'demo' ? 'GET /v1/datasets/demo and GET /v1/datasets/demo/analysis' : 'POST /v1/datasets/analyze'}
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
