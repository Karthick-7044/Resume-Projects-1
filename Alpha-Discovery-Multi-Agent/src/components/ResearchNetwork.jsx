import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Cpu, Zap, Activity, ShieldCheck, Eye, RefreshCw, BarChart2, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';

export function ResearchNetwork() {
  const [selectedAgent, setSelectedAgent] = useState(null);
  const [activeRegime, setActiveRegime] = useState('Volatility Conditioning');
  const [pulseCount, setPulseCount] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setPulseCount((prev) => prev + 1);
    }, 3000);
    return () => clearInterval(interval);
  }, []);

  const agents = [
    { id: 'research', name: 'RESEARCH AGENT', icon: '🔎', metric: 'LLM (Groq / Gemini)', focus: 'Proposes economic hypotheses from an anonymised data briefing',
      position: 'top-4 left-1/2 -translate-x-1/2 md:top-6', angle: -90, alphaContribution: 'ideas',
      formula: 'hypothesis = {mechanism, literature basis, >= 2 data domains, expected sign}' },
    { id: 'quant', name: 'QUANT AGENT', icon: '🧮', metric: 'LLM + factor language', focus: 'Turns each idea into a safe formula',
      position: 'top-1/4 right-4 md:right-12', angle: -30, alphaContribution: 'formulas',
      formula: 'cs_rank(momentum_252_21d) + cs_rank(roe)' },
    { id: 'validator', name: 'VALIDATOR', icon: '🛡', metric: 'Deterministic code', focus: 'Blocks look-ahead, labels, unknown features, thin coverage',
      position: 'bottom-1/4 right-4 md:right-12', angle: 30, alphaContribution: 'valid / invalid',
      formula: 'windows 1..252, no negative lags, PIT-registered features only' },
    { id: 'backtest', name: 'BACKTESTER', icon: '📈', metric: '10 bps per trade', focus: 'Dollar-neutral long/short, next-day returns',
      position: 'bottom-4 left-1/2 -translate-x-1/2 md:bottom-6', angle: 90, alphaContribution: 'IC, Sharpe',
      formula: 'w_i = (rank_i - mean) / sum|rank - mean|;  IC_t = Spearman(f_t, r_{t+1})' },
    { id: 'attribution', name: 'ATTRIBUTION', icon: '🧩', metric: 'Leave-one-feature-out', focus: 'Which data domain drives the signal',
      position: 'bottom-1/4 left-4 md:left-12', angle: 150, alphaContribution: 'drivers',
      formula: 'contribution_f = IC(full) - IC(feature f neutralised)' },
    { id: 'critic', name: 'CRITIC AGENT', icon: '⚖', metric: 'Rule-based + memory', focus: 'ACCEPT / REVISE / REJECT with reasons; up to 2 refinements',
      position: 'top-1/4 left-4 md:left-12', angle: -150, alphaContribution: 'verdict',
      formula: 'IC_train >= 0.005, IC_valid > 0, positive in >= 2/3 of years, DSR >= 0.95' },
  ];

  const pipelineSteps = [
    { step: '01', title: 'Point-in-time data', desc: 'Prices, SEC accounts as first reported, FinBERT news, regimes and macro joined per stock and day.' },
    { step: '02', title: 'Research agent', desc: 'An LLM reads an anonymised feature briefing and proposes literature-grounded ideas.' },
    { step: '03', title: 'Quant agent + validator', desc: 'Ideas become formulas; unsafe or look-ahead formulas are rejected in code.' },
    { step: '04', title: 'Backtest', desc: 'Dollar-neutral long/short on training and validation years only, net of 10 bps.' },
    { step: '05', title: 'Attribution + Critic', desc: 'Drivers are explained; the Critic accepts, refines (max 2) or rejects, and memory learns.' },
    { step: '06', title: 'Honest evaluation', desc: 'Walk-forward, Holm correction, random baseline, Fama-French + momentum, untouched hold-out.' },
  ];

  return (
    <section className="relative py-28 bg-[#050505] overflow-hidden text-slate-100 border-y border-white/10">
      {/* Background Volumetric Lighting */}
      <div className="absolute inset-0 bg-void-950 pointer-events-none" />
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[700px] h-[700px] bg-blue-600/10 rounded-full blur-[160px] pointer-events-none" />
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] bg-purple-600/10 rounded-full blur-[140px] pointer-events-none" />
      <div className="absolute inset-0 bg-dots-pattern opacity-20 pointer-events-none" />

      <div className="relative max-w-7xl mx-auto px-6 sm:px-8 lg:px-12 space-y-16">
        
        {/* Section Header */}
        <div className="text-center max-w-3xl mx-auto space-y-4">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-gradient-to-r from-blue-950 to-purple-950 border border-blue-500/30 text-xs font-mono text-cyan-300">
            <Activity className="w-3.5 h-3.5 text-cyan-400 animate-pulse" />
            <span>INTERACTIVE MULTI-AGENT ALPHA ENGINE</span>
          </div>

          <h2 className="font-heading text-3xl sm:text-5xl font-extrabold tracking-tight text-white">
            Autonomous <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-400 via-indigo-300 to-purple-400">Research Network</span>
          </h2>

          <p className="text-slate-300 text-base sm:text-lg">
            Hover over specialized agents to inspect live mathematical alpha factor contributions and stream dynamics.
          </p>
        </div>

        {/* Central Multi-Agent Neural Network Diagram */}
        <div className="relative w-full min-h-[560px] sm:min-h-[640px] glass-card rounded-3xl border border-white/10 p-6 flex items-center justify-center overflow-hidden">
          
          {/* Animated Connecting SVG Data Streams */}
          <svg className="absolute inset-0 w-full h-full pointer-events-none z-0 stroke-blue-500/30">
            <defs>
              <linearGradient id="gradient-stream" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#2563eb" stopOpacity="0.8" />
                <stop offset="50%" stopColor="#7c3aed" stopOpacity="0.8" />
                <stop offset="100%" stopColor="#22d3ee" stopOpacity="0.9" />
              </linearGradient>
            </defs>

            {/* Connecting lines from center (50%, 50%) to nodes */}
            <line x1="50%" y1="50%" x2="50%" y2="12%" stroke="url(#gradient-stream)" strokeWidth="2" strokeDasharray="6 6" />
            <line x1="50%" y1="50%" x2="82%" y2="28%" stroke="url(#gradient-stream)" strokeWidth="2" strokeDasharray="6 6" />
            <line x1="50%" y1="50%" x2="82%" y2="72%" stroke="url(#gradient-stream)" strokeWidth="2" strokeDasharray="6 6" />
            <line x1="50%" y1="50%" x2="50%" y2="88%" stroke="url(#gradient-stream)" strokeWidth="2" strokeDasharray="6 6" />
            <line x1="50%" y1="50%" x2="18%" y2="72%" stroke="url(#gradient-stream)" strokeWidth="2" strokeDasharray="6 6" />
            <line x1="50%" y1="50%" x2="18%" y2="28%" stroke="url(#gradient-stream)" strokeWidth="2" strokeDasharray="6 6" />

            {/* Orbiting Ring Visuals */}
            <circle cx="50%" cy="50%" r="22%" fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="1" />
            <circle cx="50%" cy="50%" r="38%" fill="none" stroke="rgba(37,99,235,0.12)" strokeWidth="1.5" strokeDasharray="4 8" />
          </svg>

          {/* Central Glowing Alpha Engine */}
          <div className="relative z-20 flex flex-col items-center justify-center">
            <motion.div
              animate={{
                scale: [1, 1.06, 1],
                boxShadow: [
                  '0 0 40px rgba(37, 99, 235, 0.4)',
                  '0 0 70px rgba(124, 58, 237, 0.6)',
                  '0 0 40px rgba(37, 99, 235, 0.4)',
                ],
              }}
              transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut' }}
              className="w-28 h-28 sm:w-36 sm:h-36 rounded-full bg-gradient-to-br from-blue-600 via-indigo-700 to-purple-800 border-2 border-cyan-400/60 flex flex-col items-center justify-center shadow-2xl cursor-pointer group"
            >
              <span className="font-heading font-black text-5xl sm:text-6xl text-white group-hover:scale-110 transition-transform">
                α
              </span>
              <span className="text-[10px] font-mono tracking-widest text-cyan-300 font-semibold mt-1">
                ALPHA ENGINE
              </span>
            </motion.div>

            {/* Status Micro Badge */}
            <div className="mt-4 px-3 py-1 rounded-full bg-void-900/90 border border-blue-500/40 text-[11px] font-mono text-cyan-300 flex items-center gap-2 shadow-lg backdrop-blur-md">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
              <span>DISCOVERY RUNNING</span>
            </div>
          </div>

          {/* 6 Peripheral Agent Nodes */}
          {agents.map((agent) => (
            <motion.div
              key={agent.id}
              whileHover={{ scale: 1.08 }}
              onClick={() => setSelectedAgent(agent)}
              onMouseEnter={() => setSelectedAgent(agent)}
              className={`absolute ${agent.position} z-20 cursor-pointer max-w-[180px] sm:max-w-[210px]`}
            >
              <div
                className={`p-3.5 sm:p-4 rounded-2xl transition-all duration-300 backdrop-blur-xl ${
                  selectedAgent?.id === agent.id
                    ? 'bg-blue-950/90 border-2 border-cyan-400 shadow-glow-cyan scale-105'
                    : 'bg-void-900/90 border border-white/15 hover:border-blue-400/50 hover:bg-void-850'
                }`}
              >
                <div className="flex items-center justify-between gap-2 mb-1">
                  <span className="text-lg">{agent.icon}</span>
                  <span className="text-[10px] font-mono text-cyan-400 bg-cyan-950/60 px-2 py-0.5 rounded border border-cyan-500/30 font-semibold">
                    {agent.alphaContribution}
                  </span>
                </div>
                <div className="font-heading font-bold text-xs sm:text-sm text-white tracking-tight">
                  {agent.name}
                </div>
                <div className="text-[10px] font-mono text-slate-400 mt-1 truncate">
                  {agent.metric}
                </div>
              </div>
            </motion.div>
          ))}

          {/* Live Agent Inspector Drawer / Overlay */}
          <AnimatePresence>
            {selectedAgent && (
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 20 }}
                className="absolute bottom-4 left-4 right-4 z-30 bg-void-900/95 border border-cyan-500/40 rounded-2xl p-5 backdrop-blur-2xl shadow-2xl max-w-2xl mx-auto"
              >
                <div className="flex items-center justify-between border-b border-white/10 pb-3 mb-3">
                  <div className="flex items-center gap-3">
                    <span className="text-2xl">{selectedAgent.icon}</span>
                    <div>
                      <h4 className="font-heading font-bold text-base text-white">
                        {selectedAgent.name}
                      </h4>
                      <span className="text-xs font-mono text-cyan-400">
                        {selectedAgent.focus}
                      </span>
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setSelectedAgent(null)}
                    className="text-slate-400 hover:text-white text-xs h-7 px-2"
                  >
                    Close
                  </Button>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <div className="text-[11px] font-mono text-slate-400">HOW IT WORKS</div>
                    <div className="p-2.5 rounded-lg bg-black/60 font-mono text-xs text-cyan-300 border border-white/10 overflow-x-auto">
                      {selectedAgent.formula}
                    </div>
                  </div>
                  <div className="space-y-1.5">
                    <div className="text-[11px] font-mono text-slate-400">WHAT IT PRODUCES</div>
                    <div className="p-2.5 rounded-lg bg-black/60 font-mono text-xs text-purple-300 border border-white/10 flex items-center justify-between">
                      <span>Output:</span>
                      <span className="font-bold text-cyan-400">{selectedAgent.alphaContribution}</span>
                    </div>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* 6 Stage Pipeline Sequence */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-4">
          {pipelineSteps.map((p, idx) => (
            <div
              key={p.step}
              className="bg-void-850/70 border border-white/10 rounded-2xl p-4 space-y-2 hover:border-blue-500/40 transition-colors relative group"
            >
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs text-blue-400 font-bold bg-blue-950/60 px-2 py-0.5 rounded border border-blue-500/30">
                  {p.step}
                </span>
                {idx < 5 && <ChevronRight className="w-4 h-4 text-slate-600 hidden lg:block" />}
              </div>
              <h4 className="font-heading font-bold text-sm text-white group-hover:text-cyan-300 transition-colors">
                {p.title}
              </h4>
              <p className="text-[11px] text-slate-400 leading-normal">
                {p.desc}
              </p>
            </div>
          ))}
        </div>

      </div>
    </section>
  );
}
