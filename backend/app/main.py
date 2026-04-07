from fastapi import FastAPI

from app.auth.router import router as auth_router

# Import all models so SQLAlchemy metadata is fully populated before create_all
import app.catalog.models  # noqa: F401
import app.collections.models  # noqa: F401
import app.scanning.models  # noqa: F401

app = FastAPI(title="LooseBricks API", version="0.1.0")
app.include_router(auth_router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
