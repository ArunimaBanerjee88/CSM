"""Scenario Manager Module for Quantum City Metaverse.

Manages multiple simulated future worlds and scenarios of the city in memory,
allowing creation, retrieval, updates, deletion, and cloning of scenarios with
configurable parameters across traffic, energy, infrastructure, and environment.
"""

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
import uuid

from pydantic import BaseModel, ConfigDict, Field


class WorldNotFoundError(KeyError):
    """Raised when a requested world_id does not exist."""
    pass


class WorldAlreadyExistsError(ValueError):
    """Raised when attempting to create a world with an existing world_id."""
    pass


class TrafficParameters(BaseModel):
    """Configurable traffic parameters for a scenario."""
    model_config = ConfigDict(extra="allow")

    congestion_multiplier: float = Field(default=1.0, ge=0.0, description="Traffic congestion factor (1.0 = baseline)")
    public_transit_ratio: float = Field(default=0.3, ge=0.0, le=1.0, description="Proportion of public transit usage")
    autonomous_vehicle_ratio: float = Field(default=0.0, ge=0.0, le=1.0, description="Proportion of autonomous vehicles")
    custom: Dict[str, Any] = Field(default_factory=dict, description="Additional custom traffic parameters")


class EnergyParameters(BaseModel):
    """Configurable energy parameters for a scenario."""
    model_config = ConfigDict(extra="allow")

    renewable_percentage: float = Field(default=0.25, ge=0.0, le=1.0, description="Share of energy from renewable sources")
    grid_capacity_mw: float = Field(default=1000.0, gt=0.0, description="Total grid capacity in megawatts")
    peak_demand_mw: float = Field(default=750.0, ge=0.0, description="Peak energy demand in megawatts")
    custom: Dict[str, Any] = Field(default_factory=dict, description="Additional custom energy parameters")


class InfrastructureParameters(BaseModel):
    """Configurable infrastructure parameters for a scenario."""
    model_config = ConfigDict(extra="allow")

    road_maintenance_score: float = Field(default=0.8, ge=0.0, le=1.0, description="Overall road quality index")
    ev_charging_density: float = Field(default=0.15, ge=0.0, description="EV charging stations per square km")
    smart_sensor_coverage: float = Field(default=0.4, ge=0.0, le=1.0, description="Percentage of city monitored by sensors")
    custom: Dict[str, Any] = Field(default_factory=dict, description="Additional custom infrastructure parameters")


class EnvironmentParameters(BaseModel):
    """Configurable environmental parameters for a scenario."""
    model_config = ConfigDict(extra="allow")

    air_quality_index: float = Field(default=60.0, ge=0.0, description="Average Air Quality Index (AQI)")
    carbon_emissions_tons_per_day: float = Field(default=450.0, ge=0.0, description="Daily metric tons of carbon emissions")
    green_cover_percentage: float = Field(default=28.0, ge=0.0, le=100.0, description="Percentage of urban green space")
    custom: Dict[str, Any] = Field(default_factory=dict, description="Additional custom environmental parameters")


class WorldParameters(BaseModel):
    """Composite model containing all domain parameters for a world."""
    traffic: TrafficParameters = Field(default_factory=TrafficParameters)
    energy: EnergyParameters = Field(default_factory=EnergyParameters)
    infrastructure: InfrastructureParameters = Field(default_factory=InfrastructureParameters)
    environment: EnvironmentParameters = Field(default_factory=EnvironmentParameters)


