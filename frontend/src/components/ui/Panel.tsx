import type { ReactNode } from 'react';
import { clsx } from '@/lib/utils';

interface PanelProps {
  children: ReactNode;
  className?: string;
  title?: string;
  subtitle?: string;
  actions?: ReactNode;
  accent?: boolean;
}

export function Panel({ children, className, title, subtitle, actions, accent }: PanelProps) {
  return (
    <section
      className={clsx(
        'rounded-xl border border-surface-700/80 bg-surface-850/80 backdrop-blur-sm shadow-panel animate-fade-in',
        accent && 'shadow-glow-accent',
        className,
      )}
    >
      {(title || actions) && (
        <header className="flex items-start justify-between gap-4 border-b border-surface-700/60 px-5 py-4">
          <div className="min-w-0">
            {title && (
              <h3 className="text-sm font-semibold tracking-wide text-ink-100">{title}</h3>
            )}
            {subtitle && (
              <p className="mt-0.5 text-xs text-ink-400">{subtitle}</p>
            )}
          </div>
          {actions && <div className="shrink-0">{actions}</div>}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}
