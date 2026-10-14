using UnityEngine;
using System.Collections.Generic;

namespace QuantumCity.City
{
    /// <summary>
    /// Procedurally generates a polished realistic low-poly smart city.
    ///
    /// Features:
    /// - Varied building heights and proportions
    /// - Neutral building colors
    /// - Windows
    /// - Rooftops and rooftop equipment
    /// - Dark asphalt roads
    /// - White road markings
    /// - Street lamps
    /// - Light blue daytime environment
    /// - Low-poly geometry suitable for a large procedural city
    /// </summary>
    public class CityGridBuilder : MonoBehaviour
    {
        [Header("Grid Dimensions")]
        [SerializeField] private int gridWidth = 10;
        [SerializeField] private int gridDepth = 10;
        [SerializeField] private float blockSize = 12f;
        [SerializeField] private float roadWidth = 2.5f;

        [Header("Building Generation")]
        [SerializeField] private int minBuildingsPerBlock = 2;
        [SerializeField] private int maxBuildingsPerBlock = 6;
        [SerializeField] private float minHeight = 2.5f;
        [SerializeField] private float maxHeight = 26f; // Impressive skyline depth matching image 2

        [Header("Visuals")]
        [SerializeField] private Material buildingMaterial;
        [SerializeField] private Material roadMaterial;
        [SerializeField] private Material windowMaterial;

        private GameObject _cityRoot;

        private Material _matBuilding;
        private Material _matRoad;
        private Material _matWindow;
        private Material _matRoadMarking;
        private Material _matLamp;
        private Material _matLampGlow;
        private Material _matTreeFoliage;
        private Material _matTreeTrunk;
        private Material _matGrass;
        private Material _matSidewalk;
        private Material _matWater;
        private Material _matWaterRim;
        private Material _matCloud;
        private Material _matGlassTower;
        private Material _matBridge;

        // ============================================================
        // BUILDING COLOR PALETTE (Soft Pastel Minimal Aesthetic)
        // ============================================================

        private readonly Color[] buildingColors =
        {
            new Color(0.92f, 0.93f, 0.95f), // Soft pastel off-white / alabaster
            new Color(0.85f, 0.89f, 0.88f), // Soft pastel sage / mint
            new Color(0.82f, 0.86f, 0.91f), // Soft pastel misty blue
            new Color(0.92f, 0.90f, 0.86f), // Soft pastel linen cream
            new Color(0.88f, 0.88f, 0.90f), // Soft pastel stone grey
            new Color(0.92f, 0.89f, 0.87f), // Soft pastel blush almond
            new Color(0.84f, 0.88f, 0.90f), // Soft pastel duck egg blue
            new Color(0.89f, 0.91f, 0.87f)  // Soft pastel matcha cream
        };

        // ============================================================
        // START
        // ============================================================

        private void Start()
        {
            InitializeMaterials();
            BuildCity();
        }

        // ============================================================
        // MATERIAL INITIALIZATION
        // ============================================================

        private void InitializeMaterials()
        {
            _matBuilding =
                buildingMaterial != null
                    ? buildingMaterial
                    : CreateBuildingMaterial();

            _matRoad =
                roadMaterial != null
                    ? roadMaterial
                    : CreateRoadMaterial();

            _matWindow =
                windowMaterial != null
                    ? windowMaterial
                    : CreateWindowMaterial();

            _matRoadMarking =
                CreateRoadMarkingMaterial();

            _matLamp =
                CreateLampMaterial();

            _matLampGlow =
                CreateLampGlowMaterial();

            _matTreeFoliage =
                CreateTreeFoliageMaterial();

            _matTreeTrunk =
                CreateTreeTrunkMaterial();

            _matGrass = CreateGrassMaterial();
            _matSidewalk = CreateSidewalkMaterial();
            _matWater = CreateWaterMaterial();
            _matWaterRim = CreateWaterRimMaterial();
            _matCloud = CreateCloudMaterial();
            _matGlassTower = CreateGlassTowerMaterial();
            _matBridge = CreateBridgeMaterial();
        }

        // ============================================================
        // SAFE SHADER
        // ============================================================

        private Shader GetSafeShader()
        {
            Shader shader =
                Shader.Find("Universal Render Pipeline/Lit");

            if (shader == null)
                shader = Shader.Find("Standard");

            return shader;
        }

        // ============================================================
        // BUILDING MATERIAL
        // ============================================================

        private Material CreateBuildingMaterial()
        {
            Shader shader = GetSafeShader();

            Material mat = new Material(shader);

            Color buildingBase =
                new Color(
                    0.74f,
                    0.77f,
                    0.80f,
                    1f);

            if (mat.HasProperty("_BaseColor"))
            {
                mat.SetColor(
                    "_BaseColor",
                    buildingBase);
            }
            else if (mat.HasProperty("_Color"))
            {
                mat.SetColor(
                    "_Color",
                    buildingBase);
            }

            if (mat.HasProperty("_Smoothness"))
                mat.SetFloat("_Smoothness", 0.35f);

            if (mat.HasProperty("_Metallic"))
                mat.SetFloat("_Metallic", 0.05f);

            mat.enableInstancing = true;

            return mat;
        }

        // ============================================================
        // ROAD MATERIAL
        // ============================================================

        private Material CreateRoadMaterial()
        {
            Shader shader = GetSafeShader();

            Material mat = new Material(shader);

            Color asphalt =
                new Color(
                    0.01f,
                    0.01f,
                    0.01f,
                    1f);

            if (mat.HasProperty("_BaseColor"))
            {
                mat.SetColor(
                    "_BaseColor",
                    asphalt);
            }
            else if (mat.HasProperty("_Color"))
            {
                mat.SetColor(
                    "_Color",
                    asphalt);
            }

            if (mat.HasProperty("_Smoothness"))
                mat.SetFloat("_Smoothness", 0.18f);

            if (mat.HasProperty("_Metallic"))
                mat.SetFloat("_Metallic", 0.02f);

            mat.enableInstancing = true;

            return mat;
        }

