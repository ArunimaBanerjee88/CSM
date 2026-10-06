using UnityEngine;
using System.Collections.Generic;

namespace QuantumCity.City
{
    /// <summary>
    /// Procedurally generates a polished futuristic low-poly digital-twin city.
    /// Creates varied building blocks, roads, intersections, and subtle emissive windows.
    /// Built using primitives to keep polygons low, and heavily utilizes GPU instancing.
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
        [SerializeField] private float minHeight = 1f;
        [SerializeField] private float maxHeight = 12f;

        [Header("Visuals (Materials are dynamically created if null)")]
        [SerializeField] private Material buildingMaterial;
        [SerializeField] private Material roadMaterial;
        [SerializeField] private Material windowMaterial;

        private GameObject _cityRoot;
        private Material _matBuilding;
        private Material _matRoad;
        private Material _matWindow;
        
        // Use lists to combine meshes later if needed, but primitive + instancing is fine for now
        private void Start()
        {
            InitializeMaterials();
            BuildCity();
        }

        private void InitializeMaterials()
        {
            // Fallbacks for materials if not assigned via Inspector to avoid breaking scene references
            _matBuilding = buildingMaterial != null ? buildingMaterial : CreateBuildingMaterial();
            _matRoad = roadMaterial != null ? roadMaterial : CreateRoadMaterial();
            _matWindow = windowMaterial != null ? windowMaterial : CreateWindowMaterial();
        }

        private Material CreateBuildingMaterial()
        {
            Shader urpLit = Shader.Find("Universal Render Pipeline/Lit");
            Material mat = new Material(urpLit != null ? urpLit : Shader.Find("Hidden/Universal Render Pipeline/FallbackError"));
            mat.SetColor("_BaseColor", new Color(0.05f, 0.15f, 0.3f, 1f));
            mat.SetFloat("_Smoothness", 0.2f);
            mat.SetFloat("_Metallic", 0.4f);
            mat.EnableKeyword("_EMISSION");
            mat.SetColor("_EmissionColor", new Color(0.0f, 0.02f, 0.05f, 1f));
            mat.enableInstancing = true;
            return mat;
        }

        private Material CreateRoadMaterial()
        {
            Shader urpLit = Shader.Find("Universal Render Pipeline/Lit");
            Material mat = new Material(urpLit != null ? urpLit : Shader.Find("Hidden/Universal Render Pipeline/FallbackError"));
            mat.SetColor("_BaseColor", new Color(0.02f, 0.02f, 0.03f, 1f));
            mat.SetFloat("_Smoothness", 0.1f);
            mat.SetFloat("_Metallic", 0.1f);
            mat.enableInstancing = true;
            return mat;
        }

        private Material CreateWindowMaterial()
        {
            Shader urpUnlit = Shader.Find("Universal Render Pipeline/Unlit");
            Material mat = new Material(urpUnlit != null ? urpUnlit : Shader.Find("Hidden/Universal Render Pipeline/FallbackError"));
            mat.SetColor("_BaseColor", new Color(0.1f, 0.8f, 1.0f, 1f));
            // Simulate HDR emission
            mat.SetColor("_EmissionColor", new Color(0.2f, 1.6f, 2.0f, 1f)); 
            mat.enableInstancing = true;
            return mat;
        }

        private void BuildCity()
        {
            _cityRoot = new GameObject("ProceduralCityEnvironment");
            _cityRoot.transform.SetParent(transform, false);

            float totalWidth = gridWidth * blockSize;
            float totalDepth = gridDepth * blockSize;
            float offsetX = -totalWidth * 0.5f;
            float offsetZ = -totalDepth * 0.5f;

            for (int x = 0; x < gridWidth; x++)
            {
                for (int z = 0; z < gridDepth; z++)
                {
                    float wx = offsetX + x * blockSize + (blockSize * 0.5f);
                    float wz = offsetZ + z * blockSize + (blockSize * 0.5f);
                    Vector3 blockCenter = new Vector3(wx, 0f, wz);
                    
                    // The actual space for buildings (subtract road width)
                    float buildableSize = blockSize - roadWidth;
                    
                    GenerateBlock(blockCenter, buildableSize, x, z);
                }
            }

            GenerateRoadNetwork(offsetX, offsetZ, totalWidth, totalDepth);
            Debug.Log($"[CityGridBuilder] Visual City generated: {gridWidth}x{gridDepth} blocks.");
        }

