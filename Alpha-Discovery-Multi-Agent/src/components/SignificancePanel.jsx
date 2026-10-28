import React, { useEffect, useState } from 'react';
import { Sigma, LineChart } from 'lucide-react';
import { fetchAlphaSummary } from '@/lib/api';

const num = (v, d = 4) => (v === null || v === undefined ? '—' : Number(v).toFixed(d));
const pv = (p) => (p === null || p === undefined ? '—' : p < 0.001 ? '<0.001' : Number(p).toFixed(3));
const NAMES = { naive: 'Top-3 formulas', critic_v1: 'Stability rule', critic: 'Strict Critic (DSR ≥ 0.95)', composite: 'Composite (all stable)',
  literature: 'Five textbook factors', random: 'Random 3 (baseline)' };

function RuleTable({ title, wf, ca }) {
  if (!wf) return null;
  const best = (rule) => (ca?.rows || []).filter((r) => r.trial && r.variant.startsWith(`${rule}:`)).sort((a, b) => b.net_sh - a.net_sh)[0];
  return (
    <div className="space-y-2">
      <h5 className="text-sm font-semibold text-white">{title}</h5>
      <div className="overflow-x-auto">
        <table className="w-full text-xs font-mono">
          <thead className="text-slate-400 border-b border-white/10">
            <tr>{['Selection rule', 'Rank IC', 't (monthly)', 'Holm p', 'Random-null p', 'Best net Sharpe (after 10 bps)', 'Its Holm p'].map((h) => <th key={h} className="py-2 px-3 text-left">{h}</th>)}</tr>
          </thead>
          <tbody>
            {Object.entries(NAMES).map(([k, name]) => {
              const r = wf.rules?.[k];
              const b = best(k);
              return (
                <tr key={k} className="border-b border-white/5">
                  <td className="py-2 px-3 text-white">{name}</td>
                  {r ? (
                    <>
                      <td className={`py-2 px-3 ${r.ic > 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{num(r.ic)}</td>
                      <td className="py-2 px-3">{num(r.mt, 2)}</td>
                      <td className={`py-2 px-3 ${r.p_holm !== null && r.p_holm < 0.05 ? 'text-emerald-400' : ''}`}>{k === 'random' ? '—' : pv(r.p_holm)}</td>
                      <td className="py-2 px-3">{k === 'random' ? '—' : pv(r.null_p)}</td>
                    </>
                  ) : <td colSpan={4} className="py-2 px-3 text-slate-500">holds cash — no formula passed in any year</td>}
                  <td className="py-2 px-3">{b ? `${num(b.net_sh, 2)} (${b.variant.split(':')[1]})` : '—'}</td>
                  <td className="py-2 px-3">{b ? pv(b.p_holm) : '—'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function SignificancePanel() {
  const [s, setS] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => { fetchAlphaSummary().then(setS).catch((e) => setErr(e.message)); }, []);
  return (
    <div className="space-y-6">
      <div className="glass-card rounded-3xl p-6 border border-white/15 space-y-3">
        <h3 className="font-heading text-xl font-bold text-white flex items-center gap-2"><LineChart className="w-5 h-5 text-cyan-400" />How a formula is backtested</h3>
        <ol className="list-decimal pl-5 space-y-1.5 text-sm text-slate-300 max-w-5xl">
          <li><b className="text-white">Score:</b> each trading day the formula gives every stock a number using only data available at that day's close.</li>
          <li><b className="text-white">Rank and weight:</b> stocks are ranked; above-average ranks are bought, below-average ranks are sold short, with equal money on both sides (dollar-neutral).</li>
          <li><b className="text-white">Hold:</b> the portfolio earns the next day's return and is rebalanced every 5 (or 21/63) trading days; all rebalance days are averaged so no lucky day is picked.</li>
          <li><b className="text-white">Pay costs:</b> 10 bps (0.10%) per unit traded.</li>
          <li><b className="text-white">Measure:</b> rank IC (does the ranking predict tomorrow?), Sharpe (return per risk), drawdown, turnover, results per year and per market regime.</li>
          <li><b className="text-white">Judge honestly:</b> walk-forward selection (only past years), Holm correction for many tests, a 200-draw random-selection baseline, the deflated Sharpe ratio, Fama-French + momentum regression and an untouched 2024–25 hold-out.</li>
        </ol>
      </div>
      <div className="glass-card rounded-3xl p-6 border border-white/15 space-y-5">
        <h3 className="font-heading text-xl font-bold text-white flex items-center gap-2"><Sigma className="w-5 h-5 text-cyan-400" />Significance after multiple-testing correction</h3>
        {err && <p className="text-xs font-mono text-rose-300">{err}</p>}
        {s && (
          <>
            <RuleTable title={`Walk-forward 2016–2023 · ${s.u36?.wf5?.universe} stocks`} wf={s.u36?.wf5} ca={s.u36?.ca} />
            {s.big && <RuleTable title={`Walk-forward 2016–2023 · ${s.big.wf5.universe} stocks`} wf={s.big.wf5} ca={s.big.ca} />}
            {s.big && <RuleTable title={`Untouched hold-out 2024–2025 · ${s.big.wf5.universe} stocks`} wf={s.big.wf_hold} ca={s.big.ca_hold} />}
            <p className="text-[11px] text-slate-500 font-mono">Holm p &lt; 0.05 (green) = significant after correcting for every rule tried. Random-null p = share of 200 random
              3-formula selections that did as well. Net Sharpe is after trading costs; none of the 28 portfolio variants per universe is significant.</p>
          </>
        )}
      </div>
    </div>
  );
}
