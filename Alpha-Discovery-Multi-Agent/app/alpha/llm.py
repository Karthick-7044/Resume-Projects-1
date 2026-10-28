"""LLM layer for the Research Agent and Quant Agent (provider-agnostic, cached, logged).

Providers (selected by ALPHA_LLM_PROVIDER = auto | anthropic | gemini | groq | offline, or a fallback list "groq,gemini"):
  anthropic : official SDK, model ANTHROPIC_MODEL (default claude-opus-5-5), key ANTHROPIC_API_KEY
  gemini    : REST (no extra dependency), model GEMINI_MODEL, key GEMINI_API_KEY (free tier available)
  groq      : OpenAI-compatible REST, model GROQ_MODEL (default openai/gpt-oss-120b), key GROQ_API_KEY, 30 req/min
  auto      : anthropic if its key is set, else groq, else gemini, else offline
Keys are read from the environment / .env only and never written to logs.

Reproducibility: every call is cached by sha1(provider | model | system | user) in data/alpha/llm/cache/ and appended
to data/alpha/llm/calls.jsonl, so a rerun with identical context replays the same answers for free and the paper can
cite the exact prompts and responses. The LLM only PROPOSES: formulas still go through the validator, backtester and
critic, and a rejected formula is fed back (with the validator's error) for up to `max_repairs` repair attempts.
"""
import hashlib
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import requests

from app.alpha import prompts
from app.config.settings import (
    ALPHA_LLM_DIR, ALPHA_LLM_MODE, ALPHA_LLM_PROVIDER, ANTHROPIC_API_KEY, ANTHROPIC_MODEL, GEMINI_API_KEY, GEMINI_MODEL,
    GROQ_API_KEY, GROQ_MODEL, GROQ_MODEL_SMALL, CEREBRAS_API_KEY, CEREBRAS_MODEL,
)

logger = logging.getLogger(__name__)
CACHE_DIR = Path(ALPHA_LLM_DIR) / "cache"
CALL_LOG = Path(ALPHA_LLM_DIR) / "calls.jsonl"


REJECTED_HYPOTHESES: List[Dict] = []     # audit trail of hypotheses refused by the output rules


class LLMError(RuntimeError):
    pass


# ---------------------------------------------------------------------- clients
class LLMClient:
    provider = "base"
    model = ""

    def complete(self, system: str, user: str, max_tokens: int = 8000) -> str:  # pragma: no cover - interface
        raise NotImplementedError


class AnthropicClient(LLMClient):
    provider = "anthropic"

    def __init__(self, api_key: Optional[str] = None, model: str = ANTHROPIC_MODEL):
        import anthropic
        self._anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        self.model = model

    def complete(self, system: str, user: str, max_tokens: int = 8000) -> str:
        a = self._anthropic
        try:
            resp = self.client.messages.create(
                model=self.model, max_tokens=max_tokens, system=system,
                output_config={"effort": "medium"},                    # thinking is adaptive by default on this model
                messages=[{"role": "user", "content": user}])
        except a.RateLimitError as e:
            raise LLMError(f"Anthropic rate limited: {e}") from e
        except a.APIStatusError as e:
            raise LLMError(f"Anthropic API error {e.status_code}: {e.message}") from e
        except a.APIConnectionError as e:
            raise LLMError(f"Anthropic connection error: {e}") from e
        if resp.stop_reason == "refusal":
            raise LLMError("Anthropic declined the request (refusal)")
        return "".join(b.text for b in resp.content if b.type == "text")


class GeminiClient(LLMClient):
    provider = "gemini"
    URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    MIN_INTERVAL = 7.0          # seconds between calls (about 8 per minute)
    _last_call = 0.0

    def __init__(self, api_key: Optional[str] = None, model: str = GEMINI_MODEL, temperature: float = 0.4,
                 session: Optional[requests.Session] = None):
        self.api_key, self.model, self.temperature = api_key or GEMINI_API_KEY, model, temperature
        self.session = session or requests.Session()

    def complete(self, system: str, user: str, max_tokens: int = 8000) -> str:
        if not self.api_key:
            raise LLMError("GEMINI_API_KEY is not set")
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"temperature": self.temperature, "maxOutputTokens": max_tokens,
                                     "responseMimeType": "application/json"}}
        last = None
        wait = self.MIN_INTERVAL - (time.time() - GeminiClient._last_call)     # free tier allows only a few requests/minute
        if wait > 0:
            time.sleep(wait)
        for attempt in range(1, 6):
            GeminiClient._last_call = time.time()
            try:
                r = self.session.post(self.URL.format(model=self.model), json=body,
                                      headers={"x-goog-api-key": self.api_key}, timeout=120)
            except requests.RequestException as e:
                last = str(e)
                time.sleep(2 * attempt)
                continue
            if r.status_code == 200:
                data = r.json()
                cands = data.get("candidates") or []
                if not cands:
                    raise LLMError(f"Gemini returned no candidates: {str(data)[:200]}")
                return "".join(p.get("text", "") for p in cands[0].get("content", {}).get("parts", []))
            if r.status_code == 429 and "PerDay" in r.text:
                raise LLMError("Gemini daily quota exhausted; rerun after the quota resets (no fallback is used silently)")
            if r.status_code in (429, 500, 503):
                last = f"HTTP {r.status_code}"
                time.sleep(float(r.headers.get("Retry-After") or min(70, 15 * attempt)))
                continue
            raise LLMError(f"Gemini HTTP {r.status_code}: {r.text[:200]}")
        raise LLMError(f"Gemini request failed after retries: {last}")


