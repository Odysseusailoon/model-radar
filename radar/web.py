"""Standalone inference dashboard/API; no Postgres or LLM dependency."""
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from app.inference_radar import configure_radar_job, router


@asynccontextmanager
async def lifespan(app):
    scheduler = BackgroundScheduler(timezone="UTC")
    configure_radar_job(scheduler)
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Inference Radar", lifespan=lifespan)
app.state.inference_only = True
app.include_router(router)


@app.get("/")
def home():
    return RedirectResponse("/inference")


@app.get("/health")
def health():
    return {"status": "ok"}
