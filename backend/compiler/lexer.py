"""Phase 1 — Lexical analysis.

Scans raw natural-language text into a typed token stream. Multi-word phrases
("greater than", "sorted by", "department name") are matched greedily before
single words, mirroring maximal-munch in a classic lexer.
"""
import datetime
import re

from .tokens import Token, TokenType

# --- lexical tables -----------------------------------------------------
KEYWORDS = {
    "show", "list", "display", "get", "find", "give", "fetch", "select",
    "retrieve", "who", "which", "what", "all", "from", "in", "of", "with",
    "where", "that", "are", "is", "the", "me",
}

AGGREGATES = {
    "average": "AVG", "avg": "AVG", "mean": "AVG",
    "total": "SUM", "sum": "SUM",
    "count": "COUNT", "number": "COUNT", "how many": "COUNT",
    "maximum": "MAX", "max": "MAX", "highest": "MAX", "top scoring": "MAX",
    "minimum": "MIN", "min": "MIN", "lowest": "MIN",
}

# longest phrases first so maximal munch works
COMPARATORS = {
    "greater than or equal to": ">=", "less than or equal to": "<=",
    "greater than": ">", "more than": ">", "above": ">", "over": ">",
    "higher than": ">", "exceeds": ">",
    "less than": "<", "below": "<", "under": "<", "lower than": "<",
    "at least": ">=", "at most": "<=", "not equal to": "!=",
    # temporal: later and earlier read as greater and less on a date
    "after": ">", "since": ">=", "later than": ">",
    "before": "<", "earlier than": "<", "until": "<=", "till": "<=",
    "equal to": "=", "equals": "=", "is": "=", "between": "BETWEEN",
}

LOGICAL = {"and": "AND", "or": "OR", "not": "NOT"}

ORDERS = {
    "ascending": "ASC", "asc": "ASC", "increasing": "ASC",
    "descending": "DESC", "desc": "DESC", "decreasing": "DESC",
    "highest first": "DESC", "lowest first": "ASC",
}

LIMITS = {"top", "first", "limit", "bottom"}

DISTINCT = {"distinct", "unique", "different"}

# A superlative names the column to rank by and the direction, e.g. "youngest"
# means the smallest age. It carries an ordering, not an aggregate.
SUPERLATIVES = {
    "youngest": ("age", "ASC"),
    "oldest": ("age", "DESC"),
    "eldest": ("age", "DESC"),
    "brightest": ("marks", "DESC"),
    "best": ("marks", "DESC"),
    "worst": ("marks", "ASC"),
    "top scoring": ("marks", "DESC"),
    "highest scoring": ("marks", "DESC"),
    "lowest scoring": ("marks", "ASC"),
}

# Resolved against the current year at compile time, so the generated SQL holds
# a concrete year rather than a floating reference to "now".
RELATIVE_YEARS = {
    "this year": 0, "current year": 0,
    "last year": -1, "previous year": -1,
    "next year": 1,
}

# verbs this compiler must never translate - a read-only query language
FORBIDDEN_VERBS = {
    "drop", "delete", "truncate", "alter", "insert", "update", "create",
    "grant", "revoke", "remove", "erase", "destroy",
}
GROUPS = {"each", "per", "every", "group by", "grouped by", "by"}

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twenty": 20, "fifty": 50,
    "hundred": 100,
}

_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z_0-9]*|\d+(?:\.\d+)?|'[^']*'|\"[^\"]*\"|[^\sA-Za-z0-9]")


class LexError(Exception):
    pass


