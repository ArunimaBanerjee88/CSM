"""Simulation API Module for Quantum City.

Exposes REST endpoints to run SUMO traffic simulations and calculate key
performance indicator (KPI) metrics.
"""

from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from simulation.traffic import TrafficSimulator, TrafficSimulationResult
from simulation.metrics import TrafficMetricsCalculator, TrafficMetricsResult

router = APIRouter(
    prefix="/simulation",
    tags=["Simulation"],
)


class SimulationRunRequest(BaseModel):
    """Payload for triggering a SUMO simulation."""
    model_config = ConfigDict(extra="ignore")
    
    steps: int = 100
    step_length: float = 1.0
    gui: bool = False
    sumo_config_path: Optional[str] = None


class MetricsRequest(BaseModel):
    """Payload for calculating traffic metrics from a simulation result."""
    model_config = ConfigDict(extra="ignore")
    
    simulation_result: TrafficSimulationResult
    speed_limit: Optional[float] = 13.9


@router.post("/run", response_model=TrafficSimulationResult)
def run_simulation(request: SimulationRunRequest) -> TrafficSimulationResult:
    """Run a deterministic SUMO traffic simulation and return raw observations."""
    simulator = TrafficSimulator()
    return simulator.run_simulation(
        steps=request.steps,
        step_length=request.step_length,
        gui=request.gui,
        sumo_config_path=request.sumo_config_path,
    )


@router.post("/metrics", response_model=TrafficMetricsResult)
def calculate_metrics(request: MetricsRequest) -> TrafficMetricsResult:
    """Calculate KPI metrics from a completed simulation run result."""
    calculator = TrafficMetricsCalculator()
    return calculator.calculate_metrics(
        simulation_result=request.simulation_result,
        speed_limit=request.speed_limit,
    )
