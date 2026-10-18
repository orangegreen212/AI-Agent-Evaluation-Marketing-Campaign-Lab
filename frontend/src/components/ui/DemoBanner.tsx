import { clsx } from '@/lib/utils';

interface DemoBannerProps {
  className?: string;
  message?: string;
}

/** Loud marker for fabricated sample data. Used only where numbers are fixtures, never for real or user data. */
export function DemoBanner({ className, message }: DemoBannerProps) {
  return (
    <div
      role="note"
      className={clsx(
        'flex items-start gap-2.5 rounded-lg border border-warning-500/50 bg-warning-500/10 px-3 py-2.5 text-xs text-warning-400',
        className,
      )}
    >
      <span className="mt-px shrink-0 rounded-sm bg-warning-500/25 px-1.5 py-0.5 text-2xs font-bold uppercase tracking-wider">
        Sample data
      </span>
      <span>{message ?? 'These results are fabricated fixtures, not live model executions.'}</span>
    </div>
  );
}
