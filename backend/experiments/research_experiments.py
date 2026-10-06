import os
import sys
import csv
import time
import matplotlib.pyplot as plt
from pathlib import Path

# Ensure backend root is in PYTHONPATH so imports work
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from multiverse.world_generator import WorldGenerator
from simulation.traffic import TrafficSimulator
from simulation.metrics import TrafficMetricsCalculator
from ai.traffic_model import TrafficPredictionModel
from ai.energy_model import EnergyPredictionModel
from optimization.benchmark import SolverBenchmark
from quantum.qubo import CityResourceProblem


def run_experiments():
    output_dir = backend_dir / "experiments"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("================================================")
    print("   Quantum City Research Experiments Runner")
    print("================================================\n")

    # ── 1. SUMO Traffic Simulations ─────────────────────────────────────────
    print("--- 1. SUMO Traffic Simulations (Baseline, Eco Future, Smart Mobility) ---")
    generator = WorldGenerator()
    worlds = generator.generate_predefined_worlds()
    simulator = TrafficSimulator()
    metrics_calc = TrafficMetricsCalculator()

    scenario_names = [w.name for w in worlds]
    scenario_results = []       # (world, sim_result, metrics_result)

    traffic_csv = output_dir / "traffic_metrics.csv"
    with open(traffic_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Scenario",
            "Unique Vehicles",
            "Peak Active Vehicles",
            "Avg Speed (m/s)",
            "Avg Waiting Time (s)",
            "Cumulative Waiting (s)",
            "Congestion Index",
            "Traffic Flow Efficiency",
        ])

        for world in worlds:
            print(f"[*] Running simulation for {world.name} (100 steps)...")
            try:
                sim_res = simulator.run_simulation(steps=100, world=world)
                met_res = metrics_calc.calculate_metrics(sim_res)
                scenario_results.append((world, sim_res, met_res))
                writer.writerow([
                    world.name,
                    sim_res.total_unique_vehicles_observed,
                    met_res.peak_active_vehicles,
                    met_res.average_speed,
                    met_res.average_waiting_time_per_step,
                    met_res.cumulative_waiting_time,
                    met_res.congestion_index,
                    met_res.traffic_flow_efficiency,
                ])
                print(f"    -> Avg Speed: {met_res.average_speed} m/s | "
                      f"Peak Vehicles: {met_res.peak_active_vehicles} | "
                      f"Cumulative Wait: {met_res.cumulative_waiting_time}s | "
                      f"Congestion: {met_res.congestion_index:.4f} | "
                      f"Efficiency: {met_res.traffic_flow_efficiency:.4f}")
            except Exception as e:
                print(f"    [!] Error running simulation for {world.name}: {e}")

    print(f"[*] Saved traffic metrics to traffic_metrics.csv")

    # ── Plot: 6-panel comparison bar chart ──────────────────────────────────
    if scenario_results:
        names  = [r[0].name for r in scenario_results]
        colors = ["#4C72B0", "#55A868", "#C44E52"]

        metrics_to_plot = [
            ("Average Speed (m/s)",         [r[2].average_speed               for r in scenario_results]),
            ("Peak Active Vehicles",         [r[2].peak_active_vehicles         for r in scenario_results]),
            ("Avg Waiting Time (s/step)",    [r[2].average_waiting_time_per_step for r in scenario_results]),
            ("Cumulative Waiting Time (s)",  [r[2].cumulative_waiting_time       for r in scenario_results]),
            ("Congestion Index [0-1]",       [r[2].congestion_index              for r in scenario_results]),
            ("Traffic Flow Efficiency [0-1]",[r[2].traffic_flow_efficiency       for r in scenario_results]),
        ]

        fig, axes = plt.subplots(2, 3, figsize=(15, 8))
        fig.suptitle("Quantum City — Scenario Comparison (2030)", fontsize=14, fontweight="bold")

        for ax, (label, values) in zip(axes.flat, metrics_to_plot):
            bars = ax.bar(names, values, color=colors)
            ax.set_title(label, fontsize=10, fontweight="bold")
            ax.set_ylabel(label)
            ax.grid(axis="y", linestyle="--", alpha=0.6)
            ax.set_xticks(range(len(names)))
            ax.set_xticklabels(names, rotation=12, ha="right", fontsize=8)
            for bar, val in zip(bars, values):
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_height() + max(values) * 0.01,
                        f"{val:.3f}" if isinstance(val, float) else str(val),
                        ha="center", va="bottom", fontsize=8)

        plt.tight_layout()
        plt.savefig(output_dir / "scenario_comparison.png", dpi=120)
        plt.close()
        print("[*] Saved 6-panel comparison to scenario_comparison.png")

        # Keep the original single-metric speed chart as well
        speeds = [r[2].average_speed for r in scenario_results]
        plt.figure(figsize=(8, 5))
        plt.bar(names, speeds, color=colors)
        plt.title("Average Vehicle Speed by Scenario (2030)")
        plt.ylabel("Average Speed (m/s)")
        plt.grid(axis="y", linestyle="--", alpha=0.7)
        plt.tight_layout()
        plt.savefig(output_dir / "traffic_speeds.png")
        plt.close()
        print("[*] Saved traffic speed plot to traffic_speeds.png")

    # ── 2. Traffic RF Evaluation ─────────────────────────────────────────────
    print("\n--- 2. Traffic Random Forest Evaluation ---")
    sim_results_only = [r[1] for r in scenario_results]
    traffic_eval = None
    if sim_results_only:
        traffic_model = TrafficPredictionModel()
        try:
            traffic_eval = traffic_model.evaluate(sim_results_only, min_samples_for_split=10)
            print(f"[*] Traffic Model -> MAE: {traffic_eval.mae:.4f}, "
                  f"RMSE: {traffic_eval.rmse:.4f}, R2: {traffic_eval.r2:.4f}")
        except Exception as e:
            print(f"[!] Error evaluating traffic model: {e}")
    else:
        print("[!] No traffic simulation results available.")

    # ── 3. Energy RF Evaluation ──────────────────────────────────────────────
    print("\n--- 3. Energy Random Forest Evaluation ---")
    energy_csv_path = backend_dir / "ai" / "energy_dataset.csv"
    energy_model = EnergyPredictionModel()
    energy_eval = None
    try:
        energy_eval = energy_model.evaluate_from_csv(energy_csv_path)
        print(f"[*] Energy Model -> MAE: {energy_eval.mae:.4f}, "
              f"RMSE: {energy_eval.rmse:.4f}, R2: {energy_eval.r2:.4f}")
    except Exception as e:
        print(f"[!] Error evaluating energy model: {e}")

    # Save ML metrics
    ml_csv = output_dir / "ml_evaluation.csv"
    with open(ml_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Model", "MAE", "RMSE", "R2", "Test Samples"])
        if traffic_eval:
            writer.writerow(["Traffic RF", traffic_eval.mae, traffic_eval.rmse,
                              traffic_eval.r2, traffic_eval.test_samples])
        if energy_eval:
            writer.writerow(["Energy RF", energy_eval.mae, energy_eval.rmse,
                              energy_eval.r2, energy_eval.test_samples])
    print(f"[*] Saved ML metrics to ml_evaluation.csv")

    # ── 4 & 5. Quantum vs Classical Benchmark Scaling ────────────────────────
    print("\n--- 4 & 5. Optimization Scaling Benchmark (QAOA vs Classical) ---")
    zones = [4, 6, 8, 10, 12, 16, 20]
    benchmark = SolverBenchmark()

    bench_results = []
    bench_csv = output_dir / "optimization_scaling.csv"
    with open(bench_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Zones", "Max Allocations", "Quantum Time (ms)",
                         "Classical Time (ms)", "Quantum Obj", "Classical Obj", "Gap", "Match"])

        print(f"{'Zones':<6} | {'Q-Time (ms)':<12} | {'C-Time (ms)':<12} | {'Match':<6}")
        print("-" * 45)
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
                bench_results.append(res)
                writer.writerow([
                    res.num_zones, res.max_allocations,
                    res.quantum_execution_time_ms, res.classical_execution_time_ms,
                    res.quantum_objective, res.classical_objective,
                    res.objective_gap, res.objectives_match,
                ])
                print(f"{z:<6} | {res.quantum_execution_time_ms:<12.2f} | "
                      f"{res.classical_execution_time_ms:<12.2f} | {str(res.objectives_match):<6}")
            except Exception as e:
                print(f"[!] Failed for {z} zones: {e}")

    if bench_results:
        z_vals  = [r.num_zones for r in bench_results]
        q_times = [r.quantum_execution_time_ms for r in bench_results]
        c_times = [r.classical_execution_time_ms for r in bench_results]

        plt.figure(figsize=(8, 5))
        plt.plot(z_vals, q_times, marker="o", label="Quantum (QAOA)",
                 color="purple", linewidth=2)
        plt.plot(z_vals, c_times, marker="s", label="Classical (Brute Force)",
                 color="orange", linewidth=2)
        plt.title("Solver Execution Time vs Problem Scaling")
        plt.xlabel("Number of Zones")
        plt.ylabel("Execution Time (ms)")
        plt.yscale("log")
        plt.xticks(z_vals)
        plt.legend()
        plt.grid(True, linestyle="--", alpha=0.6)
        plt.tight_layout()
        plt.savefig(output_dir / "optimization_scaling.png")
        plt.close()
        print("[*] Saved optimization scaling plot to optimization_scaling.png")

    # ── Summary ──────────────────────────────────────────────────────────────
    print("\n================================================")
    print("   Experiment Summary")
    print("================================================")
    print("All tasks completed.")
    print(f"Artifacts generated in: {output_dir}")
    print(" - traffic_metrics.csv       (6 KPIs per scenario)")
    print(" - scenario_comparison.png   (6-panel bar chart)")
    print(" - traffic_speeds.png        (speed bar chart)")
    print(" - ml_evaluation.csv")
    print(" - optimization_scaling.csv")
    print(" - optimization_scaling.png")


if __name__ == "__main__":
    run_experiments()
