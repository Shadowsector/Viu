using System.Reflection;
using UnityEngine;

namespace Viu.Runtime
{
    /// <summary>
    /// Overlay locomotion: A/D — X, W/S — Z (к камере / вглубь). Idle/Walk через CrossFade.
    /// Baseline pins: docs/OVERLAY_BASELINE.md (X Bot@Idle, Shanya_Run-as-Walk).
    /// </summary>
    public class ShanyaLocomotion : MonoBehaviour
    {
        public float walkSpeed = 1.5f;
        public float depthWalkSpeed = 1.35f;
        public string speedParameter = "Speed";
        public float modelYawOffset;

        const float SideFaceRightYaw = 90f;
        /// <summary>W → лицом к камере (−Z). S → спиной (+Z).</summary>
        const float FaceCameraYaw = 180f;
        const float FaceAwayYaw = 0f;
        const float WalkThreshold = 0.25f;

        Animator _animator;
        int _speedHash;
        bool _walking;
        bool _loggedOnce;
        float _walkAnimSpeed = 1f;
        float _baseZ;
        bool _baseCaptured;
        ShanyaOverlayDepth _depth;
        ShanyaOverlayCorridor _corridor;

        void Awake()
        {
            _animator = GetComponent<Animator>() ?? GetComponentInChildren<Animator>(true);
            _speedHash = Animator.StringToHash(speedParameter);
            if (_animator == null)
                Debug.LogError("[Viu] Locomotion: Animator не найден под " + name);
        }

        void Start()
        {
            transform.rotation = Quaternion.Euler(0f, SideFaceRightYaw + modelYawOffset, 0f);
            _depth = FindFirstObjectByType<ShanyaOverlayDepth>();
            _corridor = FindFirstObjectByType<ShanyaOverlayCorridor>();
            CaptureBaseZ();
            if (_depth != null)
                _depth.BindCharacter(transform);

            if (_animator == null) return;

            _animator.applyRootMotion = false;
            _animator.cullingMode = AnimatorCullingMode.AlwaysAnimate;
            _walkAnimSpeed = DetectRunAsWalkSpeed();
            if (_animator.runtimeAnimatorController != null && _animator.avatar != null)
            {
                _animator.Rebind();
                _animator.Update(0f);
                _walking = false;
                _animator.SetFloat(_speedHash, 0f);
                _animator.speed = 1f;
                PlayState("Idle", 0f);
                Debug.Log(
                    "[Viu] Locomotion start human=" + _animator.isHuman
                    + " avatarValid=" + (_animator.avatar.isValid)
                    + " ctrl=" + _animator.runtimeAnimatorController.name
                    + " hasIdle=" + HasState("Idle")
                    + " hasWalk=" + HasState("Walk")
                    + " walkAnimSpeed=" + _walkAnimSpeed);
            }
            else
            {
                Debug.LogWarning(
                    "[Viu] Locomotion: Animator без controller/avatar — будет слайд без анимации. "
                    + "ctrl=" + (_animator.runtimeAnimatorController != null)
                    + " avatar=" + (_animator.avatar != null));
            }

            var camFollow = Camera.main != null ? Camera.main.GetComponent<ShanyaOverlayCamera>() : null;
            camFollow?.CalibrateFeetOffset();
        }

        void CaptureBaseZ()
        {
            if (_baseCaptured) return;
            _baseZ = transform.position.z;
            _baseCaptured = true;
        }

        void Update()
        {
            float h = ReadHorizontal();
            float v = ReadDepth();
            float planar = Mathf.Sqrt(h * h + v * v);

            if (_animator != null)
            {
                _animator.SetFloat(_speedHash, planar);
                bool wantWalk = planar > WalkThreshold;
                if (wantWalk != _walking)
                {
                    _walking = wantWalk;
                    PlayState(wantWalk ? "Walk" : "Idle", 0.08f);
                    if (!_loggedOnce && wantWalk)
                    {
                        _loggedOnce = true;
                        var info = _animator.GetCurrentAnimatorStateInfo(0);
                        Debug.Log(
                            "[Viu] Locomotion → Walk CrossFade hasWalk=" + HasState("Walk")
                            + " now=" + (info.IsName("Walk") ? "Walk" : "other"));
                    }
                }
                _animator.speed = _walking ? _walkAnimSpeed : 1f;
            }

            if (planar <= WalkThreshold)
                return;

            var pos = transform.position;
            bool depthMove = Mathf.Abs(v) > WalkThreshold;
            bool sideMove = Mathf.Abs(h) > WalkThreshold;

            if (depthMove && (!sideMove || Mathf.Abs(v) >= Mathf.Abs(h)))
            {
                float depthYaw = (v < 0f ? FaceCameraYaw : FaceAwayYaw) + modelYawOffset;
                transform.rotation = Quaternion.Euler(0f, depthYaw, 0f);
            }
            else if (sideMove)
            {
                float yaw = (h > 0f ? SideFaceRightYaw : -SideFaceRightYaw) + modelYawOffset;
                transform.rotation = Quaternion.Euler(0f, yaw, 0f);
            }

            if (sideMove)
                pos.x += h * walkSpeed * Time.deltaTime;

            if (depthMove)
            {
                float minZ;
                float maxZ;
                if (_corridor != null)
                {
                    minZ = _corridor.corridorNearZ;
                    maxZ = _corridor.corridorFarZ;
                }
                else
                {
                    minZ = _baseZ + (_depth != null ? _depth.minDepthZ : -2.5f);
                    maxZ = _baseZ + (_depth != null ? _depth.maxDepthZ : 3.5f);
                }
                CaptureBaseZ();
                pos.z = Mathf.Clamp(
                    pos.z + v * depthWalkSpeed * Time.deltaTime,
                    minZ,
                    maxZ);
                if (_depth != null)
                    _depth.SyncDepthFromCharacter(_baseZ, pos.z);
            }

            transform.position = pos;
        }

