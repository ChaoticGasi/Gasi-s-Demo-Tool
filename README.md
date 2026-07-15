# Gasi's Demo Tool
## Tutorial Video
[![TUTORIAL VIDEO](http://img.youtube.com/vi/x-xXf5EvGBk/0.jpg)](http://www.youtube.com/watch?v=x-xXf5EvGBk "
How to Record CS2 Highlights for FREE (Automatic Demo Recorder)")

<img width="1592" height="1006" alt="Screenshot 2026-06-11 181601" src="https://github.com/user-attachments/assets/da6a519f-ddca-40fd-9e5d-8bbfbcc05331" />
<img width="2555" height="1435" alt="Screenshot 2026-06-21 233520" src="https://github.com/user-attachments/assets/51a38f6b-8bab-49da-a28c-c1433806576c" />
<img width="2557" height="1435" alt="Screenshot 2026-06-21 233537" src="https://github.com/user-attachments/assets/805f4f30-3770-4e1e-8e5e-ddf05cfba65d" />
<img width="1920" height="1080" alt="video_with_audio - frame at 0m25s" src="https://github.com/user-attachments/assets/efa87294-aa5b-404a-acb1-0070f6af5a8c" />


## Disclaimer

This tool uses HLAE, which Valve can technically consider a cheat.

Use it only in Steam Offline Mode and only for recording demo files. Do not connect to online servers, especially VAC-secured servers, while using HLAE or this tool.

This tool can also change CS2 settings while preparing the recording view. Save any settings you care about before starting.

Use this tool at your own risk.

## Download Or Source Code

You can use the tool in two ways:

- Download the ready-to-use Windows app from the **Releases** tab.
- Download the source code and run or compile it yourself.

The release build does not require Python. The source code version does require Python.

## Use The Ready EXE

1. Download the latest release from the **Releases** tab.
2. Extract the downloaded archive.
3. Start `GasisDemoTool.exe`.
4. Accept the Windows administrator prompt.
5. Select a `.dem` file.
6. Check that Steam, HLAE, CS2, and FFmpeg show green status.
7. Pick your recording options in the **Recording** tab.
8. Click **Open demo in HLAE**.
9. Wait until the overlay says the demo is loaded.
10. Use the overlay or press `F10` to start recording and `F10` again to stop.
11. Open the **Encoding** tab, choose the take, adjust **Extra audio trim ms** if needed, and click **Encode / mux**.
12. Finished recordings are written to the `recordings` folder next to the EXE.

When moving or sharing the release build, keep the whole `GasisDemoTool` folder together. Do not move only the `.exe`, because it needs the bundled `_internal` folder beside it.

## Use The Source Code

### Requirements

- Windows
- Python 3.11 or newer
- HLAE
- FFmpeg

### Getting Python

If Python is not installed yet:

1. Go to https://www.python.org/downloads/
2. Download the latest Python 3 release for Windows.
3. Run the installer.
4. Make sure `Add python.exe to PATH` is checked before you click Install.

If you already have Python installed, you can check it by opening Command Prompt or PowerShell and running:

```bash
python --version
```

### Run From Source

1. Download or clone the source code.
2. Open the project folder.
3. Start the app with `start-gui.cmd`.
4. Select a `.dem` file.
5. Check that Steam, HLAE, CS2, and FFmpeg show green status.
6. Pick your recording options in the **Recording** tab.
7. Click **Open demo in HLAE**.
8. Wait until the overlay says the demo is loaded.
9. Use the overlay or press `F10` to start recording and `F10` again to stop.
10. To change non-live visual options while CS2 is already open, update the GUI options and click **Refresh in game**. If needed, press `F11` inside CS2.
11. Open the **Encoding** tab, choose the take, adjust **Extra audio trim ms** if needed, and click **Encode / mux**.
12. Finished recordings are written to the `recordings` folder.

## Compile The EXE Yourself

You can build a standalone Windows app with PyInstaller.

1. Open PowerShell in the project folder.
2. Install PyInstaller:

```bash
python -m pip install pyinstaller
```

3. Build the app:

```bash
python -m PyInstaller -y --noconsole --onedir --uac-admin --name GasisDemoTool --icon App\assets\app-icon.ico --add-data "App\assets;assets" App\desktop_app.py
```

4. After the build finishes, the app will be in:

```text
dist\GasisDemoTool\GasisDemoTool.exe
```

5. Create an empty `recordings` folder next to the EXE if it does not exist yet:

```bash
mkdir dist\GasisDemoTool\recordings
```

When sharing the compiled app, share the whole `dist\GasisDemoTool` folder. Do not share only the `.exe`, because it needs the bundled `_internal` folder beside it.

## Included Tools

This app uses FFmpeg: https://www.ffmpeg.org/

This app uses HLAE: https://github.com/advancedfx/advancedfx

Special thanks to https://github.com/abandonedpools for the HLAE config template.
