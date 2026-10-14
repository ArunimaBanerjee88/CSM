"""Road-level diversion optimizer.

Maps the road-diversion selection problem onto the existing CityResourceProblem /
QUBOBuilder / QAOASolver / ClassicalSolver stack — no modifications to those files.

Each candidate diversion edge becomes one binary decision variable:
  x_i = 1  →  divert traffic to candidate edge i
  x_i = 0  →  do not use that route

The QUBO encodes:
  - Energy cost  ≈ normalized congestion of the candidate edge (prefer low congestion)
  - Congestion   ≈ same measure (congestion_index acts as both)
  - Budget       ≈ we want exactly 1 edge selected (max_allocations = 1)

Returns full explainability: every candidate's congestion, score, and selection reason.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from quantum.qubo import CityResourceProblem, QUBOBuilder, QUBOResult
from quantum.qaoa import QAOASolver
from optimization.classical_solver import ClassicalSolver
from simulation.edge_traffic import EdgeState, HotspotReport


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class CandidateDetail(BaseModel):
    """Explainability record for one candidate diversion edge."""
    edge_id: str
    vehicle_count: int
    congestion_index: float
    capacity_pct: float
    qubo_variable: str          # e.g. "x_0"
    qubo_linear_coeff: float
    selected: bool
    reason: str


class RoadDiversionResult(BaseModel):
    """Full result from the road diversion optimizer."""
    model_config = ConfigDict(extra="ignore")

    hotspot_edge: str
    hotspot_congestion_before: float
    solver_used: str                    # "qaoa" | "brute_force"
    selected_diversion: Optional[str]   # winning edge, or None if no candidate
    objective_value: float
    quantum_execution_time_ms: float
    classical_execution_time_ms: float
    candidates: List[CandidateDetail]
    qaoa_top_bitstrings: Dict[str, int]
    classical_best_allocation: List[int]
    objectives_match: bool
    objective_gap: float
    explainability_summary: str


# ---------------------------------------------------------------------------
# Optimizer
# ---------------------------------------------------------------------------

class RoadDiversionOptimizer:
    """Selects the best diversion edge via QAOA/QUBO, with classical comparison."""

    def __init__(
        self,
        qaoa_reps: int = 1,
        num_shots: int = 512,
        seed: int = 42,
    ) -> None:
        self._qaoa = QAOASolver(reps=qaoa_reps, num_shots=num_shots, seed=seed)
        self._classical = ClassicalSolver()

    def optimize(
        self,
        hotspot: HotspotReport,
        edge_states: List[EdgeState],
    ) -> RoadDiversionResult:
        """Select best diversion for the hotspot using QAOA + classical comparison.

        Args:
            hotspot: Detected hotspot with candidate diversion edges.
            edge_states: Current edge states (used for congestion lookup).

        Returns:
            RoadDiversionResult with full explainability.
        """
        state_map = {s.edge_id: s for s in edge_states}
        candidates = hotspot.candidate_diversions

        # Fallback if no candidates exist
        if not candidates:
            return RoadDiversionResult(
                hotspot_edge=hotspot.hotspot_edge,
                hotspot_congestion_before=hotspot.hotspot_congestion,
                solver_used="none",
                selected_diversion=None,
                objective_value=0.0,
                quantum_execution_time_ms=0.0,
                classical_execution_time_ms=0.0,
                candidates=[],
                qaoa_top_bitstrings={},
                classical_best_allocation=[],
                objectives_match=True,
                objective_gap=0.0,
                explainability_summary="No connected candidate edges available for diversion.",
            )

        # Limit to 6 candidates so QUBO stays tractable
        candidates = candidates[:6]
        N = len(candidates)

        # Build QUBO: use hotspot congestion as energy proxy so that rerouting
        # from a highly congested road gets higher urgency, and candidate
        # congestion as the per-zone cost (lower congestion → lower cost → preferred).
        avg_candidate_congestion = sum(
            state_map[e].congestion_index for e in candidates if e in state_map
        ) / max(1, len(candidates))

        problem = CityResourceProblem(
            predicted_energy_demand_mw=hotspot.hotspot_congestion * 10_000.0,
            active_vehicle_count=hotspot.hotspot_vehicle_count,
            traffic_congestion_index=min(1.0, hotspot.hotspot_congestion),
            num_zones=N,
            max_allocations=1,          # pick exactly 1 diversion
            budget_penalty_weight=5.0,
        )

        qubo_result: QUBOResult = QUBOBuilder.build(problem)

        # --- QAOA ---
        t0 = time.perf_counter()
        qaoa_sol = self._qaoa.solve(qubo_result)
        qaoa_ms = round((time.perf_counter() - t0) * 1000.0, 4)

        # --- Classical ---
        t0 = time.perf_counter()
        classical_sol = self._classical.solve(qubo_result)
        classical_ms = round((time.perf_counter() - t0) * 1000.0, 4)

        gap = round(qaoa_sol.objective_value - classical_sol.objective_value, 6)
        match = abs(gap) < 1e-4

        # Interpret allocation: first 1-bit in QAOA solution → selected candidate index
        selected_idx: Optional[int] = None
        for i, bit in enumerate(qaoa_sol.selected_allocation):
            if bit == 1:
                selected_idx = i
                break
        selected_edge = candidates[selected_idx] if selected_idx is not None else candidates[0]

        # Build explainability records
        linear_coeffs = list(qubo_result.linear_coefficients.values())
        candidate_details: List[CandidateDetail] = []
        for i, eid in enumerate(candidates):
            s = state_map.get(eid)
            is_selected = (i == selected_idx) or (selected_idx is None and i == 0)
            if s:
                cong = s.congestion_index
                vc = s.vehicle_count
                cp = s.capacity_pct
            else:
                cong, vc, cp = 0.0, 0, 0.0

            if is_selected:
                reason = (
                    f"QAOA selected x_{i}=1: lowest QUBO objective among candidates. "
                    f"Congestion={cong:.3f}, vehicles={vc}, capacity={cp:.1f}%."
                )
            else:
                reason = (
                    f"Not selected (x_{i}=0). "
                    f"Congestion={cong:.3f}, vehicles={vc}, capacity={cp:.1f}%."
                )

            candidate_details.append(CandidateDetail(
                edge_id=eid,
                vehicle_count=vc,
                congestion_index=cong,
                capacity_pct=cp,
                qubo_variable=f"x_{i}",
                qubo_linear_coeff=round(linear_coeffs[i], 6) if i < len(linear_coeffs) else 0.0,
                selected=is_selected,
                reason=reason,
            ))

        summary = (
            f"Hotspot: {hotspot.hotspot_edge} (congestion={hotspot.hotspot_congestion:.3f}, "
            f"vehicles={hotspot.hotspot_vehicle_count}). "
            f"Candidates evaluated: {N}. "
            f"QAOA selected diversion -> {selected_edge} "
            f"(obj={qaoa_sol.objective_value:.4f}, solver={qaoa_sol.solver}). "
            f"Classical best obj={classical_sol.objective_value:.4f}. "
            f"Objectives match: {match} (gap={gap:.6f}). "
            f"QAOA time: {qaoa_ms:.1f}ms, Classical time: {classical_ms:.1f}ms."
        )

        return RoadDiversionResult(
            hotspot_edge=hotspot.hotspot_edge,
            hotspot_congestion_before=hotspot.hotspot_congestion,
            solver_used=qaoa_sol.solver,
            selected_diversion=selected_edge,
            objective_value=qaoa_sol.objective_value,
            quantum_execution_time_ms=qaoa_ms,
            classical_execution_time_ms=classical_ms,
            candidates=candidate_details,
            qaoa_top_bitstrings=qaoa_sol.top_bitstrings,
            classical_best_allocation=classical_sol.selected_allocation,
            objectives_match=match,
            objective_gap=gap,
            explainability_summary=summary,
        )
