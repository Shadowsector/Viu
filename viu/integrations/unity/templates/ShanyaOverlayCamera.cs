using UnityEngine;

namespace Viu.Runtime
{
    /// <summary>
    /// Камера оверлея: стопы на линии экрана.
    /// target — корень (бёдра). Высоту камеры держим от root + фиксированный offset,
    /// а не от костей стоп каждый кадр — иначе Run/Idle bobbing дёргает кадр вверх-вниз.
    /// </summary>
    public class ShanyaOverlayCamera : MonoBehaviour
    {
        public Transform target;
        /// <summary>Доля высоты окна от низа для стоп (0.07 ≈ у линии таскбара).</summary>
        public float feetScreenFraction = 0.07f;
        public float feetFractionCloseBoost = 0.011f;
        [HideInInspector] public float depthBlend;
        public float distanceZ = 12f;
        public float followSmoothX = 16f;

        public bool lockFollowX = true;
        public float lockedWorldX;

        Camera _camera;
        float _feetOffsetFromRoot;
        bool _feetCalibrated;

        void Awake()
        {
            _camera = GetComponent<Camera>();
        }

        void Start()
        {
            CalibrateFeetOffset();
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

        public void CalibrateFeetOffset()
        {
            if (target == null)
            {
                _feetCalibrated = false;
                return;
            }

            _feetOffsetFromRoot = SampleFeetY(target) - target.position.y;
            _feetCalibrated = true;
        }

        void LateUpdate()
        {
            if (target == null) return;
            if (!_feetCalibrated)
                CalibrateFeetOffset();
            if (_camera == null) _camera = GetComponent<Camera>();
            float ortho = _camera != null ? _camera.orthographicSize : 1f;

            float feetY = target.position.y + _feetOffsetFromRoot;
            float frac = feetScreenFraction + depthBlend * feetFractionCloseBoost;
            float camY = feetY + ortho * (1f - 2f * frac);

            float desiredX = lockFollowX ? lockedWorldX : target.position.x;
            float x = (!lockFollowX && followSmoothX > 0f)
                ? Mathf.Lerp(transform.position.x, desiredX, followSmoothX * Time.deltaTime)
                : desiredX;

            transform.position = new Vector3(x, camY, target.position.z - distanceZ);
            transform.rotation = Quaternion.identity;
        }

        static float SampleFeetY(Transform root)
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
