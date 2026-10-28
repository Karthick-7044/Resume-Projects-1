import React, { useEffect, useState } from 'react';
import { ArrowRight, Database, Newspaper, Brain, Code2, ShieldCheck, LineChart, Search, Archive, CheckCircle2, XCircle } from 'lucide-react';
import { fetchAlphaSummary, fetchPostCutoff } from '@/lib/api';

const num = (v, d = 4) => (v === null || v === undefined ? '—' : Number(v).toFixed(d));
const pv = (p) => (p === null || p === undefined ? '—' : p < 0.001 ? '<0.001' : Number(p).toFixed(3));

const DATA = [
  { icon: Database, title: 'Prices', text: 'Daily OHLCV 2012–Oct 2026 (Yahoo Finance) → momentum, volatility, RSI, moving averages' },
  { icon: Archive, title: 'Company accounts', text: 'SEC EDGAR filings as first reported, usable the day after filing → ROE, margins, growth, valuation' },
  { icon: Newspaper, title: 'News + FinBERT', text: 'FNSPID headlines 2013–2023 and a Google News sample 2024–Oct 2026, scored positive/negative by FinBERT' },
  { icon: LineChart, title: 'Market regime & macro', text: 'Bull / Bear / High-volatility label from an HMM using only past data; rates, VIX, yield curve (FRED)' },
];

const LOOP = [
  { icon: Search, title: 'Research agent', text: 'Reads an anonymised summary of all data (no tickers, no dates) and proposes an economic idea' },
  { icon: Code2, title: 'Quant agent', text: 'Turns the idea into a formula, e.g. cs_rank(momentum_252_21d) + cs_rank(roe)' },
  { icon: ShieldCheck, title: 'Validator', text: 'Rejects unsafe formulas: unknown features, future data, labels, unusable coverage' },
  { icon: LineChart, title: 'Backtester', text: 'Long top-ranked / short bottom-ranked stocks, next-day returns, 10 bps per trade' },
  { icon: Brain, title: 'Attribution', text: 'Removes one input at a time to see which data the formula really uses' },
  { icon: ShieldCheck, title: 'Critic agent', text: 'ACCEPT / REVISE / REJECT with reasons; failures go back to the Quant agent (max 2 refinements)' },
  { icon: Archive, title: 'Memory', text: 'Every attempt, reason and result is stored and fed into the next round' },
];