        private void GenerateBlock(Vector3 center, float size, int gridX, int gridZ)
        {
            GameObject blockParent = new GameObject($"Block_{gridX}_{gridZ}");
            blockParent.transform.SetParent(_cityRoot.transform, false);
            blockParent.transform.position = center;

            // Generate a random number of buildings in this block
            int numBuildings = Random.Range(minBuildingsPerBlock, maxBuildingsPerBlock + 1);
            
            // Subdivide the block into a grid for building placement to avoid overlap
            int subGridSize = 2; // 2x2 grid max 4 buildings, or 3x3 max 9
            if (numBuildings > 4) subGridSize = 3;
            
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

            // Shuffle cells
            for (int i = 0; i < availableCells.Count; i++)
            {
                Vector2 temp = availableCells[i];
                int randomIndex = Random.Range(i, availableCells.Count);
                availableCells[i] = availableCells[randomIndex];
                availableCells[randomIndex] = temp;
            }

            for (int i = 0; i < numBuildings && i < availableCells.Count; i++)
            {
                int cx = (int)availableCells[i].x;
                int cz = (int)availableCells[i].y;
                
                // Calculate local center of this cell
                float localX = -halfSize + (cx * cellSize) + (cellSize * 0.5f);
                float localZ = -halfSize + (cz * cellSize) + (cellSize * 0.5f);
                
                // Building dimensions (add a little padding so they don't touch exactly)
                float bWidth = cellSize * Random.Range(0.6f, 0.95f);
                float bDepth = cellSize * Random.Range(0.6f, 0.95f);
                
                // Height based on distance to center of city to create a skyline
                float distToCenter = Vector2.Distance(new Vector2(center.x, center.z), Vector2.zero);
                float maxDist = (gridWidth * blockSize) * 0.5f;
                float heightMultiplier = 1f - Mathf.Clamp01(distToCenter / maxDist);
                // Base height + center bias
                float bHeight = Random.Range(minHeight, minHeight + (maxHeight - minHeight) * 0.3f) 
                              + (Random.Range(0f, maxHeight * 0.7f) * heightMultiplier);

                Vector3 bLocalPos = new Vector3(localX, bHeight * 0.5f, localZ);
                Vector3 bScale = new Vector3(bWidth, bHeight, bDepth);

                CreateBuilding(blockParent.transform, bLocalPos, bScale, i);
            }
        }

        private void CreateBuilding(Transform parent, Vector3 localPos, Vector3 scale, int index)
        {
            GameObject building = GameObject.CreatePrimitive(PrimitiveType.Cube);
            building.name = $"Bldg_{index}";
            building.transform.SetParent(parent, false);
            building.transform.localPosition = localPos;
            building.transform.localScale = scale;

            Destroy(building.GetComponent<Collider>()); // No physics

            MeshRenderer mr = building.GetComponent<MeshRenderer>();
            mr.material = _matBuilding;
            mr.receiveShadows = false; 
            mr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.On; // Allow buildings to cast shadows

            // Add windows 30% of the time for variety
            if (Random.value > 0.7f)
            {
                AddEmissiveWindows(building.transform, scale);
            }
        }

