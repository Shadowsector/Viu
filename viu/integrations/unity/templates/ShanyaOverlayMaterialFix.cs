using System;
using UnityEngine;

namespace Viu.Runtime
{
    /// <summary>
    /// Player: FBX/Standard материалы часто magenta в build, хотя в Editor ок.
    /// Перед первым кадром — URP Lit + копия albedo с исходного материала.
    /// </summary>
    [DefaultExecutionOrder(-60)]
    public class ShanyaOverlayMaterialFix : MonoBehaviour
    {
        static Shader _lit;

        void Awake() => Apply();

        public static int Apply()
        {
#if UNITY_EDITOR
            // В Editor play mode тоже полезно для проверки.
#endif
            _lit = Shader.Find("Universal Render Pipeline/Lit")
                ?? Shader.Find("Universal Render Pipeline/Simple Lit");
            if (_lit == null)
            {
                Debug.LogError("[Viu] RuntimeMaterialFix: нет URP Lit");
                ShanyaDesktopOverlay.WriteBoot("MaterialFix FAIL: no URP Lit shader");
                return 0;
            }

            int fixedN = 0;
            int scanned = 0;
            foreach (var r in FindObjectsByType<Renderer>(FindObjectsSortMode.None))
            {
                if (r == null || !r.enabled) continue;
                var mats = r.materials;
                if (mats == null || mats.Length == 0) continue;
                bool changed = false;
                for (int i = 0; i < mats.Length; i++)
                {
                    scanned++;
                    var m = mats[i];
                    if (!NeedsFix(m)) continue;
                    mats[i] = CreateFixedMaterial(m, r.gameObject.name);
                    fixedN++;
                    changed = true;
                }
                if (changed)
                    r.materials = mats;
            }

            var msg = "MaterialFix runtime-rev=" + ShanyaDesktopOverlay.RuntimeRev
                + " scanned=" + scanned + " fixed=" + fixedN;
            Debug.Log("[Viu] " + msg);
            ShanyaDesktopOverlay.WriteBoot(msg);
            return fixedN;
        }

        static bool NeedsFix(Material m)
        {
            if (m == null) return true;
            var sn = m.shader != null ? m.shader.name : "";
            if (string.IsNullOrEmpty(sn)) return true;
            if (sn.IndexOf("Error", StringComparison.OrdinalIgnoreCase) >= 0) return true;
            if (sn.IndexOf("InternalErrorShader", StringComparison.OrdinalIgnoreCase) >= 0) return true;
            if (sn.IndexOf("Standard", StringComparison.OrdinalIgnoreCase) >= 0) return true;
            if (sn.IndexOf("Legacy", StringComparison.OrdinalIgnoreCase) >= 0) return true;
            if (sn.IndexOf("Autodesk", StringComparison.OrdinalIgnoreCase) >= 0) return true;
            if (sn.IndexOf("Universal Render Pipeline", StringComparison.OrdinalIgnoreCase) < 0
                && sn.IndexOf("Unlit/Color", StringComparison.OrdinalIgnoreCase) < 0)
                return true;
            if (IsUnityPink(m)) return true;
            return false;
        }

        static bool IsUnityPink(Material m)
        {
            if (m == null) return false;
            Color c = Color.white;
            if (m.HasProperty("_BaseColor")) c = m.GetColor("_BaseColor");
            else if (m.HasProperty("_Color")) c = m.GetColor("_Color");
            // Missing-shader pink (~1,0,1) или наш chroma (#FF0080 ≈ 1,0,0.5) на меше = битый mat.
            if (c.r > 0.92f && c.b > 0.92f && c.g < 0.08f) return true;
            if (c.r > 0.92f && c.g < 0.08f && c.b > 0.45f && c.b < 0.55f) return true;
            return false;
        }

