using System.Reflection;
using UnityEngine;

namespace Viu.Runtime
{
    /// <summary>
    /// Простая ходьба: стрелки / A-D → параметр Speed в Animator (Idle ↔ Walk).
    /// Без прямой ссылки на Input System package (собирается даже если пакет не в manifest).
    /// </summary>
    [RequireComponent(typeof(Animator))]
    public class ShanyaLocomotion : MonoBehaviour
    {
        public float walkSpeed = 1.5f;
        public string speedParameter = "Speed";
        /// <summary>Если модель смотрит боком, подкрути: 0, 90, -90, 180.</summary>
        public float modelYawOffset;

        Animator _animator;
        int _speedHash;

        void Awake()
        {
            _animator = GetComponent<Animator>();
            _speedHash = Animator.StringToHash(speedParameter);
        }

        void Update()
        {
            float h = ReadHorizontal();
            if (_animator != null)
                _animator.SetFloat(_speedHash, Mathf.Abs(h));

            if (Mathf.Abs(h) > 0.01f)
            {
                // D — вперёд по взгляду персонажа, A — назад (анимация совпадает с движением).
                float yaw = (h > 0f ? 0f : 180f) + modelYawOffset;
                var euler = transform.eulerAngles;
                transform.rotation = Quaternion.Euler(euler.x, yaw, euler.z);
                transform.position += transform.forward * (Mathf.Abs(h) * walkSpeed * Time.deltaTime);
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

        /// <summary>Читает A/D и стрелки через Input System без compile-time ссылки на пакет.</summary>
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
