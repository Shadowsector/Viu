using UnityEngine;

namespace Viu.Runtime
{
    [System.Serializable]
    public struct OverlayCameraPresetData
    {
        public float orthographicSize;
        public float feetScreenFraction;
        public float feetFractionCloseBoost;
        public float distanceZ;
        public bool lockFollowX;
        public float pitchDegrees;
        public float yawDegrees;
    }

    /// <summary>
    /// Пресеты камеры: Facade / Corridor / Instance (+ activity для готовки/сна).
    /// </summary>
    public class OverlayCameraPresets : MonoBehaviour
    {
        public OverlayCameraPresetData facade = new OverlayCameraPresetData
        {
            orthographicSize = 5.5f,
            feetScreenFraction = 0.07f,
            feetFractionCloseBoost = 0.016f,
            distanceZ = 14f,
            lockFollowX = true,
            pitchDegrees = 28f,
            yawDegrees = 90f,
        };

        public OverlayCameraPresetData corridor = new OverlayCameraPresetData
        {
            orthographicSize = 5.5f,
            feetScreenFraction = 0.07f,
            feetFractionCloseBoost = 0.022f,
            distanceZ = 14f,
            lockFollowX = true,
            pitchDegrees = 32f,
            yawDegrees = 90f,
        };

        public OverlayCameraPresetData instance = new OverlayCameraPresetData
        {
            orthographicSize = 2.15f,
            feetScreenFraction = 0.10f,
            feetFractionCloseBoost = 0f,
            distanceZ = 9.5f,
            lockFollowX = true,
            pitchDegrees = 38f,
            yawDegrees = 90f,
        };

        public OverlayCameraPresetData activity = new OverlayCameraPresetData
        {
            orthographicSize = 1.85f,
            feetScreenFraction = 0.11f,
            feetFractionCloseBoost = 0f,
            distanceZ = 8.5f,
            lockFollowX = true,
            pitchDegrees = 42f,
            yawDegrees = 90f,
        };

        ShanyaOverlayCamera _follow;
        Camera _camera;

        void Awake()
        {
            _camera = GetComponent<Camera>();
            _follow = GetComponent<ShanyaOverlayCamera>();
        }

        public OverlayCameraPresetData Get(OverlayDisplayMode mode)
        {
            return mode == OverlayDisplayMode.Instance ? instance
                : mode == OverlayDisplayMode.Corridor ? corridor
                : facade;
        }

        public void Apply(OverlayDisplayMode mode)
        {
            ApplyPreset(Get(mode), mode);
        }

        public void ApplyPreset(OverlayCameraPresetData p, OverlayDisplayMode modeForDepth)
        {
            if (_camera == null) _camera = GetComponent<Camera>();
            if (_follow == null) _follow = GetComponent<ShanyaOverlayCamera>();
            if (_camera != null)
                _camera.orthographicSize = p.orthographicSize;
            if (_follow == null) return;

            _follow.feetScreenFraction = p.feetScreenFraction;
            _follow.feetFractionCloseBoost = p.feetFractionCloseBoost;
            _follow.distanceZ = p.distanceZ;
            _follow.lockFollowX = p.lockFollowX;
            _follow.pitchDegrees = p.pitchDegrees;
            _follow.yawDegrees = p.yawDegrees;
            if (modeForDepth != OverlayDisplayMode.Corridor)
                _follow.depthBlend = 0f;
        }
    }
}
