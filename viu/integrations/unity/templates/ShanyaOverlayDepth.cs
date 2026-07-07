using System;
using System.IO;
using UnityEngine;

namespace Viu.Runtime
{
    /// <summary>
    /// Две «полосы глубины» оверлея: у панели (далеко) и на экран (ближе, для внимания).
    /// [ — в глубину, ] — на экран, F5 — сохранить настройки в overlay_tune.json рядом с exe.
    /// </summary>
    public class ShanyaOverlayDepth : MonoBehaviour
    {
        public enum Lane { Taskbar, Attention }

        [Serializable]
        public struct LaneSettings
        {
            public float viewCenterAboveFeet;
            public float distanceZ;
            public float orthoHalfHeight;
        }

        public LaneSettings taskbar = new LaneSettings
        {
            viewCenterAboveFeet = 1.0f,
            distanceZ = 10f,
            orthoHalfHeight = 1.15f,
        };

        public LaneSettings attention = new LaneSettings
        {
            viewCenterAboveFeet = 1.15f,
            distanceZ = 6f,
            orthoHalfHeight = 0.88f,
        };

        public float blendSpeed = 5f;
        public float feetLiftMeters = 0.005f;

        Lane _targetLane = Lane.Taskbar;
        LaneSettings _current;
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
            _current = LaneSettingsFor(_targetLane);
            ApplyLaneInstant(_current);
            Debug.Log("[Viu] Глубина: [ — у панели, ] — на экран, F5 — сохранить overlay_tune.json");
        }

        void Update()
        {
            if (Input.GetKeyDown(KeyCode.LeftBracket) || Input.GetKeyDown(KeyCode.Q))
                SetLane(Lane.Taskbar);
            if (Input.GetKeyDown(KeyCode.RightBracket) || Input.GetKeyDown(KeyCode.E))
                SetLane(Lane.Attention);
            if (Input.GetKeyDown(KeyCode.F5))
                SaveTuneFile();

            _current.viewCenterAboveFeet = Mathf.Lerp(
                _current.viewCenterAboveFeet, Target().viewCenterAboveFeet, blendSpeed * Time.deltaTime);
            _current.distanceZ = Mathf.Lerp(_current.distanceZ, Target().distanceZ, blendSpeed * Time.deltaTime);
            _current.orthoHalfHeight = Mathf.Lerp(
                _current.orthoHalfHeight, Target().orthoHalfHeight, blendSpeed * Time.deltaTime);

            ApplyLaneInstant(_current);
        }

        public void SetLane(Lane lane)
        {
            _targetLane = lane;
            Debug.Log("[Viu] Глубина → " + (lane == Lane.Taskbar ? "у панели" : "на экран"));
        }

        LaneSettings Target() => LaneSettingsFor(_targetLane);

        LaneSettings LaneSettingsFor(Lane lane) =>
            lane == Lane.Attention ? attention : taskbar;

        void ApplyLaneInstant(LaneSettings s)
        {
            if (_follow != null)
            {
                _follow.viewCenterAboveFeet = s.viewCenterAboveFeet;
                _follow.distanceZ = s.distanceZ;
            }
            if (_camera != null)
                _camera.orthographicSize = s.orthoHalfHeight;
            ApplyFeetLift();
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
                _targetLane = string.Equals(tune.activeLane, "attention", StringComparison.OrdinalIgnoreCase)
                    ? Lane.Attention
                    : Lane.Taskbar;
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
                viewCenterAboveFeet = _follow.viewCenterAboveFeet,
                distanceZ = _follow.distanceZ,
                orthoHalfHeight = _camera.orthographicSize,
            };
            if (_targetLane == Lane.Attention)
                attention = live;
            else
                taskbar = live;

            var data = new OverlayTuneData
            {
                feetLiftMeters = feetLiftMeters,
                characterHeightMeters = 1.77f,
                activeLane = _targetLane == Lane.Attention ? "attention" : "taskbar",
                taskbar = LaneJson.From(taskbar),
                attention = LaneJson.From(attention),
            };
            try
            {
                var path = TunePath();
                File.WriteAllText(path, JsonUtility.ToJson(data, true));
                Debug.Log("[Viu] Сохранено: " + path);
            }
            catch (Exception e)
            {
                Debug.LogWarning("[Viu] Не удалось сохранить overlay_tune.json: " + e.Message);
            }
        }

        [Serializable]
        class OverlayTuneData
        {
            public float feetLiftMeters;
            public float characterHeightMeters;
            public string activeLane = "taskbar";
            public LaneJson taskbar;
            public LaneJson attention;
        }

        [Serializable]
        class LaneJson
        {
            public float viewCenterAboveFeet;
            public float distanceZ;
            public float orthoHalfHeight;

            public LaneSettings ToSettings() => new LaneSettings
            {
                viewCenterAboveFeet = viewCenterAboveFeet,
                distanceZ = distanceZ,
                orthoHalfHeight = orthoHalfHeight,
            };

            public static LaneJson From(LaneSettings s) => new LaneJson
            {
                viewCenterAboveFeet = s.viewCenterAboveFeet,
                distanceZ = s.distanceZ,
                orthoHalfHeight = s.orthoHalfHeight,
            };
        }
    }
}
