"""Optional run tracing for the discovery loop (LangSmith and/or Langfuse). Off unless keys are in the environment.

LangSmith : set LANGSMITH_TRACING=true and LANGSMITH_API_KEY (LangGraph then traces every node automatically).
Langfuse  : set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY (optionally LANGFUSE_HOST); needs `pip install langfuse`.
Keys are read from environment variables only. Prompts are anonymised before they reach the LLM, so traces contain no tickers.
"""
import logging
import os
from typing import Any, Dict

logger = logging.getLogger(__name__)


def tracing_config(run_id: str, config: str, window: str = "", extra: Dict[str, Any] = None) -> Dict[str, Any]:
    """Returns LangGraph invoke-config fragments: run name, tags, metadata and (if configured) callbacks."""
    cfg: Dict[str, Any] = {"run_name": f"alpha-{config}", "tags": ["alpha-discovery", f"config:{config}", f"window:{window}"],
                           "metadata": {"run_id": run_id, "config": config, "window": window, **(extra or {})}}
    if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
        try:
            try:
                from langfuse.langchain import CallbackHandler          # langfuse >= 3
            except ImportError:
                from langfuse.callback import CallbackHandler           # langfuse 2.x
            cfg["callbacks"] = [CallbackHandler()]
            logger.info("Langfuse tracing enabled")
        except Exception as e:  # noqa: BLE001 - tracing must never break research runs
            logger.warning(f"Langfuse requested but unavailable: {e}")
    if os.getenv("LANGSMITH_TRACING", "").lower() == "true" and os.getenv("LANGSMITH_API_KEY"):
        logger.info("LangSmith tracing enabled")
    return cfg
