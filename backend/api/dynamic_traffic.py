from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from simulation.dynamic_traffic import DynamicTrafficEngine


router = APIRouter(
    prefix="/dynamic-traffic",
    tags=["Dynamic Traffic"],
)


class DynamicTrafficRequest(BaseModel):
    total_steps: int = Field(default=300, ge=1, le=3600)
    decision_interval: int = Field(default=60, ge=1, le=600)
    seed: int = Field(default=42)


@router.post("/run")
def run_dynamic_traffic(request: DynamicTrafficRequest):
    try:
        engine = DynamicTrafficEngine(
            total_steps=request.total_steps,
            decision_interval=request.decision_interval,
            seed=request.seed,
        )

        result = engine.run()

        # DynamicTrafficEngine.run() already returns a dict.
        return result

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )