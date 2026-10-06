"""QAOA Solver Module for Quantum City.

Solves the smart-city resource allocation QUBO using the Quantum Approximate Optimization
Algorithm (QAOA), implemented with Qiskit 1.x primitives (StatevectorSampler + QAOAAnsatz)
and SciPy classical parameter optimization.

Falls back to deterministic brute-force classical search if QAOA cannot execute locally
(e.g. missing primitives or NumPy/SciPy issues).

Usage:
    from quantum.qubo import CityResourceProblem, QUBOBuilder
    from quantum.qaoa import QAOASolver

    qubo_result = QUBOBuilder.build(problem)
    solution = QAOASolver().solve(qubo_result)
"""

from typing import Any, Dict, List, Optional, Tuple
import itertools
import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from quantum.qubo import QUBOBuilder, QUBOResult


class QAOASolution(BaseModel):
    """JSON-serializable result of a QAOA or brute-force QUBO solve."""
    model_config = ConfigDict(extra="ignore")

    solver: str = Field(description="Solver used: 'qaoa' or 'brute_force'")
    selected_allocation: List[int] = Field(description="Binary allocation vector x ∈ {0,1}^N (best measured bitstring)")
    objective_value: float = Field(description="QUBO objective value x^T Q x + offset for the selected allocation")
    num_zones: int = Field(description="Number of binary decision variables (city zones)")
    qaoa_reps: int = Field(description="Number of QAOA repetition layers (p)")
    optimal_parameters: List[float] = Field(description="Optimized QAOA variational angles [γ..., β...]")
    top_bitstrings: Dict[str, int] = Field(
        description="Top-5 measured bitstrings and their sample counts"
    )
    num_shots: int = Field(description="Number of circuit measurement shots")
    fallback_reason: Optional[str] = Field(
        default=None,
        description="Reason why brute-force fallback was used instead of QAOA (None = QAOA succeeded)"
    )


