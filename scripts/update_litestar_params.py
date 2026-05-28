"""Migrate Litestar inferred path/query parameters to FromPath/FromQuery.

Litestar 2.x deprecated the practice of inferring a route parameter's source
(path vs. query) from its name and the route's URL template. The replacement is
an explicit annotation:

- ``param: UUID``                ->  ``param: FromPath[UUID]``    (path)
- ``param: str | None = None``   ->  ``param: FromQuery[str | None] = None``

This script does the rewrite mechanically using libcst, so formatting and
comments are preserved. ``FromPath`` / ``FromQuery`` are imported from
``litestar.params`` when needed.

Usage
-----

    uv run python scripts/update_litestar_params.py src/ac_sciences/web/controllers/*.py

The script is idempotent: already-migrated files are left unchanged. Always
follow up with ``uv run ruff check . --fix && uv run ruff format .`` and the
test suite to confirm the rewrite is sound.

What gets rewritten
-------------------

For each function decorated with a Litestar route decorator (``@get``,
``@post``, ``@put``, ``@patch``, ``@delete``, ``@head``, ``@route``):

* Parameters whose name appears in the route path (``{name:type}``) get their
  annotation wrapped in ``FromPath[...]``.
* Other parameters with a default value get wrapped in ``FromQuery[...]``,
  unless their annotation is already ``FromDishka[...]``, ``FromPath[...]``,
  ``FromQuery[...]``, an ``Annotated[..., Body(...) | Parameter(...) | ...]``
  marker, or one of the well-known Litestar carrier types (``Request``,
  ``State``, etc.).
* ``self``, ``cls``, ``request``, ``data`` and a few similar reserved names
  are skipped regardless.

Requirements
------------

``libcst`` is not in the project's dependencies — install it on the fly:

    uv pip install libcst
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import libcst as cst
import libcst.matchers as m

ROUTE_DECORATORS = {"get", "post", "put", "patch", "delete", "head", "route"}

# Parameter names that are never path/query parameters.
SKIP_PARAM_NAMES = {"self", "cls", "request", "state", "scope", "socket", "data"}

# Type annotations that mark a Litestar carrier (not a path/query param).
SKIP_PARAM_ANNOTATION_NAMES = {"Request", "Body", "State", "Scope", "WebSocket"}


def extract_path_params(path: str) -> list[tuple[str, str]]:
    """Return the (name, type) pairs declared in a Litestar route path."""
    return re.findall(r"\{(\w+)\s*:\s*(\w+)\}", path)


def _module_name(expr: cst.BaseExpression) -> str:
    if isinstance(expr, cst.Name):
        return expr.value
    if isinstance(expr, cst.Attribute):
        return f"{_module_name(expr.value)}.{expr.attr.value}"
    return ""


def _decorator_name(dec: cst.Decorator) -> str | None:
    expr = dec.decorator
    if not isinstance(expr, cst.Call):
        return None
    func = expr.func
    if isinstance(func, cst.Name):
        return func.value
    if isinstance(func, cst.Attribute) and isinstance(func.attr, cst.Name):
        return func.attr.value
    return None


def _has_route_decorator(decorators: tuple[cst.Decorator, ...]) -> bool:
    return any(_decorator_name(d) in ROUTE_DECORATORS for d in decorators)


def annotation_is_fromdishka(annotation: cst.BaseExpression) -> bool:
    return m.matches(annotation, m.Subscript(value=m.Name("FromDishka")))


def annotation_is_already_wrapped(annotation: cst.BaseExpression) -> bool:
    return m.matches(
        annotation, m.Subscript(value=m.Name("FromPath") | m.Name("FromQuery"))
    )


def annotation_has_body_or_param(annotation: cst.BaseExpression) -> bool:
    """Return True if the annotation is ``Annotated[..., Body|Parameter|...]``."""
    if not m.matches(annotation, m.Subscript(value=m.Name("Annotated"))):
        return False
    assert isinstance(annotation, cst.Subscript)
    markers = m.OneOf(
        m.Call(func=m.Name("Body")),
        m.Call(func=m.Name("Parameter")),
        m.Call(func=m.Name("PathParameter")),
        m.Call(func=m.Name("QueryParameter")),
    )
    for el in annotation.slice:
        if isinstance(el.slice, cst.Index) and m.matches(el.slice.value, markers):
            return True
    return False


def annotation_name_is_skip(annotation: cst.BaseExpression) -> bool:
    return (
        isinstance(annotation, cst.Name)
        and annotation.value in SKIP_PARAM_ANNOTATION_NAMES
    )


class MigrationTransformer(cst.CSTTransformer):
    """Rewrite inferred path/query params and patch imports as needed."""

    def __init__(self) -> None:
        self.needs_frompath = False
        self.needs_fromquery = False
        self.has_frompath = False
        self.has_fromquery = False
        self._current_path_params: list[set[str]] = []

    # -- track existing imports -------------------------------------------------

    def visit_ImportFrom(self, node: cst.ImportFrom) -> None:
        if node.module is None or isinstance(node.names, cst.ImportStar):
            return
        if _module_name(node.module) != "litestar.params":
            return
        for alias in node.names:
            if not isinstance(alias.name, cst.Name):
                continue
            if alias.name.value == "FromPath":
                self.has_frompath = True
            if alias.name.value == "FromQuery":
                self.has_fromquery = True

    # -- rewrite route handlers -------------------------------------------------

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        self._current_path_params.append(self._extract_path_params(node.decorators))

    def leave_FunctionDef(
        self,
        original_node: cst.FunctionDef,
        updated_node: cst.FunctionDef,
    ) -> cst.FunctionDef:
        path_params = self._current_path_params.pop()
        if not _has_route_decorator(original_node.decorators):
            return updated_node
        return updated_node.with_changes(
            params=self._rewrite_params(updated_node.params, path_params)
        )

    def _extract_path_params(self, decorators: tuple[cst.Decorator, ...]) -> set[str]:
        params: set[str] = set()
        for dec in decorators:
            if _decorator_name(dec) not in ROUTE_DECORATORS:
                continue
            assert isinstance(dec.decorator, cst.Call)
            for arg in dec.decorator.args:
                if arg.keyword is not None:
                    continue
                self._collect_path_params_from(arg.value, params)
                break  # only the first positional arg is the path
        return params

    @staticmethod
    def _collect_path_params_from(value: cst.BaseExpression, out: set[str]) -> None:
        if isinstance(value, cst.SimpleString):
            s = value.evaluated_value
            if isinstance(s, str):
                out.update(name for name, _ in extract_path_params(s))
        elif isinstance(value, (cst.List, cst.Tuple)):
            for el in value.elements:
                if isinstance(el.value, cst.SimpleString):
                    s = el.value.evaluated_value
                    if isinstance(s, str):
                        out.update(name for name, _ in extract_path_params(s))

    def _rewrite_params(
        self, params: cst.Parameters, path_params: set[str]
    ) -> cst.Parameters:
        def rewrite_list(
            param_list: tuple[cst.Param, ...],
        ) -> tuple[cst.Param, ...]:
            return tuple(self._rewrite_param(p, path_params) for p in param_list)

        return params.with_changes(
            params=rewrite_list(params.params),
            kwonly_params=rewrite_list(params.kwonly_params),
            posonly_params=rewrite_list(params.posonly_params),
        )

    def _rewrite_param(self, param: cst.Param, path_params: set[str]) -> cst.Param:
        name = param.name.value
        if name in SKIP_PARAM_NAMES or param.annotation is None:
            return param

        annot_expr = param.annotation.annotation
        if (
            annotation_is_fromdishka(annot_expr)
            or annotation_is_already_wrapped(annot_expr)
            or annotation_name_is_skip(annot_expr)
            or annotation_has_body_or_param(annot_expr)
        ):
            return param

        is_path = name in path_params
        is_query = (not is_path) and (param.default is not None)
        if not (is_path or is_query):
            return param

        wrapper = "FromPath" if is_path else "FromQuery"
        if is_path:
            self.needs_frompath = True
        else:
            self.needs_fromquery = True

        new_annot = cst.Subscript(
            value=cst.Name(wrapper),
            slice=[cst.SubscriptElement(slice=cst.Index(value=annot_expr))],
        )
        return param.with_changes(annotation=cst.Annotation(annotation=new_annot))

    # -- patch imports ----------------------------------------------------------

    def leave_Module(
        self, original_node: cst.Module, updated_node: cst.Module
    ) -> cst.Module:
        need_frompath = self.needs_frompath and not self.has_frompath
        need_fromquery = self.needs_fromquery and not self.has_fromquery
        if not (need_frompath or need_fromquery):
            return updated_node

        new_body = list(updated_node.body)

        # Extend an existing `from litestar.params import ...` if present.
        for i, stmt in enumerate(new_body):
            if not isinstance(stmt, cst.SimpleStatementLine):
                continue
            for j, small in enumerate(stmt.body):
                if (
                    not isinstance(small, cst.ImportFrom)
                    or small.module is None
                    or isinstance(small.names, cst.ImportStar)
                    or _module_name(small.module) != "litestar.params"
                ):
                    continue
                existing = {
                    a.name.value for a in small.names if isinstance(a.name, cst.Name)
                }
                to_add: list[str] = []
                if need_frompath and "FromPath" not in existing:
                    to_add.append("FromPath")
                if need_fromquery and "FromQuery" not in existing:
                    to_add.append("FromQuery")
                if not to_add:
                    return updated_node
                merged = sorted(existing | set(to_add))
                new_aliases = tuple(cst.ImportAlias(name=cst.Name(n)) for n in merged)
                new_stmt_body = list(stmt.body)
                new_stmt_body[j] = small.with_changes(names=new_aliases)
                new_body[i] = stmt.with_changes(body=tuple(new_stmt_body))
                return updated_node.with_changes(body=tuple(new_body))

        # Otherwise, insert a fresh import after the last litestar.* import.
        last_litestar_idx = -1
        for i, stmt in enumerate(new_body):
            if not isinstance(stmt, cst.SimpleStatementLine):
                continue
            for small in stmt.body:
                if (
                    isinstance(small, cst.ImportFrom)
                    and small.module is not None
                    and _module_name(small.module).startswith("litestar")
                ):
                    last_litestar_idx = i

        to_add = []
        if need_frompath:
            to_add.append("FromPath")
        if need_fromquery:
            to_add.append("FromQuery")
        new_import = cst.SimpleStatementLine(
            body=[
                cst.ImportFrom(
                    module=cst.Attribute(
                        value=cst.Name("litestar"),
                        attr=cst.Name("params"),
                    ),
                    names=tuple(
                        cst.ImportAlias(name=cst.Name(n)) for n in sorted(to_add)
                    ),
                ),
            ]
        )
        insert_at = last_litestar_idx + 1 if last_litestar_idx >= 0 else 0
        new_body.insert(insert_at, new_import)
        return updated_node.with_changes(body=tuple(new_body))


def process_file(path: Path) -> bool:
    """Rewrite ``path`` in place. Return True if anything changed."""
    src = path.read_text()
    tree = cst.parse_module(src)
    new_tree = tree.visit(MigrationTransformer())
    if new_tree.code == src:
        return False
    path.write_text(new_tree.code)
    return True


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2

    changed = 0
    for f in argv:
        p = Path(f)
        if not p.exists():
            print(f"skip (missing): {f}")
            continue
        if process_file(p):
            print(f"modified: {f}")
            changed += 1
        else:
            print(f"unchanged: {f}")
    print(f"\n{changed} file(s) modified.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