        private void AddEmissiveWindows(Transform building, Vector3 bScale)
        {
            // Simple procedural windows: add thin cubes slightly larger than the building on specific axes
            // Horizontal window bands
            int numBands = Random.Range(1, 4);
            for (int i = 0; i < numBands; i++)
            {
                GameObject band = GameObject.CreatePrimitive(PrimitiveType.Cube);
                band.name = "WindowBand";
                band.transform.SetParent(building, false);
                Destroy(band.GetComponent<Collider>());
                
                // Random height for the band relative to building
                float yPos = Random.Range(-0.4f, 0.4f);
                band.transform.localPosition = new Vector3(0f, yPos, 0f);
                
                // Make it slightly wider/deeper but very thin vertically
                float thickness = Random.Range(0.02f, 0.08f) / bScale.y; // normalize to parent scale
                band.transform.localScale = new Vector3(1.02f, thickness, 1.02f);

                MeshRenderer mr = band.GetComponent<MeshRenderer>();
                mr.material = _matWindow;
                mr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
                mr.receiveShadows = false;
            }
        }

        private void GenerateRoadNetwork(float offsetX, float offsetZ, float totalWidth, float totalDepth)
        {
            GameObject roadRoot = new GameObject("RoadNetwork");
            roadRoot.transform.SetParent(_cityRoot.transform, false);
            
            // Draw a single large base road plane covering the whole city under the blocks
            // This is heavily optimized: 1 draw call for all roads
            GameObject mainRoad = GameObject.CreatePrimitive(PrimitiveType.Plane);
            mainRoad.name = "MainRoadBase";
            mainRoad.transform.SetParent(roadRoot.transform, false);
            
            // Unity planes are 10x10 by default, so scale accordingly
            mainRoad.transform.localScale = new Vector3(totalWidth / 10f, 1f, totalDepth / 10f);
            mainRoad.transform.position = new Vector3(0f, 0.01f, 0f); // Slightly above ground
            Destroy(mainRoad.GetComponent<Collider>());
            
            MeshRenderer mr = mainRoad.GetComponent<MeshRenderer>();
            mr.material = _matRoad;
            mr.receiveShadows = true;
            mr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;

            // Generate procedural street markings using LineRenderers (repurposing existing logic)
            // Vertical markings
            for (int x = 0; x <= gridWidth; x++)
            {
                float wx = offsetX + x * blockSize;
                CreateStreetMarking(roadRoot.transform, $"MarkingV_{x}", new Vector3(wx, 0.02f, offsetZ), new Vector3(wx, 0.02f, offsetZ + totalDepth));
            }
            // Horizontal markings
            for (int z = 0; z <= gridDepth; z++)
            {
                float wz = offsetZ + z * blockSize;
                CreateStreetMarking(roadRoot.transform, $"MarkingH_{z}", new Vector3(offsetX, 0.02f, wz), new Vector3(offsetX + totalWidth, 0.02f, wz));
            }
        }

        private void CreateStreetMarking(Transform parent, string name, Vector3 start, Vector3 end)
        {
            var go = new GameObject(name);
            go.transform.SetParent(parent, false);

            var lr = go.AddComponent<LineRenderer>();
            lr.positionCount = 2;
            lr.SetPosition(0, start);
            lr.SetPosition(1, end);
            lr.startWidth = 0.2f;
            lr.endWidth = 0.2f;
            lr.useWorldSpace = true;
            lr.material = _matWindow; // Use the emissive window material for bright cyber-markings
            
            // Dash effect settings (available in modern Unity line renderers if texture mode is set, but we'll keep it solid for low-poly)
            lr.startColor = new Color(0.2f, 0.8f, 1f, 0.3f);
            lr.endColor = new Color(0.2f, 0.8f, 1f, 0.3f);
            lr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            lr.receiveShadows = false;
        }

#if UNITY_EDITOR
        private void OnDrawGizmosSelected()
        {
            Gizmos.color = Color.cyan;
            float totalWidth = gridWidth * blockSize;
            float totalDepth = gridDepth * blockSize;
            Gizmos.DrawWireCube(
                transform.position + Vector3.up * 0.5f,
                new Vector3(totalWidth, 1f, totalDepth));
        }
#endif
    }
}
