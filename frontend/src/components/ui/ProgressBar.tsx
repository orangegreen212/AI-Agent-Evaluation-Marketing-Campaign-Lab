import { clsx } from '@/lib/utils';

interface ProgressBarProps {
  value: number; // 0..1
  className?: string;
  indeterminate?: boolean;
}

export function ProgressBar({ value, className, indeterminate }: ProgressBarProps) {
  return (
    <div className={clsx('h-1.5 w-full overflow-hidden rounded-full bg-surface-700/60', className)}>
      <div
        className={clsx(
          'h-full rounded-full bg-accent-400 transition-all duration-300',
          indeterminate && 'animate-pulse-soft',
        )}
        style={{ width: indeterminate ? '40%' : `${Math.max(0, Math.min(1, value)) * 100}%` }}
      />
    </div>
  );
}
