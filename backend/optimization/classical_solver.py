"""Classical Solver Module for Quantum City.

Provides an exact brute-force classical baseline for solving the smart-city resource
allocation QUBO formulated by QUBOBuilder. Guarantees the global optimum for small N
and serves as the reference solution for benchmarking against the QAOA solver.
"""

import itertools
import time
from typing import Dict, List, Optional
import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from quantum.qubo import QUBOBuilder, QUBOResult


class ClassicalSolution(BaseModel):
    """JSON-serializable result of classical brute-force QUBO solve."""
    model_config = ConfigDict(extra="ignore")

    solver: str = Field(default="brute_force", description="Solver name")
    selected_allocation: List[int] = Field(description="Binary allocation vector achieving minimum objective")
    objective_value: float = Field(description="Minimum QUBO objective value x^T Q x + offset")
    num_zones: int = Field(description="Number of binary decision variables")
    total_allocations: int = Field(description="Total zones allocated in optimal solution")
    execution_time_ms: float = Field(description="Wall-clock solve time in milliseconds")
    all_objectives: Dict[str, float] = Field(
        description="Objective value for every enumerated bitstring (keys are binary strings)"
    )


class ClassicalSolver:
    """Exact brute-force solver for small QUBO problems (N <= 20 is practical)."""

    def solve(self, qubo_result: QUBOResult) -> ClassicalSolution:
        """Enumerate all 2^N binary assignments and return the global minimum.

        Args:
            qubo_result: QUBOResult from QUBOBuilder.build().

        Returns:
            ClassicalSolution with the optimal allocation, objective value, and timing.

        Raises:
            ValueError: If num_variables > 20 (brute-force becomes intractable).
        """
        N = qubo_result.num_variables
        if N > 20:
            raise ValueError(
                f"Brute-force enumeration is only practical for N <= 20 variables. Got N={N}."
            )

        Q = np.array(qubo_result.qubo_matrix, dtype=np.float64)
        offset = qubo_result.offset

        best_x: List[int] = [0] * N
        best_val = float("inf")
        all_objectives: Dict[str, float] = {}

        t_start = time.perf_counter()

        for bits in itertools.product([0, 1], repeat=N):
            x = np.array(bits, dtype=np.float64)
            val = round(float(x @ Q @ x + offset), 6)
            bitstring = "".join(str(b) for b in bits)
            all_objectives[bitstring] = val
            if val < best_val:
                best_val = val
                best_x = list(bits)

        elapsed_ms = round((time.perf_counter() - t_start) * 1000.0, 4)

        return ClassicalSolution(
            solver="brute_force",
            selected_allocation=best_x,
            objective_value=best_val,
            num_zones=N,
            total_allocations=sum(best_x),
            execution_time_ms=elapsed_ms,
            all_objectives=all_objectives,
        )
