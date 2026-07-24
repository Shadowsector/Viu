using UnityEngine;

namespace Viu.Runtime
{
    /// <summary>
    /// Круговой мир: дом в центре диска, при походе мир сдвигается противоположно Шане.
    /// Камера остаётся сбоку; при возвращении домой — flip на другой бок (yaw).
    /// По умолчанию выключен — только интерьер/фасад у таскбара (baseline).
    /// </summary>
    public class WorldOrbitController : MonoBehaviour
    {
        [Header("Refs")]
        public Transform worldRoot;
        public Transform homeAnchor;
        public Transform character;

        [Header("Expedition")]
        [Tooltip("false = дом у таскбара, мир не крутится (OVERLAY_BASELINE)")]
        public bool expeditionEnabled;

        [Tooltip("Метры от якоря — дальше начинается сдвиг мира")]
        public float expeditionStartRadius = 0.6f;

        public float worldRecenterSmooth = 10f;
        public float homewardFlipDot = -0.35f;
        public float yawFlipSmooth = 6f;

        ShanyaOverlayCamera _camera;
        Vector3 _anchorCenter;
        Vector3 _lastCharPos;
        bool _hasLast;
        float _targetYaw = 90f;
        float _currentYaw = 90f;
        bool _homeward;

        void Start()
        {
            _camera = Camera.main != null ? Camera.main.GetComponent<ShanyaOverlayCamera>() : null;
            RefreshAnchor();
            if (_camera != null)
            {
                _currentYaw = _camera.yawDegrees;
                _targetYaw = _currentYaw;
            }
        }

        void LateUpdate()
        {
            if (!expeditionEnabled || worldRoot == null || character == null)
                return;
            if (_camera == null && Camera.main != null)
                _camera = Camera.main.GetComponent<ShanyaOverlayCamera>();

            UpdateHomewardFlip();
            RecenterWorld();
            ApplyCameraYaw();

            _lastCharPos = character.position;
            _hasLast = true;
        }

        public void RefreshAnchor()
        {
            if (homeAnchor != null)
                _anchorCenter = homeAnchor.position;
            else if (worldRoot != null)
                _anchorCenter = worldRoot.position;
        }

        /// <summary>Новый дом стал центром круга (поход на 2 км и т.п.).</summary>
        public void SetHomeAnchor(Transform newHome, bool instantRecenter = false)
        {
            homeAnchor = newHome;
            RefreshAnchor();
            if (instantRecenter && worldRoot != null && character != null)
            {
                var delta = character.position - _anchorCenter;
                delta.y = 0f;
                worldRoot.position -= delta;
            }
            var cam = _camera != null ? _camera : Camera.main?.GetComponent<ShanyaOverlayCamera>();
            if (cam != null && newHome != null)
                cam.LockToHome(newHome.position.x);
        }

        void RecenterWorld()
        {
            var flat = character.position - _anchorCenter;
            flat.y = 0f;
            if (flat.magnitude < expeditionStartRadius)
                return;

            var step = -flat.normalized * (flat.magnitude - expeditionStartRadius);
            step.y = 0f;
            if (_camera != null)
                _camera.UnlockFollow();
            worldRoot.position += step * Mathf.Clamp01(worldRecenterSmooth * Time.deltaTime);
        }

        void UpdateHomewardFlip()
        {
            if (!_hasLast) return;
            var vel = character.position - _lastCharPos;
            vel.y = 0f;
            if (vel.sqrMagnitude < 1e-6f) return;

            var toHome = _anchorCenter - character.position;
            toHome.y = 0f;
            if (toHome.sqrMagnitude < 0.01f) return;

            bool homeward = Vector3.Dot(vel.normalized, toHome.normalized) > -homewardFlipDot;
            if (homeward && !_homeward)
                _targetYaw = NormalizeYaw(_targetYaw + 180f);
            _homeward = homeward;
        }

        void ApplyCameraYaw()
        {
            if (_camera == null) return;
            _currentYaw = Mathf.LerpAngle(_currentYaw, _targetYaw, yawFlipSmooth * Time.deltaTime);
            _camera.yawDegrees = _currentYaw;
        }

        static float NormalizeYaw(float y)
        {
            while (y > 180f) y -= 360f;
            while (y < -180f) y += 360f;
            return y;
        }
    }
}
