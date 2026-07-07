using UnityEngine;

namespace Viu.Runtime
{
    /// <summary>Вид сбоку (Terraria): камера с −Z, персонаж ходит вдоль X.</summary>
    public class ShanyaFollowCamera : MonoBehaviour
    {
        public Transform target;
        public float height = 1.25f;
        public float distanceZ = 10f;
        public float lookAtHeight = 0.85f;
        public float followSmooth = 12f;

        void LateUpdate()
        {
            if (target == null) return;
            var t = target.position;
            var desired = new Vector3(t.x, t.y + height, t.z - distanceZ);
            transform.position = Vector3.Lerp(
                transform.position, desired, followSmooth * Time.deltaTime);
            transform.LookAt(t + Vector3.up * lookAtHeight);
        }
    }
}
