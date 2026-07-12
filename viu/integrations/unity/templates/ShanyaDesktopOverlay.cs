using System;
using System.Collections;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using UnityEngine;
using UnityEngine.Rendering;

namespace Viu.Runtime
{
    /// <summary>
    /// Прозрачное окно на Windows (build).
    /// Primary: UpdateLayeredWindow (ULW_ALPHA) — ColorKey на Unity 6 / Win11 часто оставляет solid magenta.
    /// Fallback: SetLayeredWindowAttributes ColorKey + BitBlt (-force-d3d11-bitblt-model).
    /// Chroma: #FF0080 (не Unity missing #FF00FF).
    /// Baseline (не откатывать): docs/OVERLAY_BASELINE.md
    /// </summary>
    [DefaultExecutionOrder(-50)]
    public class ShanyaDesktopOverlay : MonoBehaviour
    {
        /// <summary>
        /// НЕ чистый magenta (1,0,1) — это цвет missing-shader в Unity.
        /// Дом с URP/Standard mismatch становился magenta и chroma-key его съедал.
        /// Ключ: #FF0080 (розово-красный), COLORREF 0x008000FF (BGR).
        /// </summary>
        public static readonly Color ChromaKey = new Color(1f, 0f, 0.5f, 1f);
        static readonly Color32 ChromaKey32 = new Color32(255, 0, 128, 255);

        /// <summary>Метка в overlay_boot.log — если нет runtime-rev=37, в exe старые скрипты.</summary>
        public const string RuntimeRev = "44";

        public bool fullScreenOverlay = true;
        public int stripHeightPixels = 280;
        public int feetLineFromBottomPixels = 72;
        public bool clickThrough = false;
        public bool alwaysOnTop = true;
        public int monitorIndex = 0;

        [Tooltip("Primary transparency: camera RT → AsyncGPUReadback → UpdateLayeredWindow.")]
        public bool useUpdateLayeredWindow = true;

        [Tooltip("Fallback if UpdateLayeredWindow init fails.")]
        public bool useColorKeyFallback = true;

        Camera _camera;

#if UNITY_STANDALONE_WIN && !UNITY_EDITOR
        IntPtr _hwnd;
        int _colorKeyAttempts;
        bool _colorKeyOk;
        bool _updateLayeredOk;
        string _transparencyMode = "none";

        RenderTexture _renderTexture;
        Color32[] _pixels;
        byte[] _bgra;
        bool _readbackPending;
        int _texW;
        int _texH;

        IntPtr _hdcScreen = IntPtr.Zero;
        IntPtr _hdcMem = IntPtr.Zero;
        IntPtr _hBitmap = IntPtr.Zero;
        IntPtr _pBits = IntPtr.Zero;
        IntPtr _oldBitmap = IntPtr.Zero;
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
            HardenCamera();
            LogSceneStats("Awake");
        }

        void Start()
        {
#if UNITY_STANDALONE_WIN && !UNITY_EDITOR
            BootLog("Start runtime-rev=" + RuntimeRev
                + " UpdateLayered=" + useUpdateLayeredWindow
                + " args=" + Environment.CommandLine);
            BootLog("gfx=" + SystemInfo.graphicsDeviceType
                + " " + SystemInfo.graphicsDeviceName);
            if (Environment.CommandLine.IndexOf("bitblt", StringComparison.OrdinalIgnoreCase) < 0)
            {
                BootLog("WARN: нет -force-d3d11-bitblt-model — нужен для ColorKey fallback. "
                    + "UpdateLayeredWindow primary не требует BitBlt. "
                    + "Запускай через LaunchOverlay.bat / .vbs");
            }
            StartCoroutine(ConfigureWindowWhenReady());
#endif
        }

        void OnDestroy()
        {
#if UNITY_STANDALONE_WIN && !UNITY_EDITOR
            ReleaseLayeredResources();
            if (_renderTexture != null)
            {
                if (_camera != null && _camera.targetTexture == _renderTexture)
                    _camera.targetTexture = null;
                _renderTexture.Release();
                Destroy(_renderTexture);
                _renderTexture = null;
            }
#endif
        }

