import { clsx } from '@/lib/utils';
import type { RunStatus, CaseResultStatus, FindingSeverity, ValidationLevel } from '@/types/api';

type BadgeVariant =
  | 'neutral'
  | 'accent'
  | 'success'
  | 'warning'
  | 'danger'
  | 'info';

const variants: Record<BadgeVariant, string> = {
  neutral: 'bg-surface-700/60 text-ink-200 border-surface-600/60',
  accent: 'bg-accent-500/10 text-accent-300 border-accent-500/30',
  success: 'bg-success-500/10 text-success-400 border-success-500/30',
  warning: 'bg-warning-500/10 text-warning-400 border-warning-500/30',
  danger: 'bg-danger-500/10 text-danger-400 border-danger-500/30',
  info: 'bg-surface-700/40 text-ink-300 border-surface-600/60',
};

interface BadgeProps {
  variant?: BadgeVariant;
  children: React.ReactNode;
  dot?: boolean;
  className?: string;
}

export function Badge({ variant = 'neutral', children, dot, className }: BadgeProps) {
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-2xs font-medium uppercase tracking-wider',
        variants[variant],
        className,
      )}
    >
      {dot && <span className="h-1.5 w-1.5 rounded-full bg-current" />}
      {children}
    </span>
  );
}

const statusMap: Record<RunStatus, { variant: BadgeVariant; label: string }> = {
  idle: { variant: 'neutral', label: 'Idle' },
  queued: { variant: 'info', label: 'Queued' },
  running: { variant: 'accent', label: 'Running' },
  completed: { variant: 'success', label: 'Completed' },
  failed: { variant: 'danger', label: 'Failed' },
  partial: { variant: 'warning', label: 'Partial' },
};

export function StatusBadge({ status }: { status: RunStatus }) {
  const { variant, label } = statusMap[status];
  const pulse = status === 'running' || status === 'queued';
  return (
    <Badge variant={variant} dot className={pulse ? 'animate-pulse-soft' : undefined}>
      {label}
    </Badge>
  );
}

const caseStatusMap: Record<CaseResultStatus, { variant: BadgeVariant; label: string }> = {
  pass: { variant: 'success', label: 'Pass' },
  fail: { variant: 'danger', label: 'Fail' },
  error: { variant: 'warning', label: 'Error' },
  skipped: { variant: 'neutral', label: 'Skipped' },
};

export function CaseStatusBadge({ status }: { status: CaseResultStatus }) {
  const { variant, label } = caseStatusMap[status];
  return <Badge variant={variant}>{label}</Badge>;
}

const severityMap: Record<FindingSeverity, { variant: BadgeVariant }> = {
  critical: { variant: 'danger' },
  high: { variant: 'danger' },
  medium: { variant: 'warning' },
  low: { variant: 'info' },
  info: { variant: 'neutral' },
};

export function SeverityBadge({ severity }: { severity: FindingSeverity }) {
  const { variant } = severityMap[severity];
  return <Badge variant={variant}>{severity}</Badge>;
}

export function ValidationBadge({ level }: { level: ValidationLevel }) {
  const map: Record<ValidationLevel, { variant: BadgeVariant; label: string }> = {
    ok: { variant: 'success', label: 'OK' },
    warning: { variant: 'warning', label: 'Warning' },
    error: { variant: 'danger', label: 'Error' },
  };
  const { variant, label } = map[level];
  return <Badge variant={variant}>{label}</Badge>;
}
