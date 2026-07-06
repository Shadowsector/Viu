using UnityEngine;

namespace Viu.Runtime
{
    /// <summary>
    /// Простая ходьба: стрелки / A-D → параметр Speed в Animator (Idle ↔ Walk).
    /// Повесь на Шаню вместе с Animator + Controller.
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
            float h = Input.GetAxisRaw("Horizontal");
            if (_animator != null)
                _animator.SetFloat(_speedHash, Mathf.Abs(h));

            if (Mathf.Abs(h) > 0.01f)
            {
                var pos = transform.position;
                pos.x += h * walkSpeed * Time.deltaTime;
                transform.position = pos;
            }
        }
    }
}
