#if UNITY_EDITOR
using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Animations;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace Viu.Editor
{
    /// <summary>
    /// Автонастройка Шани: Animator Controller, Idle-клип, отключение WGT-виджетов.
    /// Меню: Viu → Setup Shanya (Idle). Batchmode: Viu.Editor.ShanyaSetup.RunBatch
    /// </summary>
    public static class ShanyaSetup
    {
        // @viu-deploy-rev 13
        const string ControllerPath = ShanyaAnimationSync.ControllerPath;
        const string ModelNameHint = "Shanya_Erisa";
        /// <summary>Целевой рост персонажа в метрах (можно подкрутить).</summary>
        const float TargetHeightMeters = 1.75f;
        const float GroundSinkMeters = 0.03f;
        /// <summary>Половина высоты кадра в метрах (2*size = видимая высота мира).</summary>
        const float CameraOrthoHalfHeight = 5.5f;

        const string ScenePath = "Assets/Scenes/GameTest.unity";

        [MenuItem("Viu/Setup Shanya (Idle)")]
        public static void RunMenu() => Run(null);

        public static void RunBatch()
        {
            int code = 0;
            try
            {
                // В пакетном режиме готовим отдельную сцену GameTest, чтобы результат
                // было видно при открытии редактора, а не пустой Untitled.
                if (File.Exists(ScenePath))
                    EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
                else
                    EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects, NewSceneMode.Single);
                Run(ScenePath);
            }
            catch (Exception e)
            {
                Debug.LogError("[Viu] Setup (batch) не удался: " + e.Message + "\n" + e.StackTrace);
                code = 1;
            }
            EditorApplication.Exit(code);
        }

        public static void Run(string saveScenePath)
        {
            var modelPath = FindModelPath();
            if (string.IsNullOrEmpty(modelPath))
            {
                Debug.LogError("[Viu] FBX модели не найден (ищу *Shanya* / *Erisa*). Положи FBX в Assets/.");
                return;
            }

            var idlePath = FindIdleInAnimationsFolder();
            if (string.IsNullOrEmpty(idlePath))
            {
                Debug.LogWarning("[Viu] Idle не найден в " + ShanyaAnimationSync.AnimationsFolder +
                    " — положи X Bot@Idle.fbx туда.");
            }

            EnsureHumanoidImport(modelPath);
            ShanyaAnimationSync.SyncAll(log: false);

            var controller = AssetDatabase.LoadAssetAtPath<AnimatorController>(
                ShanyaAnimationSync.ControllerPath);
            if (controller == null)
            {
                Debug.LogError("[Viu] Animator не создан. Положи FBX в " + ShanyaAnimationSync.AnimationsFolder);
                return;
            }

            var avatar = LoadModelAvatar(modelPath);
            if (avatar == null)
            {
                Debug.LogError("[Viu] Avatar не найден. Открой модель → Rig → Humanoid → Configure → Apply.");
                return;
            }

            var instance = PlaceCharacterInScene(modelPath, controller, avatar);
            DisableWgtMeshes(instance);
            try { ShanyaOutfit.Apply(ShanyaOutfit.Mode.Dressed); }
            catch (Exception e) { Debug.LogWarning("[Viu] Outfit пропущен: " + e.Message); }
            EnsureLocomotion(instance);
            EnsureTestSceneEnvironment(instance);
            SnapFeetToGround(instance);
            AssetDatabase.SaveAssets();
            SaveActiveScene(saveScenePath);
            Debug.Log("[Viu] Setup готов: " + instance.name + " + " + controller.name +
                ". Сцена: " + (saveScenePath ?? "текущая") + ". Открой её и нажми Play.");
        }

        static void SaveActiveScene(string saveScenePath)
        {
            var scene = SceneManager.GetActiveScene();
            EditorSceneManager.MarkSceneDirty(scene);
            var path = saveScenePath;
            if (string.IsNullOrEmpty(path))
                path = scene.path;
            if (string.IsNullOrEmpty(path))
                path = ScenePath;

            var dir = Path.GetDirectoryName(path).Replace('\\', '/');
            if (!string.IsNullOrEmpty(dir) && !AssetDatabase.IsValidFolder(dir))
                AssetDatabase.CreateFolder("Assets", "Scenes");

            EditorSceneManager.SaveScene(scene, path);
            Debug.Log("[Viu] Сцена сохранена: " + path);
        }

        static string FindModelPath()
        {
            foreach (var guid in AssetDatabase.FindAssets("t:Model"))
            {
                var path = AssetDatabase.GUIDToAssetPath(guid);
                var name = Path.GetFileNameWithoutExtension(path).ToLowerInvariant();
                if (name.Contains("shanya") || name.Contains("erisa"))
                    if (!name.Contains("idle") && !name.Contains("walk"))
                        return path;
            }
            return null;
        }

        static string FindIdleInAnimationsFolder()
        {
            foreach (var guid in AssetDatabase.FindAssets("t:Model", new[] { ShanyaAnimationSync.AnimationsFolder }))
            {
                var path = AssetDatabase.GUIDToAssetPath(guid);
                if (!path.EndsWith(".fbx", StringComparison.OrdinalIgnoreCase)) continue;
                var name = Path.GetFileNameWithoutExtension(path).ToLowerInvariant();
                if (name.Contains("idle")) return path;
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

        static void EnsureTestSceneEnvironment(GameObject shanya)
        {
            EnsureFloor();
            EnsureLighting();
            ScaleToHeight(shanya, TargetHeightMeters);
            EnsureFollowCamera(shanya.transform);
        }

        static void EnsureFloor()
        {
            if (GameObject.Find("Viu_Floor") != null) return;
            var plane = GameObject.CreatePrimitive(PrimitiveType.Plane);
            plane.name = "Viu_Floor";
            plane.transform.position = Vector3.zero;
            plane.transform.localScale = new Vector3(2f, 1f, 2f);
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
            Debug.Log("[Viu] Рост ~" + targetHeight + " м (scale " + factor.ToString("F2") + ").");
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

        static void EnsureFollowCamera(Transform target)
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
            // Игровой кадр: ~11 м по вертикали — деревья, дома, не только Шаня.
            cam.orthographicSize = CameraOrthoHalfHeight;
            var follow = cam.GetComponent<Viu.Runtime.ShanyaFollowCamera>();
            if (follow == null)
                follow = cam.gameObject.AddComponent<Viu.Runtime.ShanyaFollowCamera>();
            follow.target = target;
            follow.viewCenterAboveFeet = 2.2f;
            follow.distanceZ = 12f;
            follow.transform.position = new Vector3(
                target.position.x,
                target.position.y + follow.viewCenterAboveFeet,
                target.position.z - follow.distanceZ);
            follow.transform.rotation = Quaternion.identity;
        }

        static GameObject PlaceCharacterInScene(string modelPath, RuntimeAnimatorController controller, Avatar avatar)
        {
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(modelPath);
            var existing = GameObject.Find(prefab != null ? prefab.name : ModelNameHint);
            GameObject instance;
            if (existing != null)
            {
                instance = existing;
            }
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
            int n = 0;
            foreach (var t in root.GetComponentsInChildren<Transform>(true))
            {
                if (t.name.StartsWith("WGT") || t.name.StartsWith("WGT."))
                {
                    t.gameObject.SetActive(false);
                    n++;
                }
            }
            if (n > 0)
                Debug.Log("[Viu] Отключено WGT-объектов: " + n);
        }
    }
}
#endif
