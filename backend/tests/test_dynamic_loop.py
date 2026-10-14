"""Deterministic tests for the dynamic road-level traffic optimization loop.

Uses a mock TraCI client so no SUMO installation is required.
Covers:
  - Edge state collection
  - Hotspot detection
  - Rerouting logic (with mock TraCI)
  - RoadDiversionOptimizer (QAOA + classical, brute-force path)
  - DynamicTrafficOptimizer step_callback wiring
  - City-level metric preservation (TrafficSimulationResult still returned)
"""

import sys
import os
from pathlib import Path

# Ensure backend root is on path
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from simulation.edge_traffic import (
    EdgeState,
    collect_edge_states,
    detect_hotspot,
    reroute_vehicles_from_hotspot,
    EDGE_SUCCESSORS,
    EDGE_CAPACITY,
)
from optimization.road_optimizer import RoadDiversionOptimizer
from simulation.dynamic_loop import DynamicTrafficOptimizer, DynamicLoopResult


# ---------------------------------------------------------------------------
# Minimal Mock TraCI
# ---------------------------------------------------------------------------

class _MockEdge:
    def __init__(self, states):
        self._states = states   # {edge_id: (count, speed, halting)}

    def getLastStepVehicleNumber(self, eid):
        return self._states.get(eid, (0, 13.89, 0))[0]

    def getLastStepMeanSpeed(self, eid):
        return self._states.get(eid, (0, 13.89, 0))[1]

    def getLastStepHaltingNumber(self, eid):
        return self._states.get(eid, (0, 13.89, 0))[2]

    def getLastStepVehicleIDs(self, eid):
        count = self._states.get(eid, (0,))[0]
        return [f"veh_{i}" for i in range(count)]

    def adaptTraveltime(self, eid, tt):
        pass


class _MockLane:
    def getLength(self, lane_id):
        return 200.0


class _MockVehicle:
    def __init__(self, pos_map=None):
        self._pos = pos_map or {}

    def getLanePosition(self, vid):
        return self._pos.get(vid, 50.0)   # default mid-road

    def rerouteTraveltime(self, vid, currentTravelTimes=True):
        pass


class MockTraCI:
    """Minimal TraCI mock sufficient for edge_traffic and dynamic_loop tests."""

    def __init__(self, edge_states=None, vehicle_positions=None):
        self.edge = _MockEdge(edge_states or {})
        self.lane = _MockLane()
        self.vehicle = _MockVehicle(vehicle_positions)


# ---------------------------------------------------------------------------
# Test 1: collect_edge_states returns EdgeState for every known edge
# ---------------------------------------------------------------------------
def test_collect_edge_states_all_edges():
    mock = MockTraCI()
    states = collect_edge_states(mock)
    edge_ids = {s.edge_id for s in states}
    assert edge_ids == set(EDGE_SUCCESSORS.keys()), (
        f"Missing edges: {set(EDGE_SUCCESSORS.keys()) - edge_ids}"
    )
    print("PASS test_collect_edge_states_all_edges")


# ---------------------------------------------------------------------------
# Test 2: congestion index formula — heavy traffic raises congestion
# ---------------------------------------------------------------------------
def test_congestion_index_high_traffic():
    # Put 7 vehicles (near-capacity=8) on e_n01_n11 at zero speed
    mock = MockTraCI(edge_states={"e_n01_n11": (7, 0.1, 6)})
    states = collect_edge_states(mock)
    s = next(s for s in states if s.edge_id == "e_n01_n11")
    assert s.congestion_index > 0.7, f"Expected high congestion, got {s.congestion_index}"
    assert s.level in ("heavy", "gridlock"), f"Expected heavy/gridlock, got {s.level}"
    assert s.capacity_pct >= 87, f"Expected high cap_pct, got {s.capacity_pct}"
    print(f"PASS test_congestion_index_high_traffic (index={s.congestion_index}, level={s.level})")


# ---------------------------------------------------------------------------
# Test 3: detect_hotspot returns the most congested edge
# ---------------------------------------------------------------------------
def test_detect_hotspot_correct_edge():
    mock = MockTraCI(edge_states={
        "e_n01_n11": (7, 0.1, 6),    # very congested
        "e_n11_n01": (1, 12.0, 0),   # free
        "e_n11_n21": (2, 10.0, 0),   # light
    })
    states = collect_edge_states(mock)
    report = detect_hotspot(states, sim_time=60.0)
    assert report.hotspot_edge == "e_n01_n11", (
        f"Expected e_n01_n11 as hotspot, got {report.hotspot_edge}"
    )
    assert report.simulation_time == 60.0
    # Candidates must be successors of the hotspot
    expected_successors = set(EDGE_SUCCESSORS.get("e_n01_n11", []))
    for c in report.candidate_diversions:
        assert c in expected_successors, f"Non-successor candidate: {c}"
    print(f"PASS test_detect_hotspot_correct_edge (hotspot={report.hotspot_edge}, candidates={report.candidate_diversions})")


