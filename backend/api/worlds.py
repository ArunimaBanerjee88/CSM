"""Worlds API Module for Quantum City.

Exposes REST endpoints to manage and retrieve simulation scenarios (Worlds)
using the ScenarioManager and WorldGenerator.
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from multiverse.scenario_manager import ScenarioManager, World, WorldParameters
from multiverse.world_generator import WorldGenerator

router = APIRouter(
    prefix="/worlds",
    tags=["Worlds"],
)

# Global instances for in-memory world state
_scenario_manager = ScenarioManager()
_world_generator = WorldGenerator(scenario_manager=_scenario_manager)

# Pre-populate with standard presets on load
_world_generator.generate_predefined_worlds()


class WorldCreateRequest(BaseModel):
    """Payload for creating a new world."""
    model_config = ConfigDict(extra="ignore")
    
    name: str
    description: str = ""
    parameters: Optional[WorldParameters] = None
    world_id: Optional[str] = None
    base_preset: Optional[str] = None


class WorldUpdateRequest(BaseModel):
    """Payload for updating an existing world."""
    model_config = ConfigDict(extra="ignore")
    
    parameters: WorldParameters
    partial: bool = True


class WorldCloneRequest(BaseModel):
    """Payload for cloning a world."""
    model_config = ConfigDict(extra="ignore")
    
    new_name: str
    new_description: Optional[str] = None
    new_world_id: Optional[str] = None


@router.get("", response_model=List[World])
def list_worlds() -> List[World]:
    """Retrieve a list of all available worlds."""
    return _scenario_manager.list_worlds()


@router.get("/{world_id}", response_model=World)
def get_world(world_id: str) -> World:
    """Retrieve details for a specific world by ID."""
    try:
        return _scenario_manager.get_world(world_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("", response_model=World)
def create_world(request: WorldCreateRequest) -> World:
    """Create a new world, optionally based on a preset."""
    try:
        if request.base_preset:
            return _world_generator.generate_custom_world(
                name=request.name,
                description=request.description,
                base_preset=request.base_preset,
                parameter_overrides=request.parameters,
                world_id=request.world_id,
            )
        return _scenario_manager.create_world(
            name=request.name,
            description=request.description,
            parameters=request.parameters,
            world_id=request.world_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{world_id}", response_model=World)
def update_world(world_id: str, request: WorldUpdateRequest) -> World:
    """Update an existing world's parameters."""
    try:
        return _scenario_manager.update_parameters(
            world_id=world_id,
            parameters=request.parameters,
            partial=request.partial,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{world_id}")
def delete_world(world_id: str):
    """Delete a world by ID."""
    success = _scenario_manager.delete_world(world_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"World '{world_id}' not found.")
    return {"status": "success", "message": f"World '{world_id}' deleted."}


@router.post("/{world_id}/clone", response_model=World)
def clone_world(world_id: str, request: WorldCloneRequest) -> World:
    """Clone an existing world into a new one."""
    try:
        return _scenario_manager.clone_world(
            source_world_id=world_id,
            new_name=request.new_name,
            new_description=request.new_description,
            new_world_id=request.new_world_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
