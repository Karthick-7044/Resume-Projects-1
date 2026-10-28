import React, { useEffect, useState, useMemo } from 'react';
import {
  Database,
  Search,
  Filter,
  RefreshCw,
  SlidersHorizontal,
  Layers,
  ChevronLeft,
  ChevronRight,
  Sparkles,
  CheckCircle,
  AlertTriangle,
  Info,
  ArrowUpDown,
  TrendingUp,
  FileText,
  Radio,
  Eye,
  X
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { fetchUniverse, fetchDailyStockPanel } from '@/lib/api';

const DEFAULT_TICKERS = ['AAPL', 'AMZN', 'GOOGL', 'JNJ', 'JPM', 'META', 'MSFT', 'NVDA', 'V', 'XOM'];

const FEATURE_TABS = [
  { id: 'overview', name: 'Core Quant Panel', desc: 'Primary cross-domain signal matrix' },
  { id: 'market', name: 'Market (OHLCV)', desc: 'Prices, adjusted close, and trading volumes' },
  { id: 'technical', name: 'Technical & Momentum', desc: 'RSI, MACD, SMAs, Momentum & Volatility' },
  { id: 'fundamentals', name: 'SEC Fundamentals (PIT)', desc: 'Point-in-Time GAAP financials & growth metrics' },
  { id: 'valuation', name: 'Valuation Ratios', desc: 'P/E, P/B, and P/S multiples' },
  { id: 'news', name: 'News Sentiment', desc: 'Sentiment scores, tone, and event counts' },
  { id: 'regime', name: 'HMM Regime', desc: 'Hidden Markov states and macro regimes' },
  { id: 'quality', name: 'PIT Audit & Quality', desc: 'Data lineage, filing dates, and QA flags' },
];

export function DailyStockPanel({ onSelectTickerForChart }) {
  const [universe, setUniverse] = useState(DEFAULT_TICKERS);
  const [selectedTicker, setSelectedTicker] = useState('AAPL');
  const [startDate, setStartDate] = useState('2024-01-01');
  const [endDate, setEndDate] = useState('2025-12-31');
  const [limit, setLimit] = useState(25);
  const [page, setPage] = useState(0);

  const [panelData, setPanelData] = useState({ total: 0, rows: [], columns: [] });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [activeTab, setActiveTab] = useState('overview');
  const [selectedRow, setSelectedRow] = useState(null);

  // Load universe
  useEffect(() => {
    const loadUniverse = async () => {
      try {
        const data = await fetchUniverse();
        if (Array.isArray(data) && data.length > 0) {
          setUniverse(data.map(u => u.ticker || u));
        }
      } catch (e) {
        // keep default universe
      }
    };
    loadUniverse();
  }, []);

  // Fetch paginated panel data from DuckDB
  const loadPanel = async (targetPage = page) => {
    setLoading(true);
    setError(null);
    try {
      const offset = targetPage * limit;
      const res = await fetchDailyStockPanel({
        ticker: selectedTicker === 'ALL' ? '' : selectedTicker,
        start_date: startDate,
        end_date: endDate,
        limit,
        offset
      });
      setPanelData(res || { total: 0, rows: [], columns: [] });
      setPage(targetPage);

      // Default select first row if no row currently selected
      if (res.rows && res.rows.length > 0 && !selectedRow) {
        // Try finding AAPL on 2025-06-30 if present, else first row
        const targetRow = res.rows.find(r => r.date?.startsWith('2025-06-30')) || res.rows[0];
        setSelectedRow(targetRow);
      }
    } catch (err) {
      setError(err.message || 'Failed to query DuckDB daily stock panel table');
      setPanelData({ total: 0, rows: [], columns: [] });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadPanel(0);
  }, [selectedTicker, limit]);

  const handleApplyFilter = (e) => {
    if (e) e.preventDefault();
    loadPanel(0);
  };

  const totalPages = Math.ceil((panelData.total || 0) / limit);

  // News coverage: outside a provider's covered period every news field is NULL by design (never "0 news")
  const noCov = (row) => !row || row.news_status === 'NO_COVERAGE' || !row.news_status;
  const PROVIDER_LABEL = { fnspid: 'FNSPID', google_news_rss: 'Google News', finnhub: 'Finnhub' };
  const newsLabel = (row) => (noCov(row)
    ? 'no coverage'
    : `${PROVIDER_LABEL[row.news_provider] || row.news_provider || ''} · ${row.news_status === 'NEWS' ? 'news' : 'covered, no articles'}`);

  // Format cell display
  const fmt = (val, type = 'num', decimals = 2) => {
    if (val === null || val === undefined || val === '' || Number.isNaN(val)) return '—';
    if (typeof val === 'number') {
      if (type === 'pct') return `${(val * 100).toFixed(decimals)}%`;
      if (type === 'curr') return `$${val.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`;
      if (type === 'vol') return val >= 1e6 ? `${(val / 1e6).toFixed(1)}M` : val.toLocaleString();
      if (type === 'curr_large') return val >= 1e9 ? `$${(val / 1e9).toFixed(2)}B` : val >= 1e6 ? `$${(val / 1e6).toFixed(1)}M` : `$${val.toLocaleString()}`;
      return val.toFixed(decimals);
    }
    return String(val);
  };

  const getRegimeBadge = (label) => {
    const l = String(label || '').toLowerCase();
    if (l.includes('bull') && l.includes('low')) return 'bg-emerald-950/80 border-emerald-500/40 text-emerald-300';
    if (l.includes('bull') && l.includes('high')) return 'bg-cyan-950/80 border-cyan-500/40 text-cyan-300';
    if (l.includes('bear') && l.includes('high')) return 'bg-rose-950/80 border-rose-500/40 text-rose-300';
    if (l.includes('bear') && l.includes('low')) return 'bg-amber-950/80 border-amber-500/40 text-amber-300';
    return 'bg-blue-950/80 border-blue-500/40 text-blue-300';
  };

  return (
    <div id="quant-data" className="space-y-6">
      {/* Top Filter Bar */}
      <div className="bg-void-900/90 border border-white/10 rounded-2xl p-5 space-y-4 shadow-xl">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="p-1.5 rounded-lg bg-blue-950/80 border border-blue-500/30 text-cyan-400">
                <Database className="w-4 h-4" />
              </span>
              <h3 className="font-heading font-bold text-xl text-white">Daily Stock Panel & Quant Data</h3>
              <span className="text-xs font-mono text-cyan-300 bg-blue-950/80 border border-blue-500/30 px-2.5 py-0.5 rounded-full">
                DuckDB Unified Table
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Query 5,020 master panel records with 76 cross-domain analytical features directly from DuckDB.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            {/* Ticker Dropdown */}
            <div className="flex items-center gap-2 bg-black/40 border border-white/10 rounded-xl px-3 py-1.5">
              <span className="text-xs font-mono text-slate-400">Asset:</span>
              <select
                value={selectedTicker}
                onChange={(e) => {
                  setSelectedTicker(e.target.value);
                  if (onSelectTickerForChart && e.target.value !== 'ALL') {
                    onSelectTickerForChart(e.target.value);
                  }
                }}
                className="bg-transparent text-sm font-mono font-bold text-cyan-300 focus:outline-none cursor-pointer"
              >
                <option value="ALL" className="bg-void-950 text-white">ALL (10 Assets)</option>
                {universe.map(t => (
                  <option key={t} value={t} className="bg-void-950 text-white">{t}</option>
                ))}
              </select>
            </div>

            {/* Date Pickers */}
            <div className="flex items-center gap-1.5 bg-black/40 border border-white/10 rounded-xl px-3 py-1.5 text-xs font-mono">
              <span className="text-slate-400">From:</span>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="bg-transparent text-slate-200 focus:outline-none"
              />
              <span className="text-slate-500">to</span>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="bg-transparent text-slate-200 focus:outline-none"
              />
            </div>

            {/* Page Size */}
            <div className="flex items-center gap-1.5 bg-black/40 border border-white/10 rounded-xl px-3 py-1.5 text-xs font-mono">
              <span className="text-slate-400">Rows:</span>
              <select
                value={limit}
                onChange={(e) => setLimit(Number(e.target.value))}
                className="bg-transparent text-slate-200 focus:outline-none cursor-pointer"
              >
                <option value={25} className="bg-void-950 text-white">25</option>
                <option value={50} className="bg-void-950 text-white">50</option>
                <option value={100} className="bg-void-950 text-white">100</option>
              </select>
            </div>

            {/* Refresh / Query Button */}
            <Button
              onClick={() => handleApplyFilter()}
              disabled={loading}
              size="sm"
              className="bg-gradient-to-r from-blue-600 to-cyan-600 text-white hover:from-blue-500 hover:to-cyan-500 text-xs font-mono h-9"
            >
              <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${loading ? 'animate-spin' : ''}`} />
              Query Panel
            </Button>
          </div>
        </div>

        {/* Feature Group Tabs */}
        <div className="flex items-center gap-2 overflow-x-auto border-t border-white/10 pt-3 text-xs font-mono scrollbar-none">
          {FEATURE_TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-3 py-1.5 rounded-lg transition-all whitespace-nowrap flex items-center gap-1.5 ${
                activeTab === tab.id
                  ? 'bg-blue-600/30 border border-blue-500/50 text-white shadow-glow-blue'
                  : 'bg-black/20 border border-white/5 text-slate-400 hover:text-slate-200 hover:bg-white/5'
              }`}
            >
              <span>{tab.name}</span>
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-rose-950/30 border border-rose-500/30 text-rose-300 text-xs flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Main Table + Data Inspection Split Grid */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
        
        {/* Table Container (8 or 12 cols depending on selected row) */}
        <div className={`${selectedRow ? 'xl:col-span-8' : 'xl:col-span-12'} bg-void-900/90 border border-white/10 rounded-2xl overflow-hidden shadow-xl flex flex-col`}>
          {/* Table Header Bar */}
          <div className="p-4 border-b border-white/10 flex items-center justify-between bg-black/20">
            <div className="flex items-center gap-2 text-xs font-mono text-slate-300">
              <span className="w-2 h-2 rounded-full bg-cyan-400" />
              <span>
                Showing {panelData.rows.length} of {panelData.total?.toLocaleString() || 0} records
              </span>
              {selectedTicker !== 'ALL' && (
                <span className="text-cyan-400">({selectedTicker})</span>
              )}
            </div>
            <div className="text-[11px] font-mono text-slate-500">
              Click any row to open the full 76-feature point-in-time inspector
            </div>
          </div>

          {/* Table Scroll Area */}
          <div className="overflow-x-auto min-h-[350px]">
            <table className="w-full text-left text-xs font-mono border-collapse">
              <thead>
                <tr className="border-b border-white/10 bg-void-950/80 text-slate-400 text-[11px]">
                  <th className="py-3 px-3">Date</th>
                  <th className="py-3 px-3">Ticker</th>

                  {activeTab === 'overview' && (
                    <>
                      <th className="py-3 px-3 text-right">Close</th>
                      <th className="py-3 px-3 text-right">Mom 20D</th>
                      <th className="py-3 px-3 text-right">RSI 14</th>
                      <th className="py-3 px-3 text-right">Vol 20D</th>
                      <th className="py-3 px-3 text-right">ROE</th>
                      <th className="py-3 px-3 text-right">Rev Growth</th>
                      <th className="py-3 px-3 text-right">P/E</th>
                      <th className="py-3 px-3 text-right">P/B</th>
                      <th className="py-3 px-3 text-center">News</th>
                      <th className="py-3 px-3 text-right">Tone</th>
                      <th className="py-3 px-3">Regime</th>
                    </>
                  )}

                  {activeTab === 'market' && (
                    <>
                      <th className="py-3 px-3 text-right">Open</th>
                      <th className="py-3 px-3 text-right">High</th>
                      <th className="py-3 px-3 text-right">Low</th>
                      <th className="py-3 px-3 text-right">Close</th>
                      <th className="py-3 px-3 text-right">Adj Close</th>
                      <th className="py-3 px-3 text-right">Volume</th>
                      <th className="py-3 px-3 text-right">Return</th>
                    </>
                  )}

                  {activeTab === 'technical' && (
                    <>
                      <th className="py-3 px-3 text-right">RSI 14</th>
                      <th className="py-3 px-3 text-right">MACD</th>
                      <th className="py-3 px-3 text-right">Mom 20D</th>
                      <th className="py-3 px-3 text-right">Vol 20D</th>
                      <th className="py-3 px-3 text-right">SMA 20</th>
                      <th className="py-3 px-3 text-right">SMA 50</th>
                      <th className="py-3 px-3 text-right">SMA 200</th>
                      <th className="py-3 px-3 text-right">Vol Ratio</th>
                    </>
                  )}

                  {activeTab === 'fundamentals' && (
                    <>
                      <th className="py-3 px-3 text-right">Revenue</th>
                      <th className="py-3 px-3 text-right">Rev Growth</th>
                      <th className="py-3 px-3 text-right">Net Income</th>
                      <th className="py-3 px-3 text-right">ROE</th>
                      <th className="py-3 px-3 text-right">Profit Margin</th>
                      <th className="py-3 px-3 text-right">Debt/Equity</th>
                      <th className="py-3 px-3">Filing Date</th>
                      <th className="py-3 px-3">Form</th>
                    </>
                  )}

                  {activeTab === 'valuation' && (
                    <>
                      <th className="py-3 px-3 text-right">Close</th>
                      <th className="py-3 px-3 text-right">P/E Ratio</th>
                      <th className="py-3 px-3 text-right">P/B Ratio</th>
                      <th className="py-3 px-3 text-right">P/S Ratio</th>
                      <th className="py-3 px-3 text-right">Shares</th>
                      <th className="py-3 px-3 text-right">Equity</th>
                    </>
                  )}

                  {activeTab === 'news' && (
                    <>
                      <th className="py-3 px-3 text-center">News Count</th>
                      <th className="py-3 px-3 text-center">Positive</th>
                      <th className="py-3 px-3 text-center">Negative</th>
                      <th className="py-3 px-3 text-right">FinBERT Sentiment</th>
                      <th className="py-3 px-3 text-right">Decayed Sentiment</th>
                      <th className="py-3 px-3">Source / Status</th>
                    </>
                  )}

                  {activeTab === 'regime' && (
                    <>
                      <th className="py-3 px-3">Regime Label</th>
                      <th className="py-3 px-3 text-center">HMM State</th>
                      <th className="py-3 px-3 text-right">Bench Return</th>
                      <th className="py-3 px-3 text-right">Bench Mom 20D</th>
                      <th className="py-3 px-3 text-right">Bench Vol 20D</th>
                      <th className="py-3 px-3">Method</th>
                    </>
                  )}

                  {activeTab === 'quality' && (
                    <>
                      <th className="py-3 px-3">Status</th>
                      <th className="py-3 px-3">Source</th>
                      <th className="py-3 px-3">Filing Date</th>
                      <th className="py-3 px-3">Period End</th>
                      <th className="py-3 px-3">Downloaded At</th>
                      <th className="py-3 px-3">Version</th>
                    </>
                  )}

                  <th className="py-3 px-3 text-center">Inspect</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5 text-slate-200">
                {panelData.rows.map((row, idx) => {
                  const isSelected = selectedRow && selectedRow.date === row.date && selectedRow.ticker === row.ticker;
                  return (
                    <tr
                      key={`${row.ticker}-${row.date}-${idx}`}
                      onClick={() => setSelectedRow(row)}
                      className={`hover:bg-blue-600/10 transition-colors cursor-pointer ${
                        isSelected ? 'bg-blue-900/30 ring-1 ring-cyan-500/50' : ''
                      }`}
                    >
                      <td className="py-2.5 px-3 font-semibold text-white whitespace-nowrap">
                        {row.date?.slice(0, 10)}
                      </td>
                      <td className="py-2.5 px-3">
                        <span className="px-2 py-0.5 rounded bg-black/40 border border-white/10 font-bold text-cyan-300">
                          {row.ticker}
                        </span>
                      </td>

                      {activeTab === 'overview' && (
                        <>
                          <td className="py-2.5 px-3 text-right text-cyan-300 font-semibold">{fmt(row.close, 'curr')}</td>
                          <td className={`py-2.5 px-3 text-right ${row.momentum_20d >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                            {fmt(row.momentum_20d, 'pct')}
                          </td>
                          <td className="py-2.5 px-3 text-right text-slate-300">{fmt(row.rsi_14, 'num', 1)}</td>
                          <td className="py-2.5 px-3 text-right text-purple-300">{fmt(row.volatility_20d, 'pct', 1)}</td>
                          <td className="py-2.5 px-3 text-right text-slate-300">{fmt(row.roe, 'pct')}</td>
                          <td className="py-2.5 px-3 text-right text-emerald-400">{fmt(row.revenue_growth, 'pct')}</td>
                          <td className="py-2.5 px-3 text-right text-slate-300">{fmt(row.pe_ratio, 'num', 1)}</td>
                          <td className="py-2.5 px-3 text-right text-slate-300">{fmt(row.pb_ratio, 'num', 2)}</td>
                          <td className="py-2.5 px-3 text-center">{noCov(row) ? <span className="text-slate-500 text-[10px]">no coverage</span> : (row.news_count ?? 0)}</td>
                          <td className={`py-2.5 px-3 text-right ${(row.avg_finbert_sentiment || 0) > 0 ? 'text-emerald-400' : (row.avg_finbert_sentiment || 0) < 0 ? 'text-rose-400' : 'text-slate-400'}`}>
                            {noCov(row) ? <span className="text-slate-500 text-[10px]">no coverage</span> : fmt(row.avg_finbert_sentiment, 'num', 2)}
                          </td>
                          <td className="py-2.5 px-3 whitespace-nowrap">
                            <span className={`px-2 py-0.5 rounded text-[10px] border ${getRegimeBadge(row.market_regime)}`}>
                              {row.market_regime || `HMM ${row.hmm_state}`}
                            </span>
                          </td>
                        </>
                      )}

                      {activeTab === 'market' && (
                        <>
                          <td className="py-2.5 px-3 text-right">{fmt(row.open, 'curr')}</td>
                          <td className="py-2.5 px-3 text-right">{fmt(row.high, 'curr')}</td>
                          <td className="py-2.5 px-3 text-right">{fmt(row.low, 'curr')}</td>
                          <td className="py-2.5 px-3 text-right text-cyan-300 font-semibold">{fmt(row.close, 'curr')}</td>
                          <td className="py-2.5 px-3 text-right">{fmt(row.adj_close, 'curr')}</td>
                          <td className="py-2.5 px-3 text-right">{fmt(row.volume, 'vol')}</td>
                          <td className={`py-2.5 px-3 text-right ${row.daily_return >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                            {fmt(row.daily_return, 'pct')}
                          </td>
                        </>
                      )}

                      {activeTab === 'technical' && (
                        <>
                          <td className="py-2.5 px-3 text-right text-cyan-300">{fmt(row.rsi_14, 'num', 1)}</td>
                          <td className="py-2.5 px-3 text-right">{fmt(row.macd, 'num', 3)}</td>
                          <td className="py-2.5 px-3 text-right">{fmt(row.momentum_20d, 'pct')}</td>
                          <td className="py-2.5 px-3 text-right text-purple-300">{fmt(row.volatility_20d, 'pct', 1)}</td>
                          <td className="py-2.5 px-3 text-right text-amber-300">{fmt(row.sma_20, 'curr')}</td>
                          <td className="py-2.5 px-3 text-right text-emerald-300">{fmt(row.sma_50, 'curr')}</td>
                          <td className="py-2.5 px-3 text-right text-purple-300">{fmt(row.sma_200, 'curr')}</td>
                          <td className="py-2.5 px-3 text-right">{fmt(row.volume_ratio_20d, 'num', 2)}</td>
                        </>
                      )}

                      {activeTab === 'fundamentals' && (
                        <>
                          <td className="py-2.5 px-3 text-right">{fmt(row.revenue, 'curr_large')}</td>
                          <td className="py-2.5 px-3 text-right text-emerald-400">{fmt(row.revenue_growth, 'pct')}</td>
                          <td className="py-2.5 px-3 text-right">{fmt(row.net_income, 'curr_large')}</td>
                          <td className="py-2.5 px-3 text-right">{fmt(row.roe, 'pct')}</td>
                          <td className="py-2.5 px-3 text-right">{fmt(row.profit_margin, 'pct')}</td>
                          <td className="py-2.5 px-3 text-right">{fmt(row.debt_to_equity, 'num', 2)}</td>
                          <td className="py-2.5 px-3">{row.fundamental_filing_date?.slice(0, 10) || '—'}</td>
                          <td className="py-2.5 px-3">{row.fundamental_form || '—'}</td>
                        </>
                      )}

                      {activeTab === 'valuation' && (
                        <>
                          <td className="py-2.5 px-3 text-right text-cyan-300">{fmt(row.close, 'curr')}</td>
                          <td className="py-2.5 px-3 text-right">{fmt(row.pe_ratio, 'num', 2)}</td>
                          <td className="py-2.5 px-3 text-right">{fmt(row.pb_ratio, 'num', 2)}</td>
                          <td className="py-2.5 px-3 text-right">{fmt(row.ps_ratio, 'num', 2)}</td>
                          <td className="py-2.5 px-3 text-right">{fmt(row.shares, 'vol')}</td>
                          <td className="py-2.5 px-3 text-right">{fmt(row.shareholders_equity, 'curr_large')}</td>
                        </>
                      )}

                      {activeTab === 'news' && (
                        <>
                          <td className="py-2.5 px-3 text-center">{noCov(row) ? '—' : (row.news_count ?? 0)}</td>
                          <td className="py-2.5 px-3 text-center text-emerald-400">{noCov(row) ? '—' : (row.positive_news_count ?? 0)}</td>
                          <td className="py-2.5 px-3 text-center text-rose-400">{noCov(row) ? '—' : (row.negative_news_count ?? 0)}</td>
                          <td className="py-2.5 px-3 text-right">{fmt(row.avg_finbert_sentiment, 'num', 2)}</td>
                          <td className="py-2.5 px-3 text-right">{fmt(row.sent_decay, 'num', 2)}</td>
                          <td className="py-2.5 px-3 text-slate-400 whitespace-nowrap">{newsLabel(row)}</td>
                        </>
                      )}

                      {activeTab === 'regime' && (
                        <>
                          <td className="py-2.5 px-3">
                            <span className={`px-2 py-0.5 rounded text-[10px] border ${getRegimeBadge(row.market_regime)}`}>
                              {row.market_regime || `HMM ${row.hmm_state}`}
                            </span>
                          </td>
                          <td className="py-2.5 px-3 text-center font-bold text-cyan-300">State {row.hmm_state}</td>
                          <td className="py-2.5 px-3 text-right">{fmt(row.benchmark_return, 'pct')}</td>
                          <td className="py-2.5 px-3 text-right">{fmt(row.benchmark_momentum_20d, 'pct')}</td>
                          <td className="py-2.5 px-3 text-right text-purple-300">{fmt(row.benchmark_volatility_20d, 'pct')}</td>
                          <td className="py-2.5 px-3 text-slate-400">{row.regime_method || 'HMM+Rules'}</td>
                        </>
                      )}

                      {activeTab === 'quality' && (
                        <>
                          <td className="py-2.5 px-3">
                            <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-950/80 border border-emerald-500/40 text-emerald-300">
                              {row.quality_status || 'PASS'}
                            </span>
                          </td>
                          <td className="py-2.5 px-3 text-slate-400">{row.source || 'yfinance/sec'}</td>
                          <td className="py-2.5 px-3">{row.fundamental_filing_date?.slice(0, 10) || '—'}</td>
                          <td className="py-2.5 px-3">{row.fundamental_period_end?.slice(0, 10) || '—'}</td>
                          <td className="py-2.5 px-3 text-slate-400">{row.downloaded_at?.slice(0, 19) || '—'}</td>
                          <td className="py-2.5 px-3 text-slate-400">{row.dataset_version || 'v1.0.0'}</td>
                        </>
                      )}

                      <td className="py-2.5 px-3 text-center">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedRow(row);
                          }}
                          className="p-1 rounded hover:bg-blue-600/20 text-cyan-400 transition-colors"
                          title="View 76-feature Point-in-Time Snapshot"
                        >
                          <Eye className="w-3.5 h-3.5" />
                        </button>
                      </td>
                    </tr>
                  );
                })}

                {panelData.rows.length === 0 && !loading && (
                  <tr>
                    <td colSpan="14" className="py-12 text-center text-slate-400">
                      No records found for the selected query filters.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination Controls Footer */}
          <div className="p-4 border-t border-white/10 bg-black/30 flex items-center justify-between text-xs font-mono">
            <div className="text-slate-400">
              Page <span className="text-white font-bold">{page + 1}</span> of <span className="text-white font-bold">{Math.max(1, totalPages)}</span>
            </div>

            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => loadPanel(page - 1)}
                disabled={page <= 0 || loading}
                className="h-8 text-xs font-mono border-white/10 text-slate-300"
              >
                <ChevronLeft className="w-3.5 h-3.5 mr-1" />
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => loadPanel(page + 1)}
                disabled={page >= totalPages - 1 || loading}
                className="h-8 text-xs font-mono border-white/10 text-slate-300"
              >
                Next
                <ChevronRight className="w-3.5 h-3.5 ml-1" />
              </Button>
            </div>
          </div>
        </div>

        {/* SECTION 5: DATA INSPECTION SNAPSHOT PANEL */}
        {selectedRow && (
          <div className="xl:col-span-4 bg-void-900/95 border border-cyan-500/30 rounded-2xl p-5 space-y-5 shadow-2xl relative flex flex-col justify-between">
            <div className="space-y-4">
              {/* Snapshot Header */}
              <div className="flex items-start justify-between border-b border-white/10 pb-3">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="px-2.5 py-0.5 rounded-md bg-blue-950/80 border border-blue-500/40 text-sm font-mono font-bold text-cyan-300">
                      {selectedRow.ticker}
                    </span>
                    <span className="text-xs font-mono text-slate-300">
                      {selectedRow.date?.slice(0, 10)}
                    </span>
                  </div>
                  <h4 className="font-heading font-bold text-white text-base">
                    Point-in-Time Snapshot
                  </h4>
                </div>
                <button
                  onClick={() => setSelectedRow(null)}
                  className="p-1 text-slate-400 hover:text-white rounded-lg hover:bg-white/10 transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* REGIME */}
              <div className="p-3 rounded-xl bg-black/40 border border-white/5 space-y-1.5 text-xs font-mono">
                <div className="text-[10px] text-slate-400 font-bold uppercase tracking-wider flex items-center justify-between">
                  <span>MARKET REGIME</span>
                  <span className="text-cyan-400">HMM State {selectedRow.hmm_state}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold border ${getRegimeBadge(selectedRow.market_regime)}`}>
                    {selectedRow.market_regime || 'Bull / Low Volatility'}
                  </span>
                  <span className="text-slate-400 text-[11px]">{selectedRow.regime_method || 'HMM+Rules'}</span>
                </div>
              </div>

              {/* TECHNICAL */}
              <div className="p-3 rounded-xl bg-black/40 border border-white/5 space-y-2 text-xs font-mono">
                <div className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">
                  TECHNICAL INDICATORS
                </div>
                <div className="grid grid-cols-2 gap-2 text-[11px]">
                  <div className="flex justify-between border-b border-white/5 pb-1">
                    <span className="text-slate-400">Close Price:</span>
                    <span className="text-cyan-300 font-bold">{fmt(selectedRow.close, 'curr')}</span>
                  </div>
                  <div className="flex justify-between border-b border-white/5 pb-1">
                    <span className="text-slate-400">RSI (14):</span>
                    <span className="text-slate-100">{fmt(selectedRow.rsi_14, 'num', 1)}</span>
                  </div>
                  <div className="flex justify-between border-b border-white/5 pb-1">
                    <span className="text-slate-400">Momentum 20D:</span>
                    <span className={selectedRow.momentum_20d >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                      {fmt(selectedRow.momentum_20d, 'pct')}
                    </span>
                  </div>
                  <div className="flex justify-between border-b border-white/5 pb-1">
                    <span className="text-slate-400">Volatility 20D:</span>
                    <span className="text-purple-300">{fmt(selectedRow.volatility_20d, 'pct', 1)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">MACD / Signal:</span>
                    <span className="text-slate-200">{fmt(selectedRow.macd, 'num', 2)} / {fmt(selectedRow.macd_signal, 'num', 2)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">SMA 20/50/200:</span>
                    <span className="text-slate-200">${fmt(selectedRow.sma_20, 'num', 0)}/${fmt(selectedRow.sma_50, 'num', 0)}/${fmt(selectedRow.sma_200, 'num', 0)}</span>
                  </div>
                </div>
              </div>

              {/* FUNDAMENTALS */}
              <div className="p-3 rounded-xl bg-black/40 border border-white/5 space-y-2 text-xs font-mono">
                <div className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">
                  FUNDAMENTALS (PIT)
                </div>
                <div className="grid grid-cols-2 gap-2 text-[11px]">
                  <div className="flex justify-between border-b border-white/5 pb-1">
                    <span className="text-slate-400">Revenue Growth:</span>
                    <span className="text-emerald-400 font-bold">{fmt(selectedRow.revenue_growth, 'pct')}</span>
                  </div>
                  <div className="flex justify-between border-b border-white/5 pb-1">
                    <span className="text-slate-400">ROE:</span>
                    <span className="text-slate-200">{fmt(selectedRow.roe, 'pct')}</span>
                  </div>
                  <div className="flex justify-between border-b border-white/5 pb-1">
                    <span className="text-slate-400">Debt / Equity:</span>
                    <span className="text-slate-200">{fmt(selectedRow.debt_to_equity, 'num', 2)}</span>
                  </div>
                  <div className="flex justify-between border-b border-white/5 pb-1">
                    <span className="text-slate-400">EPS Growth:</span>
                    <span className="text-emerald-400">{fmt(selectedRow.eps_growth, 'pct')}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Cash Reserves:</span>
                    <span className="text-cyan-300">{fmt(selectedRow.cash, 'curr_large')}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Total Assets:</span>
                    <span className="text-slate-200">{fmt(selectedRow.total_assets, 'curr_large')}</span>
                  </div>
                </div>
              </div>

              {/* VALUATION */}
              <div className="p-3 rounded-xl bg-black/40 border border-white/5 space-y-2 text-xs font-mono">
                <div className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">
                  VALUATION MULTIPLES
                </div>
                <div className="grid grid-cols-3 gap-2 text-[11px]">
                  <div className="bg-black/40 p-2 rounded-lg text-center">
                    <div className="text-[10px] text-slate-500">P/E RATIO</div>
                    <div className="font-bold text-white mt-0.5">{fmt(selectedRow.pe_ratio, 'num', 1)}</div>
                  </div>
                  <div className="bg-black/40 p-2 rounded-lg text-center">
                    <div className="text-[10px] text-slate-500">P/B RATIO</div>
                    <div className="font-bold text-cyan-300 mt-0.5">{fmt(selectedRow.pb_ratio, 'num', 2)}</div>
                  </div>
                  <div className="bg-black/40 p-2 rounded-lg text-center">
                    <div className="text-[10px] text-slate-500">P/S RATIO</div>
                    <div className="font-bold text-white mt-0.5">{fmt(selectedRow.ps_ratio, 'num', 1)}</div>
                  </div>
                </div>
              </div>

              {/* NEWS & SENTIMENT */}
              <div className="p-3 rounded-xl bg-black/40 border border-white/5 space-y-2 text-xs font-mono">
                <div className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">
                  NEWS SENTIMENT
                </div>
                <div className="grid grid-cols-2 gap-2 text-[11px]">
                  <div className="flex justify-between">
                    <span className="text-slate-400">News Count:</span>
                    <span className="text-white font-bold">{noCov(selectedRow) ? 'no coverage' : (selectedRow.news_count ?? 0)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">FinBERT Sentiment:</span>
                    <span className={(selectedRow.avg_finbert_sentiment || 0) >= 0 ? 'text-emerald-400 font-bold' : 'text-rose-400 font-bold'}>
                      {noCov(selectedRow) ? 'no coverage' : fmt(selectedRow.avg_finbert_sentiment, 'num', 2)}
                    </span>
                  </div>
                </div>
              </div>

              {/* POINT-IN-TIME AUDIT & DATA QUALITY */}
              <div className="p-3 rounded-xl bg-blue-950/30 border border-blue-500/20 space-y-2 text-[11px] font-mono">
                <div className="text-[10px] text-cyan-400 font-bold uppercase tracking-wider flex items-center gap-1.5">
                  <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
                  <span>POINT-IN-TIME (PIT) LINEAGE</span>
                </div>
                <div className="space-y-1 text-slate-300">
                  <div className="flex justify-between">
                    <span className="text-slate-400">Market Status:</span>
                    <span className="text-emerald-400 font-bold">{selectedRow.quality_status || 'PASS'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Filing Date (SEC):</span>
                    <span className="text-cyan-300">{selectedRow.fundamental_filing_date?.slice(0, 10) || 'None (Pre-IPO/Unreported)'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Form & Period End:</span>
                    <span className="text-slate-200">{selectedRow.fundamental_form || '10-Q'} ({selectedRow.fundamental_period_end?.slice(0, 10) || 'N/A'})</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Latest News Timestamp:</span>
                    <span className="text-slate-200 truncate">{selectedRow.latest_news_timestamp ? String(selectedRow.latest_news_timestamp).slice(0, 19) : newsLabel(selectedRow)}</span>
                  </div>
                </div>
              </div>
            </div>

            <div className="pt-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  if (onSelectTickerForChart) {
                    onSelectTickerForChart(selectedRow.ticker);
                  }
                }}
                className="w-full text-xs font-mono border-cyan-500/40 text-cyan-300 hover:bg-cyan-950/40"
              >
                <TrendingUp className="w-3.5 h-3.5 mr-1.5" />
                Plot {selectedRow.ticker} in Market Chart
              </Button>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
