#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;

namespace Viu.Editor
{
    /// <summary>
    /// Скан Assets/Characters/Shanya/Animations/*.fbx → Humanoid + состояния в Animator.
    /// Меню: Viu → Sync Animations. Batch: Viu.Editor.ShanyaAnimationSync.RunBatch
    /// </summary>
    public static class ShanyaAnimationSync
    {
        public const string AnimationsFolder = "Assets/Characters/Shanya/Animations";
        public const string ControllerPath = AnimationsFolder + "/Shanya_Idle_Stand.controller";
        public const string ManifestName = "viu_clips.json";
        public const string SpeedParam = "Speed";

        [MenuItem("Viu/Sync Animations (scan folder)")]
        public static void RunMenu() => SyncAll(log: true);

        public static void RunBatch()
        {
            SyncAll(log: true);
            EditorApplication.Exit(0);
        }

        public static void SyncAll(bool log = false)
        {
            if (!AssetDatabase.IsValidFolder(AnimationsFolder))
            {
                Debug.LogWarning("[Viu] Нет папки " + AnimationsFolder + " — создай и положи FBX.");
                return;
            }

            var overrides = LoadOverrides();
            var entries = DiscoverClips(overrides);
            if (entries.Count == 0)
            {
                Debug.LogWarning("[Viu] В Animations/ нет FBX с анимациями.");
                return;
            }

            foreach (var e in entries)
                EnsureHumanoidImport(e.AssetPath);

            var controller = BuildOrLoadController();
            ApplyStates(controller, entries);
            AssetDatabase.SaveAssets();
            if (log)
                Debug.Log("[Viu] Sync Animations: " + entries.Count + " клип(ов) → " + ControllerPath);
        }

        static Dictionary<string, string> LoadOverrides()
        {
            var path = AnimationsFolder + "/" + ManifestName;
            var result = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            if (!File.Exists(path)) return result;
            try
            {
                var json = File.ReadAllText(path);
                var wrapper = JsonUtility.FromJson<ClipManifest>(json);
                if (wrapper?.overrides == null) return result;
                foreach (var o in wrapper.overrides)
                    if (!string.IsNullOrEmpty(o.file) && !string.IsNullOrEmpty(o.state))
                        result[o.file] = o.state;
            }
            catch (Exception ex)
            {
                Debug.LogWarning("[Viu] viu_clips.json: " + ex.Message);
            }
            return result;
        }

        static List<ClipEntry> DiscoverClips(Dictionary<string, string> overrides)
        {
            var list = new List<ClipEntry>();
            var seenStates = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var guid in AssetDatabase.FindAssets("t:Model", new[] { AnimationsFolder }))
            {
                var path = AssetDatabase.GUIDToAssetPath(guid);
                if (!path.EndsWith(".fbx", StringComparison.OrdinalIgnoreCase)) continue;
                var fileName = Path.GetFileName(path);
                var state = ResolveStateName(fileName, overrides);
                if (string.IsNullOrEmpty(state))
                {
                    Debug.LogWarning("[Viu] Пропуск (непонятное имя): " + fileName +
                        " — переименуй (Walk, Idle) или viu_clips.json");
                    continue;
                }
                if (!seenStates.Add(state))
                {
                    Debug.LogWarning("[Viu] Дубликат состояния " + state + " для " + fileName);
                    continue;
                }
                var clip = LoadFirstAnimationClip(path);
                if (clip == null)
                {
                    Debug.LogWarning("[Viu] Нет AnimationClip в " + fileName);
                    continue;
                }
                list.Add(new ClipEntry { AssetPath = path, StateName = state, Clip = clip });
            }
            return list.OrderBy(e => StateOrder(e.StateName)).ToList();
        }

        static int StateOrder(string state)
        {
            switch (state.ToLowerInvariant())
            {
                case "idle": return 0;
                case "walk": return 1;
                case "run": return 2;
                default: return 10;
            }
        }

        static string ResolveStateName(string fileName, Dictionary<string, string> overrides)
        {
            if (overrides.TryGetValue(fileName, out var s)) return s;
            var low = Path.GetFileNameWithoutExtension(fileName).ToLowerInvariant();
            if (low.Contains("idle")) return "Idle";
            if (low.Contains("walk")) return "Walk";
            if (low.Contains("run")) return "Run";
            if (low.Contains("sit")) return "Sit";
            if (low.Contains("sleep")) return "Sleep";
            if (low.Contains("stretch")) return "Stretch";
            if (low.Contains("jump")) return "Jump";
            return null;
        }

