using System;
using System.Collections;
using System.IO;
using System.Runtime.InteropServices;
using UnityEngine;

namespace Viu.Runtime
{
    /// <summary>
    /// Прозрачное окно на весь экран (Windows build). Фон — magenta + DWM. Esc — выход.
    /// </summary>
    [DefaultExecutionOrder(-50)]
    public class ShanyaDesktopOverlay : MonoBehaviour
    {
        public static readonly Color ChromaKey = new Color(1f, 0f, 1f, 1f);

        [Tooltip("На весь монитор — чтобы Шаня могла ходить вверх по миру (деревья, иконки).")]
        public bool fullScreenOverlay = true;

        [Tooltip("Только если fullScreenOverlay=false: высота полосы в пикселях.")]
        public int stripHeightPixels = 280;

        [Tooltip("Стопы на этой высоте от низа экрана (над панелью задач), в пикселях.")]
        public int feetLineFromBottomPixels = 46;

        public bool clickThrough = false;
        public bool alwaysOnTop = true;
        public int monitorIndex = 0;

        Camera _camera;

#if UNITY_STANDALONE_WIN && !UNITY_EDITOR
        IntPtr _hwnd;
        bool _configured;
        bool _colorKeyApplied;
#endif

        void Awake()
        {
            Application.runInBackground = true;
            QualitySettings.vSyncCount = 0;

#if UNITY_STANDALONE_WIN && !UNITY_EDITOR
            Screen.fullScreenMode = FullScreenMode.Windowed;
            Screen.fullScreen = false;
#endif

            _camera = Camera.main;
            if (_camera != null)
            {
                _camera.clearFlags = CameraClearFlags.SolidColor;
                _camera.backgroundColor = ChromaKey;
                _camera.depth = 0;
            }
        }

        void Start()
        {
#if UNITY_STANDALONE_WIN && !UNITY_EDITOR
            BootLog("Start product=" + Application.productName);
            StartCoroutine(ConfigureWindowWhenReady());
#endif
        }

        void Update()
        {
            if (Input.GetKeyDown(KeyCode.Escape))
                Application.Quit();
        }

#if UNITY_STANDALONE_WIN && !UNITY_EDITOR
        IEnumerator ConfigureWindowWhenReady()
        {
            // Unity часто ещё не создал HWND в первые кадры — ждём и ищем надёжнее, чем GetActiveWindow.
            for (int i = 0; i < 180 && _hwnd == IntPtr.Zero; i++)
            {
                _hwnd = ResolveGameWindow();
                if (_hwnd == IntPtr.Zero)
                    yield return null;
            }

            if (_hwnd == IntPtr.Zero)
            {
                BootLog("ERROR: окно игры не найдено (HWND=0). Alt+Tab — ищи AnabarraOverlay.");
                yield break;
            }

            BootLog("HWND ok, frame=" + Time.frameCount);
            ApplyWindowGeometry();
            _configured = true;

            // Цветовой ключ — после первого кадра с 3D, иначе весь экран «дырявый» и кажется, что оверлея нет.
            yield return new WaitForEndOfFrame();
            yield return new WaitForSeconds(0.35f);
            ApplyColorKey();
            _colorKeyApplied = true;
            BootLog("ColorKey applied, Esc=выход");
        }

