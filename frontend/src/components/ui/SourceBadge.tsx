import { clsx } from '@/lib/utils';

/**
 * Where a displayed result comes from. Four kinds, deliberately visually distinct, so a fabricated sample can
 * never be mistaken for a real run:
 *   live        a real call to the selected model endpoint, made by the backend just now
 *   builtin     the lab's own fixed synthetic test inputs (invented text; no personal or user data)
 *   your-data   a file you chose; analysed in this browser tab, never uploaded
 *   sample      fabricated fixture numbers shown only as a preview of a planned screen. NOT a measurement.
 */
export type SourceKind = 'live' | 'builtin' | 'your-data' | 'sample';

const META: Record<SourceKind, { label: string; hint: string; className: string }> = {
  live: {
    label: 'Real model call',
    hint: 'The backend sent these requests to the selected model and scored its replies.',
    className: 'border-accent-500/40 bg-accent-500/10 text-accent-200',
  },
  builtin: {
    label: 'Built-in synthetic inputs',
    hint: 'Invented test text shipped with the lab. No personal or user data.',
    className: 'border-surface-600 bg-surface-700/50 text-ink-200',
  },
  'your-data': {
    label: 'Your data · stays in this browser',
    hint: 'Your file was analysed in this browser tab. It was not uploaded, stored or sent to any model.',
    className: 'border-success-500/40 bg-success-500/10 text-success-400',
  },
  sample: {
    label: 'Sample data · fabricated',
    hint: 'Made-up example numbers. Not measured from a real model run and not from your files.',
    className: 'border-warning-500/60 bg-warning-500/15 text-warning-400',
  },
};

export function SourceBadge({ kind, className }: { kind: SourceKind; className?: string }) {
  const m = META[kind];
  return (
    <span
      title={m.hint}
      className={clsx(
        'inline-flex items-center rounded-md border px-2 py-0.5 text-2xs font-semibold uppercase tracking-wider',
        m.className,
        className,
      )}
    >
      {m.label}
    </span>
  );
}

/** A row of source badges followed by one sentence saying what that means. */
export function Provenance({ kinds, children }: { kinds: SourceKind[]; children?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-surface-700/70 bg-surface-900/50 px-3 py-2">
      <span className="text-2xs font-medium uppercase tracking-wider text-ink-500">Source</span>
      {kinds.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {kinds.map((k) => (
            <SourceBadge key={k} kind={k} />
          ))}
        </div>
      )}
      {children && <span className="text-xs text-ink-400">{children}</span>}
    </div>
  );
}
