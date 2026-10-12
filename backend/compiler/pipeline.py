"""The compiler driver.

Chains every phase and records the output of each one, so a caller (the API,
the CLI, or the dashboard) can show the full translation rather than just the
final SQL. A phase that fails stops the pipeline and reports where it stopped.
"""
import time

from .codegen import SQLGenerator, inline_params
from .ir import lower
from .lexer import Lexer
from .optimizer import Optimizer
from .parser import ParseError, Parser
from .schema import DEMO_SCHEMA
from .security import SecurityAnalyzer
from .semantic import SemanticAnalyzer, SemanticError

PHASES = [
    "lexical_analysis", "syntax_analysis", "semantic_analysis",
    "intermediate_representation", "optimization", "code_generation",
    "security_analysis",
]


class CompilationResult:
    def __init__(self):
        self.stages = {}
        self.errors = []
        self.warnings = []
        self.sql = None
        self.params = []
        self.ok = False
        self.failed_phase = None

    def to_dict(self):
        return {
            "ok": self.ok,
            "failed_phase": self.failed_phase,
            "sql": self.sql,
            "params": self.params,
            "errors": self.errors,
            "warnings": self.warnings,
            "stages": self.stages,
        }


class QueryCompiler:
    def __init__(self, schema=None, dialect=None, catalog_conn=None):
        from db.config import ACTIVE
        self.schema = schema or DEMO_SCHEMA
        self.dialect = dialect or ACTIVE.name
        if catalog_conn is not None:
            self.schema.build_value_index(catalog_conn)
        elif not self.schema.value_index:
            self._build_catalog()

    def _build_catalog(self):
        """Statistics pass - lets the lexer resolve bare literals to columns."""
        try:
            from db.executor import _connect
            conn = _connect()
            try:
                self.schema.build_value_index(conn)
            finally:
                conn.close()
        except Exception:
            pass   # catalog is an optimisation; the compiler works without it

    def compile(self, text):
        result = CompilationResult()
        t_start = time.perf_counter()

        def stage(name, payload, started):
            payload["duration_ms"] = round((time.perf_counter() - started) * 1000, 3)
            result.stages[name] = payload

        # --- Phase 1: lexical analysis ----------------------------------
        t0 = time.perf_counter()
        try:
            tokens = Lexer(self.schema).tokenize(text)
        except Exception as e:
            return self._fail(result, "lexical_analysis", str(e))
        stage("lexical_analysis", {
            "input": text,
            "tokens": [t.to_dict() for t in tokens],
            "token_count": len(tokens) - 1,
        }, t0)

        # --- Phase 2: syntax analysis -----------------------------------
        t0 = time.perf_counter()
        parser = Parser(tokens, self.schema)
        try:
            ast = parser.parse()
        except ParseError as e:
            return self._fail(result, "syntax_analysis", str(e))
        result.warnings.extend(parser.diagnostics)
        stage("syntax_analysis", {
            "ast": ast.to_dict(),
            "ast_tree": ast.tree(),
            "diagnostics": parser.diagnostics,
        }, t0)

        # --- Phase 3: semantic analysis ---------------------------------
        t0 = time.perf_counter()
        analyzer = SemanticAnalyzer(self.schema)
        try:
            report, join_plan = analyzer.analyze(ast)
        except SemanticError as e:
            result.errors.extend(analyzer.errors)
            return self._fail(result, "semantic_analysis", str(e))
        result.warnings.extend(analyzer.warnings)
        stage("semantic_analysis", report, t0)

        # --- Phase 4: intermediate representation -----------------------
        t0 = time.perf_counter()
        ir = lower(ast, join_plan)
        stage("intermediate_representation", {
            "ops": ir.to_dict(),
            "listing": ir.text(),
            "op_count": len(ir.ops),
        }, t0)

        # --- Phase 5: optimization --------------------------------------
        t0 = time.perf_counter()
        opt = Optimizer(self.schema)
        optimized = opt.optimize(ir)
        stage("optimization", {
            "ops": optimized.to_dict(),
            "listing": optimized.text(),
            "transformations": opt.transformations,
            "ops_before": len(ir.ops),
            "ops_after": len(optimized.ops),
        }, t0)

        # --- Phase 6: code generation -----------------------------------
        t0 = time.perf_counter()
        gen = SQLGenerator(self.schema, self.dialect)
        try:
            sql, params = gen.generate(ast, join_plan)
        except Exception as e:
            return self._fail(result, "code_generation", str(e))
        result.sql, result.params = sql, params
        stage("code_generation", {
            "sql": sql,
            "params": params,
            "preview": inline_params(sql, params, gen.placeholder),
            "dialect": self.dialect,
        }, t0)

        # --- Phase 7: security analysis ---------------------------------
        t0 = time.perf_counter()
        sec = SecurityAnalyzer(self.schema).analyze(sql, params, ast)
        stage("security_analysis", sec, t0)
        if not sec["safe"]:
            result.errors.extend(f for f in sec["findings"] if f["severity"] == "error")
            return self._fail(result, "security_analysis", "generated SQL failed the safety gate")

        result.ok = True
        result.stages["total_duration_ms"] = round((time.perf_counter() - t_start) * 1000, 3)
        return result

    @staticmethod
    def _fail(result, phase, message):
        result.ok = False
        result.failed_phase = phase
        result.errors.append({"severity": "error", "phase": phase, "message": message})
        return result
