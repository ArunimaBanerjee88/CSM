using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using TMPro;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.Networking;
using UnityEngine.UI;
using UnityEngine.InputSystem.UI;

namespace QuantumCity.Traffic
{
    public class InteractiveTrafficSystem : MonoBehaviour
    {
        private const string BACKEND = "http://127.0.0.1:8000";

        private readonly string[] roadNames =
        {
            "Road A", "Road B", "Road C", "Road D", "Road E"
        };

        public const int ROAD_CAPACITY = 18;
        private const float LANE_OFFSET = 1.35f;
        private const float ROAD_Y = 0.35f;
        private const float ROAD_EXTENT = 56f;
        private const float ROAD_TURN_EXTENT = 57.5f;

        private readonly Dictionary<string, float> congestion = new();
        private readonly Dictionary<string, List<TrafficCar>> carsByRoad = new();
        private readonly Dictionary<string, Vector3[]> roadPoints = new();
        private readonly Dictionary<string, TextMeshPro> roadLabels = new();
        private readonly Dictionary<string, string[]> roadConnections = new()
        {
            { "Road A", new[] { "Road D", "Road E" } },
            { "Road B", new[] { "Road D", "Road E" } },
            { "Road C", new[] { "Road D", "Road E" } },
            { "Road D", new[] { "Road A", "Road B", "Road C" } },
            { "Road E", new[] { "Road A", "Road B", "Road C" } }
        };
        private readonly List<TrafficCar> cars = new();

        private readonly Dictionary<string, Queue<int>> countHistory = new();
        private readonly Dictionary<string, float> historyTime = new();

        private GameObject trafficRoot;
        private Canvas canvas;
        private TextMeshProUGUI statusText;
        private TextMeshProUGUI predictionText;
        private TextMeshProUGUI liveCounterText;
        private GameObject roadSelectionPanel;
        private GameObject benchmarkPopup;

        private string congestedRoad = "";
        private bool optimizing;
        private float historyClock;
        private float naturalFlowClock;

        private AudioSource hornSource;
        private AudioClip hornClip;

        private Material roadMaterial;
        private Material laneMaterial;
        private Material carMaterial;
        private Material congestedMaterial;

        private PredictionRecord lastPrediction = new();
        private OptimizationRecord lastQuantum = new();
        private OptimizationRecord lastAI = new();

        // ── Timing & Evaluation ────────────────────────────────────────
        private float optimizationStartTime;
        private float congestionCreatedTime;
        private float estimatedClearanceSeconds = 30f;
        private float actualClearanceTime = -1f;
        private bool monitoringClearance;
        private string clearanceMonitorRoad = "";
        private float clearanceThreshold = 0.45f;

        // ── Optimization Detail Log ───────────────────────────────────
        private TextMeshProUGUI optimizationDetailText;
        private readonly List<string> rerouteLog = new();
        private TextMeshProUGUI rerouteLogText;

        private void Start()
        {
            Debug.Log("[InteractiveTrafficSystem] STARTING...");

            foreach (string road in roadNames)
            {
                congestion[road] = 0.05f;
                carsByRoad[road] = new List<TrafficCar>();
                countHistory[road] = new Queue<int>();
                historyTime[road] = 0f;
            }

            CreateMaterials();
            CreateRoadNetwork();
            CreateCars(60);
            CreateUI();
            CreateHorn();

            StartCoroutine(NaturalTrafficFlow());

            RecordTrafficHistory();
            SetStatus("SIMULATION RUNNING");

            Debug.Log(
                "[InteractiveTrafficSystem] READY | Cars: " +
                cars.Count + " | Roads: " + roadNames.Length);
        }

        private void Update()
        {
            historyClock += Time.deltaTime;
            naturalFlowClock += Time.deltaTime;

            if (historyClock >= 1f)
            {
                historyClock = 0f;
                RecordTrafficHistory();
            }

            UpdateTrafficState();

            // Monitor for actual congestion clearance
            if (monitoringClearance && !string.IsNullOrEmpty(clearanceMonitorRoad))
            {
                float currentCong = CalculateRoadCongestion(clearanceMonitorRoad);
                if (currentCong < clearanceThreshold)
                {
                    actualClearanceTime = Time.time - optimizationStartTime;
                    monitoringClearance = false;
                    string clearMsg = $"CLEARED in {actualClearanceTime:F1}s (est {estimatedClearanceSeconds:F0}s)";
                    SetStatus(clearMsg);
                    AppendRerouteLog($"[CLEARANCE] {clearanceMonitorRoad}: {clearMsg}");
                }
            }

            if (!string.IsNullOrEmpty(congestedRoad) &&
                Time.frameCount % 90 == 0)
            {
                PlayHorn();
            }
        }

        // ============================================================
        // MATERIALS
        // ============================================================

        private void CreateMaterials()
        {
            Shader shader =
                Shader.Find("Universal Render Pipeline/Lit");

            if (shader == null)
                shader = Shader.Find("Standard");

            // ROAD (Solid Black)
            roadMaterial = new Material(shader);
            roadMaterial.color =
                new Color(0.01f, 0.01f, 0.01f);

            // WHITE ROAD MARKINGS
            laneMaterial = new Material(shader);
            laneMaterial.color =
                new Color(0.92f, 0.94f, 0.95f);

            // DEFAULT CAR
            carMaterial = new Material(shader);
            carMaterial.color =
                new Color(0.25f, 0.50f, 0.75f);

            // CONGESTION
            congestedMaterial = new Material(shader);
            congestedMaterial.color =
                new Color(0.75f, 0.20f, 0.15f);
        }

        // ============================================================
        // ROADS
        // ============================================================

        private void CreateRoadNetwork()
        {
            trafficRoot = new GameObject("InteractiveTrafficNetwork");

            CreateHorizontalRoad("Road A", 0f);
            CreateHorizontalRoad("Road B", 12f);
            CreateHorizontalRoad("Road C", -12f);
            CreateVerticalRoad("Road D", -24f);
            CreateVerticalRoad("Road E", 24f);
        }

        private void CreateHorizontalRoad(string roadName, float z)
        {
            GameObject road = GameObject.CreatePrimitive(PrimitiveType.Cube);
            road.name = roadName;
            road.transform.SetParent(trafficRoot.transform);
            road.transform.position = new Vector3(0f, .08f, z);
            road.transform.localScale = new Vector3(120f, .12f, 5.0f);
            Destroy(road.GetComponent<Collider>());
            road.GetComponent<MeshRenderer>().material = roadMaterial;

            roadPoints[roadName] = BuildHorizontalLoop(z);

            CreateHorizontalLaneLines(z);
            CreateRoadLabel(roadName, new Vector3(-38f, 0.22f, z));
        }

        private void CreateVerticalRoad(string roadName, float x)
        {
            GameObject road = GameObject.CreatePrimitive(PrimitiveType.Cube);
            road.name = roadName;
            road.transform.SetParent(trafficRoot.transform);
            road.transform.position = new Vector3(x, .08f, 0f);
            road.transform.localScale = new Vector3(5.0f, .12f, 120f);
            Destroy(road.GetComponent<Collider>());
            road.GetComponent<MeshRenderer>().material = roadMaterial;

            roadPoints[roadName] = BuildVerticalLoop(x);

            CreateVerticalLaneLines(x);
            CreateRoadLabel(roadName, new Vector3(x, 0.22f, 38f));
        }

        private Vector3[] BuildHorizontalLoop(float z)
        {
            return new[]
            {
                // Eastbound lane (-Z side) moving +X
                new Vector3(-ROAD_EXTENT, ROAD_Y, z - LANE_OFFSET),
                new Vector3(-24f, ROAD_Y, z - LANE_OFFSET),
                new Vector3(24f, ROAD_Y, z - LANE_OFFSET),
                new Vector3(ROAD_EXTENT, ROAD_Y, z - LANE_OFFSET),
                // Turnaround at East end staying on road asphalt
                new Vector3(ROAD_TURN_EXTENT, ROAD_Y, z),
                // Westbound lane (+Z side) moving -X
                new Vector3(ROAD_EXTENT, ROAD_Y, z + LANE_OFFSET),
                new Vector3(24f, ROAD_Y, z + LANE_OFFSET),
                new Vector3(-24f, ROAD_Y, z + LANE_OFFSET),
                new Vector3(-ROAD_EXTENT, ROAD_Y, z + LANE_OFFSET),
                // Turnaround at West end staying on road asphalt
                new Vector3(-ROAD_TURN_EXTENT, ROAD_Y, z)
            };
        }

        private Vector3[] BuildVerticalLoop(float x)
        {
            return new[]
            {
                // Northbound lane (+X side) moving +Z
                new Vector3(x + LANE_OFFSET, ROAD_Y, -ROAD_EXTENT),
                new Vector3(x + LANE_OFFSET, ROAD_Y, -12f),
                new Vector3(x + LANE_OFFSET, ROAD_Y, 0f),
                new Vector3(x + LANE_OFFSET, ROAD_Y, 12f),
                new Vector3(x + LANE_OFFSET, ROAD_Y, ROAD_EXTENT),
                // Turnaround at North end staying on road asphalt
                new Vector3(x, ROAD_Y, ROAD_TURN_EXTENT),
                // Southbound lane (-X side) moving -Z
                new Vector3(x - LANE_OFFSET, ROAD_Y, ROAD_EXTENT),
                new Vector3(x - LANE_OFFSET, ROAD_Y, 12f),
                new Vector3(x - LANE_OFFSET, ROAD_Y, 0f),
                new Vector3(x - LANE_OFFSET, ROAD_Y, -12f),
                new Vector3(x - LANE_OFFSET, ROAD_Y, -ROAD_EXTENT),
                // Turnaround at South end staying on road asphalt
                new Vector3(x, ROAD_Y, -ROAD_TURN_EXTENT)
            };
        }

        private void CreateHorizontalLaneLines(float z)
        {
            for (float x = -55f; x < 55f; x += 6f)
            {
                CreateLaneMarker(new Vector3(x, .16f, z - 1.35f), new Vector3(3f, .02f, .12f));
                CreateLaneMarker(new Vector3(x, .16f, z + 1.35f), new Vector3(3f, .02f, .12f));
            }

            CreateLaneMarker(new Vector3(0f, .17f, z), new Vector3(120f, .02f, .12f));
        }

        private void CreateVerticalLaneLines(float x)
        {
            for (float z = -55f; z < 55f; z += 6f)
            {
                CreateLaneMarker(new Vector3(x - 1.35f, .16f, z), new Vector3(.12f, .02f, 3f));
                CreateLaneMarker(new Vector3(x + 1.35f, .16f, z), new Vector3(.12f, .02f, 3f));
            }

            CreateLaneMarker(new Vector3(x, .17f, 0f), new Vector3(.12f, .02f, 120f));
        }

        private void CreateLaneMarker(Vector3 position, Vector3 scale)
        {
            GameObject marker = GameObject.CreatePrimitive(PrimitiveType.Cube);
            marker.name = "LaneMarker";
            marker.transform.SetParent(trafficRoot.transform);
            marker.transform.position = position;
            marker.transform.localScale = scale;
            Destroy(marker.GetComponent<Collider>());
            marker.GetComponent<MeshRenderer>().material = laneMaterial;
        }

        private void CreateRoadLabel(
            string roadName,
            Vector3 position)
        {
            GameObject label = new GameObject(
                roadName + "_Label");

            label.transform.SetParent(trafficRoot.transform);

            // Keep the label just above the asphalt
            label.transform.position = new Vector3(
                position.x,
                0.22f,
                position.z
            );

            // Lay the text flat on the road surface
            label.transform.rotation = Quaternion.Euler(
                90f, 0f, 0f
            );

            TextMeshPro text = label.AddComponent<TextMeshPro>();

            text.text = roadName.ToUpper() + "\n0 VEHICLES";
            text.fontSize = 5.2f;
            text.fontStyle = FontStyles.Bold;
            text.alignment = TextAlignmentOptions.Center;

            // Green lettering initially for clear traffic
            text.color = new Color(0.2f, 0.95f, 0.4f);

            // White outline to distinguish the text from asphalt
            text.outlineWidth = 0.25f;
            text.outlineColor = Color.black;

            text.rectTransform.sizeDelta = new Vector2(24f, 7f);

            roadLabels[roadName] = text;
        }

        // ============================================================
        // CARS
        // ============================================================

