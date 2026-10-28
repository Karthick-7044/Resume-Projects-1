"""Deterministic formula validation: syntax, vocabulary, PIT safety, future references, coverage.

An LLM (or any generator) may propose a formula, but only this module decides whether it is
allowed to reach the backtester.
"""
import ast
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

import pandas as pd

from app.alpha.dsl import DSLError, FUNCTIONS, MAX_WINDOW, FactorEvaluator, complexity, parse
from app.features.registry import FEATURES

MAX_NODES = 60
MAX_DEPTH = 10
MIN_COVERAGE = 0.30       # share of training (date, ticker) cells with a factor value
MIN_BREADTH = 5           # names required on a date to form a portfolio
MIN_VALID_DATES = 0.30    # share of training dates with >= MIN_BREADTH names

_REGISTRY = {f["feature_name"]: f for f in FEATURES}
_WINDOW_FUNCS = {name for name, spec in FUNCTIONS.items() if spec[1]}


@dataclass
class ValidationResult:
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    features: List[str] = field(default_factory=list)
    domains: List[str] = field(default_factory=list)
    nodes: int = 0
    depth: int = 0
    coverage: Optional[float] = None
    valid_date_share: Optional[float] = None

    def to_dict(self) -> Dict:
        return self.__dict__.copy()


def validate_formula(expr: str, allowed_domains: Optional[Set[str]] = None,
                     evaluator: Optional[FactorEvaluator] = None,
                     train_start: Optional[str] = None, train_end: Optional[str] = None) -> ValidationResult:
    res = ValidationResult(valid=False)
    if not isinstance(expr, str) or not expr.strip():
        res.errors.append("SYNTAX: empty formula")
        return res

    # 1. Syntax
    try:
        tree = parse(expr)
    except DSLError as e:
        res.errors.append(f"SYNTAX: {e}")
        return res

    # 2. Structure: node whitelist, function whitelist/arity, window arguments, future references
    names: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Expression, ast.Load, ast.BinOp, ast.UnaryOp, ast.Add, ast.Sub, ast.Mult,
                             ast.Div, ast.USub, ast.UAdd)):
            continue
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                res.errors.append("OPERATOR: only numeric constants are allowed")
            continue
        if isinstance(node, ast.Name):
            if node.id not in FUNCTIONS and node.id not in names:
                names.append(node.id)
            continue
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS:
                fn = getattr(node.func, "id", type(node.func).__name__)
                res.errors.append(f"OPERATOR: function '{fn}' is not allowed")
                continue
            fn = node.func.id
            arity = FUNCTIONS[fn][0]
            if len(node.args) != arity or node.keywords:
                res.errors.append(f"OPERATOR: {fn} expects {arity} positional arguments")
                continue
            if fn in _WINDOW_FUNCS:
                arg = node.args[1]
                neg = isinstance(arg, ast.UnaryOp) and isinstance(arg.op, ast.USub)
                if neg:
                    res.errors.append(f"FUTURE_REFERENCE: {fn} with a negative window/lag would read future rows")
                elif not (isinstance(arg, ast.Constant) and isinstance(arg.value, int) and not isinstance(arg.value, bool)):
                    res.errors.append(f"OPERATOR: {fn} window/lag must be an integer constant")
                elif not 1 <= arg.value <= MAX_WINDOW:
                    res.errors.append(f"OPERATOR: {fn} window/lag must be in [1, {MAX_WINDOW}]")
            continue
        res.errors.append(f"OPERATOR: syntax element {type(node).__name__} is not allowed")

    # 3. Vocabulary: existence, PIT safety, labels, domain restriction
    domains: List[str] = []
    for n in names:
        meta = _REGISTRY.get(n)
        if n.startswith("fwd_") or (meta and meta["category"] == "label"):
            res.errors.append(f"LEAKAGE: '{n}' is a forward-return label and cannot be used in a factor")
            continue
        if meta is None:
            res.errors.append(f"FEATURE: '{n}' is not in the feature registry")
            continue
        if not meta["point_in_time_safe"]:
            res.errors.append(f"PIT: '{n}' is not point-in-time safe")
            continue
        if allowed_domains is not None and meta["category"] not in allowed_domains:
            res.errors.append(f"DOMAIN: '{n}' ({meta['category']}) is not permitted in this configuration")
            continue
        if evaluator is not None and n not in evaluator.panel.columns:
            res.errors.append(f"FEATURE: '{n}' is registered but missing from the panel")
            continue
        if meta["category"] not in domains:
            domains.append(meta["category"])
    res.features, res.domains = names, domains
    if not names:
        res.errors.append("FEATURE: formula references no features")

    # 4. Complexity
    c = complexity(expr)
    res.nodes, res.depth = c["nodes"], c["depth"]
    if c["nodes"] > MAX_NODES or c["depth"] > MAX_DEPTH:
        res.errors.append(f"COMPLEXITY: {c['nodes']} nodes / depth {c['depth']} exceeds limits ({MAX_NODES}/{MAX_DEPTH})")

    if res.errors:
        return res

    # 5. Missing-data rules on the training period (needs data)
    if evaluator is not None:
        try:
            f = evaluator.evaluate(expr)
        except DSLError as e:
            res.errors.append(f"EVALUATION: {e}")
            return res
        if train_start:
            f = f[f.index >= pd.Timestamp(train_start)]
        if train_end:
            f = f[f.index <= pd.Timestamp(train_end)]
        if f.empty:
            res.errors.append("COVERAGE: no rows in the training period")
            return res
        res.coverage = float(f.notna().mean().mean())
        breadth = f.notna().sum(axis=1)
        res.valid_date_share = float((breadth >= MIN_BREADTH).mean())
        dispersion = f.std(axis=1)[breadth >= MIN_BREADTH]  # only dates where the factor is defined
        if res.coverage < MIN_COVERAGE or res.valid_date_share < MIN_VALID_DATES:
            res.errors.append(f"COVERAGE: factor defined on {res.coverage:.0%} of cells and "
                              f"{res.valid_date_share:.0%} of dates (minimum {MIN_COVERAGE:.0%})")
        elif len(dispersion) and (dispersion.fillna(0) < 1e-12).mean() > 0.5:
            res.errors.append("DEGENERATE: factor has no cross-sectional variation on most dates "
                              "(market-wide features must be combined with stock-level features)")
        elif res.coverage < 0.6:
            res.warnings.append(f"Low coverage: {res.coverage:.0%} of training cells")

    res.valid = not res.errors
    return res
