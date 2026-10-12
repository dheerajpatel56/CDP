"""Which database the compiler targets, and what that implies.

The compiler emits standard SQL, so switching engines is a configuration change
rather than a compiler change. Two things differ per engine and both are
resolved here: the parameter placeholder style, and how a date part is
extracted. Everything else in the generated statement is identical.

Set DATABASE_URL to use PostgreSQL:

    postgresql://user:password@localhost:5432/nlqc

Leave it unset and the demo runs on SQLite with no external service.
"""
import os
from dataclasses import dataclass
from pathlib import Path

SQLITE = "sqlite"
POSTGRES = "postgres"


@dataclass(frozen=True)
class Backend:
    name: str
    placeholder: str      # how a bound parameter is written in the statement
    url: str | None       # connection string, None for the bundled SQLite file

    @property
    def is_postgres(self) -> bool:
        return self.name == POSTGRES


def load_env_file(path: str | Path | None = None) -> None:
    """Read KEY=VALUE lines from a local .env, without overriding the real
    environment. Keeps the connection string, and the password in it, out of
    the source tree and out of version control.
    """
    path = Path(path or Path(__file__).resolve().parent.parent / ".env")
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def resolve(url: str | None = None) -> Backend:
    if url is None:
        load_env_file()
    url = url if url is not None else os.environ.get("DATABASE_URL", "").strip()
    if url and url.startswith(("postgres://", "postgresql://")):
        return Backend(POSTGRES, "%s", url)
    if url and url.startswith("sqlite://"):
        return Backend(SQLITE, "?", None)
    if url:
        raise ValueError(
            "unsupported DATABASE_URL %r: expected a postgresql:// or sqlite:// url" % url
        )
    return Backend(SQLITE, "?", None)


# Resolved once at import. Tests and tooling can call resolve() for a different one.
ACTIVE = resolve()