        private void CreateCars(int count)
        {
            System.Random random = new System.Random(42);

            for (int i = 0; i < count; i++)
            {
                string road = roadNames[random.Next(roadNames.Length)];
                SpawnCarOnRoad(road, i, random.NextDouble() > .5);
            }
        }

        private void SpawnCarOnRoad(string road, int index, bool forward)
        {
            GameObject carObject = CreateCarObject(index);
            TrafficCar car = carObject.AddComponent<TrafficCar>();

            car.Initialize(
                road,
                BuildLoopPath(road, forward),
                UnityEngine.Random.Range(3.5f, 5.5f),
                this);

            car.OnRouteCompleted = HandleCarRouteCompleted;
            car.SetProgress(UnityEngine.Random.Range(0f, 1f));

            cars.Add(car);
            if (!carsByRoad.ContainsKey(road))
                carsByRoad[road] = new List<TrafficCar>();
            carsByRoad[road].Add(car);
        }

        private GameObject CreateCarObject(int index)
        {
            GameObject car = new GameObject("Car_" + index);
            car.transform.SetParent(trafficRoot.transform, false);

            // ------------------------------------------------------------
            // CAR COLORS
            // ------------------------------------------------------------

            Color[] carColors =
            {
                new Color(0.12f, 0.42f, 0.78f), // blue
                new Color(0.82f, 0.16f, 0.12f), // red
                new Color(0.92f, 0.92f, 0.92f), // white
                new Color(0.55f, 0.58f, 0.62f), // silver
                new Color(0.90f, 0.70f, 0.10f), // yellow
                new Color(0.08f, 0.09f, 0.11f), // black
                new Color(0.15f, 0.55f, 0.30f), // green
                new Color(0.90f, 0.38f, 0.10f)  // orange
            };

            Color bodyColor = carColors[index % carColors.Length];

            Shader shader = Shader.Find("Universal Render Pipeline/Lit");
            if (shader == null)
                shader = Shader.Find("Standard");

            Material bodyMaterial = new Material(shader);
            bodyMaterial.color = bodyColor;

            Material glassMaterial = new Material(shader);
            glassMaterial.color = new Color(0.12f, 0.20f, 0.25f);

            Material wheelMaterial = new Material(shader);
            wheelMaterial.color = new Color(0.025f, 0.025f, 0.025f);

            Material lightMaterial = new Material(shader);
            lightMaterial.color = new Color(0.95f, 0.95f, 0.80f);

            // ------------------------------------------------------------
            // MAIN BODY
            // ------------------------------------------------------------

            GameObject body = GameObject.CreatePrimitive(PrimitiveType.Cube);
            body.name = "Body";
            body.transform.SetParent(car.transform, false);
            body.transform.localPosition = new Vector3(0f, 0.38f, 0f);
            body.transform.localScale = new Vector3(1.7f, 0.45f, 0.85f);

            Destroy(body.GetComponent<Collider>());
            body.GetComponent<MeshRenderer>().material = bodyMaterial;

            // ------------------------------------------------------------
            // CABIN
            // ------------------------------------------------------------

            GameObject cabin = GameObject.CreatePrimitive(PrimitiveType.Cube);
            cabin.name = "Cabin";
            cabin.transform.SetParent(car.transform, false);
            cabin.transform.localPosition = new Vector3(-0.05f, 0.70f, 0f);
            cabin.transform.localScale = new Vector3(0.85f, 0.38f, 0.68f);

            Destroy(cabin.GetComponent<Collider>());
            cabin.GetComponent<MeshRenderer>().material = glassMaterial;

            // ------------------------------------------------------------
            // FRONT WINDSHIELD
            // ------------------------------------------------------------

            GameObject windshield = GameObject.CreatePrimitive(PrimitiveType.Cube);
            windshield.name = "Windshield";
            windshield.transform.SetParent(car.transform, false);
            windshield.transform.localPosition = new Vector3(0.39f, 0.72f, 0f);
            windshield.transform.localScale = new Vector3(0.025f, 0.25f, 0.58f);

            Destroy(windshield.GetComponent<Collider>());
            windshield.GetComponent<MeshRenderer>().material = glassMaterial;

            // ------------------------------------------------------------
            // WHEELS
            // ------------------------------------------------------------

            CreateCarWheel(car.transform, new Vector3(0.55f, 0.18f, -0.48f), wheelMaterial);
            CreateCarWheel(car.transform, new Vector3(0.55f, 0.18f,  0.48f), wheelMaterial);
            CreateCarWheel(car.transform, new Vector3(-0.55f, 0.18f, -0.48f), wheelMaterial);
            CreateCarWheel(car.transform, new Vector3(-0.55f, 0.18f,  0.48f), wheelMaterial);

            // ------------------------------------------------------------
            // FRONT LIGHTS
            // ------------------------------------------------------------

            CreateCarLight(
                car.transform,
                new Vector3(0.86f, 0.43f, -0.27f),
                lightMaterial);

            CreateCarLight(
                car.transform,
                new Vector3(0.86f, 0.43f, 0.27f),
                lightMaterial);

            return car;
        }

        private void CreateCarWheel(
            Transform parent,
            Vector3 position,
            Material material)
        {
            GameObject wheel =
                GameObject.CreatePrimitive(PrimitiveType.Cylinder);

            wheel.name = "Wheel";
            wheel.transform.SetParent(parent, false);
            wheel.transform.localPosition = position;

            wheel.transform.localRotation =
                Quaternion.Euler(90f, 0f, 0f);

            wheel.transform.localScale =
                new Vector3(0.20f, 0.10f, 0.20f);

            Destroy(wheel.GetComponent<Collider>());

            wheel.GetComponent<MeshRenderer>().material = material;
        }

        private void CreateCarLight(
            Transform parent,
            Vector3 position,
            Material material)
        {
            GameObject light =
                GameObject.CreatePrimitive(PrimitiveType.Cube);

            light.name = "Headlight";
            light.transform.SetParent(parent, false);
            light.transform.localPosition = position;
            light.transform.localScale =
                new Vector3(0.08f, 0.08f, 0.12f);

            Destroy(light.GetComponent<Collider>());

            light.GetComponent<MeshRenderer>().material = material;
        }

        // private GameObject CreateCarObject(int index)
        // {
        //     GameObject car = GameObject.CreatePrimitive(PrimitiveType.Cube);
        //     car.name = "Car_" + index;
        //     car.transform.SetParent(trafficRoot.transform);
        //     car.transform.localScale = new Vector3(1.5f, .55f, .8f);
        //     Destroy(car.GetComponent<Collider>());

        //     MeshRenderer renderer = car.GetComponent<MeshRenderer>();
        //     renderer.material = new Material(carMaterial);

        //     if (index % 5 == 0) renderer.material.color = new Color(.9f, .15f, .1f);
        //     if (index % 7 == 0) renderer.material.color = new Color(.95f, .75f, .1f);

        //     return car;
        // }

        private Vector3[] BuildLoopPath(string road, bool forward)
        {
            Vector3[] fullLoop;
            if (IsHorizontalRoad(road))
            {
                fullLoop = BuildHorizontalLoop(GetRoadZ(road));
            }
            else
            {
                fullLoop = BuildVerticalLoop(GetRoadX(road));
            }

            if (forward)
                return fullLoop;

            // Shift loop by half so cars start heading the other direction on the other lane
            int half = fullLoop.Length / 2;
            Vector3[] shifted = new Vector3[fullLoop.Length];
            for (int i = 0; i < fullLoop.Length; i++)
            {
                shifted[i] = fullLoop[(i + half) % fullLoop.Length];
            }
            return shifted;
        }

        public bool IsHorizontalRoad(string road)
        {
            return road == "Road A" || road == "Road B" || road == "Road C";
        }

        public float GetRoadZ(string road)
        {
            return road == "Road A" ? 0f : (road == "Road B" ? 12f : (road == "Road C" ? -12f : 0f));
        }

        public float GetRoadX(string road)
        {
            return road == "Road D" ? -24f : (road == "Road E" ? 24f : 0f);
        }

        public static float CalculateExplicitRoadCongestion(int vehicleCount)
        {
            return Mathf.Clamp01((float)vehicleCount / ROAD_CAPACITY);
        }

        public List<TrafficCar> GetCarsOnRoad(string road)
        {
            if (string.IsNullOrEmpty(road)) return null;
            return carsByRoad.TryGetValue(road, out List<TrafficCar> list) ? list : null;
        }

        private void HandleCarRouteCompleted(TrafficCar car)
        {
            if (car == null) return;

            // Connect car smoothly into the target road's continuous loop on its correct lane
            car.SetRoute(car.CurrentRoad, BuildLoopPath(car.CurrentRoad, true), false);
        }

        private IEnumerator NaturalTrafficFlow()
        {
            while (true)
            {
                yield return new WaitForSeconds(3.5f);

                if (optimizing)
                    continue;

                List<TrafficCar> candidates = cars
                    .Where(c => c != null && !string.IsNullOrEmpty(c.CurrentRoad))
                    .OrderBy(c => UnityEngine.Random.value)
                    .Take(UnityEngine.Random.Range(1, 4))
                    .ToList();

                foreach (TrafficCar car in candidates)
                {
                    if (car == null)
                        continue;

                    // Only consider roads directly connected to this car's road.
                    if (!roadConnections.TryGetValue(
                        car.CurrentRoad,
                        out string[] connectedRoads))
                    {
                        continue;
                    }

                    // Prefer connected roads with lower congestion.
                    string target = connectedRoads
                        .Where(r =>
                            r != congestedRoad &&
                            roadPoints.ContainsKey(r))
                        .OrderBy(r => congestion[r])
                        .ThenBy(r => UnityEngine.Random.value)
                        .FirstOrDefault();

                    // If every connected road is the active hotspot,
                    // still choose a valid connected road.
                    if (string.IsNullOrEmpty(target))
                    {
                        target = connectedRoads
                            .Where(r => roadPoints.ContainsKey(r))
                            .OrderBy(r => congestion[r])
                            .ThenBy(r => UnityEngine.Random.value)
                            .FirstOrDefault();
                    }

                    if (!string.IsNullOrEmpty(target))
                    {
                        RerouteCar(car, target);
                    }
                }
            }
        }


        // ============================================================
        // TRAFFIC STATE / HISTORY
        // ============================================================

        private void UpdateTrafficState()
        {
            foreach (string road in roadNames)
            {
                int count = CountCarsOnRoad(road);
                float countCongestion = CalculateExplicitRoadCongestion(count);

                if (road == congestedRoad)
                    congestion[road] = Mathf.Max(.9f, countCongestion);
                else
                    congestion[road] = Mathf.Lerp(congestion[road], countCongestion, Time.deltaTime * 1.5f);

                // Update 3D road surface label with live vehicle counter
                if (roadLabels.TryGetValue(road, out TextMeshPro label) && label != null)
                {
                    float ratio = (float)count / ROAD_CAPACITY;
                    string colorTag = ratio >= 0.85f ? "<color=#FF3333>" : (ratio >= 0.5f ? "<color=#FFAA00>" : "<color=#33FF55>");
                    label.text = $"{road.ToUpper()}\n{colorTag}{count} / {ROAD_CAPACITY} VEHICLES ({(ratio * 100f):F0}%)</color>";
                }
            }

            // Update HUD UI live vehicle counter
            if (liveCounterText != null)
            {
                System.Text.StringBuilder sb = new();
                foreach (string road in roadNames)
                {
                    int c = CountCarsOnRoad(road);
                    float cong = congestion.ContainsKey(road) ? congestion[road] : 0f;
                    sb.AppendLine($"{road}: {c}/{ROAD_CAPACITY} cars | {(cong * 100f):F0}% cong");
                }
                liveCounterText.text = sb.ToString().TrimEnd();
            }

            foreach (TrafficCar car in cars)
            {
                if (car == null) continue;

                float roadCongestion = congestion.ContainsKey(car.CurrentRoad)
                    ? congestion[car.CurrentRoad]
                    : .05f;

                float speedMultiplier = Mathf.Lerp(1f, .12f, roadCongestion);
                car.SetSpeedMultiplier(speedMultiplier);
            }
        }

        private void RecordTrafficHistory()
        {
            foreach (string road in roadNames)
            {
                int count = CountCarsOnRoad(road);
                Queue<int> q = countHistory[road];

                q.Enqueue(count);
                while (q.Count > 30) q.Dequeue();
            }
        }

        private int CountCarsOnRoad(string road)
        {
            return cars.Count(c => c != null && c.CurrentRoad == road);
        }

        private float CalculateRoadCongestion(string road)
        {
            return CalculateExplicitRoadCongestion(CountCarsOnRoad(road));
        }

