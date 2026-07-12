using UnityEngine;

namespace Viu.Runtime
{
    public enum OverlayDisplayMode
    {
        Facade,
        Corridor,
        Instance,
    }

    /// <summary>
    /// FSM режимов оверлея: Facade (дом у таскбара) → Corridor → Instance (крупный план).
    /// Не двигает объекты — только камера + окно + dollhouse.
    /// </summary>
    public class OverlayModeController : MonoBehaviour
    {
        public OverlayDisplayMode mode = OverlayDisplayMode.Facade;

        OverlayCameraPresets _presets;
        ShanyaDesktopOverlay _overlay;

        void Awake()
        {
            _presets = Camera.main != null ? Camera.main.GetComponent<OverlayCameraPresets>() : null;
            _overlay = GetComponent<ShanyaDesktopOverlay>();
            if (_overlay == null)
                _overlay = FindFirstObjectByType<ShanyaDesktopOverlay>();
        }

        void Start()
        {
            ApplyMode(mode, force: true);
        }

        public OverlayDisplayMode CurrentMode => mode;

        public void SetMode(OverlayDisplayMode next)
        {
            if (mode == next) return;
            ApplyMode(next, force: false);
        }

        void ApplyMode(OverlayDisplayMode next, bool force)
        {
            if (!force && mode == next) return;
            mode = next;
            if (_presets == null && Camera.main != null)
                _presets = Camera.main.GetComponent<OverlayCameraPresets>();
            _presets?.Apply(next);
            if (_overlay == null)
                _overlay = FindFirstObjectByType<ShanyaDesktopOverlay>();
            _overlay?.ApplyDisplayMode(next);
            Debug.Log("[Viu] Overlay mode → " + next);
        }
    }
}
