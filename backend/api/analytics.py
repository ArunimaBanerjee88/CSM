"""Analytics API Module for Quantum City.

Exposes REST endpoints for scenario comparison and traffic metrics calculation.
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from multiverse.comparison_engine import ComparisonEngine, ComparisonResult
from simulation.metrics import TrafficMetricsCalculator, TrafficMetricsResult
from simulation.traffic import TrafficSimulationResult

# Import the global scenario manager to resolve world IDs
from api.worlds import _scenario_manager

router = APIRouter(
    prefix="/analytics",
    tags=["Analytics"],
)


class CompareWorldsRequest(BaseModel):
    """Payload for comparing multiple worlds."""
    model_config = ConfigDict(extra="ignore")
    
    base_world_id: str
    target_world_ids: List[str]


class TrafficMetricsRequest(BaseModel):
    """Payload for calculating traffic metrics from a simulation result."""
    model_config = ConfigDict(extra="ignore")
    
    simulation_result: TrafficSimulationResult
    speed_limit: Optional[float] = 13.9


@router.post("/compare-worlds", response_model=ComparisonResult)
def compare_worlds(request: CompareWorldsRequest) -> ComparisonResult:
    """Compare a base world against one or more target worlds."""
    try:
        base_world = _scenario_manager.get_world(request.base_world_id)
        target_worlds = [_scenario_manager.get_world(wid) for wid in request.target_world_ids]
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
        
    engine = ComparisonEngine(_scenario_manager)
    
    world_ids = [request.base_world_id] + request.target_world_ids
    return engine.compare_worlds(
        world_ids=world_ids,
        baseline_world_id=request.base_world_id
    )


@router.post("/traffic-metrics", response_model=TrafficMetricsResult)
def calculate_traffic_metrics(request: TrafficMetricsRequest) -> TrafficMetricsResult:
    """Calculate KPI metrics from a completed simulation run result."""
    calculator = TrafficMetricsCalculator()
    return calculator.calculate_metrics(
        simulation_result=request.simulation_result,
        speed_limit=request.speed_limit,
    )
