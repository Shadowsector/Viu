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
    }

    /// <summary>
    /// Три режима камеры: Facade / Corridor / Instance. Значения задаются в Inspector сцены.
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
        };

        public OverlayCameraPresetData corridor = new OverlayCameraPresetData
        {
            orthographicSize = 5.5f,
            feetScreenFraction = 0.07f,
            feetFractionCloseBoost = 0.022f,
            distanceZ = 14f,
            lockFollowX = true,
        };

        public OverlayCameraPresetData instance = new OverlayCameraPresetData
        {
            // Чуть крупнее / ниже — интерьер сарая читается как «комната»
            orthographicSize = 2.15f,
            feetScreenFraction = 0.10f,
            feetFractionCloseBoost = 0f,
            distanceZ = 9.5f,
            lockFollowX = true,
        };

        ShanyaOverlayCamera _follow;
        Camera _camera;

        void Awake()
        {
            _camera = GetComponent<Camera>();
            _follow = GetComponent<ShanyaOverlayCamera>();
        }

        public void Apply(OverlayDisplayMode mode)
        {
            if (_camera == null) _camera = GetComponent<Camera>();
            if (_follow == null) _follow = GetComponent<ShanyaOverlayCamera>();
            var p = mode == OverlayDisplayMode.Instance ? instance
                : mode == OverlayDisplayMode.Corridor ? corridor
                : facade;

            if (_camera != null)
                _camera.orthographicSize = p.orthographicSize;
            if (_follow == null) return;

            _follow.feetScreenFraction = p.feetScreenFraction;
            _follow.feetFractionCloseBoost = p.feetFractionCloseBoost;
            _follow.distanceZ = p.distanceZ;
            _follow.lockFollowX = p.lockFollowX;
            _follow.depthBlend = mode == OverlayDisplayMode.Corridor ? _follow.depthBlend : 0f;
        }
    }
}
