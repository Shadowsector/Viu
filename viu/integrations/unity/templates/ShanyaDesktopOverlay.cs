using System;
using System.Runtime.InteropServices;
using UnityEngine;

namespace Viu.Runtime
{
    /// <summary>
    /// Прозрачное окно поверх рабочего стола (Windows build): полоса у низа экрана,
    /// клики проходят сквозь прозрачные пиксели. В Editor не применяется.
    /// </summary>
    [DefaultExecutionOrder(-50)]
    public class ShanyaDesktopOverlay : MonoBehaviour
    {
        [Tooltip("Высота полосы в пикселях (персонаж «на панели задач»).")]
        public int stripHeightPixels = 300;

        [Tooltip("Прозрачные области не ловят мышь (клик попадает в окна под Шаней).")]
        public bool clickThroughTransparent = true;

        [Tooltip("Окно поверх всех окон.")]
        public bool alwaysOnTop = true;

        Camera _camera;

#if UNITY_STANDALONE_WIN && !UNITY_EDITOR
        IntPtr _hwnd;
        bool _configured;
#endif

        void Awake()
        {
            Application.runInBackground = true;
            QualitySettings.vSyncCount = 0;

            _camera = Camera.main;
            if (_camera != null)
            {
                _camera.clearFlags = CameraClearFlags.SolidColor;
                _camera.backgroundColor = new Color(0f, 0f, 0f, 0f);
                _camera.depth = 0;
            }
        }

        void Start()
        {
#if UNITY_STANDALONE_WIN && !UNITY_EDITOR
            try
            {
                ConfigureWindow();
            }
            catch (Exception e)
            {
                Debug.LogWarning("[Viu] Overlay window: " + e.Message);
            }
#else
            Debug.Log("[Viu] Desktop overlay активен только в Windows-сборке (не в Editor).");
#endif
        }

        void Update()
        {
#if UNITY_STANDALONE_WIN && !UNITY_EDITOR
            if (!_configured)
                ConfigureWindow();
#endif
        }

#if UNITY_STANDALONE_WIN && !UNITY_EDITOR
        void ConfigureWindow()
        {
            if (_hwnd == IntPtr.Zero)
                _hwnd = GetActiveWindow();
            if (_hwnd == IntPtr.Zero)
                return;

            int screenW = GetSystemMetrics(SM_CXSCREEN);
            int screenH = GetSystemMetrics(SM_CYSCREEN);
            int h = Mathf.Clamp(stripHeightPixels, 120, screenH);
            int x = 0;
            int y = screenH - h;

            // Borderless полоса у нижнего края монитора.
            SetWindowLong(_hwnd, GWL_STYLE, WS_POPUP | WS_VISIBLE);
            uint ex = WS_EX_LAYERED;
            if (alwaysOnTop) ex |= WS_EX_TOPMOST;
            if (clickThroughTransparent) ex |= WS_EX_TRANSPARENT;
            SetWindowLong(_hwnd, GWL_EXSTYLE, ex);

            SetWindowPos(_hwnd, alwaysOnTop ? HWND_TOPMOST : HWND_NOTOPMOST,
                x, y, screenW, h, SWP_SHOWWINDOW);

            // Чёрный (0,0,0) как color key — Unity рисует фон с alpha 0, ключ вырезает остаток.
            SetLayeredWindowAttributes(_hwnd, 0, 255, LWA_COLORKEY);

            _configured = true;
        }

        const int GWL_STYLE = -16;
        const int GWL_EXSTYLE = -20;
        const uint WS_POPUP = 0x80000000;
        const uint WS_VISIBLE = 0x10000000;
        const uint WS_EX_LAYERED = 0x00080000;
        const uint WS_EX_TRANSPARENT = 0x00000020;
        const uint WS_EX_TOPMOST = 0x00000008;
        const uint SWP_SHOWWINDOW = 0x0040;
        const uint LWA_COLORKEY = 0x00000001;
        const int SM_CXSCREEN = 0;
        const int SM_CYSCREEN = 1;

        static readonly IntPtr HWND_TOPMOST = new IntPtr(-1);
        static readonly IntPtr HWND_NOTOPMOST = new IntPtr(-2);

        [DllImport("user32.dll")]
        static extern IntPtr GetActiveWindow();

        [DllImport("user32.dll", EntryPoint = "SetWindowLong")]
        static extern int SetWindowLong32(IntPtr hWnd, int nIndex, uint dwNewLong);

        [DllImport("user32.dll", EntryPoint = "SetWindowLongPtr")]
        static extern IntPtr SetWindowLongPtr64(IntPtr hWnd, int nIndex, uint dwNewLong);

        static void SetWindowLong(IntPtr hWnd, int nIndex, uint dwNewLong)
        {
            if (IntPtr.Size == 8)
                SetWindowLongPtr64(hWnd, nIndex, dwNewLong);
            else
                SetWindowLong32(hWnd, nIndex, dwNewLong);
        }

        [DllImport("user32.dll", SetLastError = true)]
        static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter,
            int X, int Y, int cx, int cy, uint uFlags);

        [DllImport("user32.dll")]
        static extern bool SetLayeredWindowAttributes(IntPtr hwnd, uint crKey, byte bAlpha, uint dwFlags);

        [DllImport("user32.dll")]
        static extern int GetSystemMetrics(int nIndex);
#endif
    }
}
