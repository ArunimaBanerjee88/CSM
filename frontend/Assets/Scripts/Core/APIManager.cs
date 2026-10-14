using System.Collections;
using UnityEngine;
using UnityEngine.Networking;

public class APIManager : MonoBehaviour
{
    public static APIManager Instance;

    [Header("Backend")]
    [SerializeField] private string baseUrl = "http://127.0.0.1:8000";

    public bool BackendConnected { get; private set; }

    private void Awake()
    {
        if (Instance != null && Instance != this)
        {
            Destroy(gameObject);
            return;
        }

        Instance = this;
        DontDestroyOnLoad(gameObject);
    }

    private void Start()
    {
        CheckBackend();
    }

    public void CheckBackend()
    {
        StartCoroutine(GetRequest("/health"));
    }

    public void RunSimulation()
    {
        string json = @"{
            ""world_id"": ""world_baseline_2030"",
            ""steps"": 100,
            ""step_length"": 1.0,
            ""headless"": true
        }";

        StartCoroutine(PostRequest("/simulation/run", json));
    }

    public void PredictTraffic()
    {
        string json = @"{
            ""step"": 50,
            ""simulation_time"": 50.0,
            ""active_vehicle_count"": 15,
            ""average_vehicle_speed"": 8.0,
            ""total_waiting_time"": 50.0
        }";

        StartCoroutine(PostRequest("/prediction/traffic", json));
    }

    public void PredictEnergy()
    {
        string json = @"{
            ""current_energy_demand"": 3000.0,
            ""simulation_time"": 50.0,
            ""renewable_energy_percentage"": 25.0,
            ""active_vehicle_count"": 15,
            ""traffic_congestion_index"": 0.4
        }";

        StartCoroutine(PostRequest("/prediction/energy", json));
    }

    public void QuantumOptimize()
    {
        string json = @"{
            ""predicted_energy_demand_mw"": 2880.76,
            ""active_vehicle_count"": 15,
            ""traffic_congestion_index"": 0.4,
            ""num_zones"": 4,
            ""max_allocations"": 2,
            ""budget_penalty_weight"": 5.0
        }";

        StartCoroutine(PostRequest("/optimization/quantum", json));
    }

    private IEnumerator GetRequest(string endpoint)
    {
        string url = baseUrl + endpoint;

        using (UnityWebRequest request = UnityWebRequest.Get(url))
        {
            request.timeout = 10;

            yield return request.SendWebRequest();

            if (request.result == UnityWebRequest.Result.Success)
            {
                BackendConnected = true;

                Debug.Log("[API] Backend connected");
                Debug.Log("[API] Response: " + request.downloadHandler.text);
            }
            else
            {
                BackendConnected = false;

                Debug.LogError(
                    "[API] Backend connection failed: " +
                    request.error
                );
            }
        }
    }

    private IEnumerator PostRequest(string endpoint, string json)
    {
        string url = baseUrl + endpoint;

        using (UnityWebRequest request = new UnityWebRequest(url, "POST"))
        {
            byte[] body = System.Text.Encoding.UTF8.GetBytes(json);

            request.uploadHandler = new UploadHandlerRaw(body);
            request.downloadHandler = new DownloadHandlerBuffer();

            request.SetRequestHeader(
                "Content-Type",
                "application/json"
            );

            request.timeout = 120;

            Debug.Log("[API] POST " + endpoint);

            yield return request.SendWebRequest();

            if (request.result == UnityWebRequest.Result.Success)
            {
                Debug.Log(
                    "[API] " + endpoint +
                    " SUCCESS\n" +
                    request.downloadHandler.text
                );
            }
            else
            {
                Debug.LogError(
                    "[API] " + endpoint +
                    " FAILED\n" +
                    request.error +
                    "\nResponse: " +
                    request.downloadHandler.text
                );
            }
        }
    }
}