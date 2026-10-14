using System;
using System.Collections;
using UnityEngine;
using UnityEngine.UI;
using UnityEngine.Networking;
using TMPro;

namespace QuantumCity.UI
{
    /// <summary>
    /// Main Quantum City dashboard.
    ///
    /// Connects Unity directly to the FastAPI backend and exposes:
    /// - SUMO traffic simulation
    /// - AI traffic prediction
    /// - AI energy prediction
    /// - Quantum QAOA optimization
    /// - Classical optimization
    /// - Quantum vs Classical benchmark
    ///
    /// Existing UI references are optional. If a reference is missing,
    /// the controller will try to find the object by name.
    /// </summary>
    public class DashboardController : MonoBehaviour
    {
        [Header("Backend")]
        [SerializeField] private string backendUrl = "http://127.0.0.1:8000";

        [Header("Status")]
        [SerializeField] private TextMeshProUGUI cityNameText;
        [SerializeField] private TextMeshProUGUI simStatusText;
        [SerializeField] private TextMeshProUGUI fpsText;

        [Header("Live Metrics")]
        [SerializeField] private TextMeshProUGUI trafficFlowText;
        [SerializeField] private TextMeshProUGUI energyText;
        [SerializeField] private TextMeshProUGUI vehiclesText;
        [SerializeField] private TextMeshProUGUI congestionText;

        [Header("AI Results")]
        [SerializeField] private TextMeshProUGUI trafficPredictionText;
        [SerializeField] private TextMeshProUGUI energyPredictionText;

        [Header("Quantum Results")]
        [SerializeField] private TextMeshProUGUI quantumResultText;
        [SerializeField] private TextMeshProUGUI classicalResultText;
        [SerializeField] private TextMeshProUGUI benchmarkText;

        [Header("Controls")]
        [SerializeField] private Button runSimulationButton;
        [SerializeField] private Button predictTrafficButton;
        [SerializeField] private Button predictEnergyButton;
        [SerializeField] private Button quantumOptimizationButton;
        [SerializeField] private Button classicalOptimizationButton;
        [SerializeField] private Button benchmarkButton;

        [Header("Side Panel")]
        [SerializeField] private GameObject sidePanel;
        [SerializeField] private Button sidePanelToggleButton;

        [Header("Simulation")]
        [SerializeField] private int simulationSteps = 100;

        private int frameCount;
        private float fpsTimer;
        private float currentFps;

        private float latestEnergy = 2897.6f;
        private int latestVehicles = 25;
        private float latestCongestion = 0.42f;

        private void Awake()
        {
            AutoFindUI();

            RegisterButton(runSimulationButton, RunSimulation);
            RegisterButton(predictTrafficButton, PredictTraffic);
            RegisterButton(predictEnergyButton, PredictEnergy);
            RegisterButton(quantumOptimizationButton, QuantumOptimization);
            RegisterButton(classicalOptimizationButton, ClassicalOptimization);
            RegisterButton(benchmarkButton, Benchmark);

            if (sidePanelToggleButton != null)
                sidePanelToggleButton.onClick.AddListener(ToggleSidePanel);
        }

        private void Start()
        {
            SetCityName("QUANTUM CITY");
            SetSimStatus("READY");
            SetTrafficFlow(0f);
            SetEnergy(0f);
            SetVehicles(0);
            SetCongestion(0f);

            SetText(trafficPredictionText, "AI Traffic: READY");
            SetText(energyPredictionText, "AI Energy: READY");
            SetText(quantumResultText, "Quantum: READY");
            SetText(classicalResultText, "Classical: READY");
            SetText(benchmarkText, "Benchmark: READY");

            StartCoroutine(CheckBackend());
        }

        private void Update()
        {
            UpdateFPS();
        }

        // =========================================================
        // UI AUTO DISCOVERY
        // =========================================================

