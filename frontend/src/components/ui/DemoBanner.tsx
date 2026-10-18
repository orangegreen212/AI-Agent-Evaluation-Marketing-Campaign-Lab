import { clsx } from '@/lib/utils';

interface DemoBannerProps {
  className?: string;
  message?: string;
}

export function DemoBanner({ className, message }: DemoBannerProps) {
  return (
    <div
      className={clsx(
        'flex items-center gap-2 rounded-lg border border-accent-500/25 bg-accent-500/5 px-3 py-2 text-xs text-ink-300',
        className,
      )}
    >
      <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-sm bg-accent-500/20 text-2xs font-bold text-accent-200">
        D
      </span>
      <span>
        {message ??
          'DEMO DATA — results shown are fabricated fixtures, not live model executions.'}
      </span>
    </div>
  );
}
