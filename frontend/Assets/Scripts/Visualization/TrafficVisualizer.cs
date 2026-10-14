using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Networking;

namespace QuantumCity.Visualization
{
    public class TrafficVisualizer : MonoBehaviour
    {
        [Header("Backend")]
        [SerializeField] private string backendUrl = "http://127.0.0.1:8000";

        [Header("Traffic")]
        [SerializeField] private Transform trafficParent;
        [SerializeField] private GameObject carPrefab;

        [Header("Road Area")]
        [SerializeField] private float roadMinX = -60f;
        [SerializeField] private float roadMaxX = 60f;
        [SerializeField] private float roadMinZ = -60f;
        [SerializeField] private float roadMaxZ = 60f;

        [Header("Cars")]
        [SerializeField] private int initialCars = 20;
        [SerializeField] private int maximumVisibleCars = 50;
        [SerializeField] private float carSpeed = 5f;
        [SerializeField] private float carHeight = 0.6f;

        [Header("Simulation")]
        [SerializeField] private bool autoRunSimulation = true;
        [SerializeField] private float refreshInterval = 5f;

        [Header("Debug")]
        [SerializeField] private bool showDebugLogs = true;

        private readonly List<GameObject> cars =
            new List<GameObject>();

        private float trafficSpeed = 5f;
        private float congestion = 0.4f;
        private bool simulationRunning;

        private void Awake()
        {
            if (trafficParent == null)
                trafficParent = transform;
        }

        private void Start()
        {
            // If the full Interactive Traffic System is active in the scene,
            // yield traffic simulation to it so duplicate cars don't randomly disappear or overlap.
            if (FindAnyObjectByType<QuantumCity.Traffic.InteractiveTrafficSystem>() != null)
            {
                Debug.Log("[TrafficVisualizer] InteractiveTrafficSystem is active; disabling visualizer to prevent duplicate cars.");
                gameObject.SetActive(false);
                return;
            }

            // IMPORTANT:
            // Spawn cars immediately so the city is never empty.
            CreateCars(initialCars);

            StartCoroutine(CheckBackend());

            if (autoRunSimulation)
                StartCoroutine(AutoSimulationLoop());

            if (showDebugLogs)
            {
                Debug.Log(
                    "[TrafficVisualizer] Traffic system started. Cars: " +
                    cars.Count
                );
            }
        }

        private void Update()
        {
            MoveCars();
        }

        // =========================================================
        // CREATE CARS
        // =========================================================

        private void CreateCars(int count)
        {
            count = Mathf.Clamp(
                count,
                0,
                maximumVisibleCars
            );

            while (cars.Count < count)
            {
                GameObject car =
                    CreateSingleCar(cars.Count);

                if (car == null)
                    break;

                cars.Add(car);
            }

            while (cars.Count > count)
            {
                GameObject car =
                    cars[cars.Count - 1];

                cars.RemoveAt(cars.Count - 1);

                if (car != null)
                    Destroy(car);
            }
        }

        private GameObject CreateSingleCar(int index)
        {
            GameObject car;

            if (carPrefab != null)
            {
                car = Instantiate(
                    carPrefab,
                    trafficParent
                );
            }
            else
            {
                // Automatic low-poly car
                car = GameObject.CreatePrimitive(
                    PrimitiveType.Cube
                );

                car.transform.SetParent(
                    trafficParent
                );

                car.name =
                    "SUMO_Car_" +
                    index.ToString("00");

                car.transform.localScale =
                    new Vector3(
                        1.2f,
                        0.5f,
                        2.2f
                    );

                Renderer renderer =
                    car.GetComponent<Renderer>();

                if (renderer != null)
                {
                    Material material =
                        new Material(
                            Shader.Find(
                                "Universal Render Pipeline/Lit"
                            )
                        );

                    material.color =
                        new Color(
                            0.05f,
                            0.55f,
                            1.0f
                        );

                    renderer.material = material;
                }
            }

            PlaceCar(
                car,
                index
            );

            return car;
        }

        // =========================================================
        // PLACE CARS ON CITY ROADS
        // =========================================================

        private void PlaceCar(
            GameObject car,
            int index)
        {
            int roadIndex =
                index % 10;

            bool horizontal =
                index % 2 == 0;

            float spacing = 12f;

            if (horizontal)
            {
                float z =
                    -54f +
                    roadIndex * spacing;

                float x =
                    Mathf.Lerp(
                        roadMinX,
                        roadMaxX,
                        (index % 7) / 6f
                    );

                car.transform.position =
                    new Vector3(
                        x,
                        carHeight,
                        z
                    );

                car.transform.rotation =
                    Quaternion.Euler(
                        0f,
                        90f,
                        0f
                    );
            }
            else
            {
                float x =
                    -54f +
                    roadIndex * spacing;

                float z =
                    Mathf.Lerp(
                        roadMinZ,
                        roadMaxZ,
                        (index % 7) / 6f
                    );

                car.transform.position =
                    new Vector3(
                        x,
                        carHeight,
                        z
                    );

                car.transform.rotation =
                    Quaternion.identity;
            }
        }

