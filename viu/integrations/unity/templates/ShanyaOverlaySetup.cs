#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Animations;
using UnityEditor.Build.Reporting;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace Viu.Editor
{
    /// <summary>
    /// Сцена оверлея + Windows-сборка: прозрачная полоса у панели задач.
    /// Batch: Viu.Editor.ShanyaOverlaySetup.RunBatch / BuildWindows
    /// </summary>
    public static class ShanyaOverlaySetup
    {
        // @viu-deploy-rev 46
        const string ScenePath = "Assets/Scenes/OverlayDesktop.unity";
        const string CharacterRootName = "Shanya_Erisa";
        const string BuildFolder = "Builds/AnabarraOverlay";
        const string BuildExe = "AnabarraOverlay.exe";
        const string EnvironmentRoot = "Assets/Environment";
        const float TargetHeightMeters = 1.77f;
        const float HomeTargetHeightMeters = 8.2f;
        /// <summary>Не топить стопы в пол — раньше 0.03 давало «провал».</summary>
        const float GroundSinkMeters = 0f;
        const float FeetLiftMeters = 0f;
        /// <summary>180 — фасад Old_Stables к камере (0 = «задом» у Дена 2026-07-12).</summary>
        const float HomeYawDegrees = 180f;
        /// <summary>Дальняя стенка коридора — фасад сарая (min.z дома).</summary>
        const float CorridorFarWallZ = 4.5f;
        /// <summary>Старт Шани у таскбара (ближе к камере).</summary>
        const float CorridorStartZ = -2.0f;
        /// <summary>Половина высоты ortho-кадра в метрах (2*size = видимая высота мира).</summary>
        const float CameraOrthoHalfHeight = 5.5f;
        const string HomeMatFolder = "Assets/Environment/ViuOverlayMats/r46";
        const string CharMatFolder = "Assets/Characters/Shanya/ViuOverlayMats/r46";

        [MenuItem("Viu/Overlay/Prepare Overlay Scene")]
        public static void RunMenu() => Run(ScenePath);

        [MenuItem("Viu/Overlay/Build Windows Overlay")]
        public static void BuildMenu()
        {
            Run(ScenePath);
            BuildWindows();
        }

        public static void RunBatch()
        {
            int code = 0;
            try
            {
                if (File.Exists(ScenePath))
                    EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
                else
                    EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects, NewSceneMode.Single);
                Run(ScenePath);
            }
            catch (Exception e)
            {
                Debug.LogError("[Viu] Overlay scene: " + e.Message + "\n" + e.StackTrace);
                code = 1;
            }
            EditorApplication.Exit(code);
        }

        public static void BuildWindowsBatch()
        {
            int code = 0;
            try
            {
                BuildWindows();
            }
            catch (Exception e)
            {
                Debug.LogError("[Viu] Overlay build: " + e.Message + "\n" + e.StackTrace);
                code = 1;
            }
            EditorApplication.Exit(code);
        }

        public static void BuildWindows()
        {
            Run(ScenePath);
            EnsureBuildFolder();
            ConfigurePlayerForOverlay();

            var scenes = new[] { ScenePath };
            var report = BuildPipeline.BuildPlayer(
                new BuildPlayerOptions
                {
                    scenes = scenes,
                    locationPathName = Path.Combine(BuildFolder, BuildExe).Replace('\\', '/'),
                    target = BuildTarget.StandaloneWindows64,
                    options = BuildOptions.None,
                });

            if (report.summary.result == BuildResult.Succeeded)
            {
                Debug.Log("[Viu] Overlay build OK: " + report.summary.outputPath);
                WriteOverlayLauncher();
            }
            else
                throw new InvalidOperationException(
                    "Overlay build failed: " + report.summary.result + " — см. Console.");
        }

        static void WriteOverlayLauncher()
        {
            var dir = Path.Combine(Application.dataPath, "..", BuildFolder);
            Directory.CreateDirectory(dir);
            var bat = Path.Combine(dir, "LaunchOverlay.bat");
            // start без ожидания — cmd-окно не висит; bitblt обязателен для ColorKey
            var body =
                "@echo off\r\n" +
                "cd /d \"%~dp0\"\r\n" +
                "start \"AnabarraOverlay\" /B \"AnabarraOverlay.exe\" -force-d3d11 -force-d3d11-bitblt-model -popupwindow\r\n" +
                "exit /b 0\r\n";
            File.WriteAllText(bat, body, System.Text.Encoding.ASCII);

            // Без чёрного терминала вообще
            var vbs = Path.Combine(dir, "LaunchOverlay.vbs");
            var vbsBody =
                "Set sh = CreateObject(\"WScript.Shell\")\r\n" +
                "sh.CurrentDirectory = CreateObject(\"Scripting.FileSystemObject\").GetParentFolderName(WScript.ScriptFullName)\r\n" +
                "sh.Run \"AnabarraOverlay.exe -force-d3d11 -force-d3d11-bitblt-model -popupwindow\", 0, False\r\n";
            File.WriteAllText(vbs, vbsBody, System.Text.Encoding.ASCII);
            Debug.Log("[Viu] Launcher: " + bat + " + LaunchOverlay.vbs");
        }

        static void ConfigurePlayerForOverlay()
        {
            PlayerSettings.fullScreenMode = FullScreenMode.Windowed;
            PlayerSettings.defaultScreenWidth = 1920;
            PlayerSettings.defaultScreenHeight = 1080;
            PlayerSettings.resizableWindow = false;
            PlayerSettings.runInBackground = true;
            PlayerSettings.visibleInBackground = true;
            PlayerSettings.colorSpace = ColorSpace.Gamma;
#if UNITY_2022_2_OR_NEWER
            PlayerSettings.useFlipModelSwapchain = false;
#endif
            PlayerSettings.SetUseDefaultGraphicsAPIs(BuildTarget.StandaloneWindows64, false);
            PlayerSettings.SetGraphicsAPIs(
                BuildTarget.StandaloneWindows64,
                new[] { UnityEngine.Rendering.GraphicsDeviceType.Direct3D11 });
            PlayerSettings.productName = "AnabarraOverlay";
            ForceFlipModelOffInProjectSettingsAsset();
        }

        /// <summary>PlayerSettings API иногда не пишет YAML вовремя — дублируем в .asset.</summary>
        static void ForceFlipModelOffInProjectSettingsAsset()
        {
            var path = Path.Combine(Application.dataPath, "..", "ProjectSettings", "ProjectSettings.asset");
            if (!File.Exists(path)) return;
            var text = File.ReadAllText(path);
            var updated = System.Text.RegularExpressions.Regex.Replace(
                text,
                @"(?m)^(\s*)useFlipModelSwapchain:\s*1\s*$",
                "$1useFlipModelSwapchain: 0");
            if (updated != text)
            {
                File.WriteAllText(path, updated);
                Debug.Log("[Viu] ProjectSettings.asset: useFlipModelSwapchain → 0");
            }
        }

        static void EnsureBuildFolder()
        {
            if (!AssetDatabase.IsValidFolder("Assets/Builds"))
                AssetDatabase.CreateFolder("Assets", "Builds");
            var full = Path.Combine(Application.dataPath, "..", BuildFolder);
            Directory.CreateDirectory(full);
        }

        /// <summary>
        /// Готовит OverlayDesktop.unity. Бросает при FAIL — иначе BuildWindows
        /// молча соберёт старую сцену с Idle_Stand (слайд без Walk).
        /// </summary>
        public static void Run(string saveScenePath)
        {
            var modelPath = FindModelPath();
            if (string.IsNullOrEmpty(modelPath))
                throw new InvalidOperationException(
                    "[Viu] FBX модели не найден. Сначала GameTest или импорт Shanya_Erisa.");

            EnsureHumanoidImport(modelPath);
            EnsureStandardMaterialImport(modelPath);
            var controller = ShanyaAnimationSync.BuildOverlayLocomotionController(log: true);
            if (controller == null)
                throw new InvalidOperationException(
                    "[Viu] Overlay locomotion FAIL — нет Shanya_Idle/Shanya_Walk. "
                    + "НЕ собираю старую сцену с Idle_Stand.");

            if (controller.name.IndexOf("Idle_Stand", StringComparison.OrdinalIgnoreCase) >= 0)
                throw new InvalidOperationException(
                    "[Viu] Отказ: controller=" + controller.name
                    + " (нужен Shanya_Overlay_Locomotion с Walk).");

            var avatar = LoadModelAvatar(modelPath);
            if (avatar == null)
                throw new InvalidOperationException("[Viu] Avatar не найден на модели.");

            var instance = PlaceCharacterInScene(modelPath, controller, avatar);
            DisableWgtMeshes(instance);
            var charDir = Path.GetDirectoryName(modelPath)?.Replace('\\', '/');
            AssetDatabase.Refresh();
            FixOverlayMaterials(instance, assetSourceDir: charDir, isHome: false);
            try { ShanyaOutfit.Apply(ShanyaOutfit.Mode.Dressed); }
            catch (Exception e) { Debug.LogWarning("[Viu] Outfit: " + e.Message); }
            // Повтор после outfit — иначе сапоги/0 переключённые слои остаются FBX-материалами (magenta в Player).
            FixOverlayMaterials(instance, assetSourceDir: charDir, isHome: false);
            EnsureLocomotion(instance);
            var home = EnsureHomeBuilding();
            EnsureOverlayEnvironment(instance);
            SnapFeetToGround(instance);
            LiftFeet(instance, FeetLiftMeters);
            if (home != null)
                PositionHomeAndShanyaInCorridor(instance, home);
            EnsureOverlayManager();
            // Камера «дома»: X = центр сарая. Фасад/кукольный дом — ShanyaOverlayCorridor.
            if (home != null)
            {
                var camFollow = Camera.main != null
                    ? Camera.main.GetComponent<Viu.Runtime.ShanyaOverlayCamera>()
                    : null;
                if (camFollow != null)
                    camFollow.LockToHome(ComputeWorldBounds(home).center.x);
            }
            AssetDatabase.SaveAssets();
            SaveActiveScene(saveScenePath);
            var meshCount = instance.GetComponentsInChildren<Renderer>(true).Length;
            var homeNote = home != null ? " + дом" : "";
            Debug.Log(
                "[Viu] Overlay scene готова" + homeNote + ": " + saveScenePath
                + " | character=" + instance.name + " from=" + modelPath
                + " renderers=" + meshCount);
        }

        static void EnsureOverlayManager()
        {
            var root = GameObject.Find("Viu_OverlayRoot");
            if (root == null)
                root = new GameObject("Viu_OverlayRoot");
            if (root.GetComponent<Viu.Runtime.ShanyaDesktopOverlay>() == null)
                root.AddComponent<Viu.Runtime.ShanyaDesktopOverlay>();
            if (root.GetComponent<Viu.Runtime.ShanyaOverlayDepth>() == null)
                root.AddComponent<Viu.Runtime.ShanyaOverlayDepth>();
            if (root.GetComponent<Viu.Runtime.ShanyaOverlayCorridor>() == null)
                root.AddComponent<Viu.Runtime.ShanyaOverlayCorridor>();
        }

        static void LiftFeet(GameObject root, float liftMeters)
        {
            if (liftMeters <= 0f) return;
            var pos = root.transform.position;
            pos.y += liftMeters;
            root.transform.position = pos;
        }

        static void EnsureOverlayEnvironment(GameObject shanya)
        {
            RenderSettings.skybox = null;
            RenderSettings.ambientMode = UnityEngine.Rendering.AmbientMode.Flat;
            RenderSettings.ambientLight = new Color(0.85f, 0.82f, 0.78f);
            DestroyInvisibleFloor();
            EnsureLighting();
            ScaleToHeight(shanya, TargetHeightMeters);
            EnsureOverlayCamera(shanya.transform);
        }

        /// <summary>
        /// Раньше Plane с выключенным Renderer всё равно иногда светился серым квадратом.
        /// </summary>
        static void DestroyInvisibleFloor()
        {
            var floor = GameObject.Find("Viu_Floor");
            if (floor != null)
                UnityEngine.Object.DestroyImmediate(floor);
        }

        static void EnsureInvisibleFloor() => DestroyInvisibleFloor();

        static void EnsureOverlayCamera(Transform target)
        {
            var cam = Camera.main;
            if (cam == null)
            {
                var go = new GameObject("Main Camera");
                go.tag = "MainCamera";
                cam = go.AddComponent<Camera>();
                go.AddComponent<AudioListener>();
            }
            cam.orthographic = true;
            cam.orthographicSize = CameraOrthoHalfHeight;
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = Viu.Runtime.ShanyaDesktopOverlay.ChromaKey;

            var follow = cam.GetComponent<Viu.Runtime.ShanyaOverlayCamera>();
            if (follow == null)
            {
                var old = cam.GetComponent<Viu.Runtime.ShanyaFollowCamera>();
                if (old != null)
                    UnityEngine.Object.DestroyImmediate(old);
                follow = cam.gameObject.AddComponent<Viu.Runtime.ShanyaOverlayCamera>();
            }
            follow.target = target;
            follow.feetScreenFraction = 0.07f;
            follow.distanceZ = 14f;
            follow.lockFollowX = true;
            follow.lockedWorldX = target.position.x;
            follow.followSmoothX = 0f;
            follow.transform.position = new Vector3(
                follow.lockedWorldX,
                target.position.y + CameraOrthoHalfHeight * (1f - 2f * follow.feetScreenFraction),
                target.position.z - follow.distanceZ);
            follow.transform.rotation = Quaternion.identity;
        }

        static void SaveActiveScene(string saveScenePath)
        {
            var scene = SceneManager.GetActiveScene();
            EditorSceneManager.MarkSceneDirty(scene);
            var path = string.IsNullOrEmpty(saveScenePath) ? scene.path : saveScenePath;
            if (string.IsNullOrEmpty(path))
                path = ScenePath;
            var dir = Path.GetDirectoryName(path).Replace('\\', '/');
            if (!string.IsNullOrEmpty(dir) && !AssetDatabase.IsValidFolder(dir))
                AssetDatabase.CreateFolder("Assets", "Scenes");
            EditorSceneManager.SaveScene(scene, path);
        }

        /// <summary>
        /// Тело персонажа, не клип анимации. Раньше первый попавшийся
        /// Shanya_Fall / Shanya_Run попадал в сцену вместо Shanya_Erisa.
        /// </summary>
        static string FindModelPath()
        {
            string best = null;
            int bestScore = int.MinValue;
            foreach (var guid in AssetDatabase.FindAssets("t:Model"))
            {
                var path = AssetDatabase.GUIDToAssetPath(guid);
                if (!path.EndsWith(".fbx", StringComparison.OrdinalIgnoreCase))
                    continue;
                var name = Path.GetFileNameWithoutExtension(path).ToLowerInvariant();
                if (!name.Contains("shanya") && !name.Contains("erisa"))
                    continue;

                // Клипы анимации (Shanya_Run/Idle/…) — НИКОГДА не тело. Иначе T-pose.
                if (path.IndexOf("/Animations/", StringComparison.OrdinalIgnoreCase) >= 0)
                    continue;
                if (IsAnimationClipName(name))
                    continue;

                int score = 0;
                if (name == "shanya_erisa" || name == "erisa" || name == "shanya")
                    score += 100;
                if (path.IndexOf("/Characters/", StringComparison.OrdinalIgnoreCase) >= 0)
                    score += 40;
                if (score > bestScore)
                {
                    bestScore = score;
                    best = path;
                }
            }
            return bestScore >= 40 ? best : null;
        }

        static bool IsAnimationClipName(string nameLower)
        {
            return nameLower.Contains("idle")
                || nameLower.Contains("walk")
                || nameLower.Contains("run")
                || nameLower.Contains("fall")
                || nameLower.Contains("sit")
                || nameLower.Contains("sleep")
                || nameLower.Contains("yawn")
                || nameLower.Contains("@");
        }

        static Avatar LoadModelAvatar(string modelPath)
        {
            return AssetDatabase.LoadAllAssetsAtPath(modelPath)
                .OfType<Avatar>()
                .FirstOrDefault();
        }

        static void EnsureHumanoidImport(string assetPath)
        {
            var importer = AssetImporter.GetAtPath(assetPath) as ModelImporter;
            if (importer == null) return;
            if (importer.animationType != ModelImporterAnimationType.Human)
            {
                importer.animationType = ModelImporterAnimationType.Human;
                importer.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
                importer.SaveAndReimport();
            }
        }

        static void EnsureLocomotion(GameObject instance)
        {
            if (instance.GetComponent<Viu.Runtime.ShanyaLocomotion>() == null)
                instance.AddComponent<Viu.Runtime.ShanyaLocomotion>();
        }

        static void EnsureLighting()
        {
            var light = UnityEngine.Object.FindFirstObjectByType<Light>();
            if (light == null)
            {
                var go = new GameObject("Viu_KeyLight");
                light = go.AddComponent<Light>();
            }
            light.type = LightType.Directional;
            light.transform.rotation = Quaternion.Euler(42f, -35f, 0f);
            light.intensity = 1.25f;
            light.color = new Color(1f, 0.96f, 0.9f);
        }

        static void ScaleToHeight(GameObject root, float targetHeight)
        {
            root.transform.localScale = Vector3.one;
            root.transform.position = Vector3.zero;
            var renderers = root.GetComponentsInChildren<Renderer>();
            if (renderers.Length == 0) return;
            Bounds bounds = renderers[0].bounds;
            foreach (var r in renderers)
                bounds.Encapsulate(r.bounds);
            float h = bounds.size.y;
            if (h < 0.01f) return;
            float factor = targetHeight / h;
            root.transform.localScale = Vector3.one * factor;
            bounds = renderers[0].bounds;
            foreach (var r in renderers)
                bounds.Encapsulate(r.bounds);
            var pos = root.transform.position;
            pos.y = -bounds.min.y - GroundSinkMeters;
            root.transform.position = pos;
        }

        static void SnapFeetToGround(GameObject root)
        {
            var anim = root.GetComponentInChildren<Animator>(true);
            if (anim != null && anim.enabled)
            {
                anim.Update(0f);
                if (anim.isHuman)
                {
                    var lf = anim.GetBoneTransform(HumanBodyBones.LeftFoot);
                    var rf = anim.GetBoneTransform(HumanBodyBones.RightFoot);
                    if (lf != null && rf != null)
                    {
                        float minY = Mathf.Min(lf.position.y, rf.position.y);
                        var p = root.transform.position;
                        p.y -= minY + GroundSinkMeters;
                        root.transform.position = p;
                        return;
                    }
                }
            }

            var renderers = root.GetComponentsInChildren<Renderer>();
            if (renderers.Length == 0) return;
            Bounds bounds = renderers[0].bounds;
            foreach (var r in renderers)
                bounds.Encapsulate(r.bounds);
            var pos = root.transform.position;
            pos.y = -bounds.min.y - GroundSinkMeters;
            root.transform.position = pos;
        }

        static GameObject PlaceCharacterInScene(string modelPath, RuntimeAnimatorController controller, Avatar avatar)
        {
            CleanupMisplacedShanyaRoots();
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(modelPath);
            if (prefab == null)
                throw new InvalidOperationException("[Viu] Не загрузился FBX персонажа: " + modelPath);

            var instance = (GameObject)PrefabUtility.InstantiatePrefab(prefab);
            instance.name = CharacterRootName;
            instance.transform.position = Vector3.zero;

            var animator = ConfigureExistingAnimator(instance, controller, avatar);
            if (!instance.activeInHierarchy)
                instance.SetActive(true);
            WriteAnimatorDiag(instance, animator, modelPath);
            return instance;
        }

        /// <summary>
        /// Нельзя Destroy/переносить Animator между объектами — Humanoid Avatar
        /// привязан к иерархии GameObject, иначе T-pose и «провал» в пол.
        /// Берём существующий Animator и только настраиваем controller/avatar.
        /// </summary>
        static Animator ConfigureExistingAnimator(
            GameObject root,
            RuntimeAnimatorController controller,
            Avatar avatar)
        {
            Animator best = null;
            foreach (var a in root.GetComponentsInChildren<Animator>(true))
            {
                if (a == null) continue;
                if (a.avatar != null && a.avatar.isValid && a.avatar.isHuman)
                {
                    best = a;
                    break;
                }
                if (best == null)
                    best = a;
            }
            if (best == null)
                best = root.AddComponent<Animator>();

            foreach (var a in root.GetComponentsInChildren<Animator>(true))
            {
                if (a == null || a == best) continue;
                // Пустой дубликат (часто от старого RequireComponent) — убрать.
                if (a.avatar == null || !a.avatar.isValid)
                    UnityEngine.Object.DestroyImmediate(a);
                else
                    a.enabled = false;
            }

            best.enabled = true;
            best.runtimeAnimatorController = controller;
            if (avatar != null)
                best.avatar = avatar;
            best.applyRootMotion = false;
            best.cullingMode = AnimatorCullingMode.AlwaysAnimate;
            best.Rebind();
            best.Update(0f);

            Debug.Log(
                "[Viu.Overlay] Animator keep=" + best.name
                + " path=" + GetTransformPath(best.transform)
                + " avatarValid=" + (best.avatar != null && best.avatar.isValid)
                + " human=" + (best.avatar != null && best.avatar.isHuman)
                + " ctrl=" + (best.runtimeAnimatorController != null));
            return best;
        }

        static string GetTransformPath(Transform t)
        {
            var parts = new List<string>();
            while (t != null)
            {
                parts.Add(t.name);
                t = t.parent;
            }
            parts.Reverse();
            return string.Join("/", parts);
        }

        static void WriteAnimatorDiag(GameObject root, Animator animator, string modelPath)
        {
            try
            {
                var path = Path.GetFullPath(Path.Combine(Application.dataPath, "..", "viu_animator.log"));
                var lines = new List<string>
                {
                    DateTime.Now.ToString("o"),
                    "model=" + modelPath,
                    "root=" + root.name,
                    "animatorGO=" + (animator != null ? animator.name : "null"),
                    "animatorPath=" + (animator != null ? GetTransformPath(animator.transform) : ""),
                    "ctrl=" + (animator != null && animator.runtimeAnimatorController != null
                        ? animator.runtimeAnimatorController.name : "null"),
                    "hasWalk=" + ControllerHasState(animator, "Walk"),
                    "hasIdle=" + ControllerHasState(animator, "Idle"),
                    "avatar=" + (animator != null && animator.avatar != null ? animator.avatar.name : "null"),
                    "avatarValid=" + (animator != null && animator.avatar != null && animator.avatar.isValid),
                    "human=" + (animator != null && animator.avatar != null && animator.avatar.isHuman),
                    "isHumanAnimator=" + (animator != null && animator.isHuman),
                };
                if (animator != null)
                {
                    foreach (var p in animator.parameters)
                        lines.Add("param " + p.name + " type=" + p.type);
                }
                foreach (var a in root.GetComponentsInChildren<Animator>(true))
                    lines.Add("foundAnimator " + GetTransformPath(a.transform)
                        + " enabled=" + a.enabled
                        + " avatar=" + (a.avatar != null));
                File.WriteAllText(path, string.Join("\n", lines) + "\n");
            }
            catch (Exception e)
            {
                Debug.LogWarning("[Viu] viu_animator.log: " + e.Message);
            }

            if (animator != null && animator.runtimeAnimatorController != null
                && !ControllerHasState(animator, "Walk"))
            {
                throw new InvalidOperationException(
                    "[Viu] Animator без Walk (ctrl="
                    + animator.runtimeAnimatorController.name + ") — сборка остановлена.");
            }
        }

        static bool ControllerHasState(Animator animator, string state)
        {
            if (animator == null || animator.runtimeAnimatorController == null)
                return false;
            var ac = animator.runtimeAnimatorController as AnimatorController;
            if (ac == null)
            {
                // Runtime override / built — пробуем через GetCurrentAnimatorClipInfo путь
                foreach (var clip in animator.runtimeAnimatorController.animationClips)
                {
                    if (clip == null) continue;
                    var n = clip.name.ToLowerInvariant();
                    if (n.Contains(state.ToLowerInvariant())) return true;
                }
                return false;
            }
            foreach (var layer in ac.layers)
            {
                if (layer.stateMachine == null) continue;
                foreach (var st in layer.stateMachine.states)
                {
                    if (st.state != null
                        && st.state.name.Equals(state, StringComparison.OrdinalIgnoreCase))
                        return true;
                }
            }
            return false;
        }

        /// <summary>
        /// Убирает старые корни (Shanya_Fall и т.п.), оставшиеся от ошибочного FindModelPath.
        /// </summary>
        static void CleanupMisplacedShanyaRoots()
        {
            var doomed = new List<GameObject>();
            foreach (var go in UnityEngine.Object.FindObjectsByType<GameObject>(
                         FindObjectsInactive.Include, FindObjectsSortMode.None))
            {
                if (go == null || go.transform.parent != null) continue;
                var n = go.name.ToLowerInvariant();
                if (n.StartsWith("viu_home_", StringComparison.Ordinal)) continue;
                if (n == "shanya_erisa" || n == "shanya"
                    || n.Contains("shanya") || n.Contains("erisa"))
                    doomed.Add(go);
            }
            foreach (var go in doomed)
                UnityEngine.Object.DestroyImmediate(go);
        }

        static void DisableWgtMeshes(GameObject root)
        {
            foreach (var t in root.GetComponentsInChildren<Transform>(true))
            {
                if (t.name.StartsWith("WGT") || t.name.StartsWith("WGT."))
                    t.gameObject.SetActive(false);
            }
        }

        /// <summary>Ставит сарай из Assets/Environment/ в сцену оверлея.</summary>
        static GameObject EnsureHomeBuilding()
        {
            if (!TryFindHomeFbx(out var fbxPath, out var metaAssetPath))
            {
                Debug.LogWarning(
                    "[Viu] Дом не найден. Экспорт сарая → Assets/Environment/<slug>/, потом Prepare Overlay снова.");
                return null;
            }

            EnsureStandardMaterialImport(fbxPath);

            var rootName = "Viu_Home_" + Path.GetFileNameWithoutExtension(fbxPath);
            var existing = GameObject.Find(rootName);
            GameObject home;
            if (existing != null)
            {
                home = existing;
            }
            else
            {
                var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(fbxPath);
                if (prefab == null)
                {
                    Debug.LogWarning("[Viu] Не загрузился FBX дома: " + fbxPath);
                    return null;
                }
                home = (GameObject)PrefabUtility.InstantiatePrefab(prefab);
                home.name = rootName;
                home.transform.position = Vector3.zero;
            }
            // Фасад к камере (иначе «дом с обратной стороны»)
            home.transform.rotation = Quaternion.Euler(0f, HomeYawDegrees, 0f);

            SnapBuildingToGround(home);
            ScaleHomeToHeight(home, HomeTargetHeightMeters);
            SnapBuildingToGround(home);
            var buildingDir = Path.GetDirectoryName(fbxPath)?.Replace('\\', '/');
            AssetDatabase.Refresh();
            FixOverlayMaterials(home, isHome: true, assetSourceDir: buildingDir, buildingMetaPath: metaAssetPath);

            var dollhouse = home.GetComponent<Viu.Runtime.DollhouseWall>();
            if (dollhouse == null)
                dollhouse = home.AddComponent<Viu.Runtime.DollhouseWall>();
            dollhouse.wallMeshName = LoadDollhouseWallFromMeta(metaAssetPath);
            dollhouse.atHome = false;
            dollhouse.Apply();

            var meshN = home.GetComponentsInChildren<Renderer>(true).Length;
            Debug.Log(
                "[Viu] Дом в overlay: " + fbxPath
                + ", dollhouse_wall=«" + dollhouse.wallMeshName + "»"
                + " (пусто → shell/barn_interior), renderers=" + meshN);
            return home;
        }

        /// <summary>
        /// Standard/Error → magenta void в Player. Материалы сохраняем как ассеты,
        /// иначе new Material() не переживает build. Fallback: URP Unlit дерево.
        /// </summary>
        static void FixOverlayMaterials(
            GameObject root,
            bool isHome = false,
            string assetSourceDir = null,
            string buildingMetaPath = null)
        {
            var lit = Shader.Find("Universal Render Pipeline/Lit")
                ?? Shader.Find("Universal Render Pipeline/Simple Lit");
            var unlit = Shader.Find("Universal Render Pipeline/Unlit")
                ?? Shader.Find("Unlit/Color")
                ?? Shader.Find("Sprites/Default");
            if (lit == null && unlit == null)
            {
                Debug.LogError("[Viu] Нет URP/Unlit шейдеров — дом будет magenta.");
                return;
            }

            string matFolder = isHome ? HomeMatFolder : CharMatFolder;
            EnsureAssetFolder(matFolder);
            var texMap = LoadAssetTextureMap(buildingMetaPath);
            int texBound = 0;

            int fixedN = 0;
            foreach (var r in root.GetComponentsInChildren<Renderer>(true))
            {
                if (r == null) continue;
                var mats = r.sharedMaterials;
                if (mats == null || mats.Length == 0)
                {
                    if (unlit != null)
                    {
                        var c = isHome ? GuessHomeColor(r, null) : new Color(0.45f, 0.32f, 0.22f);
                        var fallback = LoadOrCreateSolidMat(matFolder, "viu_wood", lit ?? unlit, c);
                        r.sharedMaterial = fallback;
                        fixedN++;
                    }
                    continue;
                }

                var changed = false;
                for (int i = 0; i < mats.Length; i++)
                {
                    var m = mats[i];
                    var sn = m != null && m.shader != null ? m.shader.name : "";
                    bool bad = m == null
                        || string.IsNullOrEmpty(sn)
                        || sn.IndexOf("Error", StringComparison.OrdinalIgnoreCase) >= 0
                        || sn.IndexOf("Hidden/InternalErrorShader", StringComparison.OrdinalIgnoreCase) >= 0
                        || sn.IndexOf("Standard", StringComparison.OrdinalIgnoreCase) >= 0
                        || sn.IndexOf("Legacy", StringComparison.OrdinalIgnoreCase) >= 0
                        || (sn.IndexOf("Universal Render Pipeline", StringComparison.OrdinalIgnoreCase) < 0
                            && sn.IndexOf("Unlit", StringComparison.OrdinalIgnoreCase) < 0
                            && sn.IndexOf("Sprites", StringComparison.OrdinalIgnoreCase) < 0);

                    // Только наши сохранённые URP-материалы с albedo — FBX-материалы в Player часто magenta.
                    if (IsViuSavedMaterial(m, matFolder) && HasMeaningfulAlbedo(m)) continue;

                    var shader = lit ?? unlit;
                    var safeName = "viu_" + (m != null ? m.name : "slot" + i);
                    if (isHome)
                        safeName += "_" + r.gameObject.name;
                    safeName = string.Join("_", safeName.Split(System.IO.Path.GetInvalidFileNameChars()));
                    if (safeName.Length > 48) safeName = safeName.Substring(0, 48);
                    var path = matFolder + "/" + safeName + ".mat";

                    Material copy = AssetDatabase.LoadAssetAtPath<Material>(path);
                    bool srcHasTex = m != null && MaterialHasAnyTexture(m);
                    if (copy != null && !HasMeaningfulAlbedo(copy)
                        && TryBindAssetTexture(copy, assetSourceDir, m != null ? m.name : null,
                            r.gameObject.name, i, texMap))
                    {
                        EditorUtility.SetDirty(copy);
                        mats[i] = copy;
                        changed = true;
                        fixedN++;
                        texBound++;
                        continue;
                    }
                    if (copy != null && srcHasTex && !HasMeaningfulAlbedo(copy))
                    {
                        AssetDatabase.DeleteAsset(path);
                        copy = null;
                    }
                    if (copy != null && !HasMeaningfulAlbedo(copy) && !srcHasTex)
                    {
                        AssetDatabase.DeleteAsset(path);
                        copy = null;
                    }

                    if (copy == null)
                    {
                        copy = new Material(shader);
                        bool gotTex = CopyMaterialTexturesFull(m, copy);
                        if (!gotTex)
                            gotTex = TryBindAssetTexture(copy, assetSourceDir, m != null ? m.name : null,
                                r.gameObject.name, i, texMap);
                        if (gotTex) texBound++;
                        Color c = isHome ? GuessHomeColor(r, m) : GuessCharacterColor(r, m);
                        if (m != null)
                        {
                            if (m.HasProperty("_Color")) c = m.GetColor("_Color");
                            else if (m.HasProperty("_BaseColor")) c = m.GetColor("_BaseColor");
                        }
                        if (!gotTex && c.r > 0.9f && c.g > 0.9f && c.b > 0.9f)
                            c = isHome ? GuessHomeColor(r, m) : GuessCharacterColor(r, m);
                        if (copy.HasProperty("_BaseColor")) copy.SetColor("_BaseColor", c);
                        if (copy.HasProperty("_Color")) copy.SetColor("_Color", c);
                        if (copy.HasProperty("_Smoothness"))
                            copy.SetFloat("_Smoothness", gotTex ? 0.25f : 0.15f);
                        AssetDatabase.CreateAsset(copy, path);
                    }
                    mats[i] = copy;
                    changed = true;
                    fixedN++;
                }
                if (changed)
                    r.sharedMaterials = mats;
            }
            AssetDatabase.SaveAssets();
            Debug.Log("[Viu] " + (isHome ? "Дом" : "Шаня") + ": материалов починено/сохранено: " + fixedN
                + ", текстур привязано: " + texBound);
        }

        static Color GuessCharacterColor(Renderer r, Material m)
        {
            var n = (r != null ? r.gameObject.name : "").ToLowerInvariant().Replace("-", "_");
            if (m != null && !string.IsNullOrEmpty(m.name))
                n += " " + m.name.ToLowerInvariant().Replace("-", "_");
            if (n.Contains("boot") || n.Contains("shoe") || n.Contains("gauntlet") || n.Contains("glove")
                || n.Contains("stock") || n.Contains("legging"))
                return new Color(0.12f, 0.10f, 0.09f);
            if (n.Contains("hair") || n.Contains("lash") || n.Contains("brow"))
                return new Color(0.22f, 0.16f, 0.10f);
            if (n.Contains("eye") || n.Contains("iris") || n.Contains("sclera"))
                return new Color(0.85f, 0.88f, 0.92f);
            if (n.Contains("lip") || n.Contains("mouth"))
                return new Color(0.72f, 0.38f, 0.36f);
            if (n.Contains("skin") || n.Contains("body") || n.Contains("head"))
                return new Color(0.82f, 0.66f, 0.56f);
            if (n.Contains("teeth"))
                return new Color(0.92f, 0.90f, 0.86f);
            return new Color(0.55f, 0.48f, 0.42f);
        }

        static Dictionary<string, string> LoadAssetTextureMap(string metaAssetPath)
        {
            var map = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            if (string.IsNullOrEmpty(metaAssetPath))
                return map;
            var full = Path.GetFullPath(Path.Combine(Application.dataPath, "..", metaAssetPath));
            if (!File.Exists(full))
                return map;
            try
            {
                var json = File.ReadAllText(full);
                var meta = JsonUtility.FromJson<ViuBuildingMeta>(json);
                if (meta?.material_texture_list != null)
                {
                    foreach (var e in meta.material_texture_list)
                    {
                        if (e == null || string.IsNullOrWhiteSpace(e.material) || string.IsNullOrWhiteSpace(e.texture))
                            continue;
                        map[e.material.Trim()] = e.texture.Trim().Replace('\\', '/');
                    }
                }
                if (meta?.slot_texture_list != null)
                {
                    foreach (var e in meta.slot_texture_list)
                    {
                        if (e == null || string.IsNullOrWhiteSpace(e.texture))
                            continue;
                        if (!string.IsNullOrWhiteSpace(e.mesh) && !string.IsNullOrWhiteSpace(e.material))
                            map[e.mesh.Trim() + "|" + e.material.Trim()] = e.texture.Trim().Replace('\\', '/');
                    }
                }
            }
            catch (Exception e)
            {
                Debug.LogWarning("[Viu] texture map: " + e.Message);
            }
            return map;
        }

        static bool TryBindAssetTexture(
            Material dst,
            string assetSourceDir,
            string matName,
            string meshName,
            int slotIndex,
            Dictionary<string, string> texMap)
        {
            if (dst == null || string.IsNullOrEmpty(assetSourceDir))
                return false;
            var rel = LookupAssetTexturePath(texMap, matName, meshName, slotIndex);
            if (string.IsNullOrEmpty(rel))
                rel = FuzzyFindAssetTextureRel(assetSourceDir, matName, meshName);
            if (string.IsNullOrEmpty(rel))
                return false;
            rel = rel.Replace('\\', '/');
            var texPath = rel.StartsWith("Assets/", StringComparison.OrdinalIgnoreCase)
                ? rel
                : (rel.Contains("/")
                    ? assetSourceDir + "/" + rel.TrimStart('/')
                    : assetSourceDir + "/Textures/" + Path.GetFileName(rel));
            var tex = AssetDatabase.LoadAssetAtPath<Texture2D>(texPath);
            if (tex == null)
                return false;
            if (dst.HasProperty("_BaseMap")) dst.SetTexture("_BaseMap", tex);
            if (dst.HasProperty("_MainTex")) dst.SetTexture("_MainTex", tex);
            if (dst.HasProperty("_Smoothness")) dst.SetFloat("_Smoothness", 0.25f);
            return true;
        }

        static string LookupAssetTexturePath(
            Dictionary<string, string> texMap,
            string matName,
            string meshName,
            int slotIndex)
        {
            if (texMap == null || texMap.Count == 0)
                return null;
            if (!string.IsNullOrEmpty(meshName) && !string.IsNullOrEmpty(matName)
                && texMap.TryGetValue(meshName + "|" + matName, out var slotExact))
                return slotExact;
            if (!string.IsNullOrEmpty(matName) && texMap.TryGetValue(matName, out var exact))
                return exact;
            var hay = ((matName ?? "") + " " + (meshName ?? "")).ToLowerInvariant().Replace("-", "_");
            string best = null;
            int bestScore = 0;
            foreach (var kv in texMap)
            {
                var key = kv.Key.ToLowerInvariant().Replace("-", "_");
                if (string.IsNullOrEmpty(key)) continue;
                int score = ScoreTextureNameMatch(key, hay, matName, meshName);
                if (score > bestScore)
                {
                    bestScore = score;
                    best = kv.Value;
                }
            }
            return bestScore >= 5 ? best : null;
        }

        static int ScoreTextureNameMatch(string key, string hay, string matName, string meshName)
        {
            int score = 0;
            if (!string.IsNullOrEmpty(matName) && key.Equals(matName, StringComparison.OrdinalIgnoreCase))
                score += 100;
            if (!string.IsNullOrEmpty(meshName) && key.Contains(meshName, StringComparison.OrdinalIgnoreCase))
                score += 50;
            if (hay.Contains(key) || key.Contains(hay.Trim()))
                score += 35;
            foreach (var tok in key.Split(new[] { '_', '.', ' ', '|' }, StringSplitOptions.RemoveEmptyEntries))
            {
                if (tok.Length < 3) continue;
                if (hay.Contains(tok)) score += tok.Length * 2;
            }
            if (!string.IsNullOrEmpty(meshName))
            {
                var meshLow = meshName.ToLowerInvariant().Replace("-", "_");
                foreach (var tok in meshLow.Split(new[] { '_', '.' }, StringSplitOptions.RemoveEmptyEntries))
                {
                    if (tok.Length < 3) continue;
                    if (key.Contains(tok)) score += tok.Length * 3;
                }
            }
            return score;
        }

        static bool IsLikelyAlbedoTexturePath(string path)
        {
            var n = Path.GetFileNameWithoutExtension(path).ToLowerInvariant();
            if (n.Contains("normal") || n.Contains("_nrm") || n.Contains("norm") || n.Contains("bump"))
                return false;
            if (n.Contains("rough") || n.Contains("metal") || n.Contains("_ao") || n.Contains("height"))
                return false;
            if (n.Contains("spec") || n.Contains("gloss") || n.Contains("opacity") && !n.Contains("diff"))
                return false;
            return true;
        }

        static string FuzzyFindAssetTextureRel(string assetSourceDir, string matName, string meshName)
        {
            var folders = new List<string> { assetSourceDir };
            var texFolder = assetSourceDir + "/Textures";
            var matFolder = assetSourceDir + "/Materials";
            if (AssetDatabase.IsValidFolder(texFolder)) folders.Add(texFolder);
            if (AssetDatabase.IsValidFolder(matFolder)) folders.Add(matFolder);
            if (assetSourceDir != null && assetSourceDir.IndexOf("/Characters/", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                var shanyaRoot = "Assets/Characters/Shanya";
                if (AssetDatabase.IsValidFolder(shanyaRoot) && !folders.Contains(shanyaRoot))
                    folders.Add(shanyaRoot);
            }
            var guids = AssetDatabase.FindAssets("t:Texture2D", folders.ToArray());
            if (guids == null || guids.Length == 0)
                return null;
            var hay = ((matName ?? "") + " " + (meshName ?? "")).ToLowerInvariant().Replace("-", "_");
            string best = null;
            int bestScore = 0;
            foreach (var guid in guids)
            {
                var path = AssetDatabase.GUIDToAssetPath(guid).Replace('\\', '/');
                if (!IsLikelyAlbedoTexturePath(path))
                    continue;
                var file = Path.GetFileNameWithoutExtension(path).ToLowerInvariant().Replace("-", "_");
                if (string.IsNullOrEmpty(file)) continue;
                int score = ScoreTextureNameMatch(file, hay, matName, meshName);
                if (path.IndexOf("/Textures/", StringComparison.OrdinalIgnoreCase) >= 0)
                    score += 5;
                if (score > bestScore)
                {
                    bestScore = score;
                    best = path;
                }
            }
            return bestScore >= 5 ? best : null;
        }

        static bool CopyMaterialTextures(Material src, Material dst)
            => CopyMaterialTexturesFull(src, dst);

        static bool CopyMaterialTexturesFull(Material src, Material dst)
        {
            if (src == null || dst == null) return false;
            bool gotTex = false;
            CopyTexProp(src, dst, "_MainTex", "_BaseMap", ref gotTex);
            CopyTexProp(src, dst, "_BaseMap", "_BaseMap", ref gotTex);
            CopyTexProp(src, dst, "_BumpMap", "_BumpMap", ref gotTex);
            CopyTexProp(src, dst, "_NormalMap", "_BumpMap", ref gotTex);
            if (!gotTex && src.mainTexture != null && dst.HasProperty("_BaseMap"))
            {
                dst.SetTexture("_BaseMap", src.mainTexture);
                gotTex = true;
            }
            if (gotTex && src.HasProperty("_MainTex") && dst.HasProperty("_BaseMap"))
            {
                dst.SetTextureScale("_BaseMap", src.GetTextureScale("_MainTex"));
                dst.SetTextureOffset("_BaseMap", src.GetTextureOffset("_MainTex"));
            }
            return gotTex;
        }

        static void CopyTexProp(Material src, Material dst, string srcProp, string dstProp, ref bool got)
        {
            if (!src.HasProperty(srcProp) || !dst.HasProperty(dstProp)) return;
            var t = src.GetTexture(srcProp);
            if (t == null) return;
            dst.SetTexture(dstProp, t);
            got = true;
        }

        static bool MaterialHasAnyTexture(Material m)
        {
            if (m == null) return false;
            if (HasMeaningfulTexture(m)) return true;
            if (m.mainTexture != null) return true;
            if (m.HasProperty("_MainTex") && m.GetTexture("_MainTex") != null) return true;
            return false;
        }

        static Color GuessHomeColor(Renderer r, Material m)
        {
            var n = (r != null ? r.gameObject.name : "").ToLowerInvariant().Replace("-", "_");
            if (m != null && !string.IsNullOrEmpty(m.name))
                n += " " + m.name.ToLowerInvariant().Replace("-", "_");
            if (n.Contains("thatch") || n.Contains("roof") || n.Contains("reed"))
                return new Color(0.62f, 0.48f, 0.28f);
            if (n.Contains("beam") || n.Contains("wood") || n.Contains("plank") || n.Contains("timber"))
                return new Color(0.42f, 0.28f, 0.16f);
            if (n.Contains("door") || n.Contains("window") || n.Contains("frame"))
                return new Color(0.35f, 0.24f, 0.14f);
            if (n.Contains("stone") || n.Contains("rock"))
                return new Color(0.55f, 0.52f, 0.48f);
            if (n.Contains("wall") || n.Contains("plaster") || n.Contains("facade"))
                return new Color(0.72f, 0.66f, 0.56f);
            if (n.Contains("interior") || n.Contains("floor"))
                return new Color(0.48f, 0.36f, 0.26f);
            return new Color(0.58f, 0.50f, 0.40f);
        }

        static bool IsViuSavedMaterial(Material m, string matFolder)
        {
            if (m == null || string.IsNullOrEmpty(matFolder)) return false;
            var path = AssetDatabase.GetAssetPath(m);
            if (string.IsNullOrEmpty(path)) return false;
            return path.Replace('\\', '/').StartsWith(matFolder + "/", StringComparison.OrdinalIgnoreCase);
        }

        static bool HasMeaningfulAlbedo(Material m)
        {
            if (m == null) return false;
            Texture tex = null;
            if (m.HasProperty("_BaseMap")) tex = m.GetTexture("_BaseMap");
            if (tex == null && m.HasProperty("_MainTex")) tex = m.GetTexture("_MainTex");
            if (tex == null) return false;
            var path = AssetDatabase.GetAssetPath(tex);
            if (string.IsNullOrEmpty(path)) return false;
            return IsLikelyAlbedoTexturePath(path);
        }

        static bool HasMeaningfulTexture(Material m)
        {
            if (m == null) return false;
            if (m.HasProperty("_BaseMap") && m.GetTexture("_BaseMap") != null) return true;
            if (m.HasProperty("_MainTex") && m.GetTexture("_MainTex") != null) return true;
            return false;
        }

        static Material LoadOrCreateSolidMat(string folder, string name, Shader shader, Color color)
        {
            var path = folder + "/" + name + ".mat";
            var mat = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (mat != null) return mat;
            mat = new Material(shader);
            if (mat.HasProperty("_BaseColor")) mat.SetColor("_BaseColor", color);
            if (mat.HasProperty("_Color")) mat.SetColor("_Color", color);
            AssetDatabase.CreateAsset(mat, path);
            return mat;
        }

        static void EnsureAssetFolder(string assetPath)
        {
            if (AssetDatabase.IsValidFolder(assetPath)) return;
            var parts = assetPath.Split('/');
            var cur = parts[0];
            for (int i = 1; i < parts.Length; i++)
            {
                var next = cur + "/" + parts[i];
                if (!AssetDatabase.IsValidFolder(next))
                    AssetDatabase.CreateFolder(cur, parts[i]);
                cur = next;
            }
        }

        static void ScaleHomeToHeight(GameObject root, float targetHeight)
        {
            // Сброс кривого scale от прошлых прогонов
            root.transform.localScale = Vector3.one;
            var bounds = ComputeWorldBounds(root);
            if (bounds.size.y < 0.05f) return;
            float factor = targetHeight / bounds.size.y;
            if (factor < 0.001f || factor > 500f) return;
            root.transform.localScale = Vector3.one * factor;
        }

        static bool TryFindHomeFbx(out string fbxPath, out string metaAssetPath)
        {
            fbxPath = null;
            metaAssetPath = null;
            if (!AssetDatabase.IsValidFolder(EnvironmentRoot))
                return false;

            var candidates = new List<(int score, string fbx, string meta)>();
            foreach (var guid in AssetDatabase.FindAssets("t:Model", new[] { EnvironmentRoot }))
            {
                var path = AssetDatabase.GUIDToAssetPath(guid);
                if (!path.EndsWith(".fbx", StringComparison.OrdinalIgnoreCase))
                    continue;

                var dir = Path.GetDirectoryName(path)?.Replace('\\', '/') ?? "";
                var slug = Path.GetFileName(dir);
                var meta = dir + "/" + slug + ".viu.json";

                var score = 0;
                if (slug.IndexOf("Stables", StringComparison.OrdinalIgnoreCase) >= 0) score += 10;
                if (slug.IndexOf("Old", StringComparison.OrdinalIgnoreCase) >= 0) score += 5;
                var metaFull = Path.GetFullPath(Path.Combine(Application.dataPath, "..", meta));
                if (File.Exists(metaFull))
                {
                    score += 3;
                    try
                    {
                        var wall = LoadDollhouseWallFromMeta(meta);
                        if (!string.IsNullOrWhiteSpace(wall))
                            score += 40; // есть вырез фасада
                        else
                            score -= 15; // Old_Stables без Wall_front
                    }
                    catch { /* ignore */ }
                }
                if (slug.EndsWith("_2", StringComparison.OrdinalIgnoreCase)) score += 2;

                candidates.Add((score, path, meta));
            }

            if (candidates.Count == 0)
                return false;

            candidates.Sort((a, b) => b.score.CompareTo(a.score));
            fbxPath = candidates[0].fbx;
            metaAssetPath = candidates[0].meta;
            return true;
        }

        static void EnsureStandardMaterialImport(string assetPath)
        {
            var importer = AssetImporter.GetAtPath(assetPath) as ModelImporter;
            if (importer == null) return;

            var changed = false;
            if (importer.importAnimation && !assetPath.Contains("/Characters/", StringComparison.OrdinalIgnoreCase))
            {
                importer.importAnimation = false;
                changed = true;
            }
            if (assetPath.Contains("/Environment/", StringComparison.OrdinalIgnoreCase))
            {
                if (importer.importAnimation)
                {
                    importer.importAnimation = false;
                    changed = true;
                }
                if (importer.animationType != ModelImporterAnimationType.None)
                {
                    importer.animationType = ModelImporterAnimationType.None;
                    changed = true;
                }
            }
            if (importer.materialImportMode != ModelImporterMaterialImportMode.ImportStandard)
            {
                importer.materialImportMode = ModelImporterMaterialImportMode.ImportStandard;
                changed = true;
            }
            if (importer.materialLocation != ModelImporterMaterialLocation.External)
            {
                importer.materialLocation = ModelImporterMaterialLocation.External;
                changed = true;
            }
            if (changed)
                importer.SaveAndReimport();
        }

        static void EnsureBuildingImport(string assetPath) => EnsureStandardMaterialImport(assetPath);

        [Serializable]
        class ViuMaterialTextureEntry
        {
            public string material;
            public string texture;
        }

        [Serializable]
        class ViuSlotTextureEntry
        {
            public string mesh;
            public string material;
            public int slot;
            public string texture;
        }

        [Serializable]
        class ViuBuildingMeta
        {
            public string dollhouse_wall;
            public ViuMaterialTextureEntry[] material_texture_list;
            public ViuSlotTextureEntry[] slot_texture_list;
        }

        static string LoadDollhouseWallFromMeta(string metaAssetPath)
        {
            // Пустая строка = нет выреза (Old_Stables). Не подставлять фейковый Wall_front.
            if (string.IsNullOrEmpty(metaAssetPath))
                return "";

            var full = Path.GetFullPath(Path.Combine(Application.dataPath, "..", metaAssetPath));
            if (!File.Exists(full))
                return "";

            try
            {
                var json = File.ReadAllText(full);
                var meta = JsonUtility.FromJson<ViuBuildingMeta>(json);
                if (!string.IsNullOrWhiteSpace(meta?.dollhouse_wall))
                    return meta.dollhouse_wall.Trim();
            }
            catch (Exception e)
            {
                Debug.LogWarning("[Viu] viu.json дома: " + e.Message);
            }

            return "";
        }

        static void SnapBuildingToGround(GameObject root)
        {
            var bounds = ComputeWorldBounds(root);
            if (bounds.size.sqrMagnitude < 0.0001f)
                return;

            var pos = root.transform.position;
            pos.y -= bounds.min.y;
            root.transform.position = pos;
        }

        static void PositionHomeAndShanyaInCorridor(GameObject shanya, GameObject home)
        {
            var bounds = ComputeWorldBounds(home);
            if (bounds.size.sqrMagnitude < 0.0001f)
                return;

            // Сарай — дальняя «стенка» коридора (фасад к камере).
            var hpos = home.transform.position;
            hpos.z += CorridorFarWallZ - bounds.min.z;
            home.transform.position = hpos;
            bounds = ComputeWorldBounds(home);

            var pos = shanya.transform.position;
            pos.x = bounds.center.x;
            pos.z = CorridorStartZ;
            shanya.transform.position = pos;
            SnapFeetToGround(shanya);
            LiftFeet(shanya, FeetLiftMeters);
            Debug.Log("[Viu] Коридор: Шаня z=" + pos.z.ToString("F2")
                + " → сарай фасад min.z=" + bounds.min.z.ToString("F2"));
        }

        static void PositionShanyaInHome(GameObject shanya, GameObject home)
        {
            PositionHomeAndShanyaInCorridor(shanya, home);
        }

        static Bounds ComputeWorldBounds(GameObject root)
        {
            var renderers = root.GetComponentsInChildren<Renderer>();
            if (renderers.Length == 0)
                return new Bounds(root.transform.position, Vector3.zero);

            var bounds = renderers[0].bounds;
            for (int i = 1; i < renderers.Length; i++)
                bounds.Encapsulate(renderers[i].bounds);
            return bounds;
        }
    }
}
#endif
