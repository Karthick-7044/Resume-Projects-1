import React from 'react';
import { motion } from 'framer-motion';
import { ArrowRight, Sparkles, Cpu, Activity, LineChart, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';

export function Hero({ onExploreClick, onContactClick }) {
  const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: 0.15,
        delayChildren: 0.2,
      },
    },
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 25 },
    visible: {
      opacity: 1,
      y: 0,
      transition: { duration: 0.8, ease: [0.16, 1, 0.3, 1] },
    },
  };

  return (
    <section className="relative min-h-screen w-full flex items-center justify-start overflow-hidden bg-[#050505] pt-28 pb-16">
      {/* Full-Screen Video Background */}
      <div className="absolute inset-0 w-full h-full z-0 overflow-hidden">
        <video
          autoPlay
          muted
          loop
          playsInline
          className="w-full h-full object-cover object-center transform scale-105"
        >
          <source src="/tput.mp4" type="video/mp4" />
          Your browser does not support the video tag.
        </video>
        
        {/* Subtle Right-side & Bottom Transition Gradients — Non-heavy, crystal clear video */}
        <div className="absolute inset-0 bg-gradient-to-r from-[#050505]/85 via-[#050505]/40 to-transparent z-10 w-full md:w-3/4" />
        <div className="absolute bottom-0 inset-x-0 h-40 bg-gradient-to-t from-[#050505] via-[#050505]/60 to-transparent z-10" />
        <div className="absolute top-0 inset-x-0 h-28 bg-gradient-to-b from-[#050505]/70 to-transparent z-10" />
      </div>

      {/* Floating Animated Ambient Particles & Glowing Vectors */}
      <div className="absolute inset-0 pointer-events-none z-10">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-blue-600/15 rounded-full blur-3xl animate-radial-pulse" />
        <div className="absolute bottom-1/3 left-1/3 w-80 h-80 bg-purple-600/15 rounded-full blur-3xl animate-radial-pulse" style={{ animationDelay: '2s' }} />
      </div>

      {/* Main Hero Content - Left Aligned */}
      <div className="relative z-20 max-w-7xl mx-auto px-6 sm:px-8 lg:px-12 w-full">
        <motion.div
          variants={containerVariants}
          initial="hidden"
          animate="visible"
          className="max-w-3xl space-y-8"
        >
          {/* Micro-copy badge */}
          <motion.div variants={itemVariants} className="inline-flex items-center">
            <div className="inline-flex items-center gap-2.5 px-4 py-2 rounded-full bg-blue-950/40 border border-blue-500/30 backdrop-blur-xl shadow-lg shadow-blue-950/50">
              <span className="relative flex h-2.5 w-2.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-cyan-500"></span>
              </span>
              <span className="text-xs font-mono font-semibold tracking-wider text-cyan-300 uppercase">
                Multi-Agent Quantitative Intelligence
              </span>
            </div>
          </motion.div>

          {/* Main Headline */}
          <motion.h1
            variants={itemVariants}
            className="font-heading text-4xl sm:text-6xl lg:text-7xl font-extrabold tracking-tight text-white leading-[1.08]"
          >
            Discover Alpha.{' '}
            <span className="block mt-1 text-transparent bg-clip-text bg-gradient-to-r from-blue-400 via-indigo-300 to-purple-400">
              Understand the Regime.
            </span>
          </motion.h1>

          {/* Supporting Copy */}
          <motion.p
            variants={itemVariants}
            className="text-lg sm:text-xl text-slate-300 font-normal leading-relaxed max-w-2xl"
          >
            Autonomous multi-agent research for discovering robust, regime-aware quantitative factors with transparent explanations.
          </motion.p>

          {/* Action CTAs */}
          <motion.div
            variants={itemVariants}
            className="flex flex-col sm:flex-row items-stretch sm:items-center gap-4 pt-2"
          >
            <Button
              variant="default"
              size="lg"
              onClick={onExploreClick}
              className="bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 text-white hover:from-blue-500 hover:to-purple-500 shadow-glow-blue border border-blue-400/40 text-base font-semibold group"
            >
              <span>Explore the Research</span>
              <ArrowRight className="w-5 h-5 ml-2 group-hover:translate-x-1 transition-transform" />
            </Button>

            <Button
              variant="secondary"
              size="lg"
              onClick={onContactClick}
              className="border-white/15 bg-slate-900/60 backdrop-blur-xl text-slate-200 hover:text-white hover:border-blue-500/40 text-base font-medium"
            >
              Contact Research Team
            </Button>
          </motion.div>

          {/* Live Quantitative Micro-Ticker Indicators */}
          <motion.div
            variants={itemVariants}
            className="pt-8 border-t border-white/10 grid grid-cols-2 sm:grid-cols-4 gap-4"
          >
            <div className="bg-void-850/60 border border-white/10 rounded-xl p-3.5 backdrop-blur-md">
              <div className="flex items-center gap-2 text-blue-400 text-xs font-mono mb-1">
                <Cpu className="w-3.5 h-3.5" />
                <span>AGENT LOOP</span>
              </div>
              <div className="text-xl font-heading font-bold text-white">7 Roles</div>
              <div className="text-[11px] text-slate-400 mt-0.5">Research · Quant · Critic · more</div>
            </div>

            <div className="bg-void-850/60 border border-white/10 rounded-xl p-3.5 backdrop-blur-md">
              <div className="flex items-center gap-2 text-purple-400 text-xs font-mono mb-1">
                <Activity className="w-3.5 h-3.5" />
                <span>REGIME STATE</span>
              </div>
              <div className="text-xl font-heading font-bold text-cyan-300">Walk-forward HMM</div>
              <div className="text-[11px] text-slate-400 mt-0.5">Bull · Bear · High volatility</div>
            </div>

            <div className="bg-void-850/60 border border-white/10 rounded-xl p-3.5 backdrop-blur-md">
              <div className="flex items-center gap-2 text-emerald-400 text-xs font-mono mb-1">
                <LineChart className="w-3.5 h-3.5" />
                <span>UNIVERSE</span>
              </div>
              <div className="text-xl font-heading font-bold text-white">192 US Stocks</div>
              <div className="text-[11px] text-slate-400 mt-0.5">Prices · SEC · news · macro</div>
            </div>

            <div className="bg-void-850/60 border border-white/10 rounded-xl p-3.5 backdrop-blur-md">
              <div className="flex items-center gap-2 text-cyan-400 text-xs font-mono mb-1">
                <ShieldCheck className="w-3.5 h-3.5" />
                <span>EXPLAINABILITY</span>
              </div>
              <div className="text-xl font-heading font-bold text-white">Per formula</div>
              <div className="text-[11px] text-slate-400 mt-0.5">Attribution + Critic reasons</div>
            </div>
          </motion.div>
        </motion.div>
      </div>
    </section>
  );
}