        // ============================================================
        // WINDOW MATERIAL
        // ============================================================

        private Material CreateWindowMaterial()
        {
            Shader shader = GetSafeShader();
            Material mat = new Material(shader);

            Color softGlass = new Color(0.88f, 0.92f, 0.96f, 1f); // Soft pastel daylight glass

            if (mat.HasProperty("_BaseColor"))
                mat.SetColor("_BaseColor", softGlass);
            else if (mat.HasProperty("_Color"))
                mat.SetColor("_Color", softGlass);

            if (mat.HasProperty("_EmissionColor"))
            {
                mat.EnableKeyword("_EMISSION");
                mat.SetColor(
                    "_EmissionColor",
                    new Color(0.24f, 0.26f, 0.30f, 1f)); // Minimal subtle ambient glow
            }

            if (mat.HasProperty("_Smoothness"))
                mat.SetFloat("_Smoothness", 0.70f);

            if (mat.HasProperty("_Metallic"))
                mat.SetFloat("_Metallic", 0.05f);

            mat.enableInstancing = true;

            return mat;
        }


        // ============================================================
        // ROAD MARKING MATERIAL
        // ============================================================

        private Material CreateRoadMarkingMaterial()
        {
            Shader shader = GetSafeShader();

            Material mat = new Material(shader);

            Color white =
                new Color(
                    0.92f,
                    0.94f,
                    0.95f,
                    1f);

            if (mat.HasProperty("_BaseColor"))
            {
                mat.SetColor(
                    "_BaseColor",
                    white);
            }
            else if (mat.HasProperty("_Color"))
            {
                mat.SetColor(
                    "_Color",
                    white);
            }

            if (mat.HasProperty("_Smoothness"))
                mat.SetFloat("_Smoothness", 0.25f);

            mat.enableInstancing = true;

            return mat;
        }

        // ============================================================
        // LAMP MATERIAL
        // ============================================================

        private Material CreateLampMaterial()
        {
            Shader shader = GetSafeShader();

            Material mat = new Material(shader);

            Color metal =
                new Color(
                    0.16f,
                    0.18f,
                    0.20f,
                    1f);

            if (mat.HasProperty("_BaseColor"))
            {
                mat.SetColor(
                    "_BaseColor",
                    metal);
            }
            else if (mat.HasProperty("_Color"))
            {
                mat.SetColor(
                    "_Color",
                    metal);
            }

            if (mat.HasProperty("_Metallic"))
                mat.SetFloat("_Metallic", 0.55f);

            if (mat.HasProperty("_Smoothness"))
                mat.SetFloat("_Smoothness", 0.6f);

            return mat;
        }

        // ============================================================
        // LAMP GLOW MATERIAL
        // ============================================================

        private Material CreateLampGlowMaterial()
        {
            Shader shader =
                Shader.Find(
                    "Universal Render Pipeline/Unlit");

            if (shader == null)
                shader = GetSafeShader();

            Material mat =
                new Material(shader);

            Color warmLight =
                new Color(
                    1.0f,
                    0.86f,
                    0.58f,
                    1f);

            if (mat.HasProperty("_BaseColor"))
            {
                mat.SetColor(
                    "_BaseColor",
                    warmLight);
            }
            else if (mat.HasProperty("_Color"))
            {
                mat.SetColor(
                    "_Color",
                    warmLight);
            }

            return mat;
        }

        // ============================================================
        // TREE MATERIALS
        // ============================================================

        private Material CreateTreeFoliageMaterial()
        {
            Shader shader = GetSafeShader();
            Material mat = new Material(shader);
            Color green = new Color(0.22f, 0.55f, 0.28f, 1f);
            if (mat.HasProperty("_BaseColor"))
                mat.SetColor("_BaseColor", green);
            else if (mat.HasProperty("_Color"))
                mat.SetColor("_Color", green);

            if (mat.HasProperty("_Smoothness"))
                mat.SetFloat("_Smoothness", 0.1f);

            mat.enableInstancing = true;
            return mat;
        }

        private Material CreateTreeTrunkMaterial()
        {
            Shader shader = GetSafeShader();
            Material mat = new Material(shader);
            Color wood = new Color(0.35f, 0.24f, 0.16f, 1f);
            if (mat.HasProperty("_BaseColor"))
                mat.SetColor("_BaseColor", wood);
            else if (mat.HasProperty("_Color"))
                mat.SetColor("_Color", wood);

            if (mat.HasProperty("_Smoothness"))
                mat.SetFloat("_Smoothness", 0.1f);

            mat.enableInstancing = true;
            return mat;
        }

        private Material CreateGrassMaterial()
        {
            Shader shader = GetSafeShader();
            Material mat = new Material(shader);
            Color grass = new Color(0.28f, 0.58f, 0.24f, 1f); // Vibrant lush grass matching image 2
            if (mat.HasProperty("_BaseColor"))
                mat.SetColor("_BaseColor", grass);
            else if (mat.HasProperty("_Color"))
                mat.SetColor("_Color", grass);
            if (mat.HasProperty("_Smoothness"))
                mat.SetFloat("_Smoothness", 0.15f);
            mat.enableInstancing = true;
            return mat;
        }

        private Material CreateSidewalkMaterial()
        {
            Shader shader = GetSafeShader();
            Material mat = new Material(shader);
            Color concrete = new Color(0.76f, 0.79f, 0.82f, 1f); // Clean light architectural concrete
            if (mat.HasProperty("_BaseColor"))
                mat.SetColor("_BaseColor", concrete);
            else if (mat.HasProperty("_Color"))
                mat.SetColor("_Color", concrete);
            if (mat.HasProperty("_Smoothness"))
                mat.SetFloat("_Smoothness", 0.25f);
            mat.enableInstancing = true;
            return mat;
        }

