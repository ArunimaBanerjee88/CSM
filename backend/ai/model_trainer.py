"""Model Trainer Module for Quantum City.

Orchestrates the end-to-end training, evaluation, and inference pipeline for both
the TrafficPredictionModel (multi-scenario SUMO datasets) and EnergyPredictionModel
(real city energy demand CSV dataset).
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union
import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from ai.energy_model import (
    EnergyDatasetBuilder,
    EnergyModelEvaluation,
    EnergyModelTrainingResult,
    EnergyObservation,
    EnergyPrediction,
    EnergyPredictionModel,
)
from ai.scenario_dataset import ScenarioDatasetBuilder, ScenarioDatasetStatistics
from ai.traffic_model import (
    TrafficModelEvaluation,
    TrafficModelTrainingResult,
    TrafficPrediction,
    TrafficPredictionModel,
)
from simulation.traffic import TrafficObservation, TrafficSimulationResult


class ModelTrainingPipelineResult(BaseModel):
    """Structured report returned by the ModelTrainer pipeline upon completion."""
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    model_status: str = Field(default="trained", description="Operational status of the model")
    model_type: str = Field(default="RandomForestRegressor", description="Machine learning algorithm name")
    number_of_worlds: int = Field(description="Number of distinct city scenarios simulated")
    number_of_simulation_runs: int = Field(description="Total simulation runs included in training")
    total_observations: int = Field(description="Total raw step observations across all runs")
    training_samples: int = Field(description="Total supervised transition pairs (t -> t+1) used for training")
    features: List[str] = Field(description="Canonical ordered list of feature names")
    target_name: str = Field(description="Target forecast variable")
    evaluation: Optional[TrafficModelEvaluation] = Field(
        default=None,
        description="Holdout test evaluation metrics (MAE, RMSE, R2) if requested",
    )
    model_saved: bool = Field(default=False, description="Whether the trained model was saved to disk")
    model_save_path: Optional[str] = Field(default=None, description="Path where the model was saved if requested")


class ModelTrainer:
    """Manages the full lifecycle of training, evaluating, and applying TrafficPredictionModel."""

    def __init__(
        self,
        dataset_builder: Optional[ScenarioDatasetBuilder] = None,
        model: Optional[TrafficPredictionModel] = None,
        speed_limit: float = 13.9,
        n_estimators: int = 200,
        random_state: int = 42,
    ) -> None:
        """Initialize ModelTrainer.

        Args:
            dataset_builder: Optional ScenarioDatasetBuilder; creates default if omitted.
            model: Optional TrafficPredictionModel; creates default if omitted.
            speed_limit: Road speed limit in m/s used for congestion normalization (default 13.9).
            n_estimators: Number of trees in the Random Forest.
            random_state: Deterministic seed for reproducible training.
        """
        self.dataset_builder = dataset_builder if dataset_builder is not None else ScenarioDatasetBuilder()
        self.model = (
            model
            if model is not None
            else TrafficPredictionModel(
                speed_limit=speed_limit,
                n_estimators=n_estimators,
                random_state=random_state,
            )
        )
        self.speed_limit = speed_limit
        self._last_training_result: Optional[ModelTrainingPipelineResult] = None

        # Energy model — initialized lazily on first train/load
        self.energy_model: EnergyPredictionModel = EnergyPredictionModel(
            n_estimators=n_estimators,
            random_state=random_state,
        )

    def is_trained(self) -> bool:
        """Check whether the underlying prediction model is trained."""
        return self.model.is_trained()

    def train(
        self,
        steps_per_world: int = 100,
        evaluate_on_train: bool = True,
        test_size: float = 0.2,
        save_path: Optional[Union[str, Path]] = None,
        simulation_results: Optional[Sequence[TrafficSimulationResult]] = None,
    ) -> ModelTrainingPipelineResult:
        """Execute the end-to-end training pipeline on real multi-scenario SUMO runs.

        Args:
            steps_per_world: Number of simulation steps per scenario (default 100).
            evaluate_on_train: Whether to automatically compute holdout test metrics.
            test_size: Holdout fraction for evaluation (default 0.2).
            save_path: Optional file path to persist the trained model to disk.
            simulation_results: Optional pre-collected runs; runs predefined worlds if omitted.

        Returns:
            ModelTrainingPipelineResult with training counts, features, and evaluation metrics.
        """
        if simulation_results is not None:
            results = list(simulation_results)
            # Use results as provided
            num_runs = len(results)
            total_obs = sum(len(r.step_observations) for r in results)
            num_worlds = len(set(r.world_id for r in results if r.world_id)) or num_runs
        else:
            results = self.dataset_builder.run_predefined_worlds(steps=steps_per_world, gui=False)
            stats: ScenarioDatasetStatistics = self.dataset_builder.get_dataset_statistics()
            num_worlds = stats.number_of_worlds
            num_runs = stats.number_of_simulation_runs
            total_obs = stats.total_observations

        # Train the model
        train_metadata: TrafficModelTrainingResult = self.model.train(results)

        # Holdout test evaluation if requested
        eval_result: Optional[TrafficModelEvaluation] = None
        if evaluate_on_train:
            eval_result = self.model.evaluate(
                results,
                test_size=test_size,
                random_state=self.model.random_state,
            )

        # Save model only when explicitly requested
        model_saved = False
        saved_str_path: Optional[str] = None
        if save_path is not None:
            self.save_model(save_path)
            model_saved = True
            saved_str_path = str(Path(save_path).resolve())

        pipeline_result = ModelTrainingPipelineResult(
            model_status="trained",
            model_type=train_metadata.model_type,
            number_of_worlds=num_worlds,
            number_of_simulation_runs=num_runs,
            total_observations=total_obs,
            training_samples=train_metadata.number_of_training_samples,
            features=train_metadata.feature_names,
            target_name=train_metadata.target_name,
            evaluation=eval_result,
            model_saved=model_saved,
            model_save_path=saved_str_path,
        )

        self._last_training_result = pipeline_result
        return pipeline_result

    def evaluate(
        self,
        simulation_results: Optional[Sequence[TrafficSimulationResult]] = None,
        test_size: float = 0.2,
    ) -> TrafficModelEvaluation:
        """Evaluate the model on a holdout test split.

        Args:
            simulation_results: Optional simulation runs; uses accumulated builder results if omitted.
            test_size: Holdout fraction (default 0.2).

        Returns:
            TrafficModelEvaluation containing MAE, RMSE, R2, and test sample count.

        Raises:
            ValueError: If no simulation data is available.
        """
        target_results = (
            list(simulation_results)
            if simulation_results is not None
            else self.dataset_builder.simulation_results
        )

        if not target_results:
            raise ValueError(
                "No simulation results available for evaluation. "
                "Execute train() first or provide simulation_results."
            )

        return self.model.evaluate(
            target_results,
            test_size=test_size,
            random_state=self.model.random_state,
        )

    def predict(
        self,
        features: Union[Dict[str, float], List[float], np.ndarray, TrafficObservation],
    ) -> TrafficPrediction:
        """Forecast the next-step congestion index from current traffic features.

        Args:
            features: TrafficObservation object, dictionary of feature -> value, or ordered list.

        Returns:
            TrafficPrediction with predicted_congestion_index clamped to [0.0, 1.0].
        """
        if isinstance(features, TrafficObservation):
            return self.model.predict_observation(features, speed_limit=self.speed_limit)
        return self.model.predict(features)

    def save_model(self, path: Union[str, Path]) -> None:
        """Save the trained model and metadata to disk using joblib.

        Args:
            path: Target file destination.
        """
        self.model.save_model(path)

    def load_model(self, path: Union[str, Path]) -> None:
        """Load a previously trained model and metadata from disk.

        Args:
            path: Source file path.
        """
        self.model.load_model(path)

    # -------------------------------------------------------------------------
    # Energy Model Methods
    # -------------------------------------------------------------------------

    def train_energy_from_csv(
        self,
        csv_path: Union[str, Path],
    ) -> EnergyModelTrainingResult:
        """Load and validate the energy dataset CSV, then train EnergyPredictionModel.

        Args:
            csv_path: Path to the energy CSV dataset file (e.g. energy_dataset.csv).

        Returns:
            EnergyModelTrainingResult containing training metadata and sample count.

        Raises:
            FileNotFoundError: If csv_path does not exist.
            ValueError: If validation fails or data is insufficient.
        """
        observations = EnergyDatasetBuilder.load_from_csv(csv_path)
        return self.energy_model.train(observations)

    def evaluate_energy_from_csv(
        self,
        csv_path: Union[str, Path],
        test_size: float = 0.2,
        random_state: int = 42,
    ) -> EnergyModelEvaluation:
        """Evaluate the energy model on a holdout split from the CSV dataset.

        Args:
            csv_path: Path to the energy CSV dataset file.
            test_size: Holdout fraction for testing (default 0.2).
            random_state: Split seed for deterministic evaluation.

        Returns:
            EnergyModelEvaluation containing MAE, RMSE, R2, and test sample count.
        """
        observations = EnergyDatasetBuilder.load_from_csv(csv_path)
        return self.energy_model.evaluate(observations, test_size=test_size, random_state=random_state)

    def predict_energy(
        self,
        features: Union[Dict[str, float], List[float], np.ndarray, EnergyObservation],
    ) -> EnergyPrediction:
        """Forecast the next-step energy demand (MW) from canonical energy features.

        Canonical feature order: current_energy_demand, simulation_time,
        renewable_energy_percentage, active_vehicle_count, traffic_congestion_index.

        Args:
            features: EnergyObservation, dict of feature -> value, or ordered list/array.

        Returns:
            EnergyPrediction with predicted_energy_demand_mw >= 0.0.

        Raises:
            ValueError: If energy model is not trained or features are invalid.
        """
        return self.energy_model.predict(features)

    def save_energy_model(self, path: Union[str, Path]) -> None:
        """Save the trained energy model and metadata to disk using joblib.

        Args:
            path: Target file destination.
        """
        self.energy_model.save_model(path)

    def load_energy_model(self, path: Union[str, Path]) -> None:
        """Load a previously trained energy model and metadata from disk.

        Args:
            path: Source file path.
        """
        self.energy_model.load_model(path)
