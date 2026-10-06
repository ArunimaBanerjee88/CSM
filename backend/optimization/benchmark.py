"""Benchmark Module for Quantum City.

Compares QAOASolver (quantum) against ClassicalSolver (classical brute-force) on the
same QUBO problem, reporting allocations, objective values, execution times, and gap.
"""

import time
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

from optimization.classical_solver import ClassicalSolver
from quantum.qaoa import QAOASolver
from quantum.qubo import CityResourceProblem, QUBOBuilder, QUBOResult


class BenchmarkResult(BaseModel):
    """JSON-serializable comparison of quantum vs classical QUBO solvers."""
    model_config = ConfigDict(extra="ignore")

    num_zones: int = Field(description="Number of binary decision variables")
    max_allocations: int = Field(description="Maximum simultaneous zone allocations")

    quantum_solver: str = Field(description="Quantum solver name")
    quantum_allocation: List[int] = Field(description="Binary allocation selected by quantum solver")
    quantum_objective: float = Field(description="QUBO objective value from quantum solver")
    quantum_execution_time_ms: float = Field(description="Wall-clock time for quantum solve in ms")

    classical_solver: str = Field(description="Classical solver name")
    classical_allocation: List[int] = Field(description="Binary allocation selected by classical solver")
    classical_objective: float = Field(description="QUBO objective value from classical solver")
    classical_execution_time_ms: float = Field(description="Wall-clock time for classical solve in ms")

    objective_gap: float = Field(description="Absolute gap between quantum and classical objectives (quantum - classical)")
    objectives_match: bool = Field(description="True if both solvers reached the same objective value")


class SolverBenchmark:
    """Runs head-to-head benchmarks of QAOASolver vs ClassicalSolver on a QUBO problem."""

    def __init__(
        self,
        qaoa_reps: int = 1,
        num_shots: int = 1024,
        seed: int = 42,
        optimizer_maxiter: int = 200,
    ) -> None:
        self._qaoa = QAOASolver(reps=qaoa_reps, num_shots=num_shots, seed=seed, optimizer_maxiter=optimizer_maxiter)
        self._classical = ClassicalSolver()

    def run(self, problem: CityResourceProblem) -> BenchmarkResult:
        """Benchmark quantum and classical solvers on the same QUBO problem.

        Args:
            problem: CityResourceProblem to formulate as QUBO and solve.

        Returns:
            BenchmarkResult with both solutions, timings, gap, and match flag.
        """
        qubo_result: QUBOResult = QUBOBuilder.build(problem)

        t0 = time.perf_counter()
        qaoa_sol = self._qaoa.solve(qubo_result)
        quantum_ms = round((time.perf_counter() - t0) * 1000.0, 4)

        t0 = time.perf_counter()
        classical_sol = self._classical.solve(qubo_result)
        classical_ms = round((time.perf_counter() - t0) * 1000.0, 4)

        gap = round(qaoa_sol.objective_value - classical_sol.objective_value, 6)

        return BenchmarkResult(
            num_zones=qubo_result.num_variables,
            max_allocations=qubo_result.max_allocations,
            quantum_solver=qaoa_sol.solver,
            quantum_allocation=qaoa_sol.selected_allocation,
            quantum_objective=qaoa_sol.objective_value,
            quantum_execution_time_ms=quantum_ms,
            classical_solver=classical_sol.solver,
            classical_allocation=classical_sol.selected_allocation,
            classical_objective=classical_sol.objective_value,
            classical_execution_time_ms=classical_sol.execution_time_ms,
            objective_gap=gap,
            objectives_match=(abs(gap) < 1e-5),
        )
