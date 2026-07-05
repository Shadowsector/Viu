#if UNITY_EDITOR
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;

namespace Viu.Editor
{
    /// <summary>
    /// Автонастройка Шани: Animator Controller, Idle-клип, отключение WGT-виджетов.
    /// Меню: Viu → Setup Shanya (Idle). Batchmode: Viu.Editor.ShanyaSetup.RunBatch
    /// </summary>
    public static class ShanyaSetup
    {
        const string ControllerPath = "Assets/Characters/Shanya/Shanya_Idle_Stand.controller";
        const string ModelNameHint = "Shanya_Erisa";
        const string IdleNameHint = "Idle";

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

            var idlePath = FindIdleClipPath();
            if (string.IsNullOrEmpty(idlePath))
            {
                Debug.LogError("[Viu] Mixamo Idle не найден (ищу *Idle*). Импортируй X Bot@Idle.fbx.");
                return;
            }

            EnsureHumanoidImport(modelPath);
            if (!string.IsNullOrEmpty(idlePath) && idlePath != modelPath)
                EnsureHumanoidImport(idlePath);

            var controller = BuildController(idlePath);
            var avatar = LoadModelAvatar(modelPath);
            if (avatar == null)
            {
                Debug.LogError("[Viu] Avatar не найден. Открой модель → Rig → Humanoid → Configure → Apply.");
                return;
            }

            var instance = PlaceCharacterInScene(modelPath, controller, avatar);
            DisableWgtMeshes(instance);
            AssetDatabase.SaveAssets();
            Debug.Log("[Viu] Setup готов: " + instance.name + " + " + controller.name);
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

        static string FindIdleClipPath()
        {
            string best = null;
            foreach (var guid in AssetDatabase.FindAssets("t:Model"))
            {
                var path = AssetDatabase.GUIDToAssetPath(guid);
                var name = Path.GetFileNameWithoutExtension(path).ToLowerInvariant();
                if (name.Contains("idle"))
                    return path;
                if (name.Contains("x bot") && best == null)
                    best = path;
            }
            return best;
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

        static AnimatorController BuildController(string idleModelPath)
        {
            var clip = LoadFirstAnimationClip(idleModelPath);
            if (clip == null)
                throw new System.InvalidOperationException("Нет AnimationClip в " + idleModelPath);

            var dir = Path.GetDirectoryName(ControllerPath).Replace('\\', '/');
            EnsureFolder(dir);

            AnimatorController controller;
            if (File.Exists(ControllerPath))
            {
                controller = AssetDatabase.LoadAssetAtPath<AnimatorController>(ControllerPath);
            }
            else
            {
                controller = AnimatorController.CreateAnimatorControllerAtPath(ControllerPath);
            }

            var layer = controller.layers[0];
            var sm = layer.stateMachine;
            foreach (var child in sm.states.ToArray())
                sm.RemoveState(child.state);

            var state = sm.AddState("Idle");
            state.motion = clip;
            sm.defaultState = state;

            EditorUtility.SetDirty(controller);
            return controller;
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

        static AnimationClip LoadFirstAnimationClip(string modelPath)
        {
            var assets = AssetDatabase.LoadAllAssetsAtPath(modelPath);
            return assets.OfType<AnimationClip>().FirstOrDefault(c => !c.name.StartsWith("__preview"));
        }

        static Avatar LoadModelAvatar(string modelPath)
        {
            var assets = AssetDatabase.LoadAllAssetsAtPath(modelPath);
            return assets.OfType<Avatar>().FirstOrDefault();
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
