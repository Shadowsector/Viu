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

            var bodyPath = FindBodyModelPath();
            var bodyAvatar = LoadBodyAvatar(bodyPath);
            // Сначала форс-импорт клипов у всех FBX — иначе Discover видит «Нет AnimationClip».
            EnsureAllAnimationFbxImport(bodyAvatar, log);

            var overrides = LoadOverrides();
            var entries = DiscoverClips(overrides);
            if (entries.Count == 0)
            {
                Debug.LogWarning("[Viu] В Animations/ нет FBX с анимациями.");
                return;
            }

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
            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh();

            var bodyAvatar = LoadBodyAvatar(FindBodyModelPath());
            EnsureAllAnimationFbxImport(bodyAvatar, log);

            // Жёстко: Idle/Walk. Legacy-recover только для пинов (не для всех X Bot).
            var loco = new List<ClipEntry>();
            foreach (var file in IdlePinFiles)
            {
                var pinPath = AnimationsFolder + "/" + file;
                if (AssetDatabase.LoadMainAssetAtPath(pinPath) != null
                    && LoadFirstAnimationClip(pinPath) == null)
                    RecoverClipsViaLegacyThenHumanoid(pinPath, bodyAvatar);
                if (TryAddPinnedClip(loco, "Idle", file)) break;
            }
            foreach (var file in WalkPinFiles)
            {
                var pinPath = AnimationsFolder + "/" + file;
                if (AssetDatabase.LoadMainAssetAtPath(pinPath) != null
                    && LoadFirstAnimationClip(pinPath) == null)
                    RecoverClipsViaLegacyThenHumanoid(pinPath, bodyAvatar);
                if (TryAddPinnedClip(loco, "Walk", file)) break;
            }

            if (!loco.Any(e => e.StateName.Equals("Idle", StringComparison.OrdinalIgnoreCase))
                || !loco.Any(e => e.StateName.Equals("Walk", StringComparison.OrdinalIgnoreCase)))
            {
                var overrides = LoadOverrides();
                foreach (var e in DiscoverClips(overrides))
                {
                    if (!e.StateName.Equals("Idle", StringComparison.OrdinalIgnoreCase)
                        && !e.StateName.Equals("Walk", StringComparison.OrdinalIgnoreCase)
                        && !e.StateName.Equals("Run", StringComparison.OrdinalIgnoreCase))
                        continue;
                    if (loco.Any(x => x.StateName.Equals(e.StateName, StringComparison.OrdinalIgnoreCase)))
                        continue;
                    loco.Add(e);
                }
            }

            bool hasIdle = loco.Any(e => e.StateName.Equals("Idle", StringComparison.OrdinalIgnoreCase));
            bool hasWalk = loco.Any(e => e.StateName.Equals("Walk", StringComparison.OrdinalIgnoreCase));
            if (!hasIdle || !hasWalk)
            {
                Debug.LogError(
                    "[Viu] Overlay locomotion FAIL: Idle=" + hasIdle + " Walk=" + hasWalk
                    + ". Нужны Shanya_Idle.fbx и Shanya_Walk.fbx в " + AnimationsFolder
                    + " (после Rig→Humanoid + Animation→Import). НЕ подставляю Idle_Stand.");
                return null;
            }

            EnsureFolder(Path.GetDirectoryName(OverlayControllerPath).Replace('\\', '/'));
            if (AssetDatabase.LoadMainAssetAtPath(OverlayControllerPath) != null)
                AssetDatabase.DeleteAsset(OverlayControllerPath);
            var controller = AnimatorController.CreateAnimatorControllerAtPath(OverlayControllerPath);

            ApplyStates(controller, loco);
            AssetDatabase.SaveAssets();
            var names = string.Join(", ", loco.Select(e => e.StateName + "<" + Path.GetFileName(e.AssetPath) + ">"));
            Debug.Log("[Viu] Overlay locomotion OK: " + names + " → " + OverlayControllerPath
                + " (НЕ " + Path.GetFileName(ControllerPath) + ")");
            return controller;
        }

        static readonly string[] IdlePinFiles =
        {
            "X Bot@Idle.fbx", "Shanya_Idle.fbx", "Shanya_Idle_2.fbx", "Idle.fbx",
        };
        static readonly string[] WalkPinFiles =
        {
            "Shanya_Walk.fbx", "Shanya_Walk_2.fbx", "Take 001.fbx", "Walk.fbx",
            "Shanya_Run.fbx",  // запас: Run как Walk (state.speed 0.55)
        };

        static void EnsureAllAnimationFbxImport(Avatar bodyAvatar, bool log = false)
        {
            foreach (var guid in AssetDatabase.FindAssets("t:Model", new[] { AnimationsFolder }))
            {
                var path = AssetDatabase.GUIDToAssetPath(guid);
                if (!path.EndsWith(".fbx", StringComparison.OrdinalIgnoreCase)) continue;
                EnsureHumanoidImport(path, bodyAvatar);
            }
            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh();
            if (log)
                Debug.Log("[Viu] EnsureAllAnimationFbxImport done in " + AnimationsFolder);
        }

        /// <returns>true если клип добавлен</returns>
        static bool TryAddPinnedClip(List<ClipEntry> loco, string state, string fileName)
        {
            var path = AnimationsFolder + "/" + fileName;
            AnimationClip clip = null;
            string from = null;

            if (AssetDatabase.LoadMainAssetAtPath(path) != null)
            {
                EnsureHumanoidImport(path, LoadBodyAvatar(FindBodyModelPath()));
                clip = LoadFirstAnimationClip(path);
                if (clip == null)
                {
                    RecoverClipsViaLegacyThenHumanoid(path, LoadBodyAvatar(FindBodyModelPath()));
                    clip = LoadFirstAnimationClip(path);
                }
                if (clip != null)
                    from = fileName;
            }

            if (clip == null)
            {
                clip = FindClipInProject(state);
                if (clip != null)
                    from = "project:" + clip.name;
            }

            if (clip == null)
            {
                clip = FindClipInControllers(state);
                if (clip != null)
                    from = "controller:" + clip.name;
            }

            if (clip == null)
            {
                Debug.LogWarning("[Viu] Пин " + state + " FAIL — нет клипа (файл="
                    + fileName + ", project search пуст)");
                return false;
            }

            var assetPath = string.IsNullOrEmpty(path) || AssetDatabase.LoadMainAssetAtPath(path) == null
                ? AssetDatabase.GetAssetPath(clip)
                : path;
            loco.RemoveAll(e => e.StateName.Equals(state, StringComparison.OrdinalIgnoreCase));
            loco.Add(new ClipEntry { AssetPath = assetPath, StateName = state, Clip = clip });
            Debug.Log("[Viu] Пин " + state + " ← " + from + " clip=" + clip.name);
            return true;
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
            // Тело: Humanoid + Create From This Model, иначе у клипов Source=None.
            var bodyImp = AssetImporter.GetAtPath(bodyPath) as ModelImporter;
            if (bodyImp != null)
            {
                var ch = false;
                if (bodyImp.animationType != ModelImporterAnimationType.Human)
                {
                    bodyImp.animationType = ModelImporterAnimationType.Human;
                    ch = true;
                }
                if (bodyImp.avatarSetup != ModelImporterAvatarSetup.CreateFromThisModel)
                {
                    bodyImp.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
                    ch = true;
                }
                if (ch)
                {
                    bodyImp.SaveAndReimport();
                    Debug.Log("[Viu] Body Rig OK: " + bodyPath);
                }
            }
            return AssetDatabase.LoadAllAssetsAtPath(bodyPath)
                .OfType<Avatar>()
                .FirstOrDefault(a => a != null && a.isValid && a.isHuman);
        }

        static Dictionary<string, string> LoadOverrides()
        {
            var path = AnimationsFolder + "/" + ManifestName;
            var result = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            var fullManifest = Path.GetFullPath(Path.Combine(Application.dataPath, "..", path));
            if (!File.Exists(fullManifest)) return result;
            try
            {
                var json = File.ReadAllText(fullManifest);
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
            var bodyAvatar = LoadBodyAvatar(FindBodyModelPath());

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
                // Discover раньше грузил клип ДО EnsureHumanoidImport → «Нет AnimationClip» на всех FBX.
                EnsureHumanoidImport(path, bodyAvatar);
                var clip = LoadFirstAnimationClip(path);
                if (clip == null)
                {
                    ForceExtractClips(path);
                    clip = LoadFirstAnimationClip(path);
                }
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
                EnsureHumanoidImport(path, LoadBodyAvatar(FindBodyModelPath()));
                var clip = LoadFirstAnimationClip(path);
                if (clip == null)
                {
                    ForceExtractClips(path);
                    clip = LoadFirstAnimationClip(path);
                }
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
                ["Idle"] = "X Bot@Idle.fbx",
                ["Walk"] = "Shanya_Walk.fbx",
                ["Run"] = "Shanya_Run.fbx",
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

            // docs/UNITY_PIPELINE.md: анимации (Mixamo/Shanya_Idle) —
            // Create From This Model. Copy From Other к Erisa →
            // «Torso for Hips not found» (скелеты разные).
            bool isAnimClip = assetPath.IndexOf(
                "/Animations/", StringComparison.OrdinalIgnoreCase) >= 0;
            if (isAnimClip)
            {
                if (importer.avatarSetup != ModelImporterAvatarSetup.CreateFromThisModel
                    || importer.sourceAvatar != null)
                {
                    importer.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
                    importer.sourceAvatar = null;
                    changed = true;
                    Debug.Log("[Viu] Rig Create From This Model (не Copy Erisa): "
                        + Path.GetFileName(assetPath));
                }
            }
            else if (bodyAvatar != null && bodyAvatar.isValid && bodyAvatar.isHuman)
            {
                // Не-анимационный FBX (редко) — можно Copy
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
                importer.sourceAvatar = null;
                changed = true;
            }

            if (!importer.importAnimation)
            {
                importer.importAnimation = true;
                changed = true;
            }

            if (changed)
                importer.SaveAndReimport();

            ForceExtractClips(assetPath);
        }

        /// <summary>
        /// Legacy-импорт часто единственный способ, когда Humanoid+CopyFromOther
        /// оставил defaultClipAnimations пустым. Потом возвращаем Humanoid.
        /// </summary>
        static bool RecoverClipsViaLegacyThenHumanoid(string assetPath, Avatar bodyAvatar)
        {
            var importer = AssetImporter.GetAtPath(assetPath) as ModelImporter;
            if (importer == null) return false;

            Debug.Log("[Viu] RecoverClips Legacy→Humanoid: " + Path.GetFileName(assetPath));
            importer.animationType = ModelImporterAnimationType.Legacy;
            importer.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
            importer.importAnimation = true;
            importer.clipAnimations = System.Array.Empty<ModelImporterClipAnimation>();
            importer.SaveAndReimport();

            importer = AssetImporter.GetAtPath(assetPath) as ModelImporter;
            if (importer == null) return false;

            var defaults = importer.defaultClipAnimations;
            if (defaults != null && defaults.Length > 0)
            {
                for (int i = 0; i < defaults.Length; i++)
                {
                    defaults[i].loopTime = true;
                    defaults[i].loopPose = true;
                }
                importer.clipAnimations = defaults;
                importer.SaveAndReimport();
                importer = AssetImporter.GetAtPath(assetPath) as ModelImporter;
            }

            if (LoadFirstAnimationClip(assetPath) == null
                && LoadClipFromLegacyAnimationComponent(assetPath) == null)
            {
                Debug.LogWarning(
                    "[Viu] Legacy тоже без клипа: " + Path.GetFileName(assetPath)
                    + " (файл без AnimationStack? type="
                    + (importer != null ? importer.animationType.ToString() : "?")
                    + " importAnim=" + (importer != null && importer.importAnimation) + ")");
                return false;
            }

            // Mecanim Humanoid: анимация = свой Avatar (Create From This Model).
            // Retarget на Erisa делает Unity через Humanoid muscle space.
            importer = AssetImporter.GetAtPath(assetPath) as ModelImporter;
            if (importer == null) return false;
            importer.animationType = ModelImporterAnimationType.Human;
            importer.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
            importer.sourceAvatar = null;
            importer.importAnimation = true;
            defaults = importer.defaultClipAnimations;
            if (defaults != null && defaults.Length > 0)
            {
                for (int i = 0; i < defaults.Length; i++)
                {
                    defaults[i].loopTime = true;
                    defaults[i].loopPose = true;
                }
                importer.clipAnimations = defaults;
            }
            importer.SaveAndReimport();
            return LoadFirstAnimationClip(assetPath) != null;
        }

        /// <summary>
        /// Unity не создаёт AnimationClip sub-asset, пока clipAnimations не заполнены
        /// из defaultClipAnimations (Takes). Без этого LoadAllAssetsAtPath → 0 клипов.
        /// </summary>
        static bool ForceExtractClips(string assetPath)
        {
            var importer = AssetImporter.GetAtPath(assetPath) as ModelImporter;
            if (importer == null) return false;

            bool touched = false;
            if (!importer.importAnimation
                || importer.animationType == ModelImporterAnimationType.None)
            {
                importer.importAnimation = true;
                if (importer.animationType == ModelImporterAnimationType.None)
                    importer.animationType = ModelImporterAnimationType.Human;
                importer.SaveAndReimport();
                touched = true;
                importer = AssetImporter.GetAtPath(assetPath) as ModelImporter;
                if (importer == null) return false;
            }

            var defaults = importer.defaultClipAnimations;
            if (defaults == null || defaults.Length == 0)
            {
                AssetDatabase.ImportAsset(assetPath, ImportAssetOptions.ForceUpdate);
                importer = AssetImporter.GetAtPath(assetPath) as ModelImporter;
                if (importer == null) return false;
                defaults = importer.defaultClipAnimations;
            }

            if (defaults == null || defaults.Length == 0)
                return false; // тише: RecoverClips / FindClipInProject разберутся

            var current = importer.clipAnimations;
            bool needAssign = current == null || current.Length == 0;
            var clips = needAssign ? defaults : current;

            bool loopChanged = false;
            for (int i = 0; i < clips.Length; i++)
            {
                if (clips[i].loopTime && clips[i].loopPose) continue;
                clips[i].loopTime = true;
                clips[i].loopPose = true;
                loopChanged = true;
            }

            if (needAssign || loopChanged)
            {
                importer.clipAnimations = clips;
                importer.SaveAndReimport();
                return true;
            }
            return touched;
        }

        static AnimationClip LoadClipFromLegacyAnimationComponent(string modelPath)
        {
            var go = AssetDatabase.LoadMainAssetAtPath(modelPath) as GameObject;
            if (go == null) return null;
            var clips = AnimationUtility.GetAnimationClips(go);
            if (clips == null || clips.Length == 0)
            {
                var anim = go.GetComponent<Animation>() ?? go.GetComponentInChildren<Animation>();
                if (anim != null)
                    clips = AnimationUtility.GetAnimationClips(anim.gameObject);
            }
            if (clips == null) return null;
            return clips.FirstOrDefault(c => c != null && !c.name.StartsWith("__preview"));
        }

        /// <summary>Ищем любой AnimationClip в проекте по имени состояния.</summary>
        static AnimationClip FindClipInProject(string state)
        {
            AnimationClip best = null;
            int bestScore = int.MinValue;
            foreach (var guid in AssetDatabase.FindAssets("t:AnimationClip"))
            {
                var path = AssetDatabase.GUIDToAssetPath(guid);
                foreach (var clip in AssetDatabase.LoadAllAssetsAtPath(path).OfType<AnimationClip>())
                {
                    if (clip == null || clip.name.StartsWith("__preview")) continue;
                    int score = ScoreClipFile(clip.name, state);
                    score += ScoreClipFile(Path.GetFileNameWithoutExtension(path), state);
                    if (path.IndexOf("/Animations/", StringComparison.OrdinalIgnoreCase) >= 0)
                        score += 20;
                    if (score > bestScore)
                    {
                        bestScore = score;
                        best = clip;
                    }
                }
            }
            // Нужен уверенный матч, не случайный SitIdle для Idle
            if (best == null || bestScore < 80)
                return null;
            Debug.Log("[Viu] FindClipInProject " + state + " ← " + best.name
                + " score=" + bestScore + " @ " + AssetDatabase.GetAssetPath(best));
            return best;
        }

        static AnimationClip FindClipInControllers(string state)
        {
            foreach (var guid in AssetDatabase.FindAssets("t:AnimatorController"))
            {
                var path = AssetDatabase.GUIDToAssetPath(guid);
                var ctrl = AssetDatabase.LoadAssetAtPath<AnimatorController>(path);
                if (ctrl == null) continue;
                foreach (var layer in ctrl.layers)
                {
                    if (layer.stateMachine == null) continue;
                    foreach (var st in layer.stateMachine.states)
                    {
                        if (st.state == null) continue;
                        if (!st.state.name.Equals(state, StringComparison.OrdinalIgnoreCase))
                            continue;
                        var clip = st.state.motion as AnimationClip;
                        if (clip != null)
                        {
                            Debug.Log("[Viu] FindClipInControllers " + state
                                + " ← " + clip.name + " from " + Path.GetFileName(path));
                            return clip;
                        }
                    }
                }
            }
            return null;
        }

        /// <summary>Loop Time на FBX — иначе Idle/Walk играют один раз и замирают.</summary>
        static bool EnsureFbxClipLoops(ModelImporter importer)
        {
            if (importer == null) return false;
            return ForceExtractClips(importer.assetPath);
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

            // Idle <-> Walk по Speed (порог выше — иначе дрейф → вечный Walk/Run)
            if (byName.TryGetValue("Idle", out var idle) && byName.TryGetValue("Walk", out var walk))
            {
                var toWalk = idle.AddTransition(walk);
                toWalk.hasExitTime = false;
                toWalk.duration = 0.1f;
                toWalk.AddCondition(AnimatorConditionMode.Greater, 0.25f, SpeedParam);

                var toIdle = walk.AddTransition(idle);
                toIdle.hasExitTime = false;
                toIdle.duration = 0.1f;
                toIdle.AddCondition(AnimatorConditionMode.Less, 0.2f, SpeedParam);
            }

            // Если в Walk попал Run-клип — замедлить стейт (~похожая на ходьбу)
            if (byName.TryGetValue("Walk", out var walkState))
            {
                var motion = walkState.motion as AnimationClip;
                var pathHint = entries.FirstOrDefault(e =>
                    e.StateName.Equals("Walk", StringComparison.OrdinalIgnoreCase));
                bool looksRun = (motion != null && motion.name.IndexOf("run", StringComparison.OrdinalIgnoreCase) >= 0)
                    || (pathHint != null && pathHint.AssetPath.IndexOf("run", StringComparison.OrdinalIgnoreCase) >= 0);
                if (looksRun)
                {
                    walkState.speed = 0.55f;
                    Debug.Log("[Viu] Walk ← Run-клип, state.speed=0.55");
                }
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
            var fromAll = AssetDatabase.LoadAllAssetsAtPath(modelPath)
                .OfType<AnimationClip>()
                .FirstOrDefault(c => c != null && !c.name.StartsWith("__preview"));
            if (fromAll != null) return fromAll;

            var reps = AssetDatabase.LoadAllAssetRepresentationsAtPath(modelPath);
            if (reps != null)
            {
                foreach (var o in reps)
                {
                    var c = o as AnimationClip;
                    if (c != null && !c.name.StartsWith("__preview"))
                        return c;
                }
            }
            return null;
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

    /// <summary>
    /// Импорт FBX в Animations/: назначить takes в OnPreprocessAnimation
    /// (единственный момент, когда defaultClipAnimations стабильно непустой).
    /// </summary>
    public class ShanyaAnimationPostprocessor : AssetPostprocessor
    {
        void OnPreprocessAnimation()
        {
            if (!assetPath.StartsWith(
                    ShanyaAnimationSync.AnimationsFolder, StringComparison.OrdinalIgnoreCase))
                return;
            var mi = assetImporter as ModelImporter;
            if (mi == null) return;
            mi.importAnimation = true;
            mi.animationType = ModelImporterAnimationType.Human;
            // Никогда Copy From Other к Erisa — скелет Torso≠Mixamo Hips
            mi.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
            mi.sourceAvatar = null;
            var defaults = mi.defaultClipAnimations;
            if (defaults == null || defaults.Length == 0) return;
            for (int i = 0; i < defaults.Length; i++)
            {
                defaults[i].loopTime = true;
                defaults[i].loopPose = true;
            }
            mi.clipAnimations = defaults;
        }

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
