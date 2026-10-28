import React, { useEffect, useState, useMemo } from 'react';
import { TrendingUp, BarChart2, Eye, EyeOff, Calendar, AlertCircle } from 'lucide-react';
import { fetchMarketData } from '@/lib/api';
import { Button } from '@/components/ui/button';

export function MarketTechnicalChart({ ticker = 'AAPL', startDate, endDate }) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showSMA20, setShowSMA20] = useState(true);
  const [showSMA50, setShowSMA50] = useState(true);
  const [showSMA200, setShowSMA200] = useState(true);
  const [hoveredPoint, setHoveredPoint] = useState(null);

  useEffect(() => {
    let isCancelled = false;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const rows = await fetchMarketData(ticker, {
          start_date: startDate,
          end_date: endDate,
          limit: 1000
        });
        if (!isCancelled) {
          setData(rows || []);
          if (rows && rows.length > 0) {
            setHoveredPoint(rows[rows.length - 1]);
          }
        }
      } catch (err) {
        if (!isCancelled) {
          setError(err.message || 'Failed to load market chart data');
          setData([]);
        }
      } finally {
        if (!isCancelled) setLoading(false);
      }
    };

    load();
    return () => { isCancelled = true; };
  }, [ticker, startDate, endDate]);

  // Compute SVG plotting coordinates
  const chartMetrics = useMemo(() => {
    if (!data.length) return null;

    const validCloses = data.map(d => d.close).filter(v => v !== null && !isNaN(v));
    const validSma20 = showSMA20 ? data.map(d => d.sma_20).filter(v => v !== null && !isNaN(v)) : [];
    const validSma50 = showSMA50 ? data.map(d => d.sma_50).filter(v => v !== null && !isNaN(v)) : [];
    const validSma200 = showSMA200 ? data.map(d => d.sma_200).filter(v => v !== null && !isNaN(v)) : [];

    const allPrices = [...validCloses, ...validSma20, ...validSma50, ...validSma200];
    const minPrice = Math.min(...allPrices) * 0.98;
    const maxPrice = Math.max(...allPrices) * 1.02;

    const maxVolume = Math.max(...data.map(d => d.volume || 0), 1);

    return { minPrice, maxPrice, maxVolume };
  }, [data, showSMA20, showSMA50, showSMA200]);

  const width = 800;
  const height = 320;
  const padding = { top: 20, right: 60, bottom: 40, left: 20 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;

  const getX = (idx) => {
    if (data.length <= 1) return padding.left;
    return padding.left + (idx / (data.length - 1)) * plotWidth;
  };

  const getY = (val) => {
    if (!chartMetrics || chartMetrics.maxPrice === chartMetrics.minPrice) return height / 2;
    const norm = (val - chartMetrics.minPrice) / (chartMetrics.maxPrice - chartMetrics.minPrice);
    return padding.top + (1 - norm) * plotHeight;
  };

  const generateLinePath = (key) => {
    if (!data.length) return '';
    let path = '';
    let first = true;

    data.forEach((d, i) => {
      const val = d[key];
      if (val !== null && val !== undefined && !isNaN(val)) {
        const x = getX(i);
        const y = getY(val);
        if (first) {
          path += `M ${x.toFixed(1)} ${y.toFixed(1)}`;
          first = false;
        } else {
          path += ` L ${x.toFixed(1)} ${y.toFixed(1)}`;
        }
      }
    });
    return path;
  };

  const generateAreaPath = () => {
    const line = generateLinePath('close');
    if (!line) return '';
    const lastX = getX(data.length - 1);
    const firstX = getX(0);
    const bottomY = padding.top + plotHeight;
    return `${line} L ${lastX.toFixed(1)} ${bottomY} L ${firstX.toFixed(1)} ${bottomY} Z`;
  };

  const active = hoveredPoint || (data.length ? data[data.length - 1] : null);

  return (
    <div className="bg-void-900/90 border border-white/10 rounded-2xl p-6 space-y-5 shadow-xl relative">
      {/* Header with Title & Legend Toggles */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 border-b border-white/10 pb-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="p-1.5 rounded-lg bg-blue-950/80 border border-blue-500/30 text-cyan-400">
              <TrendingUp className="w-4 h-4" />
            </span>
            <h3 className="font-heading font-bold text-lg text-white">
              {ticker} Historical Price & Moving Averages
            </h3>
            <span className="text-xs font-mono text-cyan-300 bg-blue-950/60 border border-blue-500/30 px-2 py-0.5 rounded">
              {data.length} trading days
            </span>
          </div>
          <p className="text-xs text-slate-400">
            Real-time daily OHLCV dataset linked with SMA overlays & technical oscillators
          </p>
        </div>

        {/* Legend Controls */}
        <div className="flex flex-wrap items-center gap-2 text-xs font-mono">
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-black/40 border border-cyan-500/40 text-cyan-300">
            <span className="w-2.5 h-0.5 bg-cyan-400 rounded-full" />
            <span>Close Price</span>
          </div>

          <button
            onClick={() => setShowSMA20(!showSMA20)}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg border transition-all ${
              showSMA20
                ? 'bg-amber-950/40 border-amber-500/40 text-amber-300'
                : 'bg-black/20 border-white/10 text-slate-500 line-through'
            }`}
          >
            <span className="w-2.5 h-0.5 bg-amber-400 rounded-full" />
            <span>SMA 20</span>
          </button>

          <button
            onClick={() => setShowSMA50(!showSMA50)}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg border transition-all ${
              showSMA50
                ? 'bg-emerald-950/40 border-emerald-500/40 text-emerald-300'
                : 'bg-black/20 border-white/10 text-slate-500 line-through'
            }`}
          >
            <span className="w-2.5 h-0.5 bg-emerald-400 rounded-full" />
            <span>SMA 50</span>
          </button>

          <button
            onClick={() => setShowSMA200(!showSMA200)}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg border transition-all ${
              showSMA200
                ? 'bg-purple-950/40 border-purple-500/40 text-purple-300'
                : 'bg-black/20 border-white/10 text-slate-500 line-through'
            }`}
          >
            <span className="w-2.5 h-0.5 bg-purple-400 rounded-full" />
            <span>SMA 200</span>
          </button>
        </div>
      </div>

      {/* Real-time Hovered Snapshot Telemetry Bar */}
      {active && (
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2.5 p-3 rounded-xl bg-black/40 border border-white/5 text-xs font-mono">
          <div>
            <div className="text-[10px] text-slate-500">DATE</div>
            <div className="text-white font-semibold">{active.date?.slice(0, 10)}</div>
          </div>
          <div>
            <div className="text-[10px] text-slate-500">CLOSE</div>
            <div className="text-cyan-300 font-bold">${typeof active.close === 'number' ? active.close.toFixed(2) : 'N/A'}</div>
          </div>
          <div>
            <div className="text-[10px] text-slate-500">SMA 20</div>
            <div className="text-amber-300">{typeof active.sma_20 === 'number' ? `$${active.sma_20.toFixed(2)}` : 'N/A'}</div>
          </div>
          <div>
            <div className="text-[10px] text-slate-500">SMA 50</div>
            <div className="text-emerald-300">{typeof active.sma_50 === 'number' ? `$${active.sma_50.toFixed(2)}` : 'N/A'}</div>
          </div>
          <div>
            <div className="text-[10px] text-slate-500">SMA 200</div>
            <div className="text-purple-300">{typeof active.sma_200 === 'number' ? `$${active.sma_200.toFixed(2)}` : 'N/A'}</div>
          </div>
          <div>
            <div className="text-[10px] text-slate-500">RSI (14)</div>
            <div className={`${(active.rsi_14 > 70) ? 'text-rose-400' : (active.rsi_14 < 30) ? 'text-emerald-400' : 'text-slate-200'}`}>
              {typeof active.rsi_14 === 'number' ? active.rsi_14.toFixed(1) : 'N/A'}
            </div>
          </div>
          <div>
            <div className="text-[10px] text-slate-500">VOLUME</div>
            <div className="text-slate-300">{active.volume ? (active.volume / 1e6).toFixed(1) + 'M' : 'N/A'}</div>
          </div>
        </div>
      )}

      {/* Chart Canvas */}
      <div className="relative w-full h-[320px] bg-void-950/80 rounded-xl border border-white/5 overflow-hidden">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-void-950/80 z-20">
            <div className="flex items-center gap-2 text-xs font-mono text-cyan-300">
              <span className="w-4 h-4 rounded-full border-2 border-cyan-400 border-t-transparent animate-spin" />
              <span>Fetching DuckDB Market Records...</span>
            </div>
          </div>
        )}

        {error && !loading && (
          <div className="absolute inset-0 flex items-center justify-center p-6 text-center text-xs text-rose-400">
            <AlertCircle className="w-5 h-5 mr-2 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {!loading && !error && data.length > 0 && (
          <svg
            viewBox={`0 0 ${width} ${height}`}
            className="w-full h-full cursor-crosshair select-none"
            preserveAspectRatio="none"
            onMouseMove={(e) => {
              const rect = e.currentTarget.getBoundingClientRect();
              const relX = e.clientX - rect.left;
              const ratio = Math.max(0, Math.min(1, (relX - (padding.left / width) * rect.width) / ((plotWidth / width) * rect.width)));
              const idx = Math.round(ratio * (data.length - 1));
              if (data[idx]) setHoveredPoint(data[idx]);
            }}
            onMouseLeave={() => setHoveredPoint(data[data.length - 1])}
          >
            <defs>
              <linearGradient id="priceGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#06b6d4" stopOpacity="0.25" />
                <stop offset="100%" stopColor="#06b6d4" stopOpacity="0.0" />
              </linearGradient>
            </defs>

            {/* Horizontal Grid lines */}
            {[0, 0.25, 0.5, 0.75, 1].map((pct, i) => {
              const yVal = padding.top + pct * plotHeight;
              const priceLabel = chartMetrics ? (chartMetrics.maxPrice - pct * (chartMetrics.maxPrice - chartMetrics.minPrice)).toFixed(2) : 0;
              return (
                <g key={i}>
                  <line
                    x1={padding.left}
                    y1={yVal}
                    x2={width - padding.right}
                    y2={yVal}
                    stroke="rgba(255,255,255,0.06)"
                    strokeDasharray="4 4"
                  />
                  <text
                    x={width - padding.right + 8}
                    y={yVal + 3}
                    fill="#64748b"
                    fontSize="9"
                    fontFamily="monospace"
                  >
                    ${priceLabel}
                  </text>
                </g>
              );
            })}

            {/* Volume Histogram (bottom layer) */}
            {data.map((d, i) => {
              if (!d.volume || !chartMetrics) return null;
              const x = getX(i);
              const barHeight = (d.volume / chartMetrics.maxVolume) * (plotHeight * 0.25);
              const y = padding.top + plotHeight - barHeight;
              const barWidth = Math.max(1, plotWidth / data.length - 1);
              const isGreen = (d.daily_return || 0) >= 0;
              return (
                <rect
                  key={`vol-${i}`}
                  x={x - barWidth / 2}
                  y={y}
                  width={barWidth}
                  height={barHeight}
                  fill={isGreen ? 'rgba(16, 185, 129, 0.25)' : 'rgba(244, 63, 94, 0.25)'}
                />
              );
            })}

            {/* Price Area Fill */}
            <path d={generateAreaPath()} fill="url(#priceGradient)" />

            {/* Price Main Line */}
            <path
              d={generateLinePath('close')}
              fill="none"
              stroke="#06b6d4"
              strokeWidth="2"
              strokeLinecap="round"
            />

            {/* SMA Overlays */}
            {showSMA20 && (
              <path
                d={generateLinePath('sma_20')}
                fill="none"
                stroke="#f59e0b"
                strokeWidth="1.5"
                strokeDasharray="2 2"
              />
            )}
            {showSMA50 && (
              <path
                d={generateLinePath('sma_50')}
                fill="none"
                stroke="#10b981"
                strokeWidth="1.5"
                strokeDasharray="3 3"
              />
            )}
            {showSMA200 && (
              <path
                d={generateLinePath('sma_200')}
                fill="none"
                stroke="#a855f7"
                strokeWidth="1.5"
              />
            )}

            {/* Active Hover Crosshair */}
            {hoveredPoint && (
              (() => {
                const idx = data.findIndex(d => d.date === hoveredPoint.date);
                if (idx === -1) return null;
                const hx = getX(idx);
                const hy = getY(hoveredPoint.close);
                return (
                  <g>
                    <line
                      x1={hx}
                      y1={padding.top}
                      x2={hx}
                      y2={padding.top + plotHeight}
                      stroke="#38bdf8"
                      strokeWidth="1"
                      strokeDasharray="2 2"
                    />
                    <circle
                      cx={hx}
                      cy={hy}
                      r="4"
                      fill="#06b6d4"
                      stroke="#ffffff"
                      strokeWidth="2"
                    />
                  </g>
                );
              })()
            )}
          </svg>
        )}
      </div>

      {/* Date Span Footer */}
      {data.length > 0 && (
        <div className="flex items-center justify-between text-[11px] font-mono text-slate-500 pt-1">
          <span>Start: {data[0]?.date?.slice(0, 10)}</span>
          <span className="text-slate-400">Hover across canvas to inspect daily values</span>
          <span>End: {data[data.length - 1]?.date?.slice(0, 10)}</span>
        </div>
      )}
    </div>
  );
}
