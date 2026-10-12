"""Phase 4 - Intermediate representation.

The AST is lowered into a linear sequence of relational-algebra operations in
three-address form: each instruction writes a temporary (t0, t1, ...) and reads
temporaries produced earlier. This is the form the optimizer rewrites and the
code generator walks.

    t0 = SCAN students
    t1 = SCAN departments
    t2 = JOIN t0, t1 ON students.department_id = departments.id
    t3 = FILTER t2 WHERE students.marks > 85
    t4 = RANK t3 PARTITION BY departments.name ORDER BY students.marks DESC
    t5 = FILTER t4 WHERE rank <= 5
    t6 = PROJECT t5 [departments.name, students.name, students.marks]
"""
from .ast_nodes import (Aggregate, BoolOp, ColumnRef, Comparison, Extract,
                        Literal, NotOp)


class Op:
    """One IR instruction."""

    def __init__(self, kind, dest, args=None, **attrs):
        self.kind = kind          # SCAN | JOIN | FILTER | PROJECT | ...
        self.dest = dest          # temporary this writes
        self.args = args or []    # temporaries this reads
        self.attrs = attrs        # operation payload

    def to_dict(self):
        d = {"kind": self.kind, "dest": self.dest, "args": self.args}
        # attributes prefixed with "_" are internal (AST handles, not reportable)
        d.update({k: v for k, v in self.attrs.items() if not k.startswith("_")})
        return d

    def __repr__(self):
        return "%s = %s %s %s" % (self.dest, self.kind,
                                  ", ".join(self.args), self.attrs or "")


class IRProgram:
    def __init__(self, ops=None):
        self.ops = ops or []
        self._n = len(self.ops)

    def emit(self, kind, args=None, **attrs):
        dest = "t%d" % self._n
        self._n += 1
        op = Op(kind, dest, args, **attrs)
        self.ops.append(op)
        return dest

    @property
    def result(self):
        return self.ops[-1].dest if self.ops else None

    def to_dict(self):
        return [o.to_dict() for o in self.ops]

    def text(self):
        """Human-readable listing - what the UI shows as 'intermediate code'."""
        lines = []
        for o in self.ops:
            parts = [o.dest, "=", o.kind]
            if o.args:
                parts.append(", ".join(o.args))
            for k, v in o.attrs.items():
                if k.startswith("_") or v in (None, [], ""):
                    continue
                parts.append("%s %s" % (k.upper().replace("_", " "), _fmt(v)))
            lines.append(" ".join(parts))
        return "\n".join(lines)


def _fmt(v):
    if isinstance(v, list):
        return "[" + ", ".join(_fmt(x) for x in v) + "]"
    return str(v)


def expr_str(node):
    """Render an expression node as IR text."""
    if isinstance(node, ColumnRef):
        return "%s.%s" % (node.table, node.column)
    if isinstance(node, Literal):
        return repr(node.value)
    if isinstance(node, Extract):
        return "%s(%s)" % (node.part.upper(), expr_str(node.source))
    if isinstance(node, Aggregate):
        return "%s(%s)" % (node.func, expr_str(node.target) if node.target else "*")
    if isinstance(node, Comparison):
        return "%s %s %s" % (expr_str(node.left), node.op, expr_str(node.right))
    if isinstance(node, BoolOp):
        return (" %s " % node.op).join("(%s)" % expr_str(o) for o in node.operands)
    if isinstance(node, NotOp):
        return "NOT (%s)" % expr_str(node.operand)
    return str(node)


def flatten_predicate(node):
    """Split a conjunction into independent predicates the optimizer can move."""
    if node is None:
        return []
    if isinstance(node, BoolOp) and node.op == "AND":
        out = []
        for o in node.operands:
            out.extend(flatten_predicate(o))
        return out
    return [node]


def predicate_tables(node):
    """Set of tables a predicate touches - drives predicate pushdown."""
    tables = set()

    def walk(n):
        if isinstance(n, ColumnRef):
            tables.add(n.table)
        elif isinstance(n, Extract):
            walk(n.source)
        elif isinstance(n, Aggregate) and n.target:
            walk(n.target)
        elif isinstance(n, Comparison):
            walk(n.left)
            walk(n.right)
        elif isinstance(n, BoolOp):
            for o in n.operands:
                walk(o)
        elif isinstance(n, NotOp):
            walk(n.operand)

    walk(node)
    return tables


def lower(query, join_plan):
    """AST + resolved join plan -> IRProgram."""
    prog = IRProgram()

    scans = {query.source: prog.emit("SCAN", table=query.source)}
    cur = scans[query.source]

    for step in join_plan:
        if step.right not in scans:
            scans[step.right] = prog.emit("SCAN", table=step.right)
        cur = prog.emit("JOIN", [cur, scans[step.right]],
                        on="%s.%s = %s.%s" % (step.left, step.left_col,
                                              step.right, step.right_col),
                        join_type="INNER")

    for pred in flatten_predicate(query.where):
        cur = prog.emit("FILTER", [cur], predicate=expr_str(pred),
                        tables=sorted(predicate_tables(pred)), _node=pred)

    if query.group_by:
        cur = prog.emit("AGGREGATE", [cur],
                        group_by=[expr_str(g) for g in query.group_by],
                        aggregates=[expr_str(p) for p in query.projections
                                    if isinstance(p, Aggregate)])

    for pred in flatten_predicate(query.having):
        cur = prog.emit("FILTER", [cur], predicate=expr_str(pred),
                        tables=sorted(predicate_tables(pred)),
                        stage="post_aggregate", _node=pred)

    if query.partition_by:
        order = query.order_by[0] if query.order_by else None
        cur = prog.emit("RANK", [cur],
                        partition_by=[expr_str(p) for p in query.partition_by],
                        order_by=("%s %s" % (expr_str(order.target), order.direction)
                                  if order else None))
        cur = prog.emit("FILTER", [cur], predicate="rank <= %d" % query.limit,
                        stage="post_rank")
    elif query.order_by:
        cur = prog.emit("SORT", [cur],
                        keys=["%s %s" % (expr_str(o.target), o.direction)
                              for o in query.order_by])

    cur = prog.emit("PROJECT", [cur],
                    columns=[expr_str(p) for p in query.projections],
                    distinct=query.distinct)

    if query.limit and not query.partition_by:
        cur = prog.emit("LIMIT", [cur], count=query.limit)

    return prog
