using UnityEngine;
using UnityEngine.UI;
using TMPro;
using QuantumCity.Core;

namespace QuantumCity.UI
{
    /// <summary>
    /// Orchestrates communication between the UI and BackendClient.
    /// Dynamically constructs the control buttons on the Dashboard side panel.
    /// </summary>
    public class APIManager : MonoBehaviour
    {
        private BackendClient _client;
        private DashboardController _dashboard;

        // Current state
        private TrafficObservation _lastTrafficObs;

        private void Start()
        {
            _client = new BackendClient();
            _dashboard = FindFirstObjectByType<DashboardController>();

            if (_dashboard != null)
            {
                ConstructUIButtons();
                _dashboard.SetCityName("Quantum City (Connected)");
                _dashboard.SetPopulation(125000);
            }
            else
            {
                Debug.LogError("[APIManager] DashboardController not found.");
            }
        }

        private void ConstructUIButtons()
        {
            // Find or create the side panel inside the canvas
            Transform sidePanel = _dashboard.transform.Find("SidePanel");
            if (sidePanel == null)
            {
                // Create a side panel dynamically if it doesn't exist
                GameObject panelGo = new GameObject("SidePanel");
                sidePanel = panelGo.transform;
                sidePanel.SetParent(_dashboard.transform, false);
                
                RectTransform rt = panelGo.AddComponent<RectTransform>();
                rt.anchorMin = new Vector2(1, 0);
                rt.anchorMax = new Vector2(1, 1);
                rt.pivot = new Vector2(1, 0.5f);
                rt.sizeDelta = new Vector2(250, 0); // 250 width, stretch height
                rt.anchoredPosition = Vector2.zero;

                Image img = panelGo.AddComponent<Image>();
                img.color = new Color(0.05f, 0.1f, 0.2f, 0.8f);

                VerticalLayoutGroup vlg = panelGo.AddComponent<VerticalLayoutGroup>();
                vlg.padding = new RectOffset(20, 20, 50, 20);
                vlg.spacing = 15;
                vlg.childControlHeight = true;
                vlg.childControlWidth = true;
                vlg.childForceExpandHeight = false;
            }

            CreateButton(sidePanel, "Run Simulation", OnRunSimulation);
            CreateButton(sidePanel, "Predict Traffic", OnPredictTraffic);
            CreateButton(sidePanel, "Predict Energy", OnPredictEnergy);
            CreateButton(sidePanel, "Quantum Optimization", OnQuantumOptimization);
        }

        private void CreateButton(Transform parent, string label, UnityEngine.Events.UnityAction action)
        {
            GameObject btnGo = new GameObject($"Btn_{label.Replace(" ", "")}");
            btnGo.transform.SetParent(parent, false);

            Image img = btnGo.AddComponent<Image>();
            img.color = new Color(0.1f, 0.3f, 0.5f, 1f);

            Button btn = btnGo.AddComponent<Button>();
            btn.onClick.AddListener(action);

            LayoutElement le = btnGo.AddComponent<LayoutElement>();
            le.minHeight = 40;

            GameObject textGo = new GameObject("Text");
            textGo.transform.SetParent(btnGo.transform, false);
            
            TextMeshProUGUI tmp = textGo.AddComponent<TextMeshProUGUI>();
            tmp.text = label;
            tmp.fontSize = 16;
            tmp.alignment = TextAlignmentOptions.Center;
            tmp.color = Color.white;
            
            RectTransform textRt = textGo.GetComponent<RectTransform>();
            textRt.anchorMin = Vector2.zero;
            textRt.anchorMax = Vector2.one;
            textRt.sizeDelta = Vector2.zero;
        }

        private async void OnRunSimulation()
        {
            _dashboard.SetSimStatus("SIMULATING...");
            
            var req = new SimulationRunRequest { steps = 50, step_length = 1.0f, gui = false, sumo_config_path = null };
            var result = await _client.RunSimulation(req);
            
            if (result != null && result.observations.Length > 0)
            {
                _lastTrafficObs = result.observations[result.observations.Length - 1];
                _dashboard.SetSimStatus("SIM COMPLETE");
                _dashboard.SetTrafficFlow(_lastTrafficObs.average_speed * 3.6f); // Convert m/s to km/h visually
                Debug.Log($"[APIManager] Simulation complete in {result.execution_time_ms}ms.");
            }
            else
            {
                _dashboard.SetSimStatus("SIM ERROR");
            }
        }

        private async void OnPredictTraffic()
        {
            if (_lastTrafficObs == null)
            {
                Debug.LogWarning("[APIManager] Run simulation first to get observations.");
                _dashboard.SetSimStatus("NO TRAFFIC DATA");
                return;
            }

            _dashboard.SetSimStatus("PREDICTING TRAFFIC...");
            var result = await _client.PredictTraffic(_lastTrafficObs);
            
            if (result != null)
            {
                _dashboard.SetSimStatus($"TRAFFIC PREDICTED ({result.confidence_score*100:F0}% conf)");
                _dashboard.SetTrafficFlow(result.predicted_congestion_level * 100f); // Display as %
            }
            else
            {
                _dashboard.SetSimStatus("PREDICT ERROR");
            }
        }

        private async void OnPredictEnergy()
        {
            _dashboard.SetSimStatus("PREDICTING ENERGY...");
            
            var obs = new EnergyObservation { temperature = 22.5f, hour_of_day = 14, population = 125000, industrial_activity = 0.8f };
            var result = await _client.PredictEnergy(obs);
            
            if (result != null)
            {
                _dashboard.SetSimStatus($"ENERGY PREDICTED ({result.confidence_score*100:F0}% conf)");
                _dashboard.SetEnergy(result.predicted_demand_mw);
            }
            else
            {
                _dashboard.SetSimStatus("PREDICT ERROR");
            }
        }

        private async void OnQuantumOptimization()
        {
            _dashboard.SetSimStatus("OPTIMIZING (QAOA)...");

            var problem = new CityResourceProblem
            {
                total_budget = 500f,
                zones = new ZoneDemand[]
                {
                    new ZoneDemand { id = "Z1", demand = 120, priority = 3 },
                    new ZoneDemand { id = "Z2", demand = 200, priority = 1 },
                    new ZoneDemand { id = "Z3", demand = 150, priority = 2 }
                }
            };

            var result = await _client.OptimizeQuantum(problem);

            if (result != null)
            {
                _dashboard.SetSimStatus($"QAOA OPTIMIZED ({result.execution_time_ms:F0}ms)");
                Debug.Log($"[APIManager] Quantum Optimal Value: {result.optimal_value}");
            }
            else
            {
                _dashboard.SetSimStatus("QAOA ERROR");
            }
        }
    }
}
