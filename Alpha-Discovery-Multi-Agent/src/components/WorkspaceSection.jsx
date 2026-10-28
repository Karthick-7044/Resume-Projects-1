import React, { useState } from 'react';
import { useAuth } from '@/context/AuthContext';
import {
  UserCheck,
  LogOut,
  TrendingUp,
  Compass,
  FileText,
  Database,
  LayoutDashboard,
  Newspaper,
  Workflow,
  BarChart3,
  Download,
  FileCheck2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { PipelineStatusCard } from '@/components/PipelineStatusCard';
import { DailyStockPanel } from '@/components/DailyStockPanel';
import { MarketTechnicalChart } from '@/components/MarketTechnicalChart';
import { RegimeTimelineChart } from '@/components/RegimeTimelineChart';
import { FundamentalDataSection } from '@/components/FundamentalDataSection';
import { NewsIntelligence } from '@/components/NewsIntelligence';
import { AlphaDiscoveryLab } from '@/components/AlphaDiscoveryLab';
import { OverviewPanel } from '@/components/OverviewPanel';
import { AgentLoopPanel } from '@/components/AgentLoopPanel';
import { SignificancePanel } from '@/components/SignificancePanel';
import { DownloadsPanel } from '@/components/DownloadsPanel';
import { FactorReportPanel } from '@/components/FactorReportPanel';

// Main sections of the research workspace (left to right = the order in which the system works)
const SECTIONS = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard, hint: 'What the system does and the key results' },
  { id: 'data', label: 'Data', icon: Database, hint: 'Prices, SEC accounts, regimes and the daily panel' },
  { id: 'news', label: 'News & FinBERT', icon: Newspaper, hint: 'News coverage and FinBERT sentiment' },
  { id: 'agents', label: 'Agent Loop', icon: Workflow, hint: 'Research â†’ Quant â†’ Validator â†’ Backtest â†’ Attribution â†’ Critic â†’ Memory' },
  { id: 'results', label: 'Backtest Results', icon: BarChart3, hint: 'Significance, ablation, equity curves, attribution' },
  { id: 'report', label: 'Alpha Factor Report', icon: FileCheck2, hint: 'Each accepted factor explained in plain language, tested after the knowledge cutoff' },
  { id: 'downloads', label: 'Paper & Downloads', icon: Download, hint: 'Journal paper and reports' },
];

const DATA_TABS = [
  { id: 'panel', label: 'Daily stock panel', icon: Database },
  { id: 'charts', label: 'Market & technical charts', icon: TrendingUp },
  { id: 'regime', label: 'Market regimes (HMM)', icon: Compass },
  { id: 'fundamentals', label: 'SEC fundamentals (PIT)', icon: FileText },
];

