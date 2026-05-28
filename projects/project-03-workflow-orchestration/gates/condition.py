"""Safe evaluator for programmatic gate conditions.

The gate condition language is the single highest-risk surface in the
engine. Pipeline authors write strings that are evaluated against
prior-step outputs - this is *exactly* the shape that has bitten
multiple production orchestrators because the obvious implementation
(passing the string to Python's dynamic-code-execution function) is
an arbitrary-code-execution sink.

This module implements an AST walker with a closed-world whitelist:
only the nodes listed in `_ALLOWED_NODES` are accepted, every other
node type is rejected. Future Python syntax additions are rejected by
default until explicitly added.

Validate syntax with: python -m py_compile gates/condition.py

Production deployments should swap the in-house walker for
`asteval` (https://lmfit.github.io/asteval/) or `simpleeval`
(https://pypi.org/project/simpleeval/). Both have a longer track
record and the same security posture. The interface (`evaluate()`)
is intentionally narrow so the swap is mechanical.
"""

from __future__ import annotations

import ast
import operator as op
from typing import Any


class UnsafeExpression(Exception):
    """Raised when the expression contains a node not on the allowlist."""


class UndefinedName(Exception):
    """Raised when a name reference cannot be resolved in the context."""


# AST node types the evaluator will descend into. Anything else is
# rejected at parse time. Imports, calls, attribute access,
# subscripts, lambdas, comprehensions are all NOT here - intentionally.
_ALLOWED_NODES: tuple[type[ast.AST], ...] = (
    ast.Expression,
    ast.BoolOp,
    ast.BinOp,
    ast.UnaryOp,
    ast.Compare,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.And,
    ast.Or,
    ast.Not,
    ast.USub,
    ast.UAdd,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
    ast.Tuple,
    ast.List,
)


_BIN_OPS: dict[type[ast.operator], Any] = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.FloorDiv: op.floordiv,
    ast.Mod: op.mod,
}


_CMP_OPS: dict[type[ast.cmpop], Any] = {
    ast.Eq: op.eq,
    ast.NotEq: op.ne,
    ast.Lt: op.lt,
    ast.LtE: op.le,
    ast.Gt: op.gt,
    ast.GtE: op.ge,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}


def evaluate(expression: str, context: dict[str, Any]) -> bool:
    """Evaluate a gate condition against a context dict.

    The context dict maps a name (e.g., `accuracy`) to a literal
    value (number, string, bool, tuple of literals). Step authors
    populate it from the merged outputs of upstream steps.

    Returns a boolean. Raises:
      - `UnsafeExpression` if the expression contains a disallowed
        AST node (the closed-world rejection).
      - `UndefinedName` if a name in the expression is not in the
        context.
    """
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise UnsafeExpression(f"invalid expression syntax: {exc.msg}") from exc

    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise UnsafeExpression(
                f"disallowed node type {type(node).__name__!r} in expression"
            )

    return bool(_eval(tree.body, context))


def _eval(node: ast.AST, ctx: dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, ast.Name):
        if node.id not in ctx:
            raise UndefinedName(f"undefined name in gate context: {node.id!r}")
        return ctx[node.id]

    if isinstance(node, ast.UnaryOp):
        operand = _eval(node.operand, ctx)
        if isinstance(node.op, ast.Not):
            return not operand
        if isinstance(node.op, ast.USub):
            return -operand
        if isinstance(node.op, ast.UAdd):
            return +operand
        # _ALLOWED_NODES gates everything else; unreachable.
        raise UnsafeExpression(f"unsupported unary op {type(node.op).__name__!r}")

    if isinstance(node, ast.BinOp):
        fn = _BIN_OPS.get(type(node.op))
        if fn is None:
            raise UnsafeExpression(f"unsupported binary op {type(node.op).__name__!r}")
        return fn(_eval(node.left, ctx), _eval(node.right, ctx))

    if isinstance(node, ast.BoolOp):
        values = [_eval(v, ctx) for v in node.values]
        if isinstance(node.op, ast.And):
            return all(values)
        if isinstance(node.op, ast.Or):
            return any(values)
        raise UnsafeExpression(f"unsupported bool op {type(node.op).__name__!r}")

    if isinstance(node, ast.Compare):
        left = _eval(node.left, ctx)
        for cmp_op, right_node in zip(node.ops, node.comparators):
            fn = _CMP_OPS.get(type(cmp_op))
            if fn is None:
                raise UnsafeExpression(
                    f"unsupported compare op {type(cmp_op).__name__!r}"
                )
            right = _eval(right_node, ctx)
            if not fn(left, right):
                return False
            left = right
        return True

    if isinstance(node, (ast.Tuple, ast.List)):
        return [_eval(e, ctx) for e in node.elts]

    # _ALLOWED_NODES already rejected anything else; defense in depth.
    raise UnsafeExpression(f"unsupported node {type(node).__name__!r}")
