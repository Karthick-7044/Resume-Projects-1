import React, { useEffect, useMemo, useState } from 'react';
import { FlaskConical, AlertTriangle, ShieldCheck } from 'lucide-react';
import { fetchAlphaAblation, fetchAlphaAttribution, fetchAlphaEquity } from '@/lib/api';

const num = (v, d = 2) => (v === null || v === undefined ? '—' : Number(v).toFixed(d));
const pct = (v, d = 1) => (v === null || v === undefined ? '—' : `${(Number(v) * 100).toFixed(d)}%`);
const sign = (v) => (v === null || v === undefined ? 'text-slate-500' : v > 0 ? 'text-emerald-400' : 'text-rose-400');
const COLORS = { A: '#94a3b8', B: '#60a5fa', C: '#fbbf24', D: '#34d399', Full: '#22d3ee', 'Full-NoCritic': '#f87171' };
const VERDICT = {
  ACCEPT: 'bg-emerald-950/80 border-emerald-500/40 text-emerald-300',
  REVISE: 'bg-amber-950/80 border-amber-500/40 text-amber-300',
  REJECT: 'bg-rose-950/80 border-rose-500/40 text-rose-300',
  INVALID: 'bg-slate-900 border-slate-600 text-slate-400',
  UNREVIEWED: 'bg-slate-900 border-slate-600 text-slate-300',
};

function EquityChart({ rows, testStart }) {
  const { paths, xTest, yOne } = useMemo(() => {
    const byCfg = {};
    rows.forEach((r) => { (byCfg[r.config] = byCfg[r.config] || []).push(r); });
    const all = rows.map((r) => r.equity).filter((v) => v !== null);
    if (!all.length) return { paths: [], xTest: null, yOne: null };
    const lo = Math.min(...all), hi = Math.max(...all);
    const dates = [...new Set(rows.map((r) => r.date))].sort();
    const x = (d) => 40 + (dates.indexOf(d) / Math.max(dates.length - 1, 1)) * 740;
    const y = (v) => 210 - ((v - lo) / Math.max(hi - lo, 1e-9)) * 190;
    const t = dates.find((d) => d >= testStart);
    return {
      paths: Object.entries(byCfg).map(([cfg, rs]) => ({
        cfg, d: rs.map((r, i) => `${i ? 'L' : 'M'}${x(r.date).toFixed(1)},${y(r.equity).toFixed(1)}`).join(' '),
      })),
      xTest: t ? x(t) : null,
      yOne: y(1),
    };
  }, [rows, testStart]);

  if (!paths.length) return null;
  return (
    <svg viewBox="0 0 800 230" className="w-full h-64">
      <line x1="40" x2="780" y1={yOne} y2={yOne} stroke="#475569" strokeDasharray="4 4" />
      {xTest && (
        <>
          <rect x={xTest} y="10" width={780 - xTest} height="205" fill="#22d3ee" opacity="0.06" />
          <text x={xTest + 6} y="22" fill="#67e8f9" fontSize="10" fontFamily="monospace">held-out test (2025)</text>
          <text x="46" y="22" fill="#94a3b8" fontSize="10" fontFamily="monospace">validation (2024)</text>
        </>
      )}
      {paths.map((p) => (
        <path key={p.cfg} d={p.d} fill="none" stroke={COLORS[p.cfg] || '#fff'} strokeWidth={p.cfg === 'Full' ? 2.2 : 1.3} />
      ))}
    </svg>
  );
}

const DOMAIN_COLORS = {
  technical: '#22d3ee', fundamental: '#34d399', valuation: '#a78bfa', news: '#f472b6',
  regime: '#fbbf24', macro: '#fb923c', cross_sectional: '#60a5fa',
};

