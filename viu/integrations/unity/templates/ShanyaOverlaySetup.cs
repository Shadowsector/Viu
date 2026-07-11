#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
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
        // @viu-deploy-rev 16
        const string ScenePath = "Assets/Scenes/OverlayDesktop.unity";
        const string BuildFolder = "Builds/AnabarraOverlay";
        const string BuildExe = "AnabarraOverlay.exe";
        const string EnvironmentRoot = "Assets/Environment";
        const float TargetHeightMeters = 1.77f;
        const float GroundSinkMeters = 0.03f;
        const float FeetLiftMeters = 0.006f;
        const float CameraOrthoHalfHeight = 5.5f;
        const float HomeShanyaZBias = 0.18f;

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
                Debug.Log("[Viu] Overlay build OK: " + report.summary.outputPath);
            else
                throw new InvalidOperationException(
                    "Overlay build failed: " + report.summary.result + " — см. Console.");
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
        }

        static void EnsureBuildFolder()
        {
            if (!AssetDatabase.IsValidFolder("Assets/Builds"))
                AssetDatabase.CreateFolder("Assets", "Builds");
            var full = Path.Combine(Application.dataPath, "..", BuildFolder);
            Directory.CreateDirectory(full);
        }

        public static void Run(string saveScenePath)
        {
            var modelPath = FindModelPath();
            if (string.IsNullOrEmpty(modelPath))
            {
                Debug.LogError("[Viu] FBX модели не найден. Сначала GameTest или импорт Shanya_Erisa.");
                return;
            }

            EnsureHumanoidImport(modelPath);
            ShanyaAnimationSync.SyncAll(log: false);

            var controller = AssetDatabase.LoadAssetAtPath<RuntimeAnimatorController>(
                ShanyaAnimationSync.ControllerPath);
            if (controller == null)
            {
                Debug.LogError("[Viu] Animator не создан. Положи Idle/Walk в Animations/.");
                return;
            }

            var avatar = LoadModelAvatar(modelPath);
            if (avatar == null)
            {
                Debug.LogError("[Viu] Avatar не найден на модели.");
                return;
            }

            var instance = PlaceCharacterInScene(modelPath, controller, avatar);
            DisableWgtMeshes(instance);
            try { ShanyaOutfit.Apply(ShanyaOutfit.Mode.Dressed); }
            catch (Exception e) { Debug.LogWarning("[Viu] Outfit: " + e.Message); }
            EnsureLocomotion(instance);
            var home = EnsureHomeBuilding();
            EnsureOverlayEnvironment(instance);
            SnapFeetToGround(instance);
            LiftFeet(instance, FeetLiftMeters);
            if (home != null)
                PositionShanyaInHome(instance, home);
            EnsureOverlayManager();
            AssetDatabase.SaveAssets();
            SaveActiveScene(saveScenePath);
            var homeNote = home != null ? " + дом" : "";
            Debug.Log("[Viu] Overlay scene готова" + homeNote + ": " + saveScenePath);
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
            RenderSettings.ambientLight = new Color(0.92f, 0.92f, 0.92f);
            EnsureInvisibleFloor();
            EnsureLighting();
            ScaleToHeight(shanya, TargetHeightMeters);
            EnsureOverlayCamera(shanya.transform);
        }

        static void EnsureInvisibleFloor()
        {
            var floor = GameObject.Find("Viu_Floor");
            if (floor == null)
            {
                floor = GameObject.CreatePrimitive(PrimitiveType.Plane);
                floor.name = "Viu_Floor";
                floor.transform.position = Vector3.zero;
                floor.transform.localScale = new Vector3(4f, 1f, 1f);
            }
            foreach (var r in floor.GetComponentsInChildren<Renderer>())
                r.enabled = false;
        }

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
            follow.feetScreenFraction = 0.06f;
            follow.distanceZ = 14f;
            follow.transform.position = new Vector3(
                target.position.x,
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

        static string FindModelPath()
        {
            foreach (var guid in AssetDatabase.FindAssets("t:Model"))
            {
                var path = AssetDatabase.GUIDToAssetPath(guid);
                var name = Path.GetFileNameWithoutExtension(path).ToLowerInvariant();
                if ((name.Contains("shanya") || name.Contains("erisa"))
                    && !name.Contains("idle") && !name.Contains("walk"))
                    return path;
            }
            return null;
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
            if (light == null) return;
            light.type = LightType.Directional;
            light.transform.rotation = Quaternion.Euler(50f, -30f, 0f);
            light.intensity = 1.1f;
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
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(modelPath);
            var existing = GameObject.Find(prefab != null ? prefab.name : "Shanya_Erisa");
            GameObject instance;
            if (existing != null)
                instance = existing;
            else
            {
                instance = (GameObject)PrefabUtility.InstantiatePrefab(prefab);
                instance.name = prefab.name;
                instance.transform.position = Vector3.zero;
            }
            var animator = instance.GetComponent<Animator>() ?? instance.AddComponent<Animator>();
            animator.runtimeAnimatorController = controller;
            animator.avatar = avatar;
            if (!instance.activeInHierarchy)
                instance.SetActive(true);
            return instance;
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

            EnsureBuildingImport(fbxPath);

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
                home.transform.rotation = Quaternion.identity;
            }

            SnapBuildingToGround(home);

            var dollhouse = home.GetComponent<Viu.Runtime.DollhouseWall>();
            if (dollhouse == null)
                dollhouse = home.AddComponent<Viu.Runtime.DollhouseWall>();
            dollhouse.wallMeshName = LoadDollhouseWallFromMeta(metaAssetPath);
            dollhouse.atHome = true;
            dollhouse.Apply();

            Debug.Log("[Viu] Дом в overlay: " + fbxPath + ", стенка «" + dollhouse.wallMeshName + "» скрыта.");
            return home;
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
                if (File.Exists(Path.GetFullPath(Path.Combine(Application.dataPath, "..", meta))))
                    score += 3;

                candidates.Add((score, path, meta));
            }

            if (candidates.Count == 0)
                return false;

            candidates.Sort((a, b) => b.score.CompareTo(a.score));
            fbxPath = candidates[0].fbx;
            metaAssetPath = candidates[0].meta;
            return true;
        }

        static void EnsureBuildingImport(string assetPath)
        {
            var importer = AssetImporter.GetAtPath(assetPath) as ModelImporter;
            if (importer == null) return;

            var changed = false;
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
            if (changed)
                importer.SaveAndReimport();
        }

        [Serializable]
        class ViuBuildingMeta
        {
            public string dollhouse_wall;
        }

        static string LoadDollhouseWallFromMeta(string metaAssetPath)
        {
            if (string.IsNullOrEmpty(metaAssetPath))
                return "Wall_front";

            var full = Path.GetFullPath(Path.Combine(Application.dataPath, "..", metaAssetPath));
            if (!File.Exists(full))
                return "Wall_front";

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

            return "Wall_front";
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

        static void PositionShanyaInHome(GameObject shanya, GameObject home)
        {
            var bounds = ComputeWorldBounds(home);
            if (bounds.size.sqrMagnitude < 0.0001f)
                return;

            var pos = shanya.transform.position;
            pos.x = bounds.center.x;
            pos.z = bounds.center.z + bounds.extents.z * HomeShanyaZBias;
            shanya.transform.position = pos;
            SnapFeetToGround(shanya);
            LiftFeet(shanya, FeetLiftMeters);
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
