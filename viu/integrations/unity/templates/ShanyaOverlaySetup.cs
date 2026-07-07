#if UNITY_EDITOR
using System;
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
        // @viu-deploy-rev 10
        const string ScenePath = "Assets/Scenes/OverlayDesktop.unity";
        const string BuildFolder = "Builds/AnabarraOverlay";
        const string BuildExe = "AnabarraOverlay.exe";
        const float TargetHeightMeters = 1.75f;
        const float GroundSinkMeters = 0.03f;
        const float CameraOrthoHalfHeight = 1.15f;

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
            PlayerSettings.defaultScreenHeight = 280;
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
            EnsureOverlayEnvironment(instance);
            SnapFeetToGround(instance);
            EnsureOverlayManager();
            AssetDatabase.SaveAssets();
            SaveActiveScene(saveScenePath);
            Debug.Log("[Viu] Overlay scene готова: " + saveScenePath);
        }

        static void EnsureOverlayManager()
        {
            var root = GameObject.Find("Viu_OverlayRoot");
            if (root == null)
                root = new GameObject("Viu_OverlayRoot");
            if (root.GetComponent<Viu.Runtime.ShanyaDesktopOverlay>() == null)
                root.AddComponent<Viu.Runtime.ShanyaDesktopOverlay>();
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
            follow.viewCenterAboveFeet = 0.95f;
            follow.distanceZ = 10f;
            follow.transform.position = new Vector3(
                target.position.x,
                target.position.y + follow.viewCenterAboveFeet,
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
    }
}
#endif
