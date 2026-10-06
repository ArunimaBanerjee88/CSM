"""Optimization API Module for Quantum City.

Exposes REST endpoints for the quantum, classical, and benchmark optimization pipelines.
"""

from fastapi import APIRouter

from quantum.qubo import CityResourceProblem, QUBOBuilder
from quantum.quantum_solver import QuantumSolver, QuantumSolverResult
from optimization.classical_solver import ClassicalSolver, ClassicalSolution
from optimization.benchmark import SolverBenchmark, BenchmarkResult

router = APIRouter(
    prefix="/optimization",
    tags=["Optimization"],
)


@router.post("/quantum", response_model=QuantumSolverResult)
def optimize_quantum(problem: CityResourceProblem) -> QuantumSolverResult:
    """Solve the city resource allocation problem using the QAOA quantum solver."""
    solver = QuantumSolver(qaoa_reps=1, num_shots=1024, seed=42, optimizer_maxiter=100)
    return solver.solve(problem)


@router.post("/classical", response_model=ClassicalSolution)
def optimize_classical(problem: CityResourceProblem) -> ClassicalSolution:
    """Solve the city resource allocation problem using the classical brute-force solver."""
    qubo_result = QUBOBuilder.build(problem)
    solver = ClassicalSolver()
    return solver.solve(qubo_result)


@router.post("/benchmark", response_model=BenchmarkResult)
def optimize_benchmark(problem: CityResourceProblem) -> BenchmarkResult:
    """Run a head-to-head benchmark between quantum and classical solvers on the given problem."""
    benchmark = SolverBenchmark(qaoa_reps=1, num_shots=1024, seed=42, optimizer_maxiter=100)
    return benchmark.run(problem)
