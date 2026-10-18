import { useCallback, useState } from 'react';
import { Sidebar } from '@/components/Sidebar';
import type { TabId } from '@/components/Sidebar';
import { HomeView } from '@/views/HomeView';
import { AnalyzeView } from '@/views/AnalyzeView';
import { EvaluateView } from '@/views/EvaluateView';
import { CompareView } from '@/views/CompareView';
import { ChatView } from '@/views/ChatView';

function App() {
  // The app opens on the overview: a first-time user should learn what the lab is before facing any form.
  const [tab, setTab] = useState<TabId>('home');
  // A page stays mounted once opened, so switching tabs does not throw away an evaluation result or a chat.
  const [opened, setOpened] = useState<ReadonlySet<TabId>>(new Set<TabId>(['home']));
  const go = useCallback((next: TabId) => {
    setTab(next);
    setOpened((prev) => (prev.has(next) ? prev : new Set(prev).add(next)));
  }, []);
  const page = (id: TabId, node: React.ReactNode) =>
    opened.has(id) ? (
      <div key={id} hidden={tab !== id}>
        {node}
      </div>
    ) : null;

  return (
    <div className="relative z-10 flex h-screen overflow-hidden bg-surface-950 text-ink-100">
      <Sidebar active={tab} onChange={go} />
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-6xl px-6 py-6 lg:px-8">
          {page('home', <HomeView onNavigate={go} />)}
          {page('evaluate', <EvaluateView />)}
          {page('chat', <ChatView />)}
          {page('analyze', <AnalyzeView />)}
          {page('compare', <CompareView onNavigate={go} />)}
        </div>
      </main>
    </div>
  );
}

export default App;