function SignedBars({ items, scale }) {
  const max = scale || Math.max(1e-9, ...items.map((d) => Math.abs(d.value || 0)));
  return (
    <div className="space-y-1.5">
      {items.map((d) => {
        const w = (Math.abs(d.value || 0) / max) * 50;
        return (
          <div key={d.label} className="grid grid-cols-[minmax(0,10rem)_1fr_4.5rem] items-center gap-2 text-[11px] font-mono">
            <span className="truncate text-slate-300" title={d.label}>{d.label}</span>
            <div className="relative h-3 rounded bg-white/5">
              <div className="absolute top-0 bottom-0 left-1/2 w-px bg-white/20" />
              <div
                className="absolute top-0 bottom-0 rounded"
                style={{ background: d.color || '#22d3ee', width: `${w}%`, left: d.value >= 0 ? '50%' : `${50 - w}%` }}
              />
            </div>
            <span className={`text-right ${sign(d.value)}`}>{num(d.value, 4)}</span>
          </div>
        );
      })}
    </div>
  );
}

function AttributionPanel({ experiments, config }) {
  const [rows, setRows] = useState([]);
  const [sel, setSel] = useState(null);
  const [err, setErr] = useState(null);
  const ids = useMemo(() => (experiments || []).filter((e) => e.verdict !== 'INVALID').map((e) => e.experiment_id), [experiments]);

  useEffect(() => {
    let cancelled = false;
    setRows([]); setSel(null); setErr(null);
    if (!ids.length) return undefined;
    fetchAlphaAttribution(ids)
      .then((r) => { if (!cancelled) { setRows(r.rows || []); setSel((r.rows || [])[0]?.experiment_id || null); } })
      .catch((e) => { if (!cancelled) setErr(e.message); });
    return () => { cancelled = true; };
  }, [ids]);

  const row = rows.find((r) => r.experiment_id === sel);
  const features = row ? Object.entries(row.by_feature || {}).map(([f, v]) => ({
    label: f, value: v.ic_contribution, color: DOMAIN_COLORS[v.domain],
  })).sort((a, b) => Math.abs(b.value) - Math.abs(a.value)) : [];
  const domains = row ? Object.entries(row.domain_share || {}).sort((a, b) => b[1] - a[1]) : [];
  const styles = row ? Object.entries(row.style_exposure || {}).map(([k, v]) => ({ label: k, value: v })) : [];

  return (
    <div className="glass-card rounded-3xl p-6 border border-white/15 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="font-heading text-lg font-bold text-white flex items-center gap-2">
          <FlaskConical className="w-5 h-5 text-cyan-400" /> Attribution — configuration {config}
        </h3>
        {rows.length > 0 && (
          <select
            value={sel || ''}
            onChange={(e) => setSel(e.target.value)}
            className="bg-black/40 border border-white/10 rounded-lg px-2 py-1 text-xs font-mono text-cyan-200 max-w-full md:max-w-lg"
          >
            {rows.map((r) => (
              <option key={r.experiment_id} value={r.experiment_id}>[{r.verdict}] {r.formula}</option>
            ))}
          </select>
        )}
      </div>
      <p className="text-[11px] text-slate-400 font-mono">
        Leave-one-feature-out on the training period: each feature is replaced by its cross-sectional mean (market-wide
        features by their time-series mean) and the drop in rank IC is its contribution. Positive = the feature carries the signal.
      </p>
      {err && <p className="text-xs font-mono text-rose-300">{err}</p>}
      {!err && !rows.length && <p className="text-xs font-mono text-slate-500">No attribution records for this configuration.</p>}
      {row && (
        <div className="grid gap-6 md:grid-cols-3">
          <div className="md:col-span-2 space-y-2">
            <div className="text-xs font-mono text-slate-400">
              Base training rank IC <span className={sign(row.base_rank_ic)}>{num(row.base_rank_ic, 4)}</span> ·
              validation IC <span className={sign(row.valid_rank_ic)}>{num(row.valid_rank_ic, 4)}</span> ·
              dominant domain <span className="text-white">{row.dominant_domain || '—'}</span>
            </div>
            <SignedBars items={features} />
            <div className="pt-2 text-xs font-mono text-slate-400">Style exposure (mean cross-sectional rank correlation)</div>
            <SignedBars items={styles} scale={1} />
          </div>
          <div className="space-y-2">
            <div className="text-xs font-mono text-slate-400">Share of |IC contribution| by domain</div>
            {domains.map(([d, s]) => (
              <div key={d} className="space-y-1">
                <div className="flex justify-between text-[11px] font-mono text-slate-300"><span>{d}</span><span>{pct(s)}</span></div>
                <div className="h-2 rounded bg-white/5">
                  <div className="h-2 rounded" style={{ width: `${s * 100}%`, background: DOMAIN_COLORS[d] || '#94a3b8' }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function AlphaDiscoveryLab() {
  const [data, setData] = useState(null);
  const [equity, setEquity] = useState([]);
  const [active, setActive] = useState('Full');
  const [file, setFile] = useState(undefined);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const [abl, eq] = await Promise.all([fetchAlphaAblation(file), fetchAlphaEquity()]);
        if (!cancelled) {
          setData(abl);
          setEquity(eq || []);
        }
      } catch (err) {
        if (!cancelled) setError(err.message);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [file]);

  if (error) {
    return (
      <div className="glass-card rounded-3xl p-6 border border-white/15 text-xs font-mono text-rose-300 flex items-center gap-2">
        <AlertTriangle className="w-4 h-4" /> {error} — run <code className="text-cyan-300">python -m app.alpha.run_discovery</code>
      </div>
    );
  }
  if (!data) return <div className="text-xs font-mono text-slate-400">Loading alpha discovery results…</div>;

  const configs = data.configs || {};
  const cfg = configs[active] || Object.values(configs)[0];
  const testStart = data.periods?.test?.[0] || '2025-01-01';

  return (
    <div className="space-y-6">
      <div className="glass-card rounded-3xl p-6 border border-white/15 space-y-4">
        <div className="flex items-center gap-3">
          <FlaskConical className="w-5 h-5 text-cyan-400" />
          <h3 className="font-heading text-xl font-bold text-white">Ablation Study — Combined Factor per Configuration</h3>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs font-mono">
          <span className="text-slate-400">Results file:</span>
          <select
            value={data.file}
            onChange={(e) => setFile(e.target.value)}
            className="bg-black/40 border border-white/10 rounded-lg px-2 py-1 text-cyan-200"
          >
            {(data.available_files || []).map((f) => (<option key={f} value={f}>{f}</option>))}
          </select>
          <span className="text-slate-500">offline = built-in knowledge base · llm = Gemini/Claude agents</span>
        </div>
        <p className="text-xs text-slate-400 font-mono">
          Budget {data.budget} formulas per configuration · top {data.top_k} selected on validation · test year evaluated once ·
          36-stock universe, 10 bps one-way cost. Research output, not investment advice.
        </p>
        <div className="rounded-xl border border-amber-500/30 bg-amber-950/40 px-3 py-2 text-[11px] font-mono text-amber-200">
          Honest reading: backtests are net of 10 bps costs and evaluated once on a held-out period. No configuration reaches
          statistical significance (|t| &lt; 2), so these curves demonstrate the validated process, not a tradable edge.
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs font-mono">
            <thead className="text-slate-400 border-b border-white/10">
              <tr>
                {['Config', 'Information', 'Tested', 'Selected', 'Train IC', 'Valid IC', 'Test IC', 'Test Sharpe', 'Test return', 'Test max DD'].map((h) => (
                  <th key={h} className="py-2 px-3 text-right first:text-left [&:nth-child(2)]:text-left">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Object.entries(configs).map(([name, c]) => {
                const k = c.combined || {};
                return (
                  <tr
                    key={name}
                    onClick={() => setActive(name)}
                    className={`border-b border-white/5 cursor-pointer ${active === name ? 'bg-white/5' : ''}`}
                  >
                    <td className="py-2 px-3 font-bold" style={{ color: COLORS[name] }}>{name}</td>
                    <td className="py-2 px-3 text-slate-300">{c.label}</td>
                    <td className="py-2 px-3 text-right">{c.n_tested}</td>
                    <td className="py-2 px-3 text-right">{c.n_selected}</td>
                    <td className={`py-2 px-3 text-right ${sign(k.train?.rank_ic)}`}>{num(k.train?.rank_ic, 4)}</td>
                    <td className={`py-2 px-3 text-right ${sign(k.valid?.rank_ic)}`}>{num(k.valid?.rank_ic, 4)}</td>
                    <td className={`py-2 px-3 text-right ${sign(k.test?.rank_ic)}`}>{num(k.test?.rank_ic, 4)}</td>
                    <td className={`py-2 px-3 text-right ${sign(k.test?.sharpe)}`}>{num(k.test?.sharpe)}</td>
                    <td className={`py-2 px-3 text-right ${sign(k.test?.ann_return)}`}>{pct(k.test?.ann_return)}</td>
                    <td className="py-2 px-3 text-right text-rose-300">{pct(k.test?.max_drawdown)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <EquityChart rows={equity} testStart={testStart} />
        <div className="flex flex-wrap gap-4 text-xs font-mono">
          {Object.keys(configs).map((n) => (
            <span key={n} className="flex items-center gap-1.5 text-slate-300">
              <span className="w-3 h-0.5 inline-block" style={{ background: COLORS[n] }} /> {n}
            </span>
          ))}
        </div>
      </div>

      {cfg && (
        <div className="glass-card rounded-3xl p-6 border border-white/15 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h3 className="font-heading text-lg font-bold text-white flex items-center gap-2">
              <ShieldCheck className="w-5 h-5 text-emerald-400" /> Research memory — configuration {active}
            </h3>
            <div className="flex gap-2 text-xs font-mono">
              {Object.entries(cfg.verdicts || {}).map(([v, n]) => (
                <span key={v} className={`px-2 py-0.5 rounded border ${VERDICT[v] || VERDICT.INVALID}`}>{v}: {n}</span>
              ))}
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs font-mono">
              <thead className="text-slate-400 border-b border-white/10">
                <tr>
                  <th className="py-2 px-3 text-left">#</th>
                  <th className="py-2 px-3 text-left">Hypothesis</th>
                  <th className="py-2 px-3 text-left">Formula</th>
                  <th className="py-2 px-3 text-right">Train IC</th>
                  <th className="py-2 px-3 text-right">Valid IC</th>
                  <th className="py-2 px-3 text-right">Valid Sharpe</th>
                  <th className="py-2 px-3 text-left">Verdict</th>
                </tr>
              </thead>
              <tbody>
                {(cfg.experiments || []).map((e) => (
                  <tr key={e.experiment_id} className="border-b border-white/5 text-slate-200 align-top" title={e.critique}>
                    <td className="py-2 px-3 text-slate-500">{e.iteration + 1}</td>
                    <td className="py-2 px-3">
                      {e.hypothesis_title}
                      {e.revision_action && <span className="ml-2 text-amber-300">↻ {e.revision_action}</span>}
                    </td>
                    <td className="py-2 px-3 text-cyan-200 max-w-md break-words">{e.formula}</td>
                    <td className={`py-2 px-3 text-right ${sign(e.train_rank_ic)}`}>{num(e.train_rank_ic, 4)}</td>
                    <td className={`py-2 px-3 text-right ${sign(e.valid_rank_ic)}`}>{num(e.valid_rank_ic, 4)}</td>
                    <td className={`py-2 px-3 text-right ${sign(e.valid_sharpe)}`}>{num(e.valid_sharpe)}</td>
                    <td className="py-2 px-3">
                      <span className={`px-2 py-0.5 rounded border ${VERDICT[e.verdict] || VERDICT.INVALID}`}>{e.verdict}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-[11px] text-slate-500 font-mono">Hover a row to read the Critic’s reasoning.</p>
        </div>
      )}

      {cfg && <AttributionPanel experiments={cfg.experiments} config={active} />}
    </div>
  );
}
