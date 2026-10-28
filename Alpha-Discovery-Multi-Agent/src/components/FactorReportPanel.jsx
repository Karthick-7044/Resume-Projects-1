import React, { useEffect, useState } from 'react';
import { FileText, CheckCircle2, XCircle, AlertTriangle, CornerDownRight, Info } from 'lucide-react';
import { fetchFactorReport } from '@/lib/api';

const num = (v, d = 2) => (v === null || v === undefined || Number.isNaN(v) ? '—' : Number(v).toFixed(d));
const pct = (v, d = 1) => (v === null || v === undefined ? '—' : `${(Number(v) * 100).toFixed(d)}%`);
const pv = (p) => (p === null || p === undefined ? '—' : p < 0.001 ? '<0.001' : Number(p).toFixed(3));
const STATUS = { PASS: 'text-emerald-400', WARN: 'text-amber-300', FAIL: 'text-rose-400' };

const GLOSSARY = [
  ['Rank IC', 'Correlation between today\'s ranking and tomorrow\'s returns. 0 = no skill; 0.02–0.05 is typical for real factors.'],
  ['t-stat', 'How many standard errors the average IC is from zero. Above about 2 is unlikely to be luck (before correction).'],
  ['Corrected p', 'Probability of a result this good by luck, corrected (Holm) for testing several factors. Below 0.05 = significant.'],
  ['Sharpe ratio', 'Yearly return divided by yearly volatility. Gross = before trading costs, net = after 10 bps per trade.'],
  ['Max drawdown', 'Worst fall from a previous peak of the strategy\'s value.'],
  ['Turnover', 'How many times per year the portfolio is traded in full; more turnover = more costs.'],
  ['FF5 + Mom alpha', 'Return left after removing exposure to market, size, value, profitability, investment and momentum factors.'],
  ['Novelty', 'Highest rank correlation with a known factor; above 0.5 would mean "a known factor in disguise".'],
];

