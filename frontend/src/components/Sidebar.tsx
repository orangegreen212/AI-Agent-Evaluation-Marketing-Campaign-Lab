import { BarChart3, ShieldCheck, GitCompare, FlaskConical, MessageSquare, Circle } from 'lucide-react';
import { clsx } from '@/lib/utils';

export type TabId = 'analyze' | 'evaluate' | 'chat' | 'compare';

interface SidebarProps {
  active: TabId;
  onChange: (tab: TabId) => void;
}

const nav: { id: TabId; label: string; icon: typeof BarChart3; description: string }[] = [
  { id: 'analyze', label: 'Analyze', icon: BarChart3, description: 'Campaign metrics' },
  { id: 'evaluate', label: 'Evaluate & Safety', icon: ShieldCheck, description: 'Single model runs' },
  { id: 'chat', label: 'Agent Chat', icon: MessageSquare, description: 'Local model conversation' },
  { id: 'compare', label: 'Compare Models', icon: GitCompare, description: 'Side-by-side' },
];

export function Sidebar({ active, onChange }: SidebarProps) {
  return (
    <aside className="flex w-64 shrink-0 flex-col border-r border-surface-700/60 bg-surface-900/60 backdrop-blur-sm">
      {/* Brand */}
      <div className="flex items-center gap-3 border-b border-surface-700/60 px-5 py-4">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-accent-500/40 bg-accent-500/10">
          <FlaskConical className="h-5 w-5 text-accent-300" />
        </div>
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-ink-50">Eval & Safety Lab</div>
          <div className="truncate text-2xs text-ink-500">AI Agent Evaluation</div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 space-y-1 px-3 py-4">
        <div className="px-2 pb-2 text-2xs font-medium uppercase tracking-wider text-ink-500">
          Workflows
        </div>
        {nav.map((item) => {
          const Icon = item.icon;
          const isActive = active === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onChange(item.id)}
              className={clsx(
                'group flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-all',
                isActive
                  ? 'border border-accent-500/30 bg-accent-500/10 text-ink-50'
                  : 'border border-transparent text-ink-300 hover:bg-surface-800/60 hover:text-ink-100',
              )}
            >
              <Icon
                className={clsx(
                  'h-4 w-4 shrink-0',
                  isActive ? 'text-accent-300' : 'text-ink-400 group-hover:text-ink-200',
                )}
              />
              <div className="min-w-0">
                <div className="text-sm font-medium">{item.label}</div>
                <div className="truncate text-2xs text-ink-500">{item.description}</div>
              </div>
            </button>
          );
        })}
      </nav>

      {/* Footer: data source per view. Keep in sync with dataSourceByView in the API client. */}
      <div className="border-t border-surface-700/60 px-4 py-3 space-y-1.5 text-2xs text-ink-400">
        <div className="flex items-center gap-2">
          <Circle className="h-2 w-2 fill-current text-success-400" />
          <span>Analyze, Evaluate, Agent Chat: backend</span>
        </div>
        <div className="flex items-center gap-2">
          <Circle className="h-2 w-2 fill-current text-warning-400" />
          <span>Compare Models: demo only</span>
        </div>
      </div>
    </aside>
  );
}
