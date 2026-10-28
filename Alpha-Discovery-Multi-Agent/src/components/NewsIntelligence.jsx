import React, { useEffect, useMemo, useState } from 'react';
import { Newspaper, AlertTriangle, RefreshCw, ExternalLink, ChevronDown, ChevronRight } from 'lucide-react';
import { fetchNewsArticles, fetchNewsCoverage, fetchNewsData, fetchNewsQuality } from '@/lib/api';

const num = (v, d = 2) => (v === null || v === undefined ? '—' : Number(v).toFixed(d));
const tone = (v) => (v === null || v === undefined ? 'text-slate-500' : v > 0.05 ? 'text-emerald-400' : v < -0.05 ? 'text-rose-400' : 'text-slate-300');
const PROVIDER = { fnspid: 'FNSPID', google_news_rss: 'Google News', finnhub: 'Finnhub' };
const RANGES = [
  { id: 'fnspid', label: 'FNSPID 2013–2023', start: '2013-01-01', end: '2023-12-31' },
  { id: 'recent', label: 'Google News 2024–2026', start: '2024-01-01', end: '2026-12-31' },
  { id: 'all', label: 'All years', start: '2013-01-01', end: '2026-12-31' },
  { id: 'latest', label: 'Latest', start: undefined, end: undefined },
];

