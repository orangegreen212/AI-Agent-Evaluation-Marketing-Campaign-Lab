import type { ReactNode } from 'react';

interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-surface-700 bg-surface-900/40 px-6 py-14 text-center">
      {icon && <div className="mb-3 text-ink-400">{icon}</div>}
      <h3 className="text-sm font-semibold text-ink-100">{title}</h3>
      {description && (
        <p className="mt-1 max-w-sm text-xs text-ink-400">{description}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

interface ErrorStateProps {
  title?: string;
  message: string;
  onRetry?: () => void;
}

export function ErrorState({ title = 'Something went wrong', message, onRetry }: ErrorStateProps) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-danger-500/30 bg-danger-500/5 px-6 py-12 text-center">
      <h3 className="text-sm font-semibold text-danger-300">{title}</h3>
      <p className="mt-1 max-w-md text-xs text-ink-300">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-4 rounded-lg border border-danger-500/40 bg-danger-500/10 px-3 py-1.5 text-xs font-medium text-danger-200 transition-colors hover:bg-danger-500/20"
        >
          Try again
        </button>
      )}
    </div>
  );
}

interface LoadingStateProps {
  label?: string;
}

export function LoadingState({ label = 'Loading…' }: LoadingStateProps) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-surface-700 bg-surface-900/40 px-6 py-14 text-center">
      <span className="h-6 w-6 animate-spin rounded-full border-2 border-accent-400/40 border-t-accent-400" />
      <p className="mt-3 text-sm text-ink-300">{label}</p>
    </div>
  );
}
