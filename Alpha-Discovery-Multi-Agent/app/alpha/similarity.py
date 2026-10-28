"""Originality of a factor formula: structural (AST) similarity to formulas already tested.

AlphaAgent-style originality control: a formula that is a trivial rewrite of an earlier one (same sub-expressions,
different constants or wrapper) adds no new information and only inflates the number of trials. Each formula is
reduced to the set of its sub-expression signatures (function name + child signatures, feature names, numeric
constants collapsed to a token); similarity is the Jaccard overlap of these sets.
"""
import ast
from typing import Iterable, List, Optional, Tuple

from app.alpha.dsl import DSLError, parse


def _sig(node) -> str:
    if isinstance(node, ast.Constant):
        return "#"                                          # constants collapse: ts_mean(x, 5) ~ ts_mean(x, 10) structurally
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.UnaryOp):
        return f"{type(node.op).__name__}({_sig(node.operand)})"
    if isinstance(node, ast.BinOp):
        kids = sorted([_sig(node.left), _sig(node.right)]) if isinstance(node.op, (ast.Add, ast.Mult)) else [_sig(node.left), _sig(node.right)]
        return f"{type(node.op).__name__}({','.join(kids)})"
    if isinstance(node, ast.Call):
        return f"{node.func.id}({','.join(_sig(a) for a in node.args)})"
    return type(node).__name__


def signatures(formula: str) -> frozenset:
    """All sub-expression signatures of a formula (empty set if it does not parse)."""
    try:
        tree = parse(formula)
    except DSLError:
        return frozenset()
    sigs = set()

    def walk(n):
        if isinstance(n, (ast.Call, ast.BinOp, ast.UnaryOp, ast.Name)):
            sigs.add(_sig(n))
        for c in ast.iter_child_nodes(n):
            walk(c)

    walk(tree.body)
    return frozenset(sigs)


def similarity(a: str, b: str) -> float:
    sa, sb = signatures(a), signatures(b)
    return len(sa & sb) / len(sa | sb) if sa and sb else 0.0


def most_similar(formula: str, others: Iterable[str]) -> Tuple[float, Optional[str]]:
    best, best_f = 0.0, None
    s = signatures(formula)
    for o in others:
        so = signatures(o)
        v = len(s & so) / len(s | so) if s and so else 0.0
        if v > best:
            best, best_f = v, o
    return best, best_f