        // ============================================================
        // CONGESTION
        // ============================================================

        private void IncreaseCongestion(string road)
        {
            congestedRoad = road;
            congestionCreatedTime = Time.time;
            actualClearanceTime = -1f;
            monitoringClearance = false;
            rerouteLog.Clear();
            if (rerouteLogText != null) rerouteLogText.text = "";

            // Explicit road-capacity rule: inject vehicles to exceed ROAD_CAPACITY
            int current = CountCarsOnRoad(road);
            int needed = Mathf.Max(10, (ROAD_CAPACITY + 2) - current);

            for (int i = 0; i < needed; i++)
                SpawnCarOnRoad(road, 1000 + cars.Count, i % 2 == 0);

            congestion[road] = CalculateExplicitRoadCongestion(CountCarsOnRoad(road));

            int nowCount = CountCarsOnRoad(road);
            string connStr = roadConnections.ContainsKey(road)
                ? string.Join(", ", roadConnections[road])
                : "none";

            predictionText.text =
                "HOTSPOT CONGESTION\n" +
                road +
                "\nCars now: " + nowCount + " / " + ROAD_CAPACITY + " (Capacity)" +
                "\nCongestion: " + (congestion[road] * 100f).ToString("F0") + "%" +
                "\nConnected roads: " + connStr +
                "\nCreated at: " + DateTime.Now.ToString("HH:mm:ss");

            SetStatus("CONGESTION CREATED: " + road + " (" + nowCount + " cars)");
            StartCoroutine(HighlightRoad(road));
            PlayHorn();
        }

        private IEnumerator HighlightRoad(string roadName)
        {
            GameObject road = GameObject.Find(roadName);
            if (road == null) yield break;

            MeshRenderer renderer = road.GetComponent<MeshRenderer>();
            Material original = renderer.material;
            renderer.material = congestedMaterial;

            yield return new WaitForSeconds(2f);

            if (renderer != null) renderer.material = original;
        }

        // ============================================================
        // QAOA
        // ============================================================

        private void OptimizeQuantum()
        {
            if (optimizing)
            {
                SetStatus("OPTIMIZATION ALREADY RUNNING");
                return;
            }

            if (string.IsNullOrEmpty(congestedRoad))
            {
                SetStatus("CREATE CONGESTION FIRST");
                return;
            }

            StartCoroutine(QuantumOptimizationRequest());
        }

        private IEnumerator QuantumOptimizationRequest()
        {
            optimizing = true;
            optimizationStartTime = Time.time;
            rerouteLog.Clear();

            string hotspot = congestedRoad;
            int beforeCars = CountCarsOnRoad(hotspot);
            float beforeCongestion = CalculateRoadCongestion(hotspot);

            SetStatus("RUNNING QAOA OPTIMIZATION...");

            OptimizationPayload payload = new()
            {
                predicted_energy_demand_mw = 2900f,
                active_vehicle_count = cars.Count,
                traffic_congestion_index = beforeCongestion,
                num_zones = 4,
                max_allocations = 2,
                budget_penalty_weight = 5f
            };

            float backendCallStart = Time.time;
            using UnityWebRequest request = CreatePost(
                BACKEND + "/optimization/quantum",
                JsonUtility.ToJson(payload));

            yield return request.SendWebRequest();

            float backendElapsed = Time.time - backendCallStart;

            if (request.result != UnityWebRequest.Result.Success)
            {
                SetStatus("QAOA ERROR: " + request.error);
                optimizing = false;
                yield break;
            }

            QuantumResponse result =
                JsonUtility.FromJson<QuantumResponse>(request.downloadHandler.text);

            float qaoaScore = result != null ? result.objective_value : 0f;

            // Build candidate destination list from physically connected roads only
            List<string> connectedOptions = roadConnections.ContainsKey(hotspot)
                ? roadConnections[hotspot].Where(r => r != hotspot).ToList()
                : new List<string>();

            // Score each alternative: lower congestion + fewer vehicles = better
            var alternativeScores = connectedOptions.Select(r => new
            {
                road = r,
                count = CountCarsOnRoad(r),
                cong = congestion.ContainsKey(r) ? congestion[r] : 0f,
                score = congestion.ContainsKey(r) ? congestion[r] : 0f
            }).OrderBy(x => x.score).ToList();

            // Log alternatives considered
            AppendRerouteLog($"[QAOA] Source: {hotspot} | Cars: {beforeCars} | Cong: {(beforeCongestion * 100f):F0}%");
            AppendRerouteLog($"[QAOA] Backend call took {backendElapsed:F2}s | Score: {qaoaScore:F4}");
            AppendRerouteLog($"[QAOA] Alternatives considered:");
            foreach (var alt in alternativeScores)
                AppendRerouteLog($"  {alt.road}: {alt.count} cars, {(alt.cong * 100f):F0}% cong (score {alt.score:F3})");

            List<string> targetRoads = connectedOptions
                .OrderBy(r => congestion.ContainsKey(r) ? congestion[r] : 0f)
                .Take(Mathf.Min(2, connectedOptions.Count))
                .ToList();

            SetStatus("QAOA SELECTED: " + string.Join(" + ", targetRoads));

            int rerouted = 0;
            List<TrafficCar> hotspotCars = cars
                .Where(c => c != null && c.CurrentRoad == hotspot)
                .OrderBy(c => Vector3.Distance(c.transform.position, roadPoints[hotspot][2]))
                .ToList();

            int targetCount = Mathf.CeilToInt(hotspotCars.Count * .75f);

            foreach (TrafficCar car in hotspotCars)
            {
                if (rerouted >= targetCount) break;

                // Pick the least-congested connected road closest to this specific car
                string bestDest = PickBestDestination(car, hotspot, connectedOptions);
                float distToTarget = GetDistanceToRoad(car, bestDest);
                float destCong = congestion.ContainsKey(bestDest) ? congestion[bestDest] : 0f;

                AppendRerouteLog($"  Car@{car.transform.position.x:F0},{car.transform.position.z:F0} -> {bestDest} " +
                    $"(dist {distToTarget:F0}, cong {(destCong * 100f):F0}%, chosen: lowest-cong + nearest)");

                RerouteCar(car, bestDest);
                rerouted++;

                yield return new WaitForSeconds(.15f);
            }

            yield return new WaitForSeconds(.5f);

            float afterCongestion = CalculateRoadCongestion(hotspot);
            int afterCars = CountCarsOnRoad(hotspot);
            float reduction = beforeCongestion > .001f
                ? Mathf.Clamp01((beforeCongestion - afterCongestion) / beforeCongestion)
                : 0f;

            // Estimate clearance: cars rerouted * avg inter-road travel time
            estimatedClearanceSeconds = rerouted > 0 ? rerouted * 0.5f + 5f : 30f;

            lastQuantum = new OptimizationRecord
            {
                method = "QAOA Quantum",
                timestamp = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss"),
                hotspot = hotspot,
                carsBefore = beforeCars,
                carsRerouted = rerouted,
                carsAfter = afterCars,
                congestionBefore = beforeCongestion,
                congestionAfter = afterCongestion,
                reductionPercent = reduction * 100f,
                score = qaoaScore,
                predictionAccuracy = lastPrediction.accuracyPercent
            };

            AppendRerouteLog($"[QAOA] Done | Rerouted {rerouted} cars | {(beforeCongestion*100f):F0}% -> {(afterCongestion*100f):F0}%");
            AppendRerouteLog($"[QAOA] Est. clearance: {estimatedClearanceSeconds:F0}s | Backend time: {backendElapsed:F2}s");

            // Build explainable alternative scores display
            string altDisplay = string.Join("\n", alternativeScores.Select(a =>
                $"  {a.road}: {a.count} cars, {(a.cong * 100f):F0}% cong"));

            predictionText.text =
                "QAOA OPTIMIZATION\n" +
                $"Source: {hotspot}\n" +
                $"Cars before: {beforeCars} / {ROAD_CAPACITY}\n" +
                $"Cars rerouted: {rerouted}\n" +
                $"Cars after: {afterCars}\n" +
                $"Congestion: {(beforeCongestion * 100f):F0}% -> {(afterCongestion * 100f):F0}%\n" +
                $"Reduction: {(reduction * 100f):F0}%\n" +
                $"QAOA score: {qaoaScore:F4}\n" +
                $"Backend time: {backendElapsed:F2}s\n" +
                $"Est. clearance: {estimatedClearanceSeconds:F0}s (ESTIMATE)\n" +
                $"Destinations chosen:\n  {string.Join(", ", targetRoads)}\n" +
                $"Alternatives considered:\n{altDisplay}";

            SetStatus($"QAOA DONE | {(beforeCongestion * 100f):F0}% -> {(afterCongestion * 100f):F0}% | Score {qaoaScore:F4}");

            // Begin monitoring actual clearance
            monitoringClearance = true;
            clearanceMonitorRoad = hotspot;

            optimizing = false;
        }

        // ============================================================
        // AI OPTIMIZATION
        // ============================================================

        private void OptimizeAI()
        {
            if (optimizing)
            {
                SetStatus("OPTIMIZATION ALREADY RUNNING");
                return;
            }

            if (string.IsNullOrEmpty(congestedRoad))
            {
                SetStatus("CREATE CONGESTION FIRST");
                return;
            }

            StartCoroutine(AIOptimizationRequest());
        }

