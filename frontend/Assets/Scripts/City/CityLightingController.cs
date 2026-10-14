using UnityEngine;

namespace QuantumCity.City
{
    /// <summary>
    /// Controls the Quantum City day/night cycle.
    /// Supports:
    /// - Day mode
    /// - Night mode
    /// - Smooth transition
    /// - Sky/ambient lighting
    /// - Directional sun rotation
    /// - Optional moon-style night light
    /// 
    /// Can be controlled from another script using:
    /// lightingController.ToggleDayNight();
    /// lightingController.SetDay();
    /// lightingController.SetNight();
    /// </summary>
    public class CityLightingController : MonoBehaviour
    {
        [Header("Main Directional Light")]
        [SerializeField] private Light directionalLight;

        [Header("Optional Night Light")]
        [SerializeField] private Light nightLight;

        [Header("Day Settings")]
        [SerializeField] private Color dayLightColor =
            new Color(1.0f, 0.98f, 0.92f);

        [SerializeField] private float dayLightIntensity = 1.35f;

        [SerializeField] private Color dayAmbientColor =
            new Color(0.72f, 0.84f, 0.96f);

        [SerializeField] private Color daySkyColor =
            new Color(0.42f, 0.68f, 0.95f); // Rich bright daytime sky as in Image 2

        [Header("Night Settings")]
        [SerializeField] private Color nightLightColor =
            new Color(0.55f, 0.68f, 0.90f);

        [SerializeField] private float nightLightIntensity = 0.25f;

        [SerializeField] private Color nightAmbientColor =
            new Color(0.12f, 0.16f, 0.22f);

        [SerializeField] private Color nightSkyColor =
            new Color(0.025f, 0.05f, 0.10f);

        [Header("Night Light")]
        [SerializeField] private Color moonLightColor =
            new Color(0.55f, 0.70f, 1.0f);

        [SerializeField] private float moonIntensity = 0.18f;

        [Header("Transition")]
        [SerializeField] private float transitionSpeed = 2.0f;

        [Header("Sun Rotation")]
        [SerializeField] private Vector3 dayRotation =
            new Vector3(50f, -30f, 0f);

        [SerializeField] private Vector3 nightRotation =
            new Vector3(145f, -30f, 0f);

        private bool isNight = false;
        private Camera cityCamera;
        private Color currentLightColor;
        private Color currentAmbientColor;
        private Color currentSkyColor;

        private float currentLightIntensity;
        private float currentMoonIntensity;

        private void Awake()
        {
            FindLights();
            cityCamera = Camera.main;
            RenderSettings.fog = true;

            if (directionalLight != null)
            {
                currentLightColor = directionalLight.color;
                currentLightIntensity = directionalLight.intensity;
            }

            currentAmbientColor = RenderSettings.ambientLight;

            if (RenderSettings.fog)
                currentSkyColor = RenderSettings.fogColor;

            ApplyDayImmediate();
        }

        private void Update()
        {
            SmoothLighting();
        }

        // ============================================================
        // FIND LIGHTS
        // ============================================================

        private void FindLights()
        {
            if (directionalLight == null)
            {
                GameObject lightObject = GameObject.Find("DirectionalLight");

                if (lightObject != null)
                    directionalLight = lightObject.GetComponent<Light>();
            }

            if (directionalLight == null)
            {
                Light[] lights = FindObjectsByType<Light>(
                    FindObjectsSortMode.None);

                foreach (Light light in lights)
                {
                    if (light.type == LightType.Directional)
                    {
                        directionalLight = light;
                        break;
                    }
                }
            }

            if (nightLight == null)
            {
                GameObject nightObject = GameObject.Find("NightLight");

                if (nightObject != null)
                    nightLight = nightObject.GetComponent<Light>();
            }

            // Create a subtle night light if one doesn't exist.
            if (nightLight == null)
            {
                GameObject moonObject =
                    new GameObject("NightLight");

                moonObject.transform.SetParent(
                    transform,
                    false);

                nightLight =
                    moonObject.AddComponent<Light>();

                nightLight.type =
                    LightType.Directional;

                nightLight.color =
                    moonLightColor;

                nightLight.intensity = 0f;

                nightLight.shadows =
                    LightShadows.None;

                moonObject.transform.rotation =
                    Quaternion.Euler(
                        nightRotation);
            }
        }

        // ============================================================
        // DAY / NIGHT API
        // ============================================================

        public void ToggleDayNight()
        {
            if (isNight)
                SetDay();
            else
                SetNight();
        }

        public void SetDay()
        {
            isNight = false;

            if (directionalLight != null)
            {
                directionalLight.transform.rotation =
                    Quaternion.Euler(dayRotation);
            }

            Debug.Log("[Lighting] DAY MODE");
        }

        public void SetNight()
        {
            isNight = true;

            if (directionalLight != null)
            {
                directionalLight.transform.rotation =
                    Quaternion.Euler(nightRotation);
            }

            Debug.Log("[Lighting] NIGHT MODE");
        }

        public bool IsNight()
        {
            return isNight;
        }

        // ============================================================
        // IMMEDIATE APPLICATION
        // ============================================================

        private void ApplyDayImmediate()
        {
            isNight = false;

            if (directionalLight != null)
            {
                directionalLight.color =
                    dayLightColor;

                directionalLight.intensity =
                    dayLightIntensity;

                directionalLight.transform.rotation =
                    Quaternion.Euler(dayRotation);
            }

            if (nightLight != null)
                nightLight.intensity = 0f;

            RenderSettings.ambientLight =
                dayAmbientColor;

            RenderSettings.fogColor = daySkyColor;
            RenderSettings.fogDensity = 0.002f;

            if (cityCamera != null)
            {
                cityCamera.clearFlags = CameraClearFlags.SolidColor;
                cityCamera.backgroundColor = daySkyColor;
            }
        }

        // ============================================================
        // SMOOTH TRANSITION
        // ============================================================

        private void SmoothLighting()
        {
            if (directionalLight == null)
                return;

            Color targetLightColor =
                isNight
                    ? nightLightColor
                    : dayLightColor;

            float targetIntensity =
                isNight
                    ? nightLightIntensity
                    : dayLightIntensity;

            Color targetAmbient =
                isNight
                    ? nightAmbientColor
                    : dayAmbientColor;

            Color targetSky =
                isNight
                    ? nightSkyColor
                    : daySkyColor;

            float targetMoon =
                isNight
                    ? moonIntensity
                    : 0f;

            float speed =
                transitionSpeed * Time.deltaTime;

            directionalLight.color =
                Color.Lerp(
                    directionalLight.color,
                    targetLightColor,
                    speed);

            directionalLight.intensity =
                Mathf.Lerp(
                    directionalLight.intensity,
                    targetIntensity,
                    speed);

            RenderSettings.ambientLight =
                Color.Lerp(
                    RenderSettings.ambientLight,
                    targetAmbient,
                    speed);

            RenderSettings.fogColor =
                Color.Lerp(
                    RenderSettings.fogColor,
                    targetSky,
                    speed);

            if (cityCamera != null)
            {
                cityCamera.backgroundColor = Color.Lerp(
                    cityCamera.backgroundColor,
                    targetSky,
                    speed);
            }

            if (nightLight != null)
            {
                nightLight.color =
                    moonLightColor;

                nightLight.intensity =
                    Mathf.Lerp(
                        nightLight.intensity,
                        targetMoon,
                        speed);
            }

            // Keep fog subtle during both modes.
            float targetFog =
                isNight
                    ? 0.0035f
                    : 0.002f;

            RenderSettings.fogDensity =
                Mathf.Lerp(
                    RenderSettings.fogDensity,
                    targetFog,
                    speed);
        }

        // ============================================================
        // PUBLIC STATUS
        // ============================================================

        public string GetLightingStatus()
        {
            return isNight
                ? "NIGHT"
                : "DAY";
        }
    }
}