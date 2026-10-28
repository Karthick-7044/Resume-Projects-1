"""Alpha factor expression language (safe AST evaluator).

A factor is a Python-syntax expression over registered panel features, e.g.
    cs_rank(momentum_60d) - cs_rank(volatility_60d)
    if_else(regime_bull, cs_rank(ts_mean(sentiment_5d, 5)), -cs_rank(momentum_5d))

Evaluation works on wide matrices (index = date, columns = ticker). Every time-series operator
looks strictly backward (rolling windows, positive lags); there is no operator that can read a
future row, and the validator additionally rejects negative lags and label columns.
Nothing is executed with eval(): the expression is parsed with `ast` and walked node by node.
"""
import ast
from typing import Callable, Dict, List, Set

import numpy as np
import pandas as pd

MAX_WINDOW = 252

# name -> (arity, indices of integer-window arguments, description)
FUNCTIONS: Dict[str, tuple] = {
    "cs_rank": (1, [], "cross-sectional percentile rank per date, centred to [-0.5, 0.5]"),
    "cs_zscore": (1, [], "cross-sectional z-score per date"),
    "cs_demean": (1, [], "cross-sectional demeaning per date"),
    "ts_mean": (2, [1], "rolling mean over n days"),
    "ts_std": (2, [1], "rolling standard deviation over n days"),
    "ts_sum": (2, [1], "rolling sum over n days"),
    "ts_min": (2, [1], "rolling minimum over n days"),
    "ts_max": (2, [1], "rolling maximum over n days"),
    "ts_delta": (2, [1], "x_t - x_{t-n}"),
    "ts_pct_change": (2, [1], "x_t / x_{t-n} - 1"),
    "ts_zscore": (2, [1], "(x_t - mean_n) / std_n (own history)"),
    "ts_rank": (2, [1], "percentile of x_t within its last n values"),
    "lag": (2, [1], "x_{t-n}, n >= 1"),
    "ewm": (2, [1], "exponentially weighted mean with half-life n"),
    "abs": (1, [], "absolute value"),
    "sign": (1, [], "sign"),
    "slog": (1, [], "sign(x) * log(1 + |x|)"),
    "clip": (3, [], "clip(x, lo, hi) with constant bounds"),
    "max": (2, [], "element-wise maximum"),
    "min": (2, [], "element-wise minimum"),
    "gt": (2, [], "1 where x > y else 0 (NULL where x or y is NULL)"),
    "lt": (2, [], "1 where x < y else 0 (NULL where x or y is NULL)"),
    "if_else": (3, [], "if_else(cond, a, b) = a where cond > 0.5 else b"),
}

ALLOWED_BINOPS = {ast.Add: np.add, ast.Sub: np.subtract, ast.Mult: np.multiply, ast.Div: None}
ALLOWED_UNARY = {ast.USub: np.negative, ast.UAdd: lambda x: x}


class DSLError(ValueError):
    pass


def parse(expr: str) -> ast.Expression:
    try:
        return ast.parse(expr.strip(), mode="eval")
    except SyntaxError as e:
        raise DSLError(f"Syntax error: {e.msg}") from e


def referenced_features(expr: str) -> List[str]:
    tree = parse(expr)
    out: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id not in FUNCTIONS and node.id not in out:
            out.append(node.id)
    return out


def complexity(expr: str) -> Dict[str, int]:
    tree = parse(expr)

    def depth(n) -> int:
        kids = list(ast.iter_child_nodes(n))
        return 1 + (max(depth(k) for k in kids) if kids else 0)

    nodes = sum(1 for n in ast.walk(tree) if isinstance(n, (ast.Call, ast.BinOp, ast.UnaryOp, ast.Name, ast.Constant)))
    return {"nodes": nodes, "depth": depth(tree.body)}