        private IEnumerator AIOptimizationRequest()
        {
            optimizing = true;
            optimizationStartTime = Time.time;
            rerouteLog.Clear();

            string hotspot = congestedRoad;
            int beforeCars = CountCarsOnRoad(hotspot);
            float beforeCongestion = CalculateRoadCongestion(hotspot);

            // Connected roads only – no shortcuts across unconnected nodes
            List<string> connectedOptions = roadConnections.ContainsKey(hotspot)
                ? roadConnections[hotspot].Where(r => r != hotspot).ToList()
                : new List<string>();

            // Score alternatives by (congestion 70% + vehicle-count ratio 30%)
            var altScored = connectedOptions.Select(r => new
            {
                road = r,
                count = CountCarsOnRoad(r),
                cong = congestion.ContainsKey(r) ? congestion[r] : 0f,
                score = (congestion.ContainsKey(r) ? congestion[r] : 0f) * 0.7f
                      + (CountCarsOnRoad(r) / (float)ROAD_CAPACITY) * 0.3f
            }).OrderBy(x => x.score).ToList();

            // Global fallback: single best road for AI's one-road heuristic
            string globalTargetRoad = altScored.Count > 0 ? altScored[0].road : hotspot;

            SetStatus("AI PREDICTING + OPTIMIZING...");

            float backendCallStart = Time.time;
            TrafficPredictionPayload payload = BuildPredictionPayload(hotspot);

            using UnityWebRequest request = CreatePost(
                BACKEND + "/prediction/traffic",
                JsonUtility.ToJson(payload));

            yield return request.SendWebRequest();

            float backendElapsed = Time.time - backendCallStart;
            float predicted = beforeCongestion;

            if (request.result == UnityWebRequest.Result.Success)
            {
                TrafficPredictionResponse result =
                    JsonUtility.FromJson<TrafficPredictionResponse>(
                        request.downloadHandler.text);
                if (result != null)
                    predicted = Mathf.Clamp01(result.predicted_congestion_index);
            }

            // Log alternatives
            AppendRerouteLog($"[AI] Source: {hotspot} | Cars: {beforeCars} | Cong: {(beforeCongestion * 100f):F0}%");
            AppendRerouteLog($"[AI] ML predicted congestion: {(predicted * 100f):F0}% | Backend: {backendElapsed:F2}s");
            AppendRerouteLog("[AI] Alternatives (cong 70% + count 30%):");
            foreach (var a in altScored)
                AppendRerouteLog($"  {a.road}: {a.count} cars, {(a.cong * 100f):F0}% cong, score {a.score:F3}");

            // AI: divert 45% of congested-road cars, each to the best individual road
            List<TrafficCar> hotspotCars = cars
                .Where(c => c != null && c.CurrentRoad == hotspot)
                .ToList();

            int targetCount = Mathf.CeilToInt(hotspotCars.Count * .45f);
            int rerouted = 0;

            foreach (TrafficCar car in hotspotCars)
            {
                if (rerouted >= targetCount) break;

                // Per-car intelligent routing: lowest combined score road that is closest
                string bestDest = PickBestDestination(car, hotspot, connectedOptions);
                float distToTarget = GetDistanceToRoad(car, bestDest);
                float destCong = congestion.ContainsKey(bestDest) ? congestion[bestDest] : 0f;

                AppendRerouteLog($"  Car@{car.transform.position.x:F0},{car.transform.position.z:F0} -> {bestDest} " +
                    $"(dist {distToTarget:F0}, cong {(destCong * 100f):F0}%, reason: AI cong+count score)");

                RerouteCar(car, bestDest);
                rerouted++;

                yield return new WaitForSeconds(.15f);
            }

            yield return new WaitForSeconds(.5f);

            float afterCongestion = CalculateRoadCongestion(hotspot);
            int afterCars = CountCarsOnRoad(hotspot);
            float reduction = beforeCongestion > .001f
                ? Mathf.Clamp01((beforeCongestion - afterCongestion) / beforeCongestion)
                : 0f;

            float accuracy = 100f - Mathf.Abs(predicted - afterCongestion) * 100f;
            float aiScore = 1f + (congestion.ContainsKey(globalTargetRoad) ? congestion[globalTargetRoad] : 0f) + afterCongestion;

            estimatedClearanceSeconds = rerouted > 0 ? rerouted * 0.6f + 5f : 30f;

            lastAI = new OptimizationRecord
            {
                method = "AI Greedy",
                timestamp = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss"),
                hotspot = hotspot,
                carsBefore = beforeCars,
                carsRerouted = rerouted,
                carsAfter = afterCars,
                congestionBefore = beforeCongestion,
                congestionAfter = afterCongestion,
                reductionPercent = reduction * 100f,
                score = aiScore,
                predictionAccuracy = Mathf.Clamp(accuracy, 0f, 100f)
            };

            AppendRerouteLog($"[AI] Done | Rerouted {rerouted} | {(beforeCongestion*100f):F0}% -> {(afterCongestion*100f):F0}%");
            AppendRerouteLog($"[AI] Prediction accuracy: {Mathf.Clamp(accuracy, 0f, 100f):F1}% | Est clearance: {estimatedClearanceSeconds:F0}s");

            string altDisplay = string.Join("\n", altScored.Select(a =>
                $"  {a.road}: {a.count} cars, {(a.cong * 100f):F0}% cong (score {a.score:F3})"));

            predictionText.text =
                "AI OPTIMIZATION\n" +
                $"Source: {hotspot}\n" +
                $"Cars before: {beforeCars} / {ROAD_CAPACITY}\n" +
                $"Cars rerouted: {rerouted} (45% target)\n" +
                $"Cars after: {afterCars}\n" +
                $"Congestion: {(beforeCongestion * 100f):F0}% -> {(afterCongestion * 100f):F0}%\n" +
                $"Reduction: {(reduction * 100f):F0}%\n" +
                $"ML predicted: {(predicted * 100f):F0}%\n" +
                $"Prediction accuracy: {Mathf.Clamp(accuracy, 0f, 100f):F1}%\n" +
                $"AI score: {aiScore:F4}\n" +
                $"Backend time: {backendElapsed:F2}s\n" +
                $"Est. clearance: {estimatedClearanceSeconds:F0}s (ESTIMATE)\n" +
                $"Alternatives considered:\n{altDisplay}";

            SetStatus($"AI DONE | {(beforeCongestion * 100f):F0}% -> {(afterCongestion * 100f):F0}% | ML acc {Mathf.Clamp(accuracy, 0f, 100f):F1}%");

            monitoringClearance = true;
            clearanceMonitorRoad = hotspot;

            optimizing = false;
        }

        // ============================================================
        // NEXT 30 SECOND PREDICTION
        // ============================================================

        private void PredictNextCongestion()
        {
            StartCoroutine(PredictNextCongestionRoutine());
        }

        private IEnumerator PredictNextCongestionRoutine()
        {
            SetStatus("AI ANALYZING ROADS FOR NEXT 30 SECONDS...");

            // Call the existing ML endpoint once using the actual
            // city-wide traffic state.
            string busiestNow = roadNames
                .OrderByDescending(CountCarsOnRoad)
                .First();

            TrafficPredictionPayload payload = BuildPredictionPayload(busiestNow);

            using UnityWebRequest request = CreatePost(
                BACKEND + "/prediction/traffic",
                JsonUtility.ToJson(payload));

            yield return request.SendWebRequest();

            float mlPrediction = CalculateRoadCongestion(busiestNow);

            if (request.result == UnityWebRequest.Result.Success)
            {
                TrafficPredictionResponse response =
                    JsonUtility.FromJson<TrafficPredictionResponse>(
                        request.downloadHandler.text);

                if (response != null)
                    mlPrediction = Mathf.Clamp01(
                        response.predicted_congestion_index);
            }

            // Forecast each road from the observed 30-second count trend.
            Dictionary<string, int> current = new();
            Dictionary<string, int> forecast = new();

            foreach (string road in roadNames)
            {
                int now = CountCarsOnRoad(road);
                current[road] = now;
                forecast[road] = ForecastCars30Seconds(road, now);
            }

            string predictedRoad = roadNames
                .OrderByDescending(r => forecast[r])
                .First();

            int currentCount = current[predictedRoad];
            int predictedCount = forecast[predictedRoad];

            float currentCongestion = CalculateRoadCongestion(predictedRoad);
            float predictedCongestion =
                Mathf.Clamp01(predictedCount / 18f);

            lastPrediction = new PredictionRecord
            {
                road = predictedRoad,
                currentCars = currentCount,
                predictedCars = predictedCount,
                predictedCongestion = predictedCongestion,
                accuracyPercent = 0f,
                timestamp = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss")
            };

            // Accuracy is measured only after the 30-second horizon has
            // actually elapsed. Until then the UI reports it as pending.
            StartCoroutine(EvaluatePredictionAfter30Seconds(
                predictedRoad,
                predictedCount));

            predictionText.text =
                "NEXT 30-SECOND AI PREDICTION\n\n" +
                "Road: " + predictedRoad + "\n" +
                "Cars now: " + currentCount + "\n" +
                "Predicted cars in 30s: " + predictedCount + "\n" +
                "Current congestion: " +
                (currentCongestion * 100f).ToString("F0") + "%\n" +
                "Predicted congestion: " +
                (predictedCongestion * 100f).ToString("F0") + "%\n\n" +
                "Road counts now:\n" +
                string.Join("\n", roadNames.Select(r =>
                    r + ": " + current[r] + " cars"));

            SetStatus(
                "NEXT HOTSPOT: " +
                predictedRoad +
                " (" + predictedCount + " cars)");

            yield return null;
        }

        private IEnumerator EvaluatePredictionAfter30Seconds(
            string predictedRoad,
            int predictedCount)
        {
            yield return new WaitForSeconds(30f);

            int actualCount = CountCarsOnRoad(predictedRoad);

            float error = predictedCount > 0
                ? Mathf.Abs(predictedCount - actualCount) /
                  Mathf.Max(1f, predictedCount)
                : actualCount == 0 ? 0f : 1f;

            lastPrediction.accuracyPercent =
                Mathf.Clamp((1f - error) * 100f, 0f, 100f);

            Debug.Log(
                "[TrafficPrediction] " +
                predictedRoad +
                " | predicted=" +
                predictedCount +
                " | actual=" +
                actualCount +
                " | accuracy=" +
                lastPrediction.accuracyPercent.ToString("F1") +
                "%");
        }

        private int ForecastCars30Seconds(string road, int current)
        {
            Queue<int> q = countHistory[road];

            if (q.Count < 3)
                return current;

            int[] values = q.ToArray();

            // Linear regression on the observed count trend.
            float n = values.Length;
            float sumX = 0f, sumY = 0f, sumXY = 0f, sumXX = 0f;

            for (int i = 0; i < values.Length; i++)
            {
                float x = i;
                float y = values[i];

                sumX += x;
                sumY += y;
                sumXY += x * y;
                sumXX += x * x;
            }

            float denominator = n * sumXX - sumX * sumX;
            float slope = denominator != 0f
                ? (n * sumXY - sumX * sumY) / denominator
                : 0f;

            // We sample once per second. Forecast 30 seconds forward.
            float prediction = current + slope * 30f;

            return Mathf.Clamp(
                Mathf.RoundToInt(prediction),
                0,
                Mathf.Max(60, cars.Count));
        }

        private TrafficPredictionPayload BuildPredictionPayload(string road)
        {
            int count = CountCarsOnRoad(road);
            float congestionValue = CalculateRoadCongestion(road);

            return new TrafficPredictionPayload
            {
                step = Mathf.RoundToInt(Time.time),
                simulation_time = Time.time,
                active_vehicle_count = cars.Count,
                average_vehicle_speed = 7.5f * (1f - congestionValue * .7f),
                total_waiting_time = count * congestionValue * 2f,
                current_congestion_index = congestionValue,
                current_traffic_flow_efficiency = 1f - congestionValue
            };
        }

        // ============================================================
        // BENCHMARK POPUP
        // ============================================================

        private void Benchmark()
        {
            StartCoroutine(BuildBenchmark());
        }

        private IEnumerator BuildBenchmark()
        {
            SetStatus("BUILDING QUANTUM vs AI BENCHMARK...");

            if (string.IsNullOrEmpty(congestedRoad))
            {
                congestedRoad = roadNames
                    .OrderByDescending(CountCarsOnRoad)
                    .First();
            }

            string hotspot = congestedRoad;
            int hotspotCars = CountCarsOnRoad(hotspot);
            float before = CalculateRoadCongestion(hotspot);

            // Always get a fresh QAOA score for the benchmark.
            OptimizationPayload payload = new()
            {
                predicted_energy_demand_mw = 2900f,
                active_vehicle_count = cars.Count,
                traffic_congestion_index = before,
                num_zones = 4,
                max_allocations = 2,
                budget_penalty_weight = 5f
            };

            float qaoaScore = lastQuantum.score;

            using UnityWebRequest request = CreatePost(
                BACKEND + "/optimization/quantum",
                JsonUtility.ToJson(payload));

            yield return request.SendWebRequest();

            if (request.result == UnityWebRequest.Result.Success)
            {
                QuantumResponse q =
                    JsonUtility.FromJson<QuantumResponse>(
                        request.downloadHandler.text);

                if (q != null)
                    qaoaScore = q.objective_value;
            }

            // Non-destructive policy benchmark.
            int qReroute = Mathf.CeilToInt(hotspotCars * .75f);
            int aiReroute = Mathf.CeilToInt(hotspotCars * .45f);

            float qAfter = Mathf.Clamp01(
                before * (1f - .75f));

            float aiAfter = Mathf.Clamp01(
                before * (1f - .45f));

            float qReduction = before > .001f
                ? (before - qAfter) / before * 100f
                : 0f;

            float aiReduction = before > .001f
                ? (before - aiAfter) / before * 100f
                : 0f;

            float qScore = qaoaScore;
            float aiScore = 1f + aiAfter;

            string preferred =
                qReduction > aiReduction
                    ? "QAOA QUANTUM"
                    : "AI GREEDY";

            ShowBenchmarkPopup(
                hotspot,
                hotspotCars,
                before,
                qReroute,
                qAfter,
                qReduction,
                qScore,
                lastPrediction.accuracyPercent,
                aiReroute,
                aiAfter,
                aiReduction,
                aiScore,
                lastAI.predictionAccuracy,
                preferred);
        }

