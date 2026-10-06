"""QUBO Formulation Module for Quantum City.

Builds Quadratic Unconstrained Binary Optimization (QUBO) matrices for smart-city
resource allocation problems. Encodes energy demand minimization and traffic
congestion reduction into a binary objective function compatible with Qiskit's
QUBO/Ising solver interfaces.

Problem:
  Given predicted_energy_demand_mw, active_vehicle_count, and traffic_congestion_index,
  decide which of N city zones should receive additional resource allocation (1 = yes, 0 = no)
  to minimize energy cost and traffic congestion while respecting an allocation budget.

QUBO Form:
  minimize  x^T Q x
  where x ∈ {0, 1}^N are binary allocation decisions per zone.

The objective combines three terms:
  1. Energy cost:     penalty for activating zones proportional to energy demand.
  2. Congestion cost: penalty for activating zones proportional to congestion.
  3. Budget penalty:  quadratic penalty if total allocations exceed the maximum budget.
"""

from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from pydantic import BaseModel, ConfigDict, Field


class CityResourceProblem(BaseModel):
    """Input problem specification for QUBO resource allocation formulation."""
    model_config = ConfigDict(extra="ignore")

    predicted_energy_demand_mw: float = Field(
        description="Predicted next-step city energy demand in MW (>= 0.0)", ge=0.0
    )
    active_vehicle_count: int = Field(
        description="Number of active vehicles on the road network (>= 0)", ge=0
    )
    traffic_congestion_index: float = Field(
        description="Normalized traffic congestion index [0.0, 1.0]", ge=0.0, le=1.0
    )
    num_zones: int = Field(
        default=4,
        description="Number of city zones (QUBO binary variables), must be >= 2",
        ge=2,
    )
    max_allocations: int = Field(
        default=2,
        description="Maximum number of zones that can receive allocation simultaneously",
        ge=1,
    )
    budget_penalty_weight: float = Field(
        default=5.0,
        description="Lagrange penalty weight for budget constraint violation",
        gt=0.0,
    )


class QUBOResult(BaseModel):
    """JSON-serializable QUBO formulation output."""
    model_config = ConfigDict(extra="ignore")

    num_variables: int = Field(description="Number of binary decision variables (city zones)")
    max_allocations: int = Field(description="Maximum allowed simultaneous zone allocations")
    qubo_matrix: List[List[float]] = Field(
        description="Upper-triangular QUBO matrix Q (num_variables x num_variables)"
    )
    linear_coefficients: Dict[str, float] = Field(
        description="Diagonal terms Q[i][i]: individual cost per zone activation"
    )
    quadratic_coefficients: Dict[str, float] = Field(
        description="Off-diagonal terms Q[i][j] (i < j): pairwise interaction costs"
    )
    ising_h: List[float] = Field(
        description="Ising longitudinal field coefficients h_i (from QUBO diagonal terms)"
    )
    ising_J: Dict[str, float] = Field(
        description="Ising coupling coefficients J_ij (from QUBO off-diagonal terms)"
    )
    energy_cost_weight: float = Field(
        description="Normalized energy demand cost weight applied to zone activations"
    )
    congestion_cost_weight: float = Field(
        description="Normalized traffic congestion cost weight applied to zone activations"
    )
    budget_penalty_weight: float = Field(
        description="Lagrange multiplier for max allocation budget constraint"
    )
    offset: float = Field(
        description="Constant offset from the budget penalty term expansion: A * max_allocations^2"
    )


