"""Phase 5 - Optimization.

Rewrites the IR with classic relational optimizations, recording every
transformation so the UI can show a before/after plan diff.

Passes:
  1. constant folding      - evaluate literal-only comparisons
  2. predicate pushdown    - move single-table filters below joins
  3. filter merging        - combine adjacent filters on the same input
  4. projection pruning    - drop columns no later stage reads
  5. join reordering       - filtered (smaller) relations join first
  6. limit pushdown        - stop sorting rows that cannot survive the limit
  7. dead code elimination - remove temporaries nothing reads
"""
from .ir import IRProgram, Op


class Optimizer:
    def __init__(self, schema=None):
        self.schema = schema
        self.transformations = []

    def optimize(self, prog):
        ops = [Op(o.kind, o.dest, list(o.args), **dict(o.attrs)) for o in prog.ops]
        self.transformations = []

        ops = self._constant_fold(ops)
        ops = self._pushdown_predicates(ops)
        ops = self._merge_filters(ops)
        ops = self._prune_projections(ops)
        ops = self._reorder_joins(ops)
        ops = self._pushdown_limit(ops)
        ops = self._eliminate_dead_code(ops)

        out = IRProgram(ops)
        out._n = len(ops)
        return out

    def record(self, rule, detail):
        self.transformations.append({"rule": rule, "detail": detail})

    # --- 1. constant folding ---------------------------------------------
    def _constant_fold(self, ops):
        kept = []
        for o in ops:
            pred = o.attrs.get("predicate", "")
            folded = _fold_literal_comparison(pred)
            if folded is True:
                self.record("constant folding",
                            "predicate '%s' is always true - filter removed" % pred)
                _rewire(ops, o.dest, o.args[0])
                continue
            if folded is False:
                self.record("constant folding",
                            "predicate '%s' is always false - query returns no rows" % pred)
                o.attrs["predicate"] = "FALSE"
                o.attrs["contradiction"] = True
            kept.append(o)
        return kept

    # --- 2. predicate pushdown -------------------------------------------
    def _pushdown_predicates(self, ops):
        by_dest = {o.dest: o for o in ops}
        moved = True
        guard = 0
        while moved and guard < 20:
            moved = False
            guard += 1
            for idx, o in enumerate(ops):
                if o.kind != "FILTER" or o.attrs.get("stage"):
                    continue
                tables = set(o.attrs.get("tables") or [])
                if len(tables) != 1:
                    continue
                src = by_dest.get(o.args[0])
                if src is None or src.kind != "JOIN":
                    continue
                target = self._branch_providing(src, by_dest, tables)
                if target is None:
                    continue
                # everything that read the filter now reads the join directly
                _rewire(ops, o.dest, src.dest)
                # splice the filter between `target` and the join
                src.args = [o.dest if a == target else a for a in src.args]
                o.args = [target]
                ops.pop(idx)
                ops.insert(ops.index(src), o)
                self.record("predicate pushdown",
                            "moved filter '%s' below the join - fewer rows enter it"
                            % o.attrs.get("predicate"))
                moved = True
                break
        return ops

    def _branch_providing(self, join_op, by_dest, tables):
        """Which join input supplies exactly the tables this predicate needs."""
        for arg in join_op.args:
            if tables <= self._tables_of(arg, by_dest):
                return arg
        return None

    def _tables_of(self, dest, by_dest, seen=None):
        seen = seen or set()
        if dest in seen:
            return set()
        seen.add(dest)
        op = by_dest.get(dest)
        if op is None:
            return set()
        if op.kind == "SCAN":
            return {op.attrs["table"]}
        out = set()
        for a in op.args:
            out |= self._tables_of(a, by_dest, seen)
        return out

    # --- 3. filter merging -----------------------------------------------
    def _merge_filters(self, ops):
        by_dest = {o.dest: o for o in ops}
        kept = []
        for o in ops:
            if o.kind == "FILTER" and o.args:
                prev = by_dest.get(o.args[0])
                if (prev is not None and prev.kind == "FILTER"
                        and prev.attrs.get("stage") == o.attrs.get("stage")
                        and prev in kept):
                    prev.attrs["predicate"] = "(%s) AND (%s)" % (
                        prev.attrs.get("predicate"), o.attrs.get("predicate"))
                    prev.attrs["tables"] = sorted(
                        set(prev.attrs.get("tables") or []) | set(o.attrs.get("tables") or []))
                    self.record("filter merging",
                                "combined two filters into '%s'" % prev.attrs["predicate"])
                    _rewire(ops, o.dest, prev.dest)
                    continue
            kept.append(o)
        return kept

    # --- 4. projection pruning -------------------------------------------
    def _prune_projections(self, ops):
        project = next((o for o in reversed(ops) if o.kind == "PROJECT"), None)
        if project is None:
            return ops
        needed = set(project.attrs.get("columns") or [])
        for o in ops:
            # join keys must survive pruning even though nothing projects them
            needed |= _columns_in(o.attrs.get("on"))
            for key in ("predicate", "keys", "partition_by", "order_by", "group_by"):
                v = o.attrs.get(key)
                if isinstance(v, str):
                    needed |= _columns_in(v)
                elif isinstance(v, list):
                    for item in v:
                        needed |= _columns_in(str(item))
        scanned = set()
        for o in ops:
            if o.kind == "SCAN":
                tbl = o.attrs["table"]
                cols = sorted(c for c in needed if c.startswith(tbl + "."))
                if cols:
                    o.attrs["columns"] = cols
                    scanned |= set(cols)
        if scanned:
            self.record("projection pruning",
                        "scans narrowed to %d column(s) actually used" % len(scanned))
        return ops

    # --- 5. join reordering ----------------------------------------------
    def _reorder_joins(self, ops):
        by_dest = {o.dest: o for o in ops}
        for o in ops:
            if o.kind != "JOIN" or len(o.args) != 2:
                continue
            left, right = o.args
            if self._is_filtered(left, by_dest) or not self._is_filtered(right, by_dest):
                continue
            o.args = [right, left]
            self.record("join reordering",
                        "filtered relation %s now drives the join" % right)
        return ops

    def _is_filtered(self, dest, by_dest, seen=None):
        seen = seen or set()
        if dest in seen:
            return False
        seen.add(dest)
        op = by_dest.get(dest)
        if op is None:
            return False
        if op.kind == "FILTER":
            return True
        return any(self._is_filtered(a, by_dest, seen) for a in op.args)

    # --- 6. limit pushdown -----------------------------------------------
    def _pushdown_limit(self, ops):
        by_dest = {o.dest: o for o in ops}
        for o in ops:
            if o.kind != "LIMIT":
                continue
            src = by_dest.get(o.args[0])
            # LIMIT over PROJECT over SORT -> bound the sort itself
            while src is not None and src.kind == "PROJECT":
                src = by_dest.get(src.args[0]) if src.args else None
            if src is not None and src.kind == "SORT":
                src.attrs["top_n"] = o.attrs["count"]
                self.record("limit pushdown",
                            "sort keeps only the top %d rows instead of ordering everything"
                            % o.attrs["count"])
        return ops

    # --- 7. dead code elimination ----------------------------------------
    def _eliminate_dead_code(self, ops):
        if not ops:
            return ops
        live = {ops[-1].dest}
        by_dest = {o.dest: o for o in ops}
        stack = [ops[-1].dest]
        while stack:
            d = stack.pop()
            op = by_dest.get(d)
            if not op:
                continue
            for a in op.args:
                if a not in live:
                    live.add(a)
                    stack.append(a)
        dead = [o.dest for o in ops if o.dest not in live]
        if dead:
            self.record("dead code elimination",
                        "removed unused temporaries: %s" % ", ".join(dead))
        return [o for o in ops if o.dest in live]


# --- helpers -------------------------------------------------------------
def _rewire(ops, old, new):
    for o in ops:
        o.args = [new if a == old else a for a in o.args]


def _columns_in(text):
    """Pull table.column references out of an IR expression string."""
    import re
    return set(re.findall(r"\b[a-z_]+\.[a-z_]+\b", text or ""))


def _fold_literal_comparison(pred):
    """Return True/False if a predicate compares two literals, else None."""
    import re
    m = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*(>=|<=|!=|>|<|=)\s*(-?\d+(?:\.\d+)?)\s*",
                     pred or "")
    if not m:
        return None
    a, op, b = float(m.group(1)), m.group(2), float(m.group(3))
    return {">": a > b, "<": a < b, ">=": a >= b,
            "<=": a <= b, "=": a == b, "!=": a != b}[op]