function SentimentChart({ rows }) {
  const pts = (rows || []).filter((r) => r.sent_decay !== null && r.sent_decay !== undefined);
  if (pts.length < 2) return <p className="text-xs font-mono text-slate-500">No daily FinBERT sentiment in this range (outside news coverage).</p>;
  const w = 760, h = 120;
  const x = (i) => 30 + (i / (pts.length - 1)) * (w - 40);
  const y = (v) => h / 2 - v * (h / 2 - 8);
  const d = pts.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.sent_decay).toFixed(1)}`).join(' ');
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-28" role="img" aria-label="Daily decayed FinBERT sentiment">
      <line x1="30" x2={w - 10} y1={h / 2} y2={h / 2} stroke="rgba(255,255,255,0.15)" strokeDasharray="4 4" />
      <text x="2" y="12" fontSize="10" className="fill-slate-500">+1</text>
      <text x="2" y={h - 2} fontSize="10" className="fill-slate-500">−1</text>
      <path d={d} fill="none" stroke="#22d3ee" strokeWidth="1.2" />
      <text x="34" y={h - 4} fontSize="10" className="fill-slate-500">{String(pts[0].date).slice(0, 10)}</text>
      <text x={w - 80} y={h - 4} fontSize="10" className="fill-slate-500">{String(pts[pts.length - 1].date).slice(0, 10)}</text>
    </svg>
  );
}

export function NewsIntelligence() {
  const [ticker, setTicker] = useState('AAPL');
  const [range, setRange] = useState(RANGES[0]);
  const [articles, setArticles] = useState([]);
  const [daily, setDaily] = useState([]);
  const [coverage, setCoverage] = useState({ coverage: [], status_days: [] });
  const [quality, setQuality] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showCoverage, setShowCoverage] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchNewsCoverage(), fetchNewsQuality()])
      .then(([cov, q]) => { if (!cancelled) { setCoverage(cov); setQuality(q.rows || []); } })
      .catch((err) => !cancelled && setError(err.message));
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      fetchNewsArticles({ ticker, limit: 60, start_date: range.start, end_date: range.end }),
      fetchNewsData(ticker, { limit: 2000 }),
    ])
      .then(([res, d]) => {
        if (cancelled) return;
        setArticles(res.rows || []);
        const rows = Array.isArray(d) ? d : [];
        setDaily(rows.filter((r) => (!range.start || r.date >= range.start) && (!range.end || r.date <= range.end)));
      })
      .catch((err) => !cancelled && setError(err.message))
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
  }, [ticker, range]);

  const tickers = useMemo(() => [...new Set((coverage.coverage || []).map((c) => c.ticker))].sort(), [coverage]);
  const statusByTicker = {};
  (coverage.status_days || []).forEach((r) => { statusByTicker[r.ticker] = { ...(statusByTicker[r.ticker] || {}), [r.news_status]: r.days }; });
  const qualityByTicker = Object.fromEntries(quality.map((q) => [`${q.ticker}|${q.provider}`, q]));
  const scored = articles.filter((a) => a.finbert_status === 'OK');
  const avg = scored.length ? scored.reduce((s, a) => s + a.finbert_score, 0) / scored.length : null;

  return (
    <div className="space-y-6">
      <div className="glass-card rounded-3xl p-6 border border-white/15 space-y-4">
        <div className="flex items-center gap-3">
          <Newspaper className="w-5 h-5 text-cyan-400" />
          <h3 className="font-heading text-xl font-bold text-white">Headlines & FinBERT sentiment</h3>
        </div>
        <p className="text-xs text-slate-400">
          Every headline is scored by FinBERT: score = P(positive) − P(negative), from −1 (very negative) to +1 (very positive).
          Sources: FNSPID 2013–2023, a Google News headline sample 2024–2026 and Finnhub (recent). A headline counts from the
          first trading day after it was published (16:00 New York cut-off). Days outside coverage are empty on purpose, never "0 news".
        </p>
        <div className="flex flex-wrap items-center gap-2 text-xs font-mono">
          <label className="text-slate-400" htmlFor="news-ticker">Stock:</label>
          <select id="news-ticker" value={ticker} onChange={(e) => setTicker(e.target.value)}
            className="bg-black/40 border border-white/10 rounded-lg px-2 py-1 text-cyan-200">
            {(tickers.length ? tickers : ['AAPL']).map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <span className="text-slate-400 ml-2">Period:</span>
          {RANGES.map((r) => (
            <button key={r.id} onClick={() => setRange(r)}
              className={`px-3 py-1 rounded-lg ${range.id === r.id ? 'bg-cyan-500 text-black font-bold' : 'bg-black/30 border border-white/10 text-slate-300 hover:text-white'}`}>
              {r.label}
            </button>
          ))}
          {loading && <RefreshCw className="w-4 h-4 text-cyan-400 animate-spin ml-1" />}
        </div>
        {error && <div className="flex items-center gap-2 text-xs text-rose-300 font-mono"><AlertTriangle className="w-4 h-4" /> {error}</div>}
        <div className="space-y-1">
          <div className="text-xs font-mono text-slate-400">Daily FinBERT sentiment for {ticker} (time-decayed, half-life 3 days)</div>
          <SentimentChart rows={daily} />
        </div>
        <div className="text-xs font-mono text-slate-400">
          {articles.length} most recent headlines in this period · {scored.length} scored · average FinBERT{' '}
          <span className={tone(avg)}>{num(avg, 3)}</span>
        </div>
        <div className="overflow-x-auto max-h-[560px] overflow-y-auto">
          <table className="w-full text-xs font-mono">
            <thead className="text-slate-400 border-b border-white/10 sticky top-0 bg-void-950">
              <tr>
                <th className="py-2 px-3 text-left">Published</th>
                <th className="py-2 px-3 text-left">Headline</th>
                <th className="py-2 px-3 text-left">Source</th>
                <th className="py-2 px-3 text-right">FinBERT</th>
              </tr>
            </thead>
            <tbody>
              {articles.map((a) => (
                <tr key={`${a.article_id}-${a.ticker}`} className="border-b border-white/5 text-slate-200">
                  <td className="py-2 px-3 whitespace-nowrap text-slate-400">{String(a.published_at).slice(0, 10)}</td>
                  <td className="py-2 px-3 max-w-xl">
                    <a href={a.url} target="_blank" rel="noopener noreferrer" className="hover:text-cyan-300 inline-flex items-start gap-1">
                      <span>{a.title}</span><ExternalLink className="w-3 h-3 mt-0.5 shrink-0 opacity-60" />
                    </a>
                  </td>
                  <td className="py-2 px-3 text-slate-400 whitespace-nowrap">{PROVIDER[a.provider] || a.provider}</td>
                  <td className={`py-2 px-3 text-right whitespace-nowrap ${tone(a.finbert_score)}`}>
                    {a.finbert_status === 'OK' ? `${num(a.finbert_score)} (${a.finbert_label})` : a.finbert_status}
                  </td>
                </tr>
              ))}
              {!loading && articles.length === 0 && (
                <tr><td colSpan={4} className="py-4 px-3 text-slate-500">No headlines for {ticker} in this period.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="glass-card rounded-3xl p-6 border border-white/15 space-y-3">
        <button onClick={() => setShowCoverage(!showCoverage)} className="w-full flex items-center justify-between text-left">
          <h3 className="font-heading text-lg font-bold text-white">News Archive Coverage & Quality ({tickers.length} stocks)</h3>
          {showCoverage ? <ChevronDown className="w-4 h-4 text-slate-400" /> : <ChevronRight className="w-4 h-4 text-slate-400" />}
        </button>
        {showCoverage && (
          <div className="overflow-x-auto max-h-[520px] overflow-y-auto">
            <table className="w-full text-xs font-mono">
              <thead className="text-slate-400 border-b border-white/10 sticky top-0 bg-void-950">
                <tr>
                  {['Ticker', 'Provider', 'Articles', 'FinBERT scored', 'Avg FinBERT', 'Covered from', 'Covered to', 'Days w/ news', 'Covered, none', 'No coverage'].map((h) => (
                    <th key={h} className="py-2 px-3 text-right first:text-left">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(coverage.coverage || []).map((c) => {
                  const q = qualityByTicker[`${c.ticker}|${c.provider}`] || {};
                  const s = statusByTicker[c.ticker] || {};
                  return (
                    <tr key={`${c.ticker}-${c.provider}`} className="border-b border-white/5 text-slate-200 cursor-pointer hover:bg-white/5"
                      onClick={() => setTicker(c.ticker)}>
                      <td className="py-2 px-3 font-bold text-cyan-300">{c.ticker}</td>
                      <td className="py-2 px-3 text-right text-slate-400">{PROVIDER[c.provider] || c.provider}</td>
                      <td className="py-2 px-3 text-right">{q.articles ?? '—'}</td>
                      <td className="py-2 px-3 text-right">{q.finbert_scored ?? '—'}</td>
                      <td className={`py-2 px-3 text-right ${tone(q.avg_finbert_sentiment)}`}>{num(q.avg_finbert_sentiment, 3)}</td>
                      <td className="py-2 px-3 text-right">{String(c.coverage_start || '').slice(0, 10)}</td>
                      <td className="py-2 px-3 text-right">{String(c.coverage_end || '').slice(0, 10)}</td>
                      <td className="py-2 px-3 text-right text-emerald-300">{s.NEWS ?? 0}</td>
                      <td className="py-2 px-3 text-right">{s.NO_ARTICLES ?? 0}</td>
                      <td className="py-2 px-3 text-right text-amber-300">{s.NO_COVERAGE ?? 0}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
