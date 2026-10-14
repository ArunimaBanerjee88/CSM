using UnityEngine;
using UnityEngine.UI;
using TMPro;

namespace QuantumCity.Core
{
    /// <summary>
    /// Controls Unity Display 1-8.
    ///
    /// IMPORTANT:
    /// Unity can only physically activate displays that are actually
    /// connected to the computer/monitor configuration.
    ///
    /// For your capstone this also provides:
    /// - Display selection
    /// - Camera assignment
    /// - Display status
    /// - Keyboard shortcuts
    /// </summary>
    public class MultiDisplayManager : MonoBehaviour
    {
        [Header("Cameras")]
        [SerializeField] private Camera[] displayCameras =
            new Camera[8];

        [Header("Display Settings")]
        [SerializeField] private bool activateDisplaysOnStart = true;

        [SerializeField] private bool showDebugLogs = true;

        [Header("Optional UI")]
        [SerializeField] private TextMeshProUGUI displayStatusText;

        [Header("Current Display")]
        [SerializeField] private int currentDisplay = 1;

        private const int MAX_DISPLAYS = 8;

        private void Awake()
        {
            currentDisplay =
                Mathf.Clamp(
                    currentDisplay,
                    1,
                    MAX_DISPLAYS);
        }

        private void Start()
        {
            ActivateAvailableDisplays();

            ConfigureCameras();

            UpdateDisplayStatus();
        }

        private void Update()
        {
            HandleKeyboardShortcuts();
        }

        // ============================================================
        // DISPLAY ACTIVATION
        // ============================================================

        private void ActivateAvailableDisplays()
        {
            if (!activateDisplaysOnStart)
                return;

            int displayCount =
                Display.displays.Length;

            if (showDebugLogs)
            {
                Debug.Log(
                    "[MultiDisplay] Physical displays detected: "
                    + displayCount);
            }

            for (int i = 0; i < displayCount; i++)
            {
                if (i >= MAX_DISPLAYS)
                    break;

                try
                {
                    Display.displays[i].Activate();

                    if (showDebugLogs)
                    {
                        Debug.Log(
                            "[MultiDisplay] Activated Display "
                            + (i + 1));
                    }
                }
                catch (System.Exception e)
                {
                    Debug.LogWarning(
                        "[MultiDisplay] Could not activate Display "
                        + (i + 1)
                        + ": "
                        + e.Message);
                }
            }
        }

        // ============================================================
        // CAMERA CONFIGURATION
        // ============================================================

        private void ConfigureCameras()
        {
            if (displayCameras == null)
                return;

            for (int i = 0;
                i < displayCameras.Length && i < MAX_DISPLAYS;
                i++)
            {
                if (displayCameras[i] == null)
                    continue;

                displayCameras[i].targetDisplay = i;

                if (showDebugLogs)
                {
                    Debug.Log(
                        "[MultiDisplay] Camera "
                        + displayCameras[i].name
                        + " -> Display "
                        + (i + 1));
                }
            }
        }

        // ============================================================
        // KEYBOARD SHORTCUTS
        // ============================================================

        private void HandleKeyboardShortcuts()
        {
            if (Input.GetKeyDown(KeyCode.Alpha1))
                SelectDisplay(1);

            if (Input.GetKeyDown(KeyCode.Alpha2))
                SelectDisplay(2);

            if (Input.GetKeyDown(KeyCode.Alpha3))
                SelectDisplay(3);

            if (Input.GetKeyDown(KeyCode.Alpha4))
                SelectDisplay(4);

            if (Input.GetKeyDown(KeyCode.Alpha5))
                SelectDisplay(5);

            if (Input.GetKeyDown(KeyCode.Alpha6))
                SelectDisplay(6);

            if (Input.GetKeyDown(KeyCode.Alpha7))
                SelectDisplay(7);

            if (Input.GetKeyDown(KeyCode.Alpha8))
                SelectDisplay(8);
        }

        // ============================================================
        // SELECT DISPLAY
        // ============================================================

        public void SelectDisplay(int displayNumber)
        {
            if (displayNumber < 1 ||
                displayNumber > MAX_DISPLAYS)
            {
                Debug.LogWarning(
                    "[MultiDisplay] Invalid display: "
                    + displayNumber);

                return;
            }

            int index =
                displayNumber - 1;

            currentDisplay =
                displayNumber;

            // If physical display doesn't exist,
            // still update the UI so the system knows
            // what the user requested.
            if (index >= Display.displays.Length)
            {
                Debug.LogWarning(
                    "[MultiDisplay] Display "
                    + displayNumber
                    + " is not physically connected.");

                UpdateDisplayStatus();

                return;
            }

            Display.displays[index].Activate();

            // Disable cameras from other displays.
            for (int i = 0;
                i < displayCameras.Length;
                i++)
            {
                if (displayCameras[i] == null)
                    continue;

                displayCameras[i].enabled =
                    i == index;
            }

            if (showDebugLogs)
            {
                Debug.Log(
                    "[MultiDisplay] Viewing Display "
                    + displayNumber);
            }

            UpdateDisplayStatus();
        }

        // ============================================================
        // SHOW ALL DISPLAY CAMERAS
        // ============================================================

        public void EnableAllDisplayCameras()
        {
            for (int i = 0;
                i < displayCameras.Length;
                i++)
            {
                if (displayCameras[i] == null)
                    continue;

                if (i < Display.displays.Length)
                {
                    displayCameras[i].targetDisplay =
                        i;

                    displayCameras[i].enabled =
                        true;
                }
            }

            UpdateDisplayStatus();
        }

        // ============================================================
        // DISABLE ALL
        // ============================================================

        public void DisableAllDisplayCameras()
        {
            for (int i = 0;
                i < displayCameras.Length;
                i++)
            {
                if (displayCameras[i] == null)
                    continue;

                displayCameras[i].enabled = false;
            }

            UpdateDisplayStatus();
        }

        // ============================================================
        // DISPLAY STATUS
        // ============================================================

        private void UpdateDisplayStatus()
        {
            if (displayStatusText == null)
                return;

            int physicalDisplays =
                Display.displays.Length;

            displayStatusText.text =
                "DISPLAY "
                + currentDisplay
                + " / 8\n"
                + "PHYSICAL DISPLAYS: "
                + physicalDisplays;
        }

        // ============================================================
        // PUBLIC INFORMATION
        // ============================================================

        public int GetCurrentDisplay()
        {
            return currentDisplay;
        }

        public int GetConnectedDisplayCount()
        {
            return Display.displays.Length;
        }

        public bool IsDisplayAvailable(
            int displayNumber)
        {
            if (displayNumber < 1 ||
                displayNumber > MAX_DISPLAYS)
                return false;

            return displayNumber <=
                   Display.displays.Length;
        }

        // ============================================================
        // DISPLAY BUTTON HELPERS
        // ============================================================

        public void Display1()
        {
            SelectDisplay(1);
        }

        public void Display2()
        {
            SelectDisplay(2);
        }

        public void Display3()
        {
            SelectDisplay(3);
        }

        public void Display4()
        {
            SelectDisplay(4);
        }

        public void Display5()
        {
            SelectDisplay(5);
        }

        public void Display6()
        {
            SelectDisplay(6);
        }

        public void Display7()
        {
            SelectDisplay(7);
        }

        public void Display8()
        {
            SelectDisplay(8);
        }
    }
}