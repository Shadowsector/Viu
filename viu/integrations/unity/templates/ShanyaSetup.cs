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

        [MenuItem("Viu/Setup Shanya (Idle)")]
        public static void RunMenu() => Run();

        public static void RunBatch()
        {
            Run();
            EditorApplication.Exit(0);
        }

        public static void Run()
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
            EnsureLocomotion(instance);
            DisableWgtMeshes(instance);
            ShanyaOutfit.Apply(ShanyaOutfit.Mode.Dressed);
            AssetDatabase.SaveAssets();
            SaveActiveScene();
            Debug.Log("[Viu] Setup готов: " + instance.name + " + " + controller.name +
                ". Открой сцену и нажми Play.");
        }

        static void SaveActiveScene()
        {
            var scene = SceneManager.GetActiveScene();
            EditorSceneManager.MarkSceneDirty(scene);
            if (string.IsNullOrEmpty(scene.path))
            {
                if (!AssetDatabase.IsValidFolder("Assets/Scenes"))
                    AssetDatabase.CreateFolder("Assets", "Scenes");
                var path = "Assets/Scenes/GameTest.unity";
                EditorSceneManager.SaveScene(scene, path);
                Debug.Log("[Viu] Сцена сохранена: " + path);
            }
            else
            {
                EditorSceneManager.SaveScene(scene);
                Debug.Log("[Viu] Сцена сохранена: " + scene.path);
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
