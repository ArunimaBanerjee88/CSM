"""Quantum Solver Module for Quantum City.

High-level interface that accepts a CityResourceProblem, formulates the QUBO
using QUBOBuilder, solves it with QAOASolver, and returns a single unified
JSON-serializable result.
"""

from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

from quantum.qaoa import QAOASolution, QAOASolver
from quantum.qubo import CityResourceProblem, QUBOBuilder, QUBOResult


class QuantumSolverResult(BaseModel):
    """Unified JSON-serializable result from the quantum optimization pipeline."""
    model_config = ConfigDict(extra="ignore")

    predicted_energy_demand_mw: float = Field(description="Input energy demand in MW")
    active_vehicle_count: int = Field(description="Input active vehicle count")
    traffic_congestion_index: float = Field(description="Input traffic congestion index")
    num_zones: int = Field(description="Number of binary decision variables (city zones)")
    max_allocations: int = Field(description="Maximum simultaneous zone allocations")
    energy_cost_weight: float = Field(description="Normalized energy cost weight from QUBO")
    congestion_cost_weight: float = Field(description="Normalized congestion cost weight from QUBO")
    qubo_offset: float = Field(description="Constant offset from QUBO budget penalty expansion")
    solver: str = Field(description="Solver used: 'qaoa' or 'brute_force'")
    selected_allocation: List[int] = Field(description="Optimal binary zone allocation vector")
    total_zones_allocated: int = Field(description="Number of zones selected in the solution")
    objective_value: float = Field(description="QUBO objective value for the selected allocation")
    qaoa_reps: int = Field(description="Number of QAOA layers (p)")
    optimal_parameters: List[float] = Field(description="Optimized QAOA variational angles")
    fallback_reason: Optional[str] = Field(default=None, description="Reason for brute-force fallback if used")


class QuantumSolver:
    """High-level quantum optimization interface for Quantum City resource allocation."""

    def __init__(
        self,
        qaoa_reps: int = 1,
        num_shots: int = 1024,
        seed: int = 42,
        optimizer_maxiter: int = 200,
    ) -> None:
        """Initialize QuantumSolver with QAOA configuration.

        Args:
            qaoa_reps: Number of QAOA layers (p).
            num_shots: Measurement shots per circuit evaluation.
            seed: Deterministic seed for reproducible results.
            optimizer_maxiter: Maximum classical optimizer iterations.
        """
        self._qaoa = QAOASolver(
            reps=qaoa_reps,
            num_shots=num_shots,
            seed=seed,
            optimizer_maxiter=optimizer_maxiter,
        )

    def solve(self, problem: CityResourceProblem) -> QuantumSolverResult:
        """Run the full quantum optimization pipeline on a city resource problem.

        Args:
            problem: CityResourceProblem specifying city inputs and QUBO parameters.

        Returns:
            QuantumSolverResult containing problem inputs, QUBO summary, allocation,
            objective value, and QAOA solver metadata in a single JSON-serializable object.
        """
        qubo_result: QUBOResult = QUBOBuilder.build(problem)
        solution: QAOASolution = self._qaoa.solve(qubo_result)

        return QuantumSolverResult(
            predicted_energy_demand_mw=problem.predicted_energy_demand_mw,
            active_vehicle_count=problem.active_vehicle_count,
            traffic_congestion_index=problem.traffic_congestion_index,
            num_zones=qubo_result.num_variables,
            max_allocations=qubo_result.max_allocations,
            energy_cost_weight=qubo_result.energy_cost_weight,
            congestion_cost_weight=qubo_result.congestion_cost_weight,
            qubo_offset=qubo_result.offset,
            solver=solution.solver,
            selected_allocation=solution.selected_allocation,
            total_zones_allocated=sum(solution.selected_allocation),
            objective_value=solution.objective_value,
            qaoa_reps=solution.qaoa_reps,
            optimal_parameters=solution.optimal_parameters,
            fallback_reason=solution.fallback_reason,
        )
