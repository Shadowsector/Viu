# ComfyUI во Вью

Вью сама держит Comfy в `U:\Viu\ComfyUI`, пишет промпты под Cascadeur MoCap, шлёт тебе в Telegram на одобрение и после «ок» гоняет **3 ракурса** (сбоку / ¾ / анфас) в `Lab/Refs`.

Пайплайн: [COMFY_CASCADEUR_PIPELINE.md](./COMFY_CASCADEUR_PIPELINE.md).

---

## Модель

**Wan 2.1** (выбор Вью): лучший open T2V/I2V для явного full-body motion.

| Роль | Файл (в `ComfyUI/models/…`) |
|------|-----------------------------|
| T2V (основной, ~VRAM) | `diffusion_models/wan2.1_t2v_1.3B_fp16.safetensors` |
| I2V (last frame → next) | `diffusion_models/wan2.1_i2v_480p_14B_fp16.safetensors` |
| VAE | `vae/wan_2.1_vae.safetensors` |
| Text | `text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors` |
| CLIP Vision (I2V) | `clip_vision/clip_vision_h.safetensors` |

---

## Как пользоваться (Ден почти не трогает)

1. Comfy лежит в `U:\Viu\ComfyUI`.
2. Во Вью: кнопка **«Лаборатория: Comfy MoCap»** или `comfy_mocap action=sit down on chair`.
3. Вью поднимает API (`comfy_ensure`), готовит промпт → **Telegram**.
4. Ты: `ок` / `правки: …` / `стоп`.
5. Вью генерит 3 mp4 → `U:\Anabarra\Library\Lab\Refs\`.

Один раз (если ещё stub): в ComfyUI открой официальный Wan 2.1 T2V → **Save (API Format)** →  
`U:\Viu\.viu\comfy\workflows\t2v.json` (и при желании `i2v.json`).  
Если в `ComfyUI/user/.../workflows` уже есть wan*.json — Вью подхватит сама.

---

## Инструменты

| Tool | Что |
|------|-----|
| `comfy_status` | ping, путь, Wan ready, workflows |
| `comfy_ensure` | запуск `main.py --listen` |
| `comfy_mocap` | lab topic=comfy + Telegram + 3 ракурса |
| `comfy_triple` | 3 ракурса сразу (без Telegram) |
| `comfy_run` | один workflow |
| `lab_start topic=comfy action=…` | то же через lab |

---

## Env

| Ключ | Default |
|------|---------|
| `VIU_COMFY_URL` | `http://127.0.0.1:8188` |
| `VIU_COMFY_ROOT` | `U:/Viu/ComfyUI` |

VRAM: не гоняй Comfy + Cascadeur + Unity одновременно.
