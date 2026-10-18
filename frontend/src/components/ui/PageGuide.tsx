import type { ReactNode } from 'react';
import { HelpCircle } from 'lucide-react';

export interface PageGuideProps {
  purpose: ReactNode;
  how: ReactNode;
  inputs: ReactNode;
  output: ReactNode;
  limits: ReactNode;
}

const ROWS: { key: keyof PageGuideProps; label: string }[] = [
  { key: 'purpose', label: 'Purpose' },
  { key: 'how', label: 'How it works' },
  { key: 'inputs', label: 'Inputs' },
  { key: 'output', label: 'How to read the result' },
  { key: 'limits', label: 'What it does not prove' },
];

/** Short, collapsible explanation shown at the top of every page. Open by default so a first-time user sees it. */
export function PageGuide(props: PageGuideProps) {
  return (
    <details open className="group rounded-xl border border-surface-700/70 bg-surface-900/50">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-2.5 text-xs font-medium text-ink-300 hover:text-ink-100">
        <HelpCircle className="h-3.5 w-3.5 text-accent-300" />
        What is this page?
        <span className="ml-auto text-2xs text-ink-500 group-open:hidden">show</span>
        <span className="ml-auto hidden text-2xs text-ink-500 group-open:inline">hide</span>
      </summary>
      <dl className="grid grid-cols-1 gap-x-6 gap-y-2.5 border-t border-surface-700/60 px-4 py-3 text-xs sm:grid-cols-[9.5rem_1fr]">
        {ROWS.map((r) => (
          <div key={r.key} className="contents">
            <dt className="font-medium uppercase tracking-wider text-ink-500">{r.label}</dt>
            <dd className="text-ink-300">{props[r.key]}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}
