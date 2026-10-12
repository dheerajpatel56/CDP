"""Phase 2 - Syntax analysis.

Recursive-descent parser over the token stream. Natural language has no strict
grammar, so the parser is intent-driven: it recognises clause patterns in any
order and folds them into a single Query node. Unrecognised tokens are reported
as syntax diagnostics rather than aborting the parse.
"""
from .ast_nodes import (Aggregate, BoolOp, ColumnRef, Comparison, Extract,
                        Literal, NotOp, OrderBy, Query)
from .tokens import TokenType as TT


# Words that only glue the sentence together. The parser looks through them when
# deciding whether a clause continues, but never derives meaning from them.
FILLER = {
    "are", "is", "was", "were", "be", "been", "that", "who", "whose", "which",
    "with", "of", "in", "from", "the", "a", "an", "has", "have", "had", "and",
    "there", "me", "all",
}


class ParseError(Exception):
    pass


class Parser:
    def __init__(self, tokens, schema):
        self.tokens = tokens
        self.schema = schema
        self.i = 0
        self.diagnostics = []

    # --- token helpers ---------------------------------------------------
    @property
    def cur(self):
        return self.tokens[self.i]

    def peek(self, k=1):
        j = min(self.i + k, len(self.tokens) - 1)
        return self.tokens[j]

    def advance(self):
        tok = self.tokens[self.i]
        if self.cur.type is not TT.EOF:
            self.i += 1
        return tok

    def at(self, *types):
        return self.cur.type in types

    def _skip_filler(self, start):
        """Index of the next token that carries meaning, looking past glue words."""
        j = start
        while (
            j < len(self.tokens) - 1
            and self.tokens[j].type is TT.KEYWORD
            and self.tokens[j].value in FILLER
        ):
            j += 1
        return j

    def _is_count_comparison(self, i):
        """'more than 20 students' compares a row count, not a column value."""
        j = self._skip_filler(i)
        if self.tokens[j].type is not TT.COMPARATOR:
            return False
        if self.tokens[j + 1].type is not TT.NUMBER:
            return False
        return self.tokens[j + 2].type is TT.TABLE

    def warn(self, msg, tok=None):
        tok = tok or self.cur
        self.diagnostics.append({
            "severity": "warning", "message": msg,
            "lexeme": tok.lexeme, "pos": tok.pos,
        })

    # --- entry point -----------------------------------------------------
    def parse(self):
        q = Query()
        self._collect_tables(q)

        while not self.at(TT.EOF):
            t = self.cur
            if t.type is TT.LIMIT:
                self._parse_limit(q)
            elif t.type is TT.GROUP:
                self._parse_group(q)
            elif t.type is TT.ORDER:
                self._parse_order(q)
            elif t.type is TT.AGGREGATE:
                self._parse_aggregate(q)
            elif t.type is TT.COLUMN:
                self._parse_column_clause(q)
            elif t.type is TT.VALUE:
                self._parse_value(q)
            elif t.type is TT.SUPERLATIVE:
                self._parse_superlative(q)
            elif t.type is TT.DISTINCT:
                self.advance()
                q.distinct = True
            elif t.type is TT.COMPARATOR and self._is_count_comparison(self.i):
                self._parse_count_comparison(q)
            elif t.type is TT.FORBIDDEN:
                raise ParseError(
                    "'%s' is not a query - this compiler only translates "
                    "questions that read data" % t.lexeme)
            elif t.type is TT.LOGICAL and t.value == "NOT":
                self._parse_not(q)
            elif t.type is TT.IDENT:
                self.warn("unrecognised word '%s' - ignored" % t.lexeme)
                self.advance()
            else:
                self.advance()

        self._finalize(q)
        return q

    # --- clause parsers --------------------------------------------------
    def _collect_tables(self, q):
        """First pass: pick the source table and any other mentioned tables."""
        seen = []
        for t in self.tokens:
            if t.type is TT.TABLE and t.value not in seen:
                seen.append(t.value)
            if t.type is TT.COLUMN and t.value[0] not in seen:
                seen.append(t.value[0])
            if t.type is TT.VALUE and t.value[0] not in seen:
                seen.append(t.value[0])
        if not seen:
            raise ParseError("no table or column recognised in the query")
        q.source = seen[0]
        q.joins = seen[1:]

    def _parse_limit(self, q):
        kind = self.advance().value              # top | first | bottom | limit
        if self.at(TT.NUMBER):
            q.limit = int(self.advance().value)
        else:
            q.limit = 1
            self.warn("limit keyword without a number - defaulting to 1")
        if kind == "bottom":
            q._limit_from_bottom = True

    def _parse_group(self, q):
        self.advance()                            # consume each/per/by
        if self.at(TT.TABLE):
            tbl = self.advance().value
            col = self.schema.resolve_column("name", tbl)
            if col:
                q.group_by.append(ColumnRef(*col))
            if tbl not in q.joins and tbl != q.source:
                q.joins.append(tbl)
        elif self.at(TT.COLUMN):
            q.group_by.append(ColumnRef(*self.advance().value))
        else:
            self.warn("grouping keyword without a group target")

    def _parse_order(self, q):
        tok = self.advance()
        if tok.value == "ORDER_BY":
            target = self._parse_operand()
            direction = "ASC"
            if self.at(TT.ORDER):
                direction = self.advance().value
            if target:
                q.order_by.append(OrderBy(target, direction))
            return
        # bare "descending" attaches to the last ordered target
        if q.order_by:
            q.order_by[-1].direction = tok.value
            return
        target = None
        if self.at(TT.COLUMN):
            target = ColumnRef(*self.advance().value)
        if target:
            q.order_by.append(OrderBy(target, tok.value))
        else:
            q._pending_order = tok.value

    def _parse_aggregate(self, q):
        func = self.advance().value
        target = None
        if self.at(TT.COLUMN):
            target = ColumnRef(*self.advance().value)
        elif self.at(TT.TABLE) and func == "COUNT":
            self.advance()                        # COUNT(*) over the table
        agg = Aggregate(func, target)

        # "average marks greater than 70" -> HAVING clause
        if self.at(TT.COMPARATOR):
            cmp_node = self._parse_comparison_tail(agg)
            q.having = self._merge(q.having, cmp_node)
        else:
            q.projections.append(agg)

    def _parse_column_clause(self, q):
        col = ColumnRef(*self.advance().value)

        # "cities with at least 15 students" counts rows per city; the comparator
        # belongs to the count, not to the city column.
        if self._is_count_comparison(self.i):
            q.projections.append(col)
            return

        j = self._skip_filler(self.i)
        nxt = self.tokens[j]

        if nxt.type is TT.COMPARATOR:
            self.i = j
            cond = self._parse_comparison_tail(col)
            q.where = self._merge(q.where, cond)
        elif nxt.type is TT.ORDER:
            self.i = j
            direction = self.advance().value
            q.order_by.append(OrderBy(col, direction))
        elif nxt.type in (TT.NUMBER, TT.STRING):
            # "admitted in 2023": a bare literal after a column means equality
            self.i = j
            value = self.advance().value
            q.where = self._merge(q.where, Comparison(col, "=", Literal(value)))
        else:
            q.projections.append(col)

    def _parse_value(self, q):
        """A bare literal the catalog recognised: "from Mumbai" -> city = 'Mumbai'."""
        table, column, original = self.advance().value
        col = ColumnRef(table, column)
        if self.at(TT.COMPARATOR):
            cond = self._parse_comparison_tail(col)
        else:
            cond = Comparison(col, "=", Literal(original))
        q.where = self._merge(q.where, cond)

    def _parse_count_comparison(self, q):
        """'departments with more than 20 students' becomes HAVING COUNT(*) > 20."""
        self.i = self._skip_filler(self.i)
        op = self.advance().value
        count = self.advance().value          # the NUMBER guarded by _is_count_comparison
        if self.at(TT.TABLE):
            self.advance()
        q.having = self._merge(q.having, Comparison(Aggregate("COUNT", None), op,
                                                    Literal(count)))

    def _parse_superlative(self, q):
        """'youngest 5 students' is an ordering plus a limit, not an aggregate."""
        column, direction = self.advance().value
        resolved = self.schema.resolve_column(column)
        if not resolved:
            self.warn("no column named '%s' to rank by" % column)
            return
        q.order_by.append(OrderBy(ColumnRef(*resolved), direction))
        if self.at(TT.NUMBER):
            q.limit = int(self.advance().value)
        elif q.limit is None:
            q.limit = 1

    def _parse_comparison_tail(self, left):
        op = self.advance().value
        if op == "BETWEEN":
            lo = self._parse_operand()
            if self.at(TT.LOGICAL) and self.cur.value == "AND":
                self.advance()
            hi = self._parse_operand()
            return BoolOp("AND", [
                Comparison(left, ">=", lo or Literal(None)),
                Comparison(left, "<=", hi or Literal(None)),
            ])
        right = self._parse_operand()
        if right is None:
            self.warn("comparison '%s' is missing a right-hand value" % op)
            right = Literal(None)
        return Comparison(left, op, right)

    def _parse_operand(self):
        if self.at(TT.NUMBER, TT.STRING):
            return Literal(self.advance().value)
        if self.at(TT.COLUMN):
            return ColumnRef(*self.advance().value)
        if self.at(TT.AGGREGATE):
            func = self.advance().value
            target = ColumnRef(*self.advance().value) if self.at(TT.COLUMN) else None
            return Aggregate(func, target)
        if self.at(TT.VALUE):
            return Literal(self.advance().value[2])
        if self.at(TT.IDENT):
            return Literal(self.advance().value)
        return None

    def _parse_not(self, q):
        """Negates the predicate that follows, whatever form it takes."""
        self.advance()
        self.i = self._skip_filler(self.i)
        inner = None

        if self.at(TT.VALUE):
            table, column, original = self.advance().value
            col = ColumnRef(table, column)
            inner = (self._parse_comparison_tail(col) if self.at(TT.COMPARATOR)
                     else Comparison(col, "=", Literal(original)))
        elif self.at(TT.COLUMN):
            col = ColumnRef(*self.advance().value)
            self.i = self._skip_filler(self.i)
            if self.at(TT.COMPARATOR):
                inner = self._parse_comparison_tail(col)
            elif self.at(TT.NUMBER, TT.STRING):
                inner = Comparison(col, "=", Literal(self.advance().value))

        if inner is None:
            self.warn("'not' without a condition to negate")
            return
        q.where = self._merge(q.where, NotOp(inner))

    # --- combination -----------------------------------------------------
    def _merge(self, existing, new):
        """Fold a new predicate into the accumulated boolean tree."""
        if new is None:
            return existing
        if existing is None:
            return new
        op = "AND"
        # look backwards for an explicit OR connecting the two predicates
        for k in range(self.i - 1, max(self.i - 8, -1), -1):
            if self.tokens[k].type is TT.LOGICAL and self.tokens[k].value in ("AND", "OR"):
                op = self.tokens[k].value
                break
        if isinstance(existing, BoolOp) and existing.op == op:
            existing.operands.append(new)
            return existing
        return BoolOp(op, [existing, new])

    # --- post-processing -------------------------------------------------
    def _finalize(self, q):
        pending = getattr(q, "_pending_order", None)
        if pending and q.projections:
            last_col = next((p for p in reversed(q.projections)
                             if isinstance(p, (ColumnRef, Aggregate))), None)
            if last_col:
                q.order_by.append(OrderBy(last_col, pending))

        # "top N" implies an ordering; default to the first numeric predicate
        if q.limit and not q.order_by:
            target = self._infer_rank_target(q)
            if target:
                direction = "ASC" if getattr(q, "_limit_from_bottom", False) else "DESC"
                q.order_by.append(OrderBy(target, direction))

        # "top N per group" is a partitioned rank, not a plain LIMIT
        if q.limit and q.group_by and not q.having:
            q.partition_by = list(q.group_by)
            q.group_by = []

        if not q.projections:
            q.projections = self._default_projections(q)

        # a grouped query must project what it grouped by, before the aggregates
        for g in reversed(q.group_by):
            if not any(isinstance(p, ColumnRef) and p.table == g.table
                       and p.column == g.column for p in q.projections):
                q.projections.insert(0, ColumnRef(g.table, g.column))

    def _infer_rank_target(self, q):
        found = []

        def walk(n):
            if isinstance(n, Comparison):
                if isinstance(n.left, ColumnRef):
                    found.append(n.left)
                walk(n.right)
            elif isinstance(n, BoolOp):
                for o in n.operands:
                    walk(o)
            elif isinstance(n, NotOp):
                walk(n.operand)

        walk(q.where)
        if found:
            return found[0]
        for p in q.projections:
            if isinstance(p, (ColumnRef, Aggregate)):
                return p
        tbl = self.schema.tables.get(q.source)
        if tbl:
            for c in tbl.columns:
                if c.type in ("int", "float") and c.name != "id" and not c.name.endswith("_id"):
                    return ColumnRef(q.source, c.name)
        return None

    def _default_projections(self, q):
        """No explicit columns requested -> project the table's identity columns."""
        out = []
        tbl = self.schema.tables.get(q.source)
        if tbl:
            for c in tbl.columns:
                if c.name in ("name", "title"):
                    out.append(ColumnRef(tbl.name, c.name))
        for g in q.group_by + q.partition_by:
            if g not in out:
                out.insert(0, g)
        for o in q.order_by:
            if isinstance(o.target, ColumnRef) and o.target not in out:
                out.append(o.target)
        if not out and tbl:
            out = [ColumnRef(tbl.name, c.name) for c in tbl.columns[:4]]
        return out
