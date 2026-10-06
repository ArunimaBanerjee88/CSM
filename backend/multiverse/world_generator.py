"""World Generator Module for Quantum City Metaverse.

Generates complete, simulation-ready city world configurations across predefined
future presets (Baseline 2030, Eco Future 2030, Smart Mobility 2030) as well as
custom configurable scenarios, using ScenarioManager for scenario persistence.
"""

from copy import deepcopy
import hashlib
import json
from typing import Any, Dict, List, Optional, Union

from multiverse.scenario_manager import (
    EnergyParameters,
    EnvironmentParameters,
    InfrastructureParameters,
    ScenarioManager,
    TrafficParameters,
    World,
    WorldParameters,
)


class WorldGenerator:
    """Generates simulation-ready city world scenarios using ScenarioManager."""

    # Predefined scenario specifications with distinct multi-domain parameters
    PRESETS: Dict[str, Dict[str, Any]] = {
        "baseline_2030": {
            "name": "Baseline 2030",
            "description": "Standard business-as-usual city development following existing infrastructure and growth trends.",
            "default_id": "world_baseline_2030",
            "parameters": {
                "traffic": {
                    "congestion_multiplier": 1.0,
                    "public_transit_ratio": 0.30,
                    "autonomous_vehicle_ratio": 0.05,
                },
                "energy": {
                    "renewable_percentage": 0.25,
                    "grid_capacity_mw": 1000.0,
                    "peak_demand_mw": 750.0,
                },
                "infrastructure": {
                    "road_maintenance_score": 0.80,
                    "ev_charging_density": 0.15,
                    "smart_sensor_coverage": 0.40,
                },
                "environment": {
                    "air_quality_index": 65.0,
                    "carbon_emissions_tons_per_day": 450.0,
                    "green_cover_percentage": 28.0,
                },
            },
        },
        "eco_future_2030": {
            "name": "Eco Future 2030",
            "description": "Sustainability-first urban ecosystem emphasizing renewable energy, carbon reduction, and extensive green cover.",
            "default_id": "world_eco_future_2030",
            "parameters": {
                "traffic": {
                    "congestion_multiplier": 0.75,
                    "public_transit_ratio": 0.60,
                    "autonomous_vehicle_ratio": 0.15,
                },
                "energy": {
                    "renewable_percentage": 0.85,
                    "grid_capacity_mw": 1200.0,
                    "peak_demand_mw": 650.0,
                },
                "infrastructure": {
                    "road_maintenance_score": 0.88,
                    "ev_charging_density": 0.60,
                    "smart_sensor_coverage": 0.70,
                },
                "environment": {
                    "air_quality_index": 30.0,
                    "carbon_emissions_tons_per_day": 120.0,
                    "green_cover_percentage": 45.0,
                },
            },
        },
        "smart_mobility_2030": {
            "name": "Smart Mobility 2030",
            "description": "High-tech transportation network characterized by high autonomous vehicle penetration, multi-modal transit, and sensor saturation.",
            "default_id": "world_smart_mobility_2030",
            "parameters": {
                "traffic": {
                    "congestion_multiplier": 0.55,
                    "public_transit_ratio": 0.50,
                    "autonomous_vehicle_ratio": 0.75,
                },
                "energy": {
                    "renewable_percentage": 0.50,
                    "grid_capacity_mw": 1100.0,
                    "peak_demand_mw": 720.0,
                },
                "infrastructure": {
                    "road_maintenance_score": 0.92,
                    "ev_charging_density": 0.75,
                    "smart_sensor_coverage": 0.90,
                },
                "environment": {
                    "air_quality_index": 45.0,
                    "carbon_emissions_tons_per_day": 260.0,
                    "green_cover_percentage": 32.0,
                },
            },
        },
    }

    def __init__(self, scenario_manager: Optional[ScenarioManager] = None) -> None:
        """Initialize WorldGenerator with an existing or new ScenarioManager.

        Args:
            scenario_manager: Optional ScenarioManager instance to store worlds.
        """
        self.scenario_manager = scenario_manager if scenario_manager is not None else ScenarioManager()

    @staticmethod
    def _compute_deterministic_id(name: str, params: Dict[str, Any]) -> str:
        """Compute a deterministic world_id based on name and parameter payload."""
        payload = json.dumps({"name": name, "params": params}, sort_keys=True)
        hash_digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8]
        clean_name = "".join(c if c.isalnum() else "_" for c in name.lower()).strip("_")
        return f"world_{clean_name}_{hash_digest}"

    def generate_preset(self, preset_key: str, world_id: Optional[str] = None) -> World:
        """Generate a predefined world by preset key.

        Args:
            preset_key: One of 'baseline_2030', 'eco_future_2030', 'smart_mobility_2030'.
            world_id: Optional explicit world_id. If omitted, uses standard deterministic ID.

        Returns:
            The generated World instance stored in scenario_manager.

        Raises:
            ValueError: If preset_key is not recognized.
        """
        key = preset_key.lower().replace("-", "_").replace(" ", "_")
        if key not in self.PRESETS:
            valid = list(self.PRESETS.keys())
            raise ValueError(f"Unknown preset '{preset_key}'. Available presets: {valid}")

        preset = self.PRESETS[key]
        target_id = world_id or preset["default_id"]
        params = WorldParameters.model_validate(preset["parameters"])

        return self.scenario_manager.create_world(
            name=preset["name"],
            description=preset["description"],
            parameters=params,
            world_id=target_id,
        )

    def generate_baseline_2030(self, world_id: Optional[str] = None) -> World:
        """Generate the Baseline 2030 world scenario."""
        return self.generate_preset("baseline_2030", world_id=world_id)

    def generate_eco_future_2030(self, world_id: Optional[str] = None) -> World:
        """Generate the Eco Future 2030 world scenario."""
        return self.generate_preset("eco_future_2030", world_id=world_id)

    def generate_smart_mobility_2030(self, world_id: Optional[str] = None) -> World:
        """Generate the Smart Mobility 2030 world scenario."""
        return self.generate_preset("smart_mobility_2030", world_id=world_id)

    def generate_predefined_worlds(self) -> List[World]:
        """Generate all three predefined city futures in the scenario manager.

        Returns:
            List containing Baseline 2030, Eco Future 2030, and Smart Mobility 2030 worlds.
        """
        return [
            self.generate_baseline_2030(),
            self.generate_eco_future_2030(),
            self.generate_smart_mobility_2030(),
        ]

    def generate_custom_world(
        self,
        name: str,
        description: str = "",
        base_preset: Optional[str] = None,
        parameter_overrides: Optional[Union[WorldParameters, Dict[str, Any]]] = None,
        world_id: Optional[str] = None,
    ) -> World:
        """Generate a custom city scenario with optional base preset and overrides.

        Args:
            name: Human-readable scenario name.
            description: Narrative description of this scenario.
            base_preset: Optional preset key to use as starting values.
            parameter_overrides: Dictionary or WorldParameters containing parameter overrides.
            world_id: Optional explicit world_id; if omitted, computed deterministically.

        Returns:
            The generated World instance stored in scenario_manager.
        """
        if base_preset:
            key = base_preset.lower().replace("-", "_").replace(" ", "_")
            if key not in self.PRESETS:
                raise ValueError(f"Unknown base preset '{base_preset}'. Available presets: {list(self.PRESETS.keys())}")
            merged_dict = deepcopy(self.PRESETS[key]["parameters"])
        else:
            merged_dict = WorldParameters().model_dump()

        if parameter_overrides:
            override_data = (
                parameter_overrides.model_dump()
                if isinstance(parameter_overrides, WorldParameters)
                else parameter_overrides
            )
            for domain, sub_params in override_data.items():
                if domain in merged_dict and isinstance(sub_params, dict) and isinstance(merged_dict[domain], dict):
                    merged_dict[domain].update(sub_params)
                else:
                    merged_dict[domain] = sub_params

        validated_params = WorldParameters.model_validate(merged_dict)
        final_id = world_id or self._compute_deterministic_id(name, merged_dict)

        return self.scenario_manager.create_world(
            name=name,
            description=description,
            parameters=validated_params,
            world_id=final_id,
        )
