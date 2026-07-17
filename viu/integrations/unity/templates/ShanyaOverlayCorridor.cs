using UnityEngine;

namespace Viu.Runtime
{
    /// <summary>
    /// Коридор в глубину: Шаня у таскбара → идёт к сараю → у двери вход → кукольный дом.
    /// Режимы камеры/окна — через OverlayModeController (Facade / Corridor / Instance).
    /// </summary>
    public class ShanyaOverlayCorridor : MonoBehaviour
    {
        [Header("Corridor Z (world meters) — fallback если нет Anchor_*")]
        public float corridorNearZ = -2.0f;
        public float corridorFarZ = 4.5f;

        [Header("Door")]
        public float enterMargin = 0.15f;
        public float exitMargin = 0.35f;

        [Header("Scale (approach / retreat)")]
        public float scaleAtNear = 1.40f;
        public float scaleAtFar = 0.72f;

        Transform _character;
        DollhouseWall _dollhouse;
        ShanyaOverlayDepth _depth;
        ShanyaOverlayCamera _camera;
        OverlayModeController _modes;
        float _doorZ;
        float _baseScale = 1f;
        bool _inside;
        bool _initialized;

        void Start()
        {
            _depth = GetComponent<ShanyaOverlayDepth>();
            _modes = GetComponent<OverlayModeController>();
            _camera = Camera.main != null ? Camera.main.GetComponent<ShanyaOverlayCamera>() : null;
            ResolveReferences();
            SyncCorridorZFromAnchors();
            if (_character != null)
                _baseScale = _character.localScale.x;
            StartCoroutine(InitAfterScene());
        }

        System.Collections.IEnumerator InitAfterScene()
        {
            yield return null;
            yield return null;
            ResolveReferences();
            SyncCorridorZFromAnchors();
            if (_dollhouse != null)
            {
                var b = _dollhouse.WorldBounds();
                _doorZ = b.min.z;
                _inside = false;
                _dollhouse.SetAtHome(false);
                _modes?.SetMode(OverlayDisplayMode.Facade);
                Debug.Log("[Viu] Corridor: doorZ=" + _doorZ.ToString("F2")
                    + " near=" + corridorNearZ + " far=" + corridorFarZ + " outside=facade");
            }
            _initialized = true;
            ApplyDepthPresentation();
        }

        void Update()
        {
            if (!_initialized || _character == null)
            {
                ResolveReferences();
                return;
            }

            ApplyDepthPresentation();
            UpdateHomeTransition();
        }

        void SyncCorridorZFromAnchors()
        {
            var start = OverlaySceneAnchor.TryGetPosition(OverlayAnchorKind.CharacterStart);
            if (start.HasValue)
                corridorNearZ = start.Value.z;
            var barn = OverlaySceneAnchor.TryGetPosition(OverlayAnchorKind.BarnEntrance);
            if (barn.HasValue)
                corridorFarZ = barn.Value.z;
        }

        void ResolveReferences()
        {
            if (_modes == null)
                _modes = GetComponent<OverlayModeController>();
            if (_camera == null && Camera.main != null)
                _camera = Camera.main.GetComponent<ShanyaOverlayCamera>();
            if (_character == null && _camera != null)
                _character = _camera.target;
            if (_dollhouse == null)
            {
                foreach (var d in FindObjectsByType<DollhouseWall>(FindObjectsSortMode.None))
                {
                    if (d != null)
                    {
                        _dollhouse = d;
                        break;
                    }
                }
            }
        }

        void ApplyDepthPresentation()
        {
            if (_character == null) return;
            float z = _character.position.z;
            float span = Mathf.Max(0.01f, corridorFarZ - corridorNearZ);
            float t = Mathf.Clamp01((z - corridorNearZ) / span);

            if (!_inside && t > 0.08f && _modes != null && _modes.CurrentMode == OverlayDisplayMode.Facade)
                _modes.SetMode(OverlayDisplayMode.Corridor);

            if (!_inside)
            {
                float mul = Mathf.Lerp(scaleAtNear, scaleAtFar, t);
                _character.localScale = Vector3.one * (_baseScale * mul);
                if (_camera != null)
                    _camera.depthBlend = 1f - t;
            }

            if (_inside && _character != null)
                _character.localScale = Vector3.one * _baseScale;
        }

        void UpdateHomeTransition()
        {
            if (_dollhouse == null || _character == null) return;
            if (_doorZ == 0f && _dollhouse.WorldBounds().size.sqrMagnitude > 0.01f)
                _doorZ = _dollhouse.WorldBounds().min.z;

            float z = _character.position.z;
            if (!_inside && z >= _doorZ - enterMargin)
                EnterHome();
            else if (_inside && z < _doorZ - exitMargin)
                ExitHome();
        }

        void EnterHome()
        {
            _inside = true;
            _dollhouse.SetAtHome(true);
            _modes?.SetMode(OverlayDisplayMode.Instance);
            if (_character != null)
                _character.localScale = Vector3.one * _baseScale;
            if (_camera != null)
                _camera.depthBlend = 0f;
            Debug.Log("[Viu] Corridor → ENTER home (Instance preset)");
        }

        void ExitHome()
        {
            _inside = false;
            _dollhouse.SetAtHome(false);
            _modes?.SetMode(OverlayDisplayMode.Facade);
            Debug.Log("[Viu] Corridor → EXIT home (Facade preset)");
        }
    }
}
