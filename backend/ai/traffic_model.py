"""Traffic Prediction Model Module for Quantum City.

Supervised machine learning model for forecasting the next-step congestion index
from current traffic observations, supporting training from single or multiple
SUMO simulation runs across diverse multiverse scenarios.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
import numpy as np
from pydantic import BaseModel, ConfigDict, Field

try:
    import joblib
except ImportError:
    joblib = None

from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

from simulation.traffic import TrafficObservation, TrafficSimulationResult


class TrafficModelTrainingResult(BaseModel):
    """Structured summary returned upon successful model training."""
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    model_type: str = Field(default="RandomForestRegressor", description="Machine learning algorithm used")
    number_of_training_samples: int = Field(description="Total supervised transition pairs (t -> t+1)")
    number_of_features: int = Field(description="Number of input features per sample")
    feature_names: List[str] = Field(description="Ordered list of feature names used for training")
    target_name: str = Field(description="Target prediction variable name")
    training_completed: bool = Field(default=True, description="Whether training executed to completion")
    speed_limit: float = Field(description="Road speed limit in m/s used for congestion normalization")


class TrafficModelEvaluation(BaseModel):
    """Evaluation metrics computed on an independent holdout test set."""
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    mae: float = Field(description="Mean Absolute Error on holdout test set")
    rmse: float = Field(description="Root Mean Squared Error on holdout test set")
    r2: float = Field(description="R-squared coefficient of determination on holdout test set")
    test_samples: int = Field(description="Number of test transition pairs evaluated")


class TrafficPrediction(BaseModel):
    """Result of a next-step traffic congestion forecast."""
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    predicted_congestion_index: float = Field(
        description="Predicted congestion index for next timestep t+1, clamped to [0.0, 1.0]"
    )
    model_type: str = Field(default="RandomForestRegressor", description="Model algorithm used")
    target_name: str = Field(default="next_step_congestion_index", description="Target variable name")


class TrafficDatasetBuilder:
    """Extracts supervised transition pairs (X_t -> y_{t+1}) from simulation runs."""

    FEATURE_NAMES: List[str] = [
        "step",
        "simulation_time",
        "active_vehicle_count",
        "average_vehicle_speed",
        "total_waiting_time",
        "current_congestion_index",
        "current_traffic_flow_efficiency",
    ]
    TARGET_NAME: str = "next_step_congestion_index"

    @classmethod
    def extract_observation_features(
        cls,
        obs: TrafficObservation,
        speed_limit: float,
    ) -> List[float]:
        """Convert a single TrafficObservation into the canonical feature vector."""
        if speed_limit <= 0.0:
            raise ValueError(f"speed_limit must be strictly greater than 0, got {speed_limit}")

        speed_ratio = obs.average_vehicle_speed / speed_limit
        curr_congestion = max(0.0, min(1.0, 1.0 - speed_ratio))
        curr_efficiency = max(0.0, min(1.0, speed_ratio))

        return [
            float(obs.step),
            float(obs.simulation_time),
            float(obs.active_vehicle_count),
            float(obs.average_vehicle_speed),
            float(obs.total_waiting_time),
            float(curr_congestion),
            float(curr_efficiency),
        ]

    @classmethod
    def calculate_congestion_target(
        cls,
        obs: TrafficObservation,
        speed_limit: float,
    ) -> float:
        """Compute the normalized congestion index target from a future observation."""
        if speed_limit <= 0.0:
            raise ValueError(f"speed_limit must be strictly greater than 0, got {speed_limit}")
        speed_ratio = obs.average_vehicle_speed / speed_limit
        return float(max(0.0, min(1.0, 1.0 - speed_ratio)))

    @classmethod
    def build_dataset(
        cls,
        simulation_results: Union[TrafficSimulationResult, Sequence[TrafficSimulationResult]],
        speed_limit: float = 13.9,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Convert one or multiple simulation runs into supervised (X, y) matrices.

        For each run of N observations, forms N - 1 transition pairs where:
          - X[i] = features at step t
          - y[i] = congestion index at step t + 1
        The final observation of each run is excluded from X because it lacks a t+1 target.

        Args:
            simulation_results: Single TrafficSimulationResult or collection of them.
            speed_limit: Speed limit in m/s used for normalization (default 13.9).

        Returns:
            Tuple of (X, y) as numpy arrays.

        Raises:
            ValueError: If speed_limit <= 0 or if no valid transition pairs exist.
        """
        if speed_limit <= 0.0:
            raise ValueError(f"speed_limit must be strictly greater than 0, got {speed_limit}")

        runs: List[TrafficSimulationResult] = (
            [simulation_results]
            if isinstance(simulation_results, TrafficSimulationResult)
            else list(simulation_results)
        )

        all_x: List[List[float]] = []
        all_y: List[float] = []

        for run in runs:
            observations = run.step_observations
            if not observations or len(observations) < 2:
                continue

            for t in range(len(observations) - 1):
                obs_t = observations[t]
                obs_next = observations[t + 1]

                x_t = cls.extract_observation_features(obs_t, speed_limit=speed_limit)
                y_next = cls.calculate_congestion_target(obs_next, speed_limit=speed_limit)

                all_x.append(x_t)
                all_y.append(y_next)

        if not all_x:
            raise ValueError(
                "Insufficient simulation data to build dataset. At least one run "
                "with 2 or more sequential step observations is required."
            )

        return np.array(all_x, dtype=np.float64), np.array(all_y, dtype=np.float64)