        private Material CreateWaterMaterial()
        {
            Shader shader = GetSafeShader();
            Material mat = new Material(shader);
            Color water = new Color(0.12f, 0.48f, 0.82f, 0.90f); // Translucent azure blue pond water
            if (mat.HasProperty("_BaseColor"))
                mat.SetColor("_BaseColor", water);
            else if (mat.HasProperty("_Color"))
                mat.SetColor("_Color", water);
            if (mat.HasProperty("_Smoothness"))
                mat.SetFloat("_Smoothness", 0.95f);
            if (mat.HasProperty("_Metallic"))
                mat.SetFloat("_Metallic", 0.20f);
            mat.enableInstancing = true;
            return mat;
        }

        private Material CreateWaterRimMaterial()
        {
            Shader shader = GetSafeShader();
            Material mat = new Material(shader);
            Color stone = new Color(0.72f, 0.75f, 0.78f, 1f); // Smooth light grey stone curb
            if (mat.HasProperty("_BaseColor"))
                mat.SetColor("_BaseColor", stone);
            else if (mat.HasProperty("_Color"))
                mat.SetColor("_Color", stone);
            if (mat.HasProperty("_Smoothness"))
                mat.SetFloat("_Smoothness", 0.35f);
            mat.enableInstancing = true;
            return mat;
        }

        private Material CreateCloudMaterial()
        {
            Shader shader = GetSafeShader();
            Material mat = new Material(shader);
            Color cloud = new Color(0.98f, 0.98f, 1.0f, 0.95f); // Soft puffy cumulus white
            if (mat.HasProperty("_BaseColor"))
                mat.SetColor("_BaseColor", cloud);
            else if (mat.HasProperty("_Color"))
                mat.SetColor("_Color", cloud);
            if (mat.HasProperty("_Smoothness"))
                mat.SetFloat("_Smoothness", 0.05f);
            mat.enableInstancing = true;
            return mat;
        }

        private Material CreateGlassTowerMaterial()
        {
            Shader shader = GetSafeShader();
            Material mat = new Material(shader);
            Color glass = new Color(0.18f, 0.45f, 0.72f, 1f); // Modern cyan/blue glass tower
            if (mat.HasProperty("_BaseColor"))
                mat.SetColor("_BaseColor", glass);
            else if (mat.HasProperty("_Color"))
                mat.SetColor("_Color", glass);
            if (mat.HasProperty("_Smoothness"))
                mat.SetFloat("_Smoothness", 0.88f);
            if (mat.HasProperty("_Metallic"))
                mat.SetFloat("_Metallic", 0.65f);
            mat.enableInstancing = true;
            return mat;
        }

        private Material CreateBridgeMaterial()
        {
            Shader shader = GetSafeShader();
            Material mat = new Material(shader);
            Color bridge = new Color(0.68f, 0.71f, 0.74f, 1f); // Concrete overpass bridge
            if (mat.HasProperty("_BaseColor"))
                mat.SetColor("_BaseColor", bridge);
            else if (mat.HasProperty("_Color"))
                mat.SetColor("_Color", bridge);
            if (mat.HasProperty("_Smoothness"))
                mat.SetFloat("_Smoothness", 0.28f);
            mat.enableInstancing = true;
            return mat;
        }

        // ============================================================
        // BUILD CITY
        // ============================================================

        private void BuildCity()
        {
            // --------------------------------------------------------
            // DAYTIME ENVIRONMENT (MATCHING IMAGE 2)
            // --------------------------------------------------------

            RenderSettings.ambientLight =
                new Color(0.74f, 0.84f, 0.94f);

            RenderSettings.fog = true;

            RenderSettings.fogColor =
                new Color(0.52f, 0.74f, 0.92f);

            RenderSettings.fogDensity =
                0.0016f;

            if (Camera.main != null)
            {
                Camera.main.clearFlags = CameraClearFlags.SolidColor;
                Camera.main.backgroundColor =
                    new Color(0.42f, 0.68f, 0.95f); // Rich daytime blue sky
            }

            // --------------------------------------------------------
            // ROOT
            // --------------------------------------------------------

            _cityRoot =
                new GameObject("ProceduralCityEnvironment");

            _cityRoot.transform.SetParent(
                transform,
                false);

            // --------------------------------------------------------
            // CITY DIMENSIONS
            // --------------------------------------------------------

            float totalWidth =
                gridWidth * blockSize;

            float totalDepth =
                gridDepth * blockSize;

            float offsetX =
                -totalWidth * 0.5f;

            float offsetZ =
                -totalDepth * 0.5f;

            // 1. Lush Green Ground Terrain Base
            CreateGroundTerrain(totalWidth * 1.6f, totalDepth * 1.6f);

            // --------------------------------------------------------
            // 2. GENERATE BLOCKS & BUILDINGS
            // --------------------------------------------------------

            for (int x = 0; x < gridWidth; x++)
            {
                for (int z = 0; z < gridDepth; z++)
                {
                    float wx =
                        offsetX +
                        x * blockSize +
                        blockSize * 0.5f;

                    float wz =
                        offsetZ +
                        z * blockSize +
                        blockSize * 0.5f;

                    Vector3 blockCenter =
                        new Vector3(wx, 0f, wz);

                    float buildableSize = 6.2f;

                    GenerateBlock(
                        blockCenter,
                        buildableSize,
                        x,
                        z);
                }
            }

            // --------------------------------------------------------
            // 3. ROADS & OVERPASS BRIDGE
            // --------------------------------------------------------

            GenerateRoadNetwork(
                offsetX,
                offsetZ,
                totalWidth,
                totalDepth);

            // --------------------------------------------------------
            // 4. SKY & PROCEDURAL 3D CLOUDS (MATCHING IMAGE 2)
            // --------------------------------------------------------

            CreateClouds(totalWidth, totalDepth);

            Debug.Log(
                $"[CityGridBuilder] Visual City generated: " +
                $"{gridWidth}x{gridDepth} blocks with sky, clouds, and realistic depth.");
        }

