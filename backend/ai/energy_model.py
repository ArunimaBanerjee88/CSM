"""Energy Demand Prediction Model Module for Quantum City.

Supervised machine learning model for forecasting the next-step city energy demand (MW)
from current energy state and coupled urban mobility features (active vehicles, traffic congestion),
using scikit-learn RandomForestRegressor. Supports observation sequences as well as direct loading
and validation from real energy CSV datasets.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

try:
    import joblib
except ImportError:
    joblib = None

from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split


class EnergyObservation(BaseModel):
    """Snapshot of city energy and coupled mobility state at a given timestep."""
    model_config = ConfigDict(extra="ignore")

    simulation_time: float = Field(description="Simulation time in seconds", ge=0.0)
    energy_demand_mw: float = Field(description="Current total energy demand in megawatts (MW)", ge=0.0)
    renewable_percentage: float = Field(
        default=0.25,
        description="Share of energy from renewable sources [0.0, 1.0]",
        ge=0.0,
        le=1.0,
    )
    active_vehicle_count: int = Field(
        default=0,
        description="Coupled active vehicle count on the road network",
        ge=0,
    )
    congestion_index: float = Field(
        default=0.0,
        description="Coupled traffic congestion index [0.0, 1.0]",
        ge=0.0,
        le=1.0,
    )
    next_step_demand_mw: Optional[float] = Field(
        default=None,
        description="Target next-step energy demand in MW if recorded in dataset",
        ge=0.0,
    )


class EnergyModelTrainingResult(BaseModel):
    """Structured summary returned upon successful energy model training."""
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    model_type: str = Field(default="RandomForestRegressor", description="Machine learning algorithm name")
    number_of_training_samples: int = Field(description="Total supervised transition pairs (t -> t+1)")
    number_of_features: int = Field(description="Number of input features per sample")
    feature_names: List[str] = Field(description="Ordered list of feature names used for training")
    target_name: str = Field(description="Target forecast variable name")
    training_completed: bool = Field(default=True, description="Whether training completed successfully")


class EnergyModelEvaluation(BaseModel):
    """Holdout test evaluation metrics for the energy prediction model."""
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    mae: float = Field(description="Mean Absolute Error on holdout test set in MW")
    rmse: float = Field(description="Root Mean Squared Error on holdout test set in MW")
    r2: float = Field(description="R-squared coefficient of determination on holdout test set")
    test_samples: int = Field(description="Number of holdout test samples evaluated")


class EnergyPrediction(BaseModel):
    """Result of next-step energy demand forecast."""
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    predicted_energy_demand_mw: float = Field(description="Forecasted energy demand for step t+1 in MW (>= 0.0)")
    model_type: str = Field(default="RandomForestRegressor", description="Algorithm used")
    target_name: str = Field(default="next_step_energy_demand", description="Target variable name")


class EnergyDatasetBuilder:
    """Extracts supervised transition pairs (X_t -> y_{t+1}) from energy time-series and CSVs."""

    FEATURE_NAMES: List[str] = [
        "current_energy_demand",
        "simulation_time",
        "renewable_energy_percentage",
        "active_vehicle_count",
        "traffic_congestion_index",
    ]
    TARGET_NAME: str = "next_step_energy_demand"

    @classmethod
    def extract_features(cls, obs: EnergyObservation) -> List[float]:
        """Convert an EnergyObservation into the canonical feature vector."""
        return [
            float(obs.energy_demand_mw),
            float(obs.simulation_time),
            float(obs.renewable_percentage),
            float(obs.active_vehicle_count),
            float(obs.congestion_index),
        ]

    @classmethod
    def load_from_csv(
        cls,
        csv_path: Union[str, Path],
    ) -> List[EnergyObservation]:
        """Load real energy time-series dataset from a CSV file into EnergyObservation models.

        Validates:
          - File existence
          - Missing/null values
          - Timestamp ordering (strictly monotonic increasing without duplicates)
          - Numeric ranges (demand >= 0, percentages in [0, 100], vehicles >= 0)
          - Target alignment (next_step_demand_mw[t] == current_demand_mw[t+1])

        Maps:
          - current_demand_mw -> energy_demand_mw
          - renewable_share_pct / 100 -> renewable_percentage
          - active_vehicles_count -> active_vehicle_count
          - traffic_congestion_pct / 100 -> congestion_index
          - timestamp -> simulation_time starting at 0.0 seconds

        Args:
            csv_path: Path to the CSV dataset file.

        Returns:
            List of validated EnergyObservation objects.

        Raises:
            FileNotFoundError: If the CSV file does not exist.
            ValueError: If validation fails on ordering, nulls, ranges, or target alignment.
        """
        path = Path(csv_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Energy dataset CSV not found at '{path}'")

        df = pd.read_csv(str(path))

        required_cols = [
            "timestamp",
            "current_demand_mw",
            "renewable_share_pct",
            "traffic_congestion_pct",
            "active_vehicles_count",
        ]
        missing_cols = [c for c in required_cols if c not in df.columns]
        if missing_cols:
            raise ValueError(f"CSV is missing required columns: {missing_cols}. Found: {df.columns.tolist()}")

        # 1. Missing values check
        if df[required_cols].isnull().any().any():
            raise ValueError("CSV contains missing or null values in required columns.")

        # 2. Timestamp ordering validation
        timestamps = pd.to_datetime(df["timestamp"])
        if not timestamps.is_monotonic_increasing:
            raise ValueError("Timestamps in CSV must be strictly monotonically increasing.")
        if timestamps.duplicated().any():
            raise ValueError("Duplicate timestamps found in CSV dataset.")

        # 3. Numeric range validation
        if (df["current_demand_mw"] < 0.0).any():
            raise ValueError("current_demand_mw contains invalid negative values (must be >= 0.0).")
        if (df["renewable_share_pct"] < 0.0).any() or (df["renewable_share_pct"] > 100.0).any():
            raise ValueError("renewable_share_pct must be between 0.0 and 100.0 percent.")
        if (df["traffic_congestion_pct"] < 0.0).any() or (df["traffic_congestion_pct"] > 100.0).any():
            raise ValueError("traffic_congestion_pct must be between 0.0 and 100.0 percent.")
        if (df["active_vehicles_count"] < 0).any():
            raise ValueError("active_vehicles_count contains negative counts (must be >= 0).")

        has_next_step = "next_step_demand_mw" in df.columns
        if has_next_step:
            if df["next_step_demand_mw"].isnull().any():
                raise ValueError("next_step_demand_mw column contains missing/null values.")
            if (df["next_step_demand_mw"] < 0.0).any():
                raise ValueError("next_step_demand_mw contains negative values (must be >= 0.0).")

            # 4. Target alignment validation across sequential steps
            diff = np.abs(df["next_step_demand_mw"].iloc[:-1].values - df["current_demand_mw"].iloc[1:].values)
            if len(diff) > 0 and np.max(diff) > 0.01:
                mismatch_idx = int(np.argmax(diff > 0.01))
                raise ValueError(
                    f"Target alignment mismatch at row {mismatch_idx}: "
                    f"next_step_demand_mw ({df['next_step_demand_mw'].iloc[mismatch_idx]}) "
                    f"!= subsequent current_demand_mw ({df['current_demand_mw'].iloc[mismatch_idx + 1]})"
                )

        # 5. Derive simulation_time starting at 0.0 seconds
        ts_0 = timestamps.iloc[0]
        simulation_times = (timestamps - ts_0).dt.total_seconds().values

        observations: List[EnergyObservation] = []
        demands = df["current_demand_mw"].values
        renewables = (df["renewable_share_pct"] / 100.0).values
        vehicles = df["active_vehicles_count"].values
        congestions = (df["traffic_congestion_pct"] / 100.0).values
        next_demands = df["next_step_demand_mw"].values if has_next_step else [None] * len(df)

        for i in range(len(df)):
            observations.append(
                EnergyObservation(
                    simulation_time=float(simulation_times[i]),
                    energy_demand_mw=float(demands[i]),
                    renewable_percentage=float(renewables[i]),
                    active_vehicle_count=int(vehicles[i]),
                    congestion_index=float(congestions[i]),
                    next_step_demand_mw=float(next_demands[i]) if has_next_step else None,
                )
            )

        return observations

    @classmethod
    def build_dataset(
        cls,
        runs: Union[Sequence[EnergyObservation], Sequence[Sequence[EnergyObservation]]],
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Convert one or multiple energy simulation runs into supervised (X, y) matrices.

        When next_step_demand_mw is present:
          - Uses next_step_demand_mw as the target for each observation.
          - Validates target alignment: obs[t].next_step_demand_mw == obs[t+1].energy_demand_mw.
        When next_step_demand_mw is not present:
          - Preserves existing sequential X_t -> y_{t+1} behavior across observation pairs.
          - Excludes the final observation of each sequence (no t+1 target).

        Args:
            runs: Either a single sequence of EnergyObservation, or multiple sequences.

        Returns:
            Tuple of (X, y) as numpy arrays.

        Raises:
            ValueError: If insufficient observations are provided or target alignment fails.
        """
        if not runs:
            raise ValueError("No energy observations provided to build dataset.")

        # Normalize to list of sequences
        if isinstance(runs[0], EnergyObservation):
            run_list: List[Sequence[EnergyObservation]] = [runs]  # type: ignore
        else:
            run_list = list(runs)  # type: ignore

        all_x: List[List[float]] = []
        all_y: List[float] = []

        for seq in run_list:
            n = len(seq)
            if n < 2:
                continue

            for t in range(n):
                obs_curr = seq[t]

                if obs_curr.next_step_demand_mw is not None:
                    # Validate target alignment with next observation if not at sequence end
                    if t < n - 1:
                        if abs(obs_curr.next_step_demand_mw - seq[t + 1].energy_demand_mw) > 0.01:
                            raise ValueError(
                                f"Target alignment mismatch at step {t}: "
                                f"next_step_demand_mw={obs_curr.next_step_demand_mw} != "
                                f"subsequent energy_demand_mw={seq[t+1].energy_demand_mw}"
                            )
                    x_t = cls.extract_features(obs_curr)
                    y_t = float(obs_curr.next_step_demand_mw)
                    all_x.append(x_t)
                    all_y.append(y_t)
                elif t < n - 1:
                    # Fallback to sequential next observation
                    x_t = cls.extract_features(obs_curr)
                    y_t = float(seq[t + 1].energy_demand_mw)
                    all_x.append(x_t)
                    all_y.append(y_t)

        if not all_x:
            raise ValueError(
                "Insufficient energy observation data. At least one sequence "
                "with 2 or more sequential timesteps is required."
            )

        return np.array(all_x, dtype=np.float64), np.array(all_y, dtype=np.float64)


