using UnityEngine;

namespace Viu.Runtime
{
    /// <summary>
    /// Кукольный дом: передняя стенка скрывается, когда Шаня «дома».
    /// Имя из viu.json + эвристика «стена к камере» (камера оверлея смотрит +Z).
    /// </summary>
    public class DollhouseWall : MonoBehaviour
    {
        [Tooltip("Имя меша из viu.json → dollhouse_wall, обычно Wall_front")]
        public string wallMeshName = "Wall_front";

        [Tooltip("true = Шаня дома, стенка к экрану не рисуется")]
        public bool atHome = true;

        public int LastMatchCount { get; private set; }

        public void Apply()
        {
            LastMatchCount = 0;
            // Сначала всё включить, потом спрятать фасад
            foreach (var r in GetComponentsInChildren<Renderer>(true))
            {
                if (r != null)
                    r.enabled = true;
            }

            if (!atHome)
                return;

            var target = (wallMeshName ?? "").Trim();
            var homeBounds = WorldBounds();
            float nearZ = homeBounds.min.z;
            float depth = Mathf.Max(homeBounds.size.z, 0.01f);

            foreach (var r in GetComponentsInChildren<Renderer>(true))
            {
                if (r == null) continue;
                bool match = RendererMatchesWall(r, target)
                    || HeuristicFrontWall(r)
                    || NearCameraFace(r, nearZ, depth);
                if (!match) continue;
                LastMatchCount++;
                r.enabled = false;
            }

            // Если имени Wall_front нет (типично для сырого FBX) — режем переднюю
            // «плиту» по Z: всё, что касается ближних 22% глубины дома к камере.
            if (LastMatchCount == 0)
            {
                float slab = nearZ + depth * 0.22f;
                foreach (var r in GetComponentsInChildren<Renderer>(true))
                {
                    if (r == null || !r.enabled) continue;
                    if (r.bounds.min.z > slab) continue;
                    r.enabled = false;
                    LastMatchCount++;
                }
                Debug.LogWarning(
                    "[Viu] Dollhouse: «" + target + "» не найдена — скрыто по Z-slab: "
                    + LastMatchCount + " (белый куб = фасад). Пришли имена детей дома.");
            }
            else
                Debug.Log("[Viu] Dollhouse: скрыто мешей передней стенки: " + LastMatchCount);
        }

        public void SetAtHome(bool inside)
        {
            atHome = inside;
            Apply();
            var cam = Camera.main != null ? Camera.main.GetComponent<ShanyaOverlayCamera>() : null;
            if (cam == null) return;
            if (inside)
            {
                var b = WorldBounds();
                cam.LockToHome(b.center.x);
            }
            else
                cam.UnlockFollow();
        }

        public Bounds WorldBounds()
        {
            var renderers = GetComponentsInChildren<Renderer>(true);
            if (renderers == null || renderers.Length == 0)
                return new Bounds(transform.position, Vector3.one);
            Bounds? b = null;
            for (int i = 0; i < renderers.Length; i++)
            {
                if (renderers[i] == null) continue;
                if (b == null) b = renderers[i].bounds;
                else
                {
                    var bb = b.Value;
                    bb.Encapsulate(renderers[i].bounds);
                    b = bb;
                }
            }
            return b ?? new Bounds(transform.position, Vector3.one);
        }

        /// <summary>
        /// Камера оверлея с −Z смотрит на +Z: ближняя грань дома = min Z.
        /// Прячем тонкие «стенные» меши у этой грани — даже если имя не Wall_front.
        /// </summary>
        static bool NearCameraFace(Renderer r, float nearZ, float depth)
        {
            if (r == null) return false;
            var b = r.bounds;
            // ближняя четверть дома по Z
            if (b.center.z > nearZ + depth * 0.28f)
                return false;
            var size = b.size;
            // стена: тонкая по Z относительно ширины/высоты
            bool thinZ = size.z < Mathf.Max(size.x, size.y) * 0.35f + 0.05f;
            var n = r.gameObject.name.ToLowerInvariant();
            bool wallName = n.Contains("wall") || n.Contains("facade") || n.Contains("front")
                || n.Contains("стен");
            return thinZ || wallName;
        }

        static bool HeuristicFrontWall(Renderer r)
        {
            if (r == null) return false;
            var n = r.gameObject.name.ToLowerInvariant().Replace("-", "_");
            if (n.Contains("wall") && (n.Contains("front") || n.Contains("перед") || n.EndsWith("_f")))
                return true;
            var mf = r.GetComponent<MeshFilter>();
            if (mf != null && mf.sharedMesh != null)
            {
                var mn = mf.sharedMesh.name.ToLowerInvariant().Replace("-", "_");
                if (mn.Contains("wall") && (mn.Contains("front") || mn.Contains("перед")))
                    return true;
            }
            return false;
        }

        static bool RendererMatchesWall(Renderer r, string wallName)
        {
            if (r == null || string.IsNullOrEmpty(wallName)) return false;
            if (string.Equals(r.gameObject.name, wallName, System.StringComparison.OrdinalIgnoreCase))
                return true;
            if (r.gameObject.name.Replace("-", "_").Equals(
                    wallName.Replace("-", "_"), System.StringComparison.OrdinalIgnoreCase))
                return true;

            var meshFilter = r.GetComponent<MeshFilter>();
            if (meshFilter != null && meshFilter.sharedMesh != null)
            {
                var meshName = meshFilter.sharedMesh.name;
                if (string.Equals(meshName, wallName, System.StringComparison.OrdinalIgnoreCase))
                    return true;
                if (meshName.Replace("-", "_").Equals(
                        wallName.Replace("-", "_"), System.StringComparison.OrdinalIgnoreCase))
                    return true;
            }

            return false;
        }

        void Start() => Apply();
    }
}