        private void CreateGroundTerrain(float width, float depth)
        {
            // Recolor any existing scene Ground object to lush green to completely eliminate white borders
            GameObject existingGround = GameObject.Find("Ground");
            if (existingGround != null)
            {
                MeshRenderer mr = existingGround.GetComponent<MeshRenderer>();
                if (mr != null)
                    mr.material = _matGrass;

                existingGround.transform.localScale = new Vector3(450f, 0.1f, 450f);
                existingGround.transform.position = new Vector3(0f, -0.055f, 0f);
            }

            GameObject terrain =
                GameObject.CreatePrimitive(PrimitiveType.Cube);

            terrain.name = "LushGrassLandscape";
            terrain.transform.SetParent(_cityRoot.transform, false);
            terrain.transform.position = new Vector3(0f, -0.05f, 0f);
            terrain.transform.localScale = new Vector3(450f, 0.1f, 450f);
            Destroy(terrain.GetComponent<Collider>());
            terrain.GetComponent<MeshRenderer>().material = _matGrass;
        }

        private void CreateClouds(float totalWidth, float totalDepth)
        {
            GameObject cloudsRoot = new GameObject("CloudsSkyLayer");
            cloudsRoot.transform.SetParent(_cityRoot.transform, false);

            int cloudCount = 18;
            for (int i = 0; i < cloudCount; i++)
            {
                GameObject cloud = new GameObject($"Cloud_{i}");
                cloud.transform.SetParent(cloudsRoot.transform, false);

                float cx = Random.Range(-totalWidth * 0.65f, totalWidth * 0.65f);
                float cz = Random.Range(-totalDepth * 0.65f, totalDepth * 0.65f);
                float cy = Random.Range(38f, 54f);
                cloud.transform.position = new Vector3(cx, cy, cz);

                int puffs = Random.Range(5, 9);
                for (int p = 0; p < puffs; p++)
                {
                    GameObject puff = GameObject.CreatePrimitive(PrimitiveType.Sphere);
                    puff.name = "Puff";
                    puff.transform.SetParent(cloud.transform, false);
                    Destroy(puff.GetComponent<Collider>());

                    float px = Random.Range(-4.5f, 4.5f);
                    float py = Random.Range(-1.2f, 1.5f);
                    float pz = Random.Range(-3.5f, 3.5f);
                    puff.transform.localPosition = new Vector3(px, py, pz);

                    float sx = Random.Range(5.5f, 9.5f);
                    float sy = Random.Range(3.2f, 5.0f);
                    float sz = Random.Range(5.5f, 8.5f);
                    puff.transform.localScale = new Vector3(sx, sy, sz);

                    puff.GetComponent<MeshRenderer>().material = _matCloud;
                }
            }
        }

        // ============================================================
        // GENERATE BLOCK
        // ============================================================

        private void GenerateBlock(
            Vector3 center,
            float size,
            int gridX,
            int gridZ)
        {
            GameObject blockParent =
                new GameObject($"Block_{gridX}_{gridZ}");

            blockParent.transform.SetParent(
                _cityRoot.transform,
                false);

            blockParent.transform.position =
                center;

            // Green grass lawn foundation where buildings stand
            GameObject grassPad =
                GameObject.CreatePrimitive(PrimitiveType.Cube);

            grassPad.name = "BlockGrassPad";
            grassPad.transform.SetParent(blockParent.transform, false);
            grassPad.transform.localPosition = new Vector3(0f, 0.04f, 0f);
            grassPad.transform.localScale = new Vector3(size + 0.8f, 0.08f, size + 0.8f);
            Destroy(grassPad.GetComponent<Collider>());
            grassPad.GetComponent<MeshRenderer>().material = _matGrass;

            // Concrete perimeter sidewalk curb around the block
            GameObject sidewalk =
                GameObject.CreatePrimitive(PrimitiveType.Cube);

            sidewalk.name = "BlockSidewalk";
            sidewalk.transform.SetParent(blockParent.transform, false);
            sidewalk.transform.localPosition = new Vector3(0f, 0.02f, 0f);
            sidewalk.transform.localScale = new Vector3(size + 1.6f, 0.04f, size + 1.6f);
            Destroy(sidewalk.GetComponent<Collider>());
            sidewalk.GetComponent<MeshRenderer>().material = _matSidewalk;

            // --------------------------------------------------------
            // NUMBER OF BUILDINGS
            // --------------------------------------------------------

            int numBuildings =
                Random.Range(
                    minBuildingsPerBlock,
                    maxBuildingsPerBlock + 1);

            int subGridSize = numBuildings > 4 ? 3 : 2;
            float cellSize = size / subGridSize;
            float halfSize = size * 0.5f;

            List<Vector2> availableCells = new List<Vector2>();
            for (int i = 0; i < subGridSize; i++)
            {
                for (int j = 0; j < subGridSize; j++)
                {
                    availableCells.Add(new Vector2(i, j));
                }
            }

            // Shuffle
            for (int i = 0; i < availableCells.Count; i++)
            {
                int r = Random.Range(i, availableCells.Count);
                Vector2 temp = availableCells[i];
                availableCells[i] = availableCells[r];
                availableCells[r] = temp;
            }

            // Safe from vehicle roads: Roads A, B, C (Z = 0, 12, -12), D, E (X = -24, 24)
            bool isSafeFromRoads =
                Mathf.Abs(center.z) > 3.5f &&
                Mathf.Abs(center.z - 12f) > 3.5f &&
                Mathf.Abs(center.z + 12f) > 3.5f &&
                Mathf.Abs(center.x - 24f) > 3.5f &&
                Mathf.Abs(center.x + 24f) > 3.5f;

            // Courtyard Pond near buildings (strictly inside courtyard, not on or near roads)
            bool pondPlaced = false;
            if (isSafeFromRoads && (gridX + gridZ) % 3 == 0 && availableCells.Count > numBuildings)
            {
                Vector2 pondCell = availableCells[availableCells.Count - 1];
                float px = -halfSize + pondCell.x * cellSize + cellSize * 0.5f;
                float pz = -halfSize + pondCell.y * cellSize + cellSize * 0.5f;
                CreateCourtyardPond(
                    blockParent.transform,
                    new Vector3(px, 0.05f, pz),
                    cellSize * 0.85f,
                    cellSize * 0.85f);
                pondPlaced = true;
            }

            int buildingCount = pondPlaced
                ? Mathf.Min(numBuildings, availableCells.Count - 1)
                : Mathf.Min(numBuildings, availableCells.Count);

            for (int i = 0; i < buildingCount; i++)
            {
                int cx = (int)availableCells[i].x;
                int cz = (int)availableCells[i].y;

                float localX =
                    -halfSize + cx * cellSize + cellSize * 0.5f;

                float localZ =
                    -halfSize + cz * cellSize + cellSize * 0.5f;

                float bWidth =
                    cellSize * Random.Range(0.68f, 0.92f);

                float bDepth =
                    cellSize * Random.Range(0.68f, 0.92f);

                float distToCenter =
                    Vector2.Distance(
                        new Vector2(center.x, center.z),
                        Vector2.zero);

                float maxDist =
                    (gridWidth * blockSize) * 0.5f;

                float heightMultiplier =
                    1f - Mathf.Clamp01(distToCenter / maxDist);

                float randomHeight =
                    Random.Range(
                        minHeight,
                        minHeight + (maxHeight - minHeight) * 0.35f);

                float skylineHeight =
                    Random.Range(0f, maxHeight * 0.85f) * heightMultiplier;

                float bHeight =
                    Mathf.Max(randomHeight + skylineHeight, 3.5f);

                Vector3 bLocalPos =
                    new Vector3(localX, bHeight * 0.5f, localZ);

                Vector3 bScale =
                    new Vector3(bWidth, bHeight, bDepth);

                CreateBuilding(
                    blockParent.transform,
                    bLocalPos,
                    bScale,
                    i);
            }
        }

