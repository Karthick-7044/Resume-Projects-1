import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Cpu, Network, Layers, ShieldCheck, Database, Sliders, CheckCircle2, TrendingUp, AlertTriangle, Binary } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';

export function Company() {
  const [activeRegimeTab, setActiveRegimeTab] = useState('volatility');

  const agents = [
    { name: 'Research Agent', desc: 'An LLM proposes literature-grounded hypotheses from an anonymised briefing of every data domain and past failures.', color: 'from-blue-500 to-cyan-400' },
    { name: 'Quant Agent', desc: 'Turns each hypothesis into a short formula in a safe factor language (cross-sectional and backward-looking operators only).', color: 'from-indigo-500 to-blue-400' },
    { name: 'Validator & Backtester', desc: 'Rejects look-ahead and unknown features, then backtests a dollar-neutral long/short portfolio net of 10 bps.', color: 'from-purple-500 to-indigo-400' },
    { name: 'News & FinBERT Layer', desc: 'FNSPID (2013-2023) and Google News (2024-2025) headlines, scored by FinBERT and aligned to the first tradable day.', color: 'from-cyan-500 to-teal-400' },
    { name: 'Attribution', desc: 'Leave-one-feature-out: measures how much each feature and data domain contributes to the predictive power.', color: 'from-violet-500 to-purple-400' },
    { name: 'Critic Agent & Memory', desc: 'Rule-based checks (leakage, stability, regimes, concentration, costs, deflated Sharpe); failures are refined up to twice and remembered.', color: 'from-blue-600 to-violet-500' },
  ];

  const regimes = {
    volatility: {
      name: 'High vs. Low Volatility',
      desc: 'Factors with strong momentum in low-volatility regimes often experience severe breakdown during sudden volatility spikes. Our system conditions factor weights based on instantaneous VIX/realized volatility state matrices.',
      tags: ['VIX Conditioning', 'Vol Spike Defense', 'Variance Risk Premium']
    },
    trending: {
      name: 'Trending vs. Mean-Reverting',
      desc: 'Trend-following alpha factors decompose when asset prices enter tight range-bound mean-reverting states. Agents dynamically switch signal formulation based on Hurst exponent and market efficiency ratios.',
      tags: ['Hurst Exponent', 'Autocorrelation Shift', 'Ornstein-Uhlenbeck Fit']
    },
    liquidity: {
      name: 'Liquidity Stress & Event-Driven',
      desc: 'During market-wide liquidity crunches, asset correlation spikes to 1. The regime module detects liquidity drying in depth charts and reduces exposure to high-turnover micro-cap factors.',
      tags: ['Amihud Illiquidity', 'Bid-Ask Spread Skew', 'Flow Toxicity (VPIN)']
    }
  };

  return (
    <section id="company" className="relative py-28 bg-[#050505] text-slate-100 overflow-hidden">
      {/* Ambient background glows */}
      <div className="absolute top-1/3 right-0 w-[500px] h-[500px] bg-blue-600/10 rounded-full blur-[140px] pointer-events-none" />
      <div className="absolute bottom-10 left-10 w-[450px] h-[450px] bg-purple-600/10 rounded-full blur-[140px] pointer-events-none" />
      <div className="absolute inset-0 bg-grid-pattern opacity-30 pointer-events-none" />

      <div className="relative max-w-7xl mx-auto px-6 sm:px-8 lg:px-12">
        {/* Section Header */}
        <div className="text-center max-w-3xl mx-auto space-y-4 mb-20">
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-blue-950/40 border border-blue-500/30 text-xs font-mono text-blue-300">
            <Database className="w-3.5 h-3.5 text-cyan-400" />
            <span>Institutional Research Platform</span>
          </div>

          <h2 className="font-heading text-3xl sm:text-5xl font-extrabold tracking-tight text-white">
            Where AI Meets <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-400 via-indigo-300 to-purple-400">Quantitative Research</span>
          </h2>

          <p className="text-slate-300 text-lg leading-relaxed">
            We build intelligent quantitative research systems that combine multiple specialized AI agents to discover, evaluate, and explain alpha factors across changing market environments.
          </p>
        </div>

        {/* 3 Core Principles Grid */}
        <div className="space-y-16">
          
          {/* Principle 01 — Multi-Agent Research */}
          <div className="glass-card rounded-3xl p-8 sm:p-12 border border-white/10 relative overflow-hidden">

            <div className="max-w-3xl space-y-4 mb-8">
              <div className="text-sm font-medium text-blue-300">
                Specialized agent teams
              </div>
              <h3 className="font-heading text-2xl sm:text-4xl font-bold text-white">
                Multi-Agent Research Architecture
              </h3>
              <p className="text-slate-300 text-base sm:text-lg leading-relaxed">
                Rather than relying on a single opaque monolithic neural network, our platform employs specialized autonomous agents. Each agent independently analyzes a distinct dimension of market data and collaborates through multi-agent consensus.
              </p>
            </div>

            {/* Agent Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 pt-4">
              {agents.map((agent, idx) => (
                <motion.div
                  key={agent.name}
                  initial={{ opacity: 0, y: 15 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: idx * 0.08 }}
                  className="bg-void-850/80 border border-white/10 rounded-2xl p-5 hover:border-blue-500/40 hover:bg-void-800 transition-all group"
                >
                  <div className="flex items-center gap-3 mb-2.5">
                    <div className={`w-8 h-8 rounded-lg bg-gradient-to-br ${agent.color} flex items-center justify-center text-slate-950 font-bold text-xs shadow-md`}>
                      <span className="block w-2 h-2 rounded-full bg-slate-950/70" />
                    </div>
                    <h4 className="font-heading font-semibold text-white group-hover:text-blue-300 transition-colors">
                      {agent.name}
                    </h4>
                  </div>
                  <p className="text-xs text-slate-400 leading-relaxed">
                    {agent.desc}
                  </p>
                </motion.div>
              ))}
            </div>
          </div>

          {/* Principle 02 — Regime Awareness */}
          <div className="glass-card rounded-3xl p-8 sm:p-12 border border-white/10 relative overflow-hidden">

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-center">
              <div className="lg:col-span-6 space-y-6">
                <div className="text-sm font-medium text-purple-300">
                  Adaptive factor testing
                </div>
                <h3 className="font-heading text-2xl sm:text-4xl font-bold text-white">
                  Regime-Aware Factor Evaluation
                </h3>
                <p className="text-slate-300 text-base sm:text-lg leading-relaxed">
                  Financial markets non-stationarily shift across distinct environments. Alpha factors are evaluated conditionally across regimes rather than assuming a single factor works universally.
                </p>

                {/* Regime Selector Tabs */}
                <div className="flex flex-wrap gap-2 pt-2">
                  {Object.keys(regimes).map((key) => (
                    <button
                      key={key}
                      onClick={() => setActiveRegimeTab(key)}
                      className={`px-4 py-2 rounded-xl text-xs font-medium transition-all ${
                        activeRegimeTab === key
                          ? 'bg-purple-600 text-white border border-purple-400/50 shadow-lg shadow-purple-600/30'
                          : 'bg-void-850 text-slate-400 hover:text-white border border-white/10'
                      }`}
                    >
                      {regimes[key].name}
                    </button>
                  ))}
                </div>

                <div className="bg-void-850/90 border border-white/10 rounded-2xl p-6 space-y-4">
                  <h4 className="font-heading font-semibold text-lg text-purple-300">
                    {regimes[activeRegimeTab].name}
                  </h4>
                  <p className="text-sm text-slate-300 leading-relaxed">
                    {regimes[activeRegimeTab].desc}
                  </p>
                  <div className="flex flex-wrap gap-2 pt-2">
                    {regimes[activeRegimeTab].tags.map((tag) => (
                      <span key={tag} className="px-2.5 py-1 rounded-md bg-purple-950/60 border border-purple-500/30 text-[11px] font-mono text-purple-200">
                        #{tag}
                      </span>
                    ))}
                  </div>
                </div>
              </div>

              {/* Regime Environment Matrix Visual */}
              <div className="lg:col-span-6 bg-void-900/90 border border-white/10 rounded-2xl p-6 space-y-4">
                <div className="flex items-center justify-between text-xs font-mono text-slate-400 pb-3 border-b border-white/10">
                  <span>REGIME CLASSIFICATION MATRIX</span>
                  <span className="text-cyan-400 flex items-center gap-1">
                    <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" /> LIVE STATE
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  {[
                    { state: 'Bull Market', status: 'High Momentum', alpha: 'Momentum-type factors' },
                    { state: 'Bear Market', status: 'Hedging Active', alpha: 'Conditional' },
                    { state: 'High Volatility', status: 'Vol Adjusted', alpha: 'Active (Tail Risk Hedged)' },
                    { state: 'Low Volatility', status: 'Leverage Optimized', alpha: 'Quality-type factors' },
                    { state: 'Trending', status: 'Directional Alpha', alpha: 'High Conviction' },
                    { state: 'Mean-Reverting', status: 'Stat-Arb Active', alpha: 'Mean-Reversion Signal' },
                    { state: 'Liquidity Stress', status: 'Risk-Off Shift', alpha: 'Defensive Mode' },
                    { state: 'Event-Driven', status: 'Catalyst Isolation', alpha: 'Skew Aware' },
                  ].map((r, i) => (
                    <div key={i} className="p-3 rounded-xl bg-void-800/80 border border-white/5 space-y-1 hover:border-purple-500/30 transition-colors">
                      <div className="text-xs font-bold text-white">{r.state}</div>
                      <div className="text-[11px] font-mono text-purple-300">{r.status}</div>
                      <div className="text-[10px] text-slate-400">{r.alpha}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Principle 03 — Explainable Alpha */}
          <div className="glass-card rounded-3xl p-8 sm:p-12 border border-white/10 relative overflow-hidden">

            <div className="max-w-3xl space-y-4 mb-10">
              <div className="text-sm font-medium text-cyan-300">
                Traceable alpha logic
              </div>
              <h3 className="font-heading text-2xl sm:text-4xl font-bold text-white">
                Explainable & Interpretable Factor Intelligence
              </h3>
              <p className="text-slate-300 text-base sm:text-lg leading-relaxed">
                Institutional investment committees require transparency. Every candidate alpha factor generated by our research system includes comprehensive economic logic and statistical diagnostics.
              </p>
            </div>

            {/* Explainability Checklist Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
              {[
                { title: 'Economic Drivers', desc: 'Transparent explanation of why the factor generates excess returns and its structural rationale.' },
                { title: 'Feature Attribution', desc: 'Exact mathematical breakdown of variable influence, Shapley values, and gradient sensitivity.' },
                { title: 'Regime Performance', desc: 'Historical & simulated performance breakdown across every recognized market regime.' },
                { title: 'Failure Conditions', desc: 'Explicit boundary conditions identifying when the signal degrades or experiences capacity limits.' },
              ].map((item, idx) => (
                <div key={idx} className="bg-void-850/80 border border-white/10 rounded-2xl p-6 hover:border-cyan-500/40 transition-all space-y-3">
                  <CheckCircle2 className="w-6 h-6 text-cyan-400" />
                  <h4 className="font-heading font-bold text-lg text-white">{item.title}</h4>
                  <p className="text-xs text-slate-400 leading-relaxed">{item.desc}</p>
                </div>
              ))}
            </div>
          </div>

        </div>
      </div>
    </section>
  );
}
