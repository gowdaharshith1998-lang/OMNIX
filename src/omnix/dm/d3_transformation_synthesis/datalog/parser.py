"""Recursive-descent parser for the supported Datalog fragment.

Grammar (informal):
    program     := rule*
    rule        := atom (":-" body)? "."
    body        := body_item ("," body_item)*
    body_item   := atom | "not" atom | constraint | aggregate
    aggregate   := var "=" agg_fn "(" var ")"
    constraint  := expr cmp expr
    expr        := term (arith term)*
    term        := var | const | "(" expr ")"
    atom        := IDENT "(" term ("," term)* ")"
    var         := IDENT starting upper-case
    const       := INTEGER | FLOAT | STRING | IDENT (lower-case)
    cmp         := "==" | "!=" | "<" | "<=" | ">" | ">="
    arith       := "+" | "-" | "*" | "/" | "%"

Comments use ``#`` to end-of-line.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from .ast import Aggregate, ArithConstraint, Atom, Program, Rule, Term


class DatalogSyntaxError(ValueError):
    """Raised when the Datalog source cannot be parsed."""


_TOKEN_RE = re.compile(
    r"""
      (?P<STRING>"(?:[^"\\]|\\.)*")
    | (?P<FLOAT>-?\d+\.\d+)
    | (?P<INT>-?\d+)
    | (?P<NEQ>!=)
    | (?P<LEQ><=)
    | (?P<GEQ>>=)
    | (?P<EQ>==)
    | (?P<LT><)
    | (?P<GT>>)
    | (?P<ASSIGN>=)
    | (?P<TURNSTILE>:-)
    | (?P<DOT>\.)
    | (?P<COMMA>,)
    | (?P<LPAREN>\()
    | (?P<RPAREN>\))
    | (?P<PLUS>\+)
    | (?P<MINUS>-)
    | (?P<STAR>\*)
    | (?P<SLASH>/)
    | (?P<PERCENT>%)
    | (?P<IDENT>[A-Za-z_][A-Za-z0-9_]*)
    | (?P<WS>\s+)
    | (?P<COMMENT>\#[^\n]*)
""",
    re.VERBOSE,
)

_KEYWORDS = {"not"}
_AGG_FNS = {"count", "sum", "min", "max"}


def _tokenize(src: str) -> List[tuple]:
    pos = 0
    tokens: List[tuple] = []
    while pos < len(src):
        m = _TOKEN_RE.match(src, pos)
        if not m:
            raise DatalogSyntaxError(f"unexpected character at {pos}: {src[pos:pos+20]!r}")
        kind = m.lastgroup
        value = m.group()
        pos = m.end()
        if kind in ("WS", "COMMENT"):
            continue
        tokens.append((kind, value))
    return tokens


class _Parser:
    def __init__(self, tokens: List[tuple]):
        self.tokens = tokens
        self.pos = 0

    def peek(self, *kinds: str) -> Optional[tuple]:
        if self.pos >= len(self.tokens):
            return None
        tok = self.tokens[self.pos]
        if kinds and tok[0] not in kinds:
            return None
        return tok

    def eat(self, kind: str) -> tuple:
        tok = self.peek()
        if tok is None or tok[0] != kind:
            raise DatalogSyntaxError(
                f"expected {kind}, got {tok!r} at position {self.pos}"
            )
        self.pos += 1
        return tok

    def at_end(self) -> bool:
        return self.pos >= len(self.tokens)

    # ----- grammar -----

    def parse_program(self) -> Program:
        rules: List[Rule] = []
        while not self.at_end():
            rules.append(self.parse_rule())
        edb = self._compute_edb(tuple(rules))
        return Program(rules=tuple(rules), edb_predicates=edb)

    def parse_rule(self) -> Rule:
        head = self._make_atom(negated=False)
        body_atoms: List[Atom] = []
        constraints: List[ArithConstraint] = []
        aggregate: Optional[Aggregate] = None
        if self.peek("TURNSTILE"):
            self.eat("TURNSTILE")
            while True:
                # Aggregate: "Y = count(X)" / sum/min/max.
                save = self.pos
                agg = self._try_parse_aggregate()
                if agg is not None:
                    if aggregate is not None:
                        raise DatalogSyntaxError("multiple aggregates in one rule")
                    aggregate = agg
                else:
                    self.pos = save
                    item = self.parse_body_item()
                    if isinstance(item, Atom):
                        body_atoms.append(item)
                    else:
                        constraints.append(item)
                if self.peek("COMMA"):
                    self.eat("COMMA")
                else:
                    break
        self.eat("DOT")
        # head var binding check: every var in head must appear in body positive
        # atoms, be the aggregate bind_to, OR be the LHS/RHS of a binding-style
        # constraint ``Var == expr``.
        positive_vars = {
            t.value for atom in body_atoms if not atom.negated for t in atom.terms if t.is_var()
        }
        if aggregate is not None:
            positive_vars.add(aggregate.bind_to)
        for c in constraints:
            if c.op == "==":
                for side in (c.lhs, c.rhs):
                    if isinstance(side, tuple) and len(side) == 2 and side[0] == "var":
                        positive_vars.add(side[1])
        for t in head.terms:
            if t.is_var() and t.value not in positive_vars:
                raise DatalogSyntaxError(
                    f"head variable {t.value!r} not bound by any positive body atom"
                )
        return Rule(
            head=head,
            body=tuple(body_atoms),
            constraints=tuple(constraints),
            aggregate=aggregate,
        )

    def _try_parse_aggregate(self) -> Optional[Aggregate]:
        # pattern: var = fn(var)
        if not self.peek("IDENT"):
            return None
        save = self.pos
        first = self.eat("IDENT")
        if not _is_var_name(first[1]):
            self.pos = save
            return None
        if not self.peek("ASSIGN"):
            self.pos = save
            return None
        self.eat("ASSIGN")
        if not self.peek("IDENT"):
            self.pos = save
            return None
        fn_tok = self.peek()
        if fn_tok[1] not in _AGG_FNS:
            self.pos = save
            return None
        self.eat("IDENT")
        self.eat("LPAREN")
        arg = self.eat("IDENT")
        if not _is_var_name(arg[1]):
            raise DatalogSyntaxError(f"aggregate argument must be a variable, got {arg[1]!r}")
        self.eat("RPAREN")
        return Aggregate(fn=fn_tok[1], var=arg[1], bind_to=first[1])

    def parse_body_item(self):
        tok = self.peek()
        if tok and tok[0] == "IDENT" and tok[1] == "not":
            self.eat("IDENT")
            return self._make_atom(negated=True)
        if tok and tok[0] == "IDENT":
            # could be atom OR constraint LHS (var)
            # We try atom first; if next is "(", it's an atom.
            save = self.pos
            name = self.eat("IDENT")[1]
            if self.peek("LPAREN"):
                self.pos = save
                return self._make_atom(negated=False)
            # back up and parse as constraint
            self.pos = save
        return self.parse_constraint()

    def _make_atom(self, *, negated: bool) -> Atom:
        name = self.eat("IDENT")[1]
        if name in _KEYWORDS or name in _AGG_FNS:
            raise DatalogSyntaxError(f"predicate name {name!r} is reserved")
        self.eat("LPAREN")
        terms: List[Term] = []
        if not self.peek("RPAREN"):
            terms.append(self.parse_term())
            while self.peek("COMMA"):
                self.eat("COMMA")
                terms.append(self.parse_term())
        self.eat("RPAREN")
        return Atom(predicate=name, terms=tuple(terms), negated=negated)

    def parse_term(self) -> Term:
        tok = self.peek()
        if tok is None:
            raise DatalogSyntaxError("unexpected EOF in atom")
        if tok[0] == "STRING":
            self.eat("STRING")
            # strip quotes + decode escapes
            return Term("const", _unquote(tok[1]))
        if tok[0] == "INT":
            self.eat("INT")
            return Term("const", int(tok[1]))
        if tok[0] == "FLOAT":
            self.eat("FLOAT")
            return Term("const", float(tok[1]))
        if tok[0] == "IDENT":
            self.eat("IDENT")
            if _is_var_name(tok[1]):
                return Term("var", tok[1])
            return Term("const", tok[1])
        if tok[0] == "MINUS":
            # negative numeric literal: -5 (after the lexer may not capture it,
            # but tokenize already handles -5; fall through anyway)
            self.eat("MINUS")
            inner = self.parse_term()
            if isinstance(inner.value, (int, float)):
                return Term("const", -inner.value)
            raise DatalogSyntaxError("unary minus only on numeric constants")
        raise DatalogSyntaxError(f"unexpected token in term position: {tok!r}")

    def parse_constraint(self) -> ArithConstraint:
        lhs = self._parse_expr()
        op_tok = self.peek()
        if op_tok is None or op_tok[0] not in (
            "EQ",
            "NEQ",
            "LT",
            "LEQ",
            "GT",
            "GEQ",
        ):
            raise DatalogSyntaxError(
                f"expected comparison operator, got {op_tok!r}"
            )
        op_map = {"EQ": "==", "NEQ": "!=", "LT": "<", "LEQ": "<=", "GT": ">", "GEQ": ">="}
        op = op_map[op_tok[0]]
        self.pos += 1
        rhs = self._parse_expr()
        return ArithConstraint(lhs=lhs, op=op, rhs=rhs)

    def _parse_expr(self):
        """Left-associative expression: term ((+|-|*|/|%) term)*."""
        left = self._parse_primary()
        while True:
            tok = self.peek()
            if tok is None or tok[0] not in ("PLUS", "MINUS", "STAR", "SLASH", "PERCENT"):
                return left
            op_map = {"PLUS": "+", "MINUS": "-", "STAR": "*", "SLASH": "/", "PERCENT": "%"}
            op = op_map[tok[0]]
            self.pos += 1
            right = self._parse_primary()
            left = (left, op, right)

    def _parse_primary(self):
        tok = self.peek()
        if tok is None:
            raise DatalogSyntaxError("unexpected EOF in expression")
        if tok[0] == "LPAREN":
            self.eat("LPAREN")
            e = self._parse_expr()
            self.eat("RPAREN")
            return e
        if tok[0] == "INT":
            self.eat("INT")
            return int(tok[1])
        if tok[0] == "FLOAT":
            self.eat("FLOAT")
            return float(tok[1])
        if tok[0] == "STRING":
            self.eat("STRING")
            return _unquote(tok[1])
        if tok[0] == "IDENT":
            self.eat("IDENT")
            if _is_var_name(tok[1]):
                return ("var", tok[1])
            return tok[1]  # lowercase ident → string constant
        if tok[0] == "MINUS":
            self.eat("MINUS")
            inner = self._parse_primary()
            if isinstance(inner, (int, float)):
                return -inner
            return (0, "-", inner)
        raise DatalogSyntaxError(f"unexpected token in primary: {tok!r}")

    def _compute_edb(self, rules: Tuple[Rule, ...]) -> frozenset:
        defined = {r.head.predicate for r in rules}
        used = set()
        for r in rules:
            for atom in r.body:
                used.add(atom.predicate)
        return frozenset(used - defined)


def _is_var_name(name: str) -> bool:
    return bool(name) and (name[0].isupper() or name[0] == "_")


def _unquote(s: str) -> str:
    return s[1:-1].encode().decode("unicode_escape")


def parse_program(source: str) -> Program:
    """Parse the given Datalog source. Raises :class:`DatalogSyntaxError` on
    malformed input."""
    tokens = _tokenize(source)
    p = _Parser(tokens)
    return p.parse_program()


__all__ = ["DatalogSyntaxError", "parse_program"]
