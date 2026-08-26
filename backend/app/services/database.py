"""
Database connection pool and async session provider.

Observability additions:
  - Connection pool events: connect, checkout, checkin, invalidate.
  - Session transaction logging (commit / rollback) with error diagnostics.
  - check_db_health() utility for diagnostic endpoints.
"""
import time
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.config import settings
from app.observability.logger import get_logger, Timer

logger = get_logger("lenny.db")

engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    pool_recycle=1800,
    echo=False,
)

# Attach connection pool event listeners for observability
@event.listens_for(engine.sync_engine, "connect")
def _on_connect(dbapi_connection, connection_record):
    logger.debug("db_connection_created", extra={"event": "db_pool_connect"})

@event.listens_for(engine.sync_engine, "checkout")
def _on_checkout(dbapi_connection, connection_record, connection_proxy):
    logger.debug("db_connection_checkout", extra={"event": "db_pool_checkout"})

@event.listens_for(engine.sync_engine, "checkin")
def _on_checkin(dbapi_connection, connection_record):
    logger.debug("db_connection_checkin", extra={"event": "db_pool_checkin"})

@event.listens_for(engine.sync_engine, "invalidate")
def _on_invalidate(dbapi_connection, connection_record, exception):
    logger.warning(
        f"db_connection_invalidated: {exception}",
        extra={"event": "db_pool_invalidate", "error": str(exception)},
    )

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async def get_db():
    async with SessionLocal() as session:
        t0 = time.perf_counter()
        try:
            yield session
            await session.commit()
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            logger.error(
                f"db_transaction_rollback error={e}",
                extra={"event": "db_transaction_rollback", "error": str(e), "duration_ms": elapsed_ms},
                exc_info=True,
            )
            await session.rollback()
            raise


async def check_db_health() -> dict:
    """Run a diagnostic probe against Postgres, measuring latency and vector table stats."""
    with Timer() as t:
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
                docs_count = (await conn.execute(text("SELECT COUNT(*) FROM documents"))).scalar() or 0
                chunks_count = (await conn.execute(text("SELECT COUNT(*) FROM chunks"))).scalar() or 0
                sessions_count = (await conn.execute(text("SELECT COUNT(*) FROM sessions"))).scalar() or 0
            return {
                "ok": True,
                "latency_ms": t.elapsed_ms,
                "documents_count": docs_count,
                "chunks_count": chunks_count,
                "sessions_count": sessions_count,
            }
        except Exception as e:
            logger.error(
                f"db_health_check_failed: {e}",
                extra={"event": "db_health_error", "error": str(e), "duration_ms": t.elapsed_ms},
            )
            return {
                "ok": False,
                "latency_ms": t.elapsed_ms,
                "error": str(e),
            }
