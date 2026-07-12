using UnityEngine;

namespace Viu.Runtime
{
    /// <summary>
    /// Камера оверлея: стопы на линии экрана.
    /// Важно: target — корень персонажа (бёдра), НЕ стопы. Считаем feetY по костям/bounds.
    /// Дома (lockFollowX) — X не следует за Шаней.
    /// </summary>
    public class ShanyaOverlayCamera : MonoBehaviour
    {
        public Transform target;
        /// <summary>Доля высоты окна от низа для стоп (0.12 ≈ не обрезать ноги).</summary>
        public float feetScreenFraction = 0.12f;
        public float feetFractionCloseBoost = 0.011f;
        [HideInInspector] public float depthBlend;
        public float distanceZ = 12f;
        public float followSmoothX = 16f;

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

            float feetY = ResolveFeetY(target);
            float frac = feetScreenFraction + depthBlend * feetFractionCloseBoost;
            float camY = feetY + ortho * (1f - 2f * frac);

            float desiredX = lockFollowX ? lockedWorldX : target.position.x;
            float x = (!lockFollowX && followSmoothX > 0f)
                ? Mathf.Lerp(transform.position.x, desiredX, followSmoothX * Time.deltaTime)
                : desiredX;

            transform.position = new Vector3(x, camY, target.position.z - distanceZ);
            transform.rotation = Quaternion.identity;
        }

        static float ResolveFeetY(Transform root)
        {
            var anim = root.GetComponentInChildren<Animator>();
            if (anim != null && anim.isHuman)
            {
                var lf = anim.GetBoneTransform(HumanBodyBones.LeftFoot);
                var rf = anim.GetBoneTransform(HumanBodyBones.RightFoot);
                if (lf != null && rf != null)
                    return Mathf.Min(lf.position.y, rf.position.y);
            }

            var renderers = root.GetComponentsInChildren<Renderer>();
            if (renderers != null && renderers.Length > 0)
            {
                float minY = float.PositiveInfinity;
                foreach (var r in renderers)
                {
                    if (r == null || !r.enabled) continue;
                    minY = Mathf.Min(minY, r.bounds.min.y);
                }
                if (!float.IsInfinity(minY))
                    return minY;
            }

            return root.position.y;
        }
    }
}