        static void EnsureHumanoidImport(string assetPath)
        {
            var importer = AssetImporter.GetAtPath(assetPath) as ModelImporter;
            if (importer == null) return;
            var changed = false;
            if (importer.animationType != ModelImporterAnimationType.Human)
            {
                importer.animationType = ModelImporterAnimationType.Human;
                importer.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
                changed = true;
            }
            if (!importer.importAnimation)
            {
                importer.importAnimation = true;
                changed = true;
            }
            if (changed) importer.SaveAndReimport();
        }

        static AnimatorController BuildOrLoadController()
        {
            EnsureFolder(Path.GetDirectoryName(ControllerPath).Replace('\\', '/'));
            if (File.Exists(ControllerPath))
                return AssetDatabase.LoadAssetAtPath<AnimatorController>(ControllerPath);
            return AnimatorController.CreateAnimatorControllerAtPath(ControllerPath);
        }

        static void ApplyStates(AnimatorController controller, List<ClipEntry> entries)
        {
            var layer = controller.layers[0];
            var sm = layer.stateMachine;

            // Удалить старые состояния
            foreach (var child in sm.states.ToArray())
                sm.RemoveState(child.state);

            // Параметр Speed для Idle/Walk
            if (!controller.parameters.Any(p => p.name == SpeedParam))
                controller.AddParameter(SpeedParam, AnimatorControllerParameterType.Float);

            AnimatorState idleState = null;
            var byName = new Dictionary<string, AnimatorState>(StringComparer.OrdinalIgnoreCase);

            foreach (var e in entries)
            {
                var st = sm.AddState(e.StateName);
                st.motion = e.Clip;
                byName[e.StateName] = st;
                if (e.StateName.Equals("Idle", StringComparison.OrdinalIgnoreCase))
                    idleState = st;
            }

            if (idleState == null && byName.Count > 0)
                idleState = byName.Values.First();
            if (idleState != null)
                sm.defaultState = idleState;

            // Idle <-> Walk по Speed
            if (byName.TryGetValue("Idle", out var idle) && byName.TryGetValue("Walk", out var walk))
            {
                var toWalk = idle.AddTransition(walk);
                toWalk.hasExitTime = false;
                toWalk.duration = 0.1f;
                toWalk.AddCondition(AnimatorConditionMode.Greater, 0.05f, SpeedParam);

                var toIdle = walk.AddTransition(idle);
                toIdle.hasExitTime = false;
                toIdle.duration = 0.1f;
                toIdle.AddCondition(AnimatorConditionMode.Less, 0.05f, SpeedParam);
            }

            EditorUtility.SetDirty(controller);
        }

        static AnimationClip LoadFirstAnimationClip(string modelPath)
        {
            return AssetDatabase.LoadAllAssetsAtPath(modelPath)
                .OfType<AnimationClip>()
                .FirstOrDefault(c => !c.name.StartsWith("__preview"));
        }

        static void EnsureFolder(string assetPath)
        {
            if (AssetDatabase.IsValidFolder(assetPath)) return;
            var parts = assetPath.Split('/');
            var current = parts[0];
            for (int i = 1; i < parts.Length; i++)
            {
                var next = current + "/" + parts[i];
                if (!AssetDatabase.IsValidFolder(next))
                    AssetDatabase.CreateFolder(current, parts[i]);
                current = next;
            }
        }

        class ClipEntry
        {
            public string AssetPath;
            public string StateName;
            public AnimationClip Clip;
        }

        [Serializable]
        class ClipManifest
        {
            public ClipOverride[] overrides;
        }

        [Serializable]
        class ClipOverride
        {
            public string file;
            public string state;
        }
    }

    /// <summary>При импорте FBX в Animations/ — автосинк (если Unity открыт).</summary>
    public class ShanyaAnimationPostprocessor : AssetPostprocessor
    {
        static void OnPostprocessAllAssets(
            string[] importedAssets,
            string[] deletedAssets,
            string[] movedAssets,
            string[] movedFromAssetPaths)
        {
            var touched = importedAssets.Concat(movedAssets)
                .Any(p => p.StartsWith(ShanyaAnimationSync.AnimationsFolder, StringComparison.OrdinalIgnoreCase)
                    && p.EndsWith(".fbx", StringComparison.OrdinalIgnoreCase));
            if (!touched) return;
            EditorApplication.delayCall += () =>
            {
                if (!EditorApplication.isPlayingOrWillChangePlaymode)
                    ShanyaAnimationSync.SyncAll(log: true);
            };
        }
    }
}
#endif