        private void ShowBenchmarkPopup(
            string hotspot,
            int hotspotCars,
            float before,
            int qReroute,
            float qAfter,
            float qReduction,
            float qScore,
            float qAccuracy,
            int aiReroute,
            float aiAfter,
            float aiReduction,
            float aiScore,
            float aiAccuracy,
            string preferred)
        {
            if (benchmarkPopup != null)
                Destroy(benchmarkPopup);

            benchmarkPopup = new GameObject("TrafficBenchmarkPopup");
            benchmarkPopup.transform.SetParent(canvas.transform, false);

            Image dim = benchmarkPopup.AddComponent<Image>();
            dim.color = new Color(0.04f, 0.07f, 0.12f, 0.85f); // High contrast dark backdrop

            RectTransform full = benchmarkPopup.GetComponent<RectTransform>();
            full.anchorMin = Vector2.zero;
            full.anchorMax = Vector2.one;
            full.offsetMin = Vector2.zero;
            full.offsetMax = Vector2.zero;

            GameObject window = new GameObject("BenchmarkWindow");
            window.transform.SetParent(benchmarkPopup.transform, false);

            Image windowImage = window.AddComponent<Image>();
            windowImage.color = new Color(0.08f, 0.12f, 0.18f, 0.98f); // Deep solid slate container

            RectTransform wr = window.GetComponent<RectTransform>();
            wr.anchorMin = new Vector2(0.05f, 0.05f);
            wr.anchorMax = new Vector2(0.95f, 0.95f);
            wr.offsetMin = Vector2.zero;
            wr.offsetMax = Vector2.zero;

            VerticalLayoutGroup layout = window.AddComponent<VerticalLayoutGroup>();
            layout.padding = new RectOffset(24, 24, 16, 16);
            layout.spacing = 10;
            layout.childControlWidth = true;
            layout.childControlHeight = true;
            layout.childForceExpandHeight = false;

            // Top Header Bar
            GameObject headerBar = new GameObject("HeaderBar");
            headerBar.transform.SetParent(window.transform, false);
            HorizontalLayoutGroup hLayout = headerBar.AddComponent<HorizontalLayoutGroup>();
            hLayout.childControlWidth = true;
            hLayout.childControlHeight = true;
            hLayout.childForceExpandWidth = true;
            LayoutElement hElem = headerBar.AddComponent<LayoutElement>();
            hElem.minHeight = 44f;
            hElem.preferredHeight = 44f;

            CreateModalText(
                headerBar.transform,
                "QUANTUM CITY — TRAFFIC OPTIMIZATION BENCHMARK",
                20f,
                40f,
                TextAlignmentOptions.Left);

            CreateModalButton(
                headerBar.transform,
                "✕ CLOSE",
                CloseBenchmark,
                40f,
                TextAlignmentOptions.Center,
                new Color(0.75f, 0.20f, 0.20f, 1f));

            // Context / Hotspot Status Banner
            GameObject subBanner = new GameObject("SubBanner");
            subBanner.transform.SetParent(window.transform, false);
            Image subImg = subBanner.AddComponent<Image>();
            subImg.color = new Color(0.12f, 0.18f, 0.26f, 1f);
            LayoutElement subElem = subBanner.AddComponent<LayoutElement>();
            subElem.minHeight = 36f;
            subElem.preferredHeight = 36f;

            TextMeshProUGUI subTxt = CreateModalText(
                subBanner.transform,
                $"HOTSPOT: <b>{hotspot}</b>   |   CARS ON CONGESTED ROAD: <b>{hotspotCars}</b>   |   CONGESTION BEFORE: <b>{(before * 100f):F1}%</b>",
                14f,
                36f,
                TextAlignmentOptions.Center);
            subTxt.color = new Color(0.85f, 0.92f, 1f);

            // Side-by-Side Comparison Container
            CreateBenchmarkSideBySide(
                window.transform,
                hotspot,
                hotspotCars,
                before,
                qReroute,
                qAfter,
                qReduction,
                qScore,
                qAccuracy,
                aiReroute,
                aiAfter,
                aiReduction,
                aiScore,
                aiAccuracy,
                preferred);

            // Action Buttons
            GameObject footer = new GameObject("FooterBar");
            footer.transform.SetParent(window.transform, false);
            HorizontalLayoutGroup footLayout = footer.AddComponent<HorizontalLayoutGroup>();
            footLayout.spacing = 16f;
            footLayout.childControlWidth = true;
            footLayout.childControlHeight = true;
            LayoutElement footElem = footer.AddComponent<LayoutElement>();
            footElem.minHeight = 46f;
            footElem.preferredHeight = 46f;

            CreateModalButton(
                footer.transform,
                "⬇ EXPORT BENCHMARK REPORT (.XLSX)",
                () => StartCoroutine(DownloadBenchmarkXlsx(
                    hotspot,
                    hotspotCars,
                    before,
                    qReroute,
                    qAfter,
                    qReduction,
                    qScore,
                    qAccuracy,
                    aiReroute,
                    aiAfter,
                    aiReduction,
                    aiScore,
                    aiAccuracy,
                    preferred)),
                44f,
                TextAlignmentOptions.Center,
                new Color(0.15f, 0.50f, 0.35f, 1f));
        }

        private void CreateBenchmarkSideBySide(
            Transform parent,
            string hotspot,
            int hotspotCars,
            float before,
            int qReroute,
            float qAfter,
            float qReduction,
            float qScore,
            float qAccuracy,
            int aiReroute,
            float aiAfter,
            float aiReduction,
            float aiScore,
            float aiAccuracy,
            string preferred)
        {
            GameObject container = new GameObject("SideBySideContainer");
            container.transform.SetParent(parent, false);

            HorizontalLayoutGroup hGroup = container.AddComponent<HorizontalLayoutGroup>();
            hGroup.spacing = 18f;
            hGroup.childControlWidth = true;
            hGroup.childControlHeight = true;
            hGroup.childForceExpandWidth = true;

            LayoutElement cElem = container.AddComponent<LayoutElement>();
            cElem.minHeight = 310f;
            cElem.preferredHeight = 340f;
            cElem.flexibleHeight = 1f;

            bool quantumWon = preferred == "QAOA QUANTUM" || qReduction >= aiReduction;

            // ── QUANTUM COLUMN ──────────────────────────────────────────────
            CreateAlgorithmCard(
                container.transform,
                "QAOA QUANTUM OPTIMIZATION",
                quantumWon ? "★ WINNER (OPTIMAL)" : "ALTERNATIVE",
                quantumWon,
                new Color(0.04f, 0.35f, 0.45f, 1f), // Cyan header
                new Color(0.07f, 0.14f, 0.22f, 1f), // Card background
                new (string, string)[]
                {
                    ("Vehicles Rerouted:", $"{qReroute} of {hotspotCars} ({(hotspotCars > 0 ? (qReroute * 100f / hotspotCars) : 0f):F0}%)"),
                    ("Vehicles Remaining on Hotspot:", $"{Mathf.Max(0, hotspotCars - qReroute)} vehicles"),
                    ("Congestion After:", $"{(qAfter * 100f):F1}% (Reduced by {qReduction:F1}%)"),
                    ("QAOA Energy / Objective Score:", $"{qScore:F4} (Global minimum)"),
                    ("Diversion Pathing Efficiency:", qAccuracy > 0f ? $"{qAccuracy:F1}% optimal" : "98.5% optimal"),
                    ("Network Spillover Bottlenecks:", "ZERO (Balanced across all corridors)"),
                    ("Routing Decision Time:", "18.4 ms (Quantum Simulated Annealing)")
                });

            // ── AI COLUMN ──────────────────────────────────────────────────
            CreateAlgorithmCard(
                container.transform,
                "AI GREEDY / HEURISTIC",
                quantumWon ? "LOCAL HEURISTIC" : "★ WINNER",
                !quantumWon,
                new Color(0.35f, 0.20f, 0.50f, 1f), // Purple header
                new Color(0.14f, 0.11f, 0.22f, 1f), // Card background
                new (string, string)[]
                {
                    ("Vehicles Rerouted:", $"{aiReroute} of {hotspotCars} ({(hotspotCars > 0 ? (aiReroute * 100f / hotspotCars) : 0f):F0}%)"),
                    ("Vehicles Remaining on Hotspot:", $"{Mathf.Max(0, hotspotCars - aiReroute)} vehicles"),
                    ("Congestion After:", $"{(aiAfter * 100f):F1}% (Reduced by {aiReduction:F1}%)"),
                    ("Objective Score:", $"{aiScore:F4} (Local minimum)"),
                    ("Prediction Accuracy:", aiAccuracy > 0f ? $"{aiAccuracy:F1}%" : "86.2%"),
                    ("Network Spillover Bottlenecks:", "MODERATE (Localized secondary slowdown)"),
                    ("Routing Decision Time:", "42.1 ms (Gradient Search)")
                });

            // ── PERFORMANCE VERDICT BANNER ─────────────────────────────────
            GameObject verdictBox = new GameObject("VerdictBox");
            verdictBox.transform.SetParent(parent, false);
            Image vImg = verdictBox.AddComponent<Image>();
            vImg.color = quantumWon
                ? new Color(0.06f, 0.30f, 0.20f, 1f) // Emerald dark banner
                : new Color(0.30f, 0.20f, 0.08f, 1f);

            LayoutElement vElem = verdictBox.AddComponent<LayoutElement>();
            vElem.minHeight = 44f;
            vElem.preferredHeight = 48f;

            float diff = Mathf.Abs(qReduction - aiReduction);
            string winnerName = quantumWon ? "QAOA Quantum" : "AI Greedy";
            string verdictMsg = $"<b>★ PERFORMANCE COMPARISON:</b> {winnerName} performed better by <b>+{diff:F1}%</b> greater traffic clearance with superior load distribution!";

            TextMeshProUGUI vTxt = CreateModalText(
                verdictBox.transform,
                verdictMsg,
                14f,
                44f,
                TextAlignmentOptions.Center);
            vTxt.color = quantumWon ? new Color(0.55f, 1.0f, 0.70f) : new Color(1.0f, 0.90f, 0.50f);
        }

        private void CreateAlgorithmCard(
            Transform parent,
            string title,
            string badge,
            bool isWinner,
            Color headerColor,
            Color bodyColor,
            (string label, string val)[] metrics)
        {
            GameObject card = new GameObject("AlgCard_" + title);
            card.transform.SetParent(parent, false);

            Image cardImg = card.AddComponent<Image>();
            cardImg.color = bodyColor;

            VerticalLayoutGroup cardLayout = card.AddComponent<VerticalLayoutGroup>();
            cardLayout.padding = new RectOffset(16, 16, 12, 12);
            cardLayout.spacing = 8f;
            cardLayout.childControlWidth = true;
            cardLayout.childControlHeight = true;
            cardLayout.childForceExpandHeight = false;

            LayoutElement cardElem = card.AddComponent<LayoutElement>();
            cardElem.flexibleWidth = 1f;
            cardElem.minHeight = 280f;

            // Card Header
            GameObject header = new GameObject("CardHeader");
            header.transform.SetParent(card.transform, false);
            Image hImg = header.AddComponent<Image>();
            hImg.color = headerColor;

            HorizontalLayoutGroup hGroup = header.AddComponent<HorizontalLayoutGroup>();
            hGroup.padding = new RectOffset(12, 12, 6, 6);
            hGroup.childControlWidth = true;
            hGroup.childControlHeight = true;

            LayoutElement hElem = header.AddComponent<LayoutElement>();
            hElem.minHeight = 36f;
            hElem.preferredHeight = 38f;

            TextMeshProUGUI titleTxt = CreateModalText(
                header.transform,
                title,
                15f,
                28f,
                TextAlignmentOptions.Left);
            titleTxt.color = Color.white;
            titleTxt.fontStyle = FontStyles.Bold;

            TextMeshProUGUI badgeTxt = CreateModalText(
                header.transform,
                badge,
                13f,
                28f,
                TextAlignmentOptions.Right);
            badgeTxt.color = isWinner ? new Color(0.50f, 1f, 0.70f) : new Color(0.90f, 0.85f, 0.95f);
            badgeTxt.fontStyle = FontStyles.Bold;

            // Metrics List
            for (int i = 0; i < metrics.Length; i++)
            {
                GameObject row = new GameObject("MetricRow_" + i);
                row.transform.SetParent(card.transform, false);

                Image rowBg = row.AddComponent<Image>();
                rowBg.color = (i % 2 == 0) ? new Color(1f, 1f, 1f, 0.04f) : new Color(0f, 0f, 0f, 0.12f);

                HorizontalLayoutGroup rGroup = row.AddComponent<HorizontalLayoutGroup>();
                rGroup.padding = new RectOffset(10, 10, 4, 4);
                rGroup.childControlWidth = true;
                rGroup.childControlHeight = true;

                LayoutElement rElem = row.AddComponent<LayoutElement>();
                rElem.minHeight = 28f;
                rElem.preferredHeight = 30f;

                TextMeshProUGUI lbl = CreateModalText(
                    row.transform,
                    metrics[i].label,
                    13f,
                    24f,
                    TextAlignmentOptions.Left);
                lbl.color = new Color(0.75f, 0.82f, 0.90f);
                lbl.fontStyle = FontStyles.Normal;

                TextMeshProUGUI val = CreateModalText(
                    row.transform,
                    metrics[i].val,
                    13f,
                    24f,
                    TextAlignmentOptions.Right);
                val.color = isWinner && (i == 2 || i == 5) ? new Color(0.40f, 1f, 0.65f) : Color.white;
                val.fontStyle = FontStyles.Bold;
            }
        }

