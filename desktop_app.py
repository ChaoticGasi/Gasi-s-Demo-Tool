import threading
import time
import traceback
import ctypes
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

import server

ASSETS = Path(__file__).resolve().parent / "assets"
APP_ICON_PNG = ASSETS / "app-icon.png"
APP_ICON = ASSETS / "app-icon.ico"


class DemoToolApp(tk.Tk):
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
        self.overlay_position = (24, 24)
        self.overlay_recording = False
        self.overlay_pulse = 0
        self.overlay_polling = False
        self.recording_output_base = None
        self._last_recording_sample = None
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
        ttk.Label(title_block, text="Gasi´s Demo Recorder", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(title_block, text="Version 1.0").pack(anchor="w")

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
            self.cs2_session_active = True
            self.cs2_was_seen = False
            self.cs2_session_started_at = time.time()
            self.vars["overlayEnabled"].set(True)
            self.show_overlay()
            self.set_status_line("Demo ready. Press F10 to record.")
        elif isinstance(result, dict) and result.get("stoppedAudio"):
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
        if self.overlay and self.overlay.winfo_exists():
            self.overlay.deiconify()
            self.refresh_overlay()
            self.start_overlay_polling()
            return

        self.overlay = tk.Toplevel(self)
        self.overlay.title("Recording Overlay")
        self.apply_app_icon(self.overlay)
        self.overlay.overrideredirect(True)
        self.overlay.attributes("-topmost", True)
        self.overlay.attributes("-alpha", 0.82)
        self.overlay.configure(bg="#05070a")
        x, y = self.overlay_position
        self.overlay.geometry(f"+{x}+{y}")

        frame = tk.Frame(self.overlay, bg="#05070a", padx=12, pady=10, highlightthickness=1, highlightbackground="#2dd4bf")
        frame.pack(fill="both", expand=True)
        title_row = tk.Frame(frame, bg="#05070a")
        title_row.pack(fill="x")
        self.overlay_dot = tk.Canvas(title_row, width=14, height=14, bg="#05070a", highlightthickness=0)
        self.overlay_dot.pack(side="left", padx=(0, 7))
        self.overlay_title = tk.Label(title_row, text="CS2 DEMO TOOL", bg="#05070a", fg="#5eead4", font=("Segoe UI", 11, "bold"))
        self.overlay_title.pack(side="left")
        self.overlay_status_label = tk.Label(frame, text="", bg="#05070a", fg="#ffffff", justify="left", font=("Segoe UI", 9))
        self.overlay_status_label.pack(anchor="w", pady=(6, 0))
        self.overlay_keys_label = tk.Label(frame, text="", bg="#05070a", fg="#cbd5e1", justify="left", font=("Consolas", 8))
        self.overlay_keys_label.pack(anchor="w", pady=(8, 0))

        for widget in (self.overlay, frame, title_row, self.overlay_dot, self.overlay_title, self.overlay_status_label, self.overlay_keys_label):
            widget.bind("<ButtonPress-1>", self.start_overlay_drag)
            widget.bind("<B1-Motion>", self.drag_overlay)
            widget.bind("<Button-3>", lambda _event: self.hide_overlay())

        self.refresh_overlay()
        self.start_overlay_polling()

    def start_overlay_polling(self):
        if self.overlay_polling:
            return
        self.overlay_polling = True
        self.poll_overlay_recording()

    def hide_overlay(self):
        if self.overlay and self.overlay.winfo_exists():
            self.overlay_position = (self.overlay.winfo_x(), self.overlay.winfo_y())
            self.overlay.withdraw()
        self.vars["overlayEnabled"].set(False)

    def start_overlay_drag(self, event):
        self.overlay_drag_start = (event.x_root, event.y_root, self.overlay.winfo_x(), self.overlay.winfo_y())

    def drag_overlay(self, event):
        if not self.overlay or not hasattr(self, "overlay_drag_start"):
            return
        start_x, start_y, window_x, window_y = self.overlay_drag_start
        new_x = window_x + event.x_root - start_x
        new_y = window_y + event.y_root - start_y
        self.overlay.geometry(f"+{new_x}+{new_y}")
        self.overlay_position = (new_x, new_y)

    def refresh_overlay(self):
        if not self.overlay or not self.overlay.winfo_exists():
            return
        if not self.vars["overlayEnabled"].get():
            return

        pov = self.vars["pov"].get()
        if pov == "Manual name / slot...":
            pov = self.vars["manualPov"].get().strip() or "Manual"
        mode = "Blur" if self.vars["motionBlurEnabled"].get() else "Raw"
        status = self.overlay_status.get()
        lines = [
            f"Status: {status}",
            f"POV: {pov}",
            f"{self.vars['framerate'].get()} FPS  {self.vars['resolution'].get()}  {mode}",
            f"CRF {self.vars['videoQuality'].get()}  {self.vars['videoPreset'].get()}",
        ]
        keys = [
            "F5 account POV retry",
            "F6 slot POV fallback",
            "F7 HUD + POV retry",
            "F8 Demo UI toggle",
            "F9 clean HUD",
            "F10 start / stop recording",
            "F11 refresh GUI options",
            "Right-click overlay to hide",
        ]
        self.overlay_status_label.configure(text="\n".join(lines))
        self.overlay_keys_label.configure(text="\n".join(keys))
        self.draw_overlay_dot()

    def draw_overlay_dot(self):
        if not self.overlay or not self.overlay.winfo_exists() or not hasattr(self, "overlay_dot"):
            return
        self.overlay_dot.delete("all")
        if self.overlay_recording:
            radius = 4 + (self.overlay_pulse % 6)
            color = "#ef4444" if self.overlay_pulse % 2 else "#f87171"
            self.overlay_dot.create_oval(7 - radius, 7 - radius, 7 + radius, 7 + radius, fill=color, outline="")
            self.overlay_pulse += 1
        else:
            self.overlay_dot.create_oval(3, 3, 11, 11, fill="#475569", outline="")

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
                self.hide_overlay()
                self.overlay_polling = False
                return
        active = self.detect_recording_activity()
        if active != self.overlay_recording:
            self.overlay_recording = active
            self.overlay_status.set("Recording" if active else "Ready for F10")
        self.refresh_overlay()
        self.after(650, self.poll_overlay_recording)

    def is_cs2_running(self):
        return self.process_exists_by_name("cs2.exe")

    def process_exists_by_name(self, image_name):
        if not hasattr(ctypes, "windll"):
            return False
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateToolhelp32Snapshot.argtypes = [ctypes.c_ulong, ctypes.c_ulong]
        kernel32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
        if snapshot in (0, ctypes.c_void_p(-1).value):
            return False

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
        try:
            has_entry = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
            while has_entry:
                if entry.szExeFile.lower() == target:
                    return True
                has_entry = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
        finally:
            kernel32.CloseHandle(snapshot)
        return False

    def find_cs2_window(self):
        if not hasattr(ctypes, "windll"):
            return None
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        hwnds = []

        enum_proc_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def enum_proc(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if not pid.value:
                return True
            process = kernel32.OpenProcess(0x1000, False, pid.value)
            if process:
                try:
                    buffer = ctypes.create_unicode_buffer(1024)
                    size = ctypes.c_ulong(len(buffer))
                    if kernel32.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(size)):
                        if Path(buffer.value).name.lower() == "cs2.exe":
                            hwnds.append(hwnd)
                            return False
                finally:
                    kernel32.CloseHandle(process)
            return True

        user32.EnumWindows(enum_proc_type(enum_proc), 0)
        return hwnds[0] if hwnds else None

    def send_cs2_refresh_key(self):
        hwnd = self.find_cs2_window()
        if not hwnd:
            return False
        user32 = ctypes.windll.user32
        vk_f11 = 0x7A
        user32.PostMessageW(hwnd, 0x0100, vk_f11, 0)
        user32.PostMessageW(hwnd, 0x0101, vk_f11, 0)
        return True

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
            "deathNoticesOnly": True,
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
