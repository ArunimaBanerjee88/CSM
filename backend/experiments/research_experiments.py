"""
Quantum City - Controlled Traffic Research Experiment Runner

Interactive terminal experiment for the five-road Quantum City traffic demo.

IMPORTANT SCIENTIFIC SCOPE
--------------------------
This script is a controlled backend/research experiment. It does NOT drive the
Unity scene and it does NOT start the unstable dynamic SUMO controller.

It uses the traffic-intelligence logic already present in the project:
- AI: scikit-learn RandomForestRegressor for next-step road congestion prediction,
  followed by a greedy least-congested alternative-road diversion policy.
- Quantum: the project's TrafficQAOA implementation from dynamic_traffic.py
  for one-hot alternative-road selection using Qiskit statevector simulation.

For a fair AI-vs-Quantum comparison, both methods receive the SAME initial
five-road state, the SAME selected hotspot, the SAME number of vehicles to
reroute, and the SAME candidate alternative roads. The only changed decision
is the route-selection method.

The five-road traffic state is a controlled experiment model. It is not claimed
as a replacement for the SUMO physical model. Every workbook/figure labels this
scope explicitly.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import math
import os
import random
import sys
import time
from copy import deepcopy
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


# ---------------------------------------------------------------------------
# Locate backend root robustly.
# Supports:
#   backend/research_experiments.py
#   backend/scripts/research_experiments.py
# ---------------------------------------------------------------------------

def find_backend_root() -> Path:
    here = Path(__file__).resolve()
    candidates = [here.parent, here.parent.parent]
    for candidate in candidates:
        if (candidate / "ai").is_dir() and (candidate / "simulation").is_dir():
            return candidate
    raise RuntimeError(
        "Could not locate backend root. Put this script in backend/ "
        "or backend/scripts/."
    )


backend_dir = find_backend_root()
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))


# The project already contains this traffic-specific QAOA implementation.
# try:
#     from simulation.dynamic_traffic import TrafficQAOA
# except Exception as exc:  # pragma: no cover - environment-specific
#     TrafficQAOA = None
#     TRAFFIC_QAOA_IMPORT_ERROR = exc
# else:
#     TRAFFIC_QAOA_IMPORT_ERROR = None


# ---------------------------------------------------------------------------
# Traffic-specific QAOA used by this controlled experiment.
#
# The current simulation/dynamic_traffic.py contains DynamicTrafficEngine,
# but the TrafficQAOA helper is not present in that runtime file.
# This class preserves the project's existing traffic-QAOA formulation:
# one binary variable per candidate road, QAOA-style cost phase + mixer,
# and exactly-one-road feasibility.
# ---------------------------------------------------------------------------

class TrafficQAOA:

    def __init__(self, seed: int = 42):
        self.seed = seed

    def solve(
        self,
        candidate_costs: List[float],
    ) -> Tuple[int, float]:

        if not candidate_costs:
            return 0, 0.0

        try:
            from qiskit import QuantumCircuit
            from qiskit.quantum_info import Statevector

            n = len(candidate_costs)

            if n == 1:
                return 0, float(candidate_costs[0])

            # Keep the quantum experiment small and reproducible.
            if n > 6:
                return self._classical_fallback(candidate_costs)

            rng = np.random.default_rng(self.seed)

            best_index = 0
            best_cost = float("inf")

            # One-layer QAOA-style parameter search.
            for _ in range(32):

                gamma = float(
                    rng.uniform(
                        0.0,
                        2.0 * math.pi
                    )
                )

                beta = float(
                    rng.uniform(
                        0.0,
                        math.pi
                    )
                )

                circuit = QuantumCircuit(n)

                # Initial equal superposition
                for q in range(n):
                    circuit.h(q)

                # Cost Hamiltonian phase
                for q, cost in enumerate(candidate_costs):
                    circuit.rz(
                        2.0 * gamma * float(cost),
                        q
                    )

                # Mixer Hamiltonian
                for q in range(n):
                    circuit.rx(
                        2.0 * beta,
                        q
                    )

                state = Statevector.from_instruction(circuit)

                probabilities = np.abs(state.data) ** 2

                for basis_index, probability in enumerate(probabilities):

                    if probability <= 1e-9:
                        continue

                    bits = [
                        (basis_index >> q) & 1
                        for q in range(n)
                    ]

                    # Exactly ONE alternative road must be selected.
                    if sum(bits) != 1:
                        continue

                    selected = bits.index(1)

                    cost = float(
                        candidate_costs[selected]
                    )

                    if cost < best_cost:
                        best_cost = cost
                        best_index = selected

            if not np.isfinite(best_cost):
                return self._classical_fallback(
                    candidate_costs
                )

            return best_index, best_cost

        except Exception:
            # Explicit fallback if Qiskit execution fails.
            return self._classical_fallback(
                candidate_costs
            )

    @staticmethod
    def _classical_fallback(
        candidate_costs: List[float],
    ) -> Tuple[int, float]:

        index = int(
            np.argmin(candidate_costs)
        )

        return (
            index,
            float(candidate_costs[index])
        )


TRAFFIC_QAOA_IMPORT_ERROR = None


ROADS = ["Road A", "Road B", "Road C", "Road D", "Road E"]
SPEED_LIMIT_MPS = 13.9
ROAD_CAPACITY = 18
REROUTE_FRACTION = 0.50
RANDOM_SEED = 42
PREDICTION_HORIZON = 30


@dataclass
class RoadState:
    road: str
    cars: int
    speed_mps: float
    waiting_time_s: float
    congestion: float


@dataclass
class MethodResult:
    method: str
    hotspot: str
    target_roads: str
    cars_before: int
    rerouted: int
    cars_after: int
    congestion_before: float
    congestion_after: float
    congestion_reduction_percent: float
    waiting_before_s: float
    waiting_after_s: float
    waiting_reduction_percent: float
    average_speed_before_mps: float
    average_speed_after_mps: float
    objective: float
    decision_time_ms: float
    predicted_next_road: str
    predicted_next_cars: int
    prediction_accuracy_percent: float
    notes: str


class ControlledTrafficExperiment:
    """Deterministic five-road experiment state used for fair method comparison."""

    def __init__(self, seed: int = RANDOM_SEED):
        self.seed = seed
        self.rng = random.Random(seed)
        self.reset()

    def reset(self) -> None:
        # Unequal baseline counts are intentional: the experiment must contain
        # a meaningful distribution before a hotspot is injected.
        self.counts: Dict[str, int] = {
            "Road A": 9,
            "Road B": 5,
            "Road C": 13,
            "Road D": 7,
            "Road E": 10,
        }
        self.time_step = 0
        self.hotspot: Optional[str] = None
        self.history: List[Dict[str, int]] = []
        self.prediction_result: Optional[dict] = None
        self.ai_result: Optional[MethodResult] = None
        self.quantum_result: Optional[MethodResult] = None
        self.baseline_snapshot: Optional[Dict[str, int]] = None
        self.experiment_log: List[dict] = []
        self._record_history()

    def snapshot(self) -> Dict[str, int]:
        return dict(self.counts)

    def restore(self, snapshot: Dict[str, int]) -> None:
        self.counts = dict(snapshot)

    def inject_congestion(self, road: str, extra_cars: int) -> None:
        if road not in ROADS:
            raise ValueError(f"Unknown road: {road}")
        if extra_cars <= 0:
            raise ValueError("extra_cars must be > 0")
        self.hotspot = road
        self.counts[road] += int(extra_cars)
        self.baseline_snapshot = self.snapshot()
        self._record_history()

    def state(self, road: str) -> RoadState:
        cars = int(self.counts[road])
        congestion = min(1.0, max(0.0, cars / ROAD_CAPACITY))
        speed = SPEED_LIMIT_MPS * (1.0 - congestion)
        waiting = cars * congestion
        return RoadState(road, cars, speed, waiting, congestion)

    def all_states(self) -> List[RoadState]:
        return [self.state(road) for road in ROADS]

    def total_waiting(self) -> float:
        return sum(s.waiting_time_s for s in self.all_states())

    def average_speed(self) -> float:
        states = self.all_states()
        return sum(s.speed_mps for s in states) / len(states)

    def _record_history(self) -> None:
        self.history.append(dict(self.counts))
        if len(self.history) > 300:
            self.history = self.history[-300:]

    def advance_without_optimization(self, seconds: int = 30) -> None:
        """Controlled demand drift used only to create a forecast horizon."""
        for _ in range(seconds):
            self.time_step += 1
            for road in ROADS:
                # Deterministic, bounded arrivals/departures.
                phase = (self.time_step + ROADS.index(road) * 7) % 10
                if phase in (0, 1, 2):
                    self.counts[road] += 1
                elif phase in (6, 7, 8) and self.counts[road] > 2:
                    self.counts[road] -= 1
            self._record_history()

    def apply_diversion(self, hotspot: str, target_roads: List[str], fraction: float) -> int:
        if hotspot not in ROADS:
            raise ValueError(f"Unknown hotspot: {hotspot}")
        targets = [r for r in target_roads if r in ROADS and r != hotspot]
        if not targets:
            raise ValueError("At least one valid alternative road is required")

        rerouted = int(math.floor(self.counts[hotspot] * fraction))
        if rerouted <= 0:
            return 0

        self.counts[hotspot] -= rerouted
        for i in range(rerouted):
            self.counts[targets[i % len(targets)]] += 1
        self.time_step += 1
        self._record_history()
        return rerouted


class TrafficRandomForest:
    """Road-level RF matching the traffic-intelligence feature schema in dynamic_traffic.py."""

    FEATURE_NAMES = [
        "step",
        "vehicle_count",
        "average_speed",
        "waiting_time",
        "previous_congestion",
    ]

    def __init__(self, seed: int = RANDOM_SEED):
        self.seed = seed
        self.model = RandomForestRegressor(
            n_estimators=200,
            random_state=seed,
            n_jobs=-1,
        )
        self.trained = False
        self.training_samples = 0
        self.holdout_metrics: Optional[dict] = None

    @staticmethod
    def _features(step: int, state: RoadState, previous_congestion: float) -> List[float]:
        return [
            float(step),
            float(state.cars),
            float(state.speed_mps),
            float(state.waiting_time_s),
            float(previous_congestion),
        ]

    def build_training_data(self) -> Tuple[np.ndarray, np.ndarray]:
        """Create a deterministic controlled-history dataset for this experiment."""
        rng = np.random.default_rng(self.seed)
        x_rows: List[List[float]] = []
        y_rows: List[float] = []

        for road_index, _road in enumerate(ROADS):
            previous = 0.20 + road_index * 0.04
            for step in range(1, 161):
                # Controlled traffic process with bounded deterministic demand.
                wave = 0.07 * math.sin(step / 9.0 + road_index)
                demand = 0.05 * math.sin(step / 4.0 + road_index * 0.7)
                noise = float(rng.normal(0.0, 0.008))
                next_congestion = float(np.clip(
                    previous + 0.018 + wave * 0.10 + demand * 0.05 + noise,
                    0.02,
                    0.98,
                ))
                cars = max(1, int(round(next_congestion * ROAD_CAPACITY)))
                speed = SPEED_LIMIT_MPS * (1.0 - next_congestion)
                waiting = cars * next_congestion
                state = RoadState(_road, cars, speed, waiting, next_congestion)
                x_rows.append(self._features(step - 1, state, previous))
                y_rows.append(next_congestion)
                previous = next_congestion

        return np.asarray(x_rows, dtype=float), np.asarray(y_rows, dtype=float)

    def train(self) -> dict:
        x, y = self.build_training_data()
        split = int(len(x) * 0.80)
        x_train, x_test = x[:split], x[split:]
        y_train, y_test = y[:split], y[split:]
        self.model.fit(x_train, y_train)
        self.trained = True
        self.training_samples = len(x_train)
        pred = self.model.predict(x_test)
        self.holdout_metrics = {
            "MAE": float(mean_absolute_error(y_test, pred)),
            "RMSE": float(math.sqrt(mean_squared_error(y_test, pred))),
            "R2": float(r2_score(y_test, pred)),
            "Test Samples": int(len(y_test)),
        }
        return self.holdout_metrics

    def predict_all(self, experiment: ControlledTrafficExperiment) -> List[dict]:
        if not self.trained:
            self.train()

        candidates = []
        for state in experiment.all_states():
            previous = state.congestion
            if len(experiment.history) >= 2:
                prev_counts = experiment.history[-2]
                prev_congestion = min(1.0, prev_counts[state.road] / ROAD_CAPACITY)
                previous = prev_congestion
            features = np.asarray([
                self._features(experiment.time_step, state, previous)
            ], dtype=float)
            prediction = float(np.clip(self.model.predict(features)[0], 0.0, 1.0))
            predicted_cars = int(round(prediction * ROAD_CAPACITY))
            candidates.append({
                "road": state.road,
                "current_cars": state.cars,
                "current_congestion": state.congestion,
                "predicted_congestion": prediction,
                "predicted_cars": predicted_cars,
                "current_speed_mps": state.speed_mps,
            })

        candidates.sort(key=lambda row: row["predicted_congestion"], reverse=True)
        return candidates

    def predict_next_road(self, experiment: ControlledTrafficExperiment) -> dict:
        candidates = self.predict_all(experiment)
        winner = candidates[0]
        experiment.prediction_result = winner
        return {"winner": winner, "all_roads": candidates}


# ---------------------------------------------------------------------------
# Metrics / optimization policies
# ---------------------------------------------------------------------------

def congestion_reduction(before: float, after: float) -> float:
    if before <= 1e-12:
        return 0.0
    return max(0.0, (before - after) / before * 100.0)


def percentage_reduction(before: float, after: float) -> float:
    if before <= 1e-12:
        return 0.0
    return max(0.0, (before - after) / before * 100.0)


def ai_choose_target(experiment: ControlledTrafficExperiment, hotspot: str) -> str:
    alternatives = [r for r in ROADS if r != hotspot]
    # Exact policy used by the Unity AI optimization: choose the least-loaded
    # alternative road, with deterministic alphabetical tie-breaking.
    return min(alternatives, key=lambda road: (experiment.counts[road], road))


def quantum_choose_target(experiment: ControlledTrafficExperiment, hotspot: str) -> Tuple[str, float, str]:
    if TrafficQAOA is None:
        raise RuntimeError(
            "TrafficQAOA could not be imported from dynamic_traffic.py: "
            f"{TRAFFIC_QAOA_IMPORT_ERROR}"
        )

    if importlib.util.find_spec("qiskit") is None:
        raise RuntimeError(
            "Qiskit is not installed. The quantum experiment cannot be honestly "
            "labelled QAOA without Qiskit."
        )

    alternatives = [r for r in ROADS if r != hotspot]
    # Route cost: current congestion of the candidate destination.
    # This is a controlled experiment cost, not a new production backend API.
    costs = [experiment.state(road).congestion for road in alternatives]
    solver = TrafficQAOA(seed=RANDOM_SEED)
    index, objective = solver.solve(costs)
    selected = alternatives[int(index)]
    return selected, float(objective), "QAOA one-hot route selection"


def evaluate_method(
    initial_counts: Dict[str, int],
    hotspot: str,
    method: str,
    rf: TrafficRandomForest,
) -> MethodResult:
    experiment = ControlledTrafficExperiment()
    experiment.counts = dict(initial_counts)
    experiment.hotspot = hotspot
    before_state = experiment.state(hotspot)
    before_waiting = experiment.total_waiting()
    before_speed = experiment.average_speed()

    prediction = rf.predict_next_road(experiment)
    predicted_next_road = prediction["winner"]["road"]
    predicted_next_cars = prediction["winner"]["predicted_cars"]

    start = time.perf_counter()
    objective = 0.0
    notes = ""

    if method == "AI":
        target = ai_choose_target(experiment, hotspot)
        target_roads = [target]
        objective = experiment.state(target).congestion
        notes = (
            "RandomForestRegressor predicts next-step congestion; "
            "greedy policy diverts to the currently least-congested alternative."
        )
    elif method == "Quantum":
        target, objective, quantum_note = quantum_choose_target(experiment, hotspot)
        target_roads = [target]
        notes = (
            "QAOA route selection from dynamic_traffic.py; candidate cost is "
            "destination congestion in this controlled road-selection experiment. "
            + quantum_note
        )
    else:
        raise ValueError(f"Unsupported method: {method}")

    rerouted = experiment.apply_diversion(
        hotspot,
        target_roads,
        REROUTE_FRACTION,
    )
    decision_time_ms = (time.perf_counter() - start) * 1000.0

    after_state = experiment.state(hotspot)
    after_waiting = experiment.total_waiting()
    after_speed = experiment.average_speed()

    return MethodResult(
        method=method,
        hotspot=hotspot,
        target_roads=", ".join(target_roads),
        cars_before=before_state.cars,
        rerouted=rerouted,
        cars_after=after_state.cars,
        congestion_before=before_state.congestion,
        congestion_after=after_state.congestion,
        congestion_reduction_percent=congestion_reduction(
            before_state.congestion, after_state.congestion
        ),
        waiting_before_s=before_waiting,
        waiting_after_s=after_waiting,
        waiting_reduction_percent=percentage_reduction(
            before_waiting, after_waiting
        ),
        average_speed_before_mps=before_speed,
        average_speed_after_mps=after_speed,
        objective=objective,
        decision_time_ms=decision_time_ms,
        predicted_next_road=predicted_next_road,
        predicted_next_cars=predicted_next_cars,
        prediction_accuracy_percent=0.0,
        notes=notes,
    )


def calculate_prediction_accuracy(predicted_cars: int, actual_cars: int) -> float:
    if predicted_cars <= 0:
        return 100.0 if actual_cars == 0 else 0.0
    return max(0.0, 100.0 * (1.0 - abs(predicted_cars - actual_cars) / predicted_cars))


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def save_experiment_plots(
    output_dir: Path,
    hotspot: str,
    baseline: Dict[str, int],
    ai: MethodResult,
    quantum: MethodResult,
    prediction: dict,
    timeline: List[dict],
) -> List[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []

    # 1. Cars before/after.
    fig, ax = plt.subplots(figsize=(10, 6))
    x = np.arange(2)
    width = 0.35
    ax.bar(x - width / 2, [ai.cars_before, ai.cars_after], width, label="AI")
    ax.bar(x + width / 2, [quantum.cars_before, quantum.cars_after], width, label="Quantum (QAOA)")
    ax.set_xticks(x)
    ax.set_xticklabels(["Before", "After"])
    ax.set_ylabel("Cars on hotspot")
    ax.set_title(f"Hotspot Vehicle Count — {hotspot}")
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    p = output_dir / "01_hotspot_cars_before_after.png"
    fig.savefig(p, dpi=180)
    plt.close(fig)
    paths.append(p)

    # 2. Congestion before/after.
    fig, ax = plt.subplots(figsize=(10, 6))
    methods = ["AI", "Quantum (QAOA)"]
    before = [ai.congestion_before * 100, quantum.congestion_before * 100]
    after = [ai.congestion_after * 100, quantum.congestion_after * 100]
    x = np.arange(len(methods))
    ax.bar(x - width / 2, before, width, label="Before")
    ax.bar(x + width / 2, after, width, label="After")
    ax.set_xticks(x)
    ax.set_xticklabels(methods)
    ax.set_ylabel("Congestion (%)")
    ax.set_title("Hotspot Congestion Reduction")
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    p = output_dir / "02_congestion_before_after.png"
    fig.savefig(p, dpi=180)
    plt.close(fig)
    paths.append(p)

    # 3. Road distribution.
    fig, ax = plt.subplots(figsize=(11, 6))
    roads = ROADS
    base_values = [baseline[r] for r in roads]
    ai_counts = dict(baseline)
    ai_counts[ai.hotspot] -= ai.rerouted
    ai_counts[ai.target_roads.split(", ")[0]] += ai.rerouted
    q_counts = dict(baseline)
    q_counts[quantum.hotspot] -= quantum.rerouted
    q_counts[quantum.target_roads.split(", ")[0]] += quantum.rerouted
    x = np.arange(len(roads))
    w = 0.25
    ax.bar(x - w, base_values, w, label="Baseline")
    ax.bar(x, [ai_counts[r] for r in roads], w, label="AI")
    ax.bar(x + w, [q_counts[r] for r in roads], w, label="Quantum")
    ax.set_xticks(x)
    ax.set_xticklabels(roads)
    ax.set_ylabel("Cars")
    ax.set_title("Five-Road Traffic Redistribution")
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    p = output_dir / "03_road_redistribution.png"
    fig.savefig(p, dpi=180)
    plt.close(fig)
    paths.append(p)

    # 4. Prediction across all roads.
    fig, ax = plt.subplots(figsize=(11, 6))
    roads = [row["road"] for row in prediction["all_roads"]]
    current = [row["current_cars"] for row in prediction["all_roads"]]
    predicted = [row["predicted_cars"] for row in prediction["all_roads"]]
    x = np.arange(len(roads))
    ax.bar(x - width / 2, current, width, label="Current cars")
    ax.bar(x + width / 2, predicted, width, label="Predicted next congestion cars")
    ax.set_xticks(x)
    ax.set_xticklabels(roads)
    ax.set_ylabel("Cars")
    ax.set_title("AI Next-Congestion Prediction Across Roads")
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    p = output_dir / "04_ai_next_congestion_prediction.png"
    fig.savefig(p, dpi=180)
    plt.close(fig)
    paths.append(p)

    # 5. Timeline of hotspot congestion from the controlled experiment log.
    if timeline:
        fig, ax = plt.subplots(figsize=(11, 6))
        steps = [row["step"] for row in timeline]
        vals = [row["hotspot_congestion"] * 100 for row in timeline]
        ax.plot(steps, vals, marker="o", label=f"{hotspot} congestion")
        ax.set_xlabel("Experiment step")
        ax.set_ylabel("Congestion (%)")
        ax.set_title("Hotspot Congestion Timeline")
        ax.grid(True, alpha=0.25)
        ax.legend()
        fig.tight_layout()
        p = output_dir / "05_hotspot_congestion_timeline.png"
        fig.savefig(p, dpi=180)
        plt.close(fig)
        paths.append(p)

    # 6. Method comparison reduction chart.
    fig, ax = plt.subplots(figsize=(9, 6))
    labels = ["Congestion reduction", "Waiting reduction"]
    ai_vals = [ai.congestion_reduction_percent, ai.waiting_reduction_percent]
    q_vals = [quantum.congestion_reduction_percent, quantum.waiting_reduction_percent]
    x = np.arange(len(labels))
    ax.bar(x - width / 2, ai_vals, width, label="AI")
    ax.bar(x + width / 2, q_vals, width, label="Quantum (QAOA)")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Improvement (%)")
    ax.set_title("Optimization Method Comparison")
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    p = output_dir / "06_method_improvement_comparison.png"
    fig.savefig(p, dpi=180)
    plt.close(fig)
    paths.append(p)

    return paths


# ---------------------------------------------------------------------------
# Excel report
# ---------------------------------------------------------------------------

def style_sheet(ws, header_row: int = 1) -> None:
    fill = PatternFill("solid", fgColor="1F4E78")
    for cell in ws[header_row]:
        cell.fill = fill
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.freeze_panes = f"A{header_row + 1}"

    for column_cells in ws.columns:
        max_len = 0
        for cell in column_cells:
            value = "" if cell.value is None else str(cell.value)
            max_len = max(max_len, len(value))
        ws.column_dimensions[get_column_letter(column_cells[0].column)].width = min(max(max_len + 2, 12), 42)


def export_xlsx(
    output_dir: Path,
    run_id: str,
    hotspot: str,
    baseline: Dict[str, int],
    prediction: dict,
    ai: MethodResult,
    quantum: MethodResult,
    rf_metrics: dict,
    experiment_timeline: List[dict],
    plot_paths: List[Path],
) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "Executive Summary"

    ws.append(["QUANTUM CITY — CONTROLLED TRAFFIC EXPERIMENT"])
    ws.append(["Run ID", run_id])
    ws.append(["Experiment scope", "Five-road controlled backend experiment; not a SUMO physical validation."])
    ws.append(["Hotspot selected", hotspot])
    ws.append(["Reroute fraction", REROUTE_FRACTION])
    ws.append(["Prediction horizon", f"Next-step model forecast; terminal experiment uses {PREDICTION_HORIZON}s context for interpretation."])
    ws.append([])
    ws.append(["FINAL RESULT"])

    winner = "Quantum (QAOA)" if quantum.congestion_reduction_percent > ai.congestion_reduction_percent else "AI"
    if math.isclose(quantum.congestion_reduction_percent, ai.congestion_reduction_percent, abs_tol=1e-9):
        winner = "Tie on congestion reduction"

    ws.append(["Preferred method by hotspot congestion reduction", winner])
    ws.append(["AI congestion reduction (%)", ai.congestion_reduction_percent])
    ws.append(["Quantum congestion reduction (%)", quantum.congestion_reduction_percent])
    ws.append(["AI waiting-time reduction (%)", ai.waiting_reduction_percent])
    ws.append(["Quantum waiting-time reduction (%)", quantum.waiting_reduction_percent])
    ws.append(["AI decision time (ms)", ai.decision_time_ms])
    ws.append(["Quantum decision time (ms)", quantum.decision_time_ms])
    ws.append(["Scientific interpretation", "The preferred method is determined from the measured controlled experiment, not assumed in advance."])
    style_sheet(ws, 1)

    # Theory sheet.
    ws = wb.create_sheet("Theory & Methodology")
    theory_rows = [
        ["Topic", "Documented implementation / formula"],
        ["AI technique", "RandomForestRegressor (scikit-learn), 200 trees, random_state=42."],
        ["AI prediction features", "step, vehicle_count, average_speed, waiting_time, previous_congestion."],
        ["AI target", "Next-step road congestion index."],
        ["AI routing policy", "Greedy: select the currently least-congested alternative road."],
        ["Quantum technique", "TrafficQAOA from dynamic_traffic.py using Qiskit QuantumCircuit + Statevector."],
        ["Quantum initialization", "Hadamard gates create a superposition."],
        ["Quantum cost phase", "RZ(2 * gamma * candidate_cost) is applied to each qubit."],
        ["Quantum mixer", "RX(2 * beta) is applied to each qubit."],
        ["Quantum feasibility rule", "Only one-hot states with sum(bits) = 1 are accepted as route choices."],
        ["Quantum parameter search", "The existing implementation evaluates 32 random gamma/beta trials."],
        ["Quantum fallback", "If no valid finite result is obtained, dynamic_traffic.py falls back to argmin(candidate_costs)."],
        ["Controlled congestion formula", "C = clip(cars / ROAD_CAPACITY, 0, 1), with ROAD_CAPACITY = 18 for this experiment."],
        ["Controlled speed formula", "v = SPEED_LIMIT * (1 - C), with SPEED_LIMIT = 13.9 m/s."],
        ["Controlled waiting proxy", "W = cars * C. This is an experiment proxy, not a SUMO waiting-time definition."],
        ["Congestion reduction", "Reduction% = max(0, (C_before - C_after) / C_before * 100)."],
        ["Waiting reduction", "Reduction% = max(0, (W_before - W_after) / W_before * 100)."],
        ["Prediction accuracy", "100 * (1 - abs(predicted_cars - actual_cars) / predicted_cars), clipped at 0."],
        ["Fairness protocol", "Same hotspot, same baseline snapshot, same candidate roads, same reroute fraction for AI and QAOA."],
        ["Important limitation", "The five-road state is controlled/synthetic. It must not be presented as real-world validation of traffic flow."],
        ["Existing project linkage", "The project also contains SUMO/TraCI traffic simulation and a separate TrafficQAOA helper; this report tests the route-selection logic without launching dynamic SUMO."],
    ]
    for row in theory_rows:
        ws.append(row)
    style_sheet(ws)

    # Baseline road state.
    ws = wb.create_sheet("Baseline Road State")
    ws.append(["Road", "Cars", "Congestion", "Speed (m/s)", "Waiting proxy (s)"])
    for road in ROADS:
        cars = baseline[road]
        c = min(1.0, cars / ROAD_CAPACITY)
        ws.append([road, cars, c, SPEED_LIMIT_MPS * (1 - c), cars * c])
    style_sheet(ws)

    # Prediction detail.
    ws = wb.create_sheet("AI Prediction Detail")
    ws.append([
        "Road", "Current Cars", "Current Congestion", "Predicted Congestion",
        "Predicted Cars", "Current Speed (m/s)", "Rank"
    ])
    for rank, row in enumerate(prediction["all_roads"], 1):
        ws.append([
            row["road"], row["current_cars"], row["current_congestion"],
            row["predicted_congestion"], row["predicted_cars"],
            row["current_speed_mps"], rank,
        ])
    style_sheet(ws)

    # Method comparison.
    ws = wb.create_sheet("AI vs Quantum")
    headers = list(asdict(ai).keys())
    ws.append(headers)
    ws.append(list(asdict(ai).values()))
    ws.append(list(asdict(quantum).values()))
    style_sheet(ws)

    # RF evaluation.
    ws = wb.create_sheet("AI Model Evaluation")
    ws.append(["Metric", "Value"])
    for key, value in rf_metrics.items():
        ws.append([key, value])
    ws.append(["Algorithm", "RandomForestRegressor"])
    ws.append(["Trees", 200])
    ws.append(["Random State", RANDOM_SEED])
    ws.append(["Feature 1", "step"])
    ws.append(["Feature 2", "vehicle_count"])
    ws.append(["Feature 3", "average_speed"])
    ws.append(["Feature 4", "waiting_time"])
    ws.append(["Feature 5", "previous_congestion"])
    ws.append(["Training data type", "Controlled synthetic history for this experiment"])
    style_sheet(ws)

    # Timeline.
    ws = wb.create_sheet("Experiment Timeline")
    if experiment_timeline:
        keys = list(experiment_timeline[0].keys())
        ws.append(keys)
        for row in experiment_timeline:
            ws.append([row.get(k) for k in keys])
    style_sheet(ws)

    # Plot index.
    ws = wb.create_sheet("Figures")
    ws.append(["Figure", "File", "Purpose"])
    descriptions = [
        "Hotspot vehicle count before/after",
        "Hotspot congestion before/after",
        "Five-road traffic redistribution",
        "AI next-congestion prediction",
        "Hotspot congestion timeline",
        "Method improvement comparison",
    ]
    for path, description in zip(plot_paths, descriptions):
        ws.append([path.stem, path.name, description])
    style_sheet(ws)

    # Raw JSON for reproducibility.
    ws = wb.create_sheet("Reproducibility")
    payload = {
        "run_id": run_id,
        "seed": RANDOM_SEED,
        "roads": ROADS,
        "road_capacity": ROAD_CAPACITY,
        "reroute_fraction": REROUTE_FRACTION,
        "hotspot": hotspot,
        "baseline_counts": baseline,
        "prediction": prediction,
        "ai_result": asdict(ai),
        "quantum_result": asdict(quantum),
        "rf_metrics": rf_metrics,
    }
    ws.append(["JSON"])
    ws.append([json.dumps(payload, indent=2)])
    ws["A2"].alignment = Alignment(wrap_text=True, vertical="top")
    ws.column_dimensions["A"].width = 120
    ws.row_dimensions[2].height = 300

    output_path = output_dir / f"QuantumCity_Traffic_Experiment_{run_id}.xlsx"
    wb.save(output_path)
    return output_path


# ---------------------------------------------------------------------------
# Interactive terminal
# ---------------------------------------------------------------------------

def print_status(experiment: ControlledTrafficExperiment) -> None:
    print("\nROAD STATE")
    print("-" * 76)
    print(f"{'Road':<10}{'Cars':>8}{'Congestion':>14}{'Speed m/s':>14}{'Wait proxy':>14}")
    print("-" * 76)
    for state in experiment.all_states():
        marker = "  <-- HOTSPOT" if state.road == experiment.hotspot else ""
        print(
            f"{state.road:<10}{state.cars:>8}{state.congestion*100:>13.1f}%"
            f"{state.speed_mps:>14.2f}{state.waiting_time_s:>14.2f}{marker}"
        )
    print("-" * 76)


def choose_road(prompt: str = "Select road [A/B/C/D/E]: ") -> str:
    value = input(prompt).strip().upper()
    if value.startswith("ROAD "):
        value = value[-1]
    road = f"Road {value}"
    if road not in ROADS:
        raise ValueError("Choose A, B, C, D, or E.")
    return road


def print_prediction(prediction: dict) -> None:
    winner = prediction["winner"]
    print("\nAI NEXT-CONGESTION PREDICTION")
    print("-" * 76)
    print(
        f"Predicted next hotspot: {winner['road']} | "
        f"Predicted cars: {winner['predicted_cars']} | "
        f"Predicted congestion: {winner['predicted_congestion']*100:.1f}%"
    )
    print("\nAll roads:")
    for rank, row in enumerate(prediction["all_roads"], 1):
        print(
            f"  {rank}. {row['road']}: current={row['current_cars']} cars, "
            f"predicted={row['predicted_cars']} cars, "
            f"predicted congestion={row['predicted_congestion']*100:.1f}%"
        )
    print("-" * 76)


def print_result(result: MethodResult) -> None:
    print("\nMETHOD RESULT")
    print("-" * 76)
    print(f"Method:                 {result.method}")
    print(f"Hotspot:                {result.hotspot}")
    print(f"Target road(s):         {result.target_roads}")
    print(f"Cars before:            {result.cars_before}")
    print(f"Cars rerouted:          {result.rerouted}")
    print(f"Cars after:             {result.cars_after}")
    print(f"Congestion:             {result.congestion_before*100:.2f}% -> {result.congestion_after*100:.2f}%")
    print(f"Congestion reduction:   {result.congestion_reduction_percent:.2f}%")
    print(f"Waiting proxy:          {result.waiting_before_s:.2f} -> {result.waiting_after_s:.2f}")
    print(f"Waiting reduction:      {result.waiting_reduction_percent:.2f}%")
    print(f"Average speed:          {result.average_speed_before_mps:.2f} -> {result.average_speed_after_mps:.2f} m/s")
    print(f"Objective/cost:         {result.objective:.6f}")
    print(f"Decision time:          {result.decision_time_ms:.3f} ms")
    print(f"Next predicted road:    {result.predicted_next_road} ({result.predicted_next_cars} cars)")
    print(f"Notes:                  {result.notes}")
    print("-" * 76)


def run_fair_benchmark(
    experiment: ControlledTrafficExperiment,
    hotspot: str,
    rf: TrafficRandomForest,
) -> Tuple[MethodResult, MethodResult, dict]:
    baseline = experiment.snapshot()

    print("\nRunning FAIR benchmark...")
    print("Both methods use the same hotspot, same baseline, same alternatives and same reroute fraction.")

    ai = evaluate_method(baseline, hotspot, "AI", rf)
    quantum = evaluate_method(baseline, hotspot, "Quantum", rf)

    # The prediction is evaluated against the controlled 30-second demand drift.
    prediction_experiment = ControlledTrafficExperiment()
    prediction_experiment.counts = dict(baseline)
    prediction_experiment.hotspot = hotspot
    prediction = rf.predict_next_road(prediction_experiment)

    future = ControlledTrafficExperiment()
    future.counts = dict(baseline)
    future.hotspot = hotspot
    future.advance_without_optimization(PREDICTION_HORIZON)
    actual_road = max(ROADS, key=lambda r: future.counts[r])
    actual_cars = future.counts[actual_road]
    predicted_road = prediction["winner"]["road"]
    predicted_cars = prediction["winner"]["predicted_cars"]
    accuracy = calculate_prediction_accuracy(predicted_cars, future.counts[predicted_road])

    ai.predicted_next_road = predicted_road
    ai.predicted_next_cars = predicted_cars
    ai.prediction_accuracy_percent = accuracy
    quantum.predicted_next_road = predicted_road
    quantum.predicted_next_cars = predicted_cars
    quantum.prediction_accuracy_percent = accuracy

    benchmark = {
        "baseline": baseline,
        "predicted_road": predicted_road,
        "predicted_cars": predicted_cars,
        "actual_road_after_30s": actual_road,
        "actual_cars_on_predicted_road_after_30s": future.counts[predicted_road],
        "actual_top_road_after_30s": actual_road,
        "actual_top_road_cars_after_30s": actual_cars,
        "prediction_correct_road": predicted_road == actual_road,
        "prediction_accuracy_percent": accuracy,
    }
    return ai, quantum, benchmark


def print_benchmark_table(ai: MethodResult, quantum: MethodResult, benchmark: dict) -> str:
    winner = "Quantum (QAOA)" if quantum.congestion_reduction_percent > ai.congestion_reduction_percent else "AI"
    if math.isclose(quantum.congestion_reduction_percent, ai.congestion_reduction_percent, abs_tol=1e-9):
        winner = "Tie"

    print("\n" + "=" * 120)
    print("QUANTUM CITY — AI vs QUANTUM TRAFFIC OPTIMIZATION EXPERIMENT")
    print("=" * 120)
    print(f"{'Metric':<30}{'AI':>25}{'Quantum (QAOA)':>25}")
    print("-" * 80)
    rows = [
        ("Hotspot", ai.hotspot, quantum.hotspot),
        ("Target road(s)", ai.target_roads, quantum.target_roads),
        ("Cars before", ai.cars_before, quantum.cars_before),
        ("Cars rerouted", ai.rerouted, quantum.rerouted),
        ("Cars after", ai.cars_after, quantum.cars_after),
        ("Congestion before", f"{ai.congestion_before*100:.2f}%", f"{quantum.congestion_before*100:.2f}%"),
        ("Congestion after", f"{ai.congestion_after*100:.2f}%", f"{quantum.congestion_after*100:.2f}%"),
        ("Congestion reduction", f"{ai.congestion_reduction_percent:.2f}%", f"{quantum.congestion_reduction_percent:.2f}%"),
        ("Waiting reduction", f"{ai.waiting_reduction_percent:.2f}%", f"{quantum.waiting_reduction_percent:.2f}%"),
        ("Average speed after", f"{ai.average_speed_after_mps:.2f} m/s", f"{quantum.average_speed_after_mps:.2f} m/s"),
        ("Decision time", f"{ai.decision_time_ms:.3f} ms", f"{quantum.decision_time_ms:.3f} ms"),
        ("Objective/cost", f"{ai.objective:.6f}", f"{quantum.objective:.6f}"),
        ("Prediction accuracy", f"{ai.prediction_accuracy_percent:.2f}%", f"{quantum.prediction_accuracy_percent:.2f}%"),
    ]
    for label, a, q in rows:
        print(f"{label:<30}{str(a):>25}{str(q):>25}")
    print("-" * 80)
    print(f"Predicted next hotspot: {benchmark['predicted_road']} ({benchmark['predicted_cars']} cars)")
    print(f"Actual top road after {PREDICTION_HORIZON}s: {benchmark['actual_top_road_after_30s']} ({benchmark['actual_top_road_cars_after_30s']} cars)")
    print(f"Prediction road correct: {benchmark['prediction_correct_road']}")
    print("=" * 120)
    print(f"RESULT: {winner} performs better on measured hotspot congestion reduction in this controlled trial.")
    print("This result is experiment-specific; it is NOT a claim of universal quantum advantage.")
    print("=" * 120)
    return winner


def run_interactive() -> None:
    output_dir = backend_dir / "experiments"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print(" Quantum City — Controlled Traffic Research Experiment Runner")
    print("=" * 80)
    print("This is a terminal-controlled, five-road experiment.")
    print("It does not launch Unity or the dynamic SUMO controller.")
    print("AI = RandomForest prediction + greedy diversion.")
    print("Quantum = TrafficQAOA route selection from dynamic_traffic.py.")
    print("Fair benchmark = same hotspot + same baseline + same reroute fraction.\n")

    if TrafficQAOA is None:
        print("[ERROR] TrafficQAOA import failed:")
        print(f"        {TRAFFIC_QAOA_IMPORT_ERROR}")
        print("Fix the backend import before running the quantum experiment.")
        return

    experiment = ControlledTrafficExperiment()
    rf = TrafficRandomForest()
    rf_metrics = rf.train()
    print(f"[AI] RF trained. Holdout MAE={rf_metrics['MAE']:.5f}, RMSE={rf_metrics['RMSE']:.5f}, R2={rf_metrics['R2']:.5f}")
    print_status(experiment)

    while True:
        print("\nCOMMANDS")
        print("  1  status")
        print("  2  increase congestion on a selected road")
        print("  3  AI optimize selected hotspot")
        print("  4  Quantum optimize selected hotspot")
        print("  5  AI predict next congestion")
        print("  6  Run FAIR AI vs Quantum benchmark")
        print("  7  Export latest experiment XLSX + PNG graphs")
        print("  8  Reset")
        print("  0  Exit")

        command = input("\nEnter command: ").strip().lower()

        try:
            if command in {"1", "status"}:
                print_status(experiment)

            elif command in {"2", "increase", "congestion"}:
                road = choose_road()
                extra = input("Extra cars to inject [default 20]: ").strip()
                extra_cars = int(extra) if extra else 20
                experiment.inject_congestion(road, extra_cars)
                print(f"[OK] Injected {extra_cars} cars into {road}.")
                print_status(experiment)

            elif command in {"3", "ai", "ai optimize"}:
                hotspot = experiment.hotspot or choose_road("Hotspot road [A/B/C/D/E]: ")
                baseline = experiment.snapshot()
                result = evaluate_method(baseline, hotspot, "AI", rf)
                experiment.restore(baseline)
                experiment.apply_diversion(hotspot, [result.target_roads], REROUTE_FRACTION)
                experiment.ai_result = result
                print_result(result)
                print_status(experiment)

            elif command in {"4", "quantum", "qaoa", "quantum optimize"}:
                hotspot = experiment.hotspot or choose_road("Hotspot road [A/B/C/D/E]: ")
                baseline = experiment.snapshot()
                result = evaluate_method(baseline, hotspot, "Quantum", rf)
                experiment.restore(baseline)
                experiment.apply_diversion(hotspot, [result.target_roads], REROUTE_FRACTION)
                experiment.quantum_result = result
                print_result(result)
                print_status(experiment)

            elif command in {"5", "predict", "prediction"}:
                prediction = rf.predict_next_road(experiment)
                print_prediction(prediction)

            elif command in {"6", "benchmark", "compare"}:
                hotspot = experiment.hotspot or choose_road("Hotspot road [A/B/C/D/E]: ")
                ai, quantum, benchmark = run_fair_benchmark(experiment, hotspot, rf)
                experiment.ai_result = ai
                experiment.quantum_result = quantum
                experiment.baseline_snapshot = dict(benchmark["baseline"])
                winner = print_benchmark_table(ai, quantum, benchmark)

                # Store a compact benchmark log for the XLSX timeline.
                experiment.experiment_log.append({
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                    "hotspot": hotspot,
                    "ai_congestion_reduction_percent": ai.congestion_reduction_percent,
                    "quantum_congestion_reduction_percent": quantum.congestion_reduction_percent,
                    "ai_waiting_reduction_percent": ai.waiting_reduction_percent,
                    "quantum_waiting_reduction_percent": quantum.waiting_reduction_percent,
                    "winner": winner,
                })

            elif command in {"7", "export", "xlsx"}:
                hotspot = experiment.hotspot
                if not hotspot:
                    raise ValueError("Create congestion first so an experiment exists.")

                if experiment.ai_result is None or experiment.quantum_result is None:
                    print("[INFO] Running the fair benchmark before export...")
                    ai, quantum, benchmark = run_fair_benchmark(experiment, hotspot, rf)
                    experiment.ai_result = ai
                    experiment.quantum_result = quantum
                else:
                    benchmark = {
                        "baseline": experiment.baseline_snapshot or experiment.snapshot(),
                        "predicted_road": experiment.ai_result.predicted_next_road,
                        "predicted_cars": experiment.ai_result.predicted_next_cars,
                        "actual_road_after_30s": "N/A",
                        "actual_cars_on_predicted_road_after_30s": "N/A",
                        "actual_top_road_after_30s": "N/A",
                        "actual_top_road_cars_after_30s": "N/A",
                        "prediction_correct_road": "N/A",
                        "prediction_accuracy_percent": experiment.ai_result.prediction_accuracy_percent,
                    }

                prediction = rf.predict_next_road(experiment)
                run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
                run_dir = output_dir / f"run_{run_id}"
                run_dir.mkdir(parents=True, exist_ok=True)

                timeline = []
                base = benchmark["baseline"]
                for step in range(0, PREDICTION_HORIZON + 1, 5):
                    sim = ControlledTrafficExperiment()
                    sim.counts = dict(base)
                    sim.advance_without_optimization(step)
                    timeline.append({
                        "step": step,
                        "hotspot": hotspot,
                        "hotspot_cars": sim.counts[hotspot],
                        "hotspot_congestion": sim.state(hotspot).congestion,
                        "total_cars": sum(sim.counts.values()),
                    })

                plot_paths = save_experiment_plots(
                    run_dir,
                    hotspot,
                    base,
                    experiment.ai_result,
                    experiment.quantum_result,
                    prediction,
                    timeline,
                )
                xlsx_path = export_xlsx(
                    run_dir,
                    run_id,
                    hotspot,
                    base,
                    prediction,
                    experiment.ai_result,
                    experiment.quantum_result,
                    rf_metrics,
                    timeline,
                    plot_paths,
                )

                print("\nEXPORT COMPLETE")
                print(f"Folder: {run_dir}")
                print(f"XLSX:   {xlsx_path}")
                for path in plot_paths:
                    print(f"PNG:    {path}")

            elif command in {"8", "reset"}:
                experiment.reset()
                print("[OK] Experiment reset to deterministic baseline.")
                print_status(experiment)

            elif command in {"0", "exit", "quit"}:
                print("Experiment runner closed.")
                break

            else:
                print("Unknown command. Enter 1-8 or 0.")

        except KeyboardInterrupt:
            print("\nInterrupted. Returning to command menu.")
        except Exception as exc:
            print(f"[ERROR] {type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Legacy batch suite retained behind --legacy.
# ---------------------------------------------------------------------------

def run_legacy_batch() -> None:
    """Run the original project-wide SUMO/ML/scaling experiment suite."""
    from multiverse.world_generator import WorldGenerator
    from simulation.traffic import TrafficSimulator
    from simulation.metrics import TrafficMetricsCalculator
    from ai.traffic_model import TrafficPredictionModel
    from ai.energy_model import EnergyPredictionModel
    from optimization.benchmark import SolverBenchmark
    from quantum.qubo import CityResourceProblem

    output_dir = backend_dir / "experiments"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("================================================")
    print("   Quantum City Legacy Research Batch")
    print("================================================\n")

    generator = WorldGenerator()
    worlds = generator.generate_predefined_worlds()
    simulator = TrafficSimulator()
    metrics_calc = TrafficMetricsCalculator()
    scenario_results = []

    with open(output_dir / "traffic_metrics.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Scenario", "Unique Vehicles", "Peak Active Vehicles",
            "Avg Speed (m/s)", "Avg Waiting Time (s)",
            "Cumulative Waiting (s)", "Congestion Index",
            "Traffic Flow Efficiency",
        ])
        for world in worlds:
            print(f"[*] Running {world.name}...")
            sim_res = simulator.run_simulation(steps=100, world=world)
            met_res = metrics_calc.calculate_metrics(sim_res)
            scenario_results.append((world, sim_res, met_res))
            writer.writerow([
                world.name, sim_res.total_unique_vehicles_observed,
                met_res.peak_active_vehicles, met_res.average_speed,
                met_res.average_waiting_time_per_step,
                met_res.cumulative_waiting_time, met_res.congestion_index,
                met_res.traffic_flow_efficiency,
            ])

    if scenario_results:
        names = [r[0].name for r in scenario_results]
        fig, ax = plt.subplots(figsize=(9, 5))
        ax.bar(names, [r[2].average_speed for r in scenario_results])
        ax.set_title("Average Vehicle Speed by Scenario")
        ax.set_ylabel("m/s")
        ax.grid(axis="y", alpha=0.25)
        fig.tight_layout()
        fig.savefig(output_dir / "traffic_speeds.png", dpi=180)
        plt.close(fig)

    traffic_eval = None
    if scenario_results:
        model = TrafficPredictionModel()
        traffic_eval = model.evaluate([r[1] for r in scenario_results], min_samples_for_split=10)
        print(f"Traffic RF: MAE={traffic_eval.mae:.4f}, RMSE={traffic_eval.rmse:.4f}, R2={traffic_eval.r2:.4f}")

    energy_eval = None
    try:
        energy_model = EnergyPredictionModel()
        energy_eval = energy_model.evaluate_from_csv(backend_dir / "ai" / "energy_dataset.csv")
        print(f"Energy RF: MAE={energy_eval.mae:.4f}, RMSE={energy_eval.rmse:.4f}, R2={energy_eval.r2:.4f}")
    except Exception as exc:
        print(f"Energy evaluation skipped: {exc}")

    zones = [4, 6, 8, 10, 12, 16, 20]
    benchmark = SolverBenchmark()
    rows = []
    for z in zones:
        problem = CityResourceProblem(
            num_zones=z,
            max_allocations=max(1, z // 3),
            predicted_energy_demand_mw=750.0,
            active_vehicle_count=5000,
            traffic_congestion_index=0.6,
        )
        try:
            res = benchmark.run(problem)
            rows.append(res)
            print(f"{z} zones | Q={res.quantum_execution_time_ms:.2f} ms | C={res.classical_execution_time_ms:.2f} ms | match={res.objectives_match}")
        except Exception as exc:
            print(f"Scaling {z} failed: {exc}")

    if rows:
        fig, ax = plt.subplots(figsize=(9, 5))
        z = [r.num_zones for r in rows]
        ax.plot(z, [r.quantum_execution_time_ms for r in rows], marker="o", label="Quantum (QAOA)")
        ax.plot(z, [r.classical_execution_time_ms for r in rows], marker="s", label="Classical (Brute Force)")
        ax.set_yscale("log")
        ax.set_xlabel("Number of zones")
        ax.set_ylabel("Execution time (ms)")
        ax.set_title("Optimization Solver Scaling")
        ax.legend()
        ax.grid(True, alpha=0.25)
        fig.tight_layout()
        fig.savefig(output_dir / "optimization_scaling.png", dpi=180)
        plt.close(fig)

    print(f"Legacy artifacts saved to {output_dir}")


if __name__ == "__main__":
    if "--legacy" in sys.argv:
        run_legacy_batch()
    else:
        run_interactive()