class EnergyPredictionModel:
    """Supervised Random Forest Regressor for forecasting next-step energy demand (MW)."""

    FEATURE_NAMES: List[str] = EnergyDatasetBuilder.FEATURE_NAMES
    TARGET_NAME: str = EnergyDatasetBuilder.TARGET_NAME

    def __init__(
        self,
        n_estimators: int = 200,
        random_state: int = 42,
        n_jobs: int = -1,
    ) -> None:
        """Initialize the energy prediction model.

        Args:
            n_estimators: Number of decision trees in the random forest.
            random_state: Seed for deterministic model training.
            n_jobs: CPU cores to utilize (-1 = all cores).
        """
        self.n_estimators = n_estimators
        self.random_state = random_state
        self.n_jobs = n_jobs

        self._model: Optional[RandomForestRegressor] = None
        self._training_metadata: Optional[EnergyModelTrainingResult] = None

    def is_trained(self) -> bool:
        """Check whether the model has been trained or loaded."""
        return self._model is not None

    def get_feature_names(self) -> List[str]:
        """Return the canonical ordered list of feature names."""
        return list(self.FEATURE_NAMES)

    def train(
        self,
        runs: Union[Sequence[EnergyObservation], Sequence[Sequence[EnergyObservation]]],
    ) -> EnergyModelTrainingResult:
        """Train the energy model from one or multiple observation sequences.

        Args:
            runs: Energy observation run or list of runs.

        Returns:
            EnergyModelTrainingResult containing training metadata.

        Raises:
            ValueError: If input data is insufficient.
        """
        x_data, y_data = EnergyDatasetBuilder.build_dataset(runs)
        return self.train_from_arrays(x_data, y_data)

    def train_from_csv(
        self,
        csv_path: Union[str, Path],
    ) -> EnergyModelTrainingResult:
        """Load dataset from CSV file, validate, and train the model."""
        observations = EnergyDatasetBuilder.load_from_csv(csv_path)
        return self.train(observations)

    def train_from_arrays(self, x_data: np.ndarray, y_data: np.ndarray) -> EnergyModelTrainingResult:
        """Train directly from pre-built numpy arrays."""
        if len(x_data) == 0 or len(y_data) == 0:
            raise ValueError("Training arrays must not be empty.")
        if len(x_data) != len(y_data):
            raise ValueError(f"Length mismatch: X has {len(x_data)} samples, y has {len(y_data)} samples.")
        if x_data.shape[1] != len(self.FEATURE_NAMES):
            raise ValueError(f"Feature count mismatch: expected {len(self.FEATURE_NAMES)}, got {x_data.shape[1]}")

        regressor = RandomForestRegressor(
            n_estimators=self.n_estimators,
            random_state=self.random_state,
            n_jobs=self.n_jobs,
        )
        regressor.fit(x_data, y_data)

        self._model = regressor
        self._training_metadata = EnergyModelTrainingResult(
            model_type="RandomForestRegressor",
            number_of_training_samples=len(x_data),
            number_of_features=len(self.FEATURE_NAMES),
            feature_names=list(self.FEATURE_NAMES),
            target_name=self.TARGET_NAME,
            training_completed=True,
        )
        return self._training_metadata

    def evaluate(
        self,
        runs: Union[Sequence[EnergyObservation], Sequence[Sequence[EnergyObservation]]],
        test_size: float = 0.2,
        random_state: int = 42,
        min_samples_for_split: int = 10,
    ) -> EnergyModelEvaluation:
        """Evaluate next-step energy demand forecasting on a holdout test split.

        Args:
            runs: Energy observation sequences.
            test_size: Holdout fraction for testing (default 0.2).
            random_state: Split seed for deterministic evaluation.
            min_samples_for_split: Minimum sample threshold required for a valid split.

        Returns:
            EnergyModelEvaluation with MAE, RMSE, and R2 on holdout samples.

        Raises:
            ValueError: If sample count is insufficient for a valid split.
        """
        x_data, y_data = EnergyDatasetBuilder.build_dataset(runs)
        total_samples = len(x_data)
        if total_samples < min_samples_for_split:
            raise ValueError(
                f"Insufficient transition samples ({total_samples}) for holdout evaluation. "
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
        # Energy demand is non-negative
        y_pred_clamped = np.maximum(y_pred, 0.0)

        mae = float(mean_absolute_error(y_test, y_pred_clamped))
        rmse = float(np.sqrt(mean_squared_error(y_test, y_pred_clamped)))
        r2 = float(r2_score(y_test, y_pred_clamped))

        return EnergyModelEvaluation(
            mae=round(mae, 4),
            rmse=round(rmse, 4),
            r2=round(r2, 4),
            test_samples=len(y_test),
        )

    def evaluate_from_csv(
        self,
        csv_path: Union[str, Path],
        test_size: float = 0.2,
        random_state: int = 42,
    ) -> EnergyModelEvaluation:
        """Load dataset from CSV file, validate, and evaluate on holdout test set."""
        observations = EnergyDatasetBuilder.load_from_csv(csv_path)
        return self.evaluate(observations, test_size=test_size, random_state=random_state)

    def predict(
        self,
        features: Union[Dict[str, float], List[float], np.ndarray, EnergyObservation],
    ) -> EnergyPrediction:
        """Forecast the next-step energy demand (MW).

        Args:
            features: EnergyObservation instance, dictionary of feature -> value, or ordered vector.

        Returns:
            EnergyPrediction containing predicted_energy_demand_mw clamped to >= 0.0.

        Raises:
            ValueError: If model is untrained or features are missing/invalid.
        """
        if self._model is None:
            raise ValueError("EnergyPredictionModel is not trained. Call train() or load_model() first.")

        if isinstance(features, EnergyObservation):
            vector = EnergyDatasetBuilder.extract_features(features)
        elif isinstance(features, dict):
            missing = [f for f in self.FEATURE_NAMES if f not in features]
            if missing:
                raise ValueError(f"Missing required energy features: {missing}")
            vector = [float(features[f]) for f in self.FEATURE_NAMES]
        elif isinstance(features, (list, tuple)):
            if len(features) != len(self.FEATURE_NAMES):
                raise ValueError(
                    f"Feature vector length mismatch: expected {len(self.FEATURE_NAMES)}, got {len(features)}"
                )
            vector = [float(v) for v in features]
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
        clamped_pred = max(0.0, raw_pred)

        return EnergyPrediction(
            predicted_energy_demand_mw=round(clamped_pred, 4),
            model_type="RandomForestRegressor",
            target_name=self.TARGET_NAME,
        )

    def save_model(self, path: Union[str, Path]) -> None:
        """Save the trained model and metadata to disk using joblib.

        Args:
            path: Target file path.
        """
        if joblib is None:
            raise RuntimeError("Model persistence requires 'joblib', which is not available.")
        if self._model is None:
            raise ValueError("Cannot save an untrained model. Call train() first.")

        target = Path(path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "model": self._model,
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
        """
        if joblib is None:
            raise RuntimeError("Model persistence requires 'joblib', which is not available.")

        target = Path(path).resolve()
        if not target.exists():
            raise FileNotFoundError(f"Model file not found at '{target}'")

        payload = joblib.load(str(target))
        self._model = payload["model"]
        meta = payload.get("training_metadata")
        if meta:
            self._training_metadata = EnergyModelTrainingResult.model_validate(meta)