        void Update()
        {
            if (Input.GetKeyDown(KeyCode.Escape))
                Application.Quit();

#if UNITY_STANDALONE_WIN && !UNITY_EDITOR
            if (_updateLayeredOk)
            {
                if (!_readbackPending && _renderTexture != null && _renderTexture.IsCreated())
                    RequestFrameReadback();
                return;
            }

            // ColorKey fallback: Unity/DXGI часто сбрасывает layered — переставляем ключ.
            if (_hwnd != IntPtr.Zero && _colorKeyAttempts > 0 && _colorKeyAttempts < 80
                && Time.frameCount % 15 == 0)
            {
                if (!_colorKeyOk || _colorKeyAttempts < 25)
                {
                    ApplyColorKey();
                    _colorKeyAttempts++;
                }
            }
#endif
        }

        void HardenCamera()
        {
            if (_camera == null)
                _camera = Camera.main;
            if (_camera == null)
                return;

            _camera.clearFlags = CameraClearFlags.SolidColor;
            // Exact byte chroma — float Color(1,0,0.5) can round off #FF0080.
            _camera.backgroundColor = ChromaKey32;
            _camera.allowHDR = false;
            _camera.allowMSAA = false;
        }

        void LogSceneStats(string tag)
        {
            var renderers = FindObjectsByType<Renderer>(FindObjectsSortMode.None);
            int enabled = 0;
            foreach (var r in renderers)
                if (r != null && r.enabled) enabled++;

            var shanya = FindShanyaRoot();
            GameObject home = null;
            foreach (var go in FindObjectsByType<GameObject>(FindObjectsSortMode.None))
            {
                if (go != null && go.name.StartsWith("Viu_Home_", StringComparison.Ordinal))
                {
                    home = go;
                    break;
                }
            }

            var shanyaName = shanya != null ? shanya.name : "нет";
            int homeEnabled = 0;
            int homeTotal = 0;
            if (home != null)
            {
                foreach (var r in home.GetComponentsInChildren<Renderer>(true))
                {
                    homeTotal++;
                    if (r != null && r.enabled) homeEnabled++;
                }
            }
            BootLog(
                $"{tag}: renderers={enabled}/{renderers.Length} shanya={(shanya != null)} "
                + $"name={shanyaName} home={(home != null ? home.name : "нет")} "
                + $"homeMesh={homeEnabled}/{homeTotal}");
        }

        static GameObject FindShanyaRoot()
        {
            var byName = GameObject.Find("Shanya_Erisa") ?? GameObject.Find("Shanya");
            if (byName != null) return byName;

            foreach (var loc in FindObjectsByType<ShanyaLocomotion>(FindObjectsSortMode.None))
            {
                if (loc != null && loc.gameObject != null)
                    return loc.gameObject;
            }

            foreach (var anim in FindObjectsByType<Animator>(FindObjectsSortMode.None))
            {
                if (anim == null || anim.gameObject == null) continue;
                var n = anim.gameObject.name.ToLowerInvariant();
                if (n.StartsWith("viu_home_", StringComparison.Ordinal)) continue;
                if (n.Contains("shanya") || n.Contains("erisa"))
                    return anim.gameObject;
            }
            return null;
        }

        static void BootLog(string line)
        {
            try
            {
                var path = Path.GetFullPath(Path.Combine(Application.dataPath, "..", "overlay_boot.log"));
                File.AppendAllText(path, DateTime.Now.ToString("HH:mm:ss") + " " + line + "\n", Encoding.UTF8);
            }
            catch
            {
                // ignore
            }
        }

#if UNITY_STANDALONE_WIN && !UNITY_EDITOR
        IEnumerator ConfigureWindowWhenReady()
        {
            for (int i = 0; i < 240 && _hwnd == IntPtr.Zero; i++)
            {
                _hwnd = ResolveGameWindow();
                if (_hwnd == IntPtr.Zero)
                    yield return null;
            }

            if (_hwnd == IntPtr.Zero)
            {
                BootLog("ERROR: HWND не найден");
                yield break;
            }

            BootLog("HWND ok");
            ApplyWindowGeometry();
            yield return new WaitForEndOfFrame();

            HardenCamera();
            ApplyTransparencyMode();
            LogSceneStats("AfterWindow");
        }