export function WorkspaceSection() {
  const { user, profile, signOut } = useAuth();
  const [section, setSection] = useState('overview');
  const [dataTab, setDataTab] = useState('panel');
  const [activeChartTicker, setActiveChartTicker] = useState('AAPL');

  const displayName = profile?.full_name || user?.user_metadata?.full_name || user?.email?.split('@')[0] || 'Researcher';
  const go = (id) => {
    setSection(id);
    document.getElementById('workspace-nav')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };
  const current = SECTIONS.find((s) => s.id === section);

  return (
    <section id="workspace" className="relative py-20 text-slate-100 overflow-x-clip">
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[750px] h-[750px] bg-blue-600/10 rounded-full blur-[180px] pointer-events-none" />
      <div className="absolute inset-0 bg-grid-pattern opacity-25 pointer-events-none" />

      <div className="relative max-w-7xl mx-auto px-4 sm:px-8 lg:px-12 space-y-8">
        {/* Workspace header */}
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 glass-card rounded-3xl p-6 border border-white/15">
          <div className="space-y-3">
            <h2 className="font-heading text-3xl sm:text-4xl text-white">Alpha Discovery Research Workspace</h2>
            <p className="text-sm text-slate-300 flex items-center gap-2">
              <UserCheck className="w-4 h-4 text-cyan-400" />
              <span>Signed in as <strong className="text-white font-semibold">{displayName}</strong> ({user?.email || 'demo-researcher@alphadiscovery.org'})</span>
            </p>
          </div>
          <Button variant="ghost" size="sm" onClick={signOut}
            className="text-xs font-mono text-rose-400 hover:text-rose-300 hover:bg-rose-950/40 border border-rose-500/30">
            <LogOut className="w-3.5 h-3.5 mr-1.5" /> Sign Out
          </Button>
        </div>

        {/* Section navigation (sticky) */}
        <nav id="workspace-nav" aria-label="Workspace sections"
          className="sticky top-24 z-30 glass-card rounded-full p-1.5 backdrop-blur-md scroll-mt-28">
          <div className="flex gap-1.5 overflow-x-auto">
            {SECTIONS.map(({ id, label, icon: I }) => (
              <button key={id} onClick={() => go(id)} aria-current={section === id ? 'page' : undefined}
                className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-mono font-semibold whitespace-nowrap transition-all ${
                  section === id ? 'bg-white text-black shadow-[0_8px_30px_-8px_rgba(165,180,252,0.6)]' : 'text-slate-300 hover:text-white hover:bg-white/5'}`}>
                <I className="w-3.5 h-3.5" /><span>{label}</span>
              </button>
            ))}
          </div>
        </nav>
        <p className="text-xs font-mono text-slate-400 px-2 pt-1">{current?.hint}</p>

        {section === 'overview' && <OverviewPanel onNavigate={go} />}

        {section === 'data' && (
          <div className="space-y-6">
            <PipelineStatusCard />
            <div className="flex flex-wrap gap-2">
              {DATA_TABS.map(({ id, label, icon: I }) => (
                <button key={id} onClick={() => setDataTab(id)}
                  className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-mono ${dataTab === id ? 'bg-cyan-500 text-black font-bold' : 'bg-black/30 border border-white/10 text-slate-300 hover:text-white'}`}>
                  <I className="w-3.5 h-3.5" />{label}
                </button>
              ))}
            </div>
            {dataTab === 'panel' && (
              <DailyStockPanel onSelectTickerForChart={(t) => { setActiveChartTicker(t); setDataTab('charts'); }} />
            )}
            {dataTab === 'charts' && (
              <div className="space-y-6">
                <div className="flex flex-wrap items-center gap-2 bg-void-900/90 border border-white/10 rounded-2xl p-4">
                  <span className="text-xs font-mono text-slate-400">Ticker:</span>
                  {['AAPL', 'AMZN', 'GOOGL', 'JNJ', 'JPM', 'META', 'MSFT', 'NVDA', 'V', 'XOM'].map((t) => (
                    <button key={t} onClick={() => setActiveChartTicker(t)}
                      className={`px-3 py-1 rounded-lg text-xs font-mono font-bold ${activeChartTicker === t ? 'bg-cyan-500 text-black' : 'bg-black/30 text-slate-400 hover:text-white border border-white/5'}`}>
                      {t}
                    </button>
                  ))}
                </div>
                <MarketTechnicalChart ticker={activeChartTicker} />
              </div>
            )}
            {dataTab === 'regime' && <RegimeTimelineChart limit={1600} />}
            {dataTab === 'fundamentals' && <FundamentalDataSection />}
          </div>
        )}

        {section === 'news' && <NewsIntelligence />}
        {section === 'agents' && <AgentLoopPanel />}
        {section === 'results' && (
          <div className="space-y-6">
            <SignificancePanel />
            <AlphaDiscoveryLab />
          </div>
        )}
        {section === 'report' && <FactorReportPanel />}
        {section === 'downloads' && <DownloadsPanel />}
      </div>
    </section>
  );
}
