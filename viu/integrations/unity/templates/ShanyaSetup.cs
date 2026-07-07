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
        const string ControllerPath = ShanyaAnimationSync.ControllerPath;
        const string ModelNameHint = "Shanya_Erisa";

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
            EnsureInputCompatible();

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
            EnsureLocomotion(instance);
            DisableWgtMeshes(instance);
            try { ShanyaOutfit.Apply(ShanyaOutfit.Mode.Dressed); }
            catch (Exception e) { Debug.LogWarning("[Viu] Outfit пропущен: " + e.Message); }
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

        /// <summary>
        /// Если в Player Settings только Input System — включаем Both,
        /// чтобы ShanyaLocomotion мог читать A/D через legacy Input.
        /// </summary>
        static void EnsureInputCompatible()
        {
            if (PlayerSettings.activeInputHandler == ActiveInputHandler.InputSystemPackage)
            {
                PlayerSettings.activeInputHandler = ActiveInputHandler.Both;
                Debug.Log("[Viu] Input → Both (старый + новый), чтобы ходьба A/D работала без ошибок.");
            }
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
