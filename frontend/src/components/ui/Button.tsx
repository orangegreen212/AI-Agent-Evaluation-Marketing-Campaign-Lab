import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { clsx } from '@/lib/utils';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';
type Size = 'sm' | 'md';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  icon?: ReactNode;
  loading?: boolean;
}

const variants: Record<Variant, string> = {
  primary:
    'bg-accent-500/15 text-accent-200 border border-accent-500/40 hover:bg-accent-500/25 hover:border-accent-400/60',
  secondary:
    'bg-surface-700/60 text-ink-100 border border-surface-600/70 hover:bg-surface-700 hover:border-surface-500',
  ghost:
    'bg-transparent text-ink-300 border border-transparent hover:bg-surface-800/60 hover:text-ink-100',
  danger:
    'bg-danger-500/15 text-danger-300 border border-danger-500/40 hover:bg-danger-500/25',
};

const sizes: Record<Size, string> = {
  sm: 'px-2.5 py-1.5 text-xs gap-1.5',
  md: 'px-4 py-2 text-sm gap-2',
};

export function Button({
  variant = 'secondary',
  size = 'md',
  icon,
  loading,
  children,
  className,
  disabled,
  ...rest
}: ButtonProps) {
  return (
    <button
      className={clsx(
        'inline-flex items-center justify-center rounded-lg font-medium transition-all duration-150 disabled:cursor-not-allowed disabled:opacity-50',
        variants[variant],
        sizes[size],
        className,
      )}
      disabled={disabled || loading}
      {...rest}
    >
      {loading ? (
        <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
      ) : (
        icon
      )}
      {children}
    </button>
  );
}
