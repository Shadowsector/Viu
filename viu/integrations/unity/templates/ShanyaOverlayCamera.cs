using UnityEngine;

namespace Viu.Runtime
{
    /// <summary>
    /// Камера для десктоп-оверлея: узкая полоса, Шаня у нижнего края кадра (над панелью задач).
    /// </summary>
    public class ShanyaOverlayCamera : MonoBehaviour
    {
        public Transform target;
        /// <summary>Центр кадра над стопами (м). Меньше — персонаж ниже в полосе.</summary>
        public float viewCenterAboveFeet = 0.95f;
        public float distanceZ = 10f;
        public float followSmooth = 18f;

        void LateUpdate()
        {
            if (target == null) return;
            var t = target.position;
            float targetY = t.y + viewCenterAboveFeet;
            float y = Mathf.Lerp(transform.position.y, targetY, followSmooth * Time.deltaTime);
            transform.position = new Vector3(t.x, y, t.z - distanceZ);
            transform.rotation = Quaternion.identity;
        }
    }
}