class World(BaseModel):
    """Represents a simulated future city scenario/world."""
    world_id: str
    name: str
    description: str = ""
    parameters: WorldParameters = Field(default_factory=WorldParameters)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ScenarioManager:
    """Manages the lifecycle of simulated city scenarios in memory."""

    def __init__(self) -> None:
        self._worlds: Dict[str, World] = {}

    def create_world(
        self,
        name: str,
        description: str = "",
        parameters: Optional[Union[WorldParameters, Dict[str, Any]]] = None,
        world_id: Optional[str] = None,
    ) -> World:
        """Create and store a new simulated world.

        Args:
            name: Human-readable name of the scenario.
            description: Narrative or description of this future scenario.
            parameters: Domain parameters (or dict), defaults to baseline if omitted.
            world_id: Optional explicit unique ID; auto-generated if omitted.

        Returns:
            The newly created World instance.

        Raises:
            WorldAlreadyExistsError: If a world with world_id already exists.
        """
        final_id = world_id or f"world_{uuid.uuid4().hex[:8]}"

        if final_id in self._worlds:
            raise WorldAlreadyExistsError(f"World with id '{final_id}' already exists.")

        if parameters is None:
            parsed_params = WorldParameters()
        elif isinstance(parameters, WorldParameters):
            parsed_params = parameters
        else:
            parsed_params = WorldParameters.model_validate(parameters)

        now = datetime.now(timezone.utc)
        world = World(
            world_id=final_id,
            name=name,
            description=description,
            parameters=parsed_params,
            created_at=now,
            updated_at=now,
        )
        self._worlds[final_id] = world
        return world

    def list_worlds(self) -> List[World]:
        """Return all available worlds.

        Returns:
            List of all stored World instances.
        """
        return list(self._worlds.values())

    def get_world(self, world_id: str) -> World:
        """Retrieve a world by its unique ID.

        Args:
            world_id: Unique identifier of the world.

        Returns:
            The matching World instance.

        Raises:
            WorldNotFoundError: If the world_id is not found.
        """
        if world_id not in self._worlds:
            raise WorldNotFoundError(f"World '{world_id}' not found.")
        return self._worlds[world_id]

    def update_parameters(
        self,
        world_id: str,
        parameters: Union[WorldParameters, Dict[str, Any]],
        partial: bool = True,
    ) -> World:
        """Update parameters for an existing world.

        Args:
            world_id: Unique identifier of the world to update.
            parameters: New parameter values (WorldParameters instance or dict).
            partial: If True, merges new values with existing parameters.
                     If False, replaces the entire parameter set.

        Returns:
            The updated World instance.

        Raises:
            WorldNotFoundError: If the world_id is not found.
        """
        world = self.get_world(world_id)

        if isinstance(parameters, WorldParameters):
            update_data = parameters.model_dump()
        else:
            update_data = parameters

        if partial:
            current_data = world.parameters.model_dump()
            # Deep merge dictionary
            for domain, sub_params in update_data.items():
                if domain in current_data and isinstance(sub_params, dict) and isinstance(current_data[domain], dict):
                    current_data[domain].update(sub_params)
                else:
                    current_data[domain] = sub_params
            world.parameters = WorldParameters.model_validate(current_data)
        else:
            world.parameters = WorldParameters.model_validate(update_data)

        world.updated_at = datetime.now(timezone.utc)
        return world

    def delete_world(self, world_id: str) -> bool:
        """Delete a world from the manager.

        Args:
            world_id: Unique identifier of the world to delete.

        Returns:
            True if deletion was successful.

        Raises:
            WorldNotFoundError: If the world_id is not found.
        """
        if world_id not in self._worlds:
            raise WorldNotFoundError(f"World '{world_id}' not found.")
        del self._worlds[world_id]
        return True

    def clone_world(
        self,
        source_world_id: str,
        new_name: str,
        new_description: Optional[str] = None,
        new_world_id: Optional[str] = None,
    ) -> World:
        """Clone an existing world into a new independent world scenario.

        Args:
            source_world_id: ID of the world to duplicate.
            new_name: Name for the cloned scenario.
            new_description: Description for the clone; defaults to source description.
            new_world_id: Optional explicit ID for the new clone.

        Returns:
            The newly created cloned World instance.

        Raises:
            WorldNotFoundError: If the source_world_id does not exist.
            WorldAlreadyExistsError: If new_world_id already exists.
        """
        source = self.get_world(source_world_id)
        cloned_parameters = deepcopy(source.parameters)
        description = new_description if new_description is not None else f"Clone of {source.name}. {source.description}"

        return self.create_world(
            name=new_name,
            description=description,
            parameters=cloned_parameters,
            world_id=new_world_id,
        )