        private void AutoFindUI()
        {
            cityNameText = FindText(cityNameText, "CityNameText");
            simStatusText = FindText(simStatusText, "SimStatusText");
            fpsText = FindText(fpsText, "FPSText");

            trafficFlowText = FindText(trafficFlowText, "TrafficFlowText");
            energyText = FindText(energyText, "EnergyText");
            vehiclesText = FindText(vehiclesText, "VehiclesText");
            congestionText = FindText(congestionText, "CongestionText");

            trafficPredictionText =
                FindText(trafficPredictionText, "TrafficPredictionText");

            energyPredictionText =
                FindText(energyPredictionText, "EnergyPredictionText");

            quantumResultText =
                FindText(quantumResultText, "QuantumResultText");

            classicalResultText =
                FindText(classicalResultText, "ClassicalResultText");

            benchmarkText =
                FindText(benchmarkText, "BenchmarkText");

            runSimulationButton =
                FindButton(runSimulationButton, "Btn_RunSimulation");

            predictTrafficButton =
                FindButton(predictTrafficButton, "Btn_PredictTraffic");

            predictEnergyButton =
                FindButton(predictEnergyButton, "Btn_PredictEnergy");

            quantumOptimizationButton =
                FindButton(
                    quantumOptimizationButton,
                    "Btn_QuantumOptimization"
                );

            classicalOptimizationButton =
                FindButton(
                    classicalOptimizationButton,
                    "Btn_ClassicalOptimization"
                );

            benchmarkButton =
                FindButton(
                    benchmarkButton,
                    "Btn_Benchmark"
                );

            if (sidePanelToggleButton == null)
            {
                sidePanelToggleButton =
                    FindButton(null, "Btn_TogglePanel");
            }

            if (sidePanel == null)
            {
                GameObject panel = GameObject.Find("SidePanel");

                if (panel != null)
                    sidePanel = panel;
            }
        }

        private TextMeshProUGUI FindText(
            TextMeshProUGUI current,
            string objectName)
        {
            if (current != null)
                return current;

            GameObject obj = GameObject.Find(objectName);

            if (obj == null)
                return null;

            return obj.GetComponent<TextMeshProUGUI>();
        }

        private Button FindButton(
            Button current,
            string objectName)
        {
            if (current != null)
                return current;

            GameObject obj = GameObject.Find(objectName);

            if (obj == null)
                return null;

            return obj.GetComponent<Button>();
        }

        private void RegisterButton(Button button, UnityEngine.Events.UnityAction action)
        {
            if (button == null)
                return;

            button.onClick.RemoveListener(action);
            button.onClick.AddListener(action);
        }

        // =========================================================
        // BACKEND CONNECTION
        // =========================================================

        private IEnumerator CheckBackend()
        {
            using UnityWebRequest request =
                UnityWebRequest.Get(backendUrl + "/health");

            request.timeout = 5;

            yield return request.SendWebRequest();

            if (request.result == UnityWebRequest.Result.Success)
            {
                SetSimStatus("BACKEND ONLINE");
                Debug.Log("[Dashboard] Backend connected.");
            }
            else
            {
                SetSimStatus("BACKEND OFFLINE");
                Debug.LogError(
                    "[Dashboard] Backend connection failed: " +
                    request.error
                );
            }
        }

        // =========================================================
        // 1. RUN SUMO SIMULATION
        // =========================================================

        public void RunSimulation()
        {
            StartCoroutine(RunSimulationRequest());
        }

        private IEnumerator RunSimulationRequest()
        {
            SetSimStatus("RUNNING SUMO...");
            SetText(trafficPredictionText, "AI Traffic: waiting...");
            
            SimulationRequest payload = new SimulationRequest
            {
                steps = simulationSteps
            };

            string json = JsonUtility.ToJson(payload);

            using UnityWebRequest request =
                CreatePostRequest(
                    backendUrl + "/simulation/run",
                    json
                );

            yield return request.SendWebRequest();

            if (request.result != UnityWebRequest.Result.Success)
            {
                HandleRequestError("SUMO simulation", request);
                yield break;
            }

            SimulationResponse result =
                JsonUtility.FromJson<SimulationResponse>(
                    request.downloadHandler.text
                );

            if (result != null)
            {
                latestVehicles = result.peak_active_vehicles;
                latestCongestion = result.congestion_index;

                SetVehicles(result.peak_active_vehicles);
                SetTrafficFlow(
                    result.traffic_flow_efficiency * 100f
                );

                SetCongestion(
                    result.congestion_index * 100f
                );

                SetSimStatus("SIMULATION COMPLETE");

                Debug.Log(
                    "[Dashboard] SUMO simulation completed."
                );

                Debug.Log(
                    "[Dashboard] Peak vehicles: " +
                    result.peak_active_vehicles
                );
            }
            else
            {
                SetSimStatus("SIMULATION COMPLETE");
            }
        }

