using UnityEngine;

namespace Viu.Runtime
{
    /// <summary>
    /// Вид сбоку (Terraria): широкий кадр мира на весь экран, не портрет персонажа.
    /// orthographicSize задаётся на Camera (в Setup) — сколько метров видно по вертикали.
    /// </summary>
    public class ShanyaFollowCamera : MonoBehaviour
    {
        public Transform target;
        /// <summary>Центр кадра по Y относительно персонажа (м). ~2 м — Шаня в нижней трети, сверху деревья.</summary>
        public float viewCenterAboveFeet = 2.2f;
        public float distanceZ = 12f;
        public float followSmooth = 14f;

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
