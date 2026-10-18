import { ArrowRight } from 'lucide-react';
import type { TabId } from '@/components/Sidebar';
import { Panel, Button, Badge, SourceBadge } from '@/components/ui';

type Status = 'works' | 'works-limits' | 'sample';

const PAGES: {
  id: TabId;
  name: string;
  does: string;
  uses: React.ReactNode;
  status: Status;
  note: string;
}[] = [
  {
    id: 'evaluate',
    name: 'Evaluate & Safety',
    does: 'Sends 4 built-in test prompts to the model you pick and checks each reply against a fixed rule. Shows PASS / FAIL / ERROR / SKIPPED per case, with the evidence.',
    uses: (
      <div className="flex flex-wrap gap-1.5">
        <SourceBadge kind="live" />
        <SourceBadge kind="builtin" />
      </div>
    ),
    status: 'works-limits',
    note: 'Works. A run is shown once and is not saved: reloading the page clears it.',
  },
  {
    id: 'chat',
    name: 'Agent Chat',
    does: 'A plain conversation with a configured model. Nothing is scored or saved.',
    uses: <SourceBadge kind="live" />,
    status: 'works',
    note: 'Works. This is a way to try a model, not an evaluation.',
  },
  {
    id: 'analyze',
    name: 'Analyze CSV',
    does: 'Checks a marketing-campaign CSV for problems and calculates ROAS, CPA, CTR and totals with fixed formulas. No AI model is involved.',
    uses: (
      <div className="flex flex-wrap gap-1.5">
        <SourceBadge kind="your-data" />
      </div>
    ),
    status: 'works-limits',
    note: 'Works on its own. The AI advisor that writes a report from these metrics exists in the backend code but is not connected to any page yet.',
  },
  {
    id: 'compare',
    name: 'Compare Models',
    does: 'Would compare saved runs of several models side by side. Today it can only show a made-up example of that screen.',
    uses: <SourceBadge kind="sample" />,
    status: 'sample',
    note: 'Not built. Needs stored run records, which do not exist yet.',
  },
];

const STATUS: Record<Status, { label: string; variant: 'success' | 'warning' | 'neutral' }> = {
  works: { label: 'Works', variant: 'success' },
  'works-limits': { label: 'Works, with limits', variant: 'neutral' },
  sample: { label: 'Sample only', variant: 'warning' },
};

const STEPS = [
  ['Choose', 'a model endpoint and the test suite.'],
  ['Run', 'the suite. Each case is one real call to that model.'],
  ['Read the evidence', 'for every case: what was expected, what the model said, which checks decided the verdict.'],
  ['Check the limits', 'a banner says whether the run was complete and what the result does not prove.'],
] as const;

export function HomeView({ onNavigate }: { onNavigate: (tab: TabId) => void }) {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-ink-50">AI Agent Evaluation & Safety Lab</h1>
        <p className="mt-1 max-w-3xl text-sm text-ink-300">
          Test how a configured AI model behaves on a fixed set of safety checks, and see the evidence behind every
          verdict. It is an evaluation tool, not a chatbot and not an analytics dashboard.
        </p>
      </div>

      <Panel title="How to use it" subtitle="The main path through the app" accent>
        <ol className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map(([title, text], i) => (
            <li key={title} className="rounded-lg border border-surface-700/70 bg-surface-800/40 px-3 py-3">
              <div className="font-mono text-2xs text-accent-300">STEP {i + 1}</div>
              <div className="mt-0.5 text-sm font-semibold text-ink-100">{title}</div>
              <p className="mt-0.5 text-xs text-ink-400">{text}</p>
            </li>
          ))}
        </ol>
        <div className="mt-4">
          <Button variant="primary" icon={<ArrowRight className="h-4 w-4" />} onClick={() => onNavigate('evaluate')}>
            Go to Evaluate & Safety
          </Button>
        </div>
      </Panel>

      <Panel title="What each page does, and what is real" subtitle="Status reflects the code in this version, not the roadmap">
        <ul className="space-y-3">
          {PAGES.map((p) => (
            <li key={p.id} className="rounded-lg border border-surface-700/60 bg-surface-800/30 px-4 py-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <button
                  type="button"
                  onClick={() => onNavigate(p.id)}
                  className="text-sm font-semibold text-ink-100 underline-offset-2 hover:text-accent-200 hover:underline"
                >
                  {p.name}
                </button>
                <Badge variant={STATUS[p.status].variant}>{STATUS[p.status].label}</Badge>
              </div>
              <p className="mt-1 text-sm text-ink-300">{p.does}</p>
              <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5">
                <span className="text-2xs font-medium uppercase tracking-wider text-ink-500">Data</span>
                {p.uses}
              </div>
              <p className="mt-2 text-xs text-ink-400">{p.note}</p>
            </li>
          ))}
        </ul>
      </Panel>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Panel title="Reading the labels">
          <dl className="space-y-2.5 text-xs text-ink-300">
            <div className="flex items-start gap-3"><SourceBadge kind="live" className="shrink-0" /><dd>The backend really called the model you selected.</dd></div>
            <div className="flex items-start gap-3"><SourceBadge kind="builtin" className="shrink-0" /><dd>The prompts are the lab&apos;s own invented test text. Nothing of yours is sent.</dd></div>
            <div className="flex items-start gap-3"><SourceBadge kind="your-data" className="shrink-0" /><dd>A file you chose. It is processed in this tab and never uploaded.</dd></div>
            <div className="flex items-start gap-3"><SourceBadge kind="sample" className="shrink-0" /><dd>Fabricated numbers that only preview a screen. Never a measurement.</dd></div>
          </dl>
        </Panel>
        <Panel title="Not built yet" subtitle="Specified in docs/PHASE3_SPEC.md; no code exists">
          <ul className="list-disc space-y-1 pl-5 text-sm text-ink-300">
            <li>Saved run records and run history</li>
            <li>Baselines and regression comparison between runs</li>
            <li>Release-gate decisions (PASS / WARN / FAIL)</li>
          </ul>
          <p className="mt-3 text-xs text-ink-400">
            Until these exist, each evaluation is a one-off result and nothing in this app tells you whether a model got
            better or worse than before.
          </p>
        </Panel>
      </div>
    </div>
  );
}
