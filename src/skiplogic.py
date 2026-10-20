"""Skip-logic auditor: reads the `relevant` (skip) expressions straight from the XLSForm and tests every submission.

 SKIP01  an answer exists for a question that should have been skipped
 SKIP02  a required, relevant question has no answer

Supports the expression vocabulary used by the FDAF: ${field}, 'text', numbers, = != < <= > >=, and, or, not(),
selected(), count-selected(), string-length(), number(), true(), false(), if(). A question whose expression uses a field
that is not present in the export at all (e.g. calculate fields that were not exported) is skipped, not guessed.
"""
import math
import re

import openpyxl
import pandas as pd

TOKEN = re.compile(r"\s*(?:(\$\{[^}]+\})|('[^']*'|\"[^\"]*\")|(\d+(?:\.\d+)?)|(!=|<=|>=|=|<|>|\(|\)|,|\+|-|\*)|([A-Za-z_][\w\-\.]*))")


class MissingVar(Exception):
    pass


def _tokenize(expr):
    pos, out = 0, []
    expr = expr.strip()
    while pos < len(expr):
        m = TOKEN.match(expr, pos)
        if not m or m.end() == pos:
            raise ValueError(f"cannot parse near: {expr[pos:pos + 25]!r}")
        var, lit, num, op, ident = m.groups()
        if var: out.append(("var", var[2:-1]))
        elif lit: out.append(("str", lit[1:-1]))
        elif num: out.append(("num", float(num)))
        elif op: out.append(("op", op))
        else:
            out.append(("kw" if ident in ("and", "or", "div", "mod") else "id", ident))
        pos = m.end()
    return out


class Parser:
    def __init__(self, toks):
        self.t, self.i = toks, 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def eat(self):
        tok = self.t[self.i]
        self.i += 1
        return tok

    def parse(self):
        node = self.or_()
        if self.i != len(self.t):
            raise ValueError("unexpected trailing tokens")
        return node

    def or_(self):
        n = self.and_()
        while self.peek() == ("kw", "or"):
            self.eat(); n = ("or", n, self.and_())
        return n

    def and_(self):
        n = self.cmp()
        while self.peek() == ("kw", "and"):
            self.eat(); n = ("and", n, self.cmp())
        return n

    def cmp(self):
        n = self.add()
        if self.peek()[0] == "op" and self.peek()[1] in ("=", "!=", "<", "<=", ">", ">="):
            op = self.eat()[1]
            n = ("cmp", op, n, self.add())
        return n

    def add(self):
        n = self.mul()
        while self.peek()[0] == "op" and self.peek()[1] in ("+", "-"):
            op = self.eat()[1]; n = ("arith", op, n, self.mul())
        return n

    def mul(self):
        n = self.prim()
        while (self.peek()[0] == "op" and self.peek()[1] == "*") or self.peek() in (("kw", "div"), ("kw", "mod")):
            op = self.eat()[1]; n = ("arith", op, n, self.prim())
        return n

    def prim(self):
        kind, val = self.eat()
        if kind == "var": return ("var", val)
        if kind == "str": return ("str", val)
        if kind == "num": return ("num", val)
        if kind == "op" and val == "(":
            n = self.or_(); self.eat(); return n
        if kind == "op" and val == "-":
            return ("arith", "-", ("num", 0.0), self.prim())
        if kind == "id":
            if self.peek() == ("op", "("):
                self.eat(); args = []
                if self.peek() != ("op", ")"):
                    args.append(self.or_())
                    while self.peek() == ("op", ","):
                        self.eat(); args.append(self.or_())
                self.eat()
                return ("fn", val, args)
            return ("str", val)
        raise ValueError(f"unexpected token {kind} {val}")


def _num(v):
    if isinstance(v, bool): return 1.0 if v else 0.0
    if isinstance(v, (int, float)): return float(v)
    try:
        return float(str(v).strip())
    except ValueError:
        return math.nan


def _bool(v):
    if isinstance(v, bool): return v
    if isinstance(v, (int, float)): return v != 0 and not math.isnan(v)
    return str(v) != ""