        private void CreateCourtyardPond(
            Transform parent,
            Vector3 localPos,
            float width,
            float depth)
        {
            GameObject pondObj = new GameObject("CourtyardPond");
            pondObj.transform.SetParent(parent, false);
            pondObj.transform.localPosition = localPos;

            // Raised stone curb border around the pond
            GameObject rim = GameObject.CreatePrimitive(PrimitiveType.Cube);
            rim.name = "PondRim";
            rim.transform.SetParent(pondObj.transform, false);
            rim.transform.localPosition = new Vector3(0f, 0.03f, 0f);
            rim.transform.localScale = new Vector3(width * 0.95f, 0.08f, depth * 0.95f);
            Destroy(rim.GetComponent<Collider>());
            rim.GetComponent<MeshRenderer>().material = _matWaterRim;

            // Reflective azure water surface
            GameObject water = GameObject.CreatePrimitive(PrimitiveType.Cube);
            water.name = "PondWater";
            water.transform.SetParent(pondObj.transform, false);
            water.transform.localPosition = new Vector3(0f, 0.055f, 0f);
            water.transform.localScale = new Vector3(width * 0.80f, 0.04f, depth * 0.80f);
            Destroy(water.GetComponent<Collider>());
            water.GetComponent<MeshRenderer>().material = _matWater;

            // Decorative park tree beside the pond
            CreateTree(pondObj.transform, new Vector3(width * 0.38f, 0f, depth * 0.38f));
        }

        // ============================================================
        // CREATE BUILDING (WITH SKYSCRAPER DEPTH MATCHING IMAGE 2)
        // ============================================================

