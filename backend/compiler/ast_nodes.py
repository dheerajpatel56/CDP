"""Abstract Syntax Tree — Phase 2 output."""
from dataclasses import dataclass, field


class Node:
    def to_dict(self):
        raise NotImplementedError

    # tree view used by the frontend graph renderer
    def tree(self):
        d = self.to_dict()
        return _to_tree(d, type(self).__name__)


def _to_tree(d, label):
    children = []
    scalars = []
    for k, v in d.items():
        if k == "node":
            continue
        if isinstance(v, dict) and "node" in v:
            children.append(_to_tree(v, f"{k}: {v['node']}"))
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict) and "node" in item:
                    children.append(_to_tree(item, f"{k}: {item['node']}"))
                elif item is not None:
                    scalars.append(f"{k}={item}")
        elif v is not None:
            scalars.append(f"{k}={v}")
    name = label if not scalars else f"{label} ({', '.join(str(s) for s in scalars)})"
    return {"name": name, "children": children}


@dataclass
class ColumnRef(Node):
    table: str
    column: str

    def to_dict(self):
        return {"node": "ColumnRef", "table": self.table, "column": self.column}


@dataclass
class Literal(Node):
    value: object

    def to_dict(self):
        return {"node": "Literal", "value": self.value}


@dataclass
class Extract(Node):
    """A component of a date column, e.g. the year part of admission_date."""
    part: str              # year | month | day
    source: Node           # ColumnRef

    def to_dict(self):
        return {"node": "Extract", "part": self.part, "source": self.source.to_dict()}


@dataclass
class Aggregate(Node):
    func: str              # AVG | SUM | COUNT | MAX | MIN
    target: Node = None    # ColumnRef or None for COUNT(*)

    def to_dict(self):
        return {"node": "Aggregate", "func": self.func,
                "target": self.target.to_dict() if self.target else None}


@dataclass
class Comparison(Node):
    left: Node
    op: str
    right: Node

    def to_dict(self):
        return {"node": "Comparison", "op": self.op,
                "left": self.left.to_dict(), "right": self.right.to_dict()}


@dataclass
class BoolOp(Node):
    op: str                # AND | OR
    operands: list

    def to_dict(self):
        return {"node": "BoolOp", "op": self.op,
                "operands": [o.to_dict() for o in self.operands]}


@dataclass
class NotOp(Node):
    operand: Node

    def to_dict(self):
        return {"node": "NotOp", "operand": self.operand.to_dict()}


@dataclass
class OrderBy(Node):
    target: Node
    direction: str = "ASC"

    def to_dict(self):
        return {"node": "OrderBy", "direction": self.direction,
                "target": self.target.to_dict()}


@dataclass
class Query(Node):
    """Root node. Mirrors a SELECT statement's logical shape."""
    projections: list = field(default_factory=list)   # ColumnRef | Aggregate
    source: str = None                                # base table
    joins: list = field(default_factory=list)         # table names to join in
    where: Node = None
    group_by: list = field(default_factory=list)      # ColumnRef
    having: Node = None
    order_by: list = field(default_factory=list)      # OrderBy
    limit: int = None
    partition_by: list = field(default_factory=list)  # "top N per group"
    distinct: bool = False

    def to_dict(self):
        return {
            "node": "Query",
            "source": self.source,
            "joins": self.joins,
            "distinct": self.distinct,
            "projections": [p.to_dict() for p in self.projections],
            "where": self.where.to_dict() if self.where else None,
            "group_by": [g.to_dict() for g in self.group_by],
            "having": self.having.to_dict() if self.having else None,
            "order_by": [o.to_dict() for o in self.order_by],
            "partition_by": [p.to_dict() for p in self.partition_by],
            "limit": self.limit,
        }
