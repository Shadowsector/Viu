using UnityEngine;

namespace Viu.Runtime
{
    /// <summary>
    /// Коридор в глубину: Шаня у таскбара → идёт к сараю → у двери вход → кукольный дом.
    /// Снаружи фасад (DollhouseWall.atHome=false), внутри стенка скрыта (atHome=true).
    /// Масштаб по Z — «приближается / отдаляется» на ortho-камере.
    /// </summary>
    public class ShanyaOverlayCorridor : MonoBehaviour
    {
        [Header("Corridor Z (world meters)")]
        public float corridorNearZ = -2.0f;
        public float corridorFarZ = 4.5f;

        [Header("Door")]
        public float enterMargin = 0.15f;
        public float exitMargin = 0.35f;

        [Header("Scale (approach / retreat)")]
        public float scaleAtNear = 1.18f;
        public float scaleAtFar = 0.72f;

        Transform _character;
        DollhouseWall _dollhouse;
        ShanyaOverlayDepth _depth;
        ShanyaOverlayCamera _camera;
        float _doorZ;
        float _baseScale = 1f;
        bool _inside;
        bool _initialized;

        void Start()
        {
            _depth = GetComponent<ShanyaOverlayDepth>();
            _camera = Camera.main != null ? Camera.main.GetComponent<ShanyaOverlayCamera>() : null;
            ResolveReferences();
            if (_character != null)
                _baseScale = _character.localScale.x;
            StartCoroutine(InitAfterScene());
        }

        System.Collections.IEnumerator InitAfterScene()
        {
            yield return null;
            yield return null;
            ResolveReferences();
            if (_dollhouse != null)
            {
                var b = _dollhouse.WorldBounds();
                _doorZ = b.min.z;
                // Снаружи: фасад виден, Шаня в коридоре у таскбара.
                _inside = false;
                _dollhouse.SetAtHome(false);
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

        void ResolveReferences()
        {
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
            float mul = Mathf.Lerp(scaleAtNear, scaleAtFar, t);
            _character.localScale = Vector3.one * (_baseScale * mul);

            if (_camera != null)
            {
                // Лёгкий zoom камеры: ближе к экрану — чуть крупнее кадр (только feet frac).
                _camera.depthBlend = 1f - t;
            }
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
            Debug.Log("[Viu] Corridor → ENTER home (dollhouse, front wall hidden)");
        }

        void ExitHome()
        {
            _inside = false;
            _dollhouse.SetAtHome(false);
            Debug.Log("[Viu] Corridor → EXIT home (facade wall)");
        }
    }
}