        float DetectRunAsWalkSpeed()
        {
            if (_animator == null || _animator.runtimeAnimatorController == null)
                return 1f;
            foreach (var clip in _animator.runtimeAnimatorController.animationClips)
            {
                if (clip == null) continue;
                var n = clip.name.ToLowerInvariant();
                if (n.Contains("run") || n.Contains("sprint"))
                    return 0.55f;
            }
            return 1f;
        }

        bool HasState(string stateName)
        {
            if (_animator == null) return false;
            return _animator.HasState(0, Animator.StringToHash(stateName));
        }

        void PlayState(string stateName, float fade)
        {
            if (_animator == null || !HasState(stateName)) return;
            if (fade <= 0.001f)
                _animator.Play(stateName, 0, 0f);
            else
                _animator.CrossFadeInFixedTime(stateName, fade, 0);
        }

        static float ReadHorizontal()
        {
            float h = TryLegacyHorizontal();
            if (Mathf.Abs(h) > 0.01f) return h;
            return ReadHorizontalNewInput();
        }

        static float ReadDepth()
        {
            float v = 0f;
            if (Input.GetKey(KeyCode.W) || Input.GetKey(KeyCode.UpArrow)) v -= 1f;
            if (Input.GetKey(KeyCode.S) || Input.GetKey(KeyCode.DownArrow)) v += 1f;
            if (Mathf.Abs(v) > 0.01f) return v;
            return ReadDepthNewInput();
        }

        static float TryLegacyHorizontal()
        {
            try
            {
                float h = 0f;
                if (Input.GetKey(KeyCode.A) || Input.GetKey(KeyCode.LeftArrow)) h -= 1f;
                if (Input.GetKey(KeyCode.D) || Input.GetKey(KeyCode.RightArrow)) h += 1f;
                return h;
            }
            catch
            {
                return 0f;
            }
        }

        static float ReadHorizontalNewInput()
        {
            try
            {
                var keyboardType = System.Type.GetType(
                    "UnityEngine.InputSystem.Keyboard, Unity.InputSystem");
                if (keyboardType == null) return 0f;
                var currentProp = keyboardType.GetProperty(
                    "current", BindingFlags.Public | BindingFlags.Static);
                var keyboard = currentProp?.GetValue(null);
                if (keyboard == null) return 0f;

                float h = 0f;
                if (IsPressed(keyboard, "aKey") || IsPressed(keyboard, "leftArrowKey")) h -= 1f;
                if (IsPressed(keyboard, "dKey") || IsPressed(keyboard, "rightArrowKey")) h += 1f;
                return h;
            }
            catch
            {
                return 0f;
            }
        }

        static float ReadDepthNewInput()
        {
            try
            {
                var keyboardType = System.Type.GetType(
                    "UnityEngine.InputSystem.Keyboard, Unity.InputSystem");
                if (keyboardType == null) return 0f;
                var currentProp = keyboardType.GetProperty(
                    "current", BindingFlags.Public | BindingFlags.Static);
                var keyboard = currentProp?.GetValue(null);
                if (keyboard == null) return 0f;

                float v = 0f;
                if (IsPressed(keyboard, "wKey") || IsPressed(keyboard, "upArrowKey")) v -= 1f;
                if (IsPressed(keyboard, "sKey") || IsPressed(keyboard, "downArrowKey")) v += 1f;
                return v;
            }
            catch
            {
                return 0f;
            }
        }

        static bool IsPressed(object keyboard, string keyProp)
        {
            var prop = keyboard.GetType().GetProperty(keyProp);
            var key = prop?.GetValue(keyboard);
            if (key == null) return false;
            var isPressed = key.GetType().GetProperty("isPressed");
            return isPressed != null && (bool)isPressed.GetValue(key);
        }
    }
}