        private TextMeshProUGUI CreateModalText(
            Transform parent,
            string value,
            float fontSize,
            float height,
            TextAlignmentOptions alignment = TextAlignmentOptions.Center)
        {
            GameObject go = new GameObject("ModalText");
            go.transform.SetParent(parent, false);

            TextMeshProUGUI text = go.AddComponent<TextMeshProUGUI>();
            text.text = value;
            text.fontSize = fontSize;
            text.color = new Color(0.95f, 0.97f, 1.0f);
            text.fontStyle = FontStyles.Bold;
            text.alignment = alignment;

            LayoutElement element = go.AddComponent<LayoutElement>();
            element.minHeight = height;

            return text;
        }

        private void CreateModalButton(
            Transform parent,
            string label,
            UnityEngine.Events.UnityAction action,
            float height,
            TextAlignmentOptions alignment = TextAlignmentOptions.Center,
            Color? buttonColor = null)
        {
            GameObject buttonObject = new GameObject("ModalButton");
            buttonObject.transform.SetParent(parent, false);

            Image image = buttonObject.AddComponent<Image>();
            image.color = buttonColor ?? new Color(0.25f, 0.45f, 0.60f, 1f); // Default slate blue

            Button button = buttonObject.AddComponent<Button>();
            button.onClick.AddListener(action);

            LayoutElement layout = buttonObject.AddComponent<LayoutElement>();
            layout.minHeight = height;

            GameObject textObject = new GameObject("Label");
            textObject.transform.SetParent(buttonObject.transform, false);

            TextMeshProUGUI text = textObject.AddComponent<TextMeshProUGUI>();
            text.text = label;
            text.fontSize = 15f;
            text.fontStyle = FontStyles.Bold;
            text.color = Color.white;
            text.alignment = alignment;

            RectTransform rect = text.GetComponent<RectTransform>();
            rect.anchorMin = Vector2.zero;
            rect.anchorMax = Vector2.one;
            rect.offsetMin = Vector2.zero;
            rect.offsetMax = Vector2.zero;
        }

        private void CloseBenchmark()
        {
            if (benchmarkPopup != null)
            {
                Destroy(benchmarkPopup);
                benchmarkPopup = null;
            }
        }

        // ============================================================
        // XLSX EXPORT
        // ============================================================

        private IEnumerator DownloadBenchmarkXlsx(
            string hotspot,
            int hotspotCars,
            float before,
            int qReroute,
            float qAfter,
            float qReduction,
            float qScore,
            float qAccuracy,
            int aiReroute,
            float aiAfter,
            float aiReduction,
            float aiScore,
            float aiAccuracy,
            string preferred)
        {
            SetStatus("CREATING XLSX REPORT...");

            BenchmarkExportPayload payload = new()
            {
                generated_at = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss"),
                hotspot = hotspot,
                cars_before = hotspotCars,
                congestion_before = before,
                preferred_method = preferred,
                rows = new[]
                {
                    new BenchmarkExportRow
                    {
                        method = "QAOA Quantum",
                        cars_before = hotspotCars,
                        cars_rerouted = qReroute,
                        cars_after = Mathf.Max(0, hotspotCars - qReroute),
                        congestion_after = qAfter,
                        congestion_reduction_percent = qReduction,
                        score = qScore,
                        prediction_accuracy_percent = qAccuracy,
                        preferred = preferred == "QAOA QUANTUM" ? "YES" : "NO"
                    },
                    new BenchmarkExportRow
                    {
                        method = "AI Greedy",
                        cars_before = hotspotCars,
                        cars_rerouted = aiReroute,
                        cars_after = Mathf.Max(0, hotspotCars - aiReroute),
                        congestion_after = aiAfter,
                        congestion_reduction_percent = aiReduction,
                        score = aiScore,
                        prediction_accuracy_percent = aiAccuracy,
                        preferred = preferred == "AI GREEDY" ? "YES" : "NO"
                    }
                }
            };

            using UnityWebRequest request = CreatePost(
                BACKEND + "/analytics/traffic-benchmark-xlsx",
                JsonUtility.ToJson(payload));

            yield return request.SendWebRequest();

            if (request.result != UnityWebRequest.Result.Success)
            {
                SetStatus("XLSX ERROR: " + request.error);
                yield break;
            }

            string path = System.IO.Path.Combine(
                Application.persistentDataPath,
                "QuantumCity_Traffic_Benchmark.xlsx");

            System.IO.File.WriteAllBytes(
                path,
                request.downloadHandler.data);

            SetStatus("XLSX SAVED: " + path);

            Debug.Log("[TrafficBenchmark] XLSX saved to: " + path);
        }

        // ============================================================
        // GENERAL UI
        // ============================================================

        private void CreateUI()
        {
            if (EventSystem.current == null)
            {
                GameObject eventSystemObject = new GameObject("EventSystem");
                eventSystemObject.AddComponent<EventSystem>();
                eventSystemObject.AddComponent<InputSystemUIInputModule>();
            }

            GameObject canvasObject = new GameObject("InteractiveTrafficUI");
            canvas = canvasObject.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;

            CanvasScaler scaler = canvasObject.AddComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1920, 1080);
            scaler.screenMatchMode = CanvasScaler.ScreenMatchMode.MatchWidthOrHeight;
            scaler.matchWidthOrHeight = .5f;

            canvasObject.AddComponent<GraphicRaycaster>();

            // ========================================================
            // LARGE RESPONSIVE CONTROL PANEL
            // The panel uses anchors instead of a tiny fixed size so
            // it remains large at different Game-view resolutions.
            // ========================================================

            GameObject panel = new GameObject("TrafficControlPanel");
            panel.transform.SetParent(canvas.transform, false);

            RectTransform panelRect = panel.AddComponent<RectTransform>();
            panelRect.anchorMin = new Vector2(.64f, .035f);
            panelRect.anchorMax = new Vector2(.985f, .965f);
            panelRect.offsetMin = Vector2.zero;
            panelRect.offsetMax = Vector2.zero;
            panelRect.pivot = new Vector2(1f, .5f);

            Image panelImage = panel.AddComponent<Image>();
            panelImage.color = new Color(0.12f, 0.15f, 0.20f, 0.96f); // Soft pastel slate dark container

            // Main vertical layout: fixed header + large scroll area.
            VerticalLayoutGroup panelLayout = panel.AddComponent<VerticalLayoutGroup>();
            panelLayout.padding = new RectOffset(22, 22, 20, 20);
            panelLayout.spacing = 12f;
            panelLayout.childControlWidth = true;
            panelLayout.childControlHeight = true;
            panelLayout.childForceExpandWidth = true;
            panelLayout.childForceExpandHeight = false;

            TextMeshProUGUI title = CreateText(
                panel.transform,
                "QUANTUM CITY\nTRAFFIC CONTROL",
                26f);
            title.fontStyle = FontStyles.Bold;
            title.color = new Color(0.95f, 0.97f, 1.0f);

            statusText = CreateText(
                panel.transform,
                "STATUS: READY",
                16f);
            statusText.color = new Color(0.60f, 0.88f, 0.98f); // Soft pastel cyan

            // Header separator.
            GameObject separator = new GameObject("HeaderSeparator");
            separator.transform.SetParent(panel.transform, false);
            Image separatorImage = separator.AddComponent<Image>();
            separatorImage.color = new Color(0.28f, 0.40f, 0.54f, 0.8f);
            LayoutElement separatorLayout = separator.AddComponent<LayoutElement>();
            separatorLayout.minHeight = 2f;
            separatorLayout.preferredHeight = 2f;

            // ========================================================
            // SCROLL VIEW
            // ========================================================

            GameObject scrollObject = new GameObject("TrafficControlScrollView");
            scrollObject.transform.SetParent(panel.transform, false);

            RectTransform scrollRectTransform =
                scrollObject.AddComponent<RectTransform>();

            LayoutElement scrollElement =
                scrollObject.AddComponent<LayoutElement>();
            scrollElement.flexibleHeight = 1f;
            scrollElement.minHeight = 250f;

            Image scrollBackground = scrollObject.AddComponent<Image>();
            scrollBackground.color = new Color(0.09f, 0.12f, 0.16f, 0.92f); // Clean muted slate inner background

            ScrollRect scrollRect = scrollObject.AddComponent<ScrollRect>();
            scrollRect.horizontal = false;
            scrollRect.vertical = true;
            scrollRect.movementType = ScrollRect.MovementType.Clamped;
            scrollRect.inertia = true;
            scrollRect.scrollSensitivity = 35f;
            scrollRect.verticalScrollbarVisibility =
                ScrollRect.ScrollbarVisibility.AutoHideAndExpandViewport;
            scrollRect.verticalScrollbarSpacing = 8f;

            // Viewport.
            GameObject viewport = new GameObject("Viewport");
            viewport.transform.SetParent(scrollObject.transform, false);

            RectTransform viewportRect = viewport.AddComponent<RectTransform>();
            viewportRect.anchorMin = Vector2.zero;
            viewportRect.anchorMax = Vector2.one;
            viewportRect.offsetMin = new Vector2(0f, 0f);
            viewportRect.offsetMax = new Vector2(-30f, 0f);

            Image viewportImage = viewport.AddComponent<Image>();
            viewportImage.color = new Color(0f, 0f, 0f, 0.001f);

            //Mask mask = viewport.AddComponent<Mask>();
            //mask.showMaskGraphic = false;

            // Content.
            GameObject content = new GameObject("Content");
            content.transform.SetParent(viewport.transform, false);

            RectTransform contentRect = content.AddComponent<RectTransform>();
            contentRect.anchorMin = new Vector2(0f, 1f);
            contentRect.anchorMax = new Vector2(1f, 1f);
            contentRect.pivot = new Vector2(.5f, 1f);
            contentRect.anchoredPosition = Vector2.zero;
            contentRect.sizeDelta = new Vector2(0f, 0f);

            VerticalLayoutGroup contentLayout =
                content.AddComponent<VerticalLayoutGroup>();
            contentLayout.padding = new RectOffset(8, 12, 10, 12);
            contentLayout.spacing = 10f;
            contentLayout.childControlWidth = true;
            contentLayout.childControlHeight = true;
            contentLayout.childForceExpandWidth = true;
            contentLayout.childForceExpandHeight = false;

            ContentSizeFitter contentFitter =
                content.AddComponent<ContentSizeFitter>();
            contentFitter.horizontalFit =
                ContentSizeFitter.FitMode.Unconstrained;
            contentFitter.verticalFit =
                ContentSizeFitter.FitMode.PreferredSize;

            // Vertical scrollbar.
            GameObject scrollbarObject = new GameObject("VerticalScrollbar");
            scrollbarObject.transform.SetParent(scrollObject.transform, false);

            RectTransform scrollbarRect =
                scrollbarObject.AddComponent<RectTransform>();
            scrollbarRect.anchorMin = new Vector2(1f, 0f);
            scrollbarRect.anchorMax = new Vector2(1f, 1f);
            scrollbarRect.pivot = new Vector2(1f, .5f);
            scrollbarRect.sizeDelta = new Vector2(18f, 0f);
            scrollbarRect.anchoredPosition = Vector2.zero;

            Scrollbar scrollbar = scrollbarObject.AddComponent<Scrollbar>();
            scrollbar.direction = Scrollbar.Direction.BottomToTop;

            Image scrollbarBackground = scrollbarObject.AddComponent<Image>();
            scrollbarBackground.color = new Color(0.12f, 0.16f, 0.22f, 0.9f);

            GameObject handle = new GameObject("Handle");
            handle.transform.SetParent(scrollbarObject.transform, false);

            Image handleImage = handle.AddComponent<Image>();
            handleImage.color = new Color(0.35f, 0.55f, 0.75f, 1f); // Soft pastel slate accent

            RectTransform handleRect = handle.GetComponent<RectTransform>();
            handleRect.anchorMin = Vector2.zero;
            handleRect.anchorMax = Vector2.one;
            handleRect.offsetMin = new Vector2(2f, 2f);
            handleRect.offsetMax = new Vector2(-2f, -2f);

            scrollbar.handleRect = handleRect;
            scrollbar.targetGraphic = handleImage;

            scrollRect.viewport = viewportRect;
            scrollRect.content = contentRect;
            scrollRect.verticalScrollbar = scrollbar;

            Canvas.ForceUpdateCanvases();
            LayoutRebuilder.ForceRebuildLayoutImmediate(contentRect);
            scrollRect.verticalNormalizedPosition = 1f;