class FactorEvaluator:
    """Evaluates expressions on a (date, ticker) panel using wide feature matrices."""

    def __init__(self, panel: pd.DataFrame):
        p = panel.copy()
        p["date"] = pd.to_datetime(p["date"])
        self.panel = p.sort_values(["date", "ticker"])
        self.dates = pd.DatetimeIndex(sorted(p["date"].unique()))
        self.tickers = sorted(p["ticker"].unique())
        self._cache: Dict[str, pd.DataFrame] = {}

    def matrix(self, feature: str) -> pd.DataFrame:
        if feature not in self._cache:
            if feature not in self.panel.columns:
                raise DSLError(f"Unknown feature '{feature}'")
            col = pd.to_numeric(self.panel[feature], errors="coerce")
            m = pd.DataFrame({"date": self.panel["date"], "ticker": self.panel["ticker"], "v": col})
            self._cache[feature] = m.pivot(index="date", columns="ticker", values="v").reindex(
                index=self.dates, columns=self.tickers)
        return self._cache[feature]

    def evaluate(self, expr: str, overrides: Dict[str, pd.DataFrame] = None) -> pd.DataFrame:
        """Returns the factor matrix (dates x tickers). `overrides` replaces features (attribution)."""
        tree = parse(expr)
        overrides = overrides or {}
        out = self._eval(tree.body, overrides)
        if np.isscalar(out):
            out = pd.DataFrame(out, index=self.dates, columns=self.tickers)
        return out.replace([np.inf, -np.inf], np.nan)

    # ------------------------------------------------------------------ internals
    def _const_int(self, node) -> int:
        if not isinstance(node, ast.Constant) or not isinstance(node.value, (int, float)):
            raise DSLError("Window/lag arguments must be numeric constants")
        n = int(node.value)
        if n != node.value:
            raise DSLError("Window/lag arguments must be integers")
        return n

    def _eval(self, node, ov):
        if isinstance(node, ast.Constant):
            if not isinstance(node.value, (int, float)):
                raise DSLError("Only numeric constants are allowed")
            return float(node.value)
        if isinstance(node, ast.Name):
            return ov[node.id] if node.id in ov else self.matrix(node.id)
        if isinstance(node, ast.UnaryOp) and type(node.op) in ALLOWED_UNARY:
            return ALLOWED_UNARY[type(node.op)](self._eval(node.operand, ov))
        if isinstance(node, ast.BinOp) and type(node.op) in ALLOWED_BINOPS:
            a, b = self._eval(node.left, ov), self._eval(node.right, ov)
            if isinstance(node.op, ast.Div):
                if isinstance(b, pd.DataFrame):
                    b = b.where(b.abs() > 1e-12)
                elif abs(b) < 1e-12:
                    raise DSLError("Division by zero constant")
                return a / b
            return ALLOWED_BINOPS[type(node.op)](a, b)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCTIONS:
            return self._call(node.func.id, node.args, ov)
        raise DSLError(f"Disallowed syntax: {type(node).__name__}")

    def _call(self, name: str, args, ov):
        arity, window_idx, _ = FUNCTIONS[name]
        if len(args) != arity:
            raise DSLError(f"{name} expects {arity} arguments, got {len(args)}")
        if name in ("ts_mean", "ts_std", "ts_sum", "ts_min", "ts_max", "ts_delta", "ts_pct_change",
                    "ts_zscore", "ts_rank", "lag", "ewm"):
            x = self._as_frame(self._eval(args[0], ov))
            n = self._const_int(args[1])
            if n < 1 or n > MAX_WINDOW:
                raise DSLError(f"{name} window/lag must be in [1, {MAX_WINDOW}] (got {n})")
            if name == "ts_mean":
                return x.rolling(n, min_periods=n).mean()
            if name == "ts_std":
                return x.rolling(n, min_periods=max(2, n)).std()
            if name == "ts_sum":
                return x.rolling(n, min_periods=n).sum()
            if name == "ts_min":
                return x.rolling(n, min_periods=n).min()
            if name == "ts_max":
                return x.rolling(n, min_periods=n).max()
            if name == "ts_delta":
                return x - x.shift(n)
            if name == "ts_pct_change":
                prev = x.shift(n)
                return x / prev.where(prev.abs() > 1e-12) - 1.0
            if name == "ts_zscore":
                r = x.rolling(n, min_periods=n)
                sd = r.std()
                return (x - r.mean()) / sd.where(sd > 1e-12)
            if name == "ts_rank":
                return x.rolling(n, min_periods=n).rank(pct=True)
            if name == "lag":
                return x.shift(n)
            if name == "ewm":
                return x.ewm(halflife=n, min_periods=n).mean()
        if name in ("cs_rank", "cs_zscore", "cs_demean"):
            x = self._as_frame(self._eval(args[0], ov))
            if name == "cs_rank":
                return x.rank(axis=1, pct=True) - 0.5
            mu = x.mean(axis=1)
            if name == "cs_demean":
                return x.sub(mu, axis=0)
            sd = x.std(axis=1)
            return x.sub(mu, axis=0).div(sd.where(sd > 1e-12), axis=0)
        if name == "abs":
            return np.abs(self._eval(args[0], ov))
        if name == "sign":
            return np.sign(self._eval(args[0], ov))
        if name == "slog":
            x = self._eval(args[0], ov)
            return np.sign(x) * np.log1p(np.abs(x))
        if name == "clip":
            lo, hi = (self._eval(a, ov) for a in args[1:])
            if not (np.isscalar(lo) and np.isscalar(hi)):
                raise DSLError("clip bounds must be constants")
            return self._as_frame(self._eval(args[0], ov)).clip(lo, hi)
        if name in ("max", "min"):
            a, b = self._as_frame(self._eval(args[0], ov)), self._as_frame(self._eval(args[1], ov))
            return np.maximum(a, b) if name == "max" else np.minimum(a, b)
        if name in ("gt", "lt"):
            a, b = self._as_frame(self._eval(args[0], ov)), self._as_frame(self._eval(args[1], ov))
            res = (a > b) if name == "gt" else (a < b)
            return res.astype(float).where(a.notna() & b.notna())
        if name == "if_else":
            c = self._as_frame(self._eval(args[0], ov))
            a, b = self._as_frame(self._eval(args[1], ov)), self._as_frame(self._eval(args[2], ov))
            out = a.where(c > 0.5, b)
            return out.where(c.notna())
        raise DSLError(f"Unsupported function {name}")

    def _as_frame(self, x) -> pd.DataFrame:
        if isinstance(x, pd.DataFrame):
            return x
        return pd.DataFrame(float(x), index=self.dates, columns=self.tickers)


def grammar_description() -> str:
    """Human/LLM-readable description of the operator vocabulary."""
    lines = [f"- {name}({', '.join(['x'] + (['n'] if spec[1] else []) + (['y'] if spec[0] == 2 and not spec[1] else []) + (['a', 'b'] if name in ('if_else', 'clip') else []))}): {spec[2]}"
             for name, spec in FUNCTIONS.items()]
    return "\n".join(lines) + "\n- arithmetic: + - * / and unary minus; numeric constants"