def _ev(node, ctx, known):
    k = node[0]
    if k in ("str", "num"): return node[1]
    if k == "var":
        if node[1] not in known:
            raise MissingVar(node[1])
        v = ctx.get(node[1], "")
        return "" if v is None or (isinstance(v, float) and math.isnan(v)) else str(v).strip()
    if k == "or": return _bool(_ev(node[1], ctx, known)) or _bool(_ev(node[2], ctx, known))
    if k == "and": return _bool(_ev(node[1], ctx, known)) and _bool(_ev(node[2], ctx, known))
    if k == "arith":
        a, b = _num(_ev(node[2], ctx, known)), _num(_ev(node[3], ctx, known))
        return {"+": lambda: a + b, "-": lambda: a - b, "*": lambda: a * b,
                "div": lambda: a / b if b else math.nan, "mod": lambda: a % b if b else math.nan}[node[1]]()
    if k == "cmp":
        op, a, b = node[1], _ev(node[2], ctx, known), _ev(node[3], ctx, known)
        if isinstance(a, bool) or isinstance(b, bool):
            a, b = _bool(a), _bool(b)
        elif isinstance(a, (int, float)) or isinstance(b, (int, float)) or op in ("<", "<=", ">", ">="):
            a, b = _num(a), _num(b)
            if math.isnan(a) or math.isnan(b):
                return op == "!="
        return {"=": a == b, "!=": a != b, "<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op]
    if k == "fn":
        name, args = node[1], node[2]
        vals = lambda: [_ev(a, ctx, known) for a in args]
        if name == "selected":
            a, b = vals()
            return str(b) in str(a).split()
        if name == "count-selected": return float(len(str(vals()[0]).split()))
        if name == "not": return not _bool(vals()[0])
        if name == "true": return True
        if name == "false": return False
        if name == "string-length": return float(len(str(vals()[0])))
        if name == "number": return _num(vals()[0])
        if name == "boolean": return _bool(vals()[0])
        if name == "if":
            c = _bool(_ev(args[0], ctx, known))
            return _ev(args[1] if c else args[2], ctx, known)
        raise ValueError(f"unsupported function {name}")
    raise ValueError(k)


def compile_expr(expr):
    return Parser(_tokenize(str(expr))).parse()


def load_questions(xlsx_path):
    """List of question dicts with their effective skip expression and whether they sit in a repeat."""
    ws = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)["survey"]
    rows = list(ws.iter_rows(values_only=True))
    head = list(rows[0])
    ix = {h: i for i, h in enumerate(head) if h}
    label_i = next(i for i, h in enumerate(head) if h and str(h).startswith("label"))
    stack, out = [], []
    for r in rows[1:]:
        t, name = r[ix["type"]], r[ix["name"]]
        rel = r[ix["relevant"]] if "relevant" in ix else None
        if t in ("begin_group", "begin_repeat"):
            stack.append((t, name, rel)); continue
        if t in ("end_group", "end_repeat"):
            if stack: stack.pop()
            continue
        if not t or not name or str(t).split()[0] in ("note", "calculate", "start", "end", "today", "deviceid",
                                                       "username", "audit", "begin", "end_group"):
            continue
        rels = [s[2] for s in stack if s[2]] + ([rel] if rel else [])
        req = str(r[ix["required"]]).strip().lower() == "true" if "required" in ix else False
        out.append({"name": name, "type": str(t).split()[0], "relevant": rels, "required": req,
                    "in_repeat": any(s[0] == "begin_repeat" for s in stack), "label": r[label_i]})
    return out


def audit_skip_logic(hh, mem, xlsx_path):
    """Return flag dicts for SKIP01 / SKIP02, plus a small coverage report."""
    qs = load_questions(xlsx_path)
    hh_known, mem_known = set(hh.columns), set(mem.columns)
    hh_rows = hh.to_dict("records")
    mem_by = {}
    for m in mem.to_dict("records"):
        mem_by.setdefault(m["uuid"], []).append(m)
    flags, evaluated, skipped = [], 0, []
    for q in qs:
        try:
            asts = [compile_expr(e) for e in q["relevant"]]
        except ValueError:
            skipped.append(q["name"]); continue
        name = q["name"]
        scope_known = mem_known if q["in_repeat"] else hh_known
        if name not in scope_known:
            continue  # column absent from export - nothing to audit
        fn = q["relevant"]
        evaluated += 1
        rule_txt = " AND ".join(f"({e})" for e in fn) if fn else ""
        for h in hh_rows:
            units = [(h, {**h, **m}, m.get("member_index")) for m in mem_by.get(h["uuid"], [])] if q["in_repeat"] else [(h, h, None)]
            for base, ctx, mi in units:
                val = ctx.get(name, "")
                val = "" if val is None or (isinstance(val, float) and math.isnan(val)) else str(val).strip()
                try:
                    relevant = all(_bool(_ev(a, ctx, set(ctx.keys()) | hh_known | mem_known)) for a in asts)
                except MissingVar:
                    continue
                if not relevant and val != "":
                    flags.append({"uuid": h["uuid"], "member_index": mi, "rule_id": "SKIP01", "severity": "Major",
                                  "level": "member" if mi else "household", "category": "Skip logic",
                                  "rule": "Answer recorded for a question that should have been skipped",
                                  "field": name, "value": val[:80],
                                  "detail": f"'{name}' has an answer but its skip condition is not met",
                                  "action": f"Check whether the earlier answers were changed. This question applies only when: {rule_txt[:160]}. Clear or correct the value."})
                elif relevant and q["required"] and val == "" and q["type"] not in ("note",):
                    flags.append({"uuid": h["uuid"], "member_index": mi, "rule_id": "SKIP02", "severity": "Major",
                                  "level": "member" if mi else "household", "category": "Skip logic",
                                  "rule": "Required question left blank although it applies",
                                  "field": name, "value": "",
                                  "detail": f"'{name}' is required and applies, but is blank",
                                  "action": "Obtain the missing answer from the family (revisit or call back) and correct the record."})
    return flags, {"questions_total": len(qs), "questions_evaluated": evaluated, "unparsed": skipped}
