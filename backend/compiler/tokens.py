"""Token definitions — Phase 1 output vocabulary."""
from dataclasses import dataclass, asdict
from enum import Enum


class TokenType(str, Enum):
    KEYWORD = "KEYWORD"          # show, list, count ...
    TABLE = "TABLE"              # resolved schema table
    COLUMN = "COLUMN"            # resolved schema column
    AGGREGATE = "AGGREGATE"      # avg, sum, max, min, count
    COMPARATOR = "COMPARATOR"    # >, <, =, >=, <=
    LOGICAL = "LOGICAL"          # and, or, not
    ORDER = "ORDER"              # asc, desc
    NUMBER = "NUMBER"
    STRING = "STRING"
    LIMIT = "LIMIT"              # top, first
    GROUP = "GROUP"              # "each", "per", "by"
    VALUE = "VALUE"              # literal matched to a catalog column
    SUPERLATIVE = "SUPERLATIVE"  # youngest, best: an ordering, not an aggregate
    DISTINCT = "DISTINCT"        # distinct, unique
    FORBIDDEN = "FORBIDDEN"      # DDL/DML verb - never legal here
    IDENT = "IDENT"              # unrecognised word
    PUNCT = "PUNCT"
    EOF = "EOF"


@dataclass
class Token:
    type: TokenType
    lexeme: str          # original text
    value: object = None # normalised value (e.g. ">", 85.0, "students")
    pos: int = 0         # character offset in source
    line: int = 1

    def to_dict(self):
        d = asdict(self)
        d["type"] = self.type.value
        return d

    def __repr__(self):
        return f"<{self.type.value} {self.lexeme!r}" + (f" -> {self.value!r}>" if self.value is not None else ">")