        void ApplyWindowGeometry()
        {
            var mon = ResolveMonitorRect(monitorIndex);
            int w = mon.width;
            int h = fullScreenOverlay ? mon.height : Mathf.Clamp(stripHeightPixels, 120, mon.height);
            int x = mon.x;
            int y = fullScreenOverlay ? mon.y : mon.y + mon.height - h;

            ShowWindow(_hwnd, SW_RESTORE);
            ShowWindow(_hwnd, SW_SHOW);

            SetWindowLong(_hwnd, GWL_STYLE, WS_POPUP | WS_VISIBLE);

            uint ex = WS_EX_LAYERED;
            if (alwaysOnTop) ex |= WS_EX_TOPMOST;
            if (clickThrough) ex |= WS_EX_TRANSPARENT;
            SetWindowLong(_hwnd, GWL_EXSTYLE, ex);

            SetWindowPos(_hwnd, alwaysOnTop ? HWND_TOPMOST : HWND_NOTOPMOST,
                x, y, w, h, SWP_SHOWWINDOW | SWP_FRAMECHANGED);

            ApplyFeetLineToCamera(h);

            try { SetForegroundWindow(_hwnd); }
            catch { /* запуск из Viu может блокировать foreground */ }

            Debug.Log($"[Viu] Overlay {w}x{h} fullscreen={fullScreenOverlay}, Esc=выход.");
            BootLog($"Geometry {w}x{h} at {x},{y}");
        }

        void ApplyColorKey()
        {
            if (_hwnd == IntPtr.Zero) return;

            var margins = new MARGINS { cxLeftWidth = -1 };
            DwmExtendFrameIntoClientArea(_hwnd, ref margins);
            SetLayeredWindowAttributes(_hwnd, ChromaColorRef, 0, LWA_COLORKEY);
        }

        static IntPtr ResolveGameWindow()
        {
            var hwnd = FindWindow("UnityWndClass", null);
            if (hwnd != IntPtr.Zero) return hwnd;

            hwnd = FindWindow(null, Application.productName);
            if (hwnd != IntPtr.Zero) return hwnd;

            uint pid = GetCurrentProcessId();
            IntPtr found = IntPtr.Zero;
            EnumWindows((h, _) =>
            {
                if (!IsWindowVisible(h)) return true;
                GetWindowThreadProcessId(h, out uint wpid);
                if (wpid != pid) return true;
                found = h;
                return false;
            }, IntPtr.Zero);
            return found;
        }

        static void BootLog(string line)
        {
            try
            {
                var path = Path.GetFullPath(Path.Combine(Application.dataPath, "..", "overlay_boot.log"));
                File.AppendAllText(path, DateTime.Now.ToString("HH:mm:ss") + " " + line + "\n");
            }
            catch
            {
                // ignore
            }
        }

        void ApplyFeetLineToCamera(int windowHeight)
        {
            if (windowHeight <= 0) return;
            float frac = Mathf.Clamp(feetLineFromBottomPixels / (float)windowHeight, 0.02f, 0.25f);
            var follow = Camera.main != null ? Camera.main.GetComponent<ShanyaOverlayCamera>() : null;
            if (follow != null)
                follow.feetScreenFraction = frac;
        }

        static RectInt ResolveMonitorRect(int index)
        {
            IntPtr target = IntPtr.Zero;
            if (index <= 0)
            {
                GetCursorPos(out var pt);
                target = MonitorFromPoint(pt, MONITOR_DEFAULTTONEAREST);
            }
            else
            {
                int n = 0;
                EnumDisplayMonitors(IntPtr.Zero, IntPtr.Zero,
                    (IntPtr hMon, IntPtr hdc, ref RECT rc, IntPtr data) =>
                    {
                        n++;
                        if (n == index) target = hMon;
                        return true;
                    }, IntPtr.Zero);
            }
            if (target == IntPtr.Zero)
                target = MonitorFromPoint(new POINT { x = 0, y = 0 }, MONITOR_DEFAULTTOPRIMARY);

            var info = new MONITORINFO { cbSize = Marshal.SizeOf<MONITORINFO>() };
            GetMonitorInfo(target, ref info);
            return new RectInt(
                info.rcMonitor.left,
                info.rcMonitor.top,
                info.rcMonitor.right - info.rcMonitor.left,
                info.rcMonitor.bottom - info.rcMonitor.top);
        }

        const uint ChromaColorRef = 0x00FF00FF;

