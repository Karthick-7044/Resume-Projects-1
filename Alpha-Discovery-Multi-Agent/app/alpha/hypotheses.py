"""Offline research knowledge base: documented, financially motivated factor hypotheses.

Each entry is a HYPOTHESIS (title + economic rationale + the literature it comes from) with one
or more formula templates. Formulas are oriented so that the expected relation is positive:
a higher factor value should predict a higher next-period return. Templates may contain {w}
(window) placeholders, expanded by the Quant Agent. The offline Research Agent selects from this
library; an LLM Research Agent may also propose hypotheses outside it.
"""
from typing import Dict, List

H = Dict[str, object]

LIBRARY: List[H] = [
    # ------------------------------------------------ technical
    {"id": "T_MOM", "title": "Medium-term price momentum", "domains": ["technical"],
     "rationale": "Winners over the past 1-3 months keep outperforming (Jegadeesh-Titman); under-reaction to news.",
     "templates": ["cs_rank(momentum_60d)", "cs_rank(ts_mean(momentum_20d, {w}))"], "windows": [10, 20]},
    {"id": "T_MOM121", "title": "12-1 month momentum", "domains": ["technical"],
     "rationale": "Classic momentum skipping the latest month to avoid short-term reversal (Carhart).",
     "templates": ["cs_rank(momentum_252_21d)"]},
    {"id": "T_REV", "title": "Short-term reversal", "domains": ["technical"],
     "rationale": "One-week losers rebound as liquidity providers are compensated for absorbing order flow.",
     "templates": ["-cs_rank(momentum_5d)", "-cs_rank(ts_mean(daily_return, {w}))"], "windows": [3, 10]},
    {"id": "T_LOWVOL", "title": "Low-volatility anomaly", "domains": ["technical"],
     "rationale": "Low-risk stocks earn higher risk-adjusted returns because leverage-constrained investors overpay for volatility.",
     "templates": ["-cs_rank(volatility_60d)", "-cs_rank(ts_mean(volatility_20d, {w}))"], "windows": [20, 60]},
    {"id": "T_RISKADJ", "title": "Risk-adjusted momentum", "domains": ["technical"],
     "rationale": "Momentum per unit of volatility is more persistent than raw momentum.",
     "templates": ["cs_rank(momentum_60d / volatility_60d)", "cs_rank(momentum_20d / volatility_20d)"]},
    {"id": "T_TREND", "title": "Long-term trend quality", "domains": ["technical"],
     "rationale": "Stocks whose 50-day average is above the 200-day average are in established uptrends.",
     "templates": ["cs_rank(sma50_to_sma200)", "cs_rank(close_to_sma200)"]},
    {"id": "T_RSI", "title": "RSI mean reversion", "domains": ["technical"],
     "rationale": "Overbought stocks (high RSI) mean-revert over the following days.",
     "templates": ["-cs_rank(rsi_14)", "-cs_rank(close_to_sma20)"]},
    {"id": "T_VOLMOM", "title": "Volume-confirmed momentum", "domains": ["technical"],
     "rationale": "Price moves accompanied by abnormal volume reflect informed trading and persist.",
     "templates": ["cs_rank(momentum_20d) * cs_rank(volume_ratio_20d)"]},
    # ------------------------------------------------ fundamental
    {"id": "F_QUALITY", "title": "Profitability / quality", "domains": ["fundamental"],
     "rationale": "Highly profitable firms earn higher returns (Novy-Marx; Fama-French RMW).",
     "templates": ["cs_rank(roe)", "cs_rank(operating_margin)", "cs_rank(profit_margin)"]},
    {"id": "F_GROWTH", "title": "Fundamental growth", "domains": ["fundamental"],
     "rationale": "Sustained revenue and earnings growth is rewarded when it is not already priced.",
     "templates": ["cs_rank(revenue_growth)", "cs_rank(net_income_growth)"]},
    {"id": "F_ACCRUAL", "title": "Low accruals (earnings quality)", "domains": ["fundamental"],
     "rationale": "Earnings backed by cash flow are more persistent than accrual-driven earnings (Sloan).",
     "templates": ["-cs_rank(accruals_ratio)"]},
    {"id": "F_INVEST", "title": "Conservative investment", "domains": ["fundamental"],
     "rationale": "Firms that grow assets aggressively subsequently underperform (Fama-French CMA).",
     "templates": ["-cs_rank(asset_growth)"]},
    {"id": "F_LEV", "title": "Balance-sheet strength", "domains": ["fundamental"],
     "rationale": "Low leverage and high cash buffers reduce distress risk in downturns.",
     "templates": ["-cs_rank(debt_to_assets)", "cs_rank(cash_to_assets)"]},
    # ------------------------------------------------ valuation
    {"id": "V_EY", "title": "Earnings-yield value", "domains": ["valuation"],
     "rationale": "Cheap stocks on earnings outperform expensive ones (value premium).",
     "templates": ["cs_rank(earnings_yield)", "-cs_rank(pe_rel_sector)"]},
    {"id": "V_CF", "title": "Cash-flow yield", "domains": ["valuation"],
     "rationale": "Cash-flow yield is a cleaner value signal than earnings because it is harder to manage.",
     "templates": ["cs_rank(ocf_yield)", "cs_rank(sales_yield)"]},
    {"id": "V_BM", "title": "Book-to-market", "domains": ["valuation"],
     "rationale": "High book-to-market stocks earn the HML value premium.",
     "templates": ["cs_rank(book_to_market)"]},
    {"id": "V_QARP", "title": "Quality at a reasonable price", "domains": ["valuation", "fundamental"],
     "rationale": "Combining profitability with cheapness avoids value traps.",
     "templates": ["cs_rank(roe) + cs_rank(earnings_yield)", "cs_rank(operating_margin) + cs_rank(ocf_yield)"]},
    {"id": "V_GARP", "title": "Growth relative to valuation", "domains": ["valuation", "fundamental"],
     "rationale": "Growth is attractive only when not overpaid for (PEG-style).",
     "templates": ["cs_rank(revenue_growth) + cs_rank(earnings_yield)"]},
    {"id": "V_MOMVAL", "title": "Value with momentum confirmation", "domains": ["valuation", "technical"],
     "rationale": "Value and momentum are negatively correlated; combining them diversifies (Asness et al.).",
     "templates": ["cs_rank(earnings_yield) + cs_rank(momentum_60d)", "cs_rank(ocf_yield) + cs_rank(momentum_252_21d)"]},
    # ------------------------------------------------ news
    {"id": "N_SENT", "title": "News sentiment momentum", "domains": ["news"],
     "rationale": "Markets under-react to the tone of news; positive coverage predicts drift (Tetlock).",
     "templates": ["cs_rank(sent_decay)", "cs_rank(sentiment_20d)", "cs_rank(sent_decay_pstd)"]},
    {"id": "N_SURPRISE", "title": "Sentiment surprise", "domains": ["news"],
     "rationale": "A recent improvement in tone relative to its own baseline is new information.",
     "templates": ["cs_rank(sent_surprise)", "cs_rank(sentiment_5d - sentiment_20d)", "cs_rank(sent_momentum)"]},
    {"id": "N_ATTN", "title": "Attention-shock reversal", "domains": ["news"],
     "rationale": "Abnormal media attention attracts retail buying and temporary overpricing (Barber-Odean).",
     "templates": ["-cs_rank(news_vol_surprise)", "-cs_rank(ts_mean(news_vol_surprise, 5))"]},
    {"id": "N_NEG", "title": "Negative-news pressure", "domains": ["news"],
     "rationale": "A high share of negative articles signals deteriorating fundamentals not yet in prices.",
     "templates": ["-cs_rank(ts_sum(negative_news_count, 20) / (ts_sum(news_count, 20) + 1))"]},
    {"id": "N_SENTMOM", "title": "Sentiment-confirmed momentum", "domains": ["news", "technical"],
     "rationale": "Momentum supported by positive news is less likely to be noise.",
     "templates": ["cs_rank(momentum_20d) + cs_rank(sent_decay)", "cs_rank(momentum_60d) + cs_rank(sent_decay)"]},
    {"id": "N_SENTVAL", "title": "Sentiment-confirmed quality", "domains": ["news", "fundamental"],
     "rationale": "Good fundamentals with improving news tone indicate recognised quality.",
     "templates": ["cs_rank(roe) + cs_rank(sent_decay)"]},
    # ------------------------------------------------ regime-conditional
    {"id": "R_MOMDEF", "title": "Momentum in bull regimes, defensive otherwise", "domains": ["regime", "technical"],
     "rationale": "Momentum crashes in volatile reversals (Daniel-Moskowitz); low-vol protects in stress.",
     "templates": ["if_else(regime_bull, cs_rank(momentum_60d), -cs_rank(volatility_60d))",
                   "regime_prob_bull * cs_rank(momentum_60d) - (1 - regime_prob_bull) * cs_rank(volatility_60d)"]},
    {"id": "R_QUALSTRESS", "title": "Flight to quality in high-volatility regimes", "domains": ["regime", "fundamental", "technical"],
     "rationale": "Investors rotate into profitable firms when volatility is high.",
     "templates": ["if_else(regime_high_vol, cs_rank(roe), cs_rank(momentum_60d))",
                   "regime_prob_high_vol * cs_rank(operating_margin) + (1 - regime_prob_high_vol) * cs_rank(momentum_60d)"]},
    {"id": "R_REVSTRESS", "title": "Reversal in high-volatility regimes", "domains": ["regime", "technical"],
     "rationale": "Liquidity provision is best rewarded when volatility is high (Nagel).",
     "templates": ["if_else(regime_high_vol, -cs_rank(momentum_5d), cs_rank(momentum_60d))"]},
    {"id": "R_VALUEBEAR", "title": "Value in stress, growth in calm", "domains": ["regime", "valuation", "fundamental"],
     "rationale": "Cheap cash-generative firms hold up in drawdowns; growth leads in calm bull markets.",
     "templates": ["if_else(regime_high_vol, cs_rank(ocf_yield), cs_rank(revenue_growth))",
                   "if_else(regime_bull, cs_rank(revenue_growth), cs_rank(earnings_yield))"]},
    {"id": "R_SENTBULL", "title": "Sentiment matters more in calm markets", "domains": ["regime", "news", "technical"],
     "rationale": "In stress, macro dominates stock-specific news; in calm markets tone differentiates stocks.",
     "templates": ["if_else(regime_high_vol, -cs_rank(volatility_60d), cs_rank(sent_decay))",
                   "if_else(regime_bull, cs_rank(sent_decay), cs_rank(roe))"]},
    # ------------------------------------------------ macro-conditional
    {"id": "M_RATES", "title": "Rising rates favour value over growth", "domains": ["macro", "valuation", "fundamental"],
     "rationale": "Higher discount rates hurt long-duration growth stocks more than cheap cash-flow stocks.",
     "templates": ["if_else(gt(treasury_10y_chg_20d, 0), cs_rank(earnings_yield), cs_rank(revenue_growth))"]},
    {"id": "M_VIX", "title": "VIX spikes favour low-risk stocks", "domains": ["macro", "technical"],
     "rationale": "When implied volatility is abnormally high, low-beta names outperform.",
     "templates": ["if_else(gt(vix_zscore_60d, 1), -cs_rank(volatility_20d), cs_rank(momentum_20d))"]},
    {"id": "M_CURVE", "title": "Curve steepening and balance-sheet-heavy firms", "domains": ["macro", "valuation"],
     "rationale": "A steepening yield curve improves margins of book-heavy financials.",
     "templates": ["sign(yield_curve_chg_20d) * cs_rank(book_to_market)"]},
]


def expand_templates(h: H) -> List[str]:
    """All concrete formulas for a hypothesis (window placeholders expanded)."""
    out: List[str] = []
    for t in h["templates"]:
        if "{w}" in t:
            out.extend(t.format(w=w) for w in h.get("windows", [20]))
        else:
            out.append(t)
    return out
