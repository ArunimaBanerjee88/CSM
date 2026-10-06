using UnityEngine;
using UnityEngine.UI;
using TMPro;

namespace QuantumCity.UI
{
    /// <summary>
    /// Canvas-based dashboard UI controller (placeholder).
    /// Manages the HUD panels visible in the MainCity scene:
    ///   - Top status bar  (city name, simulation status)
    ///   - Bottom metrics bar (FPS counter, placeholder metric slots)
    ///   - Side panel toggle button
    ///
    /// All data fields are stubs ready for future API integration.
    /// </summary>
    public class DashboardController : MonoBehaviour
    {
        [Header("Status Bar")]
        [SerializeField] private TextMeshProUGUI cityNameText;
        [SerializeField] private TextMeshProUGUI simStatusText;

        [Header("Metrics Bar")]
        [SerializeField] private TextMeshProUGUI fpsText;
        [SerializeField] private TextMeshProUGUI trafficFlowText;
        [SerializeField] private TextMeshProUGUI energyText;
        [SerializeField] private TextMeshProUGUI populationText;

        [Header("Side Panel")]
        [SerializeField] private GameObject sidePanel;
        [SerializeField] private Button     sidePanelToggleButton;

        [Header("Settings")]
        [SerializeField] private string cityName = "Quantum City";
        [SerializeField] private int    fpsUpdateInterval = 30; // frames between FPS refresh

        private int   _frameCount;
        private float _fpsTimer;
        private float _currentFps;
        private bool  _sidePanelOpen = true;

        private void Awake()
        {
            if (sidePanelToggleButton != null)
                sidePanelToggleButton.onClick.AddListener(ToggleSidePanel);
        }

        private void Start()
        {
            SetCityName(cityName);
            SetSimStatus("IDLE");
            RefreshPlaceholderMetrics();
            
            // Wire up the API Manager dynamically
            gameObject.AddComponent<APIManager>();
        }

        private void Update()
        {
            UpdateFps();
        }

        // ── Public API (called by future subsystems) ─────────────────────────

        public void SetCityName(string name)
        {
            if (cityNameText != null) cityNameText.text = name;
        }

        public void SetSimStatus(string status)
        {
            if (simStatusText != null) simStatusText.text = $"Status: {status}";
        }

        public void SetTrafficFlow(float value)
        {
            if (trafficFlowText != null) trafficFlowText.text = $"Traffic: {value:F1}%";
        }

        public void SetEnergy(float value)
        {
            if (energyText != null) energyText.text = $"Energy: {value:F1} MW";
        }

        public void SetPopulation(int value)
        {
            if (populationText != null) populationText.text = $"Pop: {value:N0}";
        }

        // ── Private helpers ──────────────────────────────────────────────────

        private void UpdateFps()
        {
            _frameCount++;
            _fpsTimer += Time.unscaledDeltaTime;

            if (_frameCount >= fpsUpdateInterval)
            {
                _currentFps = _frameCount / _fpsTimer;
                if (fpsText != null)
                    fpsText.text = $"FPS: {_currentFps:F0}";

                _frameCount = 0;
                _fpsTimer   = 0f;
            }
        }

        private void RefreshPlaceholderMetrics()
        {
            SetTrafficFlow(0f);
            SetEnergy(0f);
            SetPopulation(0);
        }

        private void ToggleSidePanel()
        {
            _sidePanelOpen = !_sidePanelOpen;
            if (sidePanel != null) sidePanel.SetActive(_sidePanelOpen);
        }
    }
}
