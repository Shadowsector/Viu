using UnityEngine;

namespace Viu.Runtime
{
    public enum OverlayAnchorKind
    {
        TaskbarFeetLine,
        HomeRoot,
        BarnEntrance,
        CharacterStart,
    }

    /// <summary>
    /// Пустой Transform-маркер в OverlayDesktop.unity — позиции правит Ден в Editor.
    /// </summary>
    public class OverlaySceneAnchor : MonoBehaviour
    {
        public OverlayAnchorKind kind;

        public static OverlaySceneAnchor Find(OverlayAnchorKind anchorKind)
        {
            foreach (var a in FindObjectsByType<OverlaySceneAnchor>(FindObjectsSortMode.None))
            {
                if (a != null && a.kind == anchorKind)
                    return a;
            }
            return null;
        }

        public static Vector3? TryGetPosition(OverlayAnchorKind anchorKind)
        {
            var a = Find(anchorKind);
            return a != null ? a.transform.position : (Vector3?)null;
        }
    }
}