class QAOASolver:
    """Solves QUBO problems using QAOA via Qiskit 1.x StatevectorSampler.

    When QAOA is unavailable or fails, falls back to exhaustive brute-force search.
    """

    def __init__(
        self,
        reps: int = 1,
        num_shots: int = 1024,
        seed: int = 42,
        optimizer_maxiter: int = 200,
    ) -> None:
        """Initialize QAOASolver.

        Args:
            reps: Number of QAOA layers (p). Higher values improve quality but increase depth.
            num_shots: Number of circuit measurement samples per evaluation.
            seed: Deterministic seed for the StatevectorSampler.
            optimizer_maxiter: Maximum classical optimizer iterations.
        """
        self.reps = reps
        self.num_shots = num_shots
        self.seed = seed
        self.optimizer_maxiter = optimizer_maxiter

    def _qubo_to_ising_operator(self, qubo_result: QUBOResult) -> Any:
        """Convert QUBOResult into a Qiskit SparsePauliOp Ising cost Hamiltonian.

        QUBO -> Ising substitution: x_i = (1 - Z_i) / 2
        For Q[i][i] (linear):    contributes -Q[i][i]/2 * Z_i  +  Q[i][i]/2 * I
        For Q[i][j] (quadratic): contributes  Q[i][j]/4 * Z_i * Z_j
                                            -  Q[i][j]/4 * Z_i
                                            -  Q[i][j]/4 * Z_j
                                            +  Q[i][j]/4 * I

        Returns:
            SparsePauliOp cost Hamiltonian for QAOAAnsatz.
        """
        from qiskit.quantum_info import SparsePauliOp

        N = qubo_result.num_variables
        Q = np.array(qubo_result.qubo_matrix, dtype=np.float64)

        pauli_terms: List[Tuple[str, complex]] = []

        for i in range(N):
            # Linear: -Q[i][i]/2 * Z_i
            coeff_z = -Q[i][i] / 2.0
            if abs(coeff_z) > 1e-12:
                label = "I" * (N - 1 - i) + "Z" + "I" * i
                pauli_terms.append((label, complex(coeff_z)))

        for i in range(N):
            for j in range(i + 1, N):
                qij = Q[i][j]
                if abs(qij) < 1e-12:
                    continue

                # ZZ term: Q[i][j]/4 * Z_i Z_j
                coeff_zz = qij / 4.0
                label_zz = list("I" * N)
                label_zz[N - 1 - i] = "Z"
                label_zz[N - 1 - j] = "Z"
                pauli_terms.append(("".join(label_zz), complex(coeff_zz)))

                # Z_i term: -Q[i][j]/4
                coeff_zi = -qij / 4.0
                label_zi = list("I" * N)
                label_zi[N - 1 - i] = "Z"
                pauli_terms.append(("".join(label_zi), complex(coeff_zi)))

                # Z_j term: -Q[i][j]/4
                coeff_zj = -qij / 4.0
                label_zj = list("I" * N)
                label_zj[N - 1 - j] = "Z"
                pauli_terms.append(("".join(label_zj), complex(coeff_zj)))

        # Collapse duplicate Pauli labels by summing coefficients
        collapsed: Dict[str, complex] = {}
        for label, coeff in pauli_terms:
            collapsed[label] = collapsed.get(label, 0.0) + coeff

        return SparsePauliOp.from_list([(lbl, val) for lbl, val in collapsed.items()])

    def _sample_expectation(
        self,
        ansatz_meas: Any,
        params: np.ndarray,
        Q: np.ndarray,
        sampler: Any,
        N: int,
    ) -> float:
        """Evaluate mean QUBO objective over sampled bitstrings as QAOA cost function."""
        job = sampler.run([(ansatz_meas, params.tolist())])
        result = job.result()[0]
        counts = result.data.meas.get_counts()
        total = sum(counts.values())
        expectation = 0.0
        for bitstring, count in counts.items():
            # Qiskit bitstrings are LSB-first in the string (rightmost bit = qubit 0)
            x = np.array([int(b) for b in reversed(bitstring)], dtype=np.float64)
            obj = float(x @ Q @ x)
            expectation += (count / total) * obj
        return expectation

    def _brute_force(self, qubo_result: QUBOResult) -> QAOASolution:
        """Exhaustively evaluate all 2^N assignments and return the minimum."""
        N = qubo_result.num_variables
        Q = np.array(qubo_result.qubo_matrix, dtype=np.float64)

        best_x: List[int] = [0] * N
        best_val = float("inf")

        for bits in itertools.product([0, 1], repeat=N):
            x = np.array(bits, dtype=np.float64)
            val = float(x @ Q @ x + qubo_result.offset)
            if val < best_val:
                best_val = val
                best_x = list(bits)

        bitstring = "".join(str(b) for b in reversed(best_x))
        return QAOASolution(
            solver="brute_force",
            selected_allocation=best_x,
            objective_value=round(best_val, 6),
            num_zones=N,
            qaoa_reps=0,
            optimal_parameters=[],
            top_bitstrings={bitstring: self.num_shots},
            num_shots=self.num_shots,
            fallback_reason=None,
        )

    def solve(
        self,
        qubo_result: QUBOResult,
        force_brute_force: bool = False,
    ) -> QAOASolution:
        """Solve the QUBO using QAOA (or brute-force fallback).

        Args:
            qubo_result: QUBOResult from QUBOBuilder.build().
            force_brute_force: If True, skips QAOA and uses brute-force directly.

        Returns:
            QAOASolution with the selected allocation, objective value, and solver metadata.
        """
        if force_brute_force:
            return self._brute_force(qubo_result)

        try:
            return self._solve_qaoa(qubo_result)
        except Exception as exc:
            fallback = self._brute_force(qubo_result)
            fallback.solver = "brute_force"
            fallback.fallback_reason = f"QAOA failed: {exc}"
            return fallback

    def _solve_qaoa(self, qubo_result: QUBOResult) -> QAOASolution:
        """Internal QAOA solve using Qiskit 1.x StatevectorSampler + QAOAAnsatz."""
        from qiskit.circuit.library import QAOAAnsatz
        from qiskit.primitives import StatevectorSampler
        from scipy.optimize import minimize

        N = qubo_result.num_variables
        Q = np.array(qubo_result.qubo_matrix, dtype=np.float64)

        # Build cost Hamiltonian from QUBO
        cost_op = self._qubo_to_ising_operator(qubo_result)

        # Build QAOA ansatz and add measurements
        ansatz = QAOAAnsatz(cost_operator=cost_op, reps=self.reps)
        ansatz_meas = ansatz.copy()
        ansatz_meas.measure_all()

        sampler = StatevectorSampler(seed=self.seed)

        # Random initial parameters with fixed seed for determinism
        rng = np.random.default_rng(self.seed)
        x0 = rng.uniform(0, np.pi, ansatz.num_parameters)

        # Minimize expected QUBO cost over variational parameters
        opt_result = minimize(
            fun=lambda params: self._sample_expectation(
                ansatz_meas, params, Q, sampler, N
            ),
            x0=x0,
            method="COBYLA",
            options={"maxiter": self.optimizer_maxiter, "rhobeg": 0.5},
        )

        optimal_params = opt_result.x

        # Final high-shot sampling with optimal parameters
        final_sampler = StatevectorSampler(seed=self.seed)
        job = final_sampler.run([(ansatz_meas, optimal_params.tolist())])
        final_counts = job.result()[0].data.meas.get_counts()

        # Select bitstring with highest count as the solution
        best_bitstring = max(final_counts, key=lambda b: final_counts[b])
        best_x = [int(b) for b in reversed(best_bitstring)]
        best_obj = QUBOBuilder.evaluate_objective(qubo_result, best_x)

        # Top-5 bitstrings by count
        top_5 = dict(
            sorted(final_counts.items(), key=lambda kv: kv[1], reverse=True)[:5]
        )

        return QAOASolution(
            solver="qaoa",
            selected_allocation=best_x,
            objective_value=round(best_obj, 6),
            num_zones=N,
            qaoa_reps=self.reps,
            optimal_parameters=[round(p, 6) for p in optimal_params.tolist()],
            top_bitstrings=top_5,
            num_shots=self.num_shots,
            fallback_reason=None,
        )