        static Material CreateFixedMaterial(Material src, string meshName)
        {
            var dst = new Material(_lit);
            bool gotTex = CopyTextures(src, dst);
            Color c = GuessColor(meshName, src);
            if (src != null)
            {
                if (src.HasProperty("_BaseColor")) c = src.GetColor("_BaseColor");
                else if (src.HasProperty("_Color")) c = src.GetColor("_Color");
            }
            if (!gotTex || IsUnityPinkColor(c))
                c = GuessColor(meshName, src);
            if (dst.HasProperty("_BaseColor")) dst.SetColor("_BaseColor", c);
            if (dst.HasProperty("_Color")) dst.SetColor("_Color", c);
            if (dst.HasProperty("_Smoothness")) dst.SetFloat("_Smoothness", gotTex ? 0.25f : 0.15f);
            return dst;
        }

        static bool IsUnityPinkColor(Color c)
        {
            if (c.r > 0.92f && c.b > 0.92f && c.g < 0.08f) return true;
            if (c.r > 0.92f && c.g < 0.08f && c.b > 0.45f && c.b < 0.55f) return true;
            return false;
        }

        static bool CopyTextures(Material src, Material dst)
        {
            if (src == null || dst == null) return false;
            bool got = false;
            TryCopyTex(src, dst, "_BaseMap", ref got);
            TryCopyTex(src, dst, "_MainTex", ref got);
            if (!got && src.mainTexture != null && dst.HasProperty("_BaseMap"))
            {
                dst.SetTexture("_BaseMap", src.mainTexture);
                got = true;
            }
            if (got && dst.HasProperty("_MainTex") && dst.HasProperty("_BaseMap"))
                dst.SetTexture("_MainTex", dst.GetTexture("_BaseMap"));
            return got;
        }

        static void TryCopyTex(Material src, Material dst, string prop, ref bool got)
        {
            if (got || !src.HasProperty(prop)) return;
            var t = src.GetTexture(prop);
            if (t == null) return;
            var tn = (t.name ?? "").ToLowerInvariant();
            if (tn.Contains("normal") || tn.Contains("nrm") || tn.Contains("bump")
                || tn.Contains("rough") || tn.Contains("metal") || tn.Contains("_ao"))
                return;
            if (dst.HasProperty("_BaseMap")) dst.SetTexture("_BaseMap", t);
            if (dst.HasProperty("_MainTex")) dst.SetTexture("_MainTex", t);
            got = true;
        }

        static Color GuessColor(string meshName, Material src)
        {
            var n = (meshName ?? "").ToLowerInvariant().Replace("-", "_");
            if (src != null && !string.IsNullOrEmpty(src.name))
                n += " " + src.name.ToLowerInvariant().Replace("-", "_");
            if (n.Contains("boot") || n.Contains("shoe") || n.Contains("gauntlet") || n.Contains("glove")
                || n.Contains("stock") || n.Contains("legging"))
                return new Color(0.12f, 0.10f, 0.09f);
            if (n.Contains("hair") || n.Contains("lash") || n.Contains("brow"))
                return new Color(0.22f, 0.16f, 0.10f);
            if (n.Contains("eye") || n.Contains("iris"))
                return new Color(0.55f, 0.15f, 0.65f);
            if (n.Contains("sclera"))
                return new Color(0.92f, 0.94f, 0.96f);
            if (n.Contains("skin") || n.Contains("body") || n.Contains("head"))
                return new Color(0.82f, 0.66f, 0.56f);
            if (n.Contains("thatch") || n.Contains("roof"))
                return new Color(0.62f, 0.48f, 0.28f);
            if (n.Contains("wood") || n.Contains("plank") || n.Contains("beam"))
                return new Color(0.42f, 0.28f, 0.16f);
            if (n.Contains("tree") || n.Contains("pine") || n.Contains("needle"))
                return new Color(0.18f, 0.32f, 0.14f);
            return new Color(0.55f, 0.48f, 0.42f);
        }
    }
}