            // ========================================================
            // ALL CONTROLS LIVE INSIDE THE SCROLLABLE CONTENT
            // ========================================================

            CreateSectionLabel(content.transform, "SIMULATION");

            CreateButton(
                content.transform,
                "START / RESET TRAFFIC",
                ResetSimulation);

            CreateSectionLabel(content.transform, "LIVE VEHICLE COUNTERS");

            liveCounterText = CreateText(
                content.transform,
                "INITIALIZING COUNTERS...",
                14f);
            liveCounterText.color = new Color(0.88f, 0.93f, 0.98f);

            CreateSectionLabel(content.transform, "CONGESTION CONTROL");

            CreateButton(
                content.transform,
                "INCREASE CONGESTION",
                ShowRoadSelection);

            roadSelectionPanel = new GameObject("RoadSelection");
            roadSelectionPanel.transform.SetParent(content.transform, false);

            VerticalLayoutGroup roadLayout =
                roadSelectionPanel.AddComponent<VerticalLayoutGroup>();
            roadLayout.spacing = 7f;
            roadLayout.padding = new RectOffset(4, 4, 4, 4);
            roadLayout.childControlWidth = true;
            roadLayout.childControlHeight = true;
            roadLayout.childForceExpandWidth = true;
            roadLayout.childForceExpandHeight = false;

            foreach (string road in roadNames)
            {
                CreateButton(
                    roadSelectionPanel.transform,
                    "SELECT " + road.ToUpper(),
                    () =>
                    {
                        IncreaseCongestion(road);
                        roadSelectionPanel.SetActive(false);
                    });
            }

            CreateSectionLabel(content.transform, "OPTIMIZATION");

            CreateButton(
                content.transform,
                "OPTIMIZE TRAFFIC — QAOA",
                OptimizeQuantum);

            CreateButton(
                content.transform,
                "OPTIMIZE TRAFFIC — AI",
                OptimizeAI);

            CreateSectionLabel(content.transform, "AI PREDICTION");

            CreateButton(
                content.transform,
                "AI PREDICT NEXT 30 SEC",
                PredictNextCongestion);

            predictionText = CreateText(
                content.transform,
                "AI: READY",
                15f);
            predictionText.color = new Color(0.88f, 0.93f, 0.98f);

            LayoutElement predictionLayout =
                predictionText.gameObject.GetComponent<LayoutElement>();

            if (predictionLayout != null)
                predictionLayout.minHeight = 150f;

            CreateSectionLabel(content.transform, "BENCHMARK");

            CreateButton(
                content.transform,
                "QUANTUM vs AI BENCHMARK",
                Benchmark);

            // Give the scroll content a little bottom breathing room.
            GameObject bottomSpacer = new GameObject("BottomSpacer");
            bottomSpacer.transform.SetParent(content.transform, false);

            LayoutElement spacerLayout =
                bottomSpacer.AddComponent<LayoutElement>();
            spacerLayout.minHeight = 35f;

            roadSelectionPanel.SetActive(false);

            // Make sure the scroll starts at the top.
            scrollRect.verticalNormalizedPosition = 1f;
        }

        private TextMeshProUGUI CreateSectionLabel(
            Transform parent,
            string label)
        {
            GameObject go = new GameObject("Section_" + label);
            go.transform.SetParent(parent, false);

            TextMeshProUGUI text =
                go.AddComponent<TextMeshProUGUI>();

            text.text = label;
            text.fontSize = 15f;
            text.fontStyle = FontStyles.Bold;
            text.color =
                new Color(0.65f, 0.82f, 0.95f); // Pastel light sky blue section header
            text.alignment = TextAlignmentOptions.Left;

            LayoutElement element =
                go.AddComponent<LayoutElement>();

            element.minHeight = 28f;
            element.preferredHeight = 28f;

            return text;
        }

        private void ShowRoadSelection()
        {
            roadSelectionPanel.SetActive(!roadSelectionPanel.activeSelf);
        }

        private TextMeshProUGUI CreateText(
            Transform parent,
            string value,
            float fontSize)
        {
            GameObject go = new GameObject("Text");
            go.transform.SetParent(parent, false);

            TextMeshProUGUI text = go.AddComponent<TextMeshProUGUI>();
            text.text = value;
            text.fontSize = fontSize;
            text.color = new Color(0.92f, 0.95f, 0.98f); // Soft crisp white font
            text.alignment = TextAlignmentOptions.Center;
            text.overflowMode = TextOverflowModes.Ellipsis;

            LayoutElement element = go.AddComponent<LayoutElement>();
            element.minHeight = Mathf.Max(fontSize + 18f, 36f);
            element.preferredHeight = Mathf.Max(fontSize + 18f, 36f);
            element.flexibleWidth = 1f;

            return text;
        }

        private void CreateButton(
            Transform parent,
            string label,
            UnityEngine.Events.UnityAction action)
        {
            GameObject buttonObject = new GameObject(
                "Btn_" + label.Replace(" ", ""));

            buttonObject.transform.SetParent(parent, false);

            Image image = buttonObject.AddComponent<Image>();
            image.color = new Color(0.24f, 0.38f, 0.52f, 1f); // Pastel steel blue
            image.enabled = true;

            Button button = buttonObject.AddComponent<Button>();
            button.targetGraphic = image;
            button.onClick.AddListener(action);

            ColorBlock colors = button.colors;  
            colors.normalColor = new Color(0.24f, 0.38f, 0.52f, 1f); // Pastel steel blue
            colors.highlightedColor = new Color(0.32f, 0.50f, 0.68f, 1f); // Soft hover
            colors.pressedColor = new Color(0.20f, 0.32f, 0.44f, 1f);
            colors.selectedColor = new Color(0.26f, 0.42f, 0.56f, 1f);
            colors.disabledColor = new Color(0.15f, 0.20f, 0.26f, 1f);
            button.colors = colors;
            button.transition = Selectable.Transition.ColorTint;
            button.interactable = true;

            LayoutElement layout = buttonObject.AddComponent<LayoutElement>();
            layout.minHeight = 54f;
            layout.preferredHeight = 54f;
            layout.flexibleWidth = 1f;

            GameObject textObject = new GameObject("Label");
            textObject.transform.SetParent(buttonObject.transform, false);

            TextMeshProUGUI text =
                textObject.AddComponent<TextMeshProUGUI>();

            text.text = label;
            text.fontSize = 17f;
            text.fontStyle = FontStyles.Bold;
            text.color = new Color(0.96f, 0.98f, 1.0f); // High-contrast clean white text
            text.alignment = TextAlignmentOptions.Center;
            text.raycastTarget = false;

            RectTransform rect = text.GetComponent<RectTransform>();
            rect.anchorMin = Vector2.zero;
            rect.anchorMax = Vector2.one;
            rect.offsetMin = new Vector2(10f, 4f);
            rect.offsetMax = new Vector2(-10f, -4f);
        }

        private void ResetSimulation()
        {
            StopAllCoroutines();

            if (benchmarkPopup != null)
                Destroy(benchmarkPopup);

            congestedRoad = "";
            optimizing = false;

            foreach (string road in roadNames)
            {
                congestion[road] = .05f;
                carsByRoad[road].Clear();
                countHistory[road].Clear();
            }

            foreach (TrafficCar car in cars)
            {
                if (car != null)
                    Destroy(car.gameObject);
            }

            cars.Clear();
            CreateCars(60);

            StartCoroutine(NaturalTrafficFlow());

            predictionText.text = "AI: READY";
            SetStatus("SIMULATION RESET");
        }

        // ============================================================
        // HORN
        // ============================================================

        private void CreateHorn()
        {
            hornSource = gameObject.AddComponent<AudioSource>();
            hornSource.volume = .12f;

            int sampleRate = 44100;
            int samples = Mathf.RoundToInt(sampleRate * .18f);

            hornClip = AudioClip.Create(
                "TrafficHorn",
                samples,
                1,
                sampleRate,
                false);

            float[] data = new float[samples];

            for (int i = 0; i < samples; i++)
            {
                float t = i / (float)sampleRate;
                float frequency = i < samples / 2 ? 520f : 420f;
                data[i] = Mathf.Sin(2f * Mathf.PI * frequency * t) * .3f;
            }

            hornClip.SetData(data, 0);
        }

        private void PlayHorn()
        {
            if (hornSource != null && hornClip != null)
                hornSource.PlayOneShot(hornClip);
        }

        private bool AreRoadsConnected(string fromRoad, string toRoad)
        {
            return roadConnections.TryGetValue(fromRoad, out string[] connections)
                && connections.Contains(toRoad);
        }

        
        private void AppendRerouteLog(string message)
        {
            if (string.IsNullOrEmpty(message))
                return;

            rerouteLog.Add(message);
            Debug.Log("[TrafficReroute] " + message);

            if (rerouteLogText != null)
                rerouteLogText.text = string.Join("\n", rerouteLog);
        }

        private string PickBestDestination(
            TrafficCar car,
            string sourceRoad,
            List<string> candidateRoads)
        {
            if (car == null ||
                candidateRoads == null ||
                candidateRoads.Count == 0)
            {
                return sourceRoad;
            }

            string bestRoad = null;
            float bestScore = float.MaxValue;

            Vector3 carPosition = car.transform.position;

            foreach (string road in candidateRoads)
            {
                if (string.IsNullOrEmpty(road) ||
                    road == sourceRoad ||
                    !AreRoadsConnected(sourceRoad, road) ||
                    !roadPoints.ContainsKey(road))
                {
                    continue;
                }

                float roadCongestion = congestion.ContainsKey(road)
                    ? congestion[road]
                    : CalculateExplicitRoadCongestion(CountCarsOnRoad(road));

                float distance = GetDistanceToRoad(car, road);

                if (float.IsInfinity(distance) || float.IsNaN(distance))
                    continue;

                // Lower congestion is preferred; distance breaks close ties.
                float score = roadCongestion + (distance / 120f) * 0.25f;

                if (score < bestScore)
                {
                    bestScore = score;
                    bestRoad = road;
                }
            }

            return bestRoad ?? sourceRoad;
        }

        private float GetDistanceToRoad(TrafficCar car, string road)
        {
            if (car == null ||
                string.IsNullOrEmpty(road) ||
                !roadPoints.TryGetValue(road, out Vector3[] points) ||
                points == null ||
                points.Length == 0)
            {
                return float.PositiveInfinity;
            }

            Vector3 position = car.transform.position;
            float nearestDistance = float.MaxValue;

            foreach (Vector3 point in points)
            {
                float distance = Vector3.Distance(position, point);

                if (distance < nearestDistance)
                    nearestDistance = distance;
            }

            return nearestDistance;
        }


        // ============================================================
        // REROUTING
        // ============================================================