        // =========================================================
        // 2. AI TRAFFIC PREDICTION
        // =========================================================

        public void PredictTraffic()
        {
            StartCoroutine(PredictTrafficRequest());
        }

        private IEnumerator PredictTrafficRequest()
        {
            SetSimStatus("AI TRAFFIC PREDICTION...");

            TrafficPredictionRequest payload =
                new TrafficPredictionRequest
                {
                    step = 50,
                    simulation_time = 50f,
                    active_vehicle_count = latestVehicles,
                    average_vehicle_speed = 7.97f,
                    total_waiting_time = 57.11f,
                    current_congestion_index = latestCongestion,
                    current_traffic_flow_efficiency =
                        1f - latestCongestion
                };

            string json = JsonUtility.ToJson(payload);

            using UnityWebRequest request =
                CreatePostRequest(
                    backendUrl + "/prediction/traffic",
                    json
                );

            yield return request.SendWebRequest();

            if (request.result != UnityWebRequest.Result.Success)
            {
                HandleRequestError("AI traffic prediction", request);
                yield break;
            }

            TrafficPredictionResponse result =
                JsonUtility.FromJson<TrafficPredictionResponse>(
                    request.downloadHandler.text
                );

            if (result != null)
            {
                float prediction =
                    result.predicted_congestion_index * 100f;

                SetText(
                    trafficPredictionText,
                    $"AI Traffic Prediction\n" +
                    $"Congestion: {prediction:F1}%"
                );

                SetSimStatus("AI TRAFFIC READY");

                Debug.Log(
                    "[Dashboard] AI predicted congestion: " +
                    prediction.ToString("F2") +
                    "%"
                );
            }
        }

        // =========================================================
        // 3. AI ENERGY PREDICTION
        // =========================================================

        public void PredictEnergy()
        {
            StartCoroutine(PredictEnergyRequest());
        }

        private IEnumerator PredictEnergyRequest()
        {
            SetSimStatus("AI ENERGY PREDICTION...");

            EnergyPredictionRequest payload =
                new EnergyPredictionRequest
                {
                    simulation_time = 50f,
                    energy_demand_mw = latestEnergy,
                    renewable_percentage = 0.25f,
                    active_vehicle_count = latestVehicles,
                    congestion_index = latestCongestion
                };

            string json = JsonUtility.ToJson(payload);

            using UnityWebRequest request =
                CreatePostRequest(
                    backendUrl + "/prediction/energy",
                    json
                );

            yield return request.SendWebRequest();

            if (request.result != UnityWebRequest.Result.Success)
            {
                HandleRequestError("AI energy prediction", request);
                yield break;
            }

            EnergyPredictionResponse result =
                JsonUtility.FromJson<EnergyPredictionResponse>(
                    request.downloadHandler.text
                );

            if (result != null)
            {
                latestEnergy =
                    result.predicted_energy_demand_mw;

                SetEnergy(latestEnergy);

                SetText(
                    energyPredictionText,
                    $"AI Energy Prediction\n" +
                    $"{latestEnergy:F1} MW"
                );

                SetSimStatus("AI ENERGY READY");

                Debug.Log(
                    "[Dashboard] AI predicted energy: " +
                    latestEnergy.ToString("F2") +
                    " MW"
                );
            }
        }

        // =========================================================
        // 4. QUANTUM OPTIMIZATION
        // =========================================================

        public void QuantumOptimization()
        {
            StartCoroutine(QuantumOptimizationRequest());
        }

        private IEnumerator QuantumOptimizationRequest()
        {
            SetSimStatus("RUNNING QAOA...");

            OptimizationRequest payload =
                CreateOptimizationRequest();

            string json = JsonUtility.ToJson(payload);

            using UnityWebRequest request =
                CreatePostRequest(
                    backendUrl + "/optimization/quantum",
                    json
                );

            yield return request.SendWebRequest();

            if (request.result != UnityWebRequest.Result.Success)
            {
                HandleRequestError("Quantum optimization", request);
                yield break;
            }

            QuantumOptimizationResponse result =
                JsonUtility.FromJson<QuantumOptimizationResponse>(
                    request.downloadHandler.text
                );

            if (result != null)
            {
                string allocation =
                    FormatAllocation(result.selected_allocation);

                SetText(
                    quantumResultText,
                    $"QUANTUM QAOA\n" +
                    $"Solver: {result.solver}\n" +
                    $"Objective: {result.objective_value:F4}\n" +
                    $"Zones: {allocation}"
                );

                SetSimStatus("QUANTUM OPTIMIZED");

                Debug.Log(
                    "[Dashboard] Quantum objective: " +
                    result.objective_value
                );
            }
        }