        void ApplyTransparencyMode()
        {
            EnsureLayeredExStyle();

            if (useUpdateLayeredWindow && TryEnableUpdateLayeredWindow())
            {
                _updateLayeredOk = true;
                _colorKeyOk = false;
                _transparencyMode = "UpdateLayeredWindow";
                BootLog("Transparency=UpdateLayeredWindow (per-pixel alpha) OK runtime-rev=" + RuntimeRev
                    + " Esc=выход");
                return;
            }

            if (useColorKeyFallback)
            {
                ApplyColorKey();
                _colorKeyAttempts = 1;
                _transparencyMode = "ColorKey";
                BootLog("Transparency=ColorKey fallback (UpdateLayered failed/off) — "
                    + "может остаться solid magenta на Unity 6/Win11");
                BootLog("ColorKey pass 1, Esc=выход");
                return;
            }

            BootLog("ERROR: no transparency mode applied");
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

            long style = WS_POPUP | WS_VISIBLE;
            SetWindowLong(_hwnd, GWL_STYLE, (uint)style);

            // OR к существующим exstyle — не затирать флаги Unity.
            EnsureLayeredExStyle();

            SetWindowPos(_hwnd, alwaysOnTop ? HWND_TOPMOST : HWND_NOTOPMOST,
                x, y, w, h, SWP_SHOWWINDOW | SWP_FRAMECHANGED);

            ApplyFeetLineToCamera(h);
            SetForegroundWindow(_hwnd);

            BootLog($"Geometry {w}x{h} at {x},{y}");
        }

        void EnsureLayeredExStyle()
        {
            uint ex = (uint)GetWindowLong(_hwnd, GWL_EXSTYLE);
            ex |= WS_EX_LAYERED;
            if (alwaysOnTop) ex |= WS_EX_TOPMOST;
            else ex &= ~WS_EX_TOPMOST;
            if (clickThrough) ex |= WS_EX_TRANSPARENT;
            else ex &= ~WS_EX_TRANSPARENT;
            SetWindowLong(_hwnd, GWL_EXSTYLE, ex);
        }

        bool TryEnableUpdateLayeredWindow()
        {
            try
            {
                HardenCamera();
                EnsureRenderTargets();
                if (_camera == null)
                {
                    BootLog("ERROR: UpdateLayered — нет Camera.main");
                    return false;
                }

                _camera.targetTexture = _renderTexture;
                _camera.Render();

                if (!EnsureGdiSurfaces(_texW, _texH))
                {
                    BootLog("ERROR: CreateDIBSection failed");
                    _camera.targetTexture = null;
                    return false;
                }

                // First paint fully transparent so user never sees solid magenta.
                if (_bgra != null)
                    Array.Clear(_bgra, 0, _bgra.Length);
                PushLayeredFrame();
                BootLog("UpdateLayeredWindow init OK " + _texW + "x" + _texH);
                return true;
            }
            catch (Exception ex)
            {
                BootLog("ERROR: UpdateLayeredWindow init: " + ex.Message);
                if (_camera != null)
                    _camera.targetTexture = null;
                return false;
            }
        }

        void ApplyColorKey()
        {
            if (_hwnd == IntPtr.Zero) return;

            if (_camera != null)
                _camera.targetTexture = null;

            EnsureLayeredExStyle();

            // С BitBlt: margins=-1 + ColorKey — классический рецепт Unity transparent window.
            var margins = new MARGINS
            {
                cxLeftWidth = -1,
                cxRightWidth = -1,
                cyTopHeight = -1,
                cyBottomHeight = -1,
            };
            DwmExtendFrameIntoClientArea(_hwnd, ref margins);

            bool ok = SetLayeredWindowAttributes(_hwnd, ChromaColorRef, 0, LWA_COLORKEY);
            _colorKeyOk = ok;
            if (_colorKeyAttempts <= 1 || !ok || _colorKeyAttempts % 8 == 0)
            {
                BootLog("SetLayeredWindowAttributes=" + ok + " err=" + Marshal.GetLastWin32Error()
                    + " key=#FF0080 margins=-1 attempt=" + _colorKeyAttempts
                    + " gfx=" + SystemInfo.graphicsDeviceType
                    + " (фон должен быть прозрачным, не магента)");
            }
        }

