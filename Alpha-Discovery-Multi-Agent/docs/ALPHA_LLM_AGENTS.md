# LLM Research Agent and Quant Agent

## Switching the LLM on
Put ONE of these in `.env` (never in code or chat):

```
ANTHROPIC_API_KEY=...        # Claude (model ANTHROPIC_MODEL, default claude-opus-5-5)
GEMINI_API_KEY=...           # Gemini free tier (model GEMINI_MODEL, default gemini-2.5-flash; set a current model id)
ALPHA_LLM_PROVIDER=auto      # auto | anthropic | gemini | offline
ALPHA_LLM_MODE=hybrid        # llm = LLM only | hybrid = LLM + built-in knowledge base | offline
```
Run: `python -m app.alpha.run_discovery --window fnspid --budget 40` (add `--offline` to force the knowledge base).
With no key the system falls back to the built-in knowledge base automatically.

## How context reaches the LLM
`ContextBuilder` renders a briefing from the real data (`app/alpha/prompts.py`): research question, universe, the
training/validation dates (the test period is never mentioned), allowed domains, regime mix, the feature catalogue
(plain-English meaning, coverage, rankable-days, sparse flags), the operator grammar, worked formula examples,
memory of earlier experiments (accepted and failed formulas with the Critic's reasons) and the editable priors file
`data/config/research_priors.md`. A real example (about 4,300 tokens): `docs/example_research_prompt.txt`.

## Roles
| Role | Input | Output | Checked by |
|---|---|---|---|
| Research Agent | briefing | hypotheses (title, mechanism, expected sign, domains, key features) | de-duplication against memory |
| Quant Agent | hypothesis + briefing + examples | up to 3 formulas | validator, with up to 2 repair rounds that show the LLM the exact error |
| Quant Agent (revision) | Critic feedback + formula | one revised formula | validator, then backtest and Critic again |

The LLM only proposes. Syntax, vocabulary, point-in-time safety, coverage, performance and plausibility are always
decided by deterministic code. Labels such as forward returns are unreachable.

## Reproducibility
Every prompt and response is cached in `data/alpha/llm/cache/` (keyed by provider, model, system and user text) and
every call is appended to `data/alpha/llm/calls.jsonl`. Reruns with identical context replay the same answers at no
cost, so the paper can cite exact prompts, models and responses. API keys are never logged.
