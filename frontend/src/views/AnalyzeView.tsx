import { useCallback, useRef, useState } from 'react';
import type { ChangeEvent } from 'react';
import { FileSpreadsheet, FileUp, RefreshCw } from 'lucide-react';
import { toUploadViewData, type AnalyzeViewData } from '@/lib/analysisAdapter';
import { analyzeCsvBytes, analyzeCsvFile, MAX_CSV_BYTES } from '@/lib/csvAnalysis';
import {
  Panel,
  MetricCard,
  Button,
  Badge,
  PageGuide,
  Provenance,
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
  const [error, setError] = useState('');
  const [source, setSource] = useState<'demo' | 'upload'>('demo');
  const [uploadError, setUploadError] = useState('');
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
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
    if (file.size > MAX_CSV_BYTES) {
      setUploadError(`The file is ${(file.size / 1e6).toFixed(0)} MB; the limit is ${MAX_CSV_BYTES / 1e6} MB.`);
      return;
    }
    setUploading(true);
    setProgress(0);
    try {
      // Analyzed in this browser tab: the file is not uploaded anywhere.
      const res = await analyzeCsvFile(file, { onProgress: setProgress });
      setData(toUploadViewData(res));
      setSource('upload');
      setPhase('success');
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'The file could not be analyzed.');
    } finally {
      setUploading(false);
    }
  }, []);

  // The bundled demo file is static (public/sample_campaigns.csv) and goes through the same in-browser analysis.
  const load = useCallback(async () => {
    setPhase('loading');
    setError('');
    try {
      const res = await fetch('/sample_campaigns.csv');
      if (!res.ok) throw new Error(`The demo file could not be loaded (HTTP ${res.status}).`);
      const out = await analyzeCsvBytes(await res.arrayBuffer(), {
        filename: 'sample_campaigns.csv',
        origin: 'SYNTHETIC_DEMO',
        datasetId: 'demo-sample-campaigns',
      });
      setData(toUploadViewData(out));
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
          <h1 className="text-xl font-semibold text-ink-50">Analyze CSV</h1>
          <p className="mt-1 text-sm text-ink-400">
            Check a marketing-campaign CSV for problems and calculate its key metrics. No AI model is involved on this page.
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

      <PageGuide
        purpose="Make sure a campaign file is usable and get its totals and ratios (ROAS, CPA, CTR) before trusting any number built on it."
        how="Your browser reads the file, applies the same validation rules as the backend, and calculates the metrics with fixed formulas. Nothing is uploaded and no model is called."
        inputs="A CSV you choose, or the bundled example file. Required columns are listed in the upload box."
        output="A validation status with a list of problems to fix, then overall metrics. A file with fatal errors gets no metrics, by design."
        limits="This checks the file and does the arithmetic. It does not say whether the campaigns were good, and it is separate from the model evaluation pages."
      />

      {phase === 'success' && data ? (
        <Provenance kinds={source === 'upload' ? ['your-data'] : ['sample']}>
          {source === 'upload'
            ? `Your file ${data.filename}. Validated and analysed in this tab; not uploaded, stored or sent to any model.`
            : 'The bundled example file (invented numbers). The calculations are real, but this is not your data.'}
        </Provenance>
      ) : (
        <Provenance kinds={[]}>No dataset analysed yet. Results will be labelled with where they come from.</Provenance>
      )}

      <Panel
        title="Upload a CSV"
        subtitle={`Required columns: ${REQUIRED_COLUMNS}. Dates as YYYY-MM-DD. Up to ${MAX_CSV_BYTES / 1e6} MB.`}
        actions={<Badge variant="info">Stays in your browser</Badge>}
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
          {uploading ? `Analyzing… ${Math.round(progress * 100)}%` : 'Choose CSV file'}
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
          title="No dataset analysed yet"
          description="Choose your own CSV above, or try the bundled example file to see what the results look like. The example is labelled as sample data."
          action={
            <Button variant="secondary" onClick={load}>
              Try the example dataset
            </Button>
          }
        />
      )}

      {phase === 'loading' && <LoadingState label="Analysing the example dataset…" />}

      {phase === 'error' && (
        <ErrorState title="Could not load the example dataset" message={error} onRetry={load} />
      )}

      {phase === 'success' && data && <AnalyzeResults data={data} source={source} />}
    </div>
  );
}

function AnalyzeResults({ data, source }: { data: AnalyzeViewData; source: 'demo' | 'upload' }) {
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
        subtitle={`${data.filename} · ${data.period ? `${data.period.start} → ${data.period.end}` : 'no valid dates'} · ${source === 'upload' ? 'your file' : 'bundled example (sample data)'}`}
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
        ) : (
          <p className="mt-4 text-sm text-ink-300">No validation issues found.</p>
        )}
      </Panel>

      <Panel title="Overall metrics" subtitle="Scope: all accepted rows together. Fixed formulas, no model; the formula is shown under each value.">
        {data.metrics.length === 0 ? (
          <p className="text-sm text-ink-400">
            {data.validation.canAnalyze
              ? 'No overall metrics were produced.'
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
        <Panel title="Limitations">
          <ul className="list-disc space-y-1 pl-5 text-sm text-ink-300">
            {data.limitations.map((lim) => (
              <li key={lim}>{lim}</li>
            ))}
          </ul>
        </Panel>
      )}

      <p className="text-2xs text-ink-500">
        {source === 'demo' ? 'Source: public/sample_campaigns.csv (synthetic), ' : 'Source: the file you chose, '}
        analyzed in this browser. Same rules as the backend validator; overall scope only.
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
