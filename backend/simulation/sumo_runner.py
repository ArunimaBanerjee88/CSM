"""SUMO Runner Module for Quantum City Multiverse.

Manages and executes traffic simulations using Eclipse SUMO via TraCI or libsumo.
Provides availability checks, step-by-step metric collection (vehicle count,
average speed, total waiting time, simulation time), safe cleanup, and Pydantic-modeled
simulation result structures.
"""

from os import path
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class SUMONotInstalledError(RuntimeError):
    """Raised when neither TraCI nor libsumo is installed or configured."""
    pass


class SUMOConfigurationError(FileNotFoundError):
    """Raised when the specified SUMO configuration or network file is invalid or missing."""
    pass


class SUMOSimulationError(RuntimeError):
    """Raised when an error occurs during simulation execution."""
    pass


class StepTrafficMetric(BaseModel):
    """Traffic metrics collected at an individual simulation step."""
    step: int = Field(description="Step index")
    simulation_time: float = Field(description="Current simulation time in seconds")
    vehicle_count: int = Field(description="Number of vehicles currently on the network")
    average_speed: float = Field(description="Average vehicle speed in m/s")
    total_waiting_time: float = Field(description="Total cumulative waiting time across all vehicles in seconds")


class SimulationResult(BaseModel):
    """Aggregated traffic simulation results and time-series step metrics."""
    world_id: Optional[str] = Field(default=None, description="Associated scenario world ID")
    sumo_config_path: str = Field(description="Path to the .sumocfg file used")
    total_steps: int = Field(description="Number of simulation steps executed")
    total_simulation_time: float = Field(description="Total simulated time in seconds")
    average_vehicle_count: float = Field(description="Mean vehicle count per step")
    average_speed: float = Field(description="Mean vehicle speed across all active steps in m/s")
    total_waiting_time: float = Field(description="Total accumulated waiting time across all vehicles")
    step_metrics: List[StepTrafficMetric] = Field(default_factory=list, description="Per-step traffic measurements")


class SUMORunner:
    """Manages SUMO traffic simulation lifecycles and metric collection."""

    def __init__(
        self,
        gui: bool = False,
        step_length: float = 1.0,
        traci_client: Optional[Any] = None,
    ) -> None:
        """Initialize SUMORunner.

        Args:
            gui: If True, uses 'sumo-gui'; otherwise uses headless 'sumo'.
            step_length: Simulation step length in seconds.
            traci_client: Optional injected TraCI/libsumo client (useful for unit testing).
        """
        self.gui = gui
        self.step_length = step_length
        self._traci = traci_client
        self._is_running = False

    @staticmethod
    def is_sumo_available() -> bool:
        """Check whether TraCI or libsumo can be imported in the current environment."""
        try:
            import traci  # noqa: F401
            return True
        except ImportError:
            try:
                import libsumo  # noqa: F401
                return True
            except ImportError:
                return False

    def _get_traci(self) -> Any:
        """Retrieve the active TraCI/libsumo client or raise SUMONotInstalledError."""
        if self._traci is not None:
            return self._traci

        try:
            import traci
            return traci
        except ImportError:
            try:
                import libsumo
                return libsumo
            except ImportError:
                raise SUMONotInstalledError(
                    "SUMO or TraCI is not installed or configured in this environment. "
                    "Please install Eclipse SUMO, configure SUMO_HOME, and install traci ('pip install traci')."
                )

    def run_simulation(
        self,
        sumo_config_path: str,
        steps: int = 100,
        world: Optional[Union[Dict[str, Any], Any]] = None,
        additional_sumo_args: Optional[List[str]] = None,
    ) -> SimulationResult:
        """Execute a SUMO traffic simulation for a given scenario and collect metrics.

        Args:
            sumo_config_path: Absolute or relative path to the .sumocfg configuration file.
            steps: Number of simulation steps to run (must be > 0).
            world: Optional World object or dictionary containing scenario metadata/parameters.
            additional_sumo_args: Optional additional command-line flags to pass to SUMO.

        Returns:
            SimulationResult containing summary statistics and step-level metrics.

        Raises:
            SUMONotInstalledError: If SUMO/TraCI is not installed.
            SUMOConfigurationError: If the sumo_config_path does not exist.
            ValueError: If steps <= 0.
            SUMOSimulationError: If an error occurs during simulation execution.
        """
        if steps <= 0:
            raise ValueError(f"steps must be greater than 0, got {steps}")

        # Check configuration file existence (unless mocked client is used with a virtual path)
        if self._traci is None and not path.exists(sumo_config_path):
            raise SUMOConfigurationError(f"SUMO configuration file not found at: '{sumo_config_path}'")

        traci = self._get_traci()
        world_id: Optional[str] = None
        if world is not None:
            world_id = getattr(world, "world_id", None) or (world.get("world_id") if isinstance(world, dict) else None)

        binary = "sumo-gui" if self.gui else "sumo"
        cmd = [
            binary,
            "-c",
            sumo_config_path,
            "--step-length",
            str(self.step_length),
            "--no-step-log",
            "true",
            "--waiting-time-memory",
            "1000",
        ]

        if additional_sumo_args:
            cmd.extend(additional_sumo_args)

        step_metrics: List[StepTrafficMetric] = []
        total_waiting_time = 0.0

        try:
            traci.start(cmd)
            self._is_running = True

            for step_idx in range(1, steps + 1):
                traci.simulationStep()
                sim_time = float(traci.simulation.getTime())

                vehicle_ids = traci.vehicle.getIDList()
                count = len(vehicle_ids)

                if count > 0:
                    step_speeds = [float(traci.vehicle.getSpeed(vid)) for vid in vehicle_ids]
                    avg_speed = sum(step_speeds) / count
                    step_waiting = sum(float(traci.vehicle.getWaitingTime(vid)) for vid in vehicle_ids)
                else:
                    avg_speed = 0.0
                    step_waiting = 0.0

                total_waiting_time += step_waiting

                step_metrics.append(
                    StepTrafficMetric(
                        step=step_idx,
                        simulation_time=round(sim_time, 2),
                        vehicle_count=count,
                        average_speed=round(avg_speed, 2),
                        total_waiting_time=round(step_waiting, 2),
                    )
                )

        except Exception as exc:
            if isinstance(exc, (SUMONotInstalledError, SUMOConfigurationError, ValueError)):
                raise
            raise SUMOSimulationError(f"SUMO simulation failed during execution: {exc}") from exc

        finally:
            if self._is_running:
                try:
                    traci.close()
                except Exception:
                    pass
                finally:
                    self._is_running = False

        # Compute overall aggregates
        total_recorded_steps = len(step_metrics)
        avg_vehicles = (
            sum(m.vehicle_count for m in step_metrics) / total_recorded_steps
            if total_recorded_steps > 0
            else 0.0
        )
        active_steps = [m.average_speed for m in step_metrics if m.vehicle_count > 0]
        avg_overall_speed = sum(active_steps) / len(active_steps) if active_steps else 0.0
        final_sim_time = step_metrics[-1].simulation_time if step_metrics else 0.0

        return SimulationResult(
            world_id=world_id,
            sumo_config_path=sumo_config_path,
            total_steps=total_recorded_steps,
            total_simulation_time=final_sim_time,
            average_vehicle_count=round(avg_vehicles, 2),
            average_speed=round(avg_overall_speed, 2),
            total_waiting_time=round(total_waiting_time, 2),
            step_metrics=step_metrics,
        )
