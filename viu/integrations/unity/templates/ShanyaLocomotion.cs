using System.Reflection;
using UnityEngine;

namespace Viu.Runtime
{
    /// <summary>
    /// Ходьба вдоль X (A/D / стрелки ←→). Idle/Walk через CrossFade на явные стейты —
    /// не полагаемся только на переходы Animator (часто ломались → слайд).
    /// </summary>
    public class ShanyaLocomotion : MonoBehaviour
    {
        public float walkSpeed = 1.5f;
        public string speedParameter = "Speed";
        public float modelYawOffset;

        const float SideFaceRightYaw = 90f;
        /// <summary>Выше — меньше ложных Walk от дребезга/стика.</summary>
        const float WalkThreshold = 0.25f;

        Animator _animator;
        int _speedHash;
        bool _walking;
        bool _loggedOnce;
        /// <summary>Если в Walk подложен Run-клип — замедляем playback.</summary>
        float _walkAnimSpeed = 1f;

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
        }

        void Update()
        {
            float h = ReadHorizontal();
            float speed = Mathf.Abs(h);

            if (_animator != null)
            {
                _animator.SetFloat(_speedHash, speed);
                bool wantWalk = speed > WalkThreshold;
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
                // Run-клип в слоте Walk: на месте Idle на полной скорости, в движении — медленнее
                _animator.speed = _walking ? _walkAnimSpeed : 1f;
            }

            if (speed > WalkThreshold)
            {
                float yaw = (h > 0f ? SideFaceRightYaw : -SideFaceRightYaw) + modelYawOffset;
                transform.rotation = Quaternion.Euler(0f, yaw, 0f);
                transform.position += Vector3.right * (h * walkSpeed * Time.deltaTime);
            }
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

        static float TryLegacyHorizontal()
        {
            try
            {
                // Только A/D и ←→. GetAxisRaw("Horizontal") НЕ использовать —
                // дрейф геймпада → Speed>0 → вечный Run в слоте Walk.
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