export function OverviewPanel({ onNavigate }) {
  const [s, setS] = useState(null);
  const [pc, setPc] = useState(null);
  useEffect(() => { fetchAlphaSummary().then(setS).catch(() => setS(null)); }, []);
  useEffect(() => { fetchPostCutoff().then(setPc).catch(() => setPc(null)); }, []);
  const PC_ROWS = [
    ['llm_v4_novel', 'LLM novel factors (Critic-accepted)'],
    ['llm_v4_all', 'All valid LLM formulas (no Critic)'],
    ['kb_composite', 'Built-in library (known factors)'],
  ];
  const big = s?.big;
  const comp = big?.wf_hold?.rules?.composite;
  const sig = big ? [
    ['Composite of all stable formulas', `${big.wf5.universe} stocks, 2016–23`, big.wf5.rules.composite],
    ['Composite of all stable formulas', `${big.wf5.universe} stocks, 2024–25 (never used before)`, big.wf_hold.rules.composite],
    ['Top-3 formulas', `${big.wf5.universe} stocks, 2016–23`, big.wf5.rules.naive],
    ['Five textbook factors', `${big.wf5.universe} stocks, 2016–23`, big.wf5.rules.literature],
  ] : [];

  return (
    <div className="space-y-6">
      <div className="glass-card rounded-3xl p-6 border border-white/15 space-y-3">
        <h3 className="font-heading text-2xl font-bold text-white">What this system does</h3>
        <p className="text-sm text-slate-300 leading-relaxed max-w-4xl">
          A team of AI agents searches for <strong className="text-white">alpha factors</strong> — formulas that rank stocks by how
          well they are likely to do next. Language models propose ideas and formulas; deterministic code checks them for
          look-ahead, backtests them with trading costs, explains them and decides whether they survive. Every number below is
          out of sample and corrected for testing many formulas.
        </p>
      </div>

      <div className="glass-card rounded-3xl p-6 border border-white/15 space-y-4">
        <h4 className="font-heading text-lg font-bold text-white">Data foundation (point-in-time)</h4>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {DATA.map(({ icon: I, title, text }) => (
            <div key={title} className="rounded-2xl bg-black/30 border border-white/10 p-4 space-y-1.5">
              <div className="flex items-center gap-2 text-cyan-300 text-sm font-semibold"><I className="w-4 h-4" />{title}</div>
              <p className="text-xs text-slate-400 leading-relaxed">{text}</p>
            </div>
          ))}
        </div>
        <p className="text-xs text-slate-500 font-mono">All joined into one table: one row per stock per day ({big ? `${big.wf5.universe} stocks` : '192 stocks'}, 714,401 rows).</p>
      </div>

      <div className="glass-card rounded-3xl p-6 border border-white/15 space-y-4">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <h4 className="font-heading text-lg font-bold text-white">The agent loop</h4>
          <button onClick={() => onNavigate('agents')} className="text-xs font-mono text-cyan-300 hover:text-white flex items-center gap-1">
            See every step live <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
        <div className="flex flex-wrap items-stretch gap-2">
          {LOOP.map(({ icon: I, title, text }, i) => (
            <React.Fragment key={title}>
              <div className="flex-1 min-w-[150px] rounded-2xl bg-black/30 border border-white/10 p-3 space-y-1">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-white"><I className="w-3.5 h-3.5 text-cyan-400" />{title}</div>
                <p className="text-[11px] text-slate-400 leading-snug">{text}</p>
              </div>
              {i < LOOP.length - 1 && <ArrowRight className="hidden xl:block w-4 h-4 text-slate-600 self-center" />}
            </React.Fragment>
          ))}
        </div>
      </div>

      <div className="glass-card rounded-3xl p-6 border border-white/15 space-y-4">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <h4 className="font-heading text-lg font-bold text-white">Key results (honest reading)</h4>
          <button onClick={() => onNavigate('results')} className="text-xs font-mono text-cyan-300 hover:text-white flex items-center gap-1">
            All results <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
        {!s && <p className="text-xs font-mono text-slate-500">Loading results…</p>}
        {s && (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-xs font-mono">
                <thead className="text-slate-400 border-b border-white/10">
                  <tr>{['Signal', 'Universe / period', 'Rank IC', 't (monthly)', 'Corrected p (Holm)', 'Beats random picks'].map((h) => <th key={h} className="py-2 px-3 text-left">{h}</th>)}</tr>
                </thead>
                <tbody>
                  {sig.map(([name, where, r]) => (
                    <tr key={name + where} className="border-b border-white/5">
                      <td className="py-2 px-3 text-white">{name}</td>
                      <td className="py-2 px-3 text-slate-300">{where}</td>
                      <td className="py-2 px-3 text-emerald-400">{num(r?.ic)}</td>
                      <td className="py-2 px-3">{num(r?.mt, 2)}</td>
                      <td className="py-2 px-3 text-emerald-400">{pv(r?.p_holm)}</td>
                      <td className="py-2 px-3">{r?.null_p !== undefined && r?.null_p !== null ? `${Math.round((1 - r.null_p) * 100)}% of 200` : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="grid md:grid-cols-2 gap-3 text-xs">
              <div className="rounded-2xl border border-emerald-500/30 bg-emerald-950/20 p-4 space-y-1">
                <div className="flex items-center gap-2 text-emerald-300 font-semibold"><CheckCircle2 className="w-4 h-4" />Significant</div>
                <p className="text-slate-300">The composite ranks stocks better than chance after correcting for every formula tried — including on
                  2024–25 data it never saw (IC {num(comp?.ic)}, corrected p {pv(comp?.p_holm)}).</p>
              </div>
              <div className="rounded-2xl border border-rose-500/30 bg-rose-950/20 p-4 space-y-1">
                <div className="flex items-center gap-2 text-rose-300 font-semibold"><XCircle className="w-4 h-4" />Not significant</div>
                <p className="text-slate-300">No portfolio earns a significant profit after 10 bps trading costs, and Fama-French + momentum explains
                  most of the signal. The strict Critic accepts no single formula.</p>
              </div>
            </div>
          </>
        )}
      </div>

      {pc && (
        <div className="glass-card rounded-3xl p-6 border border-white/15 space-y-4">
          <h4 className="font-heading text-lg font-bold text-white">Final test after the LLM's knowledge cutoff ({pc.test_window[0]} to {pc.test_window[1]})</h4>
          <p className="text-xs text-slate-400 max-w-4xl">The agents only saw data up to 2024. Every rule (novelty ≤ 0.5, positive validation Sharpe after
            costs, monthly rebalancing) was fixed before this period was opened. Corrected p = Holm over the four tests of the LLM novel signal.</p>
          <div className="overflow-x-auto">
            <table className="w-full text-xs font-mono">
              <thead className="text-slate-400 border-b border-white/10">
                <tr>{['Signal', 'Formulas', 'Rank IC (t)', 'New part: residual IC (t)', 'Long-short Sharpe gross / net', 'Long-only net Sharpe', 'FF5+Mom alpha (t)', 'Corrected p'].map((h) => <th key={h} className="py-2 px-3 text-left">{h}</th>)}</tr>
              </thead>
              <tbody>
                {PC_ROWS.filter(([k]) => pc.signals[k]).map(([k, label]) => {
                  const r = pc.signals[k];
                  const ff = r.ff_ls_net || {};
                  const h = r.holm ? Math.min(...Object.values(r.holm)) : null;
                  return (
                    <tr key={k} className="border-b border-white/5">
                      <td className="py-2 px-3 text-white">{label}</td>
                      <td className="py-2 px-3">{pc.n_formulas[k]}</td>
                      <td className="py-2 px-3">{num(r.rank_ic)} ({num(r.rank_ic_t, 2)})</td>
                      <td className="py-2 px-3">{num(r.residual_ic)} ({num(r.residual_ic_t, 2)})</td>
                      <td className="py-2 px-3">{num(r.ls_gross_sharpe, 2)} / {num(r.ls_net_sharpe, 2)}</td>
                      <td className="py-2 px-3">{num(r.lo_active_net_sharpe, 2)}</td>
                      <td className="py-2 px-3">{ff.alpha_ann !== undefined ? `${(ff.alpha_ann * 100).toFixed(1)}% (${num(ff.alpha_t, 2)})` : '—'}</td>
                      <td className="py-2 px-3">{h === null ? 'reference only' : pv(h)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="rounded-2xl border border-amber-500/30 bg-amber-950/20 p-4 text-xs text-slate-300">
            <span className="text-amber-300 font-semibold">Reading: </span>no LLM factor is significant after correction on this window. The Critic-accepted
            LLM factors do better than the unfiltered LLM output and the built-in known factors (positive net Sharpe where the others are ≤ 0),
            and their new part comes closest to significance — but 22 months is too short to confirm it.
          </div>
        </div>
      )}
    </div>
  );
}
