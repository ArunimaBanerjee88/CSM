from __future__ import annotations

import os
import random
import time
from typing import Any, Dict, List, Optional, Tuple

import traci


class DynamicTrafficEngine:
    """
    Dynamic traffic simulation engine.

    Behaviour:
    - Runs SUMO for multiple decision intervals.
    - Detects the most congested road.
    - Selects a valid alternative route using SUMO's routing engine.
    - Reroutes vehicles that are approaching the hotspot.
    - Never creates an invalid SUMO route.
    """

    def __init__(
        self,
        total_steps: int = 300,
        decision_interval: int = 60,
        seed: int = 42,
        sumo_config: Optional[str] = None,
        headless: bool = True,
    ):
        self.total_steps = max(1, int(total_steps))
        self.decision_interval = max(1, int(decision_interval))
        self.seed = int(seed)
        self.headless = headless

        random.seed(self.seed)

        if sumo_config is None:
            project_root = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..")
            )

            sumo_config = os.path.join(
                project_root,
                "simulation",
                "base_city",
                "city.sumocfg",
            )

        self.sumo_config = os.path.abspath(sumo_config)

        if not os.path.exists(self.sumo_config):
            raise FileNotFoundError(
                f"SUMO configuration not found: {self.sumo_config}"
            )

    # ------------------------------------------------------------------
    # SUMO STARTUP
    # ------------------------------------------------------------------

    def _start_sumo(self) -> None:
        """
        Start SUMO through TraCI.
        """
        import sumolib

        sumo_binary = sumolib.checkBinary(
            "sumo" if self.headless else "sumo-gui"
        )

        traci.start(
            [
                sumo_binary,
                "-c",
                self.sumo_config,
                "--seed",
                str(self.seed),
                "--no-step-log",
                "true",
                "--duration-log.disable",
                "true",
            ]
        )

    # ------------------------------------------------------------------
    # NETWORK HELPERS
    # ------------------------------------------------------------------

    def _get_road_edges(self) -> List[str]:
        """
        Return usable non-internal SUMO edges.
        """
        edges = []

        for edge_id in traci.edge.getIDList():
            if edge_id.startswith(":"):
                continue

            try:
                lane_ids = traci.edge.getLaneNumber(edge_id)

                if lane_ids > 0:
                    edges.append(edge_id)

            except Exception:
                continue

        return edges

    def _get_edge_congestion(self, edge_id: str) -> float:
        """
        Calculate congestion using mean speed relative to allowed speed.
        """
        try:
            speed = float(traci.edge.getLastStepMeanSpeed(edge_id))
            speed_limit = float(traci.edge.getMaxSpeed(edge_id))

            if speed_limit <= 0:
                return 0.0

            congestion = 1.0 - (speed / speed_limit)

            return max(0.0, min(1.0, congestion))

        except Exception:
            return 0.0

    def _get_edge_waiting(self, edge_id: str) -> float:
        try:
            return float(traci.edge.getWaitingTime(edge_id))
        except Exception:
            return 0.0

    def _get_edge_vehicle_count(self, edge_id: str) -> int:
        try:
            return int(traci.edge.getLastStepVehicleNumber(edge_id))
        except Exception:
            return 0

    # ------------------------------------------------------------------
    # HOTSPOT DETECTION
    # ------------------------------------------------------------------

    def _find_hotspot(self) -> Tuple[Optional[str], float]:
        """
        Find the road with the highest congestion.

        Score combines:
        - congestion
        - number of vehicles
        - waiting time
        """
        edges = self._get_road_edges()

        if not edges:
            return None, 0.0

        best_edge = None
        best_score = -1.0
        best_congestion = 0.0

        for edge_id in edges:
            congestion = self._get_edge_congestion(edge_id)
            vehicles = self._get_edge_vehicle_count(edge_id)
            waiting = self._get_edge_waiting(edge_id)

            score = (
                congestion * 0.60
                + min(vehicles / 20.0, 1.0) * 0.25
                + min(waiting / 300.0, 1.0) * 0.15
            )

            if score > best_score:
                best_score = score
                best_edge = edge_id
                best_congestion = congestion

        return best_edge, best_congestion

    # ------------------------------------------------------------------
    # VALID ROUTING
    # ------------------------------------------------------------------

    def _find_valid_route(
        self,
        from_edge: str,
        to_edge: str,
    ) -> Optional[List[str]]:
        """
        Ask SUMO for a valid route.

        IMPORTANT:
        We do NOT manually concatenate edge IDs.
        SUMO itself determines whether the route is connected.
        """
        if not from_edge or not to_edge:
            return None

        if from_edge == to_edge:
            return None

        try:
            result = traci.simulation.findRoute(
                from_edge,
                to_edge,
            )

            route = list(result.edges)

            if len(route) < 2:
                return None

            # Final safety validation.
            for i in range(len(route) - 1):
                current_edge = route[i]
                next_edge = route[i + 1]

                try:
                    connected = traci.simulation.findRoute(
                        current_edge,
                        next_edge,
                    ).edges

                    if not connected:
                        return None

                except Exception:
                    return None

            return route

        except Exception:
            return None

    def _find_alternative_route(
        self,
        current_edge: str,
        hotspot: str,
    ) -> Optional[List[str]]:
        """
        Find a route that moves a vehicle away from the hotspot.

        We try several candidate destination edges and let SUMO
        calculate every route.
        """
        all_edges = self._get_road_edges()

        if len(all_edges) < 3:
            return None

        candidates = []

        for edge in all_edges:
            if edge == current_edge:
                continue

            if edge == hotspot:
                continue

            congestion = self._get_edge_congestion(edge)

            vehicles = self._get_edge_vehicle_count(edge)

            score = congestion + (vehicles * 0.01)

            candidates.append((score, edge))

        candidates.sort(key=lambda x: x[0])

        # Prefer low-congestion destinations.
        for _, destination in candidates[:20]:
            route = self._find_valid_route(
                current_edge,
                destination,
            )

            if route and hotspot not in route:
                return route

        return None

    # ------------------------------------------------------------------
    # REROUTING
    # ------------------------------------------------------------------

    def _reroute_vehicles(
        self,
        hotspot: str,
    ) -> int:
        """
        Reroute vehicles that are currently on or approaching
        the congested road.
        """
        rerouted = 0

        vehicle_ids = list(traci.vehicle.getIDList())

        for vehicle_id in vehicle_ids:
            try:
                current_edge = traci.vehicle.getRoadID(vehicle_id)

                if not current_edge or current_edge.startswith(":"):
                    continue

                current_route = list(
                    traci.vehicle.getRoute(vehicle_id)
                )

                if not current_route:
                    continue

                current_index = traci.vehicle.getRouteIndex(
                    vehicle_id
                )

                # Ignore vehicles already past the hotspot.
                if hotspot not in current_route:
                    continue

                hotspot_index = current_route.index(hotspot)

                if hotspot_index < current_index:
                    continue

                # Only divert vehicles that are reasonably close.
                distance_in_edges = hotspot_index - current_index

                if distance_in_edges > 8:
                    continue

                alternative = self._find_alternative_route(
                    current_edge,
                    hotspot,
                )

                if not alternative:
                    continue

                # Make sure the new route starts at the vehicle's
                # current edge.
                if alternative[0] != current_edge:
                    continue

                traci.vehicle.setRoute(
                    vehicle_id,
                    alternative,
                )

                rerouted += 1

            except Exception:
                # One vehicle failing must never kill the simulation.
                continue

        return rerouted

    # ------------------------------------------------------------------
    # METRICS
    # ------------------------------------------------------------------

    def _collect_metrics(
        self,
        hotspot: Optional[str],
    ) -> Dict[str, Any]:

        vehicle_ids = list(traci.vehicle.getIDList())

        total_vehicles = len(vehicle_ids)

        if total_vehicles > 0:
            speeds = []

            for vehicle_id in vehicle_ids:
                try:
                    speeds.append(
                        float(
                            traci.vehicle.getSpeed(
                                vehicle_id
                            )
                        )
                    )
                except Exception:
                    pass

            average_speed = (
                sum(speeds) / len(speeds)
                if speeds
                else 0.0
            )
        else:
            average_speed = 0.0

        speed_limit = 13.9

        if average_speed > 0:
            congestion = max(
                0.0,
                min(
                    1.0,
                    1.0 - average_speed / speed_limit,
                ),
            )
        else:
            congestion = 1.0

        waiting_time = 0.0

        for vehicle_id in vehicle_ids:
            try:
                waiting_time += float(
                    traci.vehicle.getWaitingTime(
                        vehicle_id
                    )
                )
            except Exception:
                pass

        return {
            "total_vehicles": total_vehicles,
            "average_speed": average_speed,
            "congestion": congestion,
            "waiting_time": waiting_time,
            "hotspot": hotspot,
        }

    # ------------------------------------------------------------------
    # MAIN SIMULATION
    # ------------------------------------------------------------------

    def run(self) -> Dict[str, Any]:
        """
        Execute the complete dynamic traffic experiment.
        """
        started = time.perf_counter()

        cycles: List[Dict[str, Any]] = []

        initial_congestion = 0.0
        initial_waiting_time = 0.0

        final_congestion = 0.0
        final_waiting_time = 0.0

        total_rerouted = 0
        hotspot_count = 0

        try:
            self._start_sumo()

            simulation_time = 0

            first_metrics = None

            while simulation_time < self.total_steps:

                next_decision = min(
                    simulation_time + self.decision_interval,
                    self.total_steps,
                )

                while simulation_time < next_decision:
                    traci.simulationStep()
                    simulation_time += 1

                hotspot, hotspot_congestion = (
                    self._find_hotspot()
                )

                metrics_before = self._collect_metrics(
                    hotspot
                )

                if first_metrics is None:
                    first_metrics = metrics_before

                    initial_congestion = (
                        metrics_before["congestion"]
                    )

                    initial_waiting_time = (
                        metrics_before["waiting_time"]
                    )

                rerouted = 0

                if hotspot is not None:
                    rerouted = self._reroute_vehicles(
                        hotspot
                    )

                    if rerouted > 0:
                        hotspot_count += 1

                total_rerouted += rerouted

                # Give rerouted vehicles some time to move.
                for _ in range(
                    min(10, self.decision_interval)
                ):
                    if simulation_time >= self.total_steps:
                        break

                    traci.simulationStep()
                    simulation_time += 1

                final_metrics = self._collect_metrics(
                    hotspot
                )

                final_congestion = (
                    final_metrics["congestion"]
                )

                final_waiting_time = (
                    final_metrics["waiting_time"]
                )

                cycles.append(
                    {
                        "simulation_time": float(
                            simulation_time
                        ),
                        "hotspot": hotspot,
                        "diversion": (
                            rerouted > 0
                        ),
                        "total_vehicles": final_metrics[
                            "total_vehicles"
                        ],
                        "average_speed": final_metrics[
                            "average_speed"
                        ],
                        "congestion": final_metrics[
                            "congestion"
                        ],
                        "waiting_time": final_metrics[
                            "waiting_time"
                        ],
                        "rerouted_vehicles": rerouted,
                    }
                )

                print(
                    f"[DynamicTraffic] "
                    f"t={simulation_time}s | "
                    f"congestion="
                    f"{final_metrics['congestion']:.3f} | "
                    f"hotspot={hotspot} | "
                    f"rerouted={rerouted}"
                )

                if simulation_time >= self.total_steps:
                    break

            if initial_congestion > 0:
                improvement_percent = (
                    (
                        initial_congestion
                        - final_congestion
                    )
                    / initial_congestion
                ) * 100.0
            else:
                improvement_percent = 0.0

            execution_time_ms = (
                time.perf_counter() - started
            ) * 1000.0

            return {
                "simulation_steps": self.total_steps,
                "decision_interval": self.decision_interval,
                "cycles": cycles,
                "initial_congestion": initial_congestion,
                "final_congestion": final_congestion,
                "initial_waiting_time": initial_waiting_time,
                "final_waiting_time": final_waiting_time,
                "total_rerouted_vehicles": total_rerouted,
                "hotspot_count": hotspot_count,
                "improvement_percent": improvement_percent,
                "execution_time_ms": execution_time_ms,
            }

        finally:
            try:
                traci.close()
            except Exception:
                pass