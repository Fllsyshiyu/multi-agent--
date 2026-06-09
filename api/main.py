from __future__ import annotations

from pathlib import Path
import sys
from fastapi import FastAPI
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ma_deliberation_demo import run_deliberation  # noqa: E402
from ma_deliberation_demo.schemas import to_dict  # noqa: E402

app = FastAPI(title="Multi-Agent Deliberation Hall Demo", version="0.1.0")


class DeliberationRequest(BaseModel):
    topic: str = "小区门口夜市是否应该保留？"


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/deliberate")
def deliberate(req: DeliberationRequest) -> dict:
    result = run_deliberation(req.topic, ROOT / "data" / "evidence_cards.csv")
    return to_dict(result)
