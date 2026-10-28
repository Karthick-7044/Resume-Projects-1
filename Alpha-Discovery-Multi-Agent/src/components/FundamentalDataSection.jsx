import React, { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, BarChart3, CalendarDays, Database, FileText, Search, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

const displayValue = (value, options = {}) => {
  if (value === null || value === undefined || value === '' || Number.isNaN(value)) return 'N/A';
  if (typeof value === 'number') {
    if (options.percent) return `${(value * 100).toFixed(2)}%`;
    return Math.abs(value) >= 1000 ? value.toLocaleString(undefined, { maximumFractionDigits: 2 }) : value.toFixed(3);
  }
  return value;
};

const metricLabels = {
  revenue: 'Revenue',
  net_income: 'Net Income',
  total_assets: 'Total Assets',
  total_liabilities: 'Total Liabilities',
  shareholders_equity: 'Shareholders Equity',
  operating_income: 'Operating Income',
  cash: 'Cash',
  debt: 'Debt',
  eps: 'EPS',
  roe: 'ROE',
  revenue_growth: 'Revenue Growth',
  debt_to_equity: 'Debt / Equity',
  profit_margin: 'Profit Margin',
  eps_growth: 'EPS Growth',
};

export function FundamentalDataSection() {
  const [ticker, setTicker] = useState('AAPL');
  const [activeTicker, setActiveTicker] = useState('AAPL');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [qualityRows, setQualityRows] = useState([]);
  const [fundamentalRows, setFundamentalRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [warning, setWarning] = useState('');

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setWarning('');
      const params = new URLSearchParams({ limit: '25', offset: '0' });
      if (startDate) params.set('start_date', startDate);
      if (endDate) params.set('end_date', endDate);

      try {
        const [qualityResponse, fundamentalsResponse] = await Promise.all([
          fetch(`${API_BASE_URL}/api/fundamentals/quality?limit=5000`),
          fetch(`${API_BASE_URL}/api/fundamentals/${activeTicker}?${params.toString()}`),
        ]);
        const quality = qualityResponse.ok ? await qualityResponse.json() : { rows: [] };
        const fundamentals = fundamentalsResponse.ok ? await fundamentalsResponse.json() : { rows: [] };
        if (!cancelled) {
          setQualityRows(quality.rows || []);
          setFundamentalRows(fundamentals.rows || []);
          if (!qualityResponse.ok || !fundamentalsResponse.ok) {
            setWarning('Fundamental pipeline output is not available for the selected filters.');
          }
        }
      } catch (error) {
        if (!cancelled) {
          setQualityRows([]);
          setFundamentalRows([]);
          setWarning('Backend API is not reachable.');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [activeTicker, startDate, endDate]);

  const summary = useMemo(() => {
    const byTicker = new Map();
    qualityRows.forEach((row) => {
      byTicker.set(row.ticker, row.overall_status);
    });
    const statuses = Array.from(byTicker.values());
    const coverage = qualityRows.length
      ? qualityRows.reduce((sum, row) => sum + Number(row.coverage_percentage || 0), 0) / qualityRows.length
      : 0;
    return {
      processed: byTicker.size,
      passed: statuses.filter((status) => status === 'PASS').length,
      flagged: statuses.filter((status) => status !== 'PASS').length,
      coverage,
    };
  }, [qualityRows]);

  const metricCoverage = useMemo(() => {
    const grouped = new Map();
    qualityRows.forEach((row) => {
      const item = grouped.get(row.metric) || { metric: row.metric, total: 0, available: 0 };
      item.total += 1;
      if (row.available) item.available += 1;
      grouped.set(row.metric, item);
    });
    return Array.from(grouped.values())
      .map((item) => ({ ...item, percentage: item.total ? (item.available / item.total) * 100 : 0 }))
      .sort((a, b) => a.metric.localeCompare(b.metric));
  }, [qualityRows]);

  const sortedFundamentalRows = useMemo(() => {
    return [...fundamentalRows].sort((a, b) => {
      const dateA = new Date(a.filing_date || a.period_end || 0).getTime();
      const dateB = new Date(b.filing_date || b.period_end || 0).getTime();
      return dateB - dateA;
    });
  }, [fundamentalRows]);

  const latest = sortedFundamentalRows[0] || {};

  const applyTicker = () => {
    setActiveTicker((ticker || '').trim().toUpperCase());
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-mono text-cyan-300">
            <Database className="w-4 h-4" />
            <span>SEC EDGAR FUNDAMENTALS</span>
          </div>
          <h3 className="mt-2 font-heading text-2xl font-bold text-white">Fundamental Data</h3>
        </div>
        <div className="flex flex-col sm:flex-row gap-2 w-full lg:w-auto">
          <Input value={ticker} onChange={(event) => setTicker(event.target.value)} className="h-9 sm:w-24 uppercase" />
          <Input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} className="h-9" />
          <Input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} className="h-9" />
          <Button onClick={applyTicker} size="sm" className="h-9">
            <Search className="w-4 h-4 mr-1.5" />
            Load
          </Button>
        </div>
      </div>

      {warning && (
        <div className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-950/30 px-4 py-3 text-sm text-amber-200">
          <AlertTriangle className="w-4 h-4" />
          <span>{warning}</span>
        </div>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          ['Companies Processed', summary.processed, FileText],
          ['Companies Passed', summary.passed, ShieldCheck],
          ['Companies Flagged', summary.flagged, AlertTriangle],
          ['Coverage', `${summary.coverage.toFixed(1)}%`, BarChart3],
        ].map(([label, value, Icon]) => (
          <div key={label} className="rounded-lg border border-white/10 bg-void-900/90 p-4">
            <div className="flex items-center gap-2 text-[11px] font-mono text-slate-400">
              <Icon className="w-3.5 h-3.5 text-cyan-300" />
              <span>{label}</span>
            </div>
            <div className="mt-2 text-2xl font-heading font-bold text-white">{loading ? 'N/A' : value}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="rounded-lg border border-white/10 bg-void-900/90 p-4 xl:col-span-1">
          <div className="mb-3 flex items-center gap-2 text-xs font-mono text-slate-300">
            <BarChart3 className="w-4 h-4 text-cyan-300" />
            <span>METRIC COVERAGE</span>
          </div>
          <div className="space-y-2 max-h-72 overflow-auto pr-1">
            {metricCoverage.map((item) => (
              <div key={item.metric} className="space-y-1">
                <div className="flex justify-between text-xs">
                  <span className="text-slate-300">{metricLabels[item.metric] || item.metric}</span>
                  <span className="font-mono text-cyan-300">{item.percentage.toFixed(0)}%</span>
                </div>
                <div className="h-1.5 rounded-full bg-slate-800">
                  <div className="h-1.5 rounded-full bg-cyan-400" style={{ width: `${item.percentage}%` }} />
                </div>
              </div>
            ))}
            {!metricCoverage.length && <div className="text-sm text-slate-400">N/A</div>}
          </div>
        </div>

        <div className="rounded-lg border border-white/10 bg-void-900/90 p-4 xl:col-span-2 overflow-hidden">
          <div className="mb-3 flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-xs font-mono text-slate-300">
              <CalendarDays className="w-4 h-4 text-cyan-300" />
              <span>{activeTicker} VALUES BY FILING DATE</span>
            </div>
            <span className="text-[11px] font-mono text-slate-500">{loading ? 'Loading' : `${fundamentalRows.length} rows`}</span>
          </div>
          <div className="overflow-auto">
            <table className="w-full min-w-[760px] text-left text-xs">
              <thead className="text-slate-400">
                <tr className="border-b border-white/10">
                  <th className="py-2 pr-3 font-mono">Filing</th>
                  <th className="py-2 pr-3 font-mono">Period End</th>
                  <th className="py-2 pr-3 font-mono">Revenue</th>
                  <th className="py-2 pr-3 font-mono">ROE</th>
                  <th className="py-2 pr-3 font-mono">Debt / Equity</th>
                  <th className="py-2 pr-3 font-mono">Margin</th>
                  <th className="py-2 pr-3 font-mono">Accession</th>
                </tr>
              </thead>
              <tbody className="text-slate-200">
                {sortedFundamentalRows.map((row, idx) => (
                  <tr key={`${row.ticker}-${row.filing_date}-${row.accession}-${idx}`} className="border-b border-white/5">
                    <td className="py-2 pr-3 font-mono">{displayValue(row.filing_date)}</td>
                    <td className="py-2 pr-3 font-mono">{displayValue(row.period_end)}</td>
                    <td className="py-2 pr-3 font-mono">{displayValue(row.revenue)}</td>
                    <td className="py-2 pr-3 font-mono">{displayValue(row.roe, { percent: true })}</td>
                    <td className="py-2 pr-3 font-mono">{displayValue(row.debt_to_equity)}</td>
                    <td className="py-2 pr-3 font-mono">{displayValue(row.profit_margin, { percent: true })}</td>
                    <td className="py-2 pr-3 font-mono text-slate-400">{displayValue(row.accession)}</td>
                  </tr>
                ))}
                {!fundamentalRows.length && (
                  <tr>
                    <td className="py-4 text-slate-400" colSpan="7">N/A</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="rounded-lg border border-white/10 bg-void-900/90 p-4">
        <div className="mb-3 text-xs font-mono text-slate-300">DATA AVAILABILITY</div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
          {['fundamental_filing_date', 'fundamental_period_end', 'revenue', 'profit_margin'].map((key) => (
            <div key={key} className="rounded-md bg-black/30 p-3">
              <div className="font-mono text-slate-500">{key}</div>
              <div className="mt-1 font-mono text-slate-100">{displayValue(latest[key] ?? latest[key.replace('fundamental_', '')])}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