        // =========================================================
        // 5. CLASSICAL OPTIMIZATION
        // =========================================================

        public void ClassicalOptimization()
        {
            StartCoroutine(ClassicalOptimizationRequest());
        }

        private IEnumerator ClassicalOptimizationRequest()
        {
            SetSimStatus("RUNNING CLASSICAL...");

            OptimizationRequest payload =
                CreateOptimizationRequest();

            string json = JsonUtility.ToJson(payload);

            using UnityWebRequest request =
                CreatePostRequest(
                    backendUrl + "/optimization/classical",
                    json
                );

            yield return request.SendWebRequest();

            if (request.result != UnityWebRequest.Result.Success)
            {
                HandleRequestError("Classical optimization", request);
                yield break;
            }

            ClassicalOptimizationResponse result =
                JsonUtility.FromJson<ClassicalOptimizationResponse>(
                    request.downloadHandler.text
                );

            if (result != null)
            {
                string allocation =
                    FormatAllocation(result.selected_allocation);

                SetText(
                    classicalResultText,
                    $"CLASSICAL SOLVER\n" +
                    $"Method: {result.solver}\n" +
                    $"Objective: {result.objective_value:F4}\n" +
                    $"Zones: {allocation}"
                );

                SetSimStatus("CLASSICAL OPTIMIZED");
            }
        }

        // =========================================================
        // 6. QUANTUM VS CLASSICAL BENCHMARK
        // =========================================================

        public void Benchmark()
        {
            StartCoroutine(BenchmarkRequest());
        }

        private IEnumerator BenchmarkRequest()
        {
            SetSimStatus("BENCHMARKING...");

            OptimizationRequest payload =
                CreateOptimizationRequest();

            string json = JsonUtility.ToJson(payload);

            using UnityWebRequest request =
                CreatePostRequest(
                    backendUrl + "/optimization/benchmark",
                    json
                );

            yield return request.SendWebRequest();

            if (request.result != UnityWebRequest.Result.Success)
            {
                HandleRequestError("Benchmark", request);
                yield break;
            }

            BenchmarkResponse result =
                JsonUtility.FromJson<BenchmarkResponse>(
                    request.downloadHandler.text
                );

            if (result != null)
            {
                SetText(
                    benchmarkText,
                    $"QUANTUM vs CLASSICAL\n" +
                    $"Quantum: {result.quantum_objective:F4}\n" +
                    $"Classical: {result.classical_objective:F4}\n" +
                    $"Gap: {result.objective_gap:F4}\n" +
                    $"Match: {result.objectives_match}"
                );

                SetSimStatus("BENCHMARK COMPLETE");

                Debug.Log(
                    $"[Dashboard] Benchmark Q={result.quantum_objective:F4} " +
                    $"C={result.classical_objective:F4}"
                );
            }
        }

        // =========================================================
        // REQUEST HELPERS
        // =========================================================

        private OptimizationRequest CreateOptimizationRequest()
        {
            return new OptimizationRequest
            {
                predicted_energy_demand_mw =
                    latestEnergy,

                active_vehicle_count =
                    latestVehicles,

                traffic_congestion_index =
                    latestCongestion,

                num_zones = 4,

                max_allocations = 2,

                budget_penalty_weight = 5f
            };
        }

        private UnityWebRequest CreatePostRequest(
            string url,
            string json)
        {
            byte[] body =
                System.Text.Encoding.UTF8.GetBytes(json);

            UnityWebRequest request =
                new UnityWebRequest(
                    url,
                    UnityWebRequest.kHttpVerbPOST
                );

            request.uploadHandler =
                new UploadHandlerRaw(body);

            request.downloadHandler =
                new DownloadHandlerBuffer();

            request.SetRequestHeader(
                "Content-Type",
                "application/json"
            );

            request.timeout = 120;

            return request;
        }