class GroqClient(LLMClient):
    """Groq's OpenAI-compatible chat endpoint (key from the GROQ_API_KEY environment variable only)."""
    provider = "groq"
    URL = "https://api.groq.com/openai/v1/chat/completions"
    MIN_INTERVAL = 2.0          # seconds between calls (30 requests per minute on the free tier)
    _last_call = 0.0
    fast_fail = False           # set by FallbackClient: on a per-minute limit, hand over to the next model quickly

    def __init__(self, api_key: Optional[str] = None, model: str = GROQ_MODEL, temperature: float = 0.7,
                 session: Optional[requests.Session] = None):
        self.api_key, self.model, self.temperature = api_key or GROQ_API_KEY, model, temperature
        self.session = session or requests.Session()

    def complete(self, system: str, user: str, max_tokens: int = 8000) -> str:
        if not self.api_key:
            raise LLMError("GROQ_API_KEY is not set")
        body = {"model": self.model, "temperature": self.temperature, "max_tokens": min(max_tokens, 8000),
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        last = None
        for attempt in range(1, 6):
            wait = self.MIN_INTERVAL - (time.time() - GroqClient._last_call)
            if wait > 0:
                time.sleep(wait)
            GroqClient._last_call = time.time()
            try:
                r = self.session.post(self.URL, json=body, headers={"Authorization": f"Bearer {self.api_key}"}, timeout=120)
            except requests.RequestException as e:
                last = str(e)
                time.sleep(2 * attempt)
                continue
            if r.status_code == 200:
                payload = r.json()
                self.last_usage = payload.get("usage")          # prompt/completion token counts (logged per call)
                choices = payload.get("choices") or []
                if not choices:
                    raise LLMError("Groq returned no choices")
                return choices[0].get("message", {}).get("content", "")
            if r.status_code == 429 and ("per day" in r.text.lower() or "tokens per day" in r.text.lower() or "TPD" in r.text):
                raise LLMError("Groq daily quota exhausted; rerun after the quota resets")
            if r.status_code in (429, 500, 502, 503):
                last = f"HTTP {r.status_code}"
                if self.fast_fail and r.status_code == 429 and attempt >= 2:
                    # inside a model chain: a per-minute limit moves on to the next model instead of sleeping
                    raise LLMError(f"{self.provider} {self.model} rate limited (per-minute); trying the next model")
                time.sleep(min(float(r.headers.get("retry-after") or 10 * attempt), 20 if self.fast_fail else 60))
                continue
            if r.status_code == 400 and "json_validate_failed" in r.text and "response_format" in body:
                body.pop("response_format")          # strict JSON mode tripped: retry free-form; extract_json parses it
                last = "json_validate_failed"
                continue
            if r.status_code in (401, 403):
                raise LLMError(f"Groq rejected the API key (HTTP {r.status_code})")
            raise LLMError(f"Groq HTTP {r.status_code}: {r.text[:200]}")
        raise LLMError(f"Groq request failed after retries: {last}")


class CerebrasClient(GroqClient):
    """Cerebras inference (free tier, OpenAI-compatible); key from the CEREBRAS_API_KEY environment variable only."""
    provider = "cerebras"
    URL = "https://api.cerebras.ai/v1/chat/completions"
    _last_call = 0.0

    def __init__(self, api_key: Optional[str] = None, model: str = CEREBRAS_MODEL, temperature: float = 0.7,
                 session: Optional[requests.Session] = None):
        super().__init__(api_key=api_key or CEREBRAS_API_KEY, model=model, temperature=temperature, session=session)

    def complete(self, system: str, user: str, max_tokens: int = 8000) -> str:
        if not self.api_key:
            raise LLMError("CEREBRAS_API_KEY is not set")
        try:
            return super().complete(system, user, max_tokens)
        except LLMError as e:
            raise LLMError(str(e).replace("Groq", "Cerebras")) from e


class FallbackClient(LLMClient):
    """Tries providers in order (e.g. Groq then Gemini); a provider that errors is skipped for that call."""
    provider = "fallback"

    def __init__(self, clients: List[LLMClient]):
        self.clients = clients
        self.model = "+".join(f"{c.provider}:{c.model}" for c in clients)
        self.exhausted: set = set()        # providers/models whose DAILY quota ran out: skipped for the rest of the run
        if len(clients) > 1:
            for c in clients:
                if hasattr(c, "fast_fail"):
                    c.fast_fail = True

    def complete(self, system: str, user: str, max_tokens: int = 8000) -> str:
        errors = []
        for i, c in enumerate(self.clients):
            if i in self.exhausted:
                continue
            try:
                out = c.complete(system, user, max_tokens)
                self.last_model = f"{c.provider}:{c.model}"      # which model actually answered (recorded in memory)
                self.last_usage = getattr(c, "last_usage", None)
                return out
            except LLMError as e:
                if "daily quota" in str(e):
                    self.exhausted.add(i)
                errors.append(f"{c.provider}:{c.model}: {e}")
                logger.warning(f"LLM provider {c.provider} failed, trying the next one: {e}")
        raise LLMError("all LLM providers failed: " + " | ".join(errors))


class CallableClient(LLMClient):
    """Wraps a function (system, user) -> str. Used by tests and for scripted/offline replays."""
    provider = "callable"

    def __init__(self, fn: Callable[[str, str], str]):
        self.fn = fn
        self.model = f"callable-{id(fn):x}"          # distinct cache identity per scripted function

    def complete(self, system: str, user: str, max_tokens: int = 8000) -> str:
        return self.fn(system, user)


def groq_clients() -> List[LLMClient]:
    """One client per model in GROQ_MODEL (comma-separated); on Groq every model has its own daily quota."""
    return [GroqClient(model=m.strip()) for m in GROQ_MODEL.split(",") if m.strip()]


_CLIENT: Optional[LLMClient] = None
_CLIENT_SET = False


def set_client(client: Optional[LLMClient]):
    """Injects a client (tests) or forces offline mode (None)."""
    global _CLIENT, _CLIENT_SET
    _CLIENT, _CLIENT_SET = client, True


def reset_client():
    global _CLIENT, _CLIENT_SET
    _CLIENT, _CLIENT_SET = None, False


def get_client() -> Optional[LLMClient]:
    global _CLIENT, _CLIENT_SET
    if _CLIENT_SET:
        return _CLIENT
    prov = ALPHA_LLM_PROVIDER
    if ALPHA_LLM_MODE == "offline" or prov == "offline":
        client = None
    elif "," in prov:                                   # explicit fallback order, e.g. "groq,gemini"
        makers = {"groq": (GROQ_API_KEY, groq_clients), "gemini": (GEMINI_API_KEY, lambda: [GeminiClient()]),
                  "cerebras": (CEREBRAS_API_KEY, lambda: [CerebrasClient(model=m.strip()) for m in CEREBRAS_MODEL.split(",") if m.strip()]),
                  "anthropic": (ANTHROPIC_API_KEY, lambda: [AnthropicClient()])}
        chain = [c for p in (x.strip() for x in prov.split(",")) if p in makers and makers[p][0] for c in makers[p][1]()]
        client = chain[0] if len(chain) == 1 else (FallbackClient(chain) if chain else None)
    elif prov == "groq":
        g = groq_clients() if GROQ_API_KEY else []
        client = (g[0] if len(g) == 1 else FallbackClient(g)) if g else None
    elif prov == "anthropic" or (prov == "auto" and ANTHROPIC_API_KEY):
        client = AnthropicClient() if ANTHROPIC_API_KEY else None
    elif prov == "auto" and GROQ_API_KEY:
        g = groq_clients()
        client = FallbackClient(g + ([GeminiClient()] if GEMINI_API_KEY else [])) if (len(g) > 1 or GEMINI_API_KEY) else g[0]
    elif prov == "gemini" or (prov == "auto" and GEMINI_API_KEY):
        client = GeminiClient() if GEMINI_API_KEY else None
    else:
        client = None
    _CLIENT, _CLIENT_SET = client, True
    return client


def llm_available() -> bool:
    return get_client() is not None


def llm_mode() -> str:
    """'offline' without a client; otherwise ALPHA_LLM_MODE ('llm' or 'hybrid')."""
    return "offline" if not llm_available() else ("llm" if ALPHA_LLM_MODE == "llm" else "hybrid")


# ---------------------------------------------------------------------- cached, logged JSON calls
def extract_json(text: str) -> Optional[Dict]:
    """First JSON object in model text (tolerates code fences and surrounding prose)."""
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I)
    m = re.search(r"\{.*\}", t, flags=re.S)
    for cand in (t, m.group(0) if m else None):
        if not cand:
            continue
        try:
            obj = json.loads(cand)
        except json.JSONDecodeError:
            continue
        return obj if isinstance(obj, dict) else None
    return None


