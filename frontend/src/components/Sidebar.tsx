import { BarChart3, ShieldCheck, GitCompare, FlaskConical, MessageSquare, Home } from 'lucide-react';
import { clsx } from '@/lib/utils';

export type TabId = 'home' | 'evaluate' | 'chat' | 'analyze' | 'compare';

interface SidebarProps {
  active: TabId;
  onChange: (tab: TabId) => void;
}

type NavItem = { id: TabId; label: string; icon: typeof BarChart3; description: string; status?: { text: string; sample?: boolean } };

/** Order follows the workflow: understand → run a real evaluation → look closer → separate tools → previews. */
const sections: { title: string; items: NavItem[] }[] = [
  {
    title: 'Start here',
    items: [{ id: 'home', label: 'Overview', icon: Home, description: 'What this lab does and what works' }],
  },
  {
    title: 'Evaluate a model',
    items: [
      { id: 'evaluate', label: 'Evaluate & Safety', icon: ShieldCheck, description: 'Run the test suite, see evidence' },
      { id: 'chat', label: 'Agent Chat', icon: MessageSquare, description: 'Talk to a model (not scored)' },
    ],
  },
  {
    title: 'Data tool',
    items: [{ id: 'analyze', label: 'Analyze CSV', icon: BarChart3, description: 'Campaign metrics, no model involved' }],
  },
  {
    title: 'Preview (not built yet)',
    items: [
      {
        id: 'compare',
        label: 'Compare Models',
        icon: GitCompare,
        description: 'Planned feature, sample data only',
        status: { text: 'Sample', sample: true },
      },
    ],
  },
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
      <nav className="flex-1 space-y-4 overflow-y-auto px-3 py-4">
        {sections.map((section) => (
          <div key={section.title} className="space-y-1">
            <div className="px-2 pb-1 text-2xs font-medium uppercase tracking-wider text-ink-500">{section.title}</div>
            {section.items.map((item) => {
              const Icon = item.icon;
              const isActive = active === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => onChange(item.id)}
                  aria-current={isActive ? 'page' : undefined}
                  className={clsx(
                    'group flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-all',
                    isActive
                      ? 'border border-accent-500/30 bg-accent-500/10 text-ink-50'
                      : 'border border-transparent text-ink-300 hover:bg-surface-800/60 hover:text-ink-100',
                  )}
                >
                  <Icon
                    className={clsx('h-4 w-4 shrink-0', isActive ? 'text-accent-300' : 'text-ink-400 group-hover:text-ink-200')}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 text-sm font-medium">
                      {item.label}
                      {item.status && (
                        <span
                          className={clsx(
                            'rounded border px-1 text-2xs font-semibold uppercase tracking-wider',
                            item.status.sample
                              ? 'border-warning-500/50 bg-warning-500/15 text-warning-400'
                              : 'border-surface-600 text-ink-300',
                          )}
                        >
                          {item.status.text}
                        </span>
                      )}
                    </div>
                    <div className="truncate text-2xs text-ink-500">{item.description}</div>
                  </div>
                </button>
              );
            })}
          </div>
        ))}
      </nav>

      {/* Footer: what is real. Keep in sync with dataSourceByView in the API client. */}
      <div className="space-y-1.5 border-t border-surface-700/60 px-4 py-3 text-2xs text-ink-400">
        <div>
          <span className="font-medium text-ink-200">Evaluate, Chat:</span> real model calls via the backend
        </div>
        <div>
          <span className="font-medium text-ink-200">Analyze CSV:</span> computed in your browser
        </div>
        <div>
          <span className="font-medium text-warning-400">Compare:</span> fabricated sample, no model is called
        </div>
      </div>
    </aside>
  );
}
