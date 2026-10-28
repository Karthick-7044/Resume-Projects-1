import React from 'react';
import { motion } from 'framer-motion';
import { GlowingEffect } from '@/components/ui/glowing-effect';
import { Cpu, Activity, ShieldCheck, LineChart, Layers, Database, ArrowRight, Zap, CheckCircle2, SlidersHorizontal } from 'lucide-react';

export function Services() {
  const servicesList = [
    {
      num: 'SERVICE 01',
      title: 'Multi-Agent Alpha Discovery',
      description: 'Autonomous research agents explore large financial datasets and generate candidate alpha factors through collaborative quantitative reasoning.',
      icon: Cpu,
      accentColor: 'from-blue-500 to-indigo-500',
      badge: 'Collaborative Reasoning',
      visualType: 'nodes',
    },
    {
      num: 'SERVICE 02',
      title: 'Regime-Aware Factor Research',
      description: 'Evaluate how factors behave across changing market regimes and identify where signals strengthen, weaken, or break down.',
      icon: Activity,
      accentColor: 'from-purple-500 to-indigo-500',
      badge: 'Dynamic Adaptation',
      visualType: 'landscape',
    },
    {
      num: 'SERVICE 03',
      title: 'Explainable Factor Intelligence',
      description: 'Understand the economic and statistical drivers behind discovered signals instead of treating alpha as an opaque black box.',
      icon: ShieldCheck,
      accentColor: 'from-cyan-500 to-blue-500',
      badge: 'Interpretable AI',
      visualType: 'graph',
    },
    {
      num: 'SERVICE 04',
      title: 'Factor Validation & Robustness',
      description: 'Evaluate candidate factors for statistical significance, stability, turnover, correlation, drawdown behavior, and out-of-sample robustness.',
      icon: LineChart,
      accentColor: 'from-emerald-500 to-teal-500',
      badge: 'Out-Of-Sample Proof',
      visualType: 'pathways',
    },
    {
      num: 'SERVICE 05',
      title: 'Corporate Event Intelligence',
      description: 'Use SEC 8-K filings (earnings releases, executive changes, material agreements) as point-in-time event data, e.g. post-earnings drift.',
      icon: SlidersHorizontal,
      accentColor: 'from-violet-500 to-purple-500',
      badge: 'SEC 8-K Events',
      visualType: 'orderbook',
    },
    {
      num: 'SERVICE 06',
      title: 'Research Intelligence Infrastructure',
      description: 'Build scalable AI research pipelines that continuously discover, test, explain, and monitor quantitative signals.',
      icon: Database,
      accentColor: 'from-blue-600 to-cyan-500',
      badge: 'Enterprise Scalability',
      visualType: 'pipeline',
    },
  ];

  return (
    <section id="services" className="relative py-28 bg-[#050505] text-slate-100 overflow-hidden">
      {/* Background Volumetric Lighting */}
      <div className="absolute top-1/4 left-0 w-96 h-96 bg-blue-600/10 rounded-full blur-[140px] pointer-events-none" />
      <div className="absolute bottom-1/4 right-0 w-96 h-96 bg-purple-600/10 rounded-full blur-[140px] pointer-events-none" />
      <div className="absolute inset-0 bg-grid-pattern opacity-25 pointer-events-none" />

      <div className="relative max-w-7xl mx-auto px-6 sm:px-8 lg:px-12 space-y-16">
        
        {/* Section Header */}
        <div className="text-center max-w-3xl mx-auto space-y-4">
          <div className="inline-flex items-center gap-2 px-3.5 py-1 rounded-full bg-purple-950/40 border border-purple-500/30 text-xs font-mono text-purple-300">
            <Zap className="w-3.5 h-3.5 text-purple-400" />
            <span>QUANTITATIVE CAPABILITIES</span>
          </div>

          <h2 className="font-heading text-3xl sm:text-5xl font-extrabold tracking-tight text-white">
            Quantitative Intelligence, <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-400 via-indigo-300 to-purple-400">Built for Discovery.</span>
          </h2>

          <p className="text-slate-300 text-lg leading-relaxed">
            Institutional-grade software architecture engineered to deliver transparent, regime-aware alpha factor research.
          </p>
        </div>

        {/* 6 Service Cards with Glowing Effect Wrapper */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
          {servicesList.map((service, idx) => {
            const IconComponent = service.icon;
            return (
              <GlowingEffect key={service.title} className="h-full">
                <div className="h-full bg-void-850/90 border border-white/10 rounded-2xl p-7 flex flex-col justify-between hover:bg-void-800 transition-all duration-300 group">
                  
                  <div className="space-y-6">
                    {/* Card Header Top */}
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-mono font-semibold tracking-wider text-blue-400 bg-blue-950/60 px-3 py-1 rounded-full border border-blue-500/30">
                        {service.num}
                      </span>
                      <span className="text-[11px] font-mono text-slate-400 border border-white/10 px-2.5 py-0.5 rounded-full">
                        {service.badge}
                      </span>
                    </div>

                    {/* Service Title & Icon */}
                    <div className="space-y-3">
                      <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-blue-900/50 to-purple-900/40 border border-blue-500/30 flex items-center justify-center text-cyan-400 shadow-lg group-hover:scale-105 transition-transform">
                        <IconComponent className="w-6 h-6" />
                      </div>
                      <h3 className="font-heading font-bold text-xl text-white group-hover:text-cyan-300 transition-colors">
                        {service.title}
                      </h3>
                    </div>

                    {/* Description */}
                    <p className="text-sm text-slate-300 leading-relaxed">
                      {service.description}
                    </p>
                  </div>

                  {/* Card Bottom Custom Interactive Visual Cue */}
                  <div className="mt-8 pt-6 border-t border-white/10 space-y-4">
                    {service.visualType === 'nodes' && (
                      <div className="flex items-center justify-between bg-black/50 p-3 rounded-xl border border-white/5 text-xs font-mono">
                        <span className="text-slate-400">Agent Nodes</span>
                        <div className="flex items-center gap-1.5 text-blue-400">
                          <span className="w-2 h-2 rounded-full bg-blue-400 animate-ping" />
                          <span>6 Nodes $\rightarrow$ $\alpha$</span>
                        </div>
                      </div>
                    )}

                    {service.visualType === 'landscape' && (
                      <div className="flex items-center justify-between bg-black/50 p-3 rounded-xl border border-white/5 text-xs font-mono">
                        <span className="text-slate-400">Regime Bounds</span>
                        <span className="text-purple-300 font-semibold">Adaptive State Matrix</span>
                      </div>
                    )}

                    {service.visualType === 'graph' && (
                      <div className="flex items-center justify-between bg-black/50 p-3 rounded-xl border border-white/5 text-xs font-mono">
                        <span className="text-slate-400">Attribution</span>
                        <span className="text-cyan-300 font-semibold">Shapley Diagnostics</span>
                      </div>
                    )}

                    {service.visualType === 'pathways' && (
                      <div className="flex items-center justify-between bg-black/50 p-3 rounded-xl border border-white/5 text-xs font-mono">
                        <span className="text-slate-400">OOS Validation</span>
                        <span className="text-emerald-400 font-semibold">p-value &lt; 0.001</span>
                      </div>
                    )}

                    {service.visualType === 'orderbook' && (
                      <div className="flex items-center justify-between bg-black/50 p-3 rounded-xl border border-white/5 text-xs font-mono">
                        <span className="text-slate-400">Event source</span>
                        <span className="text-purple-300 font-semibold">EDGAR 8-K · Item 2.02</span>
                      </div>
                    )}

                    {service.visualType === 'pipeline' && (
                      <div className="flex items-center justify-between bg-black/50 p-3 rounded-xl border border-white/5 text-xs font-mono">
                        <span className="text-slate-400">Throughput</span>
                        <span className="text-blue-300 font-semibold">Real-Time Compute</span>
                      </div>
                    )}

                    <div className="flex items-center text-xs font-medium text-blue-400 group-hover:text-blue-300 transition-colors">
                      <span>Explore Technical Architecture</span>
                      <ArrowRight className="w-4 h-4 ml-1 group-hover:translate-x-1 transition-transform" />
                    </div>
                  </div>

                </div>
              </GlowingEffect>
            );
          })}
        </div>

      </div>
    </section>
  );
}