class Lexer:
    def __init__(self, schema):
        self.schema = schema

    def tokenize(self, text):
        raw = self._scan_raw(text)
        return self._classify(raw)

    # --- stage 1: split into raw lexemes with positions ------------------
    def _scan_raw(self, text):
        return [(m.group(0), m.start()) for m in _WORD_RE.finditer(text)]

    # --- stage 2: maximal-munch classification --------------------------
    def _classify(self, raw):
        tokens = []
        i = 0
        n = len(raw)
        while i < n:
            lexeme, pos = raw[i]
            low = lexeme.lower()

            # quoted string literal
            if lexeme[0] in "'\"":
                tokens.append(Token(TokenType.STRING, lexeme, lexeme[1:-1], pos))
                i += 1
                continue

            # numeric literal
            if re.fullmatch(r"\d+(\.\d+)?", lexeme):
                val = float(lexeme) if "." in lexeme else int(lexeme)
                tokens.append(Token(TokenType.NUMBER, lexeme, val, pos))
                i += 1
                continue

            # multi-word phrase lookahead (up to 4 words)
            matched = self._match_phrase(raw, i)
            if matched:
                tok, consumed = matched
                tokens.append(tok)
                i += consumed
                continue

            # punctuation
            if not low.isalnum() and not low.startswith("_"):
                tokens.append(Token(TokenType.PUNCT, lexeme, low, pos))
                i += 1
                continue

            tokens.append(self._classify_word(lexeme, pos))
            i += 1

        tokens.append(Token(TokenType.EOF, "", None, raw[-1][1] + 1 if raw else 0))
        return tokens

    def _match_phrase(self, raw, i):
        """Try the longest multi-word phrase starting at i. Returns (Token, n)."""
        for size in (4, 3, 2):
            if i + size > len(raw):
                continue
            words = [w.lower() for w, _ in raw[i:i + size]]
            phrase = " ".join(words)
            pos = raw[i][1]
            lexeme = phrase
            if phrase in COMPARATORS:
                return Token(TokenType.COMPARATOR, lexeme, COMPARATORS[phrase], pos), size
            if phrase in AGGREGATES:
                return Token(TokenType.AGGREGATE, lexeme, AGGREGATES[phrase], pos), size
            if phrase in ORDERS:
                return Token(TokenType.ORDER, lexeme, ORDERS[phrase], pos), size
            if phrase in RELATIVE_YEARS:
                year = datetime.date.today().year + RELATIVE_YEARS[phrase]
                return Token(TokenType.NUMBER, lexeme, year, pos), size
            if phrase in SUPERLATIVES:
                return Token(TokenType.SUPERLATIVE, lexeme, SUPERLATIVES[phrase], pos), size
            if phrase in GROUPS:
                return Token(TokenType.GROUP, lexeme, "GROUP", pos), size
            if phrase in ("sorted by", "ordered by", "order by", "sort by"):
                return Token(TokenType.ORDER, lexeme, "ORDER_BY", pos), size
            col = self.schema.resolve_column(phrase)
            if col:
                return Token(TokenType.COLUMN, lexeme, col, pos), size
            tbl = self.schema.resolve_table(phrase)
            if tbl:
                return Token(TokenType.TABLE, lexeme, tbl, pos), size
            val = self.schema.resolve_value(phrase)
            if val:
                return Token(TokenType.VALUE, lexeme, val, pos), size
        return None

    def _classify_word(self, lexeme, pos):
        low = lexeme.lower()
        if low in FORBIDDEN_VERBS:
            return Token(TokenType.FORBIDDEN, lexeme, low, pos)
        if low in AGGREGATES:
            return Token(TokenType.AGGREGATE, lexeme, AGGREGATES[low], pos)
        if low in COMPARATORS:
            return Token(TokenType.COMPARATOR, lexeme, COMPARATORS[low], pos)
        if low in LOGICAL:
            return Token(TokenType.LOGICAL, lexeme, LOGICAL[low], pos)
        if low in ORDERS:
            return Token(TokenType.ORDER, lexeme, ORDERS[low], pos)
        if low in LIMITS:
            return Token(TokenType.LIMIT, lexeme, low, pos)
        if low in DISTINCT:
            return Token(TokenType.DISTINCT, lexeme, "DISTINCT", pos)
        if low in SUPERLATIVES:
            return Token(TokenType.SUPERLATIVE, lexeme, SUPERLATIVES[low], pos)
        if low in GROUPS:
            return Token(TokenType.GROUP, lexeme, "GROUP", pos)
        if low in NUMBER_WORDS:
            return Token(TokenType.NUMBER, lexeme, NUMBER_WORDS[low], pos)

        tbl = self.schema.resolve_table(low)
        if tbl:
            return Token(TokenType.TABLE, lexeme, tbl, pos)
        col = self.schema.resolve_column(low)
        if col:
            return Token(TokenType.COLUMN, lexeme, col, pos)

        if low in KEYWORDS:
            return Token(TokenType.KEYWORD, lexeme, low, pos)

        val = self.schema.resolve_value(low)
        if val:
            return Token(TokenType.VALUE, lexeme, val, pos)
        return Token(TokenType.IDENT, lexeme, lexeme, pos)
