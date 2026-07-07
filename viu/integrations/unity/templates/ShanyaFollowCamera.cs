using UnityEngine;

namespace Viu.Runtime
{
    /// <summary>Вид сбоку (Terraria): ортокамера с −Z, персонаж по центру кадра по X.</summary>
    public class ShanyaFollowCamera : MonoBehaviour
    {
        public Transform target;
        /// <summary>Высота камеры (мир Y). ~середина тела при росте 1.7 м.</summary>
        public float cameraY = 0.85f;
        public float distanceZ = 12f;
        public float followSmooth = 14f;

        void LateUpdate()
        {
            if (target == null) return;
            var t = target.position;
            // X жёстко по персонажу — всегда по центру экрана, без «уезда» влево.
            float y = Mathf.Lerp(transform.position.y, cameraY, followSmooth * Time.deltaTime);
            transform.position = new Vector3(t.x, y, t.z - distanceZ);
            transform.rotation = Quaternion.identity;
        }
    }
}
