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
                var pos = transform.position;
                pos.x += h * walkSpeed * Time.deltaTime;
                transform.position = pos;
            }
        }

        static float ReadHorizontal()
        {
#if ENABLE_LEGACY_INPUT_MANAGER
            return Input.GetAxisRaw("Horizontal");
#else
            return ReadHorizontalNewInput();
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