        void EnsureRenderTargets()
        {
            int w = Mathf.Max(2, Screen.width);
            int h = Mathf.Max(2, Screen.height);
            if (_renderTexture != null && _texW == w && _texH == h && _renderTexture.IsCreated())
                return;

            if (_renderTexture != null)
            {
                _renderTexture.Release();
                Destroy(_renderTexture);
            }

            _texW = w;
            _texH = h;
            _renderTexture = new RenderTexture(w, h, 24, RenderTextureFormat.ARGB32)
            {
                antiAliasing = 1,
                filterMode = FilterMode.Point,
                wrapMode = TextureWrapMode.Clamp,
                useMipMap = false,
                autoGenerateMips = false,
                name = "ViuOverlayRT",
            };
            _renderTexture.Create();
            _pixels = new Color32[w * h];
            _bgra = new byte[w * h * 4];
        }

        bool EnsureGdiSurfaces(int w, int h)
        {
            ReleaseLayeredResources();

            _hdcScreen = GetDC(IntPtr.Zero);
            if (_hdcScreen == IntPtr.Zero)
                return false;

            _hdcMem = CreateCompatibleDC(_hdcScreen);
            if (_hdcMem == IntPtr.Zero)
                return false;

            var bmi = new BITMAPINFO();
            bmi.bmiHeader.biSize = (uint)Marshal.SizeOf<BITMAPINFOHEADER>();
            bmi.bmiHeader.biWidth = w;
            // Positive height = bottom-up DIB, matches Unity texture layout (no Y flip).
            bmi.bmiHeader.biHeight = h;
            bmi.bmiHeader.biPlanes = 1;
            bmi.bmiHeader.biBitCount = 32;
            bmi.bmiHeader.biCompression = BI_RGB;

            _hBitmap = CreateDIBSection(_hdcMem, ref bmi, DIB_RGB_COLORS, out _pBits, IntPtr.Zero, 0);
            if (_hBitmap == IntPtr.Zero || _pBits == IntPtr.Zero)
                return false;

            _oldBitmap = SelectObject(_hdcMem, _hBitmap);
            return true;
        }

        void ReleaseLayeredResources()
        {
            if (_hdcMem != IntPtr.Zero && _oldBitmap != IntPtr.Zero)
            {
                SelectObject(_hdcMem, _oldBitmap);
                _oldBitmap = IntPtr.Zero;
            }

            if (_hBitmap != IntPtr.Zero)
            {
                DeleteObject(_hBitmap);
                _hBitmap = IntPtr.Zero;
                _pBits = IntPtr.Zero;
            }

            if (_hdcMem != IntPtr.Zero)
            {
                DeleteDC(_hdcMem);
                _hdcMem = IntPtr.Zero;
            }

            if (_hdcScreen != IntPtr.Zero)
            {
                ReleaseDC(IntPtr.Zero, _hdcScreen);
                _hdcScreen = IntPtr.Zero;
            }
        }

        void RequestFrameReadback()
        {
            if (_renderTexture == null || !_renderTexture.IsCreated())
                return;

            if (Screen.width != _texW || Screen.height != _texH)
            {
                EnsureRenderTargets();
                if (_camera != null)
                    _camera.targetTexture = _renderTexture;
                if (!EnsureGdiSurfaces(_texW, _texH))
                {
                    BootLog("ERROR: GDI resize failed");
                    return;
                }
            }

            _readbackPending = true;
            AsyncGPUReadback.Request(_renderTexture, 0, TextureFormat.RGBA32, OnGpuReadback);
        }

