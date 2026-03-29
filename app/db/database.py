from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from app.config import DATABASE_URL

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def ensure_database_configured() -> None:
    """Fail fast with a clear message if Postgres is not configured."""
    if not DATABASE_URL or not (
        DATABASE_URL.startswith("postgresql://")
        or DATABASE_URL.startswith("postgres://")
    ):
        raise RuntimeError(
            "DATABASE_URL is missing or not a PostgreSQL URI. "
            "Set DATABASE_URL in your environment (see .env.example for Supabase)."
        )


_MIGRATIONS_DIR = _REPO_ROOT / "supabase" / "migrations"


def _migration_files() -> list[Path]:
    if not _MIGRATIONS_DIR.is_dir():
        return []
    return sorted(_MIGRATIONS_DIR.glob("*.sql"))


def _split_sql_statements(sql: str) -> list[str]:
    out: list[str] = []
    buf: list[str] = []
    for line in sql.splitlines():
        s = line.strip()
        if s.startswith("--"):
            continue
        buf.append(line)
        if s.endswith(";"):
            stmt = "\n".join(buf).strip()
            if stmt:
                out.append(stmt.rstrip(";").strip() + ";")
            buf = []
    tail = "\n".join(buf).strip()
    if tail:
        out.append(tail if tail.endswith(";") else tail + ";")
    return out


def get_connection() -> psycopg.Connection:
    ensure_database_configured()
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def init_db() -> None:
    ensure_database_configured()
    paths = _migration_files()
    if not paths:
        raise FileNotFoundError(f"No SQL migrations in {_MIGRATIONS_DIR}")
    conn = get_connection()
    try:
        for path in paths:
            sql_text = path.read_text(encoding="utf-8")
            for stmt in _split_sql_statements(sql_text):
                conn.execute(stmt)
        conn.execute(
            """INSERT INTO phase (id, current_phase)
               VALUES (1, 'pre_storm')
               ON CONFLICT (id) DO NOTHING"""
        )
        conn.commit()
    finally:
        conn.close()
