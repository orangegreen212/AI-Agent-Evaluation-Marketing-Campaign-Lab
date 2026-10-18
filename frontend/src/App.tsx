import { useState } from 'react';
import { Sidebar } from '@/components/Sidebar';
import type { TabId } from '@/components/Sidebar';
import { AnalyzeView } from '@/views/AnalyzeView';
import { EvaluateView } from '@/views/EvaluateView';
import { CompareView } from '@/views/CompareView';
import { ChatView } from '@/views/ChatView';

function App() {
  const [tab, setTab] = useState<TabId>('analyze');

  return (
    <div className="relative z-10 flex h-screen overflow-hidden bg-surface-950 text-ink-100">
      <Sidebar active={tab} onChange={setTab} />
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-6xl px-6 py-6 lg:px-8">
          {tab === 'analyze' && <AnalyzeView />}
          {tab === 'evaluate' && <EvaluateView />}
          {tab === 'chat' && <ChatView />}
          {tab === 'compare' && <CompareView />}
        </div>
      </main>
    </div>
  );
}

export default App;