        void OnGpuReadback(AsyncGPUReadbackRequest request)
        {
            _readbackPending = false;
            if (request.hasError || !_updateLayeredOk)
                return;

            var data = request.GetData<Color32>();
            if (!data.IsCreated || data.Length != _pixels.Length)
                return;

            data.CopyTo(_pixels);
            ConvertChromaToBgra();
            PushLayeredFrame();
        }

        void ConvertChromaToBgra()
        {
            byte mr = ChromaKey32.r;
            byte mg = ChromaKey32.g;
            byte mb = ChromaKey32.b;
            int n = _pixels.Length;
            for (int i = 0; i < n; i++)
            {
                Color32 c = _pixels[i];
                int o = i * 4;
                if (c.r == mr && c.g == mg && c.b == mb)
                {
                    _bgra[o] = 0;
                    _bgra[o + 1] = 0;
                    _bgra[o + 2] = 0;
                    _bgra[o + 3] = 0;
                }
                else
                {
                    _bgra[o] = c.b;
                    _bgra[o + 1] = c.g;
                    _bgra[o + 2] = c.r;
                    _bgra[o + 3] = 255;
                }
            }
        }

        void PushLayeredFrame()
        {
            if (_hwnd == IntPtr.Zero || _hdcMem == IntPtr.Zero || _hBitmap == IntPtr.Zero || _bgra == null)
                return;

            var bmi = new BITMAPINFO();
            bmi.bmiHeader.biSize = (uint)Marshal.SizeOf<BITMAPINFOHEADER>();
            bmi.bmiHeader.biWidth = _texW;
            bmi.bmiHeader.biHeight = _texH;
            bmi.bmiHeader.biPlanes = 1;
            bmi.bmiHeader.biBitCount = 32;
            bmi.bmiHeader.biCompression = BI_RGB;

            SetDIBits(_hdcMem, _hBitmap, 0, (uint)_texH, _bgra, ref bmi, DIB_RGB_COLORS);

            var size = new SIZE { cx = _texW, cy = _texH };
            var srcPt = new POINT { x = 0, y = 0 };
            var blend = new BLENDFUNCTION
            {
                BlendOp = 0, // AC_SRC_OVER
                BlendFlags = 0,
                SourceConstantAlpha = 255,
                AlphaFormat = 1, // AC_SRC_ALPHA
            };

            // Do NOT call SetLayeredWindowAttributes when using ULW_ALPHA — they conflict.
            bool ok = UpdateLayeredWindow(
                _hwnd,
                _hdcScreen,
                IntPtr.Zero,
                ref size,
                _hdcMem,
                ref srcPt,
                0,
                ref blend,
                ULW_ALPHA);

            if (!ok && Time.frameCount % 60 == 0)
            {
                BootLog("WARN: UpdateLayeredWindow=false err=" + Marshal.GetLastWin32Error());
            }
        }

