import React, { useEffect, useRef, useState } from 'react';
import { motion, useScroll, useSpring, useInView, useReducedMotion } from 'framer-motion';

/** Thin gradient bar showing how far the page has been read. */
export function ScrollProgress() {
  const { scrollYProgress } = useScroll();
  const scaleX = useSpring(scrollYProgress, { stiffness: 140, damping: 24, mass: 0.3 });
  return (
    <motion.div
      aria-hidden
      style={{ scaleX }}
      className="fixed top-0 left-0 right-0 h-[2px] origin-left z-[60] bg-gradient-to-r from-cyan-300 via-indigo-400 to-fuchsia-400"
    />
  );
}

/** Slow drifting colour fields that sit behind every section below the landing page. */
export function Aurora() {
  return (
    <div aria-hidden className="aurora-layer pointer-events-none fixed inset-0 -z-0 overflow-hidden">
      <div className="absolute -top-[10%] -left-[8%] w-[55vw] h-[55vw] max-w-[820px] max-h-[820px] rounded-full bg-indigo-600/20 blur-[120px] animate-drift" />
      <div className="absolute top-[35%] -right-[10%] w-[50vw] h-[50vw] max-w-[760px] max-h-[760px] rounded-full bg-cyan-500/[0.14] blur-[130px] animate-driftSlow" />
      <div className="absolute -bottom-[12%] left-[20%] w-[45vw] h-[45vw] max-w-[700px] max-h-[700px] rounded-full bg-fuchsia-600/[0.14] blur-[130px] animate-drift" />
      <div className="absolute inset-0 grain" />
    </div>
  );
}

/** Fade, lift and un-blur a block as it enters the viewport. */
export function Reveal({ children, delay = 0, y = 28, className = '', as = 'div' }) {
  const reduce = useReducedMotion();
  const Tag = motion[as] || motion.div;
  return (
    <Tag
      className={className}
      initial={reduce ? false : { opacity: 0, y, filter: 'blur(8px)' }}
      whileInView={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
      viewport={{ once: true, margin: '-8% 0px' }}
      transition={{ duration: 0.9, delay, ease: [0.16, 1, 0.3, 1] }}
    >
      {children}
    </Tag>
  );
}

/** Number that counts up once it scrolls into view. */
export function CountUp({ to, decimals = 0, duration = 1.6, prefix = '', suffix = '' }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: '-10% 0px' });
  const reduce = useReducedMotion();
  const [v, setV] = useState(reduce ? to : 0);
  useEffect(() => {
    if (!inView || reduce) return;
    let raf;
    const t0 = performance.now();
    const tick = (now) => {
      const p = Math.min((now - t0) / (duration * 1000), 1);
      setV(to * (1 - Math.pow(1 - p, 4)));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [inView, to, duration, reduce]);
  return <span ref={ref} className="tabular-nums">{prefix}{v.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}{suffix}</span>;
}

/** Continuous marquee of pipeline facts. */
export function Ticker({ items }) {
  const row = [...items, ...items];
  return (
    <div aria-hidden className="ticker relative overflow-hidden py-5 select-none">
      <div className="flex w-max gap-12 animate-marquee whitespace-nowrap">
        {row.map((it, i) => (
          <span key={i} className="flex items-center gap-3 text-sm font-mono text-slate-400">
            <span className="h-1.5 w-1.5 rounded-full bg-cyan-400/80" />
            <span className="text-slate-500">{it[0]}</span>
            <span className="text-slate-100">{it[1]}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

/** Flowing signal lines used as a section divider. */
export function WaveDivider({ flip = false }) {
  const d = 'M0 60 C 150 10, 300 110, 450 60 S 750 10, 900 60 S 1050 110, 1200 60';
  return (
    <div aria-hidden className={`relative h-24 overflow-hidden ${flip ? 'rotate-180' : ''}`}>
      <div className="absolute inset-y-0 left-0 w-[200%] flex animate-waveFlow">
        {[0, 1].map((k) => (
          <svg key={k} viewBox="0 0 1200 120" preserveAspectRatio="none" className="h-full w-1/2">
            <defs>
              <linearGradient id={`wg${k}${flip ? 'f' : ''}`} x1="0" x2="1">
                <stop offset="0" stopColor="#22d3ee" stopOpacity="0" />
                <stop offset="0.5" stopColor="#818cf8" stopOpacity="0.9" />
                <stop offset="1" stopColor="#e879f9" stopOpacity="0" />
              </linearGradient>
            </defs>
            <path d={d} fill="none" stroke={`url(#wg${k}${flip ? 'f' : ''})`} strokeWidth="1.4" />
            <path d={d} fill="none" stroke={`url(#wg${k}${flip ? 'f' : ''})`} strokeWidth="1" opacity="0.5" transform="translate(0 14) scale(1 .8)" />
            <path d={d} fill="none" stroke={`url(#wg${k}${flip ? 'f' : ''})`} strokeWidth="0.8" opacity="0.3" transform="translate(0 -12) scale(1 1.15)" />
          </svg>
        ))}
      </div>
    </div>
  );
}

/** Key numbers of the project with animated counters. */
export function KeyNumbers() {
  const stats = [
    { to: 192, label: 'US stocks in the universe' },
    { to: 725193, label: 'news headlines scored by FinBERT' },
    { to: 112, label: 'point-in-time features' },
    { to: 454, label: 'untouched test days (2025–26)' },
  ];
  return (
    <section aria-label="Key numbers" className="relative py-10">
      <div className="max-w-7xl mx-auto px-4 sm:px-8 lg:px-12">
        <Reveal>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-x-6 gap-y-10">
            {stats.map((s) => (
              <div key={s.label} className="stat">
                <div className="stat-num"><CountUp to={s.to} /></div>
                <div className="stat-label">{s.label}</div>
              </div>
            ))}
          </div>
        </Reveal>
      </div>
    </section>
  );
}

export const TICKER_ITEMS = [
  ['universe', '192 US stocks'], ['panel', '675,233 rows × 181 columns'], ['regimes', 'walk-forward HMM'],
  ['news', 'FNSPID + Google News'], ['sentiment', 'FinBERT P(pos) − P(neg)'], ['costs', '10 bps per trade'],
  ['validation', 'Holm · White · deflated Sharpe'], ['critic', 'deterministic, no LLM'], ['test window', '2025-01 → 2026-10'],
  ['agents', 'research → quant → critic'], ['tests', '91 passing'],
];