        private void CreateBuilding(
            Transform parent,
            Vector3 localPos,
            Vector3 scale,
            int index)
        {
            // --------------------------------------------------------
            // MAIN BUILDING
            // --------------------------------------------------------

            GameObject building =
                GameObject.CreatePrimitive(PrimitiveType.Cube);

            building.name = $"Building_{index}";
            building.transform.SetParent(parent, false);
            building.transform.localPosition = localPos;
            building.transform.localScale = scale;
            Destroy(building.GetComponent<Collider>());

            MeshRenderer renderer =
                building.GetComponent<MeshRenderer>();

            Material buildingMat = new Material(_matBuilding);
            Color selectedColor =
                buildingColors[Random.Range(0, buildingColors.Length)];

            if (buildingMat.HasProperty("_BaseColor"))
                buildingMat.SetColor("_BaseColor", selectedColor);
            else if (buildingMat.HasProperty("_Color"))
                buildingMat.SetColor("_Color", selectedColor);

            renderer.material = (index % 3 == 0) ? _matGlassTower : buildingMat;
            renderer.receiveShadows = true;
            renderer.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.On;

            // --------------------------------------------------------
            // AESTHETIC ARCHITECTURAL SETBACK & CROWN
            // --------------------------------------------------------

            if (scale.y > 8.5f)
            {
                // Elegant setback upper crown tier
                GameObject setback = GameObject.CreatePrimitive(PrimitiveType.Cube);
                setback.name = "ArchitecturalSetback";
                setback.transform.SetParent(building.transform, false);
                setback.transform.localPosition = new Vector3(0f, 0.62f, 0f);
                setback.transform.localScale = new Vector3(0.78f, 0.24f, 0.78f);
                Destroy(setback.GetComponent<Collider>());
                setback.GetComponent<MeshRenderer>().material = buildingMat;
            }

            // Subtle vertical architectural accents
            if (scale.y > 5.5f)
            {
                for (int sx = -1; sx <= 1; sx += 2)
                {
                    for (int sz = -1; sz <= 1; sz += 2)
                    {
                        GameObject stripe = GameObject.CreatePrimitive(PrimitiveType.Cube);
                        stripe.name = "FacadeCorner";
                        stripe.transform.SetParent(building.transform, false);
                        stripe.transform.localPosition = new Vector3(sx * 0.49f, 0f, sz * 0.49f);
                        stripe.transform.localScale = new Vector3(0.04f, 1.01f, 0.04f);
                        Destroy(stripe.GetComponent<Collider>());
                        stripe.GetComponent<MeshRenderer>().material = _matSidewalk;
                    }
                }
            }

            // --------------------------------------------------------
            // ROOFTOP
            // --------------------------------------------------------

            GameObject roof =
                GameObject.CreatePrimitive(PrimitiveType.Cube);

            roof.name = "Rooftop";
            roof.transform.SetParent(building.transform, false);
            roof.transform.localPosition = new Vector3(0f, 0.51f, 0f);
            roof.transform.localScale = new Vector3(1.04f, 0.04f, 1.04f);
            Destroy(roof.GetComponent<Collider>());

            Material roofMaterial = new Material(_matBuilding);
            Color roofColor = new Color(0.44f, 0.47f, 0.50f);

            if (roofMaterial.HasProperty("_BaseColor"))
                roofMaterial.SetColor("_BaseColor", roofColor);
            else if (roofMaterial.HasProperty("_Color"))
                roofMaterial.SetColor("_Color", roofColor);

            roof.GetComponent<MeshRenderer>().material = roofMaterial;

            // --------------------------------------------------------
            // WINDOWS
            // --------------------------------------------------------

            AddBuildingWindows(building.transform, scale);
        }

        // ============================================================
        // BUILDING WINDOWS
        // ============================================================

        private void AddBuildingWindows(
            Transform building,
            Vector3 scale)
        {
            // --------------------------------------------------------
            // NUMBER OF FLOORS
            // --------------------------------------------------------

            int floors =
                Mathf.Clamp(
                    Mathf.RoundToInt(
                        scale.y / 1.5f),
                    2,
                    8);

            // Keep the number of windows reasonable
            // for performance.
            int windowsPerFloor =
                Mathf.Clamp(
                    Mathf.RoundToInt(
                        scale.x * 1.15f),
                    2,
                    5);

            // --------------------------------------------------------
            // FRONT WINDOWS
            // --------------------------------------------------------

            for (int floor = 0;
                 floor < floors;
                 floor++)
            {
                float y =
                    -0.42f +
                    ((float)floor /
                    Mathf.Max(
                        1,
                        floors - 1)) *
                    0.84f;

                for (int w = 0;
                     w < windowsPerFloor;
                     w++)
                {
                    float x =
                        -0.38f +
                        ((float)w /
                        Mathf.Max(
                            1,
                            windowsPerFloor - 1)) *
                        0.76f;

                    CreateWindow(
                        building,
                        new Vector3(
                            x,
                            y,
                            -0.505f),
                        new Vector3(
                            0.09f,
                            0.075f,
                            0.018f));
                }
            }

            // --------------------------------------------------------
            // SIDE WINDOWS
            // --------------------------------------------------------

            int sideWindows =
                Mathf.Clamp(
                    Mathf.RoundToInt(
                        scale.z * 1.1f),
                    2,
                    4);

            for (int floor = 0;
                 floor < floors;
                 floor++)
            {
                float y =
                    -0.42f +
                    ((float)floor /
                    Mathf.Max(
                        1,
                        floors - 1)) *
                    0.84f;

                for (int w = 0;
                     w < sideWindows;
                     w++)
                {
                    float z =
                        -0.36f +
                        ((float)w /
                        Mathf.Max(
                            1,
                            sideWindows - 1)) *
                        0.72f;

                    CreateWindow(
                        building,
                        new Vector3(
                            -0.505f,
                            y,
                            z),
                        new Vector3(
                            0.018f,
                            0.075f,
                            0.09f));
                }
            }
        }

        // ============================================================
        // CREATE SINGLE WINDOW
        // ============================================================

        private void CreateWindow(
            Transform building,
            Vector3 localPosition,
            Vector3 localScale)
        {
            GameObject window =
                GameObject.CreatePrimitive(
                    PrimitiveType.Cube);

            window.name =
                "Window";

            window.transform.SetParent(
                building,
                false);

            window.transform.localPosition =
                localPosition;

            window.transform.localScale =
                localScale;

            Destroy(
                window.GetComponent<Collider>());

            MeshRenderer renderer =
                window.GetComponent<MeshRenderer>();

            renderer.material =
                _matWindow;

            renderer.shadowCastingMode =
                UnityEngine.Rendering
                    .ShadowCastingMode.Off;

            renderer.receiveShadows =
                false;
        }

        // ============================================================
        // OLD EMISSIVE WINDOW BANDS
        // ============================================================