class QUBOBuilder:
    """Builds QUBO matrices for smart-city resource allocation problems.

    The optimization objective is:
        min_x  w_E * (sum_i x_i) * energy_norm          (energy cost)
             + w_C * (sum_i x_i) * congestion_norm       (congestion cost)
             + A  * (sum_i x_i - K)^2                    (budget constraint penalty)

    where x_i ∈ {0, 1} for each zone i, K = max_allocations, A = budget_penalty_weight.

    After expanding (sum_i x_i - K)^2:
      = sum_i x_i^2  -  2K * sum_i x_i  +  K^2
        (since x_i^2 = x_i for binary variables)
      = (1 - 2K) * sum_i x_i  +  2 * sum_{i<j} x_i * x_j  +  K^2

    Combined QUBO:
      Q[i][i] = w_E * energy_norm + w_C * congestion_norm + A * (1 - 2K)
      Q[i][j] = 2 * A     for all i < j
      offset   = A * K^2
    """

    # Scale factors for converting raw city inputs to normalized cost weights
    _ENERGY_SCALE: float = 10_000.0   # divide demand by this to normalize
    _VEHICLE_SCALE: float = 100_000.0  # divide vehicle count by this to normalize

    @classmethod
    def build(cls, problem: CityResourceProblem) -> QUBOResult:
        """Construct the QUBO matrix and Ising representation from a city resource problem.

        Args:
            problem: CityResourceProblem specifying the city inputs and QUBO parameters.

        Returns:
            QUBOResult containing the full QUBO matrix, linear/quadratic coefficients,
            Ising h and J parameters, and the constant offset.
        """
        N = problem.num_zones
        K = problem.max_allocations
        A = problem.budget_penalty_weight

        # Normalize city inputs into unit-scale cost weights
        energy_norm = problem.predicted_energy_demand_mw / cls._ENERGY_SCALE
        congestion_norm = problem.traffic_congestion_index
        vehicle_norm = problem.active_vehicle_count / cls._VEHICLE_SCALE

        # Cost weights per zone activation
        # Energy + vehicle congestion together form the combined city cost
        w_E = energy_norm + vehicle_norm
        w_C = congestion_norm

        # Build the QUBO matrix (upper-triangular, symmetric representation)
        Q = np.zeros((N, N), dtype=np.float64)

        # Diagonal: linear terms for each zone
        linear_val = w_E + w_C + A * (1.0 - 2.0 * K)
        for i in range(N):
            Q[i][i] = round(linear_val, 6)

        # Off-diagonal: budget-constraint pairwise coupling
        offdiag_val = 2.0 * A
        for i in range(N):
            for j in range(i + 1, N):
                Q[i][j] = round(offdiag_val, 6)

        # Constant offset from budget penalty expansion
        offset = round(A * (K ** 2), 6)

        # Collect coefficients as named dictionaries
        linear_coefficients: Dict[str, float] = {f"x_{i}": Q[i][i] for i in range(N)}
        quadratic_coefficients: Dict[str, float] = {
            f"x_{i}_x_{j}": Q[i][j]
            for i in range(N)
            for j in range(i + 1, N)
        }

        # Convert QUBO to Ising representation
        # QUBO -> Ising: x_i = (1 + s_i) / 2, s_i ∈ {-1, +1}
        # h_i = 0.5 * Q[i][i] + 0.25 * sum_{j != i} (Q[i][j] + Q[j][i])
        # J_ij = 0.25 * Q[i][j]
        ising_h: List[float] = []
        ising_J: Dict[str, float] = {}

        for i in range(N):
            hi = 0.5 * Q[i][i]
            for j in range(N):
                if j != i:
                    q_ij = Q[i][j] if i < j else Q[j][i]
                    hi += 0.25 * q_ij
            ising_h.append(round(hi, 6))

        for i in range(N):
            for j in range(i + 1, N):
                ising_J[f"s_{i}_s_{j}"] = round(0.25 * Q[i][j], 6)

        return QUBOResult(
            num_variables=N,
            max_allocations=K,
            qubo_matrix=[[round(Q[r][c], 6) for c in range(N)] for r in range(N)],
            linear_coefficients=linear_coefficients,
            quadratic_coefficients=quadratic_coefficients,
            ising_h=ising_h,
            ising_J=ising_J,
            energy_cost_weight=round(w_E, 6),
            congestion_cost_weight=round(w_C, 6),
            budget_penalty_weight=A,
            offset=offset,
        )

    @classmethod
    def evaluate_objective(
        cls,
        qubo_result: QUBOResult,
        assignment: List[int],
    ) -> float:
        """Evaluate the QUBO objective x^T Q x + offset for a given binary assignment.

        Args:
            qubo_result: The QUBOResult containing matrix Q.
            assignment: Binary vector x of length num_variables, values in {0, 1}.

        Returns:
            Total objective value (including constant offset).

        Raises:
            ValueError: If assignment length does not match num_variables or contains non-binary values.
        """
        N = qubo_result.num_variables
        if len(assignment) != N:
            raise ValueError(f"Assignment length {len(assignment)} != num_variables {N}")
        if not all(v in (0, 1) for v in assignment):
            raise ValueError("Assignment must contain only binary values 0 or 1.")

        Q = np.array(qubo_result.qubo_matrix, dtype=np.float64)
        x = np.array(assignment, dtype=np.float64)
        return float(x @ Q @ x + qubo_result.offset)
