using System.Reflection;
using UnityEngine;

namespace Viu.Runtime
{
    /// <summary>
    /// Ходьба вдоль X (A/D). Walk через Animator Speed; без Walk-стейта будет только слайд.
    /// Animator может быть на дочернем FBX-хосте (Avatar), а Locomotion — на корне сцены.
    /// </summary>
    public class ShanyaLocomotion : MonoBehaviour
    {
        public float walkSpeed = 1.5f;
        public string speedParameter = "Speed";
        public float modelYawOffset;

        const float SideFaceRightYaw = 90f;

        Animator _animator;
        int _speedHash;
        bool _loggedMissingWalk;
        float _movingSeconds;

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
            if (_animator != null)
            {
                _animator.SetFloat(_speedHash, Mathf.Abs(h));
                if (Mathf.Abs(h) > 0.05f)
                {
                    _movingSeconds += Time.deltaTime;
                    if (!_loggedMissingWalk && _movingSeconds > 0.3f
                        && _animator.runtimeAnimatorController != null)
                    {
                        var info = _animator.GetCurrentAnimatorStateInfo(0);
                        if (!info.IsName("Walk"))
                        {
                            bool hasWalk = _animator.HasState(0, Animator.StringToHash("Walk"));
                            Debug.LogWarning(
                                "[Viu] Locomotion: Speed>0 state≠Walk hasWalk=" + hasWalk
                                + " avatar=" + (_animator.avatar != null && _animator.avatar.isValid)
                                + " human=" + _animator.isHuman
                                + " ctrl=" + (_animator.runtimeAnimatorController != null
                                    ? _animator.runtimeAnimatorController.name : "null")
                                + " — CrossFade Walk fallback.");
                            if (hasWalk)
                                _animator.CrossFade("Walk", 0.05f, 0);
                        }
                        _loggedMissingWalk = true;
                    }
                }
                else
                    _movingSeconds = 0f;
            }

            if (Mathf.Abs(h) > 0.01f)
            {
                float yaw = (h > 0f ? SideFaceRightYaw : -SideFaceRightYaw) + modelYawOffset;
                transform.rotation = Quaternion.Euler(0f, yaw, 0f);
                transform.position += Vector3.right * (h * walkSpeed * Time.deltaTime);
            }
        }

        static float ReadHorizontal()
        {
            float h = TryLegacyHorizontal();
            if (Mathf.Abs(h) > 0.01f) return h;
            return ReadHorizontalNewInput();
        }

        static float TryLegacyHorizontal()
        {
#if ENABLE_LEGACY_INPUT_MANAGER
            try
            {
                float h = Input.GetAxisRaw("Horizontal");
                if (Mathf.Abs(h) > 0.01f) return h;
                if (Input.GetKey(KeyCode.A) || Input.GetKey(KeyCode.LeftArrow)) h -= 1f;
                if (Input.GetKey(KeyCode.D) || Input.GetKey(KeyCode.RightArrow)) h += 1f;
                return h;
            }
            catch
            {
                return 0f;
            }
#else
            return 0f;
#endif
        }

        static float ReadHorizontalNewInput()
        {
            var keyboardType = System.Type.GetType("UnityEngine.InputSystem.Keyboard, Unity.InputSystem");
            if (keyboardType == null) return 0f;

            var current = keyboardType.GetProperty("current", BindingFlags.Static | BindingFlags.Public);
            var keyboard = current?.GetValue(null);
            if (keyboard == null) return 0f;

            float h = 0f;
            if (IsKeyPressed(keyboard, "aKey") || IsKeyPressed(keyboard, "leftArrowKey")) h -= 1f;
            if (IsKeyPressed(keyboard, "dKey") || IsKeyPressed(keyboard, "rightArrowKey")) h += 1f;
            return h;
        }

        static bool IsKeyPressed(object keyboard, string keyName)
        {
            var key = keyboard.GetType().GetProperty(keyName, BindingFlags.Instance | BindingFlags.Public);
            var keyControl = key?.GetValue(keyboard);
            if (keyControl == null) return false;

            var isPressed = keyControl.GetType().GetProperty("isPressed", BindingFlags.Instance | BindingFlags.Public);
            return isPressed != null && (bool)isPressed.GetValue(keyControl);
        }
    }
}
