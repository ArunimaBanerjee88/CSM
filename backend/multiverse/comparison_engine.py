"""Comparison Engine Module for Quantum City Metaverse.

Extracts, compares, and evaluates differences across multiple simulated city worlds
managed by ScenarioManager. Computes parameter-level deltas, percentage changes,
and trend directions (increased/decreased) in a structured, JSON-serializable format.
"""

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

from multiverse.scenario_manager import (
    ScenarioManager,
    World,
    WorldNotFoundError,
)


class ParameterDelta(BaseModel):
    """Represents difference and trend for a numeric parameter against baseline."""
    baseline_value: float
    target_value: float
    difference: float
    percentage_change: Optional[float] = None
    trend: Literal["increased", "decreased", "unchanged"]


class WorldOverview(BaseModel):
    """Minimal world metadata for comparison context."""
    world_id: str
    name: str
    description: str


class ParameterComparison(BaseModel):
    """Detailed comparison for an individual parameter across all worlds."""
    values: Dict[str, float] = Field(description="Raw values keyed by world_id")
    deltas_against_baseline: Dict[str, ParameterDelta] = Field(
        default_factory=dict,
        description="Deltas for non-baseline worlds keyed by target world_id",
    )


class ComparisonResult(BaseModel):
    """Structured, JSON-serializable multiverse comparison report."""
    baseline_world_id: str
    compared_world_ids: List[str]
    worlds: List[WorldOverview]
    # Domain -> Parameter Name -> ParameterComparison
    parameters: Dict[str, Dict[str, ParameterComparison]]
    # World ID -> {"increased": [...], "decreased": [...], "unchanged": [...]}
    trends_by_world: Dict[str, Dict[str, List[str]]]


class ComparisonEngine:
    """Engine for comparing multi-scenario city parameters and identifying trends."""

    DOMAINS: List[str] = ["traffic", "energy", "infrastructure", "environment"]

    def __init__(self, scenario_manager: ScenarioManager) -> None:
        """Initialize ComparisonEngine with a ScenarioManager instance.

        Args:
            scenario_manager: The ScenarioManager containing worlds to compare.
        """
        self.scenario_manager = scenario_manager

    def compare_worlds(
        self,
        world_ids: List[str],
        baseline_world_id: Optional[str] = None,
    ) -> ComparisonResult:
        """Compare parameters across two or more worlds.

        Args:
            world_ids: List of at least 2 unique world IDs to compare.
            baseline_world_id: Optional ID of the world to use as baseline reference.
                               Defaults to the first ID in world_ids.

        Returns:
            ComparisonResult object containing matrix of values, deltas, and trends.

        Raises:
            ValueError: If fewer than 2 world IDs are provided or baseline is invalid.
            WorldNotFoundError: If any of the world IDs do not exist.
        """
        if len(world_ids) < 2:
            raise ValueError("Comparison requires at least 2 world IDs.")

        # Ensure no duplicate world_ids while preserving order
        unique_ids: List[str] = list(dict.fromkeys(world_ids))
        if len(unique_ids) < 2:
            raise ValueError("Comparison requires at least 2 distinct world IDs.")

        # Retrieve and validate all worlds
        worlds: List[World] = []
        for wid in unique_ids:
            try:
                world = self.scenario_manager.get_world(wid)
                worlds.append(world)
            except (WorldNotFoundError, KeyError):
                raise WorldNotFoundError(f"World '{wid}' not found in scenario manager.")

        # Determine baseline world
        if baseline_world_id is not None:
            if baseline_world_id not in unique_ids:
                raise ValueError(
                    f"Baseline world '{baseline_world_id}' must be one of the compared world IDs: {unique_ids}"
                )
            baseline_id = baseline_world_id
        else:
            baseline_id = unique_ids[0]

        baseline_world = next(w for w in worlds if w.world_id == baseline_id)
        other_worlds = [w for w in worlds if w.world_id != baseline_id]

        world_overviews = [
            WorldOverview(world_id=w.world_id, name=w.name, description=w.description)
            for w in worlds
        ]

        parameters_comparison: Dict[str, Dict[str, ParameterComparison]] = {}
        trends_by_world: Dict[str, Dict[str, List[str]]] = {
            w.world_id: {"increased": [], "decreased": [], "unchanged": []}
            for w in other_worlds
        }

        # Inspect each domain
        baseline_params = baseline_world.parameters.model_dump()
        all_params_by_world = {w.world_id: w.parameters.model_dump() for w in worlds}

        for domain in self.DOMAINS:
            domain_comparison: Dict[str, ParameterComparison] = {}
            domain_baseline_dict = baseline_params.get(domain, {})

            for param_name, baseline_val in domain_baseline_dict.items():
                # Only compare numeric attributes (skip dictionaries like 'custom')
                if not isinstance(baseline_val, (int, float)) or isinstance(baseline_val, bool):
                    continue

                b_val = float(baseline_val)
                values_map: Dict[str, float] = {}
                deltas_map: Dict[str, ParameterDelta] = {}

                # Populate baseline value
                values_map[baseline_id] = b_val

                for other_w in other_worlds:
                    raw_val = all_params_by_world[other_w.world_id].get(domain, {}).get(param_name, 0.0)
                    t_val = float(raw_val)
                    values_map[other_w.world_id] = t_val

                    diff = round(t_val - b_val, 4)
                    if diff > 0:
                        trend = "increased"
                    elif diff < 0:
                        trend = "decreased"
                    else:
                        trend = "unchanged"

                    pct_change: Optional[float] = None
                    if b_val != 0.0:
                        pct_change = round(((t_val - b_val) / abs(b_val)) * 100.0, 2)

                    deltas_map[other_w.world_id] = ParameterDelta(
                        baseline_value=b_val,
                        target_value=t_val,
                        difference=diff,
                        percentage_change=pct_change,
                        trend=trend,
                    )

                    param_label = f"{domain}.{param_name}"
                    trends_by_world[other_w.world_id][trend].append(param_label)

                domain_comparison[param_name] = ParameterComparison(
                    values=values_map,
                    deltas_against_baseline=deltas_map,
                )

            parameters_comparison[domain] = domain_comparison

        return ComparisonResult(
            baseline_world_id=baseline_id,
            compared_world_ids=unique_ids,
            worlds=world_overviews,
            parameters=parameters_comparison,
            trends_by_world=trends_by_world,
        )
