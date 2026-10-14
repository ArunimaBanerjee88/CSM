"""Dynamic road-level traffic optimization loop.

Orchestrates:
  1. TrafficSimulator (unchanged) for the base SUMO run.
  2. edge_traffic.collect_edge_states() every step (collected every N seconds).
  3. edge_traffic.detect_hotspot() at 60-second checkpoints.
  4. RoadDiversionOptimizer (QAOA + classical) to select best diversion.
  5. edge_traffic.reroute_vehicles_from_hotspot() to apply rerouting via TraCI.
  6. Post-reroute metric collection to measure actual congestion change.

All existing APIs (TrafficSimulator.run_simulation, city-level metrics) are preserved.
Only the step_callback hook (added to sumo_runner.py / traffic.py in Phase 2) is used.
"""

from __future__ import annotations

import sys
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

# Make sure backend root is importable when running directly
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from simulation.traffic import TrafficSimulator, TrafficSimulationResult
from simulation.edge_traffic import (
    EdgeState,
    HotspotReport,
    RerouteRecord,
    collect_edge_states,
    detect_hotspot,
    reroute_vehicles_from_hotspot,
)
from optimization.road_optimizer import RoadDiversionOptimizer, RoadDiversionResult


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------

class CheckpointResult(BaseModel):
    """Full result at one 60-second optimization checkpoint."""
    simulation_time: float
    hotspot: HotspotReport
    optimization: RoadDiversionResult
    reroutes: List[RerouteRecord]
    vehicles_rerouted: int
    # Before / after congestion on the hotspot edge
    congestion_before: float
    congestion_after: Optional[float] = None   # filled after post-reroute steps
    congestion_clearance_estimated_s: float
    congestion_clearance_actual_s: Optional[float] = None
    diversion_applied_at_s: float