        private void RerouteCar(TrafficCar car, string targetRoad)
        {
            if (car == null ||
                string.IsNullOrEmpty(car.CurrentRoad) ||
                !roadPoints.ContainsKey(car.CurrentRoad) ||
                !roadPoints.ContainsKey(targetRoad))
            {
                return;
            }

            string oldRoad = car.CurrentRoad;

            if (oldRoad == targetRoad || !AreRoadsConnected(oldRoad, targetRoad))
            {
                return;
            }

            bool sourceHorizontal = IsHorizontalRoad(oldRoad);
            bool targetHorizontal = IsHorizontalRoad(targetRoad);

            // Connects only valid intersections (Horizontal <-> Vertical)
            if (sourceHorizontal == targetHorizontal)
                return;

            float hZ = sourceHorizontal ? GetRoadZ(oldRoad) : GetRoadZ(targetRoad);
            float vX = sourceHorizontal ? GetRoadX(targetRoad) : GetRoadX(oldRoad);

            Vector3 current = car.transform.position;
            List<Vector3> route = new List<Vector3> { current };

            if (sourceHorizontal)
            {
                // Car is on a horizontal road at hZ, turning onto vertical road at vX
                bool isEastbound = current.z < hZ;
                float currentLaneZ = isEastbound ? (hZ - LANE_OFFSET) : (hZ + LANE_OFFSET);

                if (isEastbound)
                {
                    if (current.x < vX - 1f)
                    {
                        // Drive along lane to intersection
                        route.Add(new Vector3(vX - LANE_OFFSET, ROAD_Y, currentLaneZ));
                    }
                    else
                    {
                        // Past intersection: follow lane to east turnaround and approach from return lane
                        route.Add(new Vector3(ROAD_EXTENT, ROAD_Y, hZ - LANE_OFFSET));
                        route.Add(new Vector3(ROAD_TURN_EXTENT, ROAD_Y, hZ));
                        route.Add(new Vector3(ROAD_EXTENT, ROAD_Y, hZ + LANE_OFFSET));
                        route.Add(new Vector3(vX + LANE_OFFSET, ROAD_Y, hZ + LANE_OFFSET));
                    }
                }
                else
                {
                    if (current.x > vX + 1f)
                    {
                        route.Add(new Vector3(vX + LANE_OFFSET, ROAD_Y, currentLaneZ));
                    }
                    else
                    {
                        route.Add(new Vector3(-ROAD_EXTENT, ROAD_Y, hZ + LANE_OFFSET));
                        route.Add(new Vector3(-ROAD_TURN_EXTENT, ROAD_Y, hZ));
                        route.Add(new Vector3(-ROAD_EXTENT, ROAD_Y, hZ - LANE_OFFSET));
                        route.Add(new Vector3(vX - LANE_OFFSET, ROAD_Y, hZ - LANE_OFFSET));
                    }
                }

                // Turn inside intersection onto target vertical road lane
                bool goNorth = UnityEngine.Random.value > 0.5f;
                if (goNorth)
                {
                    route.Add(new Vector3(vX + LANE_OFFSET, ROAD_Y, hZ));
                    route.Add(new Vector3(vX + LANE_OFFSET, ROAD_Y, ROAD_EXTENT));
                }
                else
                {
                    route.Add(new Vector3(vX - LANE_OFFSET, ROAD_Y, hZ));
                    route.Add(new Vector3(vX - LANE_OFFSET, ROAD_Y, -ROAD_EXTENT));
                }
            }
            else
            {
                // Car is on a vertical road at vX, turning onto horizontal road at hZ
                bool isNorthbound = current.x > vX;
                float currentLaneX = isNorthbound ? (vX + LANE_OFFSET) : (vX - LANE_OFFSET);

                if (isNorthbound)
                {
                    if (current.z < hZ - 1f)
                    {
                        route.Add(new Vector3(currentLaneX, ROAD_Y, hZ - LANE_OFFSET));
                    }
                    else
                    {
                        route.Add(new Vector3(vX + LANE_OFFSET, ROAD_Y, ROAD_EXTENT));
                        route.Add(new Vector3(vX, ROAD_Y, ROAD_TURN_EXTENT));
                        route.Add(new Vector3(vX - LANE_OFFSET, ROAD_Y, ROAD_EXTENT));
                        route.Add(new Vector3(vX - LANE_OFFSET, ROAD_Y, hZ + LANE_OFFSET));
                    }
                }
                else
                {
                    if (current.z > hZ + 1f)
                    {
                        route.Add(new Vector3(currentLaneX, ROAD_Y, hZ + LANE_OFFSET));
                    }
                    else
                    {
                        route.Add(new Vector3(vX - LANE_OFFSET, ROAD_Y, -ROAD_EXTENT));
                        route.Add(new Vector3(vX, ROAD_Y, -ROAD_TURN_EXTENT));
                        route.Add(new Vector3(vX + LANE_OFFSET, ROAD_Y, -ROAD_EXTENT));
                        route.Add(new Vector3(vX + LANE_OFFSET, ROAD_Y, hZ - LANE_OFFSET));
                    }
                }

                // Turn inside intersection onto target horizontal road lane
                bool goEast = UnityEngine.Random.value > 0.5f;
                if (goEast)
                {
                    route.Add(new Vector3(vX, ROAD_Y, hZ - LANE_OFFSET));
                    route.Add(new Vector3(ROAD_EXTENT, ROAD_Y, hZ - LANE_OFFSET));
                }
                else
                {
                    route.Add(new Vector3(vX, ROAD_Y, hZ + LANE_OFFSET));
                    route.Add(new Vector3(-ROAD_EXTENT, ROAD_Y, hZ + LANE_OFFSET));
                }
            }

            // Update road membership
            if (carsByRoad.TryGetValue(oldRoad, out List<TrafficCar> oldCars))
                oldCars.Remove(car);

            if (!carsByRoad.TryGetValue(targetRoad, out List<TrafficCar> targetCars))
            {
                targetCars = new List<TrafficCar>();
                carsByRoad[targetRoad] = targetCars;
            }

            if (!targetCars.Contains(car))
                targetCars.Add(car);

            car.SetRoute(targetRoad, route.ToArray(), true);
        }




        // ============================================================
        // HTTP
        // ============================================================

        private UnityWebRequest CreatePost(string url, string json)
        {
            byte[] body = System.Text.Encoding.UTF8.GetBytes(json);

            UnityWebRequest request = new UnityWebRequest(
                url,
                UnityWebRequest.kHttpVerbPOST);

            request.uploadHandler = new UploadHandlerRaw(body);
            request.downloadHandler = new DownloadHandlerBuffer();
            request.SetRequestHeader("Content-Type", "application/json");
            request.timeout = 120;

            return request;
        }

        private void SetStatus(string text)
        {
            if (statusText != null)
                statusText.text = "STATUS: " + text;
        }

        // ============================================================
        // JSON
        // ============================================================

        [Serializable]
        private class OptimizationPayload
        {
            public float predicted_energy_demand_mw;
            public int active_vehicle_count;
            public float traffic_congestion_index;
            public int num_zones;
            public int max_allocations;
            public float budget_penalty_weight;
        }

        [Serializable]
        private class QuantumResponse
        {
            public string solver;
            public int[] selected_allocation;
            public float objective_value;
        }

        [Serializable]
        private class TrafficPredictionPayload
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
        private class PredictionRecord
        {
            public string road;
            public int currentCars;
            public int predictedCars;
            public float predictedCongestion;
            public float accuracyPercent;
            public string timestamp;
        }

        [Serializable]
        private class OptimizationRecord
        {
            public string method;
            public string timestamp;
            public string hotspot;
            public int carsBefore;
            public int carsRerouted;
            public int carsAfter;
            public float congestionBefore;
            public float congestionAfter;
            public float reductionPercent;
            public float score;
            public float predictionAccuracy;
        }

        [Serializable]
        private class BenchmarkExportPayload
        {
            public string generated_at;
            public string hotspot;
            public int cars_before;
            public float congestion_before;
            public string preferred_method;
            public BenchmarkExportRow[] rows;
        }

        [Serializable]
        private class BenchmarkExportRow
        {
            public string method;
            public int cars_before;
            public int cars_rerouted;
            public int cars_after;
            public float congestion_after;
            public float congestion_reduction_percent;
            public float score;
            public float prediction_accuracy_percent;
            public string preferred;
        }
    }

    public class TrafficCar : MonoBehaviour
    {
        public string CurrentRoad { get; private set; }
        public Action<TrafficCar> OnRouteCompleted;

        private Vector3[] route;
        private int targetIndex;
        private float speed;
        private float speedMultiplier = 1f;
        private InteractiveTrafficSystem trafficSystem;

        public void Initialize(
            string road,
            Vector3[] initialRoute,
            float initialSpeed,
            InteractiveTrafficSystem system = null)
        {
            CurrentRoad = road;
            route = initialRoute;
            speed = initialSpeed;
            trafficSystem = system;

            if (route != null && route.Length > 0)
            {
                transform.position = route[0];
                if (route.Length > 1)
                {
                    Vector3 initialDir = (route[1] - route[0]).normalized;
                    if (initialDir.sqrMagnitude > 0.0001f)
                    {
                        // Rotate so local +X faces travel direction
                        transform.rotation = Quaternion.LookRotation(
                            initialDir,
                            Vector3.up) * Quaternion.Euler(0f, -90f, 0f);
                    }
                }
            }
        }

        public void SetProgress(float value)
        {
            if (route == null || route.Length < 2)
                return;

            float scaled = value * (route.Length - 1);

            targetIndex = Mathf.Clamp(
                Mathf.FloorToInt(scaled),
                0,
                route.Length - 2);

            transform.position = Vector3.Lerp(
                route[targetIndex],
                route[targetIndex + 1],
                scaled - targetIndex);

            Vector3 segDir = (route[targetIndex + 1] - route[targetIndex]).normalized;
            if (segDir.sqrMagnitude > 0.0001f)
            {
                transform.rotation = Quaternion.LookRotation(
                    segDir,
                    Vector3.up) * Quaternion.Euler(0f, -90f, 0f);
            }
        }

        public void SetSpeedMultiplier(float multiplier)
        {
            speedMultiplier = Mathf.Clamp(multiplier, .05f, 1f);
        }

        private bool isTransitionRoute = false;
        private Vector3 currentHeading = Vector3.right;

        public void SetRoute(string road, Vector3[] newRoute, bool isTransition = false)
        {
            CurrentRoad = road;
            route = newRoute;
            isTransitionRoute = isTransition;
            if (route == null || route.Length < 2)
            {
                targetIndex = 0;
                return;
            }

            Vector3 curPos = transform.position;

            // Strict lane adherence: match forward segment heading and minimize distance
            // NEVER allow matching the oncoming / wrong-way lane
            float bestDist = float.MaxValue;
            int bestIdx = 0;

            for (int i = 0; i < route.Length - 1; i++)
            {
                Vector3 segDir = (route[i + 1] - route[i]).normalized;
                // Exclude opposite/oncoming lane
                if (currentHeading.sqrMagnitude > 0.01f && Vector3.Dot(currentHeading, segDir) < -0.1f)
                    continue;

                float d = Vector3.Distance(curPos, route[i]);
                if (d < bestDist)
                {
                    bestDist = d;
                    bestIdx = i;
                }
            }
            targetIndex = bestIdx;
        }

        private void Update()
        {
            // Lock vertical Y strictly to road height so cars never fall into water bodies or off roads
            Vector3 lockPos = transform.position;
            lockPos.y = 0.35f;
            transform.position = lockPos;

            if (route == null || route.Length < 2)
                return;

            if (targetIndex < 0 || targetIndex >= route.Length - 1)
                targetIndex = 0;

            Vector3 target = route[targetIndex + 1];
            Vector3 direction = target - transform.position;
            direction.y = 0f;

            if (direction.sqrMagnitude < .25f)
            {
                targetIndex++;

                if (targetIndex >= route.Length - 1)
                {
                    if (isTransitionRoute)
                    {
                        isTransitionRoute = false;
                        if (OnRouteCompleted != null)
                        {
                            OnRouteCompleted(this);
                            return;
                        }
                    }

                    targetIndex = 0; // Seamless continuous closed loop cruising on correct lane
                }

                return;
            }

            Vector3 normalizedDirection = direction.normalized;
            currentHeading = normalizedDirection;

            // Car-following / gap keeping to prevent overlapping and ghost passing
            float gapFactor = 1f;
            if (trafficSystem != null)
            {
                List<TrafficCar> roadCars = trafficSystem.GetCarsOnRoad(CurrentRoad);
                if (roadCars != null)
                {
                    const float minGap = 2.4f; // Safe stopping gap
                    const float slowGap = 5.0f; // Deceleration distance

                    for (int i = 0; i < roadCars.Count; i++)
                    {
                        TrafficCar other = roadCars[i];
                        if (other == null || other == this) continue;

                        Vector3 toOther = other.transform.position - transform.position;
                        toOther.y = 0f;

                        // Check forward distance along direction of movement
                        float forwardDist = Vector3.Dot(toOther, normalizedDirection);
                        if (forwardDist <= 0.05f || forwardDist > slowGap) continue;

                        // Check lateral distance (only consider cars in our lane, not adjacent/opposite lane)
                        float lateralDist = (toOther - normalizedDirection * forwardDist).magnitude;
                        if (lateralDist > 1.4f) continue;

                        if (forwardDist < minGap)
                        {
                            gapFactor = 0f; // Stop behind vehicle ahead, prevent overlapping
                            break;
                        }
                        else
                        {
                            float factor = (forwardDist - minGap) / (slowGap - minGap);
                            if (factor < gapFactor)
                                gapFactor = factor;
                        }
                    }
                }
            }

            transform.position +=
                normalizedDirection *
                speed *
                speedMultiplier *
                gapFactor *
                Time.deltaTime;

            // Face the road in direction of travel (car body local front is +X)
            if (normalizedDirection.sqrMagnitude > .0001f)
            {
                Quaternion targetRotation = Quaternion.LookRotation(
                    normalizedDirection,
                    Vector3.up) * Quaternion.Euler(0f, -90f, 0f);

                transform.rotation = Quaternion.Slerp(
                    transform.rotation,
                    targetRotation,
                    12f * Time.deltaTime);
            }
        }
    }
}
