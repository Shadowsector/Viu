using System;
using System.IO;
using UnityEngine;

namespace Viu.Runtime
{
    /// <summary>
    /// Глубина коридора: S — отойти, W — подойти. F5 — сохранить overlay_tune.json.
    /// </summary>
    public class ShanyaOverlayDepth : MonoBehaviour
    {
        [Serializable]
        public struct LaneSettings
        {
            public float distanceZ;
            public float orthoHalfHeight;
        }

        [Range(0f, 1f)]
        public float depthBlend;

        public LaneSettings taskbar = new LaneSettings
        {
            distanceZ = 14f,
            orthoHalfHeight = 5.5f,
        };

        public LaneSettings attention = new LaneSettings
        {
            distanceZ = 4.5f,
            orthoHalfHeight = 0.95f,
        };

        public float depthMoveSpeed = 0.55f;
        public float feetLiftMeters = 0.006f;

        float _smoothBlend;
        ShanyaOverlayCamera _follow;
        Camera _camera;
        Transform _character;
        float _baseFeetY;
        bool _baseFeetCaptured;

        void Start()
        {
            _follow = Camera.main != null ? Camera.main.GetComponent<ShanyaOverlayCamera>() : null;
            _camera = Camera.main;
            _character = _follow != null ? _follow.target : null;
            LoadTuneFile();
            _smoothBlend = depthBlend;
            ApplyForBlend(_smoothBlend);
            Debug.Log("[Viu] Глубина: S — отойти, W — подойти, F5 — сохранить overlay_tune.json");
        }

        void Update()
        {
            float dir = 0f;
            if (Input.GetKey(KeyCode.W) || Input.GetKey(KeyCode.UpArrow)) dir += 1f;
            if (Input.GetKey(KeyCode.S) || Input.GetKey(KeyCode.DownArrow)) dir -= 1f;
            if (Mathf.Abs(dir) > 0.01f)
                depthBlend = Mathf.Clamp01(depthBlend + dir * depthMoveSpeed * Time.deltaTime);

            if (Input.GetKeyDown(KeyCode.F5))
                SaveTuneFile();

            _smoothBlend = Mathf.MoveTowards(_smoothBlend, depthBlend, depthMoveSpeed * 1.8f * Time.deltaTime);
            ApplyForBlend(_smoothBlend);
        }

        public void SetDepthBlend(float blend)
        {
            depthBlend = Mathf.Clamp01(blend);
            _smoothBlend = depthBlend;
            ApplyForBlend(_smoothBlend);
        }

        void ApplyForBlend(float t)
        {
            var s = Evaluate(t);
            if (_follow != null)
            {
                _follow.distanceZ = s.distanceZ;
                _follow.depthBlend = t;
            }
            if (_camera != null)
                _camera.orthographicSize = s.orthoHalfHeight;
            ApplyFeetLift();
        }

        LaneSettings Evaluate(float t)
        {
            return new LaneSettings
            {
                distanceZ = Mathf.Lerp(taskbar.distanceZ, attention.distanceZ, t),
                orthoHalfHeight = Mathf.Lerp(taskbar.orthoHalfHeight, attention.orthoHalfHeight, t),
            };
        }

        void ApplyFeetLift()
        {
            if (_character == null || feetLiftMeters <= 0f) return;
            if (!_baseFeetCaptured)
            {
                _baseFeetY = _character.position.y;
                _baseFeetCaptured = true;
            }
            var p = _character.position;
            p.y = _baseFeetY + feetLiftMeters;
            _character.position = p;
        }

        string TunePath()
        {
            var dir = Path.GetFullPath(Path.Combine(Application.dataPath, ".."));
            return Path.Combine(dir, "overlay_tune.json");
        }

        public void LoadTuneFile()
        {
            var path = TunePath();
            if (!File.Exists(path)) return;
            try
            {
                var json = File.ReadAllText(path);
                var tune = JsonUtility.FromJson<OverlayTuneData>(json);
                if (tune == null) return;
                if (tune.taskbar != null) taskbar = tune.taskbar.ToSettings();
                if (tune.attention != null) attention = tune.attention.ToSettings();
                feetLiftMeters = tune.feetLiftMeters > 0f ? tune.feetLiftMeters : feetLiftMeters;
                if (tune.depthBlend >= 0f)
                    depthBlend = Mathf.Clamp01(tune.depthBlend);
                else if (string.Equals(tune.activeLane, "attention", StringComparison.OrdinalIgnoreCase))
                    depthBlend = 1f;
            }
            catch (Exception e)
            {
                Debug.LogWarning("[Viu] overlay_tune.json: " + e.Message);
            }
        }

        public void SaveTuneFile()
        {
            if (_follow == null || _camera == null) return;
            var live = new LaneSettings
            {
                distanceZ = _follow.distanceZ,
                orthoHalfHeight = _camera.orthographicSize,
            };
            if (depthBlend < 0.5f)
                taskbar = live;
            else
                attention = live;

            var data = new OverlayTuneData
            {
                feetLiftMeters = feetLiftMeters,
                characterHeightMeters = 1.77f,
                depthBlend = depthBlend,
                activeLane = depthBlend >= 0.5f ? "attention" : "taskbar",
                taskbar = LaneJson.From(taskbar),
                attention = LaneJson.From(attention),
            };
            try
            {
                File.WriteAllText(TunePath(), JsonUtility.ToJson(data, true));
                Debug.Log("[Viu] Сохранено overlay_tune.json (depth=" + depthBlend.ToString("F2") + ")");
            }
            catch (Exception e)
            {
                Debug.LogWarning("[Viu] overlay_tune.json: " + e.Message);
            }
        }

        [Serializable]
        class OverlayTuneData
        {
            public float feetLiftMeters;
            public float characterHeightMeters;
            public float depthBlend = -1f;
            public string activeLane = "taskbar";
            public LaneJson taskbar;
            public LaneJson attention;
        }

        [Serializable]
        class LaneJson
        {
            public float distanceZ;
            public float orthoHalfHeight;
            public float viewCenterAboveFeet;

            public LaneSettings ToSettings() => new LaneSettings
            {
                distanceZ = distanceZ,
                orthoHalfHeight = orthoHalfHeight,
            };

            public static LaneJson From(LaneSettings s) => new LaneJson
            {
                distanceZ = s.distanceZ,
                orthoHalfHeight = s.orthoHalfHeight,
            };
        }
    }
}