        private void AddEmissiveWindows(
            Transform building,
            Vector3 bScale)
        {
            int numBands =
                Random.Range(1, 4);

            for (int i = 0;
                 i < numBands;
                 i++)
            {
                GameObject band =
                    GameObject.CreatePrimitive(
                        PrimitiveType.Cube);

                band.name =
                    "WindowBand";

                band.transform.SetParent(
                    building,
                    false);

                Destroy(
                    band.GetComponent<Collider>());

                float yPos =
                    Random.Range(
                        -0.4f,
                        0.4f);

                band.transform.localPosition =
                    new Vector3(
                        0f,
                        yPos,
                        0f);

                float thickness =
                    Random.Range(
                        0.02f,
                        0.08f) /
                    bScale.y;

                band.transform.localScale =
                    new Vector3(
                        1.02f,
                        thickness,
                        1.02f);

                MeshRenderer mr =
                    band.GetComponent<MeshRenderer>();

                mr.material =
                    _matWindow;

                mr.shadowCastingMode =
                    UnityEngine.Rendering
                        .ShadowCastingMode.Off;

                mr.receiveShadows =
                    false;
            }
        }

        // ============================================================
        // ROAD NETWORK
        // ============================================================

        private void GenerateRoadNetwork(
            float offsetX,
            float offsetZ,
            float totalWidth,
            float totalDepth)
        {
            GameObject roadRoot =
                new GameObject(
                    "RoadNetwork");

            roadRoot.transform.SetParent(
                _cityRoot.transform,
                false);

            // --------------------------------------------------------
            // MAIN ASPHALT
            // --------------------------------------------------------

            GameObject mainRoad =
                GameObject.CreatePrimitive(
                    PrimitiveType.Plane);

            mainRoad.name =
                "MainRoadBase";

            mainRoad.transform.SetParent(
                roadRoot.transform,
                false);

            mainRoad.transform.localScale =
                new Vector3(
                    totalWidth / 10f,
                    1f,
                    totalDepth / 10f);

            mainRoad.transform.position =
                new Vector3(
                    0f,
                    0.01f,
                    0f);

            Destroy(
                mainRoad.GetComponent<Collider>());

            MeshRenderer roadRenderer =
                mainRoad.GetComponent<MeshRenderer>();

            roadRenderer.material =
                _matRoad;

            roadRenderer.receiveShadows =
                true;

            roadRenderer.shadowCastingMode =
                UnityEngine.Rendering
                    .ShadowCastingMode.Off;

            // --------------------------------------------------------
            // ROAD MARKINGS
            // --------------------------------------------------------

            // Vertical roads
            for (int x = 0;
                 x <= gridWidth;
                 x++)
            {
                float wx =
                    offsetX +
                    x * blockSize;

                CreateStreetMarking(
                    roadRoot.transform,
                    $"MarkingV_{x}",
                    new Vector3(
                        wx,
                        0.025f,
                        offsetZ),
                    new Vector3(
                        wx,
                        0.025f,
                        offsetZ +
                        totalDepth));
            }

            // Horizontal roads
            for (int z = 0;
                 z <= gridDepth;
                 z++)
            {
                float wz =
                    offsetZ +
                    z * blockSize;

                CreateStreetMarking(
                    roadRoot.transform,
                    $"MarkingH_{z}",
                    new Vector3(
                        offsetX,
                        0.025f,
                        wz),
                    new Vector3(
                        offsetX +
                        totalWidth,
                        0.025f,
                        wz));
            }

            // --------------------------------------------------------
            // STREET LAMPS & TREES
            // --------------------------------------------------------

            CreateStreetLamps(
                roadRoot.transform,
                offsetX,
                offsetZ,
                totalWidth,
                totalDepth);

            CreateStreetTrees(
                roadRoot.transform,
                offsetX,
                offsetZ,
                totalWidth,
                totalDepth);
        }

        // ============================================================
        // ROAD MARKING
        // ============================================================

        private void CreateStreetMarking(
            Transform parent,
            string name,
            Vector3 start,
            Vector3 end)
        {
            GameObject go =
                new GameObject(name);

            go.transform.SetParent(
                parent,
                false);

            LineRenderer lr =
                go.AddComponent<LineRenderer>();

            lr.positionCount = 2;

            lr.SetPosition(
                0,
                start);

            lr.SetPosition(
                1,
                end);

            // White road line
            lr.startWidth =
                0.11f;

            lr.endWidth =
                0.11f;

            lr.useWorldSpace =
                true;

            lr.material =
                _matRoadMarking;

            lr.startColor =
                Color.white;

            lr.endColor =
                Color.white;

            lr.shadowCastingMode =
                UnityEngine.Rendering
                    .ShadowCastingMode.Off;

            lr.receiveShadows =
                false;
        }

        // ============================================================
        // STREET LAMPS
        // ============================================================

        private void CreateStreetLamps(
            Transform roadRoot,
            float offsetX,
            float offsetZ,
            float totalWidth,
            float totalDepth)
        {
            float lampSpacing = 18f;

            // --------------------------------------------------------
            // HORIZONTAL ROAD LAMPS
            // --------------------------------------------------------

            for (int z = 0;
                 z <= gridDepth;
                 z++)
            {
                float roadZ =
                    offsetZ +
                    z * blockSize;

                for (float x =
                         offsetX + 8f;
                     x < offsetX +
                         totalWidth;
                     x += lampSpacing)
                {
                    CreateStreetLamp(
                        roadRoot,
                        new Vector3(
                            x,
                            0f,
                            roadZ + 2.85f));
                }   
            }

            // --------------------------------------------------------
            // VERTICAL ROAD LAMPS
            // --------------------------------------------------------

            for (int x = 0;
                 x <= gridWidth;
                 x++)
            {
                float roadX =
                    offsetX +
                    x * blockSize;

                for (float z =
                         offsetZ + 8f;
                     z < offsetZ +
                         totalDepth;
                     z += lampSpacing)
                {
                    CreateStreetLamp(
                        roadRoot,
                        new Vector3(
                            roadX + 2.85f,
                            0f,
                            z));
                }
            }
        }

        // ============================================================
        // SINGLE STREET LAMP
        // ============================================================

