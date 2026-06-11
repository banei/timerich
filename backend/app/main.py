from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.guardian import guardian
from app.routers import auth, config, dashboard, execution_v2, holdings
from app.scheduler import create_scheduler

settings = get_settings()
scheduler = create_scheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.scheduler_enabled:
        scheduler.start()
    await guardian.start()
    yield
    await guardian.stop()
    if scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(title="TimeRich API", version="0.1.0", lifespan=lifespan)

origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(auth.users_router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(holdings.router, prefix="/api/v1")
app.include_router(holdings.execution_router, prefix="/api/v1")
app.include_router(execution_v2.router, prefix="/api/v1")
app.include_router(config.router, prefix="/api/v1")
app.include_router(config.data_router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok", "service": "timerich"}