class TrafficPredictionModel:
    """Supervised Random Forest Regressor for forecasting next-step congestion index."""

    FEATURE_NAMES: List[str] = TrafficDatasetBuilder.FEATURE_NAMES
    TARGET_NAME: str = TrafficDatasetBuilder.TARGET_NAME
    DEFAULT_SPEED_LIMIT: float = 13.9

    def __init__(
        self,
        speed_limit: float = DEFAULT_SPEED_LIMIT,
        n_estimators: int = 200,
        random_state: int = 42,
        n_jobs: int = -1,
    ) -> None:
        """Initialize the traffic prediction model.

        Args:
            speed_limit: Road speed limit in m/s for congestion normalization.
            n_estimators: Number of trees in the random forest.
            random_state: Seed for deterministic model fitting.
            n_jobs: Number of CPU threads to use (-1 = all available cores).
        """
        if speed_limit <= 0.0:
            raise ValueError(f"speed_limit must be strictly greater than 0, got {speed_limit}")

        self.speed_limit = speed_limit
        self.n_estimators = n_estimators
        self.random_state = random_state
        self.n_jobs = n_jobs

        self._model: Optional[RandomForestRegressor] = None
        self._training_metadata: Optional[TrafficModelTrainingResult] = None

    def is_trained(self) -> bool:
        """Check whether the model has been trained or loaded."""
        return self._model is not None

    def get_feature_names(self) -> List[str]:
        """Return the canonical, fixed ordered list of feature names."""
        return list(self.FEATURE_NAMES)

    def train(
        self,
        simulation_results: Union[TrafficSimulationResult, Sequence[TrafficSimulationResult]],
    ) -> TrafficModelTrainingResult:
        """Train the Random Forest model on one or multiple simulation runs.

        Args:
            simulation_results: Single or multiple TrafficSimulationResult objects.

        Returns:
            TrafficModelTrainingResult containing training metrics and metadata.

        Raises:
            ValueError: If simulation data is insufficient or invalid.
        """
        x_data, y_data = TrafficDatasetBuilder.build_dataset(
            simulation_results,
            speed_limit=self.speed_limit,
        )

        regressor = RandomForestRegressor(
            n_estimators=self.n_estimators,
            random_state=self.random_state,
            n_jobs=self.n_jobs,
        )
        regressor.fit(x_data, y_data)

        self._model = regressor
        self._training_metadata = TrafficModelTrainingResult(
            model_type="RandomForestRegressor",
            number_of_training_samples=len(x_data),
            number_of_features=len(self.FEATURE_NAMES),
            feature_names=list(self.FEATURE_NAMES),
            target_name=self.TARGET_NAME,
            training_completed=True,
            speed_limit=self.speed_limit,
        )
        return self._training_metadata

    def evaluate(
        self,
        simulation_results: Union[TrafficSimulationResult, Sequence[TrafficSimulationResult]],
        test_size: float = 0.2,
        random_state: int = 42,
        min_samples_for_split: int = 10,
    ) -> TrafficModelEvaluation:
        """Evaluate next-step prediction on an independent holdout test split.

        Args:
            simulation_results: Single or multiple TrafficSimulationResult objects.
            test_size: Fraction of samples to reserve for test evaluation (default 0.2).
            random_state: Split seed for deterministic holdout separation.
            min_samples_for_split: Minimum number of samples required for evaluation.

        Returns:
            TrafficModelEvaluation with MAE, RMSE, and R2 on the holdout test set.

        Raises:
            ValueError: If sample count is too small for a meaningful split.
        """
        x_data, y_data = TrafficDatasetBuilder.build_dataset(
            simulation_results,
            speed_limit=self.speed_limit,
        )

        total_samples = len(x_data)
        if total_samples < min_samples_for_split:
            raise ValueError(
                f"Insufficient transition samples ({total_samples}) for meaningful train/test split. "
                f"Minimum required is {min_samples_for_split}."
            )

        x_train, x_test, y_train, y_test = train_test_split(
            x_data,
            y_data,
            test_size=test_size,
            random_state=random_state,
        )

        eval_regressor = RandomForestRegressor(
            n_estimators=self.n_estimators,
            random_state=self.random_state,
            n_jobs=self.n_jobs,
        )
        eval_regressor.fit(x_train, y_train)
        y_pred = eval_regressor.predict(x_test)
        y_pred_clamped = np.clip(y_pred, 0.0, 1.0)

        mae = float(mean_absolute_error(y_test, y_pred_clamped))
        rmse = float(np.sqrt(mean_squared_error(y_test, y_pred_clamped)))
        r2 = float(r2_score(y_test, y_pred_clamped))

        return TrafficModelEvaluation(
            mae=round(mae, 4),
            rmse=round(rmse, 4),
            r2=round(r2, 4),
            test_samples=len(y_test),
        )

    def predict(
        self,
        features: Union[Dict[str, float], List[float], np.ndarray],
    ) -> TrafficPrediction:
        """Predict next-step congestion index from current traffic state features.

        Args:
            features: Dictionary of feature_name -> value, or ordered vector.

        Returns:
            TrafficPrediction with predicted_congestion_index clamped to [0.0, 1.0].

        Raises:
            ValueError: If model is not trained or features are missing/invalid.
        """
        if self._model is None:
            raise ValueError("TrafficPredictionModel is not trained. Call train() or load_model() first.")

        if isinstance(features, dict):
            missing = [f for f in self.FEATURE_NAMES if f not in features]
            if missing:
                raise ValueError(f"Missing required features for prediction: {missing}")
            vector = [float(features[f]) for f in self.FEATURE_NAMES]
        elif isinstance(features, (list, tuple)):
            if len(features) != len(self.FEATURE_NAMES):
                raise ValueError(
                    f"Feature vector length mismatch: expected {len(self.FEATURE_NAMES)}, got {len(features)}"
                )
            vector = [float(val) for val in features]
        elif isinstance(features, np.ndarray):
            if features.size != len(self.FEATURE_NAMES):
                raise ValueError(
                    f"Numpy array size mismatch: expected {len(self.FEATURE_NAMES)}, got {features.size}"
                )
            vector = features.flatten().astype(np.float64).tolist()
        else:
            raise ValueError(f"Unsupported features type: {type(features)}")

        feature_matrix = np.array([vector], dtype=np.float64)
        raw_pred = float(self._model.predict(feature_matrix)[0])
        clamped_pred = max(0.0, min(1.0, raw_pred))

        return TrafficPrediction(
            predicted_congestion_index=round(clamped_pred, 4),
            model_type="RandomForestRegressor",
            target_name=self.TARGET_NAME,
        )

    def predict_observation(
        self,
        observation: TrafficObservation,
        speed_limit: Optional[float] = None,
    ) -> TrafficPrediction:
        """Predict next-step congestion index directly from a TrafficObservation."""
        limit = speed_limit if speed_limit is not None else self.speed_limit
        vector = TrafficDatasetBuilder.extract_observation_features(observation, speed_limit=limit)
        return self.predict(vector)

    def save_model(self, path: Union[str, Path]) -> None:
        """Save trained model and metadata to disk using joblib.

        Args:
            path: Destination file path.

        Raises:
            RuntimeError: If joblib is unavailable.
            ValueError: If model is untrained.
        """
        if joblib is None:
            raise RuntimeError("Model persistence requires 'joblib', which is not available.")
        if self._model is None:
            raise ValueError("Cannot save an untrained model. Call train() first.")

        target = Path(path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "model": self._model,
            "speed_limit": self.speed_limit,
            "feature_names": self.FEATURE_NAMES,
            "target_name": self.TARGET_NAME,
            "training_metadata": (
                self._training_metadata.model_dump() if self._training_metadata else None
            ),
        }
        joblib.dump(payload, str(target))

    def load_model(self, path: Union[str, Path]) -> None:
        """Load a trained model and metadata from disk using joblib.

        Args:
            path: Source file path.

        Raises:
            RuntimeError: If joblib is unavailable.
            FileNotFoundError: If path does not exist.
        """
        if joblib is None:
            raise RuntimeError("Model persistence requires 'joblib', which is not available.")

        target = Path(path).resolve()
        if not target.exists():
            raise FileNotFoundError(f"Model file not found at '{target}'")

        payload = joblib.load(str(target))
        self._model = payload["model"]
        self.speed_limit = payload.get("speed_limit", self.DEFAULT_SPEED_LIMIT)
        meta = payload.get("training_metadata")
        if meta:
            self._training_metadata = TrafficModelTrainingResult.model_validate(meta)
