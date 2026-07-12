using System;
using System.IO;
using UnityEngine;

namespace Viu.Runtime
{
    /// <summary>
    /// Tune/lane для overlay: ortho камеры, базовый Z, F5 → overlay_tune.json.
    /// W/S движение — в ShanyaLocomotion (Z axis + Walk).
    /// </summary>
    public class ShanyaOverlayDepth : MonoBehaviour
    {
        [Serializable]
        public struct LaneSettings
        {
            public float distanceZ;
            public float orthoHalfHeight;
        }

        /// <summary>Смещение Шани по Z от базовой позиции (отрицательное = ближе к камере).</summary>
        public float characterDepthZ;

        public float minDepthZ = -2.5f;
        public float maxDepthZ = 3.5f;

        public LaneSettings taskbar = new LaneSettings
        {
            distanceZ = 14f,
            orthoHalfHeight = 2.15f,
        };

        public float feetLiftMeters = 0f;

        ShanyaOverlayCamera _follow;
        Camera _camera;
        Transform _character;
        float _baseCharZ;
        float _baseFeetY;
        bool _baseCaptured;

        void Start()
        {
            _follow = Camera.main != null ? Camera.main.GetComponent<ShanyaOverlayCamera>() : null;
            _camera = Camera.main;
            if (_character == null && _follow != null)
                _character = _follow.target;
            LoadTuneFile();
            CaptureBase();
            ApplyCameraLane();
            ApplyCharacterDepth();
            Debug.Log("[Viu] Глубина: W/S — Шаня по Z (Locomotion). F5 — сохранить overlay_tune.json.");
        }

        void Update()
        {
            if (_character == null && _follow != null)
                _character = _follow.target;

            if (Input.GetKeyDown(KeyCode.F5))
                SaveTuneFile();
        }

        public void BindCharacter(Transform character)
        {
            _character = character;
            CaptureBase();
            ApplyCharacterDepth();
        }

        public void SyncDepthFromCharacter(float baseZ, float currentZ)
        {
            _baseCharZ = baseZ;
            characterDepthZ = currentZ - baseZ;
        }

        public void SetDepthBlend(float blend)
        {
            characterDepthZ = Mathf.Lerp(maxDepthZ * 0.35f, minDepthZ, Mathf.Clamp01(blend));
            ApplyCharacterDepth();
        }

        void CaptureBase()
        {
            if (_character == null || _baseCaptured) return;
            _baseCharZ = _character.position.z;
            _baseFeetY = _character.position.y;
            _baseCaptured = true;
        }

        void ApplyCameraLane()
        {
            if (_follow != null)
            {
                _follow.distanceZ = taskbar.distanceZ;
                _follow.depthBlend = 0f;
            }
            if (_camera != null)
                _camera.orthographicSize = taskbar.orthoHalfHeight;
        }

        void ApplyCharacterDepth()
        {
            if (_character == null) return;
            CaptureBase();
            var p = _character.position;
            p.z = _baseCharZ + characterDepthZ;
            if (feetLiftMeters > 0f)
                p.y = _baseFeetY + feetLiftMeters;
            _character.position = p;
        }

        string TunePath()
        {
            var dir = Application.isEditor
                ? Path.GetFullPath(Path.Combine(Application.dataPath, ".."))
                : Path.GetFullPath(Path.Combine(Application.dataPath, ".."));
            var buildTune = Path.Combine(
                Path.GetFullPath(Path.Combine(Application.dataPath, "..", "Builds", "AnabarraOverlay")),
                "overlay_tune.json");
            if (!Application.isEditor && File.Exists(Path.Combine(dir, "overlay_tune.json")))
                return Path.Combine(dir, "overlay_tune.json");
            if (File.Exists(buildTune))
                return buildTune;
            return Path.Combine(dir, "overlay_tune.json");
        }

        public void LoadTuneFile()
        {
            var path = TunePath();
            if (!File.Exists(path)) return;
            try
            {
                var json = File.ReadAllText(path);
                var data = JsonUtility.FromJson<TuneFile>(json);
                if (data == null) return;
                if (data.taskbar.distanceZ > 0.1f)
                    taskbar = data.taskbar;
                if (Mathf.Abs(data.characterDepthZ) > 0.001f)
                    characterDepthZ = data.characterDepthZ;
                else if (data.depthBlend > 0.001f)
                    characterDepthZ = Mathf.Lerp(1.2f, minDepthZ, data.depthBlend);
                if (data.feetLiftMeters >= 0f)
                    feetLiftMeters = data.feetLiftMeters;
            }
            catch (Exception e)
            {
                Debug.LogWarning("[Viu] overlay_tune.json: " + e.Message);
            }
        }

        void SaveTuneFile()
        {
            try
            {
                if (_character != null && _baseCaptured)
                    characterDepthZ = _character.position.z - _baseCharZ;

                var data = new TuneFile
                {
                    feetLiftMeters = feetLiftMeters,
                    characterDepthZ = characterDepthZ,
                    depthBlend = 0f,
                    activeLane = "taskbar",
                    taskbar = taskbar,
                    attention = taskbar,
                };
                var path = TunePath();
                File.WriteAllText(path, JsonUtility.ToJson(data, true));
                Debug.Log("[Viu] Сохранено overlay_tune.json (characterDepthZ=" + characterDepthZ.ToString("F2") + ")");
            }
            catch (Exception e)
            {
                Debug.LogWarning("[Viu] overlay_tune.json: " + e.Message);
            }
        }

        [Serializable]
        class TuneFile
        {
            public float feetLiftMeters;
            public float characterDepthZ;
            public float depthBlend;
            public string activeLane;
            public LaneSettings taskbar;
            public LaneSettings attention;
        }
    }
}