        private void HandleRequestError(
            string operation,
            UnityWebRequest request)
        {
            SetSimStatus("ERROR");

            Debug.LogError(
                $"[Dashboard] {operation} failed: " +
                request.error +
                "\nResponse: " +
                request.downloadHandler?.text
            );
        }

        // =========================================================
        // DISPLAY
        // =========================================================

        public void SetCityName(string value)
        {
            SetText(cityNameText, value);
        }

        public void SetSimStatus(string value)
        {
            SetText(simStatusText, "STATUS: " + value);
        }

        public void SetTrafficFlow(float value)
        {
            SetText(
                trafficFlowText,
                $"Traffic Flow: {value:F1}%"
            );
        }

        public void SetEnergy(float value)
        {
            SetText(
                energyText,
                $"Energy: {value:F1} MW"
            );
        }

        public void SetVehicles(int value)
        {
            SetText(
                vehiclesText,
                $"Vehicles: {value:N0}"
            );
        }

        public void SetPopulation(int population)
        {
            SetVehicles(population);
        }

        public void SetCongestion(float value)
        {
            SetText(
                congestionText,
                $"Congestion: {value:F1}%"
            );
        }

        private void SetText(
            TextMeshProUGUI text,
            string value)
        {
            if (text != null)
                text.text = value;
        }

        private string FormatAllocation(int[] allocation)
        {
            if (allocation == null ||
                allocation.Length == 0)
                return "none";

            return "[" +
                   string.Join(",", allocation) +
                   "]";
        }

        // =========================================================
        // FPS
        // =========================================================

        private void UpdateFPS()
        {
            frameCount++;
            fpsTimer += Time.unscaledDeltaTime;

            if (fpsTimer >= 0.5f)
            {
                currentFps =
                    frameCount / fpsTimer;

                SetText(
                    fpsText,
                    $"FPS: {currentFps:F0}"
                );

                frameCount = 0;
                fpsTimer = 0f;
            }
        }

        // =========================================================
        // PANEL
        // =========================================================

        private void ToggleSidePanel()
        {
            if (sidePanel == null)
                return;

            sidePanel.SetActive(
                !sidePanel.activeSelf
            );
        }

        // =========================================================
        // JSON MODELS
        // =========================================================

        [Serializable]
        private class SimulationRequest
        {
            public int steps;
        }

        [Serializable]
        private class SimulationResponse
        {
            public int total_steps;
            public float simulation_duration;
            public int total_unique_vehicles;
            public int peak_active_vehicles;
            public float average_active_vehicles;
            public float average_speed;
            public float cumulative_waiting_time;
            public float average_waiting_time_per_step;
            public float maximum_step_waiting_time;
            public float congestion_index;
            public float traffic_flow_efficiency;
        }

        [Serializable]
        private class TrafficPredictionRequest
        {
            public int step;
            public float simulation_time;
            public int active_vehicle_count;
            public float average_vehicle_speed;
            public float total_waiting_time;
            public float current_congestion_index;
            public float current_traffic_flow_efficiency;
        }

        [Serializable]
        private class TrafficPredictionResponse
        {
            public float predicted_congestion_index;
            public string model_type;
            public string target_name;
        }

        [Serializable]
        private class EnergyPredictionRequest
        {
            public float simulation_time;
            public float energy_demand_mw;
            public float renewable_percentage;
            public int active_vehicle_count;
            public float congestion_index;
        }

        [Serializable]
        private class EnergyPredictionResponse
        {
            public float predicted_energy_demand_mw;
            public string model_type;
            public string target_name;
        }

        [Serializable]
        private class OptimizationRequest
        {
            public float predicted_energy_demand_mw;
            public int active_vehicle_count;
            public float traffic_congestion_index;
            public int num_zones;
            public int max_allocations;
            public float budget_penalty_weight;
        }

        [Serializable]
        private class QuantumOptimizationResponse
        {
            public string solver;
            public int[] selected_allocation;
            public float objective_value;
            public float[] optimal_parameters;
            public string fallback_reason;
        }

        [Serializable]
        private class ClassicalOptimizationResponse
        {
            public string solver;
            public int[] selected_allocation;
            public float objective_value;
            public float execution_time_ms;
        }

        [Serializable]
        private class BenchmarkResponse
        {
            public float quantum_objective;
            public float classical_objective;
            public float objective_gap;
            public bool objectives_match;
            public float quantum_execution_time_ms;
            public float classical_execution_time_ms;
        }
    }
}