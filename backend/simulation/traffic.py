"""Traffic Simulator Module for Quantum City.

Provides a high-level, production-structured interface for executing the base
SUMO city simulation and extracting granular traffic observations.
Reuses SUMORunner to avoid duplicating process management and TraCI lifecycle logic.

Scenario-aware simulation:
    When a World object is passed to run_simulation(), the traffic parameters
    (congestion_multiplier, autonomous_vehicle_ratio) drive scenario-specific route
    generation.  A temporary .rou.xml is written that keeps the same route topology
    but scales vehicle count and max-speed according to the world preset.
    The base city network (city.net.xml) is always reused unchanged.
"""

import os
import tempfile
import textwrap
from pathlib import Path
from typing import Any, List, Optional, Set, Union
from pydantic import BaseModel, Field

from simulation.sumo_runner import (
    SUMOConfigurationError,
    SUMONotInstalledError,
    SUMORunner,
    SUMOSimulationError,
)

# Standard default SUMO base city configuration location
DEFAULT_BASE_CITY_CONFIG = Path(__file__).resolve().parent / "base_city" / "city.sumocfg"
_BASE_CITY_DIR = DEFAULT_BASE_CITY_CONFIG.parent


def _ensure_sumo_environment() -> None:
    """Ensure SUMO_HOME and bin directory are present in the environment if installed."""
    if not os.environ.get("SUMO_HOME"):
        default_sumo_home = r"C:\Program Files (x86)\Eclipse\Sumo"
        if os.path.exists(default_sumo_home):
            os.environ["SUMO_HOME"] = default_sumo_home

    sumo_home = os.environ.get("SUMO_HOME")
    if sumo_home:
        bin_dir = os.path.join(sumo_home, "bin")
        if os.path.exists(bin_dir) and bin_dir not in os.environ.get("PATH", ""):
            os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")


class TrafficObservation(BaseModel):
    """Observation metrics collected at a single simulation step."""
    step: int = Field(description="Simulation step index")
    simulation_time: float = Field(description="Simulation time in seconds")
    active_vehicle_count: int = Field(description="Number of currently active vehicles on the network")
    average_vehicle_speed: float = Field(description="Average speed of active vehicles in m/s")
    total_waiting_time: float = Field(description="Total cumulative waiting time across active vehicles in seconds")

    @property
    def vehicle_count(self) -> int:
        """Alias for active_vehicle_count."""
        return self.active_vehicle_count

    @property
    def average_speed(self) -> float:
        """Alias for average_vehicle_speed."""
        return self.average_vehicle_speed


class TrafficSimulationResult(BaseModel):
    """Structured result of a completed traffic simulation run."""
    sumo_config_path: str = Field(description="Path to the SUMO configuration file used")
    total_simulation_steps: int = Field(description="Total number of simulation steps completed")
    simulation_duration: float = Field(description="Total simulated duration in seconds")
    total_unique_vehicles_observed: int = Field(description="Total number of distinct vehicles observed during the run")
    peak_active_vehicles: int = Field(description="Peak simultaneous active vehicles in any step")
    average_speed: float = Field(description="Overall mean active speed across all active steps in m/s")
    cumulative_waiting_time: float = Field(description="Cumulative waiting time in seconds")
    step_observations: List[TrafficObservation] = Field(default_factory=list, description="Per-step traffic observations")

    @property
    def total_steps(self) -> int:
        """Alias for total_simulation_steps."""
        return self.total_simulation_steps

    @property
    def total_unique_vehicles(self) -> int:
        """Alias for total_unique_vehicles_observed."""
        return self.total_unique_vehicles_observed


class _TraCIVehicleProxy:
    """Wraps TraCI vehicle module to track distinct vehicle IDs without altering behavior."""

    def __init__(self, vehicle_module: Any, tracker: Set[str]) -> None:
        self._vehicle = vehicle_module
        self._tracker = tracker

    def getIDList(self) -> Any:
        ids = self._vehicle.getIDList()
        self._tracker.update(ids)
        return ids

    def __getattr__(self, name: str) -> Any:
        return getattr(self._vehicle, name)


