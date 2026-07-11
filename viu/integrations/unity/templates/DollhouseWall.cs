using UnityEngine;

namespace Viu.Runtime
{
    /// <summary>
    /// Кукольный дом: передняя стенка (Wall_front) скрывается, когда Шаня «дома».
    /// Имя меша задаётся при сборке сцены из *.viu.json рядом с FBX.
    /// </summary>
    public class DollhouseWall : MonoBehaviour
    {
        [Tooltip("Имя меша из viu.json → dollhouse_wall, обычно Wall_front")]
        public string wallMeshName = "Wall_front";

        [Tooltip("true = Шаня дома, стенка к экрану не рисуется")]
        public bool atHome = true;

        public void Apply()
        {
            if (string.IsNullOrWhiteSpace(wallMeshName))
                return;

            var target = wallMeshName.Trim();
            foreach (var r in GetComponentsInChildren<Renderer>(true))
            {
                if (RendererMatchesWall(r, target))
                    r.enabled = !atHome;
            }
        }

        public void SetAtHome(bool inside)
        {
            atHome = inside;
            Apply();
        }

        static bool RendererMatchesWall(Renderer r, string wallName)
        {
            if (r == null) return false;
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
