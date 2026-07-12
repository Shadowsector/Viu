using UnityEngine;

namespace Viu.Runtime
{
    /// <summary>
    /// Кукольный дом: передняя стенка скрывается, когда Шаня «дома».
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
            if (string.IsNullOrWhiteSpace(wallMeshName) && !atHome)
                return;

            var target = (wallMeshName ?? "").Trim();
            foreach (var r in GetComponentsInChildren<Renderer>(true))
            {
                if (r == null) continue;
                bool match = RendererMatchesWall(r, target) || HeuristicFrontWall(r);
                if (!match) continue;
                LastMatchCount++;
                // Дома прячем переднюю стенку; в походе — показываем
                r.enabled = !atHome;
            }

            if (atHome && LastMatchCount == 0)
                Debug.LogWarning(
                    "[Viu] Dollhouse: не нашла стенку «" + target +
                    "». Проверь .viu.json / имена в FBX. Белая «коробка» = фасад не скрыт.");
            else if (atHome)
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
            var renderers = GetComponentsInChildren<Renderer>();
            if (renderers == null || renderers.Length == 0)
                return new Bounds(transform.position, Vector3.one);
            var b = renderers[0].bounds;
            for (int i = 1; i < renderers.Length; i++)
                if (renderers[i] != null && renderers[i].enabled)
                    b.Encapsulate(renderers[i].bounds);
            return b;
        }

        static bool HeuristicFrontWall(Renderer r)
        {
            if (r == null) return false;
            var n = r.gameObject.name.ToLowerInvariant().Replace("-", "_");
            // типичные имена экспорта
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
