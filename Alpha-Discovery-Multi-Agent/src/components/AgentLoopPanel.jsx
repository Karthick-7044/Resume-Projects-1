import React, { useEffect, useMemo, useState } from 'react';
import { Search, Code2, ShieldCheck, LineChart, Brain, CornerDownRight, ChevronDown, ChevronRight, FileText } from 'lucide-react';
import { fetchAgentLoop, fetchResearchBriefing } from '@/lib/api';

const num = (v, d = 4) => (v === null || v === undefined ? '—' : Number(v).toFixed(d));
const VERDICT = {
  ACCEPT: 'bg-emerald-950/70 border-emerald-500/50 text-emerald-300',
  REVISE: 'bg-amber-950/70 border-amber-500/50 text-amber-300',
  REJECT: 'bg-rose-950/70 border-rose-500/50 text-rose-300',
  INVALID: 'bg-slate-900 border-slate-600 text-slate-400',
  UNREVIEWED: 'bg-slate-900 border-slate-600 text-slate-400',
};
const STATUS = { PASS: 'text-emerald-400', WARN: 'text-amber-300', FAIL: 'text-rose-400' };

function Briefing() {
  const [b, setB] = useState(null);
  const [open, setOpen] = useState(false);
  const [err, setErr] = useState(null);
  useEffect(() => { fetchResearchBriefing().then(setB).catch((e) => setErr(e.message)); }, []);
  return (
    <div className="glass-card rounded-3xl p-6 border border-white/15 space-y-3">
      <button onClick={() => setOpen(!open)} className="w-full flex items-center justify-between gap-3 text-left">
        <h4 className="font-heading text-lg font-bold text-white flex items-center gap-2">
          <FileText className="w-5 h-5 text-cyan-400" /> What the Research agent receives (exact briefing)
        </h4>
        {open ? <ChevronDown className="w-4 h-4 text-slate-400" /> : <ChevronRight className="w-4 h-4 text-slate-400" />}
      </button>
      <p className="text-xs text-slate-400">
        The heterogeneous data is sent as an anonymised summary: every feature grouped by domain (technical, fundamental,
        valuation, news, regime, macro) with its real coverage, the training/validation lengths, the regime mix, earlier
        accepted factors and recent failures with the Critic's reasons. Tickers and calendar dates are withheld so the
        model cannot recall market history. {b && <>Latest call: <span className="text-cyan-300">{b.model}</span>, {b.n_research_calls} research calls logged.</>}
      </p>
      {err && <p className="text-xs font-mono text-rose-300">{err}</p>}
      {open && b && (
        <div className="grid lg:grid-cols-2 gap-3">
          <div className="space-y-1">
            <div className="text-[11px] font-mono text-slate-400">PROMPT (system rules + briefing)</div>
            <pre className="max-h-[480px] overflow-auto whitespace-pre-wrap rounded-xl bg-black/50 border border-white/10 p-3 text-[11px] text-slate-300">{`${b.system}\n\n${b.user}`}</pre>
          </div>
          <div className="space-y-1">
            <div className="text-[11px] font-mono text-slate-400">MODEL ANSWER (hypotheses)</div>
            <pre className="max-h-[480px] overflow-auto whitespace-pre-wrap rounded-xl bg-black/50 border border-white/10 p-3 text-[11px] text-emerald-200">{b.response}</pre>
          </div>
        </div>
      )}
    </div>
  );
}