RUN_SEED: Optional[int] = None


def set_run_seed(seed: Optional[int]):
    """Makes independent runs (different seeds) independent LLM samples: the seed enters the prompt and the cache key,
    so a rerun with the SAME seed still replays from the cache, but a new seed is never answered from another run."""
    global RUN_SEED
    RUN_SEED = seed


_SMALL_CLIENT: Optional[LLMClient] = None
SMALL_MODEL_ROLES = ("revise", "quant_repair")


def client_for(role: str) -> Optional[LLMClient]:
    """v5: repairs/revisions go to the small model(s) in GROQ_MODEL_SMALL (falling back to the main chain); ideas and
    first formulations use the main (large) model chain."""
    global _SMALL_CLIENT
    main = get_client()
    if role not in SMALL_MODEL_ROLES or not GROQ_MODEL_SMALL or not GROQ_API_KEY or main is None:
        return main
    if _SMALL_CLIENT is None:
        small = [GroqClient(model=m.strip()) for m in GROQ_MODEL_SMALL.split(",") if m.strip()]
        rest = main.clients if isinstance(main, FallbackClient) else [main]
        _SMALL_CLIENT = FallbackClient(small + rest)
    return _SMALL_CLIENT


def complete_json(system: str, user: str, role: str, max_tokens: int = 8000) -> Dict:
    client = client_for(role)
    if client is None:
        raise LLMError("no LLM client configured")
    if RUN_SEED is not None:
        user = (f"{user}\n\n(Independent research run #{RUN_SEED}: explore mechanisms and domain combinations that other "
                "runs are unlikely to choose; do not simply repeat the most obvious textbook factors.)")
    key = hashlib.sha1(f"{client.provider}|{client.model}|{system}|{user}".encode("utf-8")).hexdigest()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{key}.json"
    cached = path.exists()
    if cached:
        text = json.loads(path.read_text(encoding="utf-8"))["response"]
    else:
        text = client.complete(system, user, max_tokens)
        path.write_text(json.dumps({"provider": client.provider, "model": client.model, "role": role, "system": system,
                                    "user": user, "response": text,
                                    "created_at": datetime.now(timezone.utc).isoformat()}), encoding="utf-8")
    with open(CALL_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "role": role, "provider": client.provider,
                            "model": client.model, "key": key, "cached": cached, "prompt_chars": len(system) + len(user),
                            "answered_by": None if cached else getattr(client, "last_model", client.model),
                            "usage": None if cached else getattr(client, "last_usage", None)}) + "\n")
    obj = extract_json(text)
    if obj is None:
        raise LLMError(f"{role}: response was not valid JSON: {text[:160]!r}")
    return obj


