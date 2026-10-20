import os
from contextlib import asynccontextmanager
from pathlib import Path
from psycopg_pool import AsyncConnectionPool

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
_pool: AsyncConnectionPool | None = None


def configured_database_url() -> str:
    """The database URL from the environment, or "" when none is set."""
    return (
        os.getenv("STUDIOSHARE_DB_URL", "").strip()
        or os.getenv("DATABASE_URL", "").strip()
    )


def database_url() -> str:
    value = configured_database_url()

    if not value:
        raise RuntimeError(
            "Database configuration is missing. "
            "Attach a StudioShare database or set DATABASE_URL."
        )

    return value


async def open_database() -> None:
    global _pool
    _pool = AsyncConnectionPool(database_url(), min_size=1, max_size=10, open=False)
    await _pool.open(wait=True, timeout=15)


async def close_database() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def pool() -> AsyncConnectionPool:
    if _pool is None:
        raise RuntimeError("Database pool is not initialized.")
    return _pool


@asynccontextmanager
async def connection():
    async with pool().connection() as conn:
        yield conn


async def migrate() -> None:
    async with connection() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(82417631)")
            await conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
            )
            rows = await (
                await conn.execute("SELECT name FROM schema_migrations")
            ).fetchall()
            applied = {row[0] for row in rows}
            for path in sorted(MIGRATIONS.glob("*.sql")):
                if path.name in applied:
                    continue
                await conn.execute(path.read_text(encoding="utf-8"))
                await conn.execute(
                    "INSERT INTO schema_migrations(name) VALUES (%s)", (path.name,)
                )


async def database_health() -> bool:
    try:
        async with connection() as conn:
            return (await (await conn.execute("SELECT 1")).fetchone())[0] == 1
    except Exception:
        return False
