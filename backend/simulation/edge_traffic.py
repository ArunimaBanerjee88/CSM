"""Edge-level traffic state collection, hotspot detection, and rerouting.

This module adds per-road granularity on top of the existing city-level
TrafficSimulator without touching any existing files.  It plugs into
TrafficSimulator via the step_callback mechanism added in Phase 2.

Network topology (city.net.xml 3×3 grid):
  Nodes: n00 n01 n02  (row 0, top)
         n10 n11 n12  (row 1, middle)
         n20 n21 n22  (row 2, bottom)

  Directed edges (from→to):
    Horizontal: e_nXY_nXY' (same row, adjacent column)
    Vertical:   e_nXY_nX'Y (same column, adjacent row)
  All edges are one-way; connectivity follows the .net.xml connection table.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Static network graph derived from city.net.xml
# Maps edge_id → list of reachable edge_ids (via connected junctions)
# ---------------------------------------------------------------------------
EDGE_SUCCESSORS: Dict[str, List[str]] = {
    # row-0 horizontal
    "e_n00_n10": ["e_n10_n00", "e_n10_n20", "e_n10_n11"],
    "e_n10_n00": ["e_n00_n10"],
    "e_n10_n20": ["e_n20_n10", "e_n20_n21"],
    "e_n20_n10": ["e_n10_n00", "e_n10_n20", "e_n10_n11"],
    # row-1 horizontal
    "e_n01_n11": ["e_n11_n01", "e_n11_n10", "e_n11_n21", "e_n11_n12"],
    "e_n11_n01": ["e_n01_n11"],
    "e_n11_n21": ["e_n21_n11", "e_n21_n20", "e_n21_n22"],
    "e_n21_n11": ["e_n11_n01", "e_n11_n10", "e_n11_n21", "e_n11_n12"],
    # row-2 horizontal
    "e_n02_n12": ["e_n12_n02", "e_n12_n11", "e_n12_n22"],
    "e_n12_n02": ["e_n02_n12"],
    "e_n12_n22": ["e_n22_n12", "e_n22_n21"],
    "e_n22_n12": ["e_n12_n02", "e_n12_n11", "e_n12_n22"],
    # col-0 vertical
    "e_n00_n01": ["e_n01_n11", "e_n01_n00"],
    "e_n01_n02": ["e_n02_n12"],
    "e_n01_n00": ["e_n00_n10"],
    "e_n02_n01": ["e_n01_n00", "e_n01_n11"],
    # col-1 vertical
    "e_n10_n11": ["e_n11_n01", "e_n11_n10", "e_n11_n21", "e_n11_n12"],
    "e_n11_n10": ["e_n10_n00", "e_n10_n20"],
    "e_n11_n12": ["e_n12_n02", "e_n12_n11", "e_n12_n22"],
    "e_n12_n11": ["e_n11_n01", "e_n11_n10", "e_n11_n21", "e_n11_n12"],
    # col-2 vertical
    "e_n20_n21": ["e_n21_n11", "e_n21_n20", "e_n21_n22"],
    "e_n21_n20": ["e_n20_n10", "e_n20_n21"],
    "e_n21_n22": ["e_n22_n12", "e_n22_n21"],
    "e_n22_n21": ["e_n21_n11", "e_n21_n20", "e_n21_n22"],
    # turn edges (diagonal movement NOT present — only legal connected edges)
    "e_n20_n10": ["e_n10_n00", "e_n10_n20", "e_n10_n11"],
    "e_n22_n21": ["e_n21_n11", "e_n21_n20", "e_n21_n22"],
}

# Nominal capacity (vehicles) per edge for congestion index calculation
EDGE_CAPACITY: Dict[str, int] = {e: 8 for e in EDGE_SUCCESSORS}  # 2-lane × ~4 vehicles/lane

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class EdgeState(BaseModel):
    """Traffic state of one road/edge at a single simulation step."""
    edge_id: str = Field(description="SUMO edge identifier")
    vehicle_count: int = Field(description="Current number of vehicles on this edge")
    capacity: int = Field(description="Nominal edge capacity (vehicles)")
    capacity_pct: float = Field(description="Utilisation as 0–100 %")
    average_speed_ms: float = Field(description="Mean vehicle speed in m/s (0 if empty)")
    total_waiting_s: float = Field(description="Total waiting time of vehicles on edge in s")
    congestion_index: float = Field(description="Congestion index in [0, 1]; 1 = fully blocked")
    level: str = Field(description="'free' | 'moderate' | 'heavy' | 'gridlock'")


class HotspotReport(BaseModel):
    """Identifies the most congested edge at a checkpoint."""
    simulation_time: float
    hotspot_edge: str
    hotspot_congestion: float
    hotspot_vehicle_count: int
    candidate_diversions: List[str] = Field(
        description="Connected successor edges ranked by ascending congestion"
    )
    all_edge_states: List[EdgeState]


# ---------------------------------------------------------------------------
# Collection helpers
# ---------------------------------------------------------------------------

def _congestion_level(index: float) -> str:
    if index < 0.4:
        return "free"
    if index < 0.65:
        return "moderate"
    if index < 0.85:
        return "heavy"
    return "gridlock"


def collect_edge_states(traci: Any, speed_limit: float = 13.89) -> List[EdgeState]:
    """Query SUMO via TraCI for per-edge traffic state.

    Args:
        traci: Active TraCI/libsumo client (or compatible mock).
        speed_limit: Free-flow speed in m/s used to derive congestion index.

    Returns:
        List of EdgeState for every edge in EDGE_SUCCESSORS.
    """
    states: List[EdgeState] = []
    for edge_id, capacity in EDGE_CAPACITY.items():
        try:
            count = int(traci.edge.getLastStepVehicleNumber(edge_id))
            speed = float(traci.edge.getLastStepMeanSpeed(edge_id))
            waiting = float(traci.edge.getLastStepHaltingNumber(edge_id))  # halted vehicles
        except Exception:
            count, speed, waiting = 0, speed_limit, 0.0

        cap_pct = min(100.0, round(count / capacity * 100.0, 1))
        # congestion from speed deficit + occupancy
        speed_ratio = speed / speed_limit if speed_limit > 0 else 1.0
        occ_ratio = min(1.0, count / capacity) if capacity > 0 else 0.0
        congestion = round(min(1.0, 0.6 * (1.0 - speed_ratio) + 0.4 * occ_ratio), 4)

        states.append(EdgeState(
            edge_id=edge_id,
            vehicle_count=count,
            capacity=capacity,
            capacity_pct=cap_pct,
            average_speed_ms=round(speed, 3),
            total_waiting_s=round(waiting * 1.0, 2),   # halted count × 1 step
            congestion_index=congestion,
            level=_congestion_level(congestion),
        ))
    return states


def detect_hotspot(edge_states: List[EdgeState], sim_time: float) -> HotspotReport:
    """Return the most congested edge and ranked diversion candidates.

    Args:
        edge_states: Current per-edge states (from collect_edge_states).
        sim_time: Current simulation time in seconds.
    """
    if not edge_states:
        raise ValueError("edge_states must not be empty")

    worst = max(edge_states, key=lambda e: e.congestion_index)
    state_map = {s.edge_id: s for s in edge_states}

    successors = EDGE_SUCCESSORS.get(worst.edge_id, [])
    # rank candidates: ascending congestion, exclude hotspot itself
    candidates = sorted(
        [s for s in successors if s in state_map],
        key=lambda eid: state_map[eid].congestion_index,
    )

    return HotspotReport(
        simulation_time=sim_time,
        hotspot_edge=worst.edge_id,
        hotspot_congestion=worst.congestion_index,
        hotspot_vehicle_count=worst.vehicle_count,
        candidate_diversions=candidates,
        all_edge_states=edge_states,
    )


# ---------------------------------------------------------------------------
# Rerouting
# ---------------------------------------------------------------------------

class RerouteRecord(BaseModel):
    """Records one vehicle reroute decision with full explainability."""
    vehicle_id: str
    current_edge: str
    source_congestion: float
    chosen_diversion: Optional[str]
    alternatives_considered: List[Dict]  # [{edge, congestion, distance_rank, reason}]
    reroute_applied: bool
    reason: str


def reroute_vehicles_from_hotspot(
    traci: Any,
    hotspot: HotspotReport,
    max_vehicles: int = 5,
) -> List[RerouteRecord]:
    """Divert vehicles approaching the hotspot to the least-congested connected road.

    Strategy:
    - Only vehicles currently ON the hotspot edge are eligible.
    - For each vehicle pick the candidate diversion with the lowest congestion.
    - Use TraCI rerouteTraveltime so SUMO computes a legal path — no diagonal
      shortcuts, no teleportation, no head-on conflicts.
    - Vehicles that are already near the end of the edge (pos > 80 % of length)
      are skipped because rerouting mid-junction causes conflicts.

    Args:
        traci: Active TraCI client.
        hotspot: HotspotReport identifying the congested edge and ranked candidates.
        max_vehicles: Cap on simultaneous reroutes per checkpoint.

    Returns:
        List of RerouteRecord with full explainability for every vehicle considered.
    """
    records: List[RerouteRecord] = []

    if not hotspot.candidate_diversions:
        return records

    # Build alternative details for the explainability record
    state_map = {s.edge_id: s for s in hotspot.all_edge_states}

    alternatives_detail = [
        {
            "edge": eid,
            "congestion": state_map[eid].congestion_index if eid in state_map else None,
            "vehicle_count": state_map[eid].vehicle_count if eid in state_map else None,
            "distance_rank": rank + 1,
            "capacity_pct": state_map[eid].capacity_pct if eid in state_map else None,
            "reason": "ranked by ascending congestion among connected successors",
        }
        for rank, eid in enumerate(hotspot.candidate_diversions)
    ]

    best_diversion = hotspot.candidate_diversions[0]
    best_congestion = state_map[best_diversion].congestion_index if best_diversion in state_map else 0.0

    try:
        edge_length = float(traci.lane.getLength(hotspot.hotspot_edge + "_0"))
    except Exception:
        edge_length = 100.0  # safe default

    try:
        vehicles_on_edge = list(traci.edge.getLastStepVehicleIDs(hotspot.hotspot_edge))
    except Exception:
        vehicles_on_edge = []

    rerouted = 0
    for vid in vehicles_on_edge:
        if rerouted >= max_vehicles:
            break

        try:
            pos = float(traci.vehicle.getLanePosition(vid))
        except Exception:
            pos = 0.0

        # Skip vehicles too close to the junction exit (safety: avoid mid-junction change)
        if pos > edge_length * 0.8:
            records.append(RerouteRecord(
                vehicle_id=vid,
                current_edge=hotspot.hotspot_edge,
                source_congestion=hotspot.hotspot_congestion,
                chosen_diversion=None,
                alternatives_considered=alternatives_detail,
                reroute_applied=False,
                reason=f"Vehicle is at {pos:.1f}m / {edge_length:.1f}m (>{80}% of edge) — skipped to avoid junction conflict",
            ))
            continue

        try:
            # Boost travel-time on hotspot so SUMO's router prefers alternatives
            traci.edge.adaptTraveltime(hotspot.hotspot_edge, 9999.0)
            traci.vehicle.rerouteTraveltime(vid, currentTravelTimes=True)
            reroute_applied = True
            reason = (
                f"Travel-time on {hotspot.hotspot_edge} temporarily inflated; "
                f"SUMO router rerouted {vid} via legal connected roads. "
                f"Best candidate: {best_diversion} (congestion={best_congestion:.3f})"
            )
        except Exception as exc:
            reroute_applied = False
            reason = f"Reroute API call failed: {exc}"

        records.append(RerouteRecord(
            vehicle_id=vid,
            current_edge=hotspot.hotspot_edge,
            source_congestion=hotspot.hotspot_congestion,
            chosen_diversion=best_diversion if reroute_applied else None,
            alternatives_considered=alternatives_detail,
            reroute_applied=reroute_applied,
            reason=reason,
        ))
        if reroute_applied:
            rerouted += 1

    return records
