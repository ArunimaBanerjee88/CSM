using UnityEngine;
using QuantumCity.City;
using QuantumCity.UI;

namespace QuantumCity.Core
{
    /// <summary>
    /// Central game manager — bootstraps the scene, enforces target frame rate,
    /// and acts as a service locator for future subsystems (API, traffic, etc.).
    /// </summary>
    public class GameManager : MonoBehaviour
    {
        public static GameManager Instance { get; private set; }

        [Header("Performance")]
        [Tooltip("Target frames per second. 30 is safe for low-end GPUs.")]
        [SerializeField] private int targetFrameRate = 30;

        [Tooltip("Enable VSync (overrides targetFrameRate when active).")]
        [SerializeField] private bool enableVSync = false;

        [Header("Scene References")]
        [SerializeField] private CityGridBuilder cityGridBuilder;
        [SerializeField] private DashboardController dashboardController;

        private void Awake()
        {
            // Singleton enforcement
            if (Instance != null && Instance != this)
            {
                Destroy(gameObject);
                return;
            }
            Instance = this;
            DontDestroyOnLoad(gameObject);

            ApplyPerformanceSettings();
        }

        private void ApplyPerformanceSettings()
        {
            QualitySettings.vSyncCount = enableVSync ? 1 : 0;
            Application.targetFrameRate = enableVSync ? -1 : targetFrameRate;

            // Low-end GPU optimisations
            QualitySettings.shadows = ShadowQuality.HardOnly;
            QualitySettings.shadowDistance = 80f;
            QualitySettings.antiAliasing = 0;           // disable MSAA
            QualitySettings.realtimeReflectionProbes = false;
            QualitySettings.pixelLightCount = 1;

            Debug.Log($"[GameManager] Performance settings applied — Target FPS: {targetFrameRate}, VSync: {enableVSync}");
        }

        private void Start()
        {
            Debug.Log("[GameManager] Quantum City scene initialised.");
        }

        // ── Future extension points ──────────────────────────────────────────
        // public APIManager    ApiManager    { get; private set; }
        // public TrafficSystem TrafficSystem { get; private set; }
    }
}
