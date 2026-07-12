using UnityEngine;

namespace Viu.Runtime
{
    /// <summary>
    /// Камера оверлея: стопы на линии экрана.
    /// Дома (lockFollowX) — X не следует за Шаней (иначе дом «уезжает» вбок).
    /// </summary>
    public class ShanyaOverlayCamera : MonoBehaviour
    {
        public Transform target;
        /// <summary>Доля высоты окна от низа для стоп (0.06 ≈ 65 px на 1080p).</summary>
        public float feetScreenFraction = 0.06f;
        /// <summary>Доп. подъём стоп при приближении.</summary>
        public float feetFractionCloseBoost = 0.011f;
        [HideInInspector] public float depthBlend;
        public float distanceZ = 12f;
        public float followSmoothX = 16f;

        /// <summary>true = Шаня дома: камера X зафиксирована (якорь дома).</summary>
        public bool lockFollowX = true;
        public float lockedWorldX;

        Camera _camera;

        void Awake()
        {
            _camera = GetComponent<Camera>();
        }

        public void LockToHome(float worldX)
        {
            lockFollowX = true;
            lockedWorldX = worldX;
            followSmoothX = 0f;
        }

        public void UnlockFollow()
        {
            lockFollowX = false;
            followSmoothX = 16f;
        }

        void LateUpdate()
        {
            if (target == null) return;
            if (_camera == null) _camera = GetComponent<Camera>();
            float ortho = _camera != null ? _camera.orthographicSize : 1f;
            var t = target.position;

            float frac = feetScreenFraction + depthBlend * feetFractionCloseBoost;
            float camY = t.y + ortho * (1f - 2f * frac);

            float desiredX = lockFollowX ? lockedWorldX : t.x;
            float x = (!lockFollowX && followSmoothX > 0f)
                ? Mathf.Lerp(transform.position.x, desiredX, followSmoothX * Time.deltaTime)
                : desiredX;

            transform.position = new Vector3(x, camY, t.z - distanceZ);
            transform.rotation = Quaternion.identity;
        }
    }
}
