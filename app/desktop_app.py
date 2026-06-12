import threading
import time
import traceback
import ctypes
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

import server

APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
ASSETS = (Path(getattr(sys, "_MEIPASS", APP_DIR)) / "assets") if getattr(sys, "frozen", False) else APP_DIR / "assets"
APP_ICON_PNG = ASSETS / "app-icon.png"
APP_ICON = ASSETS / "app-icon.ico"


class DemoToolApp(tk.Tk):
    OVERLAY_TRANSPARENT_COLOR = "#010203"
    OVERLAY_PANEL_BG = "#07111f"
    OVERLAY_PANEL_STROKE = "#1e3a4a"
    VK_KEYS = {
        "F1": 0x70,
        "F2": 0x71,
        "F3": 0x72,
        "F7": 0x76,
        "F8": 0x77,
        "F9": 0x78,
        "F10": 0x79,
        "F11": 0x7A,
        "F4": 0x73,
    }

    def __init__(self):
        super().__init__()
        self.title("Gasi's CS2 Demo Tool")
        self.geometry("1280x820")
        self.minsize(980, 720)

        self.players = []
        self.player_by_label = {}
        self.render_takes = []
        self.take_by_label = {}
        self.path_status_labels = {}
        self.overlay = None
        self.overlay_status = tk.StringVar(value="Idle")
        self.overlay_last_action = tk.StringVar(value="")
        self.overlay_position = (24, 24)
        self.overlay_widgets = {}
        self.overlay_buttons = {}
        self.overlay_button_specs = {}
        self.overlay_ui_scale = 1.0
        self.overlay_shell = None
        self.overlay_status_panel = None
        self.overlay_spacer = None
        self.overlay_dock = None
        self.overlay_settings_panel = None
        self.overlay_settings_body = None
        self.overlay_menu = None
        self.overlay_collapsed = False
        self.overlay_recording = False
        self.overlay_paused = False
        self.overlay_pulse = 0
        self.overlay_polling = False
        self.overlay_jump_seconds = 10
        self.recording_output_base = None
        self._last_recording_sample = None
        self.last_input_error = ""
        self.demo_ready_marker = None
        self.demo_ready_log = None
        self.demo_ready_logs = []
        self.demo_ready_dump_dirs = []
        self.demo_ready_text = "CS2_DEMO_TOOL_DEMO_LOADED"
        self.demo_log_name = ""
        self.demo_ready = False
        self.cs2_session_active = False
        self.cs2_was_seen = False
        self.cs2_session_started_at = 0

        self.vars = {
            "demoPath": tk.StringVar(),
            "hlaePath": tk.StringVar(),
            "cs2Path": tk.StringVar(),
            "ffmpegPath": tk.StringVar(),
            "outputDir": tk.StringVar(value=str(server.RECORDINGS)),
            "sessionName": tk.StringVar(),
            "pov": tk.StringVar(value="Auto / current POV"),
            "manualPov": tk.StringVar(),
            "framerate": tk.StringVar(value="60"),
            "resolution": tk.StringVar(value="1920x1080"),
            "fov": tk.StringVar(value="100"),
            "soundEnabled": tk.BooleanVar(value=True),
            "syncCueEnabled": tk.BooleanVar(value=True),
            "motionBlurEnabled": tk.BooleanVar(value=False),
            "motionBlurAmount": tk.DoubleVar(value=0.7),
            "motionBlurMethod": tk.StringVar(value="rectangle"),
            "motionBlurSampleFps": tk.StringVar(value="1080"),
            "videoQuality": tk.StringVar(value="9"),
            "videoPreset": tk.StringVar(value="ultrafast"),
            "hudEnabled": tk.BooleanVar(value=False),
            "deathNoticesEnabled": tk.BooleanVar(value=True),
            "crosshairEnabled": tk.BooleanVar(value=False),
            "xrayEnabled": tk.BooleanVar(value=False),
            "radarEnabled": tk.BooleanVar(value=False),
            "nametagsEnabled": tk.BooleanVar(value=False),
            "hideTeamNames": tk.BooleanVar(value=True),
            "trueViewEnabled": tk.BooleanVar(value=False),
            "muteDialog": tk.BooleanVar(value=True),
            "unmuteAutomutedPlayers": tk.BooleanVar(value=True),
            "hidePlayerPings": tk.BooleanVar(value=True),
            "hideSpecBindings": tk.BooleanVar(value=True),
            "hideObserverCrosshair": tk.BooleanVar(value=True),
            "hideKillAssists": tk.BooleanVar(value=False),
            "deathmsgHighlightLocalPlayer": tk.BooleanVar(value=False),
            "deathmsgBlockOtherKills": tk.BooleanVar(value=False),
            "deathmsgLongLifetime": tk.BooleanVar(value=False),
            "recordingFormat": tk.StringVar(value="ffmpeg"),
            "deleteFramesAfterEncode": tk.BooleanVar(value=False),
            "selectedTake": tk.StringVar(value="Latest take"),
            "audioTrimMs": tk.StringVar(value="0"),
            "overlayEnabled": tk.BooleanVar(value=True),
        }
        self.app_icon_photo = None
        if APP_ICON_PNG.exists():
            try:
                self.app_icon_photo = tk.PhotoImage(file=str(APP_ICON_PNG))
            except tk.TclError:
                self.app_icon_photo = None
        self.apply_app_icon(self)

        self._build_styles()
        self._build_ui()
        for key in ("demoPath", "outputDir", "hlaePath", "cs2Path", "ffmpegPath"):
            self.vars[key].trace_add("write", lambda *_args: self.update_path_status())
        self.refresh_status()

    def compute_overlay_scale(self):
        height = max(720, self.winfo_screenheight())
        return max(0.85, min(1.65, height / 1080))

    def os(self, value):
        return max(1, int(round(value * self.overlay_ui_scale)))

    def overlay_font(self, family, size, weight=None):
        font = (family, self.os(size))
        return (*font, weight) if weight else font

    def _build_styles(self):
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"))
        style.configure("Section.TLabelframe.Label", font=("Segoe UI", 10, "bold"))
        style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"))

    def apply_app_icon(self, window):
        if APP_ICON.exists():
            try:
                window.iconbitmap(str(APP_ICON))
            except tk.TclError:
                pass
        if self.app_icon_photo is not None:
            try:
                window.iconphoto(False, self.app_icon_photo)
            except tk.TclError:
                pass

    def _build_ui(self):
        root = ttk.Frame(self, padding=16)
        root.pack(fill="both", expand=True)

        header = ttk.Frame(root)
        header.pack(fill="x")
        ttk.Label(header, text="Gasi's CS2 Demo Tool", style="Title.TLabel").pack(side="left")
        ttk.Button(header, text="Refresh status", command=self.refresh_status).pack(side="right")

        main = ttk.PanedWindow(root, orient="horizontal")
        main.pack(fill="both", expand=True, pady=(14, 0))

        left = ttk.Frame(main, padding=(0, 0, 10, 0))
        right = ttk.Frame(main, padding=(10, 0, 0, 0))
        main.add(left, weight=4)
        main.add(right, weight=3)

        self._build_paths(left)
        self._build_recording_options(left)
        self._build_status(right)
        self._build_output(right)

    def _build_paths(self, parent):
        box = ttk.LabelFrame(parent, text="Files", style="Section.TLabelframe", padding=12)
        box.pack(fill="x", pady=(0, 12))

        self._path_row(box, "Demo file", "demoPath", self.select_demo)
        self._path_row(box, "Output folder", "outputDir", self.select_output_dir)
        self._path_row(box, "HLAE executable", "hlaePath", lambda: self.select_exe("hlae"))
        self._path_row(box, "CS2 executable", "cs2Path", lambda: self.select_exe("cs2"))
        self._path_row(box, "FFmpeg executable", "ffmpegPath", lambda: self.select_exe("ffmpeg"))

        tools = ttk.Frame(box)
        tools.pack(fill="x", pady=(8, 0))
        ttk.Button(tools, text="Install / update HLAE", command=lambda: self.run_task("Installing HLAE...", self.install_hlae)).pack(side="left")
        ttk.Button(tools, text="Install FFmpeg", command=lambda: self.run_task("Installing FFmpeg...", self.install_ffmpeg)).pack(side="left", padx=(8, 0))

    def _path_row(self, parent, label, key, command):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=4)
        status = tk.Label(row, text="X", width=2, fg="#b00020", bg=self.cget("bg"), font=("Segoe UI", 10, "bold"))
        status.pack(side="left")
        self.path_status_labels[key] = status
        ttk.Label(row, text=label, width=14).pack(side="left")
        ttk.Entry(row, textvariable=self.vars[key]).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(row, text="Browse", command=command).pack(side="right")

    def _build_recording_options(self, parent):
        settings = ttk.LabelFrame(parent, text="Workflow", style="Section.TLabelframe", padding=8)
        settings.pack(fill="x", pady=(0, 12))
        notebook = ttk.Notebook(settings)
        notebook.pack(fill="x")

        recording = ttk.Frame(notebook, padding=12)
        encoding = ttk.Frame(notebook, padding=12)
        about = ttk.Frame(notebook, padding=12)
        notebook.add(recording, text="Recording")
        notebook.add(encoding, text="Encoding")
        notebook.add(about, text="About")

        recording_tabs = ttk.Notebook(recording)
        recording_tabs.pack(fill="x")
        capture = ttk.Frame(recording_tabs, padding=12)
        audio = ttk.Frame(recording_tabs, padding=12)
        hud = ttk.Frame(recording_tabs, padding=12)
        deathmsg = ttk.Frame(recording_tabs, padding=12)
        hlae = ttk.Frame(recording_tabs, padding=12)
        recording_tabs.add(capture, text="Capture")
        recording_tabs.add(audio, text="Audio")
        recording_tabs.add(hud, text="HUD")
        recording_tabs.add(deathmsg, text="Kill feed")
        recording_tabs.add(hlae, text="HLAE")

        grid = ttk.Frame(capture)
        grid.pack(fill="x")
        for column in range(4):
            grid.columnconfigure(column, weight=1)

        ttk.Label(grid, text="POV").grid(row=0, column=0, sticky="w")
        self.pov_combo = ttk.Combobox(grid, textvariable=self.vars["pov"], state="readonly", values=["Auto / current POV", "Manual name / slot..."])
        self.pov_combo.grid(row=1, column=0, columnspan=2, sticky="ew", padx=(0, 10), pady=(2, 8))
        self.pov_combo.bind("<<ComboboxSelected>>", lambda _event: self.update_manual_pov_state())

        ttk.Label(grid, text="Manual POV").grid(row=0, column=2, sticky="w")
        self.manual_pov_entry = ttk.Entry(grid, textvariable=self.vars["manualPov"])
        self.manual_pov_entry.grid(row=1, column=2, columnspan=2, sticky="ew", pady=(2, 8))

        ttk.Label(grid, text="Framerate").grid(row=2, column=0, sticky="w")
        ttk.Combobox(grid, textvariable=self.vars["framerate"], values=["60", "120", "300", "600", "1000"], state="readonly").grid(row=3, column=0, sticky="ew", padx=(0, 10), pady=(2, 8))

        ttk.Label(grid, text="Resolution").grid(row=2, column=1, sticky="w")
        ttk.Combobox(grid, textvariable=self.vars["resolution"], values=["1920x1080", "2560x1440", "3840x2160", "1280x720"], state="readonly").grid(row=3, column=1, sticky="ew", padx=(0, 10), pady=(2, 8))

        ttk.Label(grid, text="FOV").grid(row=2, column=2, sticky="w")
        ttk.Entry(grid, textvariable=self.vars["fov"]).grid(row=3, column=2, sticky="ew", padx=(0, 10), pady=(2, 8))

        ttk.Label(grid, text="Output mode").grid(row=2, column=3, sticky="w")
        ttk.Combobox(grid, textvariable=self.vars["recordingFormat"], values=["ffmpeg", "frames"], state="readonly").grid(row=3, column=3, sticky="ew", pady=(2, 8))

        audio_grid = ttk.Frame(audio)
        audio_grid.pack(fill="x")
        for column in range(4):
            audio_grid.columnconfigure(column, weight=1)
        ttk.Checkbutton(audio_grid, text="Sound on", variable=self.vars["soundEnabled"]).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(audio_grid, text="Start sync cue", variable=self.vars["syncCueEnabled"]).grid(row=0, column=1, sticky="w")
        ttk.Checkbutton(audio_grid, text="Mute radio dialog", variable=self.vars["muteDialog"]).grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Checkbutton(audio_grid, text="Unmute automuted players", variable=self.vars["unmuteAutomutedPlayers"]).grid(row=1, column=1, columnspan=2, sticky="w", pady=(8, 0))

        hud_grid = ttk.Frame(hud)
        hud_grid.pack(fill="x")
        for column in range(4):
            hud_grid.columnconfigure(column, weight=1)
        ttk.Checkbutton(hud_grid, text="HUD", variable=self.vars["hudEnabled"]).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(hud_grid, text="Kill feed", variable=self.vars["deathNoticesEnabled"]).grid(row=0, column=1, sticky="w")
        ttk.Checkbutton(hud_grid, text="Crosshair", variable=self.vars["crosshairEnabled"]).grid(row=0, column=2, sticky="w")
        ttk.Checkbutton(hud_grid, text="X-ray", variable=self.vars["xrayEnabled"]).grid(row=1, column=0, sticky="w")
        ttk.Checkbutton(hud_grid, text="Radar", variable=self.vars["radarEnabled"]).grid(row=1, column=1, sticky="w")
        ttk.Checkbutton(hud_grid, text="Nametags", variable=self.vars["nametagsEnabled"]).grid(row=1, column=2, sticky="w")
        ttk.Checkbutton(hud_grid, text="TrueView status", variable=self.vars["trueViewEnabled"]).grid(row=1, column=3, sticky="w")
        ttk.Checkbutton(hud_grid, text="Hide teammate names", variable=self.vars["hideTeamNames"]).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Checkbutton(hud_grid, text="Remove player pings", variable=self.vars["hidePlayerPings"]).grid(row=2, column=2, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Checkbutton(hud_grid, text="Hide GOTV bindings", variable=self.vars["hideSpecBindings"]).grid(row=3, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(hud_grid, text="Hide observer crosshair", variable=self.vars["hideObserverCrosshair"]).grid(row=3, column=2, columnspan=2, sticky="w")
        ttk.Checkbutton(hud_grid, text="Hide kill assists", variable=self.vars["hideKillAssists"]).grid(row=4, column=0, columnspan=2, sticky="w")

        deathmsg_grid = ttk.Frame(deathmsg)
        deathmsg_grid.pack(fill="x")
        for column in range(3):
            deathmsg_grid.columnconfigure(column, weight=1)
        ttk.Checkbutton(deathmsg_grid, text="Highlight POV kills", variable=self.vars["deathmsgHighlightLocalPlayer"]).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(deathmsg_grid, text="Block other kills", variable=self.vars["deathmsgBlockOtherKills"]).grid(row=0, column=1, sticky="w")
        ttk.Checkbutton(deathmsg_grid, text="Longer killfeed lifetime", variable=self.vars["deathmsgLongLifetime"]).grid(row=0, column=2, sticky="w")

        hlae_grid = ttk.Frame(hlae)
        hlae_grid.pack(fill="x")
        for column in range(4):
            hlae_grid.columnconfigure(column, weight=1)
        ttk.Checkbutton(hlae_grid, text="HLAE motion blur", variable=self.vars["motionBlurEnabled"]).grid(row=0, column=0, columnspan=2, sticky="w")

        ttk.Label(hlae_grid, text="Quality CRF").grid(row=0, column=2, sticky="w")
        ttk.Combobox(hlae_grid, textvariable=self.vars["videoQuality"], values=["1", "4", "9", "12", "16", "18", "23"], state="readonly").grid(row=1, column=2, sticky="ew", padx=(0, 10), pady=(2, 8))

        ttk.Label(hlae_grid, text="Preset").grid(row=0, column=3, sticky="w")
        ttk.Combobox(hlae_grid, textvariable=self.vars["videoPreset"], values=["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow"], state="readonly").grid(row=1, column=3, sticky="ew", pady=(2, 8))

        ttk.Label(hlae_grid, text="Blur method").grid(row=2, column=3, sticky="w")
        ttk.Combobox(hlae_grid, textvariable=self.vars["motionBlurMethod"], values=["rectangle"], state="readonly").grid(row=3, column=3, sticky="ew", pady=(2, 8))

        ttk.Label(hlae_grid, text="Blur Exposure/Strength").grid(row=2, column=0, sticky="w")
        ttk.Scale(hlae_grid, variable=self.vars["motionBlurAmount"], from_=0.0, to=1.0, command=self.update_blur_amount_label).grid(row=3, column=0, columnspan=2, sticky="ew", padx=(0, 10), pady=(2, 8))
        self.blur_amount_label = ttk.Label(hlae_grid, text="0.70")
        self.blur_amount_label.grid(row=3, column=2, sticky="w", pady=(2, 8))

        ttk.Label(hlae_grid, text="Blur sample FPS").grid(row=4, column=0, sticky="w")
        ttk.Combobox(hlae_grid, textvariable=self.vars["motionBlurSampleFps"], values=["240", "300", "600", "1080", "1440", "2160"], state="readonly").grid(row=5, column=0, sticky="ew", pady=(2, 8))

        recording_actions = ttk.Frame(recording)
        recording_actions.pack(fill="x", pady=(12, 0))
        ttk.Button(recording_actions, text="Open demo in HLAE", style="Primary.TButton", command=self.open_demo_requested).pack(side="left")
        ttk.Button(recording_actions, text="Generate config only", command=lambda: self.run_task("Generating config...", self.generate_config)).pack(side="left", padx=(8, 0))
        ttk.Button(recording_actions, text="Refresh in game", command=lambda: self.run_task("Refreshing in-game options...", self.refresh_in_game)).pack(side="left", padx=(8, 0))

        post_grid = ttk.Frame(encoding)
        post_grid.pack(fill="x")
        for column in range(5):
            post_grid.columnconfigure(column, weight=1)
        ttk.Label(post_grid, text="Take").grid(row=0, column=0, sticky="w")
        self.take_combo = ttk.Combobox(post_grid, textvariable=self.vars["selectedTake"], values=["Latest take"], state="readonly")
        self.take_combo.grid(row=1, column=0, columnspan=4, sticky="ew", padx=(0, 10), pady=(2, 8))
        ttk.Button(post_grid, text="Refresh takes", command=lambda: self.run_task("Refreshing takes...", self.refresh_takes)).grid(row=1, column=4, sticky="ew", pady=(2, 8))

        ttk.Label(post_grid, text="Extra audio trim ms").grid(row=2, column=0, sticky="w")
        ttk.Entry(post_grid, textvariable=self.vars["audioTrimMs"]).grid(row=3, column=0, columnspan=2, sticky="ew", padx=(0, 10), pady=(2, 0))

        encoding_actions = ttk.Frame(encoding)
        encoding_actions.pack(fill="x", pady=(12, 0))
        ttk.Button(encoding_actions, text="Encode / mux", style="Primary.TButton", command=lambda: self.run_task("Encoding selected take...", self.encode_latest)).pack(side="left")

        about_header = ttk.Frame(about)
        about_header.pack(fill="x", pady=(0, 14))
        self.about_icon_photo = None
        if APP_ICON_PNG.exists():
            try:
                self.about_icon_photo = tk.PhotoImage(file=str(APP_ICON_PNG)).subsample(12, 12)
                ttk.Label(about_header, image=self.about_icon_photo).pack(side="left", padx=(0, 12))
            except tk.TclError:
                self.about_icon_photo = None

        title_block = ttk.Frame(about_header)
        title_block.pack(side="left", fill="x", expand=True)
        ttk.Label(title_block, text="Gasi´s Demo Tool", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(title_block, text="Version 1.1.0").pack(anchor="w")

        about_text = (
            "Made by Gasi (https://github.com/ChaoticGasi)\n"
            "Use this tool at your own risk.\n\n"
            "This tool uses FFMPEG (https://www.ffmpeg.org/) and HLAE "
            "(https://github.com/advancedfx/advancedfx).\n"
            "Special thanks to https://github.com/abandonedpools for the HLAE Config Template."
        )
        ttk.Label(about, text=about_text, justify="left", wraplength=560).pack(anchor="w")

        self.status_line = ttk.Label(settings, text="Ready.")
        self.status_line.pack(anchor="w", pady=(10, 0))

    def _build_status(self, parent):
        box = ttk.LabelFrame(parent, text="Status", style="Section.TLabelframe", padding=12)
        box.pack(fill="x", pady=(0, 12))

        self.status_text = tk.Text(box, height=5, wrap="word", relief="flat", bg=self.cget("bg"))
        self.status_text.pack(fill="x")
        self.status_text.configure(state="disabled")

    def _build_output(self, parent):
        box = ttk.LabelFrame(parent, text="Generated commands / logs", style="Section.TLabelframe", padding=12)
        box.pack(fill="both", expand=True)

        self.output = scrolledtext.ScrolledText(box, wrap="word", font=("Consolas", 9))
        self.output.pack(fill="both", expand=True)

    def log(self, text):
        self.output.insert("end", text.rstrip() + "\n")
        self.output.see("end")

    def set_status_line(self, text):
        self.status_line.configure(text=text)
        self.overlay_status.set(text)
        self.refresh_overlay()

    def set_status_text(self, lines):
        self.status_text.configure(state="normal")
        self.status_text.delete("1.0", "end")
        self.status_text.tag_configure("ok", foreground="#0a7a20")
        self.status_text.tag_configure("bad", foreground="#b00020")
        self.status_text.tag_configure("neutral", foreground="#202020")
        for item in lines:
            if isinstance(item, dict):
                tag = "ok" if item.get("ok") else "bad"
                glyph = "\u2713" if item.get("ok") else "X"
                self.status_text.insert("end", f"{glyph} {item.get('text', '')}\n", tag)
            else:
                self.status_text.insert("end", f"{item}\n", "neutral")
        self.status_text.configure(state="disabled")

    def update_path_status(self):
        checks = {
            "demoPath": self.path_ok("demoPath", suffix=".dem"),
            "outputDir": self.path_ok("outputDir", directory=True),
            "hlaePath": self.path_ok("hlaePath", suffix=".exe"),
            "cs2Path": self.path_ok("cs2Path", suffix=".exe"),
            "ffmpegPath": self.path_ok("ffmpegPath", suffix=".exe"),
        }
        for key, ok in checks.items():
            label = self.path_status_labels.get(key)
            if label:
                label.configure(text="\u2713" if ok else "X", fg="#0a7a20" if ok else "#b00020")

    def path_ok(self, key, suffix=None, directory=False):
        value = self.vars[key].get().strip()
        if not value:
            return False
        path = Path(value)
        if directory:
            return path.is_dir()
        if not path.is_file():
            return False
        return path.suffix.lower() == suffix if suffix else True

    def update_blur_amount_label(self, _value=None):
        self.blur_amount_label.configure(text=f"{self.vars['motionBlurAmount'].get():.2f}")

    def select_demo(self):
        path = filedialog.askopenfilename(title="Select CS2 .dem file", filetypes=[("CS2 demo", "*.dem"), ("All files", "*.*")])
        if path:
            self.vars["demoPath"].set(path)
            if not self.vars["sessionName"].get().strip():
                self.vars["sessionName"].set(Path(path).stem)
            self.run_task("Scanning userinfo...", self.scan_players)

    def select_output_dir(self):
        path = filedialog.askdirectory(title="Select output folder")
        if path:
            self.vars["outputDir"].set(path)

    def select_exe(self, kind):
        titles = {
            "hlae": "Select hlae.exe",
            "cs2": "Select cs2.exe",
            "ffmpeg": "Select ffmpeg.exe",
        }
        path = filedialog.askopenfilename(title=titles[kind], filetypes=[("Executable", "*.exe"), ("All files", "*.*")])
        if path:
            self.vars[f"{kind}Path"].set(path)

    def refresh_status(self):
        try:
            hlae = server.hlae_status()
            cs2 = server.cs2_status()
            steam = server.steam_status()
            ffmpeg = server.ffmpeg_status()
            render = server.render_status(self.vars["outputDir"].get().strip())

            if hlae.get("path") and not self.vars["hlaePath"].get():
                self.vars["hlaePath"].set(hlae["path"])
            if cs2.get("path") and not self.vars["cs2Path"].get():
                self.vars["cs2Path"].set(cs2["path"])
            if ffmpeg.get("path") and not self.vars["ffmpegPath"].get():
                self.vars["ffmpegPath"].set(ffmpeg["path"])
            self.update_take_list(render.get("takes", []))
            self.update_path_status()
            self.set_status_text([
                {"ok": bool(steam.get("offlineLikely")), "text": f"Steam: {steam.get('message', '')}"},
                {"ok": bool(hlae.get("installed")), "text": f"HLAE: {hlae.get('message', '')}"},
                {"ok": bool(cs2.get("found")), "text": f"CS2: {cs2.get('message', '')}"},
                {"ok": bool(ffmpeg.get("found")), "text": f"FFmpeg: {ffmpeg.get('message', '')}"},
            ])
        except Exception as exc:
            self.set_status_text([f"Status error: {exc}"])

    def update_take_list(self, takes):
        current = self.vars["selectedTake"].get()
        labels = ["Latest take"]
        take_by_label = {}
        for item in takes:
            badges = []
            if item.get("videoPath"):
                badges.append("video")
            if item.get("audioPath"):
                badges.append("audio")
            if item.get("hasFrames"):
                badges.append("frames")
            badge_text = ", ".join(badges) if badges else "empty"
            take_name = item.get("take", "Take")
            session = item.get("session", "")
            label = f"{take_name} - {session} ({badge_text})" if session else f"{item.get('label', item.get('takeDir', 'Take'))} ({badge_text})"
            labels.append(label)
            take_by_label[label] = item

        self.render_takes = takes
        self.take_by_label = take_by_label
        if hasattr(self, "take_combo"):
            self.take_combo.configure(values=labels)
        self.vars["selectedTake"].set(current if current in labels else labels[0])

    def refresh_takes(self):
        render = server.render_status(self.vars["outputDir"].get().strip())
        self.after(0, lambda: self.update_take_list(render.get("takes", [])))
        return {
            "refreshed": True,
            "takesFound": len(render.get("takes", [])),
            "message": render.get("message", ""),
        }

    def run_task(self, label, func):
        self.set_status_line(label)

        def worker():
            try:
                result = func()
                self.after(0, lambda result=result: self.task_done(result))
            except Exception as exc:
                detail = traceback.format_exc()
                self.after(0, lambda exc=exc, detail=detail: self.task_failed(exc, detail))

        threading.Thread(target=worker, daemon=True).start()

    def task_done(self, result):
        if isinstance(result, dict) and result.get("started"):
            self.recording_output_base = result.get("outputBase")
            self._last_recording_sample = None
            self.demo_ready_marker = Path(result["demoReadyMarker"]) if result.get("demoReadyMarker") else None
            self.demo_ready_log = Path(result["demoReadyLog"]) if result.get("demoReadyLog") else None
            self.demo_ready_logs = [Path(path) for path in result.get("demoReadyLogs", [])]
            if self.demo_ready_log and self.demo_ready_log not in self.demo_ready_logs:
                self.demo_ready_logs.insert(0, self.demo_ready_log)
            self.demo_ready_dump_dirs = [Path(path) for path in result.get("demoReadyDumpDirs", [])]
            self.demo_ready_text = result.get("demoReadyText") or "CS2_DEMO_TOOL_DEMO_LOADED"
            demo_path = Path(self.vars["demoPath"].get().strip()) if self.vars["demoPath"].get().strip() else None
            self.demo_log_name = demo_path.name.lower() if demo_path else ""
            self.demo_ready = False
            self.cs2_session_active = True
            self.cs2_was_seen = False
            self.cs2_session_started_at = time.time()
            self.overlay_recording = False
            self.overlay_paused = False
            self.overlay_collapsed = False
            self.overlay_last_action.set("Waiting for demo playback marker.")
            self.vars["overlayEnabled"].set(True)
            self.show_overlay()
            self.set_status_line("Demo loading...")
        elif isinstance(result, dict) and result.get("stoppedAudio"):
            self.overlay_recording = False
            self.set_status_line("Recording stopped.")
        elif isinstance(result, dict) and result.get("videoPath"):
            self.set_status_line("Encode complete.")
        elif isinstance(result, dict) and result.get("refreshedInGame"):
            self.set_status_line("In-game options refreshed.")
        elif isinstance(result, dict) and result.get("refreshCfgPaths"):
            self.set_status_line("Refresh cfg written. Press F11 in CS2.")
        else:
            self.set_status_line("Done.")
        if result is not None:
            self.log_result(result)
        self.refresh_status()

    def task_failed(self, exc, detail):
        self.set_status_line(f"Error: {exc}")
        self.log(detail)
        messagebox.showerror("Gasi's Demo Tool", str(exc))

    def toggle_overlay(self):
        if self.vars["overlayEnabled"].get():
            self.show_overlay()
        else:
            self.hide_overlay()

    def show_overlay(self):
        self.overlay_ui_scale = self.compute_overlay_scale()
        if self.overlay and self.overlay.winfo_exists():
            self.overlay.deiconify()
            self.set_overlay_collapsed(self.overlay_collapsed)
            self.refresh_overlay()
            self.start_overlay_polling()
            return

        self.overlay = tk.Toplevel(self)
        self.overlay.title("Recording Overlay")
        self.apply_app_icon(self.overlay)
        self.overlay.overrideredirect(True)
        self.overlay.attributes("-topmost", True)
        self.overlay.configure(bg=self.OVERLAY_TRANSPARENT_COLOR)
        try:
            self.overlay.attributes("-transparentcolor", self.OVERLAY_TRANSPARENT_COLOR)
        except tk.TclError:
            self.overlay.configure(bg="#0b1220")
            try:
                self.overlay.attributes("-alpha", 0.92)
            except tk.TclError:
                pass
        self.configure_overlay_geometry()
        self.configure_overlay_window_styles()

        self.overlay_widgets = {}
        self.overlay_buttons = {}
        self.overlay_button_specs = {}

        shell = tk.Frame(self.overlay, bg=self.overlay.cget("bg"), padx=self.os(26), pady=self.os(22))
        self.overlay_shell = shell
        shell.pack(fill="both", expand=True)
        shell.bind("<Button-3>", lambda _event: self.toggle_overlay_collapsed())
        shell.bind("<Escape>", lambda _event: self.toggle_overlay_collapsed())

        top = tk.Frame(shell, bg=shell.cget("bg"))
        top.pack(fill="x")

        status_panel = self.overlay_panel(top, padx=self.os(18), pady=self.os(14))
        self.overlay_status_panel = status_panel
        status_panel.pack(side="left", anchor="nw")

        title_row = tk.Frame(status_panel, bg=self.OVERLAY_PANEL_BG)
        title_row.pack(fill="x")
        self.overlay_dot = tk.Canvas(title_row, width=self.os(20), height=self.os(20), bg=self.OVERLAY_PANEL_BG, highlightthickness=0)
        self.overlay_dot.pack(side="left", padx=(0, self.os(9)))
        title = tk.Label(title_row, text="CS2 DEMO RECORDER", bg=self.OVERLAY_PANEL_BG, fg="#5eead4", font=self.overlay_font("Segoe UI", 12, "bold"))
        title.pack(side="left")
        self.overlay_widgets["state"] = tk.Label(title_row, text="READY", bg=self.OVERLAY_PANEL_BG, fg="#cbd5e1", font=self.overlay_font("Segoe UI", 10, "bold"))
        self.overlay_widgets["state"].pack(side="left", padx=(self.os(14), 0))

        self.overlay_widgets["status"] = tk.Label(
            status_panel,
            text="",
            bg=self.OVERLAY_PANEL_BG,
            fg="#ffffff",
            justify="left",
            anchor="w",
            width=42,
            font=self.overlay_font("Segoe UI", 11, "bold"),
        )
        self.overlay_widgets["status"].pack(anchor="w", pady=(self.os(9), 0))
        self.overlay_widgets["meta"] = tk.Label(
            status_panel,
            text="",
            bg=self.OVERLAY_PANEL_BG,
            fg="#cbd5e1",
            justify="left",
            anchor="w",
            width=52,
            font=self.overlay_font("Consolas", 9),
        )
        self.overlay_widgets["meta"].pack(anchor="w", pady=(self.os(8), 0))
        self.overlay_widgets["last_action"] = tk.Label(
            status_panel,
            text="",
            bg=self.OVERLAY_PANEL_BG,
            fg="#93c5fd",
            justify="left",
            anchor="w",
            width=52,
            font=self.overlay_font("Segoe UI", 9),
        )
        self.overlay_widgets["last_action"].pack(anchor="w", pady=(self.os(7), 0))

        top_actions = self.overlay_panel(top, padx=self.os(12), pady=self.os(10))
        top_actions.pack(side="right", anchor="ne")
        self.add_overlay_button(top_actions, "hide", "hide", "Hide", self.toggle_overlay_collapsed, accent="#94a3b8", width=104, height=66)

        spacer = tk.Frame(shell, bg=shell.cget("bg"))
        self.overlay_spacer = spacer
        spacer.pack(fill="both", expand=True)

        self.overlay_settings_panel = self.overlay_panel(shell, padx=self.os(14), pady=self.os(12))
        self.overlay_settings_body = tk.Frame(self.overlay_settings_panel, bg=self.OVERLAY_PANEL_BG)
        self.overlay_settings_body.pack(fill="x")

        dock = self.overlay_panel(shell, padx=self.os(14), pady=self.os(12))
        self.overlay_dock = dock
        dock.pack(side="bottom", anchor="s")

        primary = tk.Frame(dock, bg=self.OVERLAY_PANEL_BG)
        primary.pack(side="left")
        self.add_overlay_button(primary, "back", "back", f"-{self.overlay_jump_seconds}s", lambda: self.overlay_skip(-1), accent="#38bdf8", width=92, height=72)
        self.add_overlay_button(primary, "pause", "pause", "Pause", self.overlay_pause_toggle, accent="#facc15", width=92, height=72)
        self.add_overlay_button(primary, "forward", "forward", f"+{self.overlay_jump_seconds}s", lambda: self.overlay_skip(1), accent="#38bdf8", width=92, height=72)
        self.add_overlay_button(primary, "record", "record", "Record", self.overlay_record_toggle, accent="#ef4444", width=112, height=72)

        divider = tk.Frame(dock, bg="#1f3342", width=self.os(1), height=self.os(64))
        divider.pack(side="left", padx=self.os(12), fill="y")

        secondary = tk.Frame(dock, bg=self.OVERLAY_PANEL_BG)
        secondary.pack(side="left")
        self.add_overlay_button(secondary, "capture_menu", "target", "Capture", lambda: self.show_overlay_menu("capture"), accent="#a78bfa", width=92, height=72)
        self.add_overlay_button(secondary, "audio_menu", "audio", "Audio", lambda: self.show_overlay_menu("audio"), accent="#60a5fa", width=84, height=72)
        self.add_overlay_button(secondary, "hud_menu", "hud", "HUD", lambda: self.show_overlay_menu("hud"), accent="#2dd4bf", width=84, height=72)
        self.add_overlay_button(secondary, "killfeed_menu", "feed", "Killfeed", lambda: self.show_overlay_menu("killfeed"), accent="#fbbf24", width=92, height=72)
        self.add_overlay_button(secondary, "demo_ui", "window", "Demo UI", lambda: self.send_cs2_overlay_key("F8", "Demo UI"), accent="#fb923c", width=96, height=72)

        self.refresh_overlay()
        self.start_overlay_polling()

    def configure_overlay_geometry(self):
        if not self.overlay or not self.overlay.winfo_exists():
            return
        width = self.winfo_screenwidth()
        height = self.winfo_screenheight()
        self.overlay.geometry(f"{width}x{height}+0+0")

    def configure_overlay_window_styles(self):
        if not self.overlay or not self.overlay.winfo_exists() or not hasattr(ctypes, "windll"):
            return
        try:
            self.overlay.update_idletasks()
            hwnd = self.overlay.winfo_id()
            user32 = ctypes.windll.user32
            get_window_long = user32.GetWindowLongPtrW if hasattr(user32, "GetWindowLongPtrW") else user32.GetWindowLongW
            set_window_long = user32.SetWindowLongPtrW if hasattr(user32, "SetWindowLongPtrW") else user32.SetWindowLongW
            get_window_long.argtypes = [ctypes.c_void_p, ctypes.c_int]
            get_window_long.restype = ctypes.c_ssize_t
            set_window_long.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
            set_window_long.restype = ctypes.c_ssize_t
            style = get_window_long(hwnd, -20)
            style |= 0x08000000  # WS_EX_NOACTIVATE: keep CS2 focused when overlay buttons are clicked.
            style |= 0x00000080  # WS_EX_TOOLWINDOW: keep the overlay out of Alt-Tab.
            set_window_long(hwnd, -20, style)
        except (tk.TclError, OSError, AttributeError, ValueError):
            pass

    def overlay_panel(self, parent, padx=12, pady=10):
        return tk.Frame(
            parent,
            bg=self.OVERLAY_PANEL_BG,
            padx=padx,
            pady=pady,
            highlightthickness=1,
            highlightbackground=self.OVERLAY_PANEL_STROKE,
        )

    def add_overlay_button(self, parent, key, icon, label, command, accent="#e2e8f0", width=90, height=70):
        scaled_width = self.os(width)
        scaled_height = self.os(height)
        canvas = tk.Canvas(parent, width=scaled_width, height=scaled_height, bg=self.OVERLAY_PANEL_BG, highlightthickness=0, cursor="hand2")
        canvas.pack(side="left", padx=self.os(4))
        self.overlay_buttons[key] = canvas
        self.overlay_button_specs[key] = {
            "icon": icon,
            "label": label,
            "command": command,
            "accent": accent,
            "hover": False,
            "pressed": False,
            "width": scaled_width,
            "height": scaled_height,
            "scale": self.overlay_ui_scale,
        }
        canvas.bind("<Enter>", lambda _event, button_key=key: self.set_overlay_button_hover(button_key, True))
        canvas.bind("<Leave>", lambda _event, button_key=key: self.set_overlay_button_hover(button_key, False))
        canvas.bind("<ButtonPress-1>", lambda _event, button_key=key: self.press_overlay_button(button_key))
        self.draw_overlay_button(key)
        return canvas

    def set_overlay_button_hover(self, key, hovering):
        spec = self.overlay_button_specs.get(key)
        if not spec:
            return
        spec["hover"] = hovering
        self.draw_overlay_button(key)

    def press_overlay_button(self, key):
        spec = self.overlay_button_specs.get(key)
        if not spec:
            return
        spec["pressed"] = True
        self.draw_overlay_button(key)

        def release():
            if key in self.overlay_button_specs:
                self.overlay_button_specs[key]["pressed"] = False
                self.draw_overlay_button(key)

        self.after(110, release)
        spec["command"]()

    def update_overlay_button(self, key, icon=None, label=None, accent=None):
        spec = self.overlay_button_specs.get(key)
        if not spec:
            return
        if icon is not None:
            spec["icon"] = icon
        if label is not None:
            spec["label"] = label
        if accent is not None:
            spec["accent"] = accent
        self.draw_overlay_button(key)

    def draw_overlay_button(self, key):
        canvas = self.overlay_buttons.get(key)
        spec = self.overlay_button_specs.get(key)
        if not canvas or not spec:
            return
        width = spec["width"]
        height = spec["height"]
        scale = spec.get("scale", 1.0)
        accent = spec["accent"]
        fill = "#0f1f2d" if spec["hover"] else "#0b1824"
        if spec["pressed"]:
            fill = "#142b3c"
        canvas.delete("all")
        border = max(1, int(round(2 * scale)))
        canvas.create_rectangle(border, border, width - border, height - border, fill=fill, outline="#24465a", width=max(1, int(round(scale))))
        self.draw_overlay_icon(canvas, spec["icon"], width // 2, int(round(25 * scale)), accent, scale)
        canvas.create_text(width // 2, height - int(round(17 * scale)), text=spec["label"], fill="#e5edf6", font=self.overlay_font("Segoe UI", 9, "bold"))

    def draw_overlay_icon(self, canvas, icon, cx, cy, color, scale=1.0):
        def d(value):
            return int(round(value * scale))

        if icon == "back":
            canvas.create_rectangle(cx - d(22), cy - d(12), cx - d(18), cy + d(12), fill=color, outline="")
            canvas.create_polygon(cx - d(17), cy, cx - d(2), cy - d(13), cx - d(2), cy + d(13), fill=color, outline="")
            canvas.create_polygon(cx - d(1), cy, cx + d(14), cy - d(13), cx + d(14), cy + d(13), fill=color, outline="")
        elif icon == "forward":
            canvas.create_rectangle(cx + d(18), cy - d(12), cx + d(22), cy + d(12), fill=color, outline="")
            canvas.create_polygon(cx + d(17), cy, cx + d(2), cy - d(13), cx + d(2), cy + d(13), fill=color, outline="")
            canvas.create_polygon(cx + d(1), cy, cx - d(14), cy - d(13), cx - d(14), cy + d(13), fill=color, outline="")
        elif icon == "pause":
            canvas.create_rectangle(cx - d(12), cy - d(13), cx - d(4), cy + d(13), fill=color, outline="")
            canvas.create_rectangle(cx + d(4), cy - d(13), cx + d(12), cy + d(13), fill=color, outline="")
        elif icon == "play":
            canvas.create_polygon(cx - d(9), cy - d(14), cx - d(9), cy + d(14), cx + d(14), cy, fill=color, outline="")
        elif icon == "record":
            canvas.create_oval(cx - d(13), cy - d(13), cx + d(13), cy + d(13), fill=color, outline="")
        elif icon == "stop":
            canvas.create_rectangle(cx - d(12), cy - d(12), cx + d(12), cy + d(12), fill=color, outline="")
        elif icon == "refresh":
            canvas.create_arc(cx - d(15), cy - d(15), cx + d(15), cy + d(15), start=35, extent=285, style="arc", outline=color, width=d(3))
            canvas.create_polygon(cx + d(14), cy - d(15), cx + d(20), cy - d(14), cx + d(16), cy - d(8), fill=color, outline="")
        elif icon == "hide":
            canvas.create_line(cx - d(12), cy - d(12), cx + d(12), cy + d(12), fill=color, width=d(3))
            canvas.create_line(cx + d(12), cy - d(12), cx - d(12), cy + d(12), fill=color, width=d(3))
        elif icon == "target":
            canvas.create_oval(cx - d(14), cy - d(14), cx + d(14), cy + d(14), outline=color, width=d(3))
            canvas.create_line(cx - d(20), cy, cx - d(8), cy, fill=color, width=d(2))
            canvas.create_line(cx + d(8), cy, cx + d(20), cy, fill=color, width=d(2))
            canvas.create_line(cx, cy - d(20), cx, cy - d(8), fill=color, width=d(2))
            canvas.create_line(cx, cy + d(8), cx, cy + d(20), fill=color, width=d(2))
        elif icon == "hud":
            canvas.create_rectangle(cx - d(17), cy - d(12), cx + d(17), cy + d(12), outline=color, width=d(2))
            canvas.create_line(cx - d(12), cy - d(4), cx + d(12), cy - d(4), fill=color, width=d(2))
            canvas.create_line(cx - d(12), cy + d(4), cx + d(12), cy + d(4), fill=color, width=d(2))
        elif icon == "window":
            canvas.create_rectangle(cx - d(17), cy - d(13), cx + d(17), cy + d(13), outline=color, width=d(2))
            canvas.create_line(cx - d(17), cy - d(5), cx + d(17), cy - d(5), fill=color, width=d(2))
            canvas.create_rectangle(cx - d(12), cy, cx - d(2), cy + d(8), outline=color, width=d(2))
            canvas.create_line(cx + d(4), cy + d(2), cx + d(12), cy + d(2), fill=color, width=d(2))
            canvas.create_line(cx + d(4), cy + d(7), cx + d(12), cy + d(7), fill=color, width=d(2))
        elif icon == "audio":
            canvas.create_polygon(cx - d(16), cy - d(8), cx - d(7), cy - d(8), cx + d(5), cy - d(17), cx + d(5), cy + d(17), cx - d(7), cy + d(8), cx - d(16), cy + d(8), fill=color, outline="")
            canvas.create_arc(cx + d(2), cy - d(13), cx + d(22), cy + d(13), start=-45, extent=90, style="arc", outline=color, width=d(3))
        elif icon == "feed":
            for offset in (-10, 0, 10):
                canvas.create_rectangle(cx - d(17), cy + d(offset) - d(3), cx + d(17), cy + d(offset) + d(3), fill=color, outline="")
    def show_overlay_menu(self, menu, force=False):
        if not self.overlay_settings_panel or not self.overlay_settings_body:
            return
        if not force and self.overlay_menu == menu and self.overlay_settings_panel.winfo_manager():
            self.hide_overlay_menu()
            return
        self.overlay_menu = menu
        for child in self.overlay_settings_body.winfo_children():
            child.destroy()
        builders = {
            "capture": self.build_overlay_capture_menu,
            "pov": self.build_overlay_pov_menu,
            "audio": self.build_overlay_audio_menu,
            "hud": self.build_overlay_hud_menu,
            "killfeed": self.build_overlay_killfeed_menu,
        }
        builder = builders.get(menu)
        if builder:
            builder(self.overlay_settings_body)
        if not self.overlay_settings_panel.winfo_manager():
            self.overlay_settings_panel.pack(side="bottom", anchor="s", pady=(0, 10), before=self.overlay_dock)

    def hide_overlay_menu(self):
        self.overlay_menu = None
        if self.overlay_settings_panel:
            self.overlay_settings_panel.pack_forget()

    def overlay_menu_title(self, parent, text):
        tk.Label(parent, text=text, bg=self.OVERLAY_PANEL_BG, fg="#e5edf6", font=self.overlay_font("Segoe UI", 10, "bold")).pack(side="left", padx=(0, self.os(10)))

    def overlay_menu_button(self, parent, text, command, active=False, width=15):
        bg = "#123047" if active else "#0b1824"
        fg = "#ffffff" if active else "#cbd5e1"
        button = tk.Button(
            parent,
            text=text,
            command=command,
            width=max(6, self.os(width)),
            bg=bg,
            fg=fg,
            activebackground="#1e4258",
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            font=self.overlay_font("Segoe UI", 9, "bold"),
            cursor="hand2",
        )
        button.pack(side="left", padx=self.os(4), pady=self.os(2))
        return button

    def build_overlay_capture_menu(self, parent):
        self.overlay_menu_title(parent, "Capture")
        self.overlay_menu_button(parent, "POV", lambda: self.show_overlay_menu("pov"), width=10)
        self.overlay_menu_button(parent, "FOV -5", lambda: self.overlay_adjust_fov(-5), width=9)
        self.overlay_menu_button(parent, "FOV +5", lambda: self.overlay_adjust_fov(5), width=9)
        fps_label = "FPS locked" if self.overlay_recording else f"FPS {self.vars['framerate'].get()}"
        self.overlay_menu_button(parent, fps_label, self.overlay_cycle_fps, self.overlay_recording, width=11)

    def build_overlay_pov_menu(self, parent):
        self.overlay_menu_title(parent, "POV")
        self.overlay_menu_button(parent, "Back", lambda: self.show_overlay_menu("capture"), width=8)
        self.overlay_menu_button(parent, "Auto", lambda: self.overlay_select_pov("Auto / current POV"), self.vars["pov"].get() == "Auto / current POV", width=8)
        labels = [label for label in self.overlay_pov_labels() if label not in {"Auto / current POV", "Manual name / slot..."}]
        if not labels:
            self.overlay_menu_button(parent, "No players", lambda: None, width=12)
            return
        for label in labels[:10]:
            player_name = label.split(": ", 1)[1] if ": " in label else label
            display = player_name[:14]
            self.overlay_menu_button(parent, display, lambda value=label: self.overlay_select_pov(value), self.vars["pov"].get() == label, width=15)

    def overlay_pov_labels(self):
        values = self.pov_combo.cget("values")
        if isinstance(values, str):
            return list(self.tk.splitlist(values))
        return list(values)

    def build_overlay_audio_menu(self, parent):
        self.overlay_menu_title(parent, "Audio")
        self.overlay_menu_button(parent, "Radio muted", lambda: self.overlay_toggle_bool("muteDialog", self.overlay_apply_audio), self.vars["muteDialog"].get(), width=13)
        self.overlay_menu_button(parent, "Automute off", lambda: self.overlay_toggle_bool("unmuteAutomutedPlayers", self.overlay_apply_audio), self.vars["unmuteAutomutedPlayers"].get(), width=13)

    def build_overlay_hud_menu(self, parent):
        self.overlay_menu_title(parent, "HUD")
        for key, label in (
            ("hudEnabled", "HUD"),
            ("deathNoticesEnabled", "Killfeed"),
            ("crosshairEnabled", "Crosshair"),
            ("xrayEnabled", "X-ray"),
            ("radarEnabled", "Radar"),
        ):
            self.overlay_menu_button(parent, label, lambda option=key: self.overlay_toggle_bool(option, self.overlay_apply_hud), self.vars[key].get(), width=10)
        self.overlay_menu_button(parent, "Names", self.overlay_toggle_nametags, self.vars["nametagsEnabled"].get() and not self.vars["hideTeamNames"].get(), width=10)

    def build_overlay_killfeed_menu(self, parent):
        self.overlay_menu_title(parent, "Killfeed")
        for key, label in (
            ("deathmsgHighlightLocalPlayer", "POV kills"),
            ("deathmsgBlockOtherKills", "Block others"),
            ("deathmsgLongLifetime", "Long life"),
        ):
            self.overlay_menu_button(parent, label, lambda option=key: self.overlay_toggle_bool(option, self.overlay_apply_killfeed), self.vars[key].get(), width=13)

    def overlay_toggle_bool(self, key, apply_func):
        self.vars[key].set(not self.vars[key].get())
        apply_func()
        if self.overlay_menu:
            self.show_overlay_menu(self.overlay_menu, force=True)

    def overlay_toggle_nametags(self):
        enable = not (self.vars["nametagsEnabled"].get() and not self.vars["hideTeamNames"].get())
        self.vars["nametagsEnabled"].set(enable)
        self.vars["hideTeamNames"].set(not enable)
        self.overlay_apply_hud()
        self.show_overlay_menu("hud", force=True)

    def overlay_cycle_fps(self):
        if self.overlay_recording:
            self.overlay_status.set("FPS cannot be changed while recording.")
            self.overlay_last_action.set("Stop the recording before changing FPS.")
            self.status_line.configure(text=self.overlay_status.get())
            self.refresh_overlay()
            return
        values = ["60", "120", "300", "600", "1000"]
        current = self.vars["framerate"].get()
        next_value = values[(values.index(current) + 1) % len(values)] if current in values else values[0]
        self.vars["framerate"].set(next_value)
        fps = int(next_value)
        commands = [f"host_framerate {fps}", f"mirv_streams record fps {fps}"]
        self.overlay_send_console_commands("FPS updated", commands)
        self.show_overlay_menu("capture", force=True)

    def overlay_adjust_fov(self, delta):
        current = int(float(self.vars["fov"].get() or 100))
        value = max(60, min(140, current + delta))
        self.vars["fov"].set(str(value))
        self.overlay_send_console_commands("FOV updated", [f"fov_cs_debug {value}"])

    def overlay_apply_pov(self):
        commands = self.current_pov_commands()
        if commands:
            self.overlay_send_console_commands("POV applied", commands)
        else:
            self.overlay_status.set("Select a POV in the GUI first.")
            self.overlay_last_action.set("No POV command was sent.")
            self.refresh_overlay()

    def overlay_select_pov(self, label):
        self.vars["pov"].set(label)
        self.update_manual_pov_state()
        if label == "Auto / current POV":
            self.overlay_status.set("POV set to auto.")
            self.overlay_last_action.set("No POV command needed.")
            self.refresh_overlay()
        else:
            self.overlay_apply_pov()
        self.show_overlay_menu("pov", force=True)

    def overlay_apply_audio(self):
        self.overlay_send_console_commands("Audio options applied", server.build_quality_of_life_commands(self.build_payload()))

    def overlay_apply_hud(self):
        self.overlay_send_console_commands("HUD options applied", server.build_hud_commands(self.build_payload()))

    def overlay_apply_killfeed(self):
        self.overlay_send_console_commands("Killfeed options applied", server.build_deathmsg_commands(self.build_payload()))

    def current_pov_commands(self):
        payload = self.build_payload()
        pov = str(payload.get("pov") or "").strip()
        pov_name = str(payload.get("povName") or "").strip()
        pov_account_id = str(payload.get("povAccountId") or "").strip()
        if not pov:
            return []
        commands = []
        target_name = pov_name or ("" if pov.isdigit() else pov)
        if pov_account_id.isdigit():
            commands.extend(["spec_lock_to_accountid 0", f"spec_lock_to_accountid {pov_account_id}"])
        if target_name:
            commands.append(f'spec_player "{server.cfg_quote(target_name)}"')
        elif pov.isdigit():
            commands.append(f"spec_player {pov}")
        commands.extend(["spec_mode 4", "firstperson"])
        if not pov_account_id.isdigit():
            commands.append("spec_lock_to_current_player 1")
        return commands

    def start_overlay_polling(self):
        if self.overlay_polling:
            return
        self.overlay_polling = True
        self.poll_overlay_recording()

    def hide_overlay(self):
        self.set_overlay_collapsed(True)

    def close_overlay(self):
        if self.overlay and self.overlay.winfo_exists():
            self.overlay.withdraw()
        self.vars["overlayEnabled"].set(False)
        self.overlay_polling = False

    def toggle_overlay_collapsed(self):
        self.set_overlay_collapsed(not self.overlay_collapsed)

    def set_overlay_collapsed(self, collapsed):
        if not self.overlay or not self.overlay.winfo_exists():
            return
        self.overlay_collapsed = collapsed
        if self.overlay_shell:
            self.overlay_shell.configure(padx=self.os(8 if collapsed else 26), pady=self.os(8 if collapsed else 22))
        if collapsed:
            if self.overlay_status_panel:
                self.overlay_status_panel.pack_forget()
            if self.overlay_spacer:
                self.overlay_spacer.pack_forget()
            if self.overlay_settings_panel:
                self.overlay_settings_panel.pack_forget()
            if self.overlay_dock:
                self.overlay_dock.pack_forget()
            refresh_button = self.overlay_buttons.get("refresh")
            if refresh_button:
                refresh_button.pack_forget()
            width = self.os(152)
            height = self.os(112)
            margin = self.os(24)
            x = max(0, self.winfo_screenwidth() - width - margin)
            self.overlay.geometry(f"{width}x{height}+{x}+{margin}")
        else:
            self.configure_overlay_geometry()
            if self.overlay_status_panel and not self.overlay_status_panel.winfo_manager():
                self.overlay_status_panel.pack(side="left", anchor="nw")
            refresh_button = self.overlay_buttons.get("refresh")
            if refresh_button and not refresh_button.winfo_manager():
                refresh_button.pack(side="left", padx=self.os(4))
            if self.overlay_spacer and not self.overlay_spacer.winfo_manager():
                self.overlay_spacer.pack(fill="both", expand=True)
            if self.overlay_settings_panel and self.overlay_menu and not self.overlay_settings_panel.winfo_manager():
                self.overlay_settings_panel.pack(side="bottom", anchor="s", pady=(0, self.os(10)))
            if self.overlay_dock and not self.overlay_dock.winfo_manager():
                self.overlay_dock.pack(side="bottom", anchor="s")
        self.refresh_overlay()

    def refresh_overlay(self):
        if not self.overlay or not self.overlay.winfo_exists():
            return
        if not self.vars["overlayEnabled"].get():
            return

        pov = self.vars["pov"].get()
        if pov == "Manual name / slot...":
            pov = self.vars["manualPov"].get().strip() or "Manual"
        status = self.overlay_status.get()
        if self.overlay_recording:
            state = "REC"
            state_color = "#fecaca"
        elif self.overlay_paused:
            state = "PAUSED"
            state_color = "#fef08a"
        elif not self.demo_ready:
            state = "LOADING"
            state_color = "#bfdbfe"
        else:
            state = "READY"
            state_color = "#bbf7d0"
        meta = [
            f"POV        {pov}",
            f"Capture    {self.vars['framerate'].get()} FPS  FOV {self.vars['fov'].get()}",
            f"HUD        {'on' if self.vars['hudEnabled'].get() else 'off'}  Killfeed {'on' if self.vars['deathNoticesEnabled'].get() else 'off'}",
            f"Audio      Radio {'muted' if self.vars['muteDialog'].get() else 'on'}",
        ]
        last_action = self.overlay_last_action.get().strip()
        if self.overlay_widgets:
            self.overlay_widgets["state"].configure(text=state, fg=state_color)
            self.overlay_widgets["status"].configure(text=status)
            self.overlay_widgets["meta"].configure(text="\n".join(meta))
            self.overlay_widgets["last_action"].configure(text=last_action or "Waiting for demo input.")
        self.update_overlay_button(
            "record",
            icon="stop" if self.overlay_recording else "record",
            label="Stop" if self.overlay_recording else "Record",
            accent="#f87171" if self.overlay_recording else "#ef4444",
        )
        self.update_overlay_button(
            "pause",
            icon="play" if self.overlay_paused else "pause",
            label="Resume" if self.overlay_paused else "Pause",
            accent="#22c55e" if self.overlay_paused else "#facc15",
        )
        self.update_overlay_button(
            "hide",
            icon="window" if self.overlay_collapsed else "hide",
            label="Show UI" if self.overlay_collapsed else "Hide",
            accent="#38bdf8" if self.overlay_collapsed else "#94a3b8",
        )
        self.draw_overlay_dot()

    def draw_overlay_dot(self):
        if not self.overlay or not self.overlay.winfo_exists() or not hasattr(self, "overlay_dot"):
            return
        self.overlay_dot.delete("all")
        if self.overlay_recording:
            radius = self.os(4 + (self.overlay_pulse % 6))
            color = "#ef4444" if self.overlay_pulse % 2 else "#f87171"
            center = self.os(10)
            self.overlay_dot.create_oval(center - radius, center - radius, center + radius, center + radius, fill=color, outline="")
            self.overlay_pulse += 1
        else:
            color = "#facc15" if self.overlay_paused else "#475569"
            self.overlay_dot.create_oval(self.os(4), self.os(4), self.os(16), self.os(16), fill=color, outline="")

    def overlay_record_toggle(self):
        if not self.demo_ready:
            self.overlay_status.set("Demo is still loading.")
            self.overlay_last_action.set("Waiting for demo playback marker.")
            self.status_line.configure(text=self.overlay_status.get())
            self.refresh_overlay()
            return
        was_recording = self.overlay_recording
        if self.send_cs2_overlay_key("F10", "Recording toggle", update_status=False):
            self.overlay_recording = not was_recording
            message = "Stopping recording..." if was_recording else "Starting recording..."
            self.overlay_status.set(message)
            self.status_line.configure(text=message)
            self.overlay_last_action.set("Recording toggle sent.")
            self.refresh_overlay()

    def overlay_pause_toggle(self):
        if not self.demo_ready:
            self.overlay_status.set("Demo is still loading.")
            self.overlay_last_action.set("Pause is available after demo load.")
            self.refresh_overlay()
            return
        if self.send_cs2_overlay_key("F2", "Pause toggle", update_status=False):
            self.overlay_paused = not self.overlay_paused
            message = "Demo paused." if self.overlay_paused else "Demo resumed."
            self.overlay_status.set(message)
            self.status_line.configure(text=message)
            self.overlay_last_action.set("Pause toggle sent.")
            self.refresh_overlay()

    def overlay_skip(self, direction):
        if not self.demo_ready:
            self.overlay_status.set("Demo is still loading.")
            self.overlay_last_action.set("Skipping is available after demo load.")
            self.refresh_overlay()
            return
        if direction < 0:
            sent = self.send_cs2_overlay_key("F1", f"Jump back {self.overlay_jump_seconds}s", update_status=False)
            message = f"Jumped back {self.overlay_jump_seconds}s."
        else:
            sent = self.send_cs2_overlay_key("F3", f"Jump forward {self.overlay_jump_seconds}s", update_status=False)
            message = f"Jumped forward {self.overlay_jump_seconds}s."
        if sent:
            self.overlay_status.set(message)
            self.status_line.configure(text=message)
            self.overlay_last_action.set(message)
            self.refresh_overlay()

    def overlay_send_console_commands(self, label, commands):
        if self.send_cs2_overlay_cfg(commands):
            self.overlay_status.set(label)
            self.overlay_last_action.set("Overlay command sent.")
        else:
            self.overlay_status.set(self.last_input_error or "Overlay command was not sent.")
            self.overlay_last_action.set("Direct command send failed.")
        self.status_line.configure(text=self.overlay_status.get())
        self.refresh_overlay()

    def send_cs2_overlay_cfg(self, commands):
        self.last_input_error = ""
        clean_commands = [str(command).strip() for command in commands if str(command).strip()]
        if not clean_commands:
            self.last_input_error = "No overlay commands to send."
            return False
        if not self.demo_ready:
            self.last_input_error = "Demo is still loading."
            return False
        if not self.is_cs2_running():
            self.last_input_error = "CS2 is not running."
            return False
        server.write_overlay_cfg(clean_commands)
        return self.post_cs2_key(self.VK_KEYS["F4"])

    def send_cs2_overlay_key(self, key_name, action_label, update_status=True):
        self.last_input_error = ""
        sent = self.post_cs2_key(self.VK_KEYS[key_name])
        if sent:
            message = f"{action_label} sent."
            self.overlay_last_action.set(message)
            if update_status:
                self.overlay_status.set(message)
                self.status_line.configure(text=message)
                self.refresh_overlay()
            return True
        message = self.last_input_error or "CS2 window was not found."
        self.overlay_status.set(message)
        self.overlay_last_action.set(f"{action_label} was not sent.")
        self.status_line.configure(text=message)
        self.refresh_overlay()
        return False

    def post_cs2_key(self, vk_code):
        hwnd = self.find_cs2_window()
        if not hasattr(ctypes, "windll"):
            self.last_input_error = "Windows input APIs are not available."
            return False
        user32 = ctypes.windll.user32
        overlay_was_topmost = False
        if self.overlay and self.overlay.winfo_exists():
            try:
                overlay_was_topmost = bool(int(self.overlay.attributes("-topmost")))
                self.overlay.attributes("-topmost", False)
                self.overlay.update_idletasks()
            except (tk.TclError, ValueError):
                overlay_was_topmost = False
        try:
            if hwnd:
                user32.ShowWindow(hwnd, 9)
                user32.SetForegroundWindow(hwnd)
            elif not self.is_cs2_running() and not self.activate_cs2_by_title():
                self.last_input_error = "CS2 window was not found."
                return False
            time.sleep(0.05)
            return self.send_virtual_key(vk_code)
        finally:
            if overlay_was_topmost and self.overlay and self.overlay.winfo_exists():
                self.after(120, lambda: self.overlay.winfo_exists() and self.overlay.attributes("-topmost", True))

    def send_virtual_key(self, vk_code):
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        pointer_size = ctypes.sizeof(ctypes.c_void_p)
        ulong_ptr = ctypes.c_ulonglong if pointer_size == 8 else ctypes.c_ulong

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [
                ("dx", ctypes.c_long),
                ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ulong_ptr),
            ]

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", ctypes.c_ushort),
                ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ulong_ptr),
            ]

        class HARDWAREINPUT(ctypes.Structure):
            _fields_ = [
                ("uMsg", ctypes.c_ulong),
                ("wParamL", ctypes.c_ushort),
                ("wParamH", ctypes.c_ushort),
            ]

        class INPUTUNION(ctypes.Union):
            _fields_ = [
                ("mi", MOUSEINPUT),
                ("ki", KEYBDINPUT),
                ("hi", HARDWAREINPUT),
            ]

        class INPUT(ctypes.Structure):
            _fields_ = [
                ("type", ctypes.c_ulong),
                ("union", INPUTUNION),
            ]

        user32.MapVirtualKeyW.argtypes = [ctypes.c_uint, ctypes.c_uint]
        user32.MapVirtualKeyW.restype = ctypes.c_uint
        user32.SendInput.argtypes = [ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int]
        user32.SendInput.restype = ctypes.c_uint
        scan_code = user32.MapVirtualKeyW(vk_code, 0)
        inputs = (INPUT * 2)()
        inputs[0].type = 1
        inputs[0].union.ki = KEYBDINPUT(0, scan_code, 0x0008, 0, 0)
        inputs[1].type = 1
        inputs[1].union.ki = KEYBDINPUT(0, scan_code, 0x0008 | 0x0002, 0, 0)
        sent = user32.SendInput(2, inputs, ctypes.sizeof(INPUT))
        if sent != 2:
            error = ctypes.get_last_error()
            if error == 5:
                self.last_input_error = "Input blocked by Windows. Run the GUI as admin or run CS2/HLAE without admin."
            else:
                self.last_input_error = f"Input send failed. Windows error {error}."
        return sent == 2

    def poll_overlay_recording(self):
        if not self.overlay or not self.overlay.winfo_exists() or not self.vars["overlayEnabled"].get():
            self.overlay_polling = False
            return
        if self.cs2_session_active:
            cs2_running = self.is_cs2_running()
            self.cs2_was_seen = self.cs2_was_seen or cs2_running
            launch_grace_elapsed = time.time() - self.cs2_session_started_at > 45
            if (self.cs2_was_seen or launch_grace_elapsed) and not cs2_running:
                self.cs2_session_active = False
                self.overlay_status.set("CS2 closed")
                self.status_line.configure(text="CS2 closed.")
                self.close_overlay()
                return
            if not self.demo_ready and self.check_demo_ready_marker():
                self.demo_ready = True
                self.overlay_status.set("Demo loaded. Use F10 to record.")
                self.overlay_last_action.set("Demo playback marker detected.")
                self.status_line.configure(text="Demo loaded.")
        active = self.detect_recording_activity()
        if active != self.overlay_recording:
            self.overlay_recording = active
            self.overlay_status.set("Recording" if active else ("Ready for F10" if self.demo_ready else "Demo loading..."))
        self.refresh_overlay()
        self.after(650, self.poll_overlay_recording)

    def check_demo_ready_marker(self):
        for log_path in self.demo_ready_logs:
            if self.file_contains_demo_ready_marker(log_path):
                return True
        for folder in self.demo_ready_dump_dirs:
            try:
                candidates = list(folder.glob("cs2_demo_loaded_marker*.txt")) + list(folder.glob("condump*.txt"))
            except OSError:
                continue
            for candidate in candidates:
                if self.file_contains_demo_ready_marker(candidate):
                    return True
        if not self.demo_ready_marker:
            return False
        try:
            return self.demo_ready_marker.exists() and self.demo_ready_marker.stat().st_mtime >= self.cs2_session_started_at
        except OSError:
            return False

    def file_contains_demo_ready_marker(self, path):
        try:
            if not path.exists() or path.stat().st_mtime < self.cs2_session_started_at:
                return False
            text = path.read_text(encoding="utf-8", errors="ignore")
            if self.demo_ready_text in text:
                return True
            lower_text = text.lower()
            failure_patterns = (
                "network_disconnect_replay_incompatible",
                "network version",
                "is incompatible",
                "[demo] demo playback finished ( 11.0 seconds, 1 render frames",
            )
            if any(pattern in lower_text for pattern in failure_patterns):
                return False
            ready_patterns = (
                "[demo] demo skipping finished",
                "[prediction] added trueview prediction",
            )
            if any(pattern in lower_text for pattern in ready_patterns):
                return True
            demo_signon_seen = '[client] cl:  signon traffic "demo"' in lower_text or '[client] cl: signon traffic "demo"' in lower_text
            demo_unpaused = "cgamerules - unpaused on tick" in lower_text
            return demo_signon_seen and demo_unpaused
        except OSError:
            return False

    def is_cs2_running(self):
        return self.process_exists_by_name("cs2.exe")

    def process_exists_by_name(self, image_name):
        return bool(self.process_ids_by_name(image_name))

    def process_ids_by_name(self, image_name):
        if not hasattr(ctypes, "windll"):
            return set()
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateToolhelp32Snapshot.argtypes = [ctypes.c_ulong, ctypes.c_ulong]
        kernel32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
        if snapshot in (0, ctypes.c_void_p(-1).value):
            return set()

        class PROCESSENTRY32W(ctypes.Structure):
            _fields_ = [
                ("dwSize", ctypes.c_ulong),
                ("cntUsage", ctypes.c_ulong),
                ("th32ProcessID", ctypes.c_ulong),
                ("th32DefaultHeapID", ctypes.c_void_p),
                ("th32ModuleID", ctypes.c_ulong),
                ("cntThreads", ctypes.c_ulong),
                ("th32ParentProcessID", ctypes.c_ulong),
                ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", ctypes.c_ulong),
                ("szExeFile", ctypes.c_wchar * 260),
            ]

        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        kernel32.Process32FirstW.argtypes = [ctypes.c_void_p, ctypes.POINTER(PROCESSENTRY32W)]
        kernel32.Process32FirstW.restype = ctypes.c_bool
        kernel32.Process32NextW.argtypes = [ctypes.c_void_p, ctypes.POINTER(PROCESSENTRY32W)]
        kernel32.Process32NextW.restype = ctypes.c_bool
        target = image_name.lower()
        pids = set()
        try:
            has_entry = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
            while has_entry:
                if entry.szExeFile.lower() == target:
                    pids.add(int(entry.th32ProcessID))
                has_entry = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
        finally:
            kernel32.CloseHandle(snapshot)
        return pids

    def find_cs2_window(self):
        if not hasattr(ctypes, "windll"):
            return None
        user32 = ctypes.windll.user32
        cs2_pids = self.process_ids_by_name("cs2.exe")
        hwnds = []
        fallback_hwnds = []

        enum_proc_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def enum_proc(hwnd, _lparam):
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in cs2_pids:
                hwnds.append(hwnd)
                return False
            if not user32.IsWindowVisible(hwnd):
                return True
            title = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, title, len(title))
            title_text = title.value.lower()
            if "counter-strike 2" in title_text or title_text == "cs2":
                fallback_hwnds.append(hwnd)
            return True

        user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.EnumWindows(enum_proc_type(enum_proc), 0)
        if hwnds:
            return hwnds[0]
        if fallback_hwnds:
            return fallback_hwnds[0]
        user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        user32.FindWindowW.restype = ctypes.c_void_p
        for title in ("Counter-Strike 2", "cs2"):
            hwnd = user32.FindWindowW(None, title)
            if hwnd:
                return hwnd
        return None

    def activate_cs2_by_title(self):
        user32 = ctypes.windll.user32
        user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        user32.FindWindowW.restype = ctypes.c_void_p
        for title in ("Counter-Strike 2", "cs2"):
            hwnd = user32.FindWindowW(None, title)
            if hwnd:
                user32.ShowWindow(hwnd, 9)
                return bool(user32.SetForegroundWindow(hwnd))
        return False

    def send_cs2_refresh_key(self):
        return self.post_cs2_key(self.VK_KEYS["F11"])

    def detect_recording_activity(self):
        base = Path(self.recording_output_base) if self.recording_output_base else None
        if not base or not base.exists():
            return False
        paths = []
        for take in base.glob("take*"):
            if not take.is_dir():
                continue
            paths.append(take)
            screen_dir = take / "screen"
            if screen_dir.is_dir():
                paths.append(screen_dir)
            for candidate in (
                take / "video.mp4",
                take / "audio.wav",
                screen_dir / "video.mp4",
            ):
                if candidate.exists():
                    paths.append(candidate)
            for pattern in ("*.mp4", "*.mov", "*.mkv", "*.avi", "*.webm"):
                paths.extend(path for path in take.glob(pattern) if path.is_file())
                if screen_dir.is_dir():
                    paths.extend(path for path in screen_dir.glob(pattern) if path.is_file())
        if not paths:
            return False

        total_size = 0
        newest_mtime = 0
        file_count = 0
        dir_count = 0
        for path in paths:
            try:
                stat = path.stat()
            except OSError:
                continue
            newest_mtime = max(newest_mtime, stat.st_mtime)
            if path.is_file():
                total_size += stat.st_size
                file_count += 1
            elif path.is_dir():
                dir_count += 1
        if not newest_mtime:
            return False
        now = time.time()
        sample = (total_size, newest_mtime, file_count, dir_count)
        previous = self._last_recording_sample
        self._last_recording_sample = sample
        if previous and (total_size > previous[0] or file_count > previous[2] or dir_count > previous[3] or newest_mtime > previous[1]):
            return True
        return now - newest_mtime < 4.0

    def log_result(self, result):
        if isinstance(result, dict):
            if result.get("consoleCommands"):
                self.log("Generated console commands:")
                self.log("\n".join(result["consoleCommands"]))
            elif result.get("videoPath"):
                trim = result.get("audioTrimSeconds")
                suffix = f" | audio trim: {trim}s" if trim else ""
                self.log(f"Video: {result['videoPath']}{suffix}")
                if result.get("unblurredVideoPath"):
                    self.log(f"Unblurred source: {result['unblurredVideoPath']}")
                if result.get("message"):
                    self.log(result["message"])
            elif result.get("players"):
                self.log("Players:")
                for player in result["players"]:
                    account = f" account {player.get('accountId')}" if player.get("accountId") else ""
                    self.log(f"  {player.get('slot')}: {player.get('name')}{account}")
            elif result.get("message"):
                self.log(result["message"])
            else:
                self.log(str(result))
        else:
            self.log(str(result))

    def build_payload(self):
        width, height = [int(part) for part in self.vars["resolution"].get().split("x")]
        pov_label = self.vars["pov"].get()
        player = self.player_by_label.get(pov_label, {})
        if pov_label == "Auto / current POV":
            pov = ""
        elif pov_label == "Manual name / slot...":
            pov = self.vars["manualPov"].get().strip()
        else:
            pov = player.get("name", pov_label)

        selected_take = self.take_by_label.get(self.vars["selectedTake"].get(), {})

        return {
            "demoPath": self.vars["demoPath"].get().strip(),
            "hlaePath": self.vars["hlaePath"].get().strip(),
            "cs2Path": self.vars["cs2Path"].get().strip(),
            "ffmpegPath": self.vars["ffmpegPath"].get().strip(),
            "outputDir": self.vars["outputDir"].get().strip(),
            "sessionName": self.vars["sessionName"].get().strip(),
            "pov": pov,
            "povName": player.get("name", ""),
            "povSlot": str(player.get("slot", "")),
            "povAccountId": str(player.get("accountId", "")),
            "framerate": int(self.vars["framerate"].get() or 60),
            "resolution": {"width": width, "height": height},
            "fov": int(self.vars["fov"].get() or 100),
            "soundEnabled": bool(self.vars["soundEnabled"].get()),
            "syncCueEnabled": bool(self.vars["syncCueEnabled"].get()),
            "motionBlurEnabled": bool(self.vars["motionBlurEnabled"].get()),
            "motionBlurAmount": float(self.vars["motionBlurAmount"].get()),
            "motionBlurStrength": 1.0 if self.vars["motionBlurEnabled"].get() else 0.0,
            "motionBlurMethod": self.vars["motionBlurMethod"].get(),
            "motionBlurSampleFps": int(self.vars["motionBlurSampleFps"].get() or 1080),
            "videoQuality": int(self.vars["videoQuality"].get() or 9),
            "videoPreset": self.vars["videoPreset"].get(),
            "hudEnabled": bool(self.vars["hudEnabled"].get()),
            "deathNoticesEnabled": bool(self.vars["deathNoticesEnabled"].get()),
            "deathNoticesOnly": not bool(self.vars["hudEnabled"].get()),
            "crosshairEnabled": bool(self.vars["crosshairEnabled"].get()),
            "xrayEnabled": bool(self.vars["xrayEnabled"].get()),
            "radarEnabled": bool(self.vars["radarEnabled"].get()),
            "nametagsEnabled": bool(self.vars["nametagsEnabled"].get()),
            "hideTeamNames": bool(self.vars["hideTeamNames"].get()),
            "trueViewEnabled": bool(self.vars["trueViewEnabled"].get()),
            "muteDialog": bool(self.vars["muteDialog"].get()),
            "unmuteAutomutedPlayers": bool(self.vars["unmuteAutomutedPlayers"].get()),
            "hidePlayerPings": bool(self.vars["hidePlayerPings"].get()),
            "hideSpecBindings": bool(self.vars["hideSpecBindings"].get()),
            "hideObserverCrosshair": bool(self.vars["hideObserverCrosshair"].get()),
            "hideKillAssists": bool(self.vars["hideKillAssists"].get()),
            "deathmsgHighlightLocalPlayer": bool(self.vars["deathmsgHighlightLocalPlayer"].get()),
            "deathmsgBlockOtherKills": bool(self.vars["deathmsgBlockOtherKills"].get()),
            "deathmsgLongLifetime": bool(self.vars["deathmsgLongLifetime"].get()),
            "recordingFormat": self.vars["recordingFormat"].get(),
            "deleteFramesAfterEncode": bool(self.vars["deleteFramesAfterEncode"].get()),
            "takeDir": selected_take.get("takeDir", ""),
            "audioTrimMs": int(float(self.vars["audioTrimMs"].get() or 0)),
        }

    def confirm_launch_warning(self):
        dialog = tk.Toplevel(self)
        dialog.title("HLAE Safety Warning")
        self.apply_app_icon(dialog)
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)

        body = ttk.Frame(dialog, padding=18)
        body.pack(fill="both", expand=True)
        warning = (
            "This tool is technically considered a Cheat by Valve.\n\n"
            "Use it only in Offline Mode to record Demos.\n"
            "DO NOT connect to any servers especially to VAC Secured Servers.\n\n"
            "Note: This tool might also change your CS2 Settings. "
            "Make sure to save them before starting."
        )
        ttk.Label(body, text=warning, wraplength=520, justify="left").pack(fill="x")

        result = {"continue": False}

        def accept():
            result["continue"] = True
            dialog.destroy()

        def cancel():
            dialog.destroy()

        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(18, 0))
        ttk.Button(buttons, text="Cancel", command=cancel).pack(side="right")
        ttk.Button(buttons, text="I understand, continue", style="Primary.TButton", command=accept).pack(side="right", padx=(0, 8))
        dialog.protocol("WM_DELETE_WINDOW", cancel)
        dialog.update_idletasks()
        x = self.winfo_rootx() + max(0, (self.winfo_width() - dialog.winfo_width()) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - dialog.winfo_height()) // 2)
        dialog.geometry(f"+{x}+{y}")
        self.wait_window(dialog)
        return result["continue"]

    def open_demo_requested(self):
        if self.confirm_launch_warning():
            self.run_task("Opening demo in HLAE...", self.start_recording)

    def scan_players(self):
        demo_path = self.vars["demoPath"].get().strip()
        if not demo_path:
            raise RuntimeError("Select a .dem file first.")
        result = server.inspect_demo_players(demo_path)
        self.players = result.get("players", [])

        labels = ["Auto / current POV"]
        self.player_by_label = {}
        for player in self.players:
            label = f"{player.get('slot')}: {player.get('name')}"
            labels.append(label)
            self.player_by_label[label] = player
        labels.append("Manual name / slot...")

        def update_combo():
            self.pov_combo.configure(values=labels)
            if self.vars["pov"].get() not in labels:
                self.vars["pov"].set(labels[0])
            self.update_manual_pov_state()

        self.after(0, update_combo)
        return result

    def update_manual_pov_state(self):
        enabled = self.vars["pov"].get() == "Manual name / slot..."
        self.manual_pov_entry.configure(state="normal" if enabled else "disabled")

    def install_hlae(self):
        result = server.install_hlae()
        if result.get("path"):
            self.after(0, lambda: self.vars["hlaePath"].set(result["path"]))
        return result

    def install_ffmpeg(self):
        result = server.install_ffmpeg()
        if result.get("path"):
            self.after(0, lambda: self.vars["ffmpegPath"].set(result["path"]))
        return result

    def start_recording(self):
        payload = self.build_payload()
        if not payload["demoPath"]:
            raise RuntimeError("Select a .dem file first.")
        return server.start_auto_recording(payload)

    def stop_recording(self):
        return server.stop_auto_recording()

    def encode_latest(self):
        return server.encode_take(self.build_payload())

    def refresh_in_game(self):
        paths = server.write_refresh_cfg(self.build_payload())
        sent = self.send_cs2_refresh_key()
        return {
            "refreshedInGame": sent,
            "refreshCfgPaths": [str(path) for path in paths],
            "message": "Refresh cfg was regenerated and F11 was sent to CS2." if sent else "Refresh cfg was regenerated. Press F11 in CS2 to apply it.",
        }

    def generate_config(self):
        payload = self.build_payload()
        if not payload["demoPath"]:
            raise RuntimeError("Select a .dem file first.")
        data, _mmcfg, cfg_path = server.write_auto_cfg(payload)
        return {"cfgPath": str(cfg_path), **data}


if __name__ == "__main__":
    DemoToolApp().mainloop()
