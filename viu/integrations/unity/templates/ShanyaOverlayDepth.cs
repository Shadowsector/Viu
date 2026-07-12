using System;
using System.IO;
using UnityEngine;

namespace Viu.Runtime
{
    /// <summary>
    /// W/S — Шаня ходит вглубь/к камере по Z. Дом и ortho камеры не трогаем
    /// (раньше depthBlend зумил и дом, и Шаню — это не то).
    /// F5 — сохранить Z в overlay_tune.json.
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

        public float depthMoveSpeed = 1.35f;
        public float minDepthZ = -2.5f;
        public float maxDepthZ = 3.5f;

        /// <summary>Камера: фиксированный «taskbar» кадр, без зума от W/S.</summary>
        public LaneSettings taskbar = new LaneSettings
        {
            distanceZ = 14f,
            orthoHalfHeight = 2.15f,
        };

        public float feetLiftMeters = 0.02f;

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
            _character = _follow != null ? _follow.target : null;
            LoadTuneFile();
            CaptureBase();
            ApplyCameraLane();
            ApplyCharacterDepth();
            Debug.Log("[Viu] Глубина: W/S — Шаня ближе/дальше по Z (дом стоит). F5 — сохранить.");
        }

        void Update()
        {
            float dir = 0f;
            if (Input.GetKey(KeyCode.W) || Input.GetKey(KeyCode.UpArrow)) dir -= 1f; // к камере / «подойти»
            if (Input.GetKey(KeyCode.S) || Input.GetKey(KeyCode.DownArrow)) dir += 1f; // вглубь
            if (Mathf.Abs(dir) > 0.01f)
            {
                characterDepthZ = Mathf.Clamp(
                    characterDepthZ + dir * depthMoveSpeed * Time.deltaTime,
                    minDepthZ,
                    maxDepthZ);
                ApplyCharacterDepth();
            }

            if (Input.GetKeyDown(KeyCode.F5))
                SaveTuneFile();
        }

        /// <summary>Старый API playtest/tune — больше не зумит, только сдвигает Z.</summary>
        public void SetDepthBlend(float blend)
        {
            // 0 = далеко (taskbar), 1 = близко → отрицательный Z
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
            p.y = _baseFeetY + feetLiftMeters;
            _character.position = p;
        }

        string TunePath()
        {
            // Рядом с exe в билде; в Editor — корень проекта
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
                // Старый depthBlend → характер Z; новый characterDepthZ — напрямую
                if (Mathf.Abs(data.characterDepthZ) > 0.001f)
                    characterDepthZ = data.characterDepthZ;
                else if (data.depthBlend > 0.001f)
                    characterDepthZ = Mathf.Lerp(1.2f, minDepthZ, data.depthBlend);
                if (data.feetLiftMeters > 0f)
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
