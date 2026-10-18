import type { ReactNode } from 'react';
import { clsx } from '@/lib/utils';

interface MetricCardProps {
  label: string;
  value: ReactNode;
  sublabel?: string;
  trend?: { value: string; positive?: boolean };
  icon?: ReactNode;
  accent?: boolean;
}

export function MetricCard({ label, value, sublabel, trend, icon, accent }: MetricCardProps) {
  return (
    <div
      className={clsx(
        'relative overflow-hidden rounded-xl border bg-surface-850/80 px-4 py-3.5 transition-colors',
        accent
          ? 'border-accent-500/30 shadow-glow-accent'
          : 'border-surface-700/70 hover:border-surface-600',
      )}
    >
      <div className="flex items-center justify-between">
        <span className="text-2xs font-medium uppercase tracking-wider text-ink-400">
          {label}
        </span>
        {icon && <span className="text-ink-400">{icon}</span>}
      </div>
      <div className="mt-1.5 flex items-baseline gap-2">
        <span className="font-mono text-2xl font-semibold tabular-nums text-ink-50">
          {value}
        </span>
        {trend && (
          <span
            className={clsx(
              'text-2xs font-medium',
              trend.positive ? 'text-success-400' : 'text-danger-400',
            )}
          >
            {trend.value}
          </span>
        )}
      </div>
      {sublabel && <p className="mt-0.5 text-2xs text-ink-500">{sublabel}</p>}
    </div>
  );
}
