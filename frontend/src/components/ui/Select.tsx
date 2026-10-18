import type { ReactNode } from 'react';
import { clsx } from '@/lib/utils';

interface SelectProps {
  label?: string;
  value: string;
  onChange: (value: string) => void;
  children: ReactNode;
  className?: string;
  disabled?: boolean;
  hint?: string;
}

export function Select({ label, value, onChange, children, className, disabled, hint }: SelectProps) {
  return (
    <label className={clsx('block', className)}>
      {label && (
        <span className="mb-1.5 block text-2xs font-medium uppercase tracking-wider text-ink-400">
          {label}
        </span>
      )}
      <div className="relative">
        <select
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          className={clsx(
            'w-full appearance-none rounded-lg border border-surface-600/70 bg-surface-800 px-3 py-2 pr-9 text-sm text-ink-100 transition-colors',
            'focus:border-accent-500/60 focus:outline-none',
            'disabled:cursor-not-allowed disabled:opacity-50',
          )}
        >
          {children}
        </select>
        <svg
          className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-400"
          viewBox="0 0 20 20"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
        >
          <path d="M6 8l4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
      {hint && <span className="mt-1 block text-2xs text-ink-500">{hint}</span>}
    </label>
  );
}