class DynamicLoopResult(BaseModel):
    """Complete result of the dynamic optimization loop run."""
    # City-level metrics (preserved from Phase 2)
    city_metrics: TrafficSimulationResult
    # Per-step per-edge states (list of steps, each with list of edges)
    edge_states_per_step: List[List[EdgeState]]
    # Checkpoint results (one per 60s hotspot detection)
    checkpoints: List[CheckpointResult]
    total_simulation_steps: int
    total_vehicles_rerouted: int
    summary: str


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class DynamicTrafficOptimizer:
    """Runs SUMO + per-step edge collection + 60s hotspot+QAOA rerouting loop."""

    HOTSPOT_INTERVAL_S: float = 60.0   # seconds between hotspot detections
    POST_REROUTE_STEPS: int = 10       # steps to wait after rerouting before measuring "after" congestion
    MAX_REROUTES_PER_CHECKPOINT: int = 5

    def __init__(
        self,
        qaoa_reps: int = 1,
        num_shots: int = 512,
        seed: int = 42,
        traci_client: Optional[Any] = None,
    ) -> None:
        self._simulator = TrafficSimulator(traci_client=traci_client)
        self._optimizer = RoadDiversionOptimizer(qaoa_reps=qaoa_reps, num_shots=num_shots, seed=seed)
        self._traci_ref: Optional[Any] = None   # filled by step_callback

        # Accumulated state
        self._edge_states_per_step: List[List[EdgeState]] = []
        self._checkpoints: List[CheckpointResult] = []
        self._total_rerouted: int = 0
        self._last_checkpoint_time: float = -1.0
        self._pending_after_measure: Dict[str, Any] = {}  # {hotspot_edge: {checkpoint_idx, measure_at_step}}

    def _step_callback(self, traci: Any, step_idx: int, step_metrics: list) -> None:
        """Called by SUMORunner after each simulation step via the step_callback hook."""
        self._traci_ref = traci

        # Collect edge states this step
        edge_states = collect_edge_states(traci)
        self._edge_states_per_step.append(edge_states)

        if not step_metrics:
            return
        current_time = float(step_metrics[-1].simulation_time)

        # Fill in "congestion_after" for pending checkpoints
        for key in list(self._pending_after_measure.keys()):
            pending = self._pending_after_measure[key]
            if step_idx >= pending["measure_at_step"]:
                chk_idx = pending["checkpoint_idx"]
                hotspot_edge = pending["hotspot_edge"]
                after_cong = next(
                    (s.congestion_index for s in edge_states if s.edge_id == hotspot_edge),
                    None,
                )
                if chk_idx < len(self._checkpoints):
                    chk = self._checkpoints[chk_idx]
                    chk.congestion_after = after_cong
                    if after_cong is not None and after_cong < chk.congestion_before:
                        chk.congestion_clearance_actual_s = round(
                            current_time - chk.diversion_applied_at_s, 1
                        )
                del self._pending_after_measure[key]

        # Every HOTSPOT_INTERVAL_S run detection + optimization + rerouting
        if current_time - self._last_checkpoint_time < self.HOTSPOT_INTERVAL_S:
            return
        self._last_checkpoint_time = current_time

        hotspot = detect_hotspot(edge_states, current_time)

        # Only intervene if congestion is meaningful
        if hotspot.hotspot_congestion < 0.35:
            return

        opt_result = self._optimizer.optimize(hotspot, edge_states)

        reroutes = reroute_vehicles_from_hotspot(
            traci, hotspot, max_vehicles=self.MAX_REROUTES_PER_CHECKPOINT
        )

        # Reset travel-time inflation after rerouting so it doesn't persist
        try:
            traci.edge.adaptTraveltime(hotspot.hotspot_edge, -1.0)
        except Exception:
            pass

        n_rerouted = sum(1 for r in reroutes if r.reroute_applied)
        self._total_rerouted += n_rerouted

        # Estimate clearance: rough heuristic (not claimed as measured)
        estimated_clearance = round(hotspot.hotspot_vehicle_count * 4.0, 1)

        chk = CheckpointResult(
            simulation_time=current_time,
            hotspot=hotspot,
            optimization=opt_result,
            reroutes=reroutes,
            vehicles_rerouted=n_rerouted,
            congestion_before=hotspot.hotspot_congestion,
            congestion_clearance_estimated_s=estimated_clearance,
            diversion_applied_at_s=current_time,
        )
        chk_idx = len(self._checkpoints)
        self._checkpoints.append(chk)

        # Schedule post-reroute measurement
        self._pending_after_measure[hotspot.hotspot_edge] = {
            "checkpoint_idx": chk_idx,
            "hotspot_edge": hotspot.hotspot_edge,
            "measure_at_step": step_idx + self.POST_REROUTE_STEPS,
        }

    def run(
        self,
        steps: int = 300,
        step_length: float = 1.0,
        gui: bool = False,
        world: Optional[Any] = None,
    ) -> DynamicLoopResult:
        """Run the dynamic optimization loop.

        Args:
            steps: Total simulation steps (default 300 = 5 minutes at 1 s/step).
            step_length: SUMO step length in seconds.
            gui: Launch sumo-gui if True.
            world: Optional World scenario object.

        Returns:
            DynamicLoopResult with city metrics, per-edge states, and checkpoints.
        """
        # Reset accumulated state for fresh run
        self._edge_states_per_step = []
        self._checkpoints = []
        self._total_rerouted = 0
        self._last_checkpoint_time = -1.0
        self._pending_after_measure = {}

        city_metrics = self._simulator.run_simulation(
            steps=steps,
            step_length=step_length,
            gui=gui,
            world=world,
            step_callback=self._step_callback,
        )

        # Build summary
        n_chk = len(self._checkpoints)
        if self._checkpoints:
            before_vals = [c.congestion_before for c in self._checkpoints]
            after_vals = [c.congestion_after for c in self._checkpoints if c.congestion_after is not None]
            before_avg = round(sum(before_vals) / len(before_vals), 4)
            after_avg = round(sum(after_vals) / len(after_vals), 4) if after_vals else "N/A"
            hotspots = list({c.hotspot.hotspot_edge for c in self._checkpoints})
            summary = (
                f"Dynamic loop: {steps} steps, {n_chk} checkpoints, "
                f"{self._total_rerouted} vehicles rerouted. "
                f"Avg congestion before rerouting: {before_avg}. "
                f"Avg congestion after (measured): {after_avg}. "
                f"Hotspot edges detected: {hotspots}."
            )
        else:
            summary = (
                f"Dynamic loop: {steps} steps. No congestion threshold exceeded "
                f"(threshold 0.35). City-level metrics preserved."
            )

        return DynamicLoopResult(
            city_metrics=city_metrics,
            edge_states_per_step=self._edge_states_per_step,
            checkpoints=self._checkpoints,
            total_simulation_steps=city_metrics.total_simulation_steps,
            total_vehicles_rerouted=self._total_rerouted,
            summary=summary,
        )
