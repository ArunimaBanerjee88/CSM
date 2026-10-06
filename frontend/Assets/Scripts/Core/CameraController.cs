using UnityEngine;

namespace QuantumCity.Core
{
    /// <summary>
    /// Lightweight top-down / orbit camera controller.
    /// - Middle-mouse or right-mouse drag → orbit
    /// - WASD / arrow keys → pan
    /// - Scroll wheel → zoom
    /// Designed for minimal GC pressure; no physics raycasts per frame.
    /// </summary>
    [RequireComponent(typeof(Camera))]
    public class CameraController : MonoBehaviour
    {
        [Header("Orbit")]
        [SerializeField] private float orbitSpeed = 3f;
        [SerializeField] private float minPitch = 10f;
        [SerializeField] private float maxPitch = 80f;

        [Header("Pan")]
        [SerializeField] private float panSpeed = 20f;

        [Header("Zoom")]
        [SerializeField] private float zoomSpeed = 10f;
        [SerializeField] private float minZoom = 5f;
        [SerializeField] private float maxZoom = 120f;

        [Header("Starting Pose")]
        [SerializeField] private Vector3 focusPoint = Vector3.zero;
        [SerializeField] private float startingDistance = 60f;
        [SerializeField] private float startingPitch = 45f;
        [SerializeField] private float startingYaw = -30f;

        private float _currentDistance;
        private float _currentPitch;
        private float _currentYaw;

        private void Start()
        {
            _currentDistance = startingDistance;
            _currentPitch    = startingPitch;
            _currentYaw      = startingYaw;
            ApplyTransform();
        }

        private void LateUpdate()
        {
            HandleOrbit();
            HandlePan();
            HandleZoom();
            ApplyTransform();
        }

        private void HandleOrbit()
        {
            if (Input.GetMouseButton(1) || Input.GetMouseButton(2))
            {
                _currentYaw   += Input.GetAxis("Mouse X") * orbitSpeed;
                _currentPitch -= Input.GetAxis("Mouse Y") * orbitSpeed;
                _currentPitch  = Mathf.Clamp(_currentPitch, minPitch, maxPitch);
            }
        }

        private void HandlePan()
        {
            float h = Input.GetAxis("Horizontal");
            float v = Input.GetAxis("Vertical");
            if (Mathf.Abs(h) < 0.01f && Mathf.Abs(v) < 0.01f) return;

            Vector3 right   = transform.right;
            Vector3 forward = Vector3.Cross(right, Vector3.up);
            focusPoint += (right * h + forward * v) * (panSpeed * Time.deltaTime);
        }

        private void HandleZoom()
        {
            float scroll = Input.GetAxis("Mouse ScrollWheel");
            if (Mathf.Abs(scroll) < 0.001f) return;
            _currentDistance -= scroll * zoomSpeed;
            _currentDistance  = Mathf.Clamp(_currentDistance, minZoom, maxZoom);
        }

        private void ApplyTransform()
        {
            Quaternion rotation = Quaternion.Euler(_currentPitch, _currentYaw, 0f);
            transform.position  = focusPoint + rotation * new Vector3(0f, 0f, -_currentDistance);
            transform.LookAt(focusPoint);
        }
    }
}
