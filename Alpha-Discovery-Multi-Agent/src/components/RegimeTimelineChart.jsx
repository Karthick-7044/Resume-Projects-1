import React, { useEffect, useState, useMemo } from 'react';
import { Compass, PieChart, Activity, RefreshCw, AlertTriangle, CheckCircle2 } from 'lucide-react';
import { fetchRegimeData } from '@/lib/api';
import { Button } from '@/components/ui/button';

export function RegimeTimelineChart({ limit = 500 }) {
  const [regimes, setRegimes] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [hoveredRegime, setHoveredRegime] = useState(null);

  useEffect(() => {
    let isCancelled = false;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const rows = await fetchRegimeData({ limit });
        if (!isCancelled) {
          setRegimes(rows || []);
          if (rows && rows.length > 0) {
            setHoveredRegime(rows[rows.length - 1]);
          }
        }
      } catch (err) {
        if (!isCancelled) {
          setError(err.message || 'Failed to load HMM market regime data');
        }
      } finally {
        if (!isCancelled) setLoading(false);
      }
    };

    load();
    return () => { isCancelled = true; };
  }, [limit]);

  const getRegimeColor = (label = '') => {
    const l = String(label).toLowerCase();
    if (l.includes('bull') && l.includes('low')) return { bg: 'bg-emerald-500', text: 'text-emerald-300', badge: 'bg-emerald-950/80 border-emerald-500/40 text-emerald-300', hex: '#10b981' };
    if (l.includes('bull') && l.includes('high')) return { bg: 'bg-cyan-500', text: 'text-cyan-300', badge: 'bg-cyan-950/80 border-cyan-500/40 text-cyan-300', hex: '#06b6d4' };
    if (l.includes('bear') && l.includes('high')) return { bg: 'bg-rose-500', text: 'text-rose-300', badge: 'bg-rose-950/80 border-rose-500/40 text-rose-300', hex: '#f43f5e' };
    if (l.includes('bear') && l.includes('low')) return { bg: 'bg-amber-500', text: 'text-amber-300', badge: 'bg-amber-950/80 border-amber-500/40 text-amber-300', hex: '#f59e0b' };
    return { bg: 'bg-blue-500', text: 'text-blue-300', badge: 'bg-blue-950/80 border-blue-500/40 text-blue-300', hex: '#3b82f6' };
  };

  const distribution = useMemo(() => {
    if (!regimes.length) return {};
    const counts = {};
    regimes.forEach(r => {
      const key = r.market_regime || `State ${r.hmm_state}`;
      counts[key] = (counts[key] || 0) + 1;
    });
    return counts;
  }, [regimes]);

  const active = hoveredRegime || (regimes.length ? regimes[regimes.length - 1] : null);

  return (
    <div className="bg-void-900/90 border border-white/10 rounded-2xl p-6 space-y-6 shadow-xl relative">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-white/10 pb-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="p-1.5 rounded-lg bg-purple-950/80 border border-purple-500/30 text-purple-400">
              <Compass className="w-4 h-4" />
            </span>
            <h3 className="font-heading font-bold text-lg text-white">
              HMM Market Regime Sequence & Classification
            </h3>
          </div>
          <p className="text-xs text-slate-400">
            Hidden Markov Model (HMM) fitted on benchmark SPY return & volatility with rule-based labeling
          </p>
        </div>

        {active && (
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono text-slate-400">Current State:</span>
            <span className={`px-3 py-1 rounded-full text-xs font-mono font-semibold border ${getRegimeColor(active.market_regime).badge}`}>
              {active.market_regime || `HMM State ${active.hmm_state}`}
            </span>
          </div>
        )}
      </div>

      {error && (
        <div className="p-3 rounded-lg bg-rose-950/30 border border-rose-500/30 text-rose-300 text-xs flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Breakdown Badges */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {Object.entries(distribution).map(([name, count]) => {
          const styling = getRegimeColor(name);
          const pct = ((count / regimes.length) * 100).toFixed(1);
          return (
            <div key={name} className="bg-black/30 border border-white/5 rounded-xl p-3">
              <div className="flex items-center gap-2">
                <span className={`w-2.5 h-2.5 rounded-full ${styling.bg}`} />
                <span className="text-xs font-medium text-slate-200 truncate">{name}</span>
              </div>
              <div className="flex items-baseline justify-between mt-2">
                <span className="text-lg font-heading font-bold text-white">{count} days</span>
                <span className="text-xs font-mono text-cyan-300">{pct}%</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Interactive Timeline Bar Matrix */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs font-mono text-slate-400">
          <span>REGIME TIMELINE ({regimes.length} trading days)</span>
          <span>Hover on timeline to inspect day</span>
        </div>

        <div className="relative h-14 bg-void-950/80 rounded-xl border border-white/10 p-1.5 flex gap-[1px] items-stretch overflow-hidden">
          {regimes.map((r, i) => {
            const colors = getRegimeColor(r.market_regime);
            const isHovered = hoveredRegime?.date === r.date;
            return (
              <div
                key={r.date || i}
                onMouseEnter={() => setHoveredRegime(r)}
                className={`flex-1 min-w-[2px] rounded-[1px] transition-all cursor-pointer ${colors.bg} ${
                  isHovered ? 'scale-y-125 brightness-150 z-10 ring-2 ring-white' : 'opacity-80 hover:opacity-100'
                }`}
                title={`${r.date?.slice(0, 10)}: ${r.market_regime || `State ${r.hmm_state}`}`}
              />
            );
          })}
        </div>

        {/* Date Anchors */}
        {regimes.length > 0 && (
          <div className="flex justify-between text-[10px] font-mono text-slate-500 px-1">
            <span>{regimes[0]?.date?.slice(0, 10)}</span>
            <span>{regimes[Math.floor(regimes.length / 2)]?.date?.slice(0, 10)}</span>
            <span>{regimes[regimes.length - 1]?.date?.slice(0, 10)}</span>
          </div>
        )}
      </div>

      {/* Selected Day Telemetry Snapshot */}
      {active && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 p-4 rounded-xl bg-black/40 border border-white/5 text-xs font-mono">
          <div>
            <div className="text-[10px] text-slate-500">DATE</div>
            <div className="text-white font-semibold">{active.date?.slice(0, 10)}</div>
          </div>
          <div>
            <div className="text-[10px] text-slate-500">HMM STATE</div>
            <div className="text-cyan-300 font-bold">State {active.hmm_state}</div>
          </div>
          <div>
            <div className="text-[10px] text-slate-500">REGIME LABEL</div>
            <div className={`${getRegimeColor(active.market_regime).text} font-semibold truncate`}>
              {active.market_regime}
            </div>
          </div>
          <div>
            <div className="text-[10px] text-slate-500">BENCHMARK RETURN</div>
            <div className={active.benchmark_return >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
              {typeof active.benchmark_return === 'number' ? `${(active.benchmark_return * 100).toFixed(2)}%` : 'N/A'}
            </div>
          </div>
          <div>
            <div className="text-[10px] text-slate-500">BENCHMARK MOM 20D</div>
            <div className="text-slate-200">
              {typeof active.benchmark_momentum_20d === 'number' ? `${(active.benchmark_momentum_20d * 100).toFixed(2)}%` : 'N/A'}
            </div>
          </div>
          <div>
            <div className="text-[10px] text-slate-500">BENCHMARK VOL 20D</div>
            <div className="text-purple-300">
              {typeof active.benchmark_volatility_20d === 'number' ? `${(active.benchmark_volatility_20d * 100).toFixed(2)}%` : 'N/A'}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
