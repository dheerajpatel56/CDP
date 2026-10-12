"""Terminal front-end for the compiler.

    python cli.py "show the top 5 students from each department who scored above 85"
    python cli.py --stages "average marks in each department"
    python cli.py            # interactive REPL
"""
import argparse
import sys

from compiler.pipeline import QueryCompiler
from db.executor import ExecutionError, execute

BAR = "=" * 72


def show(text, compiler, stages=False, run=True):
    result = compiler.compile(text)

    print(BAR)
    print("INPUT  %s" % text)
    print(BAR)

    if not result.ok:
        print("\n  COMPILATION FAILED in %s\n" % result.failed_phase)
        for e in result.errors:
            print("    error: %s" % e["message"])
        return 1

    if stages:
        toks = result.stages["lexical_analysis"]["tokens"]
        print("\n[1] LEXICAL ANALYSIS  (%d tokens)" % (len(toks) - 1))
        for t in toks[:-1]:
            print("    %-11s %-18s %s" % (t["type"], t["lexeme"], t["value"]))

        print("\n[2] SYNTAX ANALYSIS")
        _print_tree(result.stages["syntax_analysis"]["ast_tree"])

        sem = result.stages["semantic_analysis"]
        print("\n[3] SEMANTIC ANALYSIS")
        print("    tables: %s" % ", ".join(sem["tables"]))
        for j in sem["join_plan"]:
            print("    join:   %s" % j["on"])
        for w in sem["warnings"]:
            print("    note:   %s" % w["message"])

        print("\n[4] INTERMEDIATE REPRESENTATION")
        for line in result.stages["intermediate_representation"]["listing"].split("\n"):
            print("    %s" % line)

        opt = result.stages["optimization"]
        print("\n[5] OPTIMIZATION  (%d ops -> %d ops)"
              % (opt["ops_before"], opt["ops_after"]))
        for t in opt["transformations"]:
            print("    * %-22s %s" % (t["rule"], t["detail"]))
        print()
        for line in opt["listing"].split("\n"):
            print("    %s" % line)

        print("\n[6] CODE GENERATION")

    print("\nSQL")
    for line in result.sql.split("\n"):
        print("    %s" % line)
    print("    -- params: %s" % (result.params or "none"))

    if stages:
        sec = result.stages["security_analysis"]
        print("\n[7] SECURITY ANALYSIS  (%s)" % ("SAFE" if sec["safe"] else "BLOCKED"))
        for f in sec["findings"]:
            mark = {"pass": "ok  ", "warning": "warn", "error": "FAIL"}[f["severity"]]
            print("    [%s] %s" % (mark, f["message"]))

    if not run:
        return 0

    try:
        res = execute(result.sql, result.params)
    except ExecutionError as e:
        print("\nEXECUTION FAILED: %s" % e)
        return 1

    print("\nRESULTS  (%d rows in %.2f ms)" % (res["row_count"], res["duration_ms"]))
    if res["rows"]:
        cols = res["columns"]
        widths = [max(len(c), *(len(str(r[c])) for r in res["rows"][:20])) for c in cols]
        print("    " + "  ".join(c.ljust(w) for c, w in zip(cols, widths)))
        print("    " + "  ".join("-" * w for w in widths))
        for r in res["rows"][:20]:
            print("    " + "  ".join(str(r[c]).ljust(w) for c, w in zip(cols, widths)))
        if res["row_count"] > 20:
            print("    ... %d more rows" % (res["row_count"] - 20))
    print()
    return 0


def _print_tree(node, prefix="    ", last=True):
    print("%s%s%s" % (prefix, "`- " if last else "|- ", node["name"]))
    kids = node.get("children") or []
    for i, c in enumerate(kids):
        _print_tree(c, prefix + ("   " if last else "|  "), i == len(kids) - 1)


def main():
    ap = argparse.ArgumentParser(description="Natural Language Query Compiler")
    ap.add_argument("query", nargs="*", help="natural language question")
    ap.add_argument("--stages", action="store_true", help="show every compiler phase")
    ap.add_argument("--no-run", action="store_true", help="compile only, do not execute")
    args = ap.parse_args()

    compiler = QueryCompiler()

    if args.query:
        return show(" ".join(args.query), compiler, args.stages, not args.no_run)

    print("Natural Language Query Compiler - type a question, or 'quit'.")
    while True:
        try:
            text = input("\nnlq> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if text.lower() in ("quit", "exit", "q"):
            return 0
        if text:
            show(text, compiler, args.stages, not args.no_run)


if __name__ == "__main__":
    sys.exit(main())