        const int GWL_STYLE = -16;
        const int GWL_EXSTYLE = -20;
        const int SW_SHOW = 5;
        const int SW_RESTORE = 9;
        const uint WS_POPUP = 0x80000000;
        const uint WS_VISIBLE = 0x10000000;
        const uint WS_EX_LAYERED = 0x00080000;
        const uint WS_EX_TRANSPARENT = 0x00000020;
        const uint WS_EX_TOPMOST = 0x00000008;
        const uint SWP_SHOWWINDOW = 0x0040;
        const uint SWP_FRAMECHANGED = 0x0020;
        const uint LWA_COLORKEY = 0x00000001;
        const uint MONITOR_DEFAULTTOPRIMARY = 0x00000001;
        const uint MONITOR_DEFAULTTONEAREST = 0x00000002;

        static readonly IntPtr HWND_TOPMOST = new IntPtr(-1);
        static readonly IntPtr HWND_NOTOPMOST = new IntPtr(-2);

        delegate bool MonitorEnumProc(IntPtr hMonitor, IntPtr hdcMonitor, ref RECT lprcMonitor, IntPtr dwData);
        delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

        [StructLayout(LayoutKind.Sequential)]
        struct RECT { public int left, top, right, bottom; }

        [StructLayout(LayoutKind.Sequential)]
        struct POINT { public int x, y; }

        [StructLayout(LayoutKind.Sequential)]
        struct MONITORINFO
        {
            public int cbSize;
            public RECT rcMonitor;
            public RECT rcWork;
            public uint dwFlags;
        }

        [StructLayout(LayoutKind.Sequential)]
        struct MARGINS
        {
            public int cxLeftWidth, cxRightWidth, cyTopHeight, cyBottomHeight;
        }

        [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        static extern IntPtr FindWindow(string lpClassName, string lpWindowName);

        [DllImport("user32.dll")]
        static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);

        [DllImport("user32.dll")]
        static extern bool IsWindowVisible(IntPtr hWnd);

        [DllImport("user32.dll")]
        static extern int ShowWindow(IntPtr hWnd, int nCmdShow);

        [DllImport("user32.dll")]
        static extern uint GetCurrentProcessId();

        [DllImport("user32.dll")]
        static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);

        [DllImport("user32.dll", EntryPoint = "SetWindowLong")]
        static extern int SetWindowLong32(IntPtr hWnd, int nIndex, uint dwNewLong);

        [DllImport("user32.dll", EntryPoint = "SetWindowLongPtr")]
        static extern IntPtr SetWindowLongPtr64(IntPtr hWnd, int nIndex, uint dwNewLong);

        static void SetWindowLong(IntPtr hWnd, int nIndex, uint dwNewLong)
        {
            if (IntPtr.Size == 8) SetWindowLongPtr64(hWnd, nIndex, dwNewLong);
            else SetWindowLong32(hWnd, nIndex, dwNewLong);
        }

        [DllImport("user32.dll", SetLastError = true)]
        static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter,
            int X, int Y, int cx, int cy, uint uFlags);

        [DllImport("user32.dll")]
        static extern bool SetLayeredWindowAttributes(IntPtr hwnd, uint crKey, byte bAlpha, uint dwFlags);

        [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr hWnd);
        [DllImport("user32.dll")] static extern bool GetCursorPos(out POINT lpPoint);

        [DllImport("user32.dll")]
        static extern IntPtr MonitorFromPoint(POINT pt, uint dwFlags);

        [DllImport("user32.dll")]
        static extern bool GetMonitorInfo(IntPtr hMonitor, ref MONITORINFO lpmi);

        [DllImport("user32.dll")]
        static extern bool EnumDisplayMonitors(IntPtr hdc, IntPtr lprcClip,
            MonitorEnumProc lpfnEnum, IntPtr dwData);

        [DllImport("Dwmapi.dll")]
        static extern uint DwmExtendFrameIntoClientArea(IntPtr hWnd, ref MARGINS margins);
#endif
    }
}
