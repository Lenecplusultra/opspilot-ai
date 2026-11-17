from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.models  # noqa: F401  (register tables)
from app.api.routes import router
from app.core.config import settings
from app.db.seed import seed
from app.db.session import Base, SessionLocal, engine


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.environment in ("development", "demo"):
        Base.metadata.create_all(engine)
        with SessionLocal() as db:
            seed(db, settings.demo_scenario, password=settings.seed_password)
    yield


app = FastAPI(title="OpsPilot AI", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix="/api")
