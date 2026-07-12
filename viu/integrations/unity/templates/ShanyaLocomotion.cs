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
        const float WalkThreshold = 0.05f;

        Animator _animator;
        int _speedHash;
        bool _walking;
        bool _loggedOnce;

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
            if (_animator.runtimeAnimatorController != null && _animator.avatar != null)
            {
                _animator.Rebind();
                _animator.Update(0f);
                PlayState("Idle", 0f);
                Debug.Log(
                    "[Viu] Locomotion start human=" + _animator.isHuman
                    + " avatarValid=" + (_animator.avatar.isValid)
                    + " ctrl=" + _animator.runtimeAnimatorController.name
                    + " hasIdle=" + HasState("Idle")
                    + " hasWalk=" + HasState("Walk"));
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
            }

            if (speed > 0.01f)
            {
                float yaw = (h > 0f ? SideFaceRightYaw : -SideFaceRightYaw) + modelYawOffset;
                transform.rotation = Quaternion.Euler(0f, yaw, 0f);
                transform.position += Vector3.right * (h * walkSpeed * Time.deltaTime);
            }
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
                // Только A/D и ←→ — W/S заняты глубиной (Z), не мешаем.
                float h = 0f;
                if (Input.GetKey(KeyCode.A) || Input.GetKey(KeyCode.LeftArrow)) h -= 1f;
                if (Input.GetKey(KeyCode.D) || Input.GetKey(KeyCode.RightArrow)) h += 1f;
                if (Mathf.Abs(h) > 0.01f) return h;
                return Input.GetAxisRaw("Horizontal");
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