        // =========================================================
        // MOVE CARS
        // =========================================================

        private void MoveCars()
        {
            if (cars.Count == 0)
                return;

            float congestionMultiplier =
                Mathf.Lerp(
                    1f,
                    0.2f,
                    Mathf.Clamp01(congestion)
                );

            float speed =
                trafficSpeed *
                congestionMultiplier;

            for (int i = 0; i < cars.Count; i++)
            {
                GameObject car = cars[i];

                if (car == null)
                    continue;

                bool horizontal =
                    i % 2 == 0;

                Vector3 position =
                    car.transform.position;

                if (horizontal)
                {
                    position.x +=
                        speed *
                        Time.deltaTime;

                    if (position.x > roadMaxX)
                        position.x = roadMinX;
                }
                else
                {
                    position.z +=
                        speed *
                        Time.deltaTime;

                    if (position.z > roadMaxZ)
                        position.z = roadMinZ;
                }

                car.transform.position =
                    position;
            }
        }

        // =========================================================
        // BACKEND
        // =========================================================

        private IEnumerator CheckBackend()
        {
            using (UnityWebRequest request =
                   UnityWebRequest.Get(
                       backendUrl + "/health"))
            {
                request.timeout = 5;

                yield return request.SendWebRequest();

                if (request.result ==
                    UnityWebRequest.Result.Success)
                {
                    if (showDebugLogs)
                    {
                        Debug.Log(
                            "[TrafficVisualizer] Backend connected."
                        );
                    }
                }
                else
                {
                    Debug.LogWarning(
                        "[TrafficVisualizer] Backend unavailable. " +
                        "Using visual traffic mode."
                    );
                }
            }
        }

        // =========================================================
        // SUMO SIMULATION
        // =========================================================

        public void RunTrafficSimulation()
        {
            if (!simulationRunning)
                StartCoroutine(
                    RunSimulationRequest()
                );
        }

        private IEnumerator RunSimulationRequest()
        {
            simulationRunning = true;

            SimulationRequest payload =
                new SimulationRequest
                {
                    steps = 100
                };

            string json =
                JsonUtility.ToJson(payload);

            byte[] body =
                System.Text.Encoding.UTF8.GetBytes(
                    json
                );

            using (UnityWebRequest request =
                   new UnityWebRequest(
                       backendUrl + "/simulation/run",
                       UnityWebRequest.kHttpVerbPOST))
            {
                request.uploadHandler =
                    new UploadHandlerRaw(body);

                request.downloadHandler =
                    new DownloadHandlerBuffer();

                request.SetRequestHeader(
                    "Content-Type",
                    "application/json"
                );

                request.timeout = 120;

                yield return request.SendWebRequest();

                if (request.result !=
                    UnityWebRequest.Result.Success)
                {
                    Debug.LogError(
                        "[TrafficVisualizer] SUMO failed: " +
                        request.error
                    );

                    simulationRunning = false;
                    yield break;
                }

                SimulationResponse result =
                    JsonUtility.FromJson<SimulationResponse>(
                        request.downloadHandler.text
                    );

                if (result != null)
                {
                    ApplySUMOResult(result);
                }
            }

            simulationRunning = false;
        }

        // =========================================================
        // SUMO RESULT
        // =========================================================

        private void ApplySUMOResult(
            SimulationResponse result)
        {
            int vehicleCount =
                Mathf.Clamp(
                    result.peak_active_vehicles,
                    1,
                    maximumVisibleCars
                );

            CreateCars(vehicleCount);

            congestion =
                Mathf.Clamp01(
                    result.congestion_index
                );

            float normalizedSpeed =
                Mathf.Clamp01(
                    result.average_speed / 13.9f
                );

            trafficSpeed =
                Mathf.Lerp(
                    1.5f,
                    carSpeed,
                    normalizedSpeed
                );

            if (showDebugLogs)
            {
                Debug.Log(
                    "[TrafficVisualizer] SUMO RESULT\n" +
                    "Vehicles: " +
                    result.peak_active_vehicles +
                    "\nAverage Speed: " +
                    result.average_speed.ToString("F2") +
                    " m/s" +
                    "\nCongestion: " +
                    (congestion * 100f).ToString("F1") +
                    "%"
                );
            }
        }

        // =========================================================
        // AUTOMATIC SIMULATION
        // =========================================================

        private IEnumerator AutoSimulationLoop()
        {
            // Give Unity a moment to initialise.
            yield return new WaitForSeconds(2f);

            while (true)
            {
                if (!simulationRunning)
                    yield return RunSimulationRequest();

                yield return new WaitForSeconds(
                    refreshInterval
                );
            }
        }

        // =========================================================
        // JSON
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
    }
}
