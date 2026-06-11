# Gasi's Demo Tool
<img width="1592" height="1006" alt="Screenshot 2026-06-11 181601" src="https://github.com/user-attachments/assets/da6a519f-ddca-40fd-9e5d-8bbfbcc05331" />
<img width="1918" height="1078" alt="Screenshot 2026-06-11 181716" src="https://github.com/user-attachments/assets/0aef4022-9cfa-4ff4-81dd-55c694887aa2" />
<img width="1920" height="1080" alt="video_with_audio - frame at 0m25s" src="https://github.com/user-attachments/assets/efa87294-aa5b-404a-acb1-0070f6af5a8c" />


## Requirements

- Windows
- Python 3.11 or newer
- HLAE
- FFmpeg

## Getting Python

If Python is not installed yet:

1. Go to https://www.python.org/downloads/
2. Download the latest Python 3 release for Windows.
3. Run the installer.
4. Make sure `Add python.exe to PATH` is checked before you click Install.

If you already have Python installed, you can check it by opening Command Prompt or PowerShell and running:

```bash
python --version
```

## Disclaimer

This tool uses HLAE, which Valve can technically consider a cheat.

Use it only in Steam Offline Mode and only for recording demo files. Do not connect to online servers, especially VAC-secured servers, while using HLAE or this tool.

This tool can also change CS2 settings while preparing the recording view. Save any settings you care about before starting.

Use this tool at your own risk.

## How To Use The GUI

1. Start the app with `start-gui.cmd`.
2. Select a `.dem` file.
3. Check that Steam, HLAE, CS2, and FFmpeg show green status.
4. Pick your recording options in the **Recording** tab.
5. Click **Open demo in HLAE**.
6. In CS2, press `F10` to start recording and `F10` again to stop.
7. To change visual options while CS2 is already open, update the GUI options and click **Refresh in game**. If needed, press `F11` inside CS2.
8. Open the **Encoding** tab, choose the take, adjust **Extra audio trim ms** if needed, and click **Encode / mux**.
9. Finished recordings are written to the `recordings` folder.

## Included Tools

This app uses FFmpeg: https://www.ffmpeg.org/

This app uses HLAE: https://github.com/advancedfx/advancedfx

Special thanks to https://github.com/abandonedpools for the HLAE config template.
