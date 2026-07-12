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
        /// <summary>Только Idle/Walk/Run — для оверлея, без SitIdle в default.</summary>
        public const string OverlayControllerPath = AnimationsFolder + "/Shanya_Overlay_Locomotion.controller";
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

            var bodyPath = FindBodyModelPath();
            var bodyAvatar = LoadBodyAvatar(bodyPath);
            foreach (var e in entries)
                EnsureHumanoidImport(e.AssetPath, bodyAvatar);

            var controller = BuildOrLoadController();
            ApplyStates(controller, entries);
            AssetDatabase.SaveAssets();
            if (log)
                Debug.Log(
                    "[Viu] Sync Animations: " + entries.Count + " клип(ов) → " + ControllerPath
                    + (bodyAvatar != null ? " (avatar copy from body)" : " (per-clip avatar)"));
        }

        /// <summary>
        /// Контроллер оверлея: только Idle + Walk (+ Run). Sit/Sleep не попадают в default Idle.
        /// </summary>
        public static RuntimeAnimatorController BuildOverlayLocomotionController(bool log = false)
        {
            SyncAll(log: false);
            var overrides = LoadOverrides();
            var all = DiscoverClips(overrides);
            var loco = all
                .Where(e =>
                    e.StateName.Equals("Idle", StringComparison.OrdinalIgnoreCase)
                    || e.StateName.Equals("Walk", StringComparison.OrdinalIgnoreCase)
                    || e.StateName.Equals("Run", StringComparison.OrdinalIgnoreCase))
                .ToList();

            bool hasIdle = loco.Any(e => e.StateName.Equals("Idle", StringComparison.OrdinalIgnoreCase));
            bool hasWalk = loco.Any(e => e.StateName.Equals("Walk", StringComparison.OrdinalIgnoreCase));
            if (!hasIdle || !hasWalk)
            {
                Debug.LogError(
                    "[Viu] Overlay locomotion: нужны Idle И Walk в Animations/. "
                    + "Сейчас Idle=" + hasIdle + " Walk=" + hasWalk
                    + ". Без Walk Шаня будет скользить без анимации ног.");
                // Всё равно соберём что есть, но это явная ошибка в логе batch
            }
            if (loco.Count == 0)
            {
                Debug.LogWarning("[Viu] Overlay locomotion: нет клипов — полный controller.");
                return AssetDatabase.LoadAssetAtPath<RuntimeAnimatorController>(ControllerPath);
            }

            EnsureFolder(Path.GetDirectoryName(OverlayControllerPath).Replace('\\', '/'));
            // Всегда пересобираем: старый .controller часто без Idle↔Walk → слайд.
            if (File.Exists(OverlayControllerPath))
                AssetDatabase.DeleteAsset(OverlayControllerPath);
            var controller = AnimatorController.CreateAnimatorControllerAtPath(OverlayControllerPath);

            ApplyStates(controller, loco);
            AssetDatabase.SaveAssets();
            if (log)
            {
                var names = string.Join(", ", loco.Select(e => e.StateName + "<" + Path.GetFileName(e.AssetPath) + ">"));
                Debug.Log("[Viu] Overlay locomotion: " + names + " → " + OverlayControllerPath);
            }
            return controller;
        }

        static string FindBodyModelPath()
        {
            string best = null;
            int bestScore = int.MinValue;
            foreach (var guid in AssetDatabase.FindAssets("t:Model"))
            {
                var path = AssetDatabase.GUIDToAssetPath(guid);
                if (!path.EndsWith(".fbx", StringComparison.OrdinalIgnoreCase)) continue;
                var name = Path.GetFileNameWithoutExtension(path).ToLowerInvariant();
                if (!name.Contains("shanya") && !name.Contains("erisa")) continue;
                int score = 0;
                if (name == "shanya_erisa" || name == "erisa" || name == "shanya") score += 100;
                if (path.IndexOf("/Characters/", StringComparison.OrdinalIgnoreCase) >= 0) score += 40;
                if (path.IndexOf("/Animations/", StringComparison.OrdinalIgnoreCase) >= 0) score -= 80;
                if (name.Contains("idle") || name.Contains("walk") || name.Contains("run")
                    || name.Contains("fall") || name.Contains("sit") || name.Contains("sleep")
                    || name.Contains("yawn") || name.Contains("@"))
                    score -= 60;
                if (score > bestScore) { bestScore = score; best = path; }
            }
            return bestScore >= 40 ? best : null;
        }

        static Avatar LoadBodyAvatar(string bodyPath)
        {
            if (string.IsNullOrEmpty(bodyPath)) return null;
            return AssetDatabase.LoadAllAssetsAtPath(bodyPath)
                .OfType<Avatar>()
                .FirstOrDefault();
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
            // state → лучший клип (не SitIdle вместо Idle, не _4 вместо базового)
            var best = new Dictionary<string, ClipEntry>(StringComparer.OrdinalIgnoreCase);
            var bestScore = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);

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
                var clip = LoadFirstAnimationClip(path);
                if (clip == null)
                {
                    Debug.LogWarning("[Viu] Нет AnimationClip в " + fileName);
                    continue;
                }

                int score = ScoreClipFile(Path.GetFileNameWithoutExtension(fileName), state);
                if (bestScore.TryGetValue(state, out var prev) && score <= prev)
                    continue;

                best[state] = new ClipEntry { AssetPath = path, StateName = state, Clip = clip };
                bestScore[state] = score;
            }

            ApplyOverlayPreferred(best, overrides);
            return best.Values.OrderBy(e => StateOrder(e.StateName)).ToList();
        }

        /// <summary>viu_clips.json → overlay_preferred: Idle=Shanya_Idle.fbx, Walk=Shanya_Walk.fbx</summary>
        static void ApplyOverlayPreferred(
            Dictionary<string, ClipEntry> best,
            Dictionary<string, string> overrides)
        {
            var preferred = LoadOverlayPreferred();
            foreach (var kv in preferred)
            {
                var state = kv.Key;
                var file = kv.Value;
                if (string.IsNullOrEmpty(file)) continue;
                var path = AnimationsFolder + "/" + file;
                if (AssetDatabase.LoadMainAssetAtPath(path) == null)
                {
                    Debug.LogWarning("[Viu] overlay_preferred не найден: " + path);
                    continue;
                }
                var clip = LoadFirstAnimationClip(path);
                if (clip == null)
                {
                    Debug.LogWarning("[Viu] overlay_preferred без клипа: " + file);
                    continue;
                }
                best[state] = new ClipEntry { AssetPath = path, StateName = state, Clip = clip };
                Debug.Log("[Viu] overlay_preferred " + state + " ← " + file);
            }
        }

        static Dictionary<string, string> LoadOverlayPreferred()
        {
            var result = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
            {
                ["Idle"] = "Shanya_Idle.fbx",
                ["Walk"] = "Shanya_Walk.fbx",
            };
            try
            {
                var full = Path.GetFullPath(
                    Path.Combine(Application.dataPath, "..", AnimationsFolder, ManifestName));
                if (!File.Exists(full)) return result;
                var json = File.ReadAllText(full);
                var block = json.IndexOf("overlay_preferred", StringComparison.OrdinalIgnoreCase);
                if (block < 0) return result;
                json = json.Substring(block);
                foreach (var state in new[] { "Idle", "Walk", "Run" })
                {
                    var key = "\"" + state + "\"";
                    var idx = json.IndexOf(key, StringComparison.OrdinalIgnoreCase);
                    if (idx < 0) continue;
                    var colon = json.IndexOf(':', idx);
                    if (colon < 0) continue;
                    var q1 = json.IndexOf('"', colon + 1);
                    if (q1 < 0) continue;
                    var q2 = json.IndexOf('"', q1 + 1);
                    if (q2 < 0) continue;
                    var file = json.Substring(q1 + 1, q2 - q1 - 1).Trim();
                    if (file.EndsWith(".fbx", StringComparison.OrdinalIgnoreCase))
                        result[state] = file;
                }
            }
            catch (Exception ex)
            {
                Debug.LogWarning("[Viu] overlay_preferred: " + ex.Message);
            }
            return result;
        }

        /// <summary>Выше = лучше. Оверлей: только Shanya_Idle / Shanya_Walk, не Mixamo/Sit.</summary>
        static int ScoreClipFile(string stemLower, string state)
        {
            var low = stemLower.ToLowerInvariant();
            int score = 50;
            // Точное Shanya_Idle / Shanya_Walk — абсолютный приоритет
            if (low == "shanya_" + state.ToLowerInvariant())
                score += 200;
            else if (low == state.ToLowerInvariant())
                score += 40;
            else if (low.StartsWith("shanya_") && low.Contains(state.ToLowerInvariant()))
                score += 80;
            else if (low.EndsWith("_" + state.ToLowerInvariant()))
                score += 20;
            // Варианты _2 _3 _4 — запасные
            if (System.Text.RegularExpressions.Regex.IsMatch(low, @"_\d+$"))
                score -= 40;
            // SitIdle / SleepIdle никогда не для Idle
            if (state.Equals("Idle", StringComparison.OrdinalIgnoreCase))
            {
                if (low.Contains("sit")) score -= 200;
                if (low.Contains("sleep")) score -= 200;
            }
            // Mixamo / X Bot — только запас, не для оверлея если есть Shanya_*
            if (low.Contains("x bot") || low.Contains("xbot") || low.Contains("@"))
                score -= 80;
            if (low.Contains("tough") || low.Contains("female"))
                score -= 30;
            return score;
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
            // sit/sleep ДО idle — иначе SitIdle → Idle и анимация «сломана»
            if (low.Contains("sit")) return "Sit";
            if (low.Contains("sleep")) return "Sleep";
            if (low.Contains("idle")) return "Idle";
            if (low.Contains("walk")) return "Walk";
            if (low.Contains("run")) return "Run";
            if (low.Contains("stretch")) return "Stretch";
            if (low.Contains("jump")) return "Jump";
            if (low.Contains("yawn")) return "Yawn";
            if (low.Contains("fall")) return "Fall";
            return null;
        }

        static void EnsureHumanoidImport(string assetPath, Avatar bodyAvatar)
        {
            var importer = AssetImporter.GetAtPath(assetPath) as ModelImporter;
            if (importer == null) return;
            var changed = false;
            if (importer.animationType != ModelImporterAnimationType.Human)
            {
                importer.animationType = ModelImporterAnimationType.Human;
                changed = true;
            }

            if (bodyAvatar != null)
            {
                if (importer.avatarSetup != ModelImporterAvatarSetup.CopyFromOther
                    || importer.sourceAvatar != bodyAvatar)
                {
                    importer.avatarSetup = ModelImporterAvatarSetup.CopyFromOther;
                    importer.sourceAvatar = bodyAvatar;
                    changed = true;
                }
            }
            else if (importer.avatarSetup != ModelImporterAvatarSetup.CreateFromThisModel)
            {
                importer.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
                changed = true;
            }

            if (!importer.importAnimation)
            {
                importer.importAnimation = true;
                changed = true;
            }
            if (EnsureFbxClipLoops(importer))
                changed = true;
            if (changed) importer.SaveAndReimport();
        }

        /// <summary>Loop Time на FBX — иначе Idle/Walk играют один раз и замирают.</summary>
        static bool EnsureFbxClipLoops(ModelImporter importer)
        {
            var clips = importer.clipAnimations;
            if (clips == null || clips.Length == 0)
                clips = importer.defaultClipAnimations;
            if (clips == null || clips.Length == 0)
                return false;

            var changed = false;
            for (int i = 0; i < clips.Length; i++)
            {
                if (clips[i].loopTime && clips[i].loopPose) continue;
                clips[i].loopTime = true;
                clips[i].loopPose = true;
                changed = true;
            }
            if (changed)
                importer.clipAnimations = clips;
            return changed;
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
                EnsureClipLoops(e.Clip);
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

        static void EnsureClipLoops(AnimationClip clip)
        {
            if (clip == null) return;
            var settings = AnimationUtility.GetAnimationClipSettings(clip);
            if (settings.loopTime) return;
            settings.loopTime = true;
            AnimationUtility.SetAnimationClipSettings(clip, settings);
            EditorUtility.SetDirty(clip);
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
