"""One-shot PostgreSQL setup and verification.

    1. copy .env.example to .env and put your password in it
    2. python setup_postgres.py

Creates the database if it is missing, builds the schema, loads the demo data,
then compiles and runs the full query battery against PostgreSQL so the switch
is proven rather than assumed. Reads the connection string from the environment
or .env; no credential is ever written into the source tree.
"""
import sys
from urllib.parse import urlparse, urlunparse

from db.config import resolve
from db.seed import build_postgres


def ensure_database(url):
    """Create the target database if it does not exist yet."""
    import psycopg

    parsed = urlparse(url)
    target = parsed.path.lstrip("/")
    if not target:
        raise SystemExit("DATABASE_URL has no database name, expected .../nlqc")

    admin_url = urlunparse(parsed._replace(path="/postgres"))
    with psycopg.connect(admin_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target,))
            if cur.fetchone():
                print(f"database {target!r} already exists")
                return target
            # identifiers cannot be bound as parameters; the name comes from the
            # operator's own connection string, not from user input
            cur.execute('CREATE DATABASE "%s"' % target.replace('"', '""'))
            print(f"created database {target!r}")
    return target


def verify(backend):
    """Compile and execute the test battery against this backend."""
    from compiler.pipeline import QueryCompiler
    from db.executor import ExecutionError, execute
    from tests.test_compiler import CASES

    compiler = QueryCompiler(dialect=backend.name)
    passed = failed = 0

    for question, should_compile, _ in CASES:
        result = compiler.compile(question)
        if result.ok != should_compile:
            print(f"FAIL  {question!r}: unexpected {'success' if result.ok else 'refusal'}")
            failed += 1
            continue
        if not result.ok:
            passed += 1
            continue
        try:
            execute(result.sql, result.params, backend)
            passed += 1
        except ExecutionError as e:
            print(f"FAIL  {question!r}\n        {e}")
            print(f"        {' '.join(result.sql.split())}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed, {len(CASES)} total")
    return failed


def main():
    backend = resolve()
    if not backend.is_postgres:
        print("DATABASE_URL is not set to a postgresql:// url.")
        print("Copy .env.example to .env, set your password, then run this again.")
        return 1

    safe = urlparse(backend.url)
    print(f"target: {safe.hostname}:{safe.port or 5432}{safe.path}")

    try:
        ensure_database(backend.url)
    except Exception as e:
        print(f"\ncould not reach PostgreSQL: {e}")
        print("Check the host, port, user and password in .env.")
        return 1

    print("\nloading demo data")
    for table, n in build_postgres(backend.url).items():
        print(f"  {table:<12} {n:>4} rows")

    print("\nverifying the compiler against PostgreSQL")
    return 1 if verify(backend) else 0


if __name__ == "__main__":
    sys.exit(main())
