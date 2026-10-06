"""ORM Models for Quantum City.

Defines SQLAlchemy table mappings for persistent storage of worlds,
simulation runs, and optimization runs in the local SQLite database.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from database.database import Base


class World(Base):
    """Persistent record of a Quantum City simulation scenario (world)."""
    __tablename__ = "worlds"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    parameters_json = Column(Text, nullable=True, comment="JSON-serialized WorldParameters")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    simulation_runs = relationship("SimulationRun", back_populates="world", cascade="all, delete-orphan")
    optimization_runs = relationship("OptimizationRun", back_populates="world", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<World id={self.id} name='{self.name}'>"


class SimulationRun(Base):
    """Persistent record of a completed SUMO traffic simulation run."""
    __tablename__ = "simulation_runs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    world_id = Column(Integer, ForeignKey("worlds.id", ondelete="CASCADE"), nullable=True)
    simulation_steps = Column(Integer, nullable=False)
    duration = Column(Float, nullable=False, comment="Total simulation duration in seconds")
    average_speed = Column(Float, nullable=True, comment="Average vehicle speed in m/s")
    congestion_index = Column(Float, nullable=True, comment="Normalized congestion index [0, 1]")
    cumulative_waiting_time = Column(Float, nullable=True, comment="Total cumulative waiting time in seconds")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    world = relationship("World", back_populates="simulation_runs")

    def __repr__(self) -> str:
        return f"<SimulationRun id={self.id} world_id={self.world_id} steps={self.simulation_steps}>"


class OptimizationRun(Base):
    """Persistent record of a completed QUBO quantum/classical optimization run."""
    __tablename__ = "optimization_runs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    world_id = Column(Integer, ForeignKey("worlds.id", ondelete="CASCADE"), nullable=True)
    predicted_energy_demand = Column(Float, nullable=False, comment="Predicted energy demand in MW")
    active_vehicle_count = Column(Integer, nullable=False)
    traffic_congestion_index = Column(Float, nullable=False, comment="Normalized congestion index [0, 1]")
    quantum_objective = Column(Float, nullable=True, comment="QUBO objective value from QAOA solver")
    classical_objective = Column(Float, nullable=True, comment="QUBO objective value from brute-force solver")
    selected_allocation_json = Column(Text, nullable=True, comment="JSON-serialized binary zone allocation vector")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    world = relationship("World", back_populates="optimization_runs")

    def __repr__(self) -> str:
        return f"<OptimizationRun id={self.id} world_id={self.world_id}>"