# ---------------------------------------------------------------------- output rules (enforced in code, not by trust)
def domain_violations(h: Dict, allowed_domains: List[str]) -> List[str]:
    """Multi-domain rule: when 2+ domains are allowed, a hypothesis must combine at least two of them."""
    allowed = {str(d) for d in allowed_domains}
    used = {str(d) for d in (h.get("domains") or [])} & allowed
    if len(allowed) >= 2 and len(used) < 2:
        return [f"uses {len(used)} allowed domain(s) {sorted(used)}; at least two different domains are required"]
    return []


def leakage_violations(h: Dict, universe: List[str]) -> List[str]:
    """Reasons a proposed hypothesis breaks the no-identity / no-future-knowledge rules (empty = acceptable)."""
    from app.features.news_enrich import name_terms
    text = " ".join(str(h.get(k, "")) for k in ("title", "rationale", "condition", "literature_basis", "key_features"))
    low = text.lower()
    why = []
    if not str(h.get("literature_basis", "")).strip():
        why.append("no literature_basis (unpublished/ungrounded idea)")
    for t in universe:
        if len(t) >= 2 and re.search(rf"(?<![A-Za-z0-9]){re.escape(t)}(?![A-Za-z0-9])", text):
            why.append(f"mentions ticker {t}")
    names = {n.lower() for ns in name_terms().values() for n in ns if len(n) >= 4}
    hit = sorted(n for n in names if re.search(rf"(?<![a-z0-9]){re.escape(n)}(?![a-z0-9])", low))
    if hit:
        why.append("mentions company " + hit[0])
    # a year is allowed ONLY inside the literature citation and only if it is <= 2019 (published before the sample)
    outside = re.sub(re.escape(str(h.get("literature_basis", ""))), " ", text) if h.get("literature_basis") else text
    if re.search(r"\b(19|20)\d{2}\b", outside):
        why.append("contains a calendar year outside the literature citation")
    if any(int(y) >= 2020 for y in re.findall(r"\b(20[2-9]\d)\b", str(h.get("literature_basis", "")))):
        why.append("literature citation dated 2020 or later")
    ev = [t for t in prompts.FORBIDDEN_EVENT_TERMS if t in low]
    if ev:
        why.append("refers to a specific market event: " + ev[0])
    return why


