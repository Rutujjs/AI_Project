import asyncio
from contextlib import asynccontextmanager
import logging
import os
import sys

# Ensure Hugging Face and Transformers operate strictly offline in sandbox/local environments
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from app.routers import documents
from app.green.router import router as green_router
from app.cloud_carbon.router import router as cloud_carbon_router
from app.platform.routers.auth_router import router as auth_router
from app.platform.routers.platform_router import router as platform_router
from app.platform.routers.supplier_router import router as supplier_router
from app.platform.routers.dashboard_router import router as dashboard_router
from app.platform.routers.report_router import router as report_router
from app.platform.routers.audit_router import router as audit_router
from app.platform.routers.notification_router import router as notification_router
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger("platform.scheduler")


async def _daily_expiry_scheduler(stop_event: asyncio.Event):
    """Background scheduler task to sweep document expiries daily."""
    # Prevent concurrent sweeps during automated pytest execution
    if os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules:
        return

    try:
        await asyncio.sleep(2)
        if not stop_event.is_set():
            from app.platform.database import SessionLocal
            from app.platform.services.notification_service import run_document_expiry_sweep
            db = SessionLocal()
            try:
                await asyncio.to_thread(run_document_expiry_sweep, db)
            except Exception as e:
                logger.warning(f"Initial document expiry sweep failed: {e}")
            finally:
                db.close()
    except asyncio.CancelledError:
        return
    except Exception as e:
        logger.warning(f"Background scheduler startup exception: {e}")

    while not stop_event.is_set():
        try:
            for _ in range(86400 // 30):
                if stop_event.is_set():
                    return
                await asyncio.sleep(30)

            from app.platform.database import SessionLocal
            from app.platform.services.notification_service import run_document_expiry_sweep
            db = SessionLocal()
            try:
                await asyncio.to_thread(run_document_expiry_sweep, db)
            except Exception as e:
                logger.warning(f"Periodic document expiry sweep failed: {e}")
            finally:
                db.close()
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.warning(f"Background scheduler periodic error: {e}")
            await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    stop_event = asyncio.Event()
    task = asyncio.create_task(_daily_expiry_scheduler(stop_event))
    try:
        yield
    finally:
        stop_event.set()
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


app = FastAPI(
    title="AI ESG Sustainability Platform",
    description="Document Intelligence, Green Software, Cloud Carbon & Enterprise Platform for ESG Analysis",
    version="1.3.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:5501",
        "http://127.0.0.1:5501",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:8081",
        "http://127.0.0.1:8081",
        "null",  # file:// origin
    ],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.include_router(documents.router)
app.include_router(green_router)
app.include_router(cloud_carbon_router)
app.include_router(auth_router)
app.include_router(platform_router)
app.include_router(supplier_router)
app.include_router(dashboard_router)
app.include_router(report_router)
app.include_router(audit_router)
app.include_router(notification_router)

@app.get("/")
def home():
    return {"message": "AI ESG Document Intelligence API is running!"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}
