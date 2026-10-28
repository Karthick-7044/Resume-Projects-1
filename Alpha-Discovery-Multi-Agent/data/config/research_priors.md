# Research priors (editable; read by the Research Agent and Quant Agent)

Plain-language domain knowledge placed in the LLM's briefing. Edit freely: it is the supported way to steer the agents
without changing code. Keep it factual; the agents may use it as inspiration but every idea is still validated,
backtested and reviewed deterministically.

## What a good hypothesis looks like
- A named economic mechanism (behavioural bias, risk premium, information diffusion, liquidity, constraint), not a pattern.
- A clear expected sign: higher factor value -> higher NEXT-period return.
- Uses data that exist at the decision time (every registered feature is point-in-time safe).
- Distinct from what memory shows was already tested.

## Established anomaly families (starting points, not limits)
- Momentum and reversal: intermediate-term winners continue; one-week losers rebound; 12-1 month momentum skips the last month.
- Value and cash-flow yield: cheap relative to earnings, book, sales or cash flow earns a premium; avoid pure value traps (combine with quality).
- Profitability and quality: high ROE/margins, low accruals, conservative asset growth, low leverage.
- Low risk: low volatility / low beta stocks earn more per unit of risk.
- News and sentiment: markets under-react to tone, over-react to sudden attention; sentiment is more informative when it
  CONFIRMS price or fundamentals; earnings and analyst-rating news carry more information than generic news.
- Regime dependence: momentum is fragile in volatile reversals; defensive/quality exposures help in high-volatility
  regimes; value vs growth depends on rates.
- Macro conditioning: rising yields and a steepening curve favour value / financials over long-duration growth;
  high VIX favours low-risk names.

## Data caveats the agents must respect
- The universe is small (about 10 large-cap US stocks). Cross-sectional rankings are noisy: prefer simple formulas,
  few operators, and economically motivated combinations.
- News features exist only where the news provider had coverage; sparse features need a fallback or are untestable.
- Market-wide features (regime, macro) have the same value for every stock on a date. They must be combined with
  stock-level features (via if_else or multiplication), never ranked alone.
- A factor needs at least 5 stocks with a value on a date to form a portfolio.

## Things to avoid
- Referencing anything in the future; any label (forward returns); features not in the catalogue.
- Very deep or very long expressions: simple, interpretable formulas generalise better.
- Re-testing a formula that memory already contains.
