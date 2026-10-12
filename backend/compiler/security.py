"""Phase 7 - Static analysis / query security.

Runs over generated SQL before execution. Because codegen emits only SELECT
statements with bound parameters, this pass is a verification gate rather than
a sanitiser: it proves the generated statement stays inside the safe subset,
and refuses to execute anything that does not.
"""
import re

# statements this compiler is never allowed to emit
FORBIDDEN = [
    "DROP", "DELETE", "TRUNCATE", "ALTER", "INSERT", "UPDATE", "CREATE",
    "GRANT", "REVOKE", "ATTACH", "DETACH", "PRAGMA", "EXEC", "EXECUTE",
    "VACUUM", "REPLACE",
]

# shapes that signal an injection attempt survived into the statement text
INJECTION_PATTERNS = [
    (r"--", "SQL line comment in generated statement"),
    (r"/\*", "SQL block comment in generated statement"),
    (r";\s*\w", "multiple statements separated by a semicolon"),
    (r"\bOR\s+1\s*=\s*1\b", "tautology predicate (OR 1=1)"),
    (r"\bUNION\s+(ALL\s+)?SELECT\b", "UNION injection"),
    (r"\bxp_\w+", "extended stored procedure call"),
    (r"\bsqlite_master\b", "access to database metadata tables"),
    (r"\binformation_schema\b", "access to database metadata tables"),
]

MAX_ROWS = 1000           # hard cap enforced on every execution
MAX_JOINS = 5             # refuse plans with runaway join counts


class SecurityError(Exception):
    pass


class SecurityAnalyzer:
    def __init__(self, schema, allowed_tables=None, max_rows=MAX_ROWS):
        self.schema = schema
        self.allowed_tables = set(allowed_tables or schema.tables.keys())
        self.max_rows = max_rows

    def analyze(self, sql, params, query):
        findings = []
        body = sql.rstrip().rstrip(";")
        upper = body.upper()

        # 1. statement type - SELECT / WITH only
        if not re.match(r"^\s*(SELECT|WITH)\b", upper):
            findings.append(self._fail("statement is not a read-only SELECT"))

        # 2. no DDL/DML verbs anywhere
        for word in FORBIDDEN:
            if re.search(r"\b%s\b" % word, upper):
                findings.append(self._fail("forbidden keyword '%s' in generated SQL" % word))

        # 3. injection shapes
        for pattern, label in INJECTION_PATTERNS:
            if re.search(pattern, body, re.IGNORECASE):
                findings.append(self._fail(label))

        # 4. every literal is a bound parameter
        inline = re.findall(r"=\s*'[^']*'", body)
        if inline:
            findings.append(self._fail("literal value inlined instead of parameterised: %s"
                                       % inline[0]))
        findings.append(self._ok("all %d literal(s) passed as bound parameters"
                                 % len(params)))

        # 5. table authorisation
        used = set(re.findall(r"(?:FROM|JOIN)\s+([a-z_][a-z_0-9]*)", body, re.IGNORECASE))
        used -= {"ranked"}
        unauthorised = used - self.allowed_tables
        if unauthorised:
            findings.append(self._fail("access to unauthorised table(s): %s"
                                       % ", ".join(sorted(unauthorised))))
        else:
            findings.append(self._ok("all referenced tables are authorised"))

        # 6. resource bounds
        join_count = len(re.findall(r"\bJOIN\b", upper))
        if join_count > MAX_JOINS:
            findings.append(self._fail("query plan has %d joins (limit %d)"
                                       % (join_count, MAX_JOINS)))
        if query.limit is None:
            findings.append(self._warn("no row limit in the query - capping at %d rows"
                                       % self.max_rows))
        elif query.limit > self.max_rows:
            findings.append(self._fail("requested %d rows exceeds the %d row cap"
                                       % (query.limit, self.max_rows)))

        safe = not any(f["severity"] == "error" for f in findings)
        return {
            "safe": safe,
            "findings": findings,
            "tables_accessed": sorted(used),
            "parameter_count": len(params),
            "join_count": join_count,
            "row_cap": self.max_rows,
        }

    @staticmethod
    def _fail(msg):
        return {"severity": "error", "message": msg}

    @staticmethod
    def _warn(msg):
        return {"severity": "warning", "message": msg}

    @staticmethod
    def _ok(msg):
        return {"severity": "pass", "message": msg}