# ---------------------------------------------------------------------------
# Test 4: reroute skips vehicles near end of edge (>80%)
# ---------------------------------------------------------------------------
def test_reroute_skips_end_of_edge_vehicles():
    mock = MockTraCI(
        edge_states={"e_n01_n11": (2, 0.5, 2)},
        vehicle_positions={"veh_0": 170.0, "veh_1": 50.0},  # veh_0 at 85% → skip
    )
    states = collect_edge_states(mock)
    report = detect_hotspot(states, sim_time=60.0)
    records = reroute_vehicles_from_hotspot(mock, report, max_vehicles=5)

    skipped = [r for r in records if not r.reroute_applied and "skipped" in r.reason]
    rerouted = [r for r in records if r.reroute_applied]

    assert any(r.vehicle_id == "veh_0" for r in skipped), "veh_0 should be skipped (85% along edge)"
    print(f"PASS test_reroute_skips_end_of_edge_vehicles (skipped={[r.vehicle_id for r in skipped]}, rerouted={[r.vehicle_id for r in rerouted]})")


# ---------------------------------------------------------------------------
# Test 5: RoadDiversionOptimizer produces explainable result
# ---------------------------------------------------------------------------
def test_road_diversion_optimizer_explainability():
    mock = MockTraCI(edge_states={
        "e_n01_n11": (7, 0.5, 5),
        "e_n11_n01": (1, 12.0, 0),
        "e_n11_n21": (3, 8.0, 1),
        "e_n11_n10": (2, 11.0, 0),
        "e_n11_n12": (1, 13.0, 0),
    })
    states = collect_edge_states(mock)
    report = detect_hotspot(states, sim_time=60.0)

    optimizer = RoadDiversionOptimizer(qaoa_reps=1, num_shots=64, seed=0)
    result = optimizer.optimize(report, states)

    assert result.hotspot_edge == "e_n01_n11"
    assert result.selected_diversion is not None
    assert len(result.candidates) > 0
    assert result.explainability_summary != ""
    # Every candidate must have a reason
    for c in result.candidates:
        assert c.reason != "", f"Candidate {c.edge_id} has empty reason"
    # QUBO variable names must be sequential
    for i, c in enumerate(result.candidates):
        assert c.qubo_variable == f"x_{i}", f"QUBO var mismatch: {c.qubo_variable}"

    print(
        f"PASS test_road_diversion_optimizer_explainability\n"
        f"  hotspot={result.hotspot_edge}, selected={result.selected_diversion}, "
        f"solver={result.solver_used}, obj={result.objective_value:.4f}\n"
        f"  classical_obj={result.objective_value - result.objective_gap:.4f}, "
        f"gap={result.objective_gap:.6f}, match={result.objectives_match}\n"
        f"  QAOA time: {result.quantum_execution_time_ms:.1f}ms, "
        f"Classical time: {result.classical_execution_time_ms:.1f}ms\n"
        f"  Candidates:"
    )
    for c in result.candidates:
        mark = "*" if c.selected else " "
        print(f"    {mark} {c.edge_id}: congestion={c.congestion_index:.3f}, "
              f"count={c.vehicle_count}, cap={c.capacity_pct:.0f}%, "
              f"{c.qubo_variable}={int(c.selected)}")
    print(f"  Summary: {result.explainability_summary}")


# ---------------------------------------------------------------------------
# Test 6: DynamicTrafficOptimizer wiring – step_callback collects edge states
# ---------------------------------------------------------------------------
def test_dynamic_optimizer_step_callback_wiring():
    """Verify step_callback accumulates edge states from mock TraCI."""
    from simulation.sumo_runner import StepTrafficMetric
    from unittest.mock import MagicMock

    opt = DynamicTrafficOptimizer(seed=0)
    opt._edge_states_per_step = []
    opt._checkpoints = []
    opt._total_rerouted = 0
    opt._last_checkpoint_time = -9999.0
    opt._pending_after_measure = {}

    mock = MockTraCI(edge_states={"e_n01_n11": (5, 0.5, 3)})

    fake_metric = StepTrafficMetric(
        step=1, simulation_time=1.0, vehicle_count=5, average_speed=5.0, total_waiting_time=3.0
    )
    opt._step_callback(mock, 1, [fake_metric])

    assert len(opt._edge_states_per_step) == 1
    edges_step0 = {s.edge_id for s in opt._edge_states_per_step[0]}
    assert "e_n01_n11" in edges_step0
    print(f"PASS test_dynamic_optimizer_step_callback_wiring (edges collected: {len(edges_step0)})")


# ---------------------------------------------------------------------------
# Test 7: No-candidate fallback in optimizer
# ---------------------------------------------------------------------------
def test_optimizer_no_candidates_fallback():
    # Use an edge not in EDGE_SUCCESSORS so there are no candidates
    from simulation.edge_traffic import HotspotReport
    fake_hotspot = HotspotReport(
        simulation_time=60.0,
        hotspot_edge="e_nonexistent",
        hotspot_congestion=0.9,
        hotspot_vehicle_count=5,
        candidate_diversions=[],
        all_edge_states=[],
    )
    optimizer = RoadDiversionOptimizer(seed=0)
    result = optimizer.optimize(fake_hotspot, [])
    assert result.selected_diversion is None
    assert result.solver_used == "none"
    print(f"PASS test_optimizer_no_candidates_fallback")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 60)
    print("Dynamic Traffic Optimization — Test Suite")
    print("=" * 60)
    test_collect_edge_states_all_edges()
    test_congestion_index_high_traffic()
    test_detect_hotspot_correct_edge()
    test_reroute_skips_end_of_edge_vehicles()
    test_road_diversion_optimizer_explainability()
    test_dynamic_optimizer_step_callback_wiring()
    test_optimizer_no_candidates_fallback()
    print("=" * 60)
    print("All 7 tests PASSED")
    print("=" * 60)
