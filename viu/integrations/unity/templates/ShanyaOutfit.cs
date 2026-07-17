#if UNITY_EDITOR
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace Viu.Editor
{
    /// <summary>
    /// Переключение outfit Шани в сцене (dressed / swimsuit / shower).
    /// Меню: Viu → Outfit → …
    /// </summary>
    public static class ShanyaOutfit
    {
        public enum Mode { Dressed, Swimsuit, Shower }

        [MenuItem("Viu/Outfit/Dressed")]
        public static void MenuDressed() => Apply(Mode.Dressed);

        [MenuItem("Viu/Outfit/Swimsuit")]
        public static void MenuSwimsuit() => Apply(Mode.Swimsuit);

        [MenuItem("Viu/Outfit/Shower")]
        public static void MenuShower() => Apply(Mode.Shower);

        public static void Apply(Mode mode)
        {
            var root = FindCharacterRoot();
            if (root == null)
            {
                Debug.LogError("[Viu] Персонаж Shanya/Erisa не найден в сцене.");
                return;
            }
            int on = 0, off = 0;
            foreach (var r in root.GetComponentsInChildren<Renderer>(true))
            {
                var n = r.gameObject.name.ToLowerInvariant();
                if (IsWgt(n))
                {
                    SetActive(r.gameObject, false, ref on, ref off);
                    continue;
                }
                var show = mode switch
                {
                    Mode.Shower => IsBodyPart(n),
                    Mode.Swimsuit => IsBodyPart(n) || n.Contains("swim"),
                    _ => IsBodyPart(n) || IsDressedClothing(n),
                };
                if (mode == Mode.Dressed && n.Contains("swim"))
                    show = false;
                SetActive(r.gameObject, show, ref on, ref off);
            }
            Debug.Log($"[Viu] Outfit {mode}: включено {on}, выключено {off}");
        }

        static GameObject FindCharacterRoot()
        {
            foreach (var go in Object.FindObjectsByType<GameObject>(FindObjectsSortMode.None))
            {
                var n = go.name.ToLowerInvariant();
                if ((n.Contains("shanya") || n.Contains("erisa")) && !n.Contains("idle"))
                    if (go.GetComponentInChildren<SkinnedMeshRenderer>() != null)
                        return go;
            }
            return null;
        }

        static bool IsWgt(string n) => n.StartsWith("wgt");

        static bool IsBodyPart(string n) =>
            n.Contains("body") || n.Contains("hair") || n.Contains("eye") ||
            n.Contains("ear") || n.Contains("lash") || n.Contains("brow") ||
            n.Contains("teeth") || n.Contains("tongue") || n.Contains("head");

        static bool IsDressedClothing(string n) =>
            n.Contains("cloth") || n.Contains("outfit") || n.Contains("dress") ||
            n.Contains("shirt") || n.Contains("skirt") || n.Contains("pant") ||
            n.Contains("sock") || n.Contains("shoe") || n.Contains("boot") ||
            n.Contains("jacket") || n.Contains("coat") || n.Contains("top") ||
            n.Contains("bottom") || n.Contains("bra") || n.Contains("under");

        static void SetActive(GameObject go, bool active, ref int on, ref int off)
        {
            if (go.activeSelf == active) return;
            go.SetActive(active);
            if (active) on++; else off++;
        }
    }
}
#endif