        private void CreateStreetLamp(
            Transform parent,
            Vector3 position)
        {
            GameObject lampRoot =
                new GameObject(
                    "StreetLamp");

            lampRoot.transform.SetParent(
                parent,
                false);

            lampRoot.transform.position =
                position;

            // --------------------------------------------------------
            // POLE
            // --------------------------------------------------------

            GameObject pole =
                GameObject.CreatePrimitive(
                    PrimitiveType.Cylinder);

            pole.name =
                "LampPole";

            pole.transform.SetParent(
                lampRoot.transform,
                false);

            pole.transform.localPosition =
                new Vector3(
                    0f,
                    1.6f,
                    0f);

            pole.transform.localScale =
                new Vector3(
                    0.055f,
                    1.6f,
                    0.055f);

            Destroy(
                pole.GetComponent<Collider>());

            pole.GetComponent<MeshRenderer>()
                .material =
                _matLamp;

            // --------------------------------------------------------
            // ARM
            // --------------------------------------------------------

            GameObject arm =
                GameObject.CreatePrimitive(
                    PrimitiveType.Cube);

            arm.name =
                "LampArm";

            arm.transform.SetParent(
                lampRoot.transform,
                false);

            arm.transform.localPosition =
                new Vector3(
                    0.20f,
                    3.15f,
                    0f);

            arm.transform.localScale =
                new Vector3(
                    0.42f,
                    0.055f,
                    0.055f);

            Destroy(
                arm.GetComponent<Collider>());

            arm.GetComponent<MeshRenderer>()
                .material =
                _matLamp;

            // --------------------------------------------------------
            // LAMP HEAD
            // --------------------------------------------------------

            GameObject lampHead =
                GameObject.CreatePrimitive(
                    PrimitiveType.Sphere);

            lampHead.name =
                "LampHead";

            lampHead.transform.SetParent(
                lampRoot.transform,
                false);

            lampHead.transform.localPosition =
                new Vector3(
                    0.40f,
                    3.10f,
                    0f);

            lampHead.transform.localScale =
                Vector3.one *
                0.16f;

            Destroy(
                lampHead.GetComponent<Collider>());

            lampHead.GetComponent<MeshRenderer>()
                .material =
                _matLampGlow;
        }

        // ============================================================
        // STREET TREES
        // ============================================================

        private void CreateStreetTrees(
            Transform roadRoot,
            float offsetX,
            float offsetZ,
            float totalWidth,
            float totalDepth)
        {
            float treeSpacing = 8.5f;
            float sidewalkOffset = 3.2f; // Sidewalk distance beside homes, completely off road asphalt

            // Trees along horizontal streets (on sidewalks beside homes/blocks)
            for (int z = 0; z <= gridDepth; z++)
            {
                float roadZ = offsetZ + z * blockSize;
                for (float x = offsetX + 5f; x < offsetX + totalWidth - 4f; x += treeSpacing)
                {
                    // Skip tree placement if in or directly adjacent to a crossing intersection
                    float localX = Mathf.Abs((x - offsetX) % blockSize);
                    if (localX < 3.2f || localX > (blockSize - 3.2f))
                        continue;

                    // Strictly placed on sidewalk beside homes, never in middle of road
                    CreateTree(roadRoot, new Vector3(x, 0f, roadZ + sidewalkOffset));
                    CreateTree(roadRoot, new Vector3(x, 0f, roadZ - sidewalkOffset));
                }
            }

            // Trees along vertical streets (on sidewalks beside homes/blocks)
            for (int x = 0; x <= gridWidth; x++)
            {
                float roadX = offsetX + x * blockSize;
                for (float z = offsetZ + 5f; z < offsetZ + totalDepth - 4f; z += treeSpacing)
                {
                    // Skip tree placement if in or directly adjacent to a crossing intersection
                    float localZ = Mathf.Abs((z - offsetZ) % blockSize);
                    if (localZ < 3.2f || localZ > (blockSize - 3.2f))
                        continue;

                    // Strictly placed on sidewalk beside homes, never in middle of road
                    CreateTree(roadRoot, new Vector3(roadX + sidewalkOffset, 0f, z));
                    CreateTree(roadRoot, new Vector3(roadX - sidewalkOffset, 0f, z));
                }
            }
        }

        private void CreateTree(Transform parent, Vector3 position)
        {
            GameObject treeRoot = new GameObject("StreetTree");
            treeRoot.transform.SetParent(parent, false);
            treeRoot.transform.position = position;

            // Trunk
            GameObject trunk = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            trunk.name = "TreeTrunk";
            trunk.transform.SetParent(treeRoot.transform, false);
            trunk.transform.localPosition = new Vector3(0f, 0.65f, 0f);
            trunk.transform.localScale = new Vector3(0.16f, 0.65f, 0.16f);
            Destroy(trunk.GetComponent<Collider>());
            trunk.GetComponent<MeshRenderer>().material = _matTreeTrunk;

            // Foliage (Low-poly cone / sphere crown)
            GameObject foliage = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            foliage.name = "TreeFoliage";
            foliage.transform.SetParent(treeRoot.transform, false);
            foliage.transform.localPosition = new Vector3(0f, 1.8f, 0f);
            foliage.transform.localScale = new Vector3(1.1f, 1.4f, 1.1f);
            Destroy(foliage.GetComponent<Collider>());
            foliage.GetComponent<MeshRenderer>().material = _matTreeFoliage;
        }

#if UNITY_EDITOR

        // ============================================================
        // GIZMOS
        // ============================================================

        private void OnDrawGizmosSelected()
        {
            Gizmos.color =
                new Color(
                    0.35f,
                    0.70f,
                    0.90f);

            float totalWidth =
                gridWidth *
                blockSize;

            float totalDepth =
                gridDepth *
                blockSize;

            Gizmos.DrawWireCube(
                transform.position +
                Vector3.up * 0.5f,
                new Vector3(
                    totalWidth,
                    1f,
                    totalDepth));
        }

#endif
    }
}