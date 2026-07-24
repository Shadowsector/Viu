using UnityEngine;

namespace Viu.Runtime
{
    /// <summary>
    /// Плавный переход между пресетами камеры (Facade / Corridor / Instance / Activity).
  /// </summary>
    public class OverlayCameraBlend : MonoBehaviour
    {
        public float blendDuration = 0.45f;

        OverlayCameraPresets _presets;
        ShanyaOverlayCamera _follow;
        Camera _camera;

        OverlayDisplayMode _fromMode = OverlayDisplayMode.Facade;
        OverlayDisplayMode _toMode = OverlayDisplayMode.Facade;
        float _t = 1f;
        OverlayCameraPresetData _from;
        OverlayCameraPresetData _to;

        void Awake()
        {
            _camera = GetComponent<Camera>();
            _follow = GetComponent<ShanyaOverlayCamera>();
            _presets = GetComponent<OverlayCameraPresets>();
        }

        void Update()
        {
            if (_t >= 1f || _follow == null) return;
            _t += Time.deltaTime / Mathf.Max(0.05f, blendDuration);
            float u = Mathf.SmoothStep(0f, 1f, Mathf.Clamp01(_t));
            ApplyLerp(_from, _to, u);
        }

        public void BlendTo(OverlayDisplayMode mode, bool instant = false)
        {
            if (_presets == null) _presets = GetComponent<OverlayCameraPresets>();
            if (_follow == null) _follow = GetComponent<ShanyaOverlayCamera>();
            if (_presets == null || _follow == null) return;

            _from = CaptureCurrent();
            _to = _presets.Get(mode);
            _fromMode = _toMode;
            _toMode = mode;
            if (instant || blendDuration <= 0.01f)
            {
                _t = 1f;
                _presets.Apply(mode);
                return;
            }
            _t = 0f;
        }

        public void BlendToActivity(bool instant = false)
        {
            if (_presets == null) _presets = GetComponent<OverlayCameraPresets>();
            if (_follow == null) _follow = GetComponent<ShanyaOverlayCamera>();
            if (_presets == null || _follow == null) return;

            _from = CaptureCurrent();
            _to = _presets.activity;
            if (instant || blendDuration <= 0.01f)
            {
                _t = 1f;
                _presets.ApplyPreset(_to, OverlayDisplayMode.Instance);
                return;
            }
            _t = 0f;
        }

        OverlayCameraPresetData CaptureCurrent()
        {
            var p = new OverlayCameraPresetData();
            if (_camera != null) p.orthographicSize = _camera.orthographicSize;
            if (_follow != null)
            {
                p.feetScreenFraction = _follow.feetScreenFraction;
                p.feetFractionCloseBoost = _follow.feetFractionCloseBoost;
                p.distanceZ = _follow.distanceZ;
                p.lockFollowX = _follow.lockFollowX;
                p.pitchDegrees = _follow.pitchDegrees;
                p.yawDegrees = _follow.yawDegrees;
            }
            return p;
        }

        void ApplyLerp(OverlayCameraPresetData a, OverlayCameraPresetData b, float u)
        {
            if (_camera != null)
                _camera.orthographicSize = Mathf.Lerp(a.orthographicSize, b.orthographicSize, u);
            if (_follow == null) return;
            _follow.feetScreenFraction = Mathf.Lerp(a.feetScreenFraction, b.feetScreenFraction, u);
            _follow.feetFractionCloseBoost = Mathf.Lerp(a.feetFractionCloseBoost, b.feetFractionCloseBoost, u);
            _follow.distanceZ = Mathf.Lerp(a.distanceZ, b.distanceZ, u);
            _follow.pitchDegrees = Mathf.Lerp(a.pitchDegrees, b.pitchDegrees, u);
            _follow.yawDegrees = Mathf.LerpAngle(a.yawDegrees, b.yawDegrees, u);
            _follow.lockFollowX = u < 0.5f ? a.lockFollowX : b.lockFollowX;
            if (_toMode != OverlayDisplayMode.Corridor)
                _follow.depthBlend = 0f;
        }
    }
}
