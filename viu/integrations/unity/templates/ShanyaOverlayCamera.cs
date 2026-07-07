using UnityEngine;

namespace Viu.Runtime
{
    /// <summary>
    /// Камера оверлея: стопы на фиксированной линии экрана. Y без сглаживания (иначе «волны» при W/S).
    /// </summary>
    public class ShanyaOverlayCamera : MonoBehaviour
    {
        public Transform target;
        /// <summary>Доля высоты окна от низа для стоп (0.06 ≈ 65 px на 1080p).</summary>
        public float feetScreenFraction = 0.06f;
        /// <summary>Доп. подъём стоп при приближении (компенсация перспективы меша).</summary>
        public float feetFractionCloseBoost = 0.011f;
        /// <summary>Текущая глубина 0…1 — задаёт ShanyaOverlayDepth.</summary>
        [HideInInspector] public float depthBlend;
        public float distanceZ = 12f;
        public float followSmoothX = 16f;

        Camera _camera;

        void Awake()
        {
            _camera = GetComponent<Camera>();
        }

        void LateUpdate()
        {
            if (target == null) return;
            if (_camera == null) _camera = GetComponent<Camera>();
            float ortho = _camera != null ? _camera.orthographicSize : 1f;
            var t = target.position;

            float frac = feetScreenFraction + depthBlend * feetFractionCloseBoost;
            float camY = t.y + ortho * (1f - 2f * frac);

            float x = followSmoothX > 0f
                ? Mathf.Lerp(transform.position.x, t.x, followSmoothX * Time.deltaTime)
                : t.x;

            transform.position = new Vector3(x, camY, t.z - distanceZ);
            transform.rotation = Quaternion.identity;
        }
    }
}
