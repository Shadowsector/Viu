using UnityEngine;

namespace Viu.Runtime
{
    /// <summary>
    /// Камера оверлея: стопы прибиты к линии у низа экрана (над панелью задач).
    /// При изменении zoom (ortho) макушка двигается, стопы — нет.
    /// </summary>
    public class ShanyaOverlayCamera : MonoBehaviour
    {
        public Transform target;
        /// <summary>Доля высоты окна от низа, где стоят стопы (0.06 ≈ 65 px на 1080p).</summary>
        public float feetScreenFraction = 0.06f;
        public float distanceZ = 12f;
        public float followSmooth = 18f;

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
            // Низ кадра = camY - ortho. Стопы на fraction от низа окна.
            float camY = t.y + ortho * (1f - 2f * feetScreenFraction);
            float y = Mathf.Lerp(transform.position.y, camY, followSmooth * Time.deltaTime);
            transform.position = new Vector3(t.x, y, t.z - distanceZ);
            transform.rotation = Quaternion.identity;
        }
    }
}