function Equity({ points, testStart, validStart }) {
  if (!points?.length) return null;
  const w = 760, h = 160, vals = points.map((p) => p.equity);
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const x = (i) => 30 + (i / Math.max(points.length - 1, 1)) * (w - 40);
  const y = (v) => h - 15 - ((v - lo) / Math.max(hi - lo, 1e-9)) * (h - 30);
  const ti = points.findIndex((p) => p.date >= testStart);
  const d = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.equity).toFixed(1)}`).join(' ');
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-40" role="img" aria-label="Equity curve, net of costs">
      {ti > 0 && <rect x={x(ti)} y="5" width={w - 10 - x(ti)} height={h - 15} fill="rgba(34,211,238,0.07)" />}
      {ti > 0 && <text x={x(ti) + 6} y="17" className="fill-cyan-300" fontSize="11">test (never seen) from {testStart}</text>}
      <text x="34" y="17" className="fill-slate-500" fontSize="11">validation from {validStart}</text>
      <line x1="30" x2={w - 10} y1={y(1)} y2={y(1)} stroke="rgba(255,255,255,0.15)" strokeDasharray="4 4" />
      <path d={d} fill="none" stroke="#22d3ee" strokeWidth="1.8" />
    </svg>
  );
}

function Stat({ label, value, tone }) {
  return (
    <div className="rounded-xl bg-black/30 border border-white/10 px-3 py-2">
      <div className="text-[10px] font-mono text-slate-500">{label}</div>
      <div className={`text-sm font-mono font-bold ${tone || 'text-white'}`}>{value}</div>
    </div>
  );
}

function VerdictBadge({ text }) {
  const good = /profitable after costs/.test(text) && !/not yet/.test(text);
  const sig = /Significant/.test(text);
  const I = good ? CheckCircle2 : sig ? AlertTriangle : XCircle;
  const tone = good ? 'border-emerald-500/40 text-emerald-300 bg-emerald-950/30' : sig ? 'border-amber-500/40 text-amber-200 bg-amber-950/30' : 'border-rose-500/40 text-rose-300 bg-rose-950/30';
  return <div className={`flex items-start gap-2 rounded-xl border px-3 py-2 text-sm ${tone}`}><I className="w-4 h-4 mt-0.5 shrink-0" />{text}</div>;
}

function FactorCard({ c, summary }) {
  const t = c.test;
  const shares = Object.entries(c.attribution || {}).sort((a, b) => b[1] - a[1]);
  return (
    <div className="glass-card rounded-3xl p-6 border border-white/15 space-y-4">
      <div className="space-y-1">
        <h4 className="font-heading text-lg font-bold text-white">{c.title || 'LLM factor'}</h4>
        <div className="flex flex-wrap gap-1.5 text-[10px] font-mono">
          {c.data_types.map((d) => <span key={d} className="px-2 py-0.5 rounded border border-cyan-500/30 text-cyan-300">{d}</span>)}
          <span className="px-2 py-0.5 rounded border border-purple-500/40 text-purple-300">{c.model}</span>
        </div>
      </div>
      <VerdictBadge text={c.verdict} />
      <div className="grid lg:grid-cols-2 gap-4 text-sm">
        <div className="space-y-2">
          <p className="text-slate-300"><b className="text-white">The idea: </b>{c.hypothesis}</p>
          {c.literature && <p className="text-xs text-slate-500">Builds on: {c.literature}</p>}
          <p className="text-slate-300"><b className="text-white">What the portfolio does: </b>{c.what_it_does}</p>
          <code className="block text-xs text-cyan-200 bg-black/40 rounded-lg p-2 break-all">{c.formula}</code>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          <Stat label="Rank IC (test)" value={num(t.rank_ic, 4)} tone={t.rank_ic > 0 ? 'text-emerald-400' : 'text-rose-400'} />
          <Stat label="t-stat" value={num(t.rank_ic_t)} />
          <Stat label="Corrected p" value={pv(t.p_ic_holm)} tone={t.p_ic_holm < 0.05 ? 'text-emerald-400' : ''} />
          <Stat label="Gross Sharpe" value={num(t.gross_sharpe)} />
          <Stat label="Net Sharpe (10 bps)" value={num(t.net_sharpe)} tone={t.net_sharpe > 0 ? 'text-emerald-400' : 'text-rose-400'} />
          <Stat label="Net return / year" value={pct(t.net_ann_return)} />
          <Stat label="Max drawdown" value={pct(t.max_drawdown)} tone="text-rose-300" />
          <Stat label="Turnover / year" value={`${num(t.turnover, 1)}×`} />
          <Stat label="FF5+Mom alpha / yr (t)" value={t.ff?.alpha_ann !== undefined ? `${pct(t.ff.alpha_ann)} (${num(t.ff.alpha_t)})` : '—'} />
          <Stat label="Novelty: max corr" value={`${num(t.novelty?.max_abs_corr)} ${t.novelty?.closest ? `(${String(t.novelty.closest).slice(0, 18)})` : ''}`} />
        </div>
      </div>
      <Equity points={t.equity} testStart={summary.test_window[0]} validStart={summary.validation_window[0]} />
      <div className="grid lg:grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <div className="text-xs font-mono text-slate-400">Which data drives it (attribution, discovery period)</div>
          {shares.length ? shares.map(([d, s]) => (
            <div key={d} className="space-y-0.5">
              <div className="flex justify-between text-[11px] font-mono text-slate-300"><span>{d}</span><span>{pct(s, 0)}</span></div>
              <div className="h-2 rounded bg-white/5"><div className="h-2 rounded bg-cyan-500" style={{ width: `${s * 100}%` }} /></div>
            </div>
          )) : <p className="text-[11px] text-slate-500">No attribution recorded.</p>}
        </div>
        <div className="space-y-1">
          <div className="text-xs font-mono text-slate-400">Critic checks</div>
          <ul className="space-y-0.5 text-[11px] font-mono">
            {(c.critic_checks || []).map((k) => (
              <li key={k.check} className="flex gap-2"><span className={`w-10 shrink-0 ${STATUS[k.status] || ''}`}>{k.status}</span>
                <span className="text-slate-400 w-28 shrink-0">{k.check}</span><span className="text-slate-300">{k.detail}</span></li>
            ))}
          </ul>
        </div>
      </div>
      {c.refinements?.length > 0 && (
        <div className="space-y-1">
          <div className="text-xs font-mono text-slate-400">Refinement history (the Critic sent earlier versions back)</div>
          {c.refinements.map((r) => (
            <div key={r.formula} className="flex gap-2 text-[11px] font-mono text-slate-400"><CornerDownRight className="w-3.5 h-3.5 shrink-0 text-amber-300" />
              <span><code className="text-slate-300">{r.formula}</code> — {r.verdict}: {r.critique}</span></div>
          ))}
        </div>
      )}
    </div>
  );
}

export function FactorReportPanel() {
  const [r, setR] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => { fetchFactorReport().then(setR).catch((e) => setErr(e.message)); }, []);
  if (err) return <div className="glass-card rounded-3xl p-6 border border-white/15 text-xs font-mono text-rose-300">{err}</div>;
  if (!r) return <p className="text-xs font-mono text-slate-400">Loading factor report…</p>;
  const s = r.summary, cp = s.composite;
  return (
    <div className="space-y-6">
      <div className="glass-card rounded-3xl p-6 border border-white/15 space-y-4">
        <h3 className="font-heading text-xl font-bold text-white flex items-center gap-2"><FileText className="w-5 h-5 text-cyan-400" />Alpha Factor Report</h3>
        <p className="text-sm text-slate-300 max-w-4xl">
          Every factor written by the LLM agents and <b className="text-white">accepted by the Critic</b> ({s.n_accepted} so far), tested on
          data the agents never saw (<b className="text-white">{s.test_window[0]} to {s.test_window[1]}</b>, after the models' knowledge cutoff;
          data available to {s.panel_end}). All rules were fixed before this period was looked at.
        </p>
        {cp && (
          <div className="space-y-2">
            <div className="text-xs font-mono text-slate-400">Equal-weight composite of all accepted LLM factors</div>
            <VerdictBadge text={cp.verdict} />
            <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2">
              <Stat label="Rank IC" value={num(cp.rank_ic, 4)} /><Stat label="t-stat" value={num(cp.rank_ic_t)} /><Stat label="p (one-sided)" value={pv(cp.p_ic)} />
              <Stat label="Gross Sharpe" value={num(cp.gross_sharpe)} /><Stat label="Net Sharpe" value={num(cp.net_sharpe)} />
              <Stat label="Net return / yr" value={pct(cp.net_ann_return)} /><Stat label="Max drawdown" value={pct(cp.max_drawdown)} />
              <Stat label="FF5+Mom alpha (t)" value={cp.ff?.alpha_ann !== undefined ? `${pct(cp.ff.alpha_ann)} (${num(cp.ff.alpha_t)})` : '—'} />
            </div>
          </div>
        )}
        <details className="text-xs text-slate-400">
          <summary className="cursor-pointer flex items-center gap-1.5 text-slate-300"><Info className="w-3.5 h-3.5" />What do these terms mean?</summary>
          <dl className="mt-2 grid md:grid-cols-2 gap-x-6 gap-y-1.5">
            {GLOSSARY.map(([k, v]) => <div key={k}><dt className="text-white font-semibold">{k}</dt><dd>{v}</dd></div>)}
          </dl>
        </details>
      </div>
      {r.factors.map((c) => <FactorCard key={c.formula} c={c} summary={s} />)}
    </div>
  );
}
