using UnityEngine;

namespace Viu.Runtime
{
    /// <summary>
    /// Кукольный дом: передняя стенка / оболочка скрывается, когда Шаня «дома».
    /// Old_Stables часто без Wall_front (только barn_interior) — прячем shell по имени.
    /// </summary>
    public class DollhouseWall : MonoBehaviour
    {
        [Tooltip("Имя меша из viu.json → dollhouse_wall. Пусто = только эвристики.")]
        public string wallMeshName = "";

        [Tooltip("true = Шаня дома, фасад/оболочка к экрану не рисуется")]
        public bool atHome = true;

        public int LastMatchCount { get; private set; }

        public void Apply()
        {
            LastMatchCount = 0;
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
                bool match = (!string.IsNullOrEmpty(target) && RendererMatchesWall(r, target))
                    || HeuristicFrontWall(r)
                    || IsBuildingShell(r)
                    || NearCameraFace(r, nearZ, depth);
                if (!match) continue;
                LastMatchCount++;
                r.enabled = false;
            }

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
                    "[Viu] Dollhouse: «" + target + "» пусто/не найдено — Z-slab hide="
                    + LastMatchCount + ". Нужен open_wall в Blender или shell-имя.");
            }
            else
                Debug.Log("[Viu] Dollhouse: скрыто мешей фасада/оболочки: " + LastMatchCount);
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
        /// Old_Stables: нет Wall_front, зато есть thatched_house_big_barn_interior —
        /// это и есть серый «куб» на скрине. Прячем оболочку дома.
        /// </summary>
        static bool IsBuildingShell(Renderer r)
        {
            if (r == null) return false;
            var n = r.gameObject.name.ToLowerInvariant().Replace("-", "_");
            if (n.Contains("barn_interior") || n.Contains("house_big") || n.Contains("thatched"))
                return true;
            if (n.Contains("interior") && (n.Contains("house") || n.Contains("barn") || n.Contains("stable")))
                return true;
            if (n.Contains("wall") || n.Contains("facade") || n.Contains("roof") || n.Contains("ceiling"))
                return true;
            if (n.Contains("fog") || n == "dust")
                return true;
            var mf = r.GetComponent<MeshFilter>();
            if (mf != null && mf.sharedMesh != null)
            {
                var mn = mf.sharedMesh.name.ToLowerInvariant().Replace("-", "_");
                if (mn.Contains("barn_interior") || mn.Contains("thatched_house"))
                    return true;
            }
            return false;
        }

        static bool NearCameraFace(Renderer r, float nearZ, float depth)
        {
            if (r == null) return false;
            var b = r.bounds;
            if (b.center.z > nearZ + depth * 0.28f)
                return false;
            var size = b.size;
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
