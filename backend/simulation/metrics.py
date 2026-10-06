"""Traffic Metrics and KPI Calculator Module for Quantum City.

Analyzes TrafficSimulationResult objects produced by the traffic simulator layer,
calculating key mobility performance indicators (KPIs) including average speed,
congestion index, traffic flow efficiency, active vehicle statistics, and waiting times.
Operates purely as an analytical calculation layer without starting or controlling SUMO.
"""

from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

from simulation.traffic import TrafficObservation, TrafficSimulationResult


class TrafficMetricsResult(BaseModel):
    """Normalized traffic mobility KPIs and performance indices."""
    model_config = ConfigDict(extra="ignore")

    average_speed: float = Field(description="Mean vehicle speed across active steps in m/s")
    peak_active_vehicles: int = Field(description="Maximum active vehicles observed simultaneously in any single step")
    average_active_vehicles: float = Field(description="Mean number of active vehicles per simulation step")
    cumulative_waiting_time: float = Field(description="Total accumulated waiting time across all vehicles in seconds")
    average_waiting_time_per_step: float = Field(description="Mean waiting time accumulated per simulation step in seconds")
    maximum_step_waiting_time: float = Field(description="Highest waiting time recorded in any single step in seconds")
    simulation_duration: float = Field(description="Total simulated duration in seconds")
    total_simulation_steps: int = Field(description="Total simulation steps evaluated")
    total_unique_vehicles: int = Field(description="Total unique vehicles observed across the run")
    congestion_index: float = Field(
        description="Normalized congestion level [0.0 = free flow, 1.0 = gridlock]: max(0, min(1, 1 - avg_speed / speed_limit))"
    )
    traffic_flow_efficiency: float = Field(
        description="Normalized flow efficiency [0.0 = standstill, 1.0 = optimal]: max(0, min(1, avg_speed / speed_limit))"
    )

    @property
    def total_steps(self) -> int:
        """Alias for total_simulation_steps."""
        return self.total_simulation_steps


class TrafficMetricsCalculator:
    """Calculates mobility KPIs and congestion metrics from simulation observations."""

    # Default speed limit for base city arterial roads: 13.9 m/s (~50 km/h)
    DEFAULT_SPEED_LIMIT: float = 13.9

    def __init__(self, speed_limit: float = DEFAULT_SPEED_LIMIT) -> None:
        """Initialize TrafficMetricsCalculator with a baseline speed limit.

        Args:
            speed_limit: Road speed limit in m/s (must be > 0).

        Raises:
            ValueError: If speed_limit <= 0.
        """
        if speed_limit <= 0.0:
            raise ValueError(f"speed_limit must be strictly greater than 0, got {speed_limit}")
        self.speed_limit = speed_limit

    def calculate_metrics(
        self,
        simulation_result: TrafficSimulationResult,
        speed_limit: Optional[float] = None,
    ) -> TrafficMetricsResult:
        """Calculate traffic metrics and KPIs from a TrafficSimulationResult.

        Args:
            simulation_result: Output from TrafficSimulator.run_simulation().
            speed_limit: Optional speed limit override in m/s (must be > 0).

        Returns:
            TrafficMetricsResult containing all calculated KPIs and indicators.

        Raises:
            ValueError: If simulation_result has no observations or speed_limit <= 0.
        """
        observations: List[TrafficObservation] = simulation_result.step_observations
        if not observations:
            raise ValueError("TrafficSimulationResult contains no step observations to calculate metrics.")

        limit = speed_limit if speed_limit is not None else self.speed_limit
        if limit <= 0.0:
            raise ValueError(f"speed_limit must be strictly greater than 0, got {limit}")

        total_steps = simulation_result.total_simulation_steps or len(observations)
        if total_steps <= 0:
            raise ValueError("Total simulation steps must be greater than zero.")

        # 1. Total simulation duration
        sim_duration = (
            simulation_result.simulation_duration
            if simulation_result.simulation_duration > 0.0
            else (observations[-1].simulation_time if observations else 0.0)
        )

        # 2. Vehicle count metrics
        peak_active = (
            simulation_result.peak_active_vehicles
            if simulation_result.peak_active_vehicles > 0
            else max((obs.active_vehicle_count for obs in observations), default=0)
        )
        total_vehicle_counts = sum(obs.active_vehicle_count for obs in observations)
        avg_active_vehicles = round(total_vehicle_counts / total_steps, 2)

        unique_vehicles = (
            simulation_result.total_unique_vehicles_observed
            if hasattr(simulation_result, "total_unique_vehicles_observed")
            else getattr(simulation_result, "total_unique_vehicles", 0)
        )

        # 3. Speed metrics
        if simulation_result.average_speed > 0.0:
            avg_speed = simulation_result.average_speed
        else:
            active_speeds = [obs.average_vehicle_speed for obs in observations if obs.active_vehicle_count > 0]
            avg_speed = sum(active_speeds) / len(active_speeds) if active_speeds else 0.0
        avg_speed = round(avg_speed, 2)

        # 4. Waiting time metrics
        cumulative_waiting = (
            simulation_result.cumulative_waiting_time
            if simulation_result.cumulative_waiting_time > 0.0
            else sum(obs.total_waiting_time for obs in observations)
        )
        cumulative_waiting = round(cumulative_waiting, 2)
        avg_waiting_per_step = round(cumulative_waiting / total_steps, 2)
        max_step_waiting = round(max((obs.total_waiting_time for obs in observations), default=0.0), 2)

        # 5. Normalized indicators
        speed_ratio = avg_speed / limit
        congestion_index = round(max(0.0, min(1.0, 1.0 - speed_ratio)), 4)
        traffic_flow_efficiency = round(max(0.0, min(1.0, speed_ratio)), 4)

        return TrafficMetricsResult(
            average_speed=avg_speed,
            peak_active_vehicles=peak_active,
            average_active_vehicles=avg_active_vehicles,
            cumulative_waiting_time=cumulative_waiting,
            average_waiting_time_per_step=avg_waiting_per_step,
            maximum_step_waiting_time=max_step_waiting,
            simulation_duration=round(sim_duration, 2),
            total_simulation_steps=total_steps,
            total_unique_vehicles=unique_vehicles,
            congestion_index=congestion_index,
            traffic_flow_efficiency=traffic_flow_efficiency,
        )


def calculate_traffic_metrics(
    simulation_result: TrafficSimulationResult,
    speed_limit: float = TrafficMetricsCalculator.DEFAULT_SPEED_LIMIT,
) -> TrafficMetricsResult:
    """Convenience helper to calculate traffic metrics in a single function call."""
    calculator = TrafficMetricsCalculator(speed_limit=speed_limit)
    return calculator.calculate_metrics(simulation_result=simulation_result)
