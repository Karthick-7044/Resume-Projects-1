/**
 * Centralized API Client for Alpha Discovery Quantitative Engine
 * Connects directly to FastAPI backend and DuckDB analytical storage.
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

/**
 * Helper to execute fetch requests with error handling
 */
async function request(endpoint, params = {}) {
  const url = new URL(`${API_BASE_URL}${endpoint}`);
  Object.entries(params).forEach(([key, val]) => {
    if (val !== undefined && val !== null && val !== '') {
      url.searchParams.append(key, String(val));
    }
  });

  const response = await fetch(url.toString(), {
    headers: {
      'Accept': 'application/json',
    },
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`API error (${response.status}): ${errorText || response.statusText}`);
  }

  return response.json();
}

/**
 * Fetch universe of tracked equities
 */
export async function fetchUniverse() {
  return request('/api/universe');
}

/**
 * Fetch paginated Daily Stock Panel rows from DuckDB master panel table
 */
export async function fetchDailyStockPanel({ ticker, start_date, end_date, limit = 50, offset = 0 } = {}) {
  return request('/api/panel', { ticker, start_date, end_date, limit, offset });
}

/**
 * Fetch historical OHLCV and technical indicators for a ticker
 */
export async function fetchMarketData(ticker, { start_date, end_date, limit = 1000 } = {}) {
  if (!ticker) throw new Error('Ticker is required for market data');
  return request(`/api/market/${ticker.toUpperCase()}`, { start_date, end_date, limit });
}

/**
 * Fetch Point-in-Time fundamental metrics and valuation ratios
 */
export async function fetchFundamentalsData(ticker, { limit = 500 } = {}) {
  if (!ticker) throw new Error('Ticker is required for fundamentals');
  return request(`/api/fundamentals/${ticker.toUpperCase()}`, { limit });
}

/**
 * Fetch fundamental QA records
 */
export async function fetchFundamentalsQuality({ limit = 500 } = {}) {
  return request('/api/fundamentals/quality', { limit });
}

/**
 * Fetch sentiment and news event metrics for a ticker
 */
export async function fetchNewsData(ticker, { limit = 500 } = {}) {
  if (!ticker) throw new Error('Ticker is required for news data');
  return request(`/api/news/${ticker.toUpperCase()}`, { limit });
}

/**
 * Fetch macro HMM market regime history
 */
export async function fetchRegimeData({ limit = 1000 } = {}) {
  return request('/api/regime', { limit });
}

/**
 * Fetch real-time pipeline status, table counts, and QA summaries
 */
export async function fetchPipelineStatus() {
  return request('/api/pipeline/status');
}

export { API_BASE_URL };

/**
 * News archive: latest validated articles, provider coverage and QA summary
 */
export async function fetchNewsArticles({ ticker, limit = 50, offset = 0, start_date, end_date } = {}) {
  return request('/api/news', { ticker, limit, offset, start_date, end_date });
}

export async function fetchNewsCoverage() {
  return request('/api/news/coverage');
}

export async function fetchNewsQuality() {
  return request('/api/news/quality');
}

/**
 * Walk-forward regime validation report
 */
export async function fetchRegimeValidation() {
  return request('/api/regime/validation');
}

/**
 * Phase 2: ablation results, research memory (experiments) and equity curves
 */
export async function fetchAlphaAblation(file) {
  return request('/api/alpha/ablation', { file });
}

export async function fetchAlphaExperiments({ config, limit = 300 } = {}) {
  return request('/api/alpha/experiments', { config, limit });
}

export async function fetchAgentLoop({ file, config } = {}) {
  return request('/api/alpha/agent_loop', { file, config });
}

export async function fetchResearchBriefing() {
  return request('/api/alpha/briefing');
}

export async function fetchFactorReport() {
  return request('/api/alpha/factor_report');
}

export async function fetchPostCutoff() {
  return request('/api/alpha/post_cutoff');
}

export async function fetchAlphaSummary() {
  return request('/api/alpha/summary');
}

export async function fetchDownloads() {
  return request('/api/files');
}

export const fileUrl = (name) => `${API_BASE_URL}/api/files/${encodeURIComponent(name)}`;

export async function fetchAlphaAttribution(ids) {
  return request('/api/alpha/attribution', { ids: ids.join(',') });
}

export async function fetchAlphaEquity() {
  return request('/api/alpha/equity');
}