function Attempt({ r, parent }) {
  const [open, setOpen] = useState(false);
  const t = r.metrics?.train || {}, v = r.metrics?.valid || {};
  return (
    <div className={`rounded-xl border border-white/10 bg-black/30 p-3 space-y-2 ${parent ? 'ml-6' : ''}`}>
      {parent && (
        <div className="flex items-start gap-1.5 text-[11px] text-amber-300 font-mono">
          <CornerDownRight className="w-3.5 h-3.5 mt-0.5 shrink-0" />
          <span>Refinement ({r.revision_action}) after the Critic said: <span className="text-slate-300">{(parent.critic.summary || '').slice(0, 220)}</span></span>
        </div>
      )}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <Code2 className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
          <code className="text-xs text-cyan-200 break-all">{r.formula}</code>
        </div>
        <span className={`px-2 py-0.5 rounded border text-[11px] font-mono ${VERDICT[r.critic.verdict] || VERDICT.INVALID}`}>{r.critic.verdict}</span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-[11px] font-mono">
        <div className="rounded-lg bg-white/5 px-2 py-1.5"><span className="text-slate-500 flex items-center gap-1"><ShieldCheck className="w-3 h-3" />Validator</span>
          <span className={r.validation.valid ? 'text-emerald-400' : 'text-rose-400'}>{r.validation.valid ? 'valid' : 'rejected'}</span>
          {r.validation.nodes ? <span className="text-slate-500"> · {r.validation.nodes} nodes</span> : null}</div>
        <div className="rounded-lg bg-white/5 px-2 py-1.5"><span className="text-slate-500 flex items-center gap-1"><LineChart className="w-3 h-3" />Train IC / Sharpe</span>
          {num(t.rank_ic)} / {num(t.sharpe, 2)}</div>
        <div className="rounded-lg bg-white/5 px-2 py-1.5"><span className="text-slate-500 flex items-center gap-1"><LineChart className="w-3 h-3" />Valid IC / Sharpe</span>
          {num(v.rank_ic)} / {num(v.sharpe, 2)}</div>
        <div className="rounded-lg bg-white/5 px-2 py-1.5"><span className="text-slate-500 flex items-center gap-1"><Brain className="w-3 h-3" />Attribution</span>
          {r.attribution?.dominant_domain || '—'}</div>
      </div>
      {!r.validation.valid && r.validation.errors?.length > 0 && (
        <p className="text-[11px] text-rose-300 font-mono">Validator: {r.validation.errors.join('; ').slice(0, 240)}</p>
      )}
      {r.critic.checks?.length > 0 && (
        <button onClick={() => setOpen(!open)} className="text-[11px] font-mono text-slate-400 hover:text-white flex items-center gap-1">
          {open ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />} Critic checks ({r.critic.checks.length})
        </button>
      )}
      {open && (
        <ul className="space-y-1 text-[11px] font-mono">
          {r.critic.checks.map((c) => (
            <li key={c.check} className="flex gap-2"><span className={`w-10 shrink-0 ${STATUS[c.status] || ''}`}>{c.status}</span>
              <span className="text-slate-400 w-32 shrink-0">{c.check}</span><span className="text-slate-300">{c.detail}</span></li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function AgentLoopPanel() {
  const [data, setData] = useState(null);
  const [file, setFile] = useState(undefined);
  const [config, setConfig] = useState(undefined);
  const [err, setErr] = useState(null);
  useEffect(() => {
    let off = false;
    fetchAgentLoop({ file, config }).then((d) => { if (!off) { setData(d); setErr(null); } }).catch((e) => !off && setErr(e.message));
    return () => { off = true; };
  }, [file, config]);

  const { groups, stats, byId } = useMemo(() => {
    const rows = data?.rows || [];
    const byId = Object.fromEntries(rows.map((r) => [r.experiment_id, r]));
    const groups = [];
    const idx = {};
    rows.forEach((r) => {
      const k = r.hypothesis?.title || 'Untitled hypothesis';
      if (!(k in idx)) { idx[k] = groups.length; groups.push({ title: k, h: r.hypothesis, source: r.source, rows: [] }); }
      groups[idx[k]].rows.push(r);
    });
    const count = (v) => rows.filter((r) => r.critic.verdict === v).length;
    return { groups, byId, stats: { n: rows.length, valid: rows.filter((r) => r.validation.valid).length, acc: count('ACCEPT'),
      rev: count('REVISE'), rej: count('REJECT'), refined: rows.filter((r) => r.parent_id).length,
      llm: rows.filter((r) => String(r.source).startsWith('llm')).length } };
  }, [data]);

  return (
    <div className="space-y-6">
      <div className="glass-card rounded-3xl p-6 border border-white/15 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="font-heading text-xl font-bold text-white flex items-center gap-2"><Search className="w-5 h-5 text-cyan-400" />Agent loop — every step of a run</h3>
          {data && (
            <div className="flex flex-wrap gap-2 text-xs font-mono">
              <select value={data.file} onChange={(e) => { setFile(e.target.value); setConfig(undefined); }}
                className="bg-black/40 border border-white/10 rounded-lg px-2 py-1 text-cyan-200 max-w-full">
                {data.available_files.map((f) => <option key={f} value={f}>{f}</option>)}
              </select>
              <select value={data.config} onChange={(e) => setConfig(e.target.value)} className="bg-black/40 border border-white/10 rounded-lg px-2 py-1 text-cyan-200">
                {data.configs.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
          )}
        </div>
        <p className="text-xs text-slate-400">Each card is one idea from the <b className="text-white">Research agent</b>; under it are the formulas
          the <b className="text-white">Quant agent</b> wrote, the validator result, backtest numbers (training and validation only — the
          test period is hidden from the agents), the attribution and the <b className="text-white">Critic</b>'s verdict with every check.
          Indented rows are refinements sent back by the Critic.</p>
        {err && <p className="text-xs font-mono text-rose-300">{err}</p>}
        {data && (
          <div className="grid grid-cols-3 md:grid-cols-7 gap-2 text-center text-xs font-mono">
            {[['formulas', stats.n], ['valid', stats.valid], ['accepted', stats.acc], ['revise', stats.rev], ['rejected', stats.rej],
              ['refinements', stats.refined], ['from LLM', stats.llm]].map(([k, v]) => (
              <div key={k} className="rounded-xl bg-black/30 border border-white/10 py-2"><div className="text-lg text-white font-bold">{v}</div><div className="text-slate-500">{k}</div></div>
            ))}
          </div>
        )}
      </div>

      <Briefing />

      {!data && !err && <p className="text-xs font-mono text-slate-400">Loading agent loop…</p>}
      {groups.map((g) => (
        <div key={g.title} className="glass-card rounded-3xl p-5 border border-white/15 space-y-3">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="space-y-1 min-w-0">
              <h4 className="font-heading text-base font-bold text-white flex items-center gap-2"><Search className="w-4 h-4 text-purple-300" />{g.title}</h4>
              {g.h?.rationale && <p className="text-xs text-slate-300 max-w-4xl">{g.h.rationale}</p>}
              {g.h?.literature_basis && <p className="text-[11px] text-slate-500">Literature: {g.h.literature_basis}</p>}
            </div>
            <div className="flex flex-wrap gap-1.5 text-[10px] font-mono">
              <span className={`px-2 py-0.5 rounded border ${String(g.source).startsWith('llm') ? 'border-purple-500/50 text-purple-300' : 'border-slate-600 text-slate-400'}`}>
                {String(g.source).startsWith('llm') ? 'LLM idea' : 'knowledge base'}</span>
              {(g.h?.domains || []).map((d) => <span key={d} className="px-2 py-0.5 rounded border border-cyan-500/30 text-cyan-300">{d}</span>)}
            </div>
          </div>
          <div className="space-y-2">
            {g.rows.map((r) => <Attempt key={r.experiment_id} r={r} parent={r.parent_id ? byId[r.parent_id] : null} />)}
          </div>
        </div>
      ))}
    </div>
  );
}