        static IntPtr ResolveGameWindow()
        {
            // GetActiveWindow в batch/launcher часто 0 — но в player после фокуса ок.
            var hwnd = GetActiveWindow();
            if (hwnd != IntPtr.Zero) return hwnd;

            hwnd = FindWindow("UnityWndClass", null);
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

        void ApplyFeetLineToCamera(int windowHeight)
        {
            if (windowHeight <= 0) return;
            float frac = Mathf.Clamp(feetLineFromBottomPixels / (float)windowHeight, 0.05f, 0.25f);
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

        const uint ChromaColorRef = 0x008000FF; // #FF0080 BGR — не Unity missing-magenta

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
        const uint ULW_ALPHA = 0x00000002;
        const uint BI_RGB = 0;
        const uint DIB_RGB_COLORS = 0;
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
        struct SIZE { public int cx, cy; }

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

        [StructLayout(LayoutKind.Sequential, Pack = 1)]
        struct BLENDFUNCTION
        {
            public byte BlendOp;
            public byte BlendFlags;
            public byte SourceConstantAlpha;
            public byte AlphaFormat;
        }

        [StructLayout(LayoutKind.Sequential)]
        struct BITMAPINFOHEADER
        {
            public uint biSize;
            public int biWidth;
            public int biHeight;
            public ushort biPlanes;
            public ushort biBitCount;
            public uint biCompression;
            public uint biSizeImage;
            public int biXPelsPerMeter;
            public int biYPelsPerMeter;
            public uint biClrUsed;
            public uint biClrImportant;
        }

        [StructLayout(LayoutKind.Sequential)]
        struct BITMAPINFO
        {
            public BITMAPINFOHEADER bmiHeader;
        }

        [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        static extern IntPtr FindWindow(string lpClassName, string lpWindowName);

        [DllImport("user32.dll")]
        static extern IntPtr GetActiveWindow();

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

        [DllImport("user32.dll", EntryPoint = "GetWindowLong")]
        static extern int GetWindowLong32(IntPtr hWnd, int nIndex);

        [DllImport("user32.dll", EntryPoint = "GetWindowLongPtr")]
        static extern IntPtr GetWindowLongPtr64(IntPtr hWnd, int nIndex);

        static void SetWindowLong(IntPtr hWnd, int nIndex, uint dwNewLong)
        {
            if (IntPtr.Size == 8) SetWindowLongPtr64(hWnd, nIndex, dwNewLong);
            else SetWindowLong32(hWnd, nIndex, dwNewLong);
        }

        static int GetWindowLong(IntPtr hWnd, int nIndex)
        {
            if (IntPtr.Size == 8) return (int)GetWindowLongPtr64(hWnd, nIndex);
            return GetWindowLong32(hWnd, nIndex);
        }

        [DllImport("user32.dll", SetLastError = true)]
        static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter,
            int X, int Y, int cx, int cy, uint uFlags);

        [DllImport("user32.dll", SetLastError = true)]
        static extern bool SetLayeredWindowAttributes(IntPtr hwnd, uint crKey, byte bAlpha, uint dwFlags);

        [DllImport("user32.dll", SetLastError = true)]
        static extern bool UpdateLayeredWindow(
            IntPtr hwnd, IntPtr hdcDst, IntPtr pptDst, ref SIZE psize,
            IntPtr hdcSrc, ref POINT pptSrc, uint crKey, ref BLENDFUNCTION pblend, uint dwFlags);

        [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr hWnd);
        [DllImport("user32.dll")] static extern bool GetCursorPos(out POINT lpPoint);
        [DllImport("user32.dll")] static extern IntPtr GetDC(IntPtr hWnd);
        [DllImport("user32.dll")] static extern int ReleaseDC(IntPtr hWnd, IntPtr hDC);

        [DllImport("user32.dll")]
        static extern IntPtr MonitorFromPoint(POINT pt, uint dwFlags);

        [DllImport("user32.dll")]
        static extern bool GetMonitorInfo(IntPtr hMonitor, ref MONITORINFO lpmi);

        [DllImport("user32.dll")]
        static extern bool EnumDisplayMonitors(IntPtr hdc, IntPtr lprcClip,
            MonitorEnumProc lpfnEnum, IntPtr dwData);

        [DllImport("Dwmapi.dll")]
        static extern uint DwmExtendFrameIntoClientArea(IntPtr hWnd, ref MARGINS margins);

        [DllImport("gdi32.dll")]
        static extern IntPtr CreateCompatibleDC(IntPtr hdc);

        [DllImport("gdi32.dll")]
        static extern bool DeleteDC(IntPtr hdc);

        [DllImport("gdi32.dll")]
        static extern IntPtr CreateDIBSection(
            IntPtr hdc, ref BITMAPINFO pbmi, uint iUsage, out IntPtr ppvBits, IntPtr hSection, uint dwOffset);

        [DllImport("gdi32.dll")]
        static extern IntPtr SelectObject(IntPtr hdc, IntPtr hgdiobj);

        [DllImport("gdi32.dll")]
        static extern bool DeleteObject(IntPtr hObject);

        [DllImport("gdi32.dll")]
        static extern int SetDIBits(
            IntPtr hdc, IntPtr hbmp, uint uStartScan, uint cScanLines,
            byte[] lpvBits, ref BITMAPINFO lpbmi, uint fuColorUse);
#endif
    }
}