# ---------------------------------------------------------------------- agent roles
def research_hypotheses(context: Dict, n: int = 4) -> List[Dict]:
    """Research Agent: hypotheses (ideas + mechanism), no formulas. Returns [] on any LLM failure."""
    try:
        data = complete_json(prompts.RESEARCH_SYSTEM, prompts.research_user_prompt(context, n), "research")
    except LLMError as e:
        logger.warning(f"Research Agent LLM failed: {e}")
        return []
    out = []
    for h in data.get("hypotheses", []) or []:
        if not isinstance(h, dict) or not str(h.get("title", "")).strip():
            continue
        bad = leakage_violations(h, context.get("universe", [])) + domain_violations(h, context.get("allowed_domains", []))
        if bad:
            logger.warning(f"Rejected LLM hypothesis {str(h.get('title'))[:50]!r}: {'; '.join(bad)}")
            REJECTED_HYPOTHESES.append({"title": str(h.get("title")), "reasons": bad})
            continue
        title = str(h["title"]).strip()
        out.append({
            "id": "LLM_" + hashlib.sha1(title.lower().encode("utf-8")).hexdigest()[:8], "title": title,
            "rationale": str(h.get("rationale", "")), "literature_basis": str(h.get("literature_basis", "")),
            "expected_sign": str(h.get("expected_sign", "positive")),
            "domains": [str(d) for d in (h.get("domains") or [])], "key_features": [str(f) for f in (h.get("key_features") or [])],
            "condition": h.get("condition"), "templates": [], "source": f"llm:{getattr(get_client(), 'last_model', get_client().provider)}",
        })
    return out[:n]


def formulate(hypothesis: Dict, context: Dict, validate: Callable[[str], object],
              max_repairs: int = 2) -> Tuple[List[str], List[Tuple[str, str]]]:
    """Quant Agent: returns (valid formulas, rejected [(formula, error)]). Validator errors are fed back to the LLM."""
    valid: List[str] = []
    rejected: List[Tuple[str, str]] = []
    previous, errors = None, None
    for _ in range(max_repairs + 1):
        try:
            data = complete_json(prompts.QUANT_SYSTEM, prompts.quant_user_prompt(hypothesis, context, errors, previous),
                                 "quant_repair" if previous else "quant")
        except LLMError as e:
            logger.warning(f"Quant Agent LLM failed: {e}")
            break
        forms = [str(f).strip() for f in (data.get("formulas") or []) if isinstance(f, str) and f.strip()]
        bad = []
        for f in forms:
            r = validate(f)
            if r.valid:
                if f not in valid:
                    valid.append(f)
            else:
                msg = "; ".join(r.errors)[:300]
                bad.append((f, msg))
                rejected.append((f, msg))
        if valid or not bad:
            break
        previous, errors = [f for f, _ in bad], [e for _, e in bad]
    return valid, rejected


def revise_formula(formula: str, critique: str, actions: List[str], hypothesis: Dict, context: Dict,
                   validate: Callable[[str], object]) -> Optional[str]:
    """Quant Agent revision after a Critic REVISE verdict. Returns a valid new formula or None."""
    try:
        data = complete_json(prompts.QUANT_SYSTEM, prompts.revise_user_prompt(formula, critique, actions, hypothesis, context), "revise")
    except LLMError as e:
        logger.warning(f"Revision LLM failed: {e}")
        return None
    for f in data.get("formulas") or []:
        if isinstance(f, str) and f.strip() and f.strip() != formula and validate(f.strip()).valid:
            return f.strip()
    return None
