using UnityEngine;
#if ENABLE_INPUT_SYSTEM
using UnityEngine.InputSystem;
#endif

namespace Viu.Runtime
{
    /// <summary>
    /// Простая ходьба: стрелки / A-D → параметр Speed в Animator (Idle ↔ Walk).
    /// Работает и со старым Input Manager, и с новым Input System package.
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
#if ENABLE_INPUT_SYSTEM && !ENABLE_LEGACY_INPUT_MANAGER
            var kb = Keyboard.current;
            if (kb == null) return 0f;
            float h = 0f;
            if (kb.aKey.isPressed || kb.leftArrowKey.isPressed) h -= 1f;
            if (kb.dKey.isPressed || kb.rightArrowKey.isPressed) h += 1f;
            return h;
#else
            return Input.GetAxisRaw("Horizontal");
#endif
        }
    }
}
