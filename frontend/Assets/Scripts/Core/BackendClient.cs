using System;
using System.Text;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.Networking;

namespace QuantumCity.Core
{
    [Serializable]
    public class TrafficObservation
    {
        public int vehicle_count;
        public float average_speed;
        public int halted_vehicles;
        public float time_step;
    }

    [Serializable]
    public class TrafficPrediction
    {
        public float predicted_congestion_level;
        public float confidence_score;
    }

    [Serializable]
    public class EnergyObservation
    {
        public float temperature;
        public int hour_of_day;
        public int population;
        public float industrial_activity;
    }

    [Serializable]
    public class EnergyPrediction
    {
        public float predicted_demand_mw;
        public float confidence_score;
    }

    [Serializable]
    public class ZoneDemand
    {
        public string id;
        public float demand;
        public int priority;
    }

    [Serializable]
    public class CityResourceProblem
    {
        public ZoneDemand[] zones;
        public float total_budget;
    }

    [Serializable]
    public class ZoneAllocation
    {
        public string zone_id;
        public float allocated_budget;
    }

    [Serializable]
    public class QuantumSolverResult
    {
        public ZoneAllocation[] allocations;
        public float total_allocated;
        public float optimal_value;
        public string solver_backend;
        public float execution_time_ms;
    }

    [Serializable]
    public class SimulationRunRequest
    {
        public int steps;
        public float step_length;
        public bool gui;
        public string sumo_config_path;
    }

    [Serializable]
    public class TrafficSimulationResult
    {
        public TrafficObservation[] observations;
        public float execution_time_ms;
    }

    /// <summary>
    /// Handles communication with the FastAPI backend.
    /// </summary>
    public class BackendClient
    {
        private readonly string baseUrl = "http://127.0.0.1:8000";

        public async Task<TrafficSimulationResult> RunSimulation(SimulationRunRequest request)
        {
            return await PostJson<TrafficSimulationResult>("/simulation/run", request);
        }

        public async Task<TrafficPrediction> PredictTraffic(TrafficObservation request)
        {
            return await PostJson<TrafficPrediction>("/prediction/traffic", request);
        }

        public async Task<EnergyPrediction> PredictEnergy(EnergyObservation request)
        {
            return await PostJson<EnergyPrediction>("/prediction/energy", request);
        }

        public async Task<QuantumSolverResult> OptimizeQuantum(CityResourceProblem request)
        {
            return await PostJson<QuantumSolverResult>("/optimization/quantum", request);
        }

        private async Task<T> PostJson<T>(string endpoint, object payload)
        {
            string url = baseUrl + endpoint;
            string jsonPayload = JsonUtility.ToJson(payload);

            using (UnityWebRequest www = new UnityWebRequest(url, "POST"))
            {
                byte[] bodyRaw = Encoding.UTF8.GetBytes(jsonPayload);
                www.uploadHandler = new UploadHandlerRaw(bodyRaw);
                www.downloadHandler = new DownloadHandlerBuffer();
                www.SetRequestHeader("Content-Type", "application/json");

                var operation = www.SendWebRequest();

                while (!operation.isDone)
                    await Task.Yield();

                if (www.result == UnityWebRequest.Result.ConnectionError || www.result == UnityWebRequest.Result.ProtocolError)
                {
                    Debug.LogError($"[BackendClient] Error posting to {endpoint}: {www.error}\n{www.downloadHandler.text}");
                    return default;
                }

                return JsonUtility.FromJson<T>(www.downloadHandler.text);
            }
        }
    }
}
