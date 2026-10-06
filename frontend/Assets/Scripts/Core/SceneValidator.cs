using UnityEngine;
using UnityEngine.SceneManagement;

namespace QuantumCity.Core
{
    /// <summary>
    /// Editor-time and runtime scene setup validator.
    /// Checks that all required scene objects are present and prints
    /// actionable error messages in the Console.
    ///
    /// Attach to any persistent GameObject; runs once on Awake.
    /// </summary>
    public class SceneValidator : MonoBehaviour
    {
        [Header("Validation")]
        [SerializeField] private bool runOnAwake = true;

        private void Awake()
        {
            if (runOnAwake) Validate();
        }

        public void Validate()
        {
            bool passed = true;

            // ── Camera ───────────────────────────────────────────────────────
            var mainCam = Camera.main;
            if (mainCam == null)
            {
                Debug.LogError("[SceneValidator] No MainCamera found. Add a Camera tagged 'MainCamera'.");
                passed = false;
            }
            else
            {
                Debug.Log($"[SceneValidator] ✓ MainCamera found: {mainCam.name}");
                if (mainCam.allowMSAA)
                    Debug.LogWarning("[SceneValidator] MSAA is enabled on Camera — consider disabling for low-end GPU performance.");
            }

            // ── Directional Light ─────────────────────────────────────────────
            var lights = FindObjectsByType<Light>(FindObjectsSortMode.None);
            bool hasDirectional = false;
            foreach (var l in lights)
                if (l.type == LightType.Directional) { hasDirectional = true; break; }

            if (!hasDirectional)
            {
                Debug.LogError("[SceneValidator] No Directional Light found in the scene.");
                passed = false;
            }
            else
            {
                Debug.Log("[SceneValidator] ✓ Directional Light found.");
            }

            // ── CityGridBuilder ───────────────────────────────────────────────
            var grid = FindFirstObjectByType<City.CityGridBuilder>();
            if (grid == null)
            {
                Debug.LogWarning("[SceneValidator] CityGridBuilder not found — city grid will not be generated.");
            }
            else
            {
                Debug.Log($"[SceneValidator] ✓ CityGridBuilder found: {grid.name}");
            }

            // ── Canvas / Dashboard ────────────────────────────────────────────
            var canvas = FindFirstObjectByType<Canvas>();
            if (canvas == null)
            {
                Debug.LogWarning("[SceneValidator] No Canvas found — dashboard UI will not be visible.");
            }
            else
            {
                Debug.Log($"[SceneValidator] ✓ Canvas found: {canvas.name}");
            }

            // ── GameManager ───────────────────────────────────────────────────
            if (GameManager.Instance == null)
            {
                Debug.LogWarning("[SceneValidator] GameManager singleton not yet initialised (validate earlier in execution order if needed).");
            }
            else
            {
                Debug.Log("[SceneValidator] ✓ GameManager singleton active.");
            }

            // ── Summary ───────────────────────────────────────────────────────
            if (passed)
                Debug.Log($"[SceneValidator] ✅ Scene '{SceneManager.GetActiveScene().name}' passed all critical checks.");
            else
                Debug.LogError($"[SceneValidator] ❌ Scene '{SceneManager.GetActiveScene().name}' has critical issues — see errors above.");
        }
    }
}
