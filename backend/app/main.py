from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.bootstrap import seed_initial_data
from app.core.config import settings
from app.core.csrf import CSRFMiddleware
from app.core.https_enforcement import HTTPSRedirectMiddleware
from app.core.logging_setup import configure_logging
from app.core.rate_limit import ApiRateLimitMiddleware, limiter
from app.core.security_headers import SecurityHeadersMiddleware
from app.db.schema_compat import ensure_schema_compatibility
from app.db.session import engine, SessionLocal
from app.models import Base
from app.services.cyber_scoring_service import CyberScoringService
from app.services.data_loader_service import DataLoaderService
import logging

logger = logging.getLogger(__name__)

configure_logging()

# The application finishes its own bootstrapping here so a local developer can
# start the API without running a separate migration step first.
Base.metadata.create_all(bind=engine)
ensure_schema_compatibility(engine)

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="ChargeSafe SL Backend API - EV Charging Station Monitoring System"
)

app.state.limiter = limiter
app.add_middleware(CSRFMiddleware)
app.add_middleware(HTTPSRedirectMiddleware)
app.add_middleware(ApiRateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.backend_cors_origins,
    allow_credentials=True,
    allow_methods=settings.backend_cors_methods,
    allow_headers=settings.backend_cors_headers,
)

app.include_router(router, prefix="/api")


@app.on_event("startup")
def startup_sync_openchargemap():
    # Startup keeps the demo experience warm by seeding known records, pulling the
    # latest station feed, and recalculating cyber scores before requests arrive.
    """Auto-sync charging stations from OpenChargeMap on app startup."""
    db = None
    try:
        db = SessionLocal()
        logger.info("Seeding built-in demo stations...")
        seed_initial_data(db)
        logger.info("Starting auto-sync of OpenChargeMap stations...")
        stats = DataLoaderService.sync_openchargemap_to_database(db, force_update=True)
        logger.info(f"Auto-sync complete: {stats}")
        cyber_stats = CyberScoringService.score_all_stations(db)
        logger.info(f"Cyber scoring complete: {cyber_stats}")
    except Exception as e:
        logger.error(f"Error during auto-sync: {e}")
    finally:
        if db is not None:
            db.close()


@app.get("/")
def root():
    # This lightweight route gives containers and humans a quick way to confirm
    # the service name, version, and health without hitting protected APIs.
    """Root endpoint."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running"
    }
