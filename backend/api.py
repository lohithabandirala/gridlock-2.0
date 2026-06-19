from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel, Field

from src.command_center.db import init_db
from src.command_center.ml import train
from src.command_center.service import EventRequest, predict_event


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Smart City Command Center API", version="1.0.0", lifespan=lifespan)


class PredictRequest(BaseModel):
    event_type: str = Field(..., examples=["Cricket Match"])
    event_location: str = Field(..., examples=["M. Chinnaswamy Stadium"])
    crowd_size: int = Field(..., ge=0, examples=[50000])
    event_start_time: str = Field(..., examples=["2026-06-19T17:00:00"])
    event_duration_hr: float = Field(..., ge=0.5, le=24, examples=[4])
    weather_condition: str = Field(..., examples=["Clear"])


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/train")
def train_model():
    return train()


@app.post("/predict")
def predict(req: PredictRequest):
    return predict_event(EventRequest(**req.model_dump()))

