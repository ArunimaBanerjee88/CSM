"""Prediction API Module for Quantum City.

Exposes REST endpoints for traffic congestion and energy demand predictions using
the AI models orchestrated by ModelTrainer. Models are lazily trained on their
first invocation.
"""

from pathlib import Path
from fastapi import APIRouter

from ai.model_trainer import ModelTrainer
from simulation.traffic import TrafficObservation
from ai.traffic_model import TrafficPrediction
from ai.energy_model import EnergyObservation, EnergyPrediction

router = APIRouter(
    prefix="/prediction",
    tags=["Prediction"],
)

# Global trainer instance shared across requests
_trainer = ModelTrainer(n_estimators=100)
_ENERGY_CSV_PATH = Path(__file__).resolve().parent.parent / "ai" / "energy_dataset.csv"


@router.post("/traffic", response_model=TrafficPrediction)
def predict_traffic(observation: TrafficObservation) -> TrafficPrediction:
    """Predict next-step traffic congestion based on current traffic features.
    
    Automatically lazily-trains the model on predefined SUMO scenarios on first request.
    """
    if not _trainer.is_trained():
        # Lazily train if not already trained
        _trainer.train(steps_per_world=50, evaluate_on_train=False)
        
    return _trainer.predict(observation)


@router.post("/energy", response_model=EnergyPrediction)
def predict_energy(observation: EnergyObservation) -> EnergyPrediction:
    """Predict next-step energy demand based on current city features.
    
    Automatically lazily-trains the model from the historical dataset on first request.
    """
    if not _trainer.energy_model.is_trained():
        # Lazily train from CSV
        _trainer.train_energy_from_csv(_ENERGY_CSV_PATH)
        
    return _trainer.predict_energy(observation)