class _TraCIProxy:
    """Transparent TraCI proxy that intercepts vehicle queries to collect unique vehicle statistics."""

    def __init__(self, real_traci: Any) -> None:
        self._real = real_traci
        self.unique_vehicle_ids: Set[str] = set()
        self.vehicle = _TraCIVehicleProxy(real_traci.vehicle, self.unique_vehicle_ids)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


class TrafficSimulator:
    """High-level simulator for Quantum City traffic networks, powered by SUMORunner."""

    # All 25 vehicles from city.rou.xml with their route and base departure time
    _BASE_VEHICLES = [
        ("veh_00", "standard_car",      "r_we_row1",  0.0),
        ("veh_01", "standard_car",      "r_sn_col1",  2.0),
        ("veh_02", "public_transit_bus","r_we_row0",  4.0),
        ("veh_03", "standard_car",      "r_ns_col1",  6.0),
        ("veh_04", "standard_car",      "r_ew_row1",  8.0),
        ("veh_05", "standard_car",      "r_sn_col0", 10.0),
        ("veh_06", "standard_car",      "r_turn_w_s",12.0),
        ("veh_07", "standard_car",      "r_we_row1", 14.0),
        ("veh_08", "public_transit_bus","r_sn_col1", 16.0),
        ("veh_09", "standard_car",      "r_turn_s_e",18.0),
        ("veh_10", "standard_car",      "r_ew_row2", 20.0),
        ("veh_11", "standard_car",      "r_ns_col2", 22.0),
        ("veh_12", "standard_car",      "r_we_row1", 24.0),
        ("veh_13", "standard_car",      "r_sn_col1", 26.0),
        ("veh_14", "standard_car",      "r_ew_row0", 28.0),
        ("veh_15", "standard_car",      "r_ns_col0", 30.0),
        ("veh_16", "standard_car",      "r_we_row2", 32.0),
        ("veh_17", "standard_car",      "r_sn_col2", 34.0),
        ("veh_18", "public_transit_bus","r_we_row1", 36.0),
        ("veh_19", "standard_car",      "r_ns_col1", 38.0),
        ("veh_20", "standard_car",      "r_ew_row1", 40.0),
        ("veh_21", "standard_car",      "r_sn_col1", 42.0),
        ("veh_22", "standard_car",      "r_we_row0", 45.0),
        ("veh_23", "standard_car",      "r_turn_w_s",48.0),
        ("veh_24", "standard_car",      "r_turn_s_e",50.0),
    ]

    def __init__(
        self,
        default_config_path: Optional[Union[str, Path]] = None,
        traci_client: Optional[Any] = None,
    ) -> None:
        """Initialize TrafficSimulator.

        Args:
            default_config_path: Optional path to the default .sumocfg file.
                                 Defaults to backend/simulation/base_city/city.sumocfg.
            traci_client: Optional injected TraCI client (useful for unit testing or mocking).
        """
        _ensure_sumo_environment()
        self.default_config_path = (
            Path(default_config_path).resolve()
            if default_config_path is not None
            else DEFAULT_BASE_CITY_CONFIG
        )
        self._injected_traci = traci_client

    def _resolve_traci(self) -> Any:
        """Resolve TraCI client, wrapping it with an observation proxy."""
        if self._injected_traci is not None:
            return _TraCIProxy(self._injected_traci)

        try:
            import traci
            return _TraCIProxy(traci)
        except ImportError:
            try:
                import libsumo
                return _TraCIProxy(libsumo)
            except ImportError:
                raise SUMONotInstalledError(
                    "SUMO / TraCI is not installed or configured. "
                    "Please install Eclipse SUMO and the traci Python package."
                )

    def _build_scenario_config(
        self,
        world: Any,
        tmp_dir: str,
    ) -> str:
        """Write a temporary .rou.xml + .sumocfg adapted to world traffic parameters.

        Scales vehicle demand (count) by congestion_multiplier and boosts max-speed
        for standard_car by autonomous_vehicle_ratio (autonomous vehicles drive faster
        and more efficiently). The base network (city.net.xml) is always reused.

        Args:
            world: World object with .parameters.traffic attributes.
            tmp_dir: Directory in which to write temporary files.

        Returns:
            Absolute path string to the generated .sumocfg file.
        """
        # Extract parameters with safe defaults
        try:
            tp = world.parameters.traffic
            congestion_mult = float(getattr(tp, "congestion_multiplier", 1.0))
            av_ratio = float(getattr(tp, "autonomous_vehicle_ratio", 0.05))
        except Exception:
            congestion_mult = 1.0
            av_ratio = 0.05

        # Clamp multiplier to [0.1, 1.0] so we always have some vehicles
        congestion_mult = max(0.1, min(1.0, congestion_mult))

        # Speed boost: AV penetration allows higher effective max speed (up to +30%)
        speed_boost = 1.0 + 0.3 * av_ratio  # e.g. av_ratio=0.75 → ×1.225
        car_max_speed = round(13.89 * speed_boost, 2)

        # Select vehicles deterministically: keep first N = round(25 * congestion_mult)
        n_vehicles = max(1, round(len(self._BASE_VEHICLES) * congestion_mult))
        selected = self._BASE_VEHICLES[:n_vehicles]

        # Build route file XML
        route_xml_lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<routes xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"',
            '        xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/routes_file.xsd">',
            f'    <vType id="standard_car" accel="2.6" decel="4.5" sigma="0.0" length="4.5"'
            f' minGap="2.5" maxSpeed="{car_max_speed}" guiShape="passenger"/>',
            '    <vType id="public_transit_bus" accel="1.2" decel="3.5" sigma="0.0" length="12.0"'
            ' minGap="3.0" maxSpeed="11.11" guiShape="bus"/>',
            '    <route id="r_we_row1" edges="e_n01_n11 e_n11_n21"/>',
            '    <route id="r_sn_col1" edges="e_n10_n11 e_n11_n12"/>',
            '    <route id="r_we_row0" edges="e_n00_n10 e_n10_n20"/>',
            '    <route id="r_ns_col1" edges="e_n12_n11 e_n11_n10"/>',
            '    <route id="r_ew_row1" edges="e_n21_n11 e_n11_n01"/>',
            '    <route id="r_sn_col0" edges="e_n00_n01 e_n01_n02"/>',
            '    <route id="r_turn_w_s" edges="e_n01_n11 e_n11_n10"/>',
            '    <route id="r_turn_s_e" edges="e_n10_n11 e_n11_n21"/>',
            '    <route id="r_ew_row2" edges="e_n22_n12 e_n12_n02"/>',
            '    <route id="r_ns_col2" edges="e_n22_n21 e_n21_n20"/>',
            '    <route id="r_ew_row0" edges="e_n20_n10 e_n10_n00"/>',
            '    <route id="r_ns_col0" edges="e_n02_n01 e_n01_n00"/>',
            '    <route id="r_we_row2" edges="e_n02_n12 e_n12_n22"/>',
            '    <route id="r_sn_col2" edges="e_n20_n21 e_n21_n22"/>',
        ]
        for vid, vtype, route, depart in selected:
            route_xml_lines.append(
                f'    <vehicle id="{vid}" type="{vtype}" route="{route}" depart="{depart:.1f}"/>'
            )
        route_xml_lines.append('</routes>')
        route_xml = "\n".join(route_xml_lines) + "\n"

        net_xml_path = str(_BASE_CITY_DIR / "city.net.xml")
        rou_path = os.path.join(tmp_dir, "scenario.rou.xml")
        cfg_path = os.path.join(tmp_dir, "scenario.sumocfg")

        with open(rou_path, "w", encoding="utf-8") as f:
            f.write(route_xml)

        cfg_xml_lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<configuration>',
            '    <input>',
            f'        <net-file value="{net_xml_path}"/>',
            f'        <route-files value="{rou_path}"/>',
            '    </input>',
            '    <time>',
            '        <begin value="0"/>',
            '        <end value="100"/>',
            '        <step-length value="1.0"/>',
            '    </time>',
            '    <processing>',
            '        <collision.action value="none"/>',
            '        <time-to-teleport value="-1"/>',
            '    </processing>',
            '    <report>',
            '        <verbose value="true"/>',
            '        <no-step-log value="true"/>',
            '        <no-warnings value="false"/>',
            '    </report>',
            '</configuration>',
        ]
        cfg_xml = "\n".join(cfg_xml_lines) + "\n"

        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write(cfg_xml)

        return cfg_path

    def run_simulation(
        self,
        steps: int = 100,
        step_length: float = 1.0,
        gui: bool = False,
        sumo_config_path: Optional[Union[str, Path]] = None,
        world: Optional[Any] = None,
    ) -> TrafficSimulationResult:
        """Run a traffic simulation on the base city network and return structured results.

        Args:
            steps: Number of simulation steps to run (default 100).
            step_length: Duration of each step in seconds (default 1.0).
            gui: If True, launches sumo-gui; otherwise runs headless sumo.
            sumo_config_path: Optional path to a .sumocfg file; defaults to base_city/city.sumocfg.
            world: Optional World object. When supplied, scenario-specific traffic demand
                   is generated from world.parameters.traffic (congestion_multiplier,
                   autonomous_vehicle_ratio).

        Returns:
            TrafficSimulationResult containing aggregates and per-step observations.

        Raises:
            SUMONotInstalledError: If SUMO/TraCI is unavailable.
            SUMOConfigurationError: If the .sumocfg file does not exist.
            SUMOSimulationError: If a simulation error occurs during execution.
            ValueError: If steps <= 0.
        """
        # Build a scenario-specific config when a world with traffic params is given
        _tmp_dir_obj = None
        if world is not None and hasattr(world, "parameters") and hasattr(world.parameters, "traffic"):
            _tmp_dir_obj = tempfile.TemporaryDirectory()
            config_file = Path(self._build_scenario_config(world, _tmp_dir_obj.name))
        else:
            config_file = (
                Path(sumo_config_path).resolve()
                if sumo_config_path is not None
                else self.default_config_path
            )

            if not config_file.exists():
                raise SUMOConfigurationError(f"SUMO config file not found: '{config_file}'")

        proxy = self._resolve_traci()
        runner = SUMORunner(
            gui=gui,
            step_length=step_length,
            traci_client=proxy,
        )

        try:
            sim_result = runner.run_simulation(
                sumo_config_path=str(config_file),
                steps=steps,
                world=world,
            )
        finally:
            # Clean up temporary scenario files if they were created
            if _tmp_dir_obj is not None:
                try:
                    _tmp_dir_obj.cleanup()
                except Exception:
                    pass

        step_observations = [
            TrafficObservation(
                step=metric.step,
                simulation_time=metric.simulation_time,
                active_vehicle_count=metric.vehicle_count,
                average_vehicle_speed=metric.average_speed,
                total_waiting_time=metric.total_waiting_time,
            )
            for metric in sim_result.step_metrics
        ]

        peak_active = max((obs.active_vehicle_count for obs in step_observations), default=0)
        total_unique = len(proxy.unique_vehicle_ids)

        return TrafficSimulationResult(
            sumo_config_path=str(config_file),
            total_simulation_steps=sim_result.total_steps,
            simulation_duration=sim_result.total_simulation_time,
            total_unique_vehicles_observed=total_unique,
            peak_active_vehicles=peak_active,
            average_speed=sim_result.average_speed,
            cumulative_waiting_time=sim_result.total_waiting_time,
            step_observations=step_observations,
        )


def verify_traffic_simulation(steps: int = 100, gui: bool = False) -> TrafficSimulationResult:
    """Callable verification function for executing and testing TrafficSimulator."""
    simulator = TrafficSimulator()
    return simulator.run_simulation(steps=steps, gui=gui)
