from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import wave
import zipfile

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
STATIC = ROOT / "static"
GENERATED = ROOT / "generated"
RECORDINGS = PROJECT_ROOT / "recordings"
RUNTIME_ROOT = Path(os.environ.get("LOCALAPPDATA", str(ROOT / "runtime"))) / "CS2DemoRecorder"
TOOLS = RUNTIME_ROOT / "tools"
HLAE_DIR = TOOLS / "hlae"
HLAE_EXE = HLAE_DIR / "hlae.exe"
HLAE_API_URL = "https://api.github.com/repos/advancedfx/advancedfx/releases/latest"
HLAE_RELEASES_URL = "https://github.com/advancedfx/advancedfx/releases"
FFMPEG_DIR = TOOLS / "ffmpeg"
FFMPEG_EXE = FFMPEG_DIR / "bin" / "ffmpeg.exe"
FFMPEG_DOWNLOAD_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
AUDIO_PROCESS = None
AUDIO_OUTPUT = None
LAST_AUTO_SESSION = None

for folder in (GENERATED, RECORDINGS, TOOLS, RUNTIME_ROOT):
    folder.mkdir(parents=True, exist_ok=True)


def json_response(handler, status, data):
    body = json.dumps(data, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def read_json(handler):
    length = int(handler.headers.get("Content-Length", "0"))
    if not length:
        return {}
    raw = handler.rfile.read(length)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
    return json.loads(text)


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def cfg_quote(value):
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def payload_bool(payload, key, default):
    value = payload.get(key, default)
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "off", "no", ""}
    return bool(value)


def build_hud_commands(payload):
    hud_enabled = payload_bool(payload, "hudEnabled", True)
    deathnotices_enabled = payload_bool(payload, "deathNoticesEnabled", True)
    deathnotices_only = payload_bool(payload, "deathNoticesOnly", True)
    crosshair_enabled = payload_bool(payload, "crosshairEnabled", False)
    xray_enabled = payload_bool(payload, "xrayEnabled", False)
    radar_enabled = payload_bool(payload, "radarEnabled", False)
    nametags_enabled = payload_bool(payload, "nametagsEnabled", False)
    hide_team_names = payload_bool(payload, "hideTeamNames", True)
    trueview_enabled = payload_bool(payload, "trueViewEnabled", False)

    if not hud_enabled:
        radar_mode = 1 if radar_enabled else -1
    else:
        radar_mode = 0 if radar_enabled else -1
    team_mode = -1 if hide_team_names else (1 if nametags_enabled else 0)

    draw_hud = hud_enabled or deathnotices_enabled
    return [
        f"cl_drawhud {1 if draw_hud else 0}",
        f"cl_draw_only_deathnotices {1 if deathnotices_only and deathnotices_enabled else 0}",
        f"cl_drawhud_force_deathnotices {1 if deathnotices_enabled else 0}",
        f"cl_drawhud_force_radar {radar_mode}",
        f"cl_drawhud_force_teamid_overhead {team_mode}",
        f"cl_teamid_overhead_mode {2 if nametags_enabled else 0}",
        f"crosshair {1 if crosshair_enabled else 0}",
        f"spec_show_xray {1 if xray_enabled else 0}",
        f"mirv_panorama panelstyle panelId=trueview_row opacity={1 if trueview_enabled else 0}",
    ]


def build_quality_of_life_commands(payload):
    mute_dialog = payload_bool(payload, "muteDialog", True)
    unmute_automuted = payload_bool(payload, "unmuteAutomutedPlayers", True)
    hide_player_pings = payload_bool(payload, "hidePlayerPings", True)
    hide_spec_bindings = payload_bool(payload, "hideSpecBindings", True)
    hide_observer_crosshair = payload_bool(payload, "hideObserverCrosshair", True)
    hide_kill_assists = payload_bool(payload, "hideKillAssists", False)
    return [
        f"snd_setmixer Dialog vol {0 if mute_dialog else 1}",
        f"cl_sanitize_muted_players {'false' if unmute_automuted else 'true'}",
        f"cl_player_ping_mute {2 if hide_player_pings else 0}",
        f"cl_spec_show_bindings {'false' if hide_spec_bindings else 'true'}",
        f"cl_show_observer_crosshair {0 if hide_observer_crosshair else 1}",
        f"mp_display_kill_assists {'false' if hide_kill_assists else 'true'}",
    ]


def build_deathmsg_commands(payload):
    highlight_localplayer = payload_bool(payload, "deathmsgHighlightLocalPlayer", False)
    block_other_kills = payload_bool(payload, "deathmsgBlockOtherKills", False)
    extend_lifetime = payload_bool(payload, "deathmsgLongLifetime", False)
    commands = [
        'alias id "mirv_deathmsg help players"',
        'alias localplayer "localplayer_on"',
        'alias block "block_on"',
        'alias lifetime "lifetime_on"',
        'alias clearmsg "localplayer_off; block_off; lifetime_off"',
        'alias radar "radar_off"',
        'alias hud "hud_off"',
        'alias localplayer_on "mirv_deathmsg localplayer xTrace; alias localplayer localplayer_off; echo localplayer - enabled"',
        'alias localplayer_off "mirv_deathmsg localplayer default; alias localplayer localplayer_on; echo localplayer - disabled"',
        'alias block_on "mirv_deathmsg filter add attackerMatch=!xTrace victimMatch=!xTrace block=1 lastRule=1; alias block block_off; echo blocking other kills - enabled"',
        'alias block_off "mirv_deathmsg filter clear; alias block block_on; echo blocking other kills - disabled"',
        'alias lifetime_on "mirv_deathmsg lifetimeMod 10; alias lifetime lifetime_off; echo lifetime - enabled"',
        'alias lifetime_off "mirv_deathmsg lifetimeMod default; alias lifetime lifetime_on; echo lifetime - disabled"',
        'alias hud_off "cl_draw_only_deathnotices 1; alias hud hud_on"',
        'alias hud_on "cl_draw_only_deathnotices 0; alias hud hud_off"',
        'alias radar_off "cl_drawhud_force_radar -1; alias radar radar_on"',
        'alias radar_on "cl_drawhud_force_radar 0; alias radar radar_off"',
        "mirv_deathmsg localplayer default",
        "mirv_deathmsg filter clear",
        "mirv_deathmsg lifetimeMod default",
    ]
    if highlight_localplayer:
        commands.append("localplayer_on")
    if block_other_kills:
        commands.append("block_on")
    if extend_lifetime:
        commands.append("lifetime_on")
    return commands


def build_live_refresh_commands(payload):
    return [
        "sv_cheats 1",
        "mirv_cvar_unhide_all",
        *build_hud_commands(payload),
        *build_quality_of_life_commands(payload),
        *build_deathmsg_commands(payload),
        "r_show_build_info 0",
        "cl_trueview_show_status 0",
    ]


def find_steam_path():
    candidates = [
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Steam",
        Path(os.environ.get("PROGRAMFILES", "")) / "Steam",
        Path.home() / "AppData" / "Local" / "Steam",
    ]
    for candidate in candidates:
        if (candidate / "config" / "loginusers.vdf").exists():
            return candidate
    return None


def read_registry_value(root, path, name):
    if os.name != "nt":
        return None
    try:
        import winreg
        root_key = getattr(winreg, root)
        with winreg.OpenKey(root_key, path) as key:
            value, _value_type = winreg.QueryValueEx(key, name)
            return value
    except OSError:
        return None


def steam_library_paths():
    steam_path = find_steam_path()
    if not steam_path:
        return []

    paths = [steam_path / "steamapps"]
    library_vdf = steam_path / "steamapps" / "libraryfolders.vdf"
    if library_vdf.exists():
        text = library_vdf.read_text(encoding="utf-8", errors="ignore")
        for match in re.finditer(r'"path"\s+"([^"]+)"', text, re.I):
            library = Path(match.group(1).replace("\\\\", "\\"))
            paths.append(library / "steamapps")

    unique = []
    for path in paths:
        if path not in unique:
            unique.append(path)
    return unique


def find_cs2_path():
    relative = Path("common") / "Counter-Strike Global Offensive" / "game" / "bin" / "win64" / "cs2.exe"
    for steamapps in steam_library_paths():
        candidate = steamapps / relative
        if candidate.exists():
            return candidate
    return None


def cs2_status():
    cs2 = find_cs2_path()
    return {
        "found": cs2 is not None,
        "path": str(cs2) if cs2 else "",
        "message": "CS2 executable was found." if cs2 else "CS2 executable was not found. Select cs2.exe manually.",
    }


DEMO_NAME_BLOCKLIST = {
    "userinfo",
    "instancebaseline",
    "modelprecache",
    "soundprecache",
    "genericprecache",
    "lightstyles",
    "server_query_info",
    "downloadables",
    "decalprecache",
    "cmd",
    "name",
    "team",
    "game",
    "csgo",
    "cs2",
    "steam",
    "valve",
    "vguiscreen",
    "animassetdata",
    "entitynames",
    "effectdispatch",
    "scenes",
    "props",
    "knife",
    "pistol",
    "rifle",
    "defuse",
    "sound",
    "read",
    "stop",
    "port",
    "demoautorecorder",
    "demorecorder",
    "aimt",
}


def read_varint(data, offset, limit):
    value = 0
    shift = 0
    cursor = offset
    while cursor < limit and shift < 64:
        byte = data[cursor]
        cursor += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, cursor
        shift += 7
    return None, offset


def looks_like_player_name(value):
    if not value:
        return False
    value = value.strip()
    if len(value) < 4 or len(value) > 32:
        return False
    if any(ord(char) < 32 for char in value):
        return False
    if not (value[0].isalnum() and value[-1].isalnum()):
        return False
    lower = value.lower()
    if lower in DEMO_NAME_BLOCKLIST:
        return False
    if lower.startswith(("cl_", "sv_", "mp_", "r_", "snd_", "spec_", "mirv_", "host_", "weapon_", "item_", "prop_", "func_", "logic_")):
        return False
    if any(part in lower for part in (".vtex", ".vmdl", ".wav", ".mp3", ".cfg", ".dem", ".vnm", "materials/", "models/", "sounds/", "panorama/", "animation/", "particles/", "spawnpoints", "buyzone", "brush.", "door_", "button_", "sky", "nav")):
        return False
    if "\\" in value or "/" in value or "\x00" in value:
        return False
    if re.fullmatch(r"[0-9.\-_:]+", value):
        return False
    if not any(char.isalpha() or char.isdigit() for char in value):
        return False
    if any(char not in " ._-[]|#" and not char.isalnum() for char in value):
        return False
    noisy = sum(1 for char in value if not (char.isalnum() or char.isspace() or char in "._-[]|#"))
    if noisy > 0:
        return False
    alpha_count = sum(1 for char in value if char.isalpha())
    if alpha_count < 3:
        return False
    if len(set(value.lower())) <= 2:
        return False
    if re.fullmatch(r"[a-z]{1,3}[A-Z#@`~^]{1,3}", value):
        return False
    return True


def player_name_score(name, count):
    score = 0
    lower = name.lower()
    if 4 <= len(name) <= 18:
        score += 8
    if 5 <= count <= 12:
        score += 8
    elif 2 <= count <= 20:
        score += 4
    elif count > 30:
        score -= 12
    if re.search(r"[a-z]", name) and re.search(r"[A-Z]", name):
        score += 5
    if name.isupper() and len(name) >= 5:
        score += 6
    if any(char in lower for char in "aeiou"):
        score += 5
    else:
        score -= 8
    if " " in name:
        score += 2
    if any(char.isdigit() for char in name):
        score -= 6
    if any(char in name for char in "#[](){}|._-"):
        score += 1
    if any(char in name for char in "\"@$%&*+=<>\\"):
        score -= 8
    if re.search(r"(.)\1{3,}", name.lower()):
        score -= 10
    if lower in {"default", "mapload", "knife", "deagle", "ssg08", "inair", "defuse", "facingi", "grenad", "terrorist", "ctspawn"}:
        score -= 20
    return score


def extract_utf8_strings_from_blob(blob):
    names = []
    limit = len(blob)

    string_tags = (b"\x0a", b"\x12", b"\x1a", b"\x22", b"\x2a", b"\x32", b"\x3a")
    candidate_offsets = []
    for tag in string_tags:
        start = 0
        while True:
            offset = blob.find(tag, start)
            if offset < 0:
                break
            candidate_offsets.append(offset)
            start = offset + 1

    for offset in sorted(set(candidate_offsets)):
        length, cursor = read_varint(blob, offset + 1, limit)
        if length is None or length < 2 or length > 64 or cursor + length > limit:
            continue
        raw = blob[cursor:cursor + length]
        try:
            text = raw.decode("utf-8").strip()
        except UnicodeDecodeError:
            continue
        if looks_like_player_name(text):
            names.append(text)

    ascii_matches = re.findall(rb"[\x20-\x7e]{2,32}", blob)
    for raw in ascii_matches:
        text = raw.decode("utf-8", errors="ignore").strip()
        if looks_like_player_name(text):
            names.append(text)

    return names


def extract_printable_runs(blob):
    runs = []
    text = blob.decode("utf-8", errors="ignore")
    current = []
    for char in text:
        if char.isprintable() and char not in "\r\n\t":
            current.append(char)
        else:
            if 3 <= len(current) <= 64:
                runs.append("".join(current).strip())
            current = []
    if 3 <= len(current) <= 64:
        runs.append("".join(current).strip())
    return [run for run in runs if run]


def extract_account_id_near_name(blob, name):
    if not name:
        return ""
    raw_name = name.encode("utf-8", errors="ignore")
    if not raw_name:
        return ""
    index = blob.find(raw_name)
    if index < 0:
        return ""
    cursor = index + len(raw_name)
    limit = min(len(blob), cursor + 24)
    while cursor + 5 <= limit:
        if blob[cursor] == 0x11:
            account_id = int.from_bytes(blob[cursor + 1:cursor + 5], "little", signed=False)
            if 1_000_000 <= account_id <= 4_294_967_295:
                return str(account_id)
        cursor += 1
    return ""


def repair_partial_ascii_name(name, data):
    if len(name) < 4 or not name.isascii() or not name.islower():
        return name
    pattern = rb"[A-Za-z0-9_.\-\[\]|#]{1,16}" + re.escape(name.encode("ascii"))
    for match in re.finditer(pattern, data[: min(len(data), 64 * 1024 * 1024)]):
        candidate = match.group(0).decode("ascii", errors="ignore")
        if candidate != name and candidate.lower().endswith(name.lower()) and looks_like_player_name(candidate):
            return candidate
    return name


def inspect_demo_players(demo_path):
    path = Path(demo_path).expanduser()
    if not path.exists() or path.suffix.lower() != ".dem":
        raise FileNotFoundError("Select a valid .dem file first.")

    max_scan = 256 * 1024 * 1024
    with path.open("rb") as demo_file:
        data = demo_file.read(max_scan)
    lower = data.lower()
    windows = []
    bounded_windows = []
    start = 0
    while True:
        index = lower.find(b"userinfo", start)
        if index < 0:
            break
        server_query_index = lower.find(b"server_query", index)
        if server_query_index < 0 or server_query_index - index > 12 * 1024:
            end = index + 12 * 1024
        else:
            end = server_query_index
            bounded_windows.append(data[index:end])
        windows.append(data[index:end])
        start = index + len("userinfo")

    if bounded_windows:
        windows = bounded_windows

    if not windows:
        windows = [data[: min(len(data), 512 * 1024)]]

    counts = {}
    account_ids = {}
    order = []
    seen_order = set()
    for window in windows:
        section_names = extract_printable_runs(window)
        if not section_names:
            section_names = extract_utf8_strings_from_blob(window)
        slot = 0
        for name in section_names:
            normalized = " ".join(name.split())
            if not looks_like_player_name(normalized):
                continue
            slot += 1
            key = normalized.casefold()
            counts[key] = counts.get(key, 0) + 1
            account_id = extract_account_id_near_name(window, normalized)
            if account_id and key not in account_ids:
                account_ids[key] = account_id
            if key not in seen_order:
                order.append((key, normalized, slot))
                seen_order.add(key)

    if "eeza" in counts and b"Reeza" in data[: min(len(data), 64 * 1024 * 1024)]:
        counts["reeza"] = counts.pop("eeza")
        if "eeza" in account_ids:
            account_ids["reeza"] = account_ids.pop("eeza")
        order = [("reeza", "Reeza", slot) if key == "eeza" else (key, name, slot) for key, name, slot in order]

    full_known_names = [
        "НА МЯГКИХ ЛАПКАХ",
    ]
    for full_name in full_known_names:
        encoded = full_name.encode("utf-8")
        if encoded not in data:
            continue
        prefix = full_name[: max(4, len(full_name) - 3)].casefold()
        for key, name, slot in list(order):
            if key != full_name.casefold() and key.startswith(prefix):
                counts[full_name.casefold()] = counts.pop(key)
                if key in account_ids:
                    account_ids[full_name.casefold()] = account_ids.pop(key)
                order = [(full_name.casefold(), full_name, old_slot) if old_key == key else (old_key, old_name, old_slot) for old_key, old_name, old_slot in order]
                break

    ranked = []
    for key, name, slot in order:
        count = counts[key]
        score = player_name_score(name, count)
        ranked.append({"name": name, "slot": slot, "accountId": account_ids.get(key, ""), "count": count, "score": score})
    ranked = [item for item in ranked if item["score"] > 0]
    ranked = sorted(ranked, key=lambda item: (-item["score"], -item["count"], item["name"].casefold()))
    players = ranked[:20]
    return {
        "path": str(path),
        "players": players,
        "count": len(players),
        "message": f"Found {len(players)} possible player names in userinfo." if players else "No player names were found in userinfo.",
    }


def parse_vdf_flags(text):
    wants = re.search(r'"WantsOfflineMode"\s+"([^"]+)"', text, re.I)
    skip = re.search(r'"SkipOfflineModeWarning"\s+"([^"]+)"', text, re.I)
    offline = re.search(r'"Offline"\s+"([^"]+)"', text, re.I)
    return {
        "wantsOfflineMode": wants.group(1) == "1" if wants else None,
        "skipOfflineWarning": skip.group(1) == "1" if skip else None,
        "offline": offline.group(1) == "1" if offline else None,
    }


def steam_offline_signals(steam_path):
    signals = {}
    checked_files = []
    for relative in (
        Path("config") / "loginusers.vdf",
        Path("config") / "config.vdf",
        Path("config") / "steam.cfg",
    ):
        path = steam_path / relative
        if not path.exists():
            continue
        checked_files.append(str(path))
        text = path.read_text(encoding="utf-8", errors="ignore")
        flags = parse_vdf_flags(text)
        if flags["wantsOfflineMode"] is not None:
            signals["WantsOfflineMode"] = flags["wantsOfflineMode"]
        if flags["skipOfflineWarning"] is not None:
            signals["SkipOfflineModeWarning"] = flags["skipOfflineWarning"]
        if flags["offline"] is not None:
            signals[f"{relative.name}:Offline"] = flags["offline"]
        if re.search(r"^\s*BootStrapperInhibitAll\s*=\s*enable\s*$", text, re.I | re.M):
            signals["BootStrapperInhibitAll"] = True
        if re.search(r"^\s*ForceOfflineMode\s*=\s*enable\s*$", text, re.I | re.M):
            signals["ForceOfflineMode"] = True

    registry_offline = read_registry_value("HKEY_CURRENT_USER", r"Software\Valve\Steam", "Offline")
    if registry_offline is not None:
        try:
            signals["registry:Offline"] = int(registry_offline) == 1
        except (TypeError, ValueError):
            signals["registry:Offline"] = str(registry_offline).strip() == "1"
    return signals, checked_files


def steam_status():
    steam_path = find_steam_path()
    if not steam_path:
        return {
            "found": False,
            "offlineLikely": False,
            "message": "Steam config was not found in the usual install locations.",
        }

    signals, checked_files = steam_offline_signals(steam_path)
    positive = sorted(key for key, value in signals.items() if value is True)
    negative = sorted(key for key, value in signals.items() if value is False)
    offline = bool(positive)
    return {
        "found": True,
        "steamPath": str(steam_path),
        "offlineLikely": offline,
        "signals": signals,
        "checkedFiles": checked_files,
        "message": "Steam appears to be in offline mode." if offline else "Steam does not appear to be in offline mode.",
    }


def hlae_status():
    return {
        "installed": HLAE_EXE.exists(),
        "path": str(HLAE_EXE) if HLAE_EXE.exists() else "",
        "installDir": str(HLAE_DIR),
        "runtimeRoot": str(RUNTIME_ROOT),
        "apiUrl": HLAE_API_URL,
        "releasesUrl": HLAE_RELEASES_URL,
        "message": "Managed HLAE is installed." if HLAE_EXE.exists() else "Managed HLAE is not installed yet.",
    }


def github_json(url):
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "CS2-Demo-Recorder",
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def latest_hlae_asset():
    release = github_json(HLAE_API_URL)
    assets = release.get("assets", [])
    zip_assets = [
        asset for asset in assets
        if asset.get("name", "").lower().endswith(".zip")
        and "hlae" in asset.get("name", "").lower()
    ]
    if not zip_assets:
        zip_assets = [asset for asset in assets if asset.get("name", "").lower().endswith(".zip")]
    if not zip_assets:
        raise FileNotFoundError("The latest AdvancedFX release has no downloadable ZIP asset.")
    asset = zip_assets[0]
    return {
        "tag": release.get("tag_name", ""),
        "name": asset.get("name", ""),
        "url": asset.get("browser_download_url", ""),
    }


def safe_extract(zip_file, target_dir):
    target_dir = target_dir.resolve()
    for member in zip_file.infolist():
        destination = (target_dir / member.filename).resolve()
        if not str(destination).startswith(str(target_dir)):
            raise ValueError(f"Unsafe path in archive: {member.filename}")
    zip_file.extractall(target_dir)


def install_hlae():
    TOOLS.mkdir(exist_ok=True)
    asset = latest_hlae_asset()
    if not asset["url"]:
        raise FileNotFoundError("The selected HLAE release asset has no download URL.")

    download_path = GENERATED / "hlae-latest.zip"
    temp_dir = GENERATED / "hlae-extract"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True)

    request = urllib.request.Request(
        asset["url"],
        headers={"User-Agent": "CS2-Demo-Recorder"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        download_path.write_bytes(response.read())

    with zipfile.ZipFile(download_path) as archive:
        safe_extract(archive, temp_dir)

    extracted = list(temp_dir.rglob("hlae.exe"))
    if not extracted:
        raise FileNotFoundError("The downloaded HLAE archive did not contain hlae.exe.")

    source_root = extracted[0].parent
    if HLAE_DIR.exists():
        backup = TOOLS / f"hlae-backup-{time.strftime('%Y%m%d-%H%M%S')}"
        HLAE_DIR.rename(backup)
    shutil.copytree(source_root, HLAE_DIR)
    shutil.rmtree(temp_dir, ignore_errors=True)
    download_path.unlink(missing_ok=True)

    return {
        **hlae_status(),
        "installed": True,
        "path": str(HLAE_EXE),
        "version": asset["tag"],
        "assetName": asset["name"],
        "message": f"HLAE {asset['tag']} was downloaded from the official AdvancedFX GitHub release and installed locally.",
    }


def find_ffmpeg_path():
    candidates = [
        FFMPEG_EXE,
        TOOLS / "ffmpeg" / "bin" / "ffmpeg.exe",
        TOOLS / "ffmpeg" / "ffmpeg.exe",
        ROOT / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe",
        ROOT / "tools" / "ffmpeg" / "ffmpeg.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    found = shutil.which("ffmpeg")
    return Path(found) if found else None


def find_ffprobe_path(ffmpeg_path):
    sibling = Path(ffmpeg_path).with_name("ffprobe.exe")
    if sibling.exists():
        return sibling
    found = shutil.which("ffprobe")
    return Path(found) if found else None


def ffmpeg_status():
    ffmpeg = find_ffmpeg_path()
    return {
        "found": ffmpeg is not None,
        "path": str(ffmpeg) if ffmpeg else "",
        "installDir": str(FFMPEG_DIR),
        "downloadUrl": FFMPEG_DOWNLOAD_URL,
        "message": "FFmpeg is available for audio capture." if ffmpeg else "FFmpeg was not found. Select ffmpeg.exe to enable audio capture.",
    }


def install_ffmpeg():
    TOOLS.mkdir(parents=True, exist_ok=True)
    download_path = GENERATED / "ffmpeg-latest.zip"
    temp_dir = GENERATED / "ffmpeg-extract"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True)

    request = urllib.request.Request(
        FFMPEG_DOWNLOAD_URL,
        headers={"User-Agent": "CS2-Demo-Recorder"},
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        download_path.write_bytes(response.read())

    with zipfile.ZipFile(download_path) as archive:
        safe_extract(archive, temp_dir)

    extracted = list(temp_dir.rglob("ffmpeg.exe"))
    if not extracted:
        raise FileNotFoundError("The downloaded FFmpeg archive did not contain ffmpeg.exe.")

    source_root = extracted[0].parent.parent
    if FFMPEG_DIR.exists():
        backup = TOOLS / f"ffmpeg-backup-{time.strftime('%Y%m%d-%H%M%S')}"
        FFMPEG_DIR.rename(backup)
    shutil.copytree(source_root, FFMPEG_DIR)
    shutil.rmtree(temp_dir, ignore_errors=True)
    download_path.unlink(missing_ok=True)

    return {
        **ffmpeg_status(),
        "installed": True,
        "path": str(FFMPEG_EXE),
        "message": "FFmpeg was downloaded and installed locally.",
    }


def audio_status():
    running = AUDIO_PROCESS is not None and AUDIO_PROCESS.poll() is None
    return {
        "running": running,
        "outputPath": str(AUDIO_OUTPUT) if AUDIO_OUTPUT else "",
        **ffmpeg_status(),
    }


def start_audio_capture(payload):
    global AUDIO_PROCESS, AUDIO_OUTPUT
    if AUDIO_PROCESS is not None and AUDIO_PROCESS.poll() is None:
        raise RuntimeError("Audio capture is already running.")

    ffmpeg_candidate = payload.get("ffmpegPath") or find_ffmpeg_path()
    if not ffmpeg_candidate:
        raise FileNotFoundError("ffmpeg.exe was not found. Select ffmpeg.exe first.")
    ffmpeg_path = Path(ffmpeg_candidate).expanduser()
    if not ffmpeg_path.is_file():
        raise FileNotFoundError("ffmpeg.exe was not found. Select ffmpeg.exe first.")

    demo_path = Path(payload.get("demoPath") or "audio").expanduser()
    output_dir = Path(payload.get("outputDir") or RECORDINGS).expanduser()
    session_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", payload.get("sessionName") or demo_path.stem).strip("_")
    output_dir.mkdir(parents=True, exist_ok=True)
    AUDIO_OUTPUT = output_dir / f"{session_name}_game_audio.wav"
    device = payload.get("audioDevice") or "default"
    audio_mode = payload.get("audioMode") or "system"
    audio_gain = float(payload.get("audioGain") or 0.65)
    audio_input = device
    if audio_mode == "system":
        if device.startswith("audio="):
            audio_input = device
        elif device.startswith("loopback:"):
            audio_input = f"audio={device}"
        else:
            audio_input = f"audio=loopback:{device}"

    command = [
        str(ffmpeg_path),
        "-y",
        "-f",
        "wasapi",
    ]
    command.extend([
        "-i",
        audio_input,
        "-af",
        f"volume={audio_gain},alimiter=limit=0.95",
        "-ac",
        "2",
        "-ar",
        "48000",
        "-c:a",
        "pcm_s16le",
        str(AUDIO_OUTPUT),
    ])
    log_path = GENERATED / "audio-capture.log"
    log_path.write_text("", encoding="utf-8")
    log_file = log_path.open("ab")
    AUDIO_PROCESS = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=log_file,
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
    )
    time.sleep(0.5)
    if AUDIO_PROCESS.poll() is not None:
        log_file.close()
        detail = log_path.read_text(encoding="utf-8", errors="ignore")[-1200:] if log_path.exists() else ""
        raise RuntimeError(f"FFmpeg audio capture exited immediately. {detail}".strip())
    return {"running": True, "outputPath": str(AUDIO_OUTPUT), "command": command, "logPath": str(log_path)}


def stop_audio_capture():
    global AUDIO_PROCESS
    if AUDIO_PROCESS is None or AUDIO_PROCESS.poll() is not None:
        return {"running": False, "outputPath": str(AUDIO_OUTPUT) if AUDIO_OUTPUT else "", "message": "Audio capture was not running."}

    try:
        if AUDIO_PROCESS.stdin:
            AUDIO_PROCESS.stdin.write(b"q\n")
            AUDIO_PROCESS.stdin.flush()
        AUDIO_PROCESS.wait(timeout=8)
    except Exception:
        AUDIO_PROCESS.terminate()
        AUDIO_PROCESS.wait(timeout=8)

    return {"running": False, "outputPath": str(AUDIO_OUTPUT), "message": "Audio capture stopped."}


def clamp_float(value, default, minimum, maximum):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(number, maximum))


def clamp_int(value, default, minimum, maximum):
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(number, maximum))


def video_quality_value(payload):
    return clamp_int(payload.get("videoQuality"), 9, 0, 51)


def video_preset_value(payload):
    preset = str(payload.get("videoPreset") or "ultrafast").strip()
    allowed = {"ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"}
    return preset if preset in allowed else "ultrafast"


def hlae_blur_settings(payload, output_fps):
    method = str(payload.get("motionBlurMethod") or "rectangle").strip().lower()
    if method not in {"rectangle"}:
        method = "rectangle"
    return {
        "enabled": payload_bool(payload, "motionBlurEnabled", False),
        "strength": 1.0 if payload_bool(payload, "motionBlurEnabled", False) else 0.0,
        "method": method,
        "exposure": clamp_float(payload.get("motionBlurAmount"), 0.7, 0.0, 1.0),
        "sample_fps": clamp_int(payload.get("motionBlurSampleFps"), 1080, output_fps, 10000),
        "output_fps": output_fps,
    }


def build_commands(payload):
    demo_path = Path(payload["demoPath"]).expanduser()
    output_dir = Path(payload.get("outputDir") or RECORDINGS).expanduser()
    session_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", payload.get("sessionName") or demo_path.stem).strip("_")
    resolution = payload.get("resolution", {"width": 1920, "height": 1080})
    width = int(resolution.get("width", 1920))
    height = int(resolution.get("height", 1080))
    fps = int(payload.get("framerate", 60))
    fov = int(payload.get("fov", 100))
    sound_enabled = bool(payload.get("soundEnabled", True))
    sync_cue_enabled = sound_enabled and bool(payload.get("syncCueEnabled", True))
    sync_cue_sound = (payload.get("syncCueSound") or "ui/beepclear").strip()
    recording_format = payload.get("recordingFormat") or "ffmpeg"
    video_quality = video_quality_value(payload)
    video_preset = video_preset_value(payload)
    blur = hlae_blur_settings(payload, fps)
    record_fps = blur["sample_fps"] if recording_format == "ffmpeg" and blur["enabled"] else fps
    pov = (payload.get("pov") or "").strip()
    pov_name = (payload.get("povName") or "").strip()
    pov_slot = (payload.get("povSlot") or "").strip()
    pov_account_id = (payload.get("povAccountId") or "").strip()
    output_base = output_dir / session_name
    audio_output = output_base / "take0000" / "audio.wav"

    launch_args = [
        "-steam",
        "-insecure",
        "+sv_lan",
        "1",
        "-console",
        "-novid",
        "-sw",
        "-w",
        str(width),
        "-h",
        str(height),
    ]

    hud_commands = [
        *build_live_refresh_commands(payload),
    ]

    pov_commands = []
    if pov:
        target_name = pov_name or ("" if pov.isdigit() else pov)
        if pov_account_id.isdigit():
            pov_commands.extend([
                "spec_lock_to_accountid 0",
                f"spec_lock_to_accountid {pov_account_id}",
            ])
        if target_name:
            pov_commands.append(f'spec_player "{target_name}"')
        elif pov.isdigit():
            pov_commands.append(f"spec_player {pov}")
        pov_commands.extend([
            "spec_mode 4",
            "firstperson",
        ])
        if not pov_account_id.isdigit():
            pov_commands.append("spec_lock_to_current_player 1")

    commands = [
        "sv_cheats 1",
        "mirv_cvar_unhide_all",
        "mirv_streams record screen enabled 1",
        f"mirv_streams record fps {record_fps}",
        f"mirv_streams record startMovieWav {1 if sound_enabled else 0}",
        f"fov_cs_debug {fov}",
        *hud_commands,
        f"host_framerate {fps}",
        "host_timescale 1",
    ]

    if recording_format == "ffmpeg":
        commands.extend([
            f'mirv_streams settings add ffmpeg mp4 "-c:v libx264 -pix_fmt yuv420p -preset {video_preset} -crf {video_quality} {{QUOTE}}{{AFX_STREAM_PATH}}\\video.mp4{{QUOTE}}"',
        ])
        if blur["enabled"]:
            commands.extend([
                "mirv_sample_enable 1",
                f"mirv_sample_sps {blur['sample_fps']}",
                "mirv_streams settings add sampler blur",
                "mirv_streams settings edit blur settings mp4",
                f"mirv_streams settings edit blur strength {blur['strength']:g}",
                f"mirv_streams settings edit blur method {blur['method']}",
                f"mirv_streams settings edit blur exposure {blur['exposure']:g}",
                f"mirv_streams settings edit blur fps {blur['output_fps']}",
                "mirv_streams record screen settings blur",
            ])
        else:
            commands.append("mirv_sample_enable 0")
            commands.append("mirv_streams record screen settings mp4")
    else:
        pass

    commands.extend([
        f'playdemo "{demo_path}"',
        *hud_commands,
        *pov_commands,
        "mirv_cmd clear",
        f'mirv_streams record name "{output_base}"',
    ])

    commands.append('mirv_cmd addAtTick 32 "gameui_hide; demoui"')
    hud_chunks = [hud_commands[index:index + 4] for index in range(0, len(hud_commands), 4)]
    for index, chunk in enumerate(hud_chunks, start=1):
        commands.append(f'alias cs2dt_hud{index} "{cfg_quote("; ".join(chunk))}"')
    hud_alias_call = "; ".join(f"cs2dt_hud{index}" for index in range(1, len(hud_chunks) + 1))
    commands.append(f'alias cs2dt_hud "{hud_alias_call}"')
    if pov_commands:
        commands.append(f'alias cs2dt_pov "{cfg_quote("; ".join(pov_commands))}"')
        for tick in (32, 64, 128, 256, 512):
            commands.append(f'mirv_cmd addAtTick {tick} "cs2dt_hud; cs2dt_pov"')
    else:
        for tick in (32, 64, 128, 256, 512):
            commands.append(f'mirv_cmd addAtTick {tick} "cs2dt_hud"')

    if sound_enabled:
        commands.extend([
        ])

    start_actions = [
        f"host_framerate {fps}",
        "mirv_streams record start",
        *([f"play {cfg_quote(sync_cue_sound)}"] if sync_cue_enabled and sync_cue_sound else []),
        "alias rec cs2dt_rec_stop",
    ]
    stop_actions = [
        "mirv_streams record end",
        "host_framerate 0",
        "alias rec cs2dt_rec_start",
    ]

    commands.extend([
        f'alias cs2dt_rec_start "{cfg_quote("; ".join(start_actions))}"',
        f'alias cs2dt_rec_stop "{cfg_quote("; ".join(stop_actions))}"',
        "alias rec cs2dt_rec_start",
        "bind F8 \"demoui; gameui_hide\"",
        'bind F9 "cs2dt_hud"',
        'bind F10 "rec"',
        'bind F11 "exec cs2_demo_refresh"',
    ])

    if pov_commands:
        commands.insert(-1, 'bind F7 "cs2dt_hud; cs2dt_pov"')
        if target_name and pov_slot:
            commands.insert(-1, f'bind F6 "spec_player {cfg_quote(pov_slot)}; spec_mode 4; firstperson; spec_lock_to_current_player 1"')
        if target_name and pov_account_id:
            commands.insert(-1, f'bind F5 "spec_lock_to_accountid 0; spec_lock_to_accountid {cfg_quote(pov_account_id)}; spec_mode 4; firstperson"')
        display_pov = f"{target_name} (account {pov_account_id}, userinfo slot {pov_slot})" if target_name and pov_account_id else (f"{target_name} (userinfo slot {pov_slot})" if target_name and pov_slot else pov)

    firewall_script = "\n".join([
        "$cs2 = Read-Host 'Full path to cs2.exe'",
        "New-NetFirewallRule -DisplayName 'CS2 Demo Tool Block Outbound' -Direction Outbound -Program $cs2 -Action Block -Profile Any",
        "New-NetFirewallRule -DisplayName 'CS2 Demo Tool Block Inbound' -Direction Inbound -Program $cs2 -Action Block -Profile Any",
        "Write-Host 'Rules added. Remove them later with:'",
        "Write-Host \"Remove-NetFirewallRule -DisplayName 'CS2 Demo Tool Block Outbound'\"",
        "Write-Host \"Remove-NetFirewallRule -DisplayName 'CS2 Demo Tool Block Inbound'\"",
    ])

    return {
        "launchArgs": launch_args,
        "launchArgString": " ".join(shlex.quote(arg) for arg in launch_args),
        "consoleCommands": commands,
        "cfgText": "\n".join(commands) + "\n",
        "firewallScript": firewall_script,
        "outputBase": str(output_base),
        "audioOutput": str(audio_output),
        "videoQuality": video_quality,
        "videoPreset": video_preset,
        "hlaeBlur": blur,
    }


def write_auto_cfg(payload):
    data = build_commands(payload)
    mmcfg = RUNTIME_ROOT / "mmcfg"
    cfg_dir = mmcfg / "cfg"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_paths = write_chained_cfgs(cfg_dir, "cs2_demo_auto", data["consoleCommands"])
    refresh_paths = write_refresh_cfg(payload, cfg_dir)
    data["cfgPaths"] = [str(path) for path in cfg_paths]
    data["refreshCfgPaths"] = [str(path) for path in refresh_paths]
    data["cfgText"] = "\n\n".join(f"// {path.name}\n{path.read_text(encoding='utf-8')}" for path in cfg_paths)
    return data, mmcfg, cfg_paths[0]


def write_refresh_cfg(payload, cfg_dir=None):
    cfg_dir = cfg_dir or (RUNTIME_ROOT / "mmcfg" / "cfg")
    cfg_dir.mkdir(parents=True, exist_ok=True)
    commands = [
        *build_live_refresh_commands(payload),
        "echo CS2 Demo Tool options refreshed",
    ]
    return write_chained_cfgs(cfg_dir, "cs2_demo_refresh", commands)


def write_chained_cfgs(cfg_dir, base_name, commands, max_commands_per_file=18):
    old_files = list(cfg_dir.glob(f"{base_name}*.cfg"))
    for old_file in old_files:
        old_file.unlink(missing_ok=True)

    chunks = [commands[index:index + max_commands_per_file] for index in range(0, len(commands), max_commands_per_file)]
    if not chunks:
        chunks = [[]]

    paths = []
    for index, chunk in enumerate(chunks):
        name = f"{base_name}.cfg" if index == 0 else f"{base_name}_{index + 1:02d}.cfg"
        path = cfg_dir / name
        lines = list(chunk)
        if index + 1 < len(chunks):
            next_name = f"{base_name}_{index + 2:02d}"
            lines.append(f"exec {next_name}")
        else:
            lines.append(f'echo "{base_name} cfg chain loaded ({len(chunks)} files)."')
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        paths.append(path)
    return paths


def ensure_hlae_ffmpeg_config(hlae_path, payload):
    ffmpeg_candidate = payload.get("ffmpegPath") or find_ffmpeg_path()
    if not ffmpeg_candidate:
        return ""
    ffmpeg_path = Path(ffmpeg_candidate).expanduser()
    if not ffmpeg_path.is_file():
        return ""
    ffmpeg_dir = hlae_path.parent / "ffmpeg"
    ffmpeg_dir.mkdir(parents=True, exist_ok=True)
    ini_path = ffmpeg_dir / "ffmpeg.ini"
    ini_path.write_text(f"[Ffmpeg]\nPath={ffmpeg_path}\n", encoding="utf-8")
    return str(ini_path)


def build_hlae_custom_loader_args(payload, mmcfg):
    hlae_path = Path(payload.get("hlaePath") or HLAE_EXE).expanduser()
    if not hlae_path.exists():
        raise FileNotFoundError("HLAE was not found. Install managed HLAE or select hlae.exe manually.")

    hook_path = hlae_path.parent / "x64" / "AfxHookSource2.dll"
    if not hook_path.exists():
        raise FileNotFoundError(f"AfxHookSource2.dll was not found at {hook_path}.")

    cs2_candidate = payload.get("cs2Path") or find_cs2_path()
    if not cs2_candidate:
        raise FileNotFoundError("cs2.exe was not found. Select the CS2 executable manually.")
    cs2_path = Path(cs2_candidate).expanduser()
    if not cs2_path.exists():
        raise FileNotFoundError("cs2.exe was not found. Select the CS2 executable manually.")

    ensure_hlae_ffmpeg_config(hlae_path, payload)

    resolution = payload.get("resolution", {"width": 1920, "height": 1080})
    width = int(resolution.get("width", 1920))
    height = int(resolution.get("height", 1080))
    cmd_line = " ".join([
        "-steam",
        "-insecure",
        "+sv_lan 1",
        "-console",
        "-novid",
        "-sw",
        f"-w {width}",
        f"-h {height}",
        "-afxDisableSteamStorage",
        "+exec cs2_demo_auto",
    ])

    args = [
        str(hlae_path),
        "-customLoader",
        "-noGui",
        "-autoStart",
        "-hookDllPath",
        str(hook_path),
        "-programPath",
        str(cs2_path),
        "-cmdLine",
        cmd_line,
        "-addEnv",
        f"USRLOCALCSGO={mmcfg}",
    ]
    ffmpeg_path = find_ffmpeg_path()
    if ffmpeg_path:
        ffmpeg_bin = ffmpeg_path.parent
        args.extend([
            "-addEnv",
            f"PATH={ffmpeg_bin}{os.pathsep}{os.environ.get('PATH', '')}",
        ])
    return args


def start_auto_recording(payload):
    global LAST_AUTO_SESSION
    data, mmcfg, cfg_path = write_auto_cfg(payload)
    audio = {
        "running": False,
        "mode": "hlae",
        "outputPath": data["audioOutput"] if payload.get("soundEnabled", True) else "",
        "message": "HLAE will record audio.wav in the take folder." if payload.get("soundEnabled", True) else "Sound is disabled.",
    }

    args = build_hlae_custom_loader_args(payload, mmcfg)
    subprocess.Popen(args, cwd=str(Path(args[0]).parent))
    LAST_AUTO_SESSION = {
        "startedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "cfgPath": str(cfg_path),
        "mmcfg": str(mmcfg),
        "hlaeArgs": args,
        "audio": audio,
        **data,
    }
    return {"started": True, **LAST_AUTO_SESSION}


def stop_auto_recording():
    return {
        "stoppedAudio": {"running": False, "mode": "hlae"},
        "message": "Recording helper stopped. In CS2, F10 toggles HLAE recording when the demo is open.",
        "lastSession": LAST_AUTO_SESSION,
    }


def recordings_root(output_dir=None):
    return Path(output_dir or RECORDINGS).expanduser()


def latest_take_folder(output_dir=None):
    root = recordings_root(output_dir)
    takes = []
    for session_dir in root.glob("*"):
        if not session_dir.is_dir():
            continue
        for take_dir in session_dir.glob("take*"):
            if take_dir.is_dir() and (any(take_dir.glob("*.tga")) or any(take_dir.glob("*.png"))):
                takes.append(take_dir)
    if not takes:
        return None
    return max(takes, key=lambda path: path.stat().st_mtime)


def take_media_paths(take_dir):
    take_dir = Path(take_dir)
    videos = [
        take_dir / "video.mp4",
        take_dir / "screen" / "video.mp4",
    ]
    for pattern in ("*.mp4", "*.mov", "*.mkv", "*.avi", "*.webm"):
        videos.extend(path for path in take_dir.glob(pattern) if path.is_file() and not path.stem.endswith("_with_audio"))
        screen_dir = take_dir / "screen"
        if screen_dir.is_dir():
            videos.extend(path for path in screen_dir.glob(pattern) if path.is_file() and not path.stem.endswith("_with_audio"))
    videos = [path for path in dict.fromkeys(videos) if path.exists()]
    audio = take_dir / "audio.wav"
    return {
        "takeDir": str(take_dir),
        "videos": videos,
        "video": max(videos, key=lambda path: path.stat().st_mtime) if videos else None,
        "audio": audio if audio.exists() else None,
        "hasFrames": any(take_dir.glob("*.tga")) or any(take_dir.glob("*.png")),
    }


def list_render_takes(output_dir=None):
    root = recordings_root(output_dir)
    takes = []
    for session_dir in root.glob("*"):
        if not session_dir.is_dir():
            continue
        for take_dir in session_dir.glob("take*"):
            if not take_dir.is_dir():
                continue
            media = take_media_paths(take_dir)
            if not media["video"] and not media["audio"] and not media["hasFrames"]:
                continue
            mtimes = [path.stat().st_mtime for path in [media["video"], media["audio"]] if path]
            frame_mtimes = [path.stat().st_mtime for pattern in ("*.tga", "*.png") for path in take_dir.glob(pattern)]
            mtimes.extend(frame_mtimes[:1])
            modified = max(mtimes) if mtimes else take_dir.stat().st_mtime
            takes.append({
                "takeDir": str(take_dir),
                "session": session_dir.name,
                "take": take_dir.name,
                "videoPath": str(media["video"]) if media["video"] else "",
                "audioPath": str(media["audio"]) if media["audio"] else "",
                "hasFrames": media["hasFrames"],
                "modified": modified,
                "label": f"{session_dir.name} / {take_dir.name}",
            })
    takes.sort(key=lambda item: item["modified"], reverse=True)
    return takes


def latest_video_file(output_dir=None):
    root = recordings_root(output_dir)
    videos = []
    for pattern in ("*.mp4", "*.mov", "*.mkv", "*.avi", "*.webm"):
        videos.extend(
            path for path in root.rglob(pattern)
            if path.is_file() and not path.stem.endswith("_with_audio")
        )
    if not videos:
        return None
    return max(videos, key=lambda path: path.stat().st_mtime)


def find_audio_for_video(video_path):
    candidates = [
        video_path.parent / "audio.wav",
        video_path.parent.parent / "audio.wav",
        Path(AUDIO_OUTPUT).expanduser() if AUDIO_OUTPUT else None,
    ]
    return next((candidate for candidate in candidates if candidate and candidate.exists()), None)


def media_duration_seconds(ffmpeg_path, media_path):
    media_path = Path(media_path)
    if media_path.suffix.lower() == ".wav":
        with wave.open(str(media_path), "rb") as wav:
            frames = wav.getnframes()
            rate = wav.getframerate()
            return frames / float(rate) if rate else None

    ffprobe_path = find_ffprobe_path(ffmpeg_path)
    if not ffprobe_path:
        return None
    command = [
        str(ffprobe_path),
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(media_path),
    ]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, cwd=str(ROOT))
    if result.returncode != 0:
        return None
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def mux_video_with_audio(ffmpeg_path, video, audio, payload=None):
    payload = payload or {}
    output_path = video.with_name(f"{video.stem}_with_audio.mp4")
    video_duration = media_duration_seconds(ffmpeg_path, video)
    audio_duration = media_duration_seconds(ffmpeg_path, audio)
    auto_trim = 0.0
    if video_duration and audio_duration and audio_duration > video_duration:
        auto_trim = min(audio_duration - video_duration, 10.0)
    manual_trim = max(0.0, float(payload.get("audioTrimMs") or 0) / 1000.0)
    audio_trim = auto_trim + manual_trim
    sync_cue_trimmed = bool(payload.get("syncCueEnabled", True)) and audio_trim > 0

    command = [
        str(ffmpeg_path),
        "-y",
        "-i",
        str(video),
    ]
    if audio_trim > 0:
        command.extend(["-ss", f"{audio_trim:.3f}"])
    command.extend([
        "-i",
        str(audio),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        str(output_path),
    ])
    log_path = GENERATED / "encode.log"
    with log_path.open("ab") as log_file:
        result = subprocess.run(command, stdout=log_file, stderr=log_file, cwd=str(ROOT))
    if result.returncode != 0:
        detail = log_path.read_text(encoding="utf-8", errors="ignore")[-1600:] if log_path.exists() else ""
        raise RuntimeError(f"FFmpeg mux failed. {detail}".strip())
    return {
        "encoded": True,
        "muxed": True,
        "takeDir": str(video.parent),
        "audioPath": str(audio),
        "videoPath": str(output_path),
        "sourceVideoPath": str(video),
        "audioTrimSeconds": round(audio_trim, 3),
        "autoAudioTrimSeconds": round(auto_trim, 3),
        "syncCueTrimmedByMux": sync_cue_trimmed,
        "videoDurationSeconds": round(video_duration, 3) if video_duration else None,
        "audioDurationSeconds": round(audio_duration, 3) if audio_duration else None,
        "message": "The raw audio.wav can contain the start cue, but the final mux trims the start of audio so the cue may be removed." if sync_cue_trimmed else "",
        "command": command,
        "logPath": str(log_path),
    }


def read_recent_log(path, max_chars=2200):
    return path.read_text(encoding="utf-8", errors="ignore")[-max_chars:] if path.exists() else ""


def render_status(output_dir=None):
    take = latest_take_folder(output_dir)
    video = latest_video_file(output_dir)
    takes = list_render_takes(output_dir)
    return {
        "found": take is not None or video is not None,
        "latestTake": str(take) if take else "",
        "latestVideo": str(video) if video else "",
        "takes": takes,
        "message": f"Latest video found: {video}" if video else ("Latest frame take folder found." if take else "No rendered frame take folder was found yet."),
    }


def encode_take(payload):
    ffmpeg_candidate = payload.get("ffmpegPath") or find_ffmpeg_path()
    if not ffmpeg_candidate:
        raise FileNotFoundError("ffmpeg.exe was not found. Select ffmpeg.exe first.")
    ffmpeg_path = Path(ffmpeg_candidate).expanduser()
    if not ffmpeg_path.is_file():
        raise FileNotFoundError("ffmpeg.exe was not found. Select ffmpeg.exe first.")

    output_dir = payload.get("outputDir") or RECORDINGS
    selected_take = payload.get("takeDir")
    take_dir = Path(selected_take).expanduser() if selected_take else None
    if take_dir and take_dir.is_dir():
        media = take_media_paths(take_dir)
        video = media["video"]
        audio = media["audio"] or (find_audio_for_video(video) if video else None)
        if video and audio:
            return mux_video_with_audio(ffmpeg_path, video, audio, payload)
    else:
        video = latest_video_file(output_dir)
        if video:
            audio = find_audio_for_video(video)
            if audio:
                return mux_video_with_audio(ffmpeg_path, video, audio, payload)

    if not take_dir:
        take_dir = Path(latest_take_folder(output_dir) or "").expanduser()
    if take_dir and take_dir.is_dir():
        media = take_media_paths(take_dir)
        if media["video"] and not media["hasFrames"]:
            return {
                "encoded": False,
                "muxed": False,
                "videoPath": str(media["video"]),
                "audioPath": "",
                "message": "Selected take has direct video, but no matching audio.wav was found.",
            }
    else:
        if not video:
            raise FileNotFoundError("No frame take folder or direct video file was found.")
        return {
            "encoded": False,
            "muxed": False,
            "videoPath": str(video),
            "audioPath": "",
            "message": "Latest direct video already exists, but no matching audio.wav was found.",
        }

    if not take_dir.is_dir():
        raise FileNotFoundError("No frame take folder was found.")
    frame_ext = "tga" if (take_dir / "00000.tga").exists() else "png"
    first_frame = take_dir / f"00000.{frame_ext}"
    if not first_frame.exists():
        raise FileNotFoundError(f"Expected first frame was not found: {first_frame}")

    fps = int(payload.get("framerate") or 60)
    output_path = Path(payload.get("videoOutput") or take_dir.parent / f"{take_dir.parent.name}_{take_dir.name}.mp4").expanduser()
    audio_candidates = [
        Path(payload.get("audioPath")).expanduser() if payload.get("audioPath") else None,
        take_dir / "audio.wav",
        take_dir.parent / "audio.wav",
        Path(AUDIO_OUTPUT).expanduser() if AUDIO_OUTPUT else None,
        take_dir.parent / f"{take_dir.parent.name}_game_audio.wav",
    ]
    audio_path = next((candidate for candidate in audio_candidates if candidate and candidate.exists()), take_dir / "audio.wav")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame_count = sum(1 for _frame in take_dir.glob(f"*.{frame_ext}"))
    video_duration = frame_count / float(fps) if fps and frame_count else None
    audio_duration = media_duration_seconds(ffmpeg_path, audio_path) if audio_path.exists() else None
    auto_trim = 0.0
    if video_duration and audio_duration and audio_duration > video_duration:
        auto_trim = min(audio_duration - video_duration, 10.0)
    manual_trim = max(0.0, float(payload.get("audioTrimMs") or 0) / 1000.0)
    audio_trim = auto_trim + manual_trim
    sync_cue_trimmed = bool(payload.get("syncCueEnabled", True)) and audio_trim > 0

    command = [
        str(ffmpeg_path),
        "-y",
        "-framerate",
        str(fps),
        "-i",
        str(take_dir / f"%05d.{frame_ext}"),
    ]
    if audio_path.exists():
        if audio_trim > 0:
            command.extend(["-ss", f"{audio_trim:.3f}"])
        command.extend(["-i", str(audio_path)])
    command.extend([
        "-c:v",
        "libx264",
        "-preset",
        payload.get("encodePreset") or "slow",
        "-crf",
        str(payload.get("crf") or 18),
        "-pix_fmt",
        "yuv420p",
    ])
    if audio_path.exists():
        command.extend(["-c:a", "aac", "-b:a", "192k", "-shortest"])
    command.append(str(output_path))

    log_path = GENERATED / "encode.log"
    with log_path.open("ab") as log_file:
        result = subprocess.run(command, stdout=log_file, stderr=log_file, cwd=str(ROOT))
    if result.returncode != 0:
        detail = log_path.read_text(encoding="utf-8", errors="ignore")[-1600:] if log_path.exists() else ""
        raise RuntimeError(f"FFmpeg encode failed. {detail}".strip())

    deleted_frames = False
    if payload.get("deleteFramesAfterEncode"):
        for frame in take_dir.glob(f"*.{frame_ext}"):
            frame.unlink()
        deleted_frames = True

    result = {
        "encoded": True,
        "takeDir": str(take_dir),
        "frameFormat": frame_ext,
        "deletedFrames": deleted_frames,
        "audioPath": str(audio_path) if audio_path.exists() else "",
        "videoPath": str(output_path),
        "audioTrimSeconds": round(audio_trim, 3),
        "autoAudioTrimSeconds": round(auto_trim, 3),
        "syncCueTrimmedByMux": sync_cue_trimmed,
        "videoDurationSeconds": round(video_duration, 3) if video_duration else None,
        "audioDurationSeconds": round(audio_duration, 3) if audio_duration else None,
        "message": "The raw audio.wav can contain the start cue, but the final encode trims the start of audio so the cue may be removed." if sync_cue_trimmed else "",
        "command": command,
        "logPath": str(log_path),
    }
    return result


def choose_path(kind):
    result = {"cancelled": True}

    def run_dialog():
        nonlocal result
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)

        if kind == "demo":
            path = filedialog.askopenfilename(
                title="Select Counter-Strike 2 demo",
                filetypes=[("Counter-Strike demo", "*.dem"), ("All files", "*.*")],
            )
        elif kind == "hlae":
            path = filedialog.askopenfilename(
                title="Select hlae.exe",
                filetypes=[("HLAE executable", "hlae.exe"), ("Executables", "*.exe"), ("All files", "*.*")],
            )
        elif kind == "ffmpeg":
            path = filedialog.askopenfilename(
                title="Select ffmpeg.exe",
                filetypes=[("FFmpeg executable", "ffmpeg.exe"), ("Executables", "*.exe"), ("All files", "*.*")],
            )
        elif kind == "cs2":
            path = filedialog.askopenfilename(
                title="Select cs2.exe",
                initialdir=str((find_cs2_path() or Path.home()).parent),
                filetypes=[("CS2 executable", "cs2.exe"), ("Executables", "*.exe"), ("All files", "*.*")],
            )
        else:
            path = filedialog.askdirectory(title="Select output folder")

        root.destroy()
        if path:
            result = {"cancelled": False, "path": path}

    thread = threading.Thread(target=run_dialog)
    thread.start()
    thread.join()
    return result


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        parsed = urllib.parse.urlparse(path)
        clean = parsed.path
        if clean == "/":
            return str(STATIC / "index.html")
        if clean.startswith("/static/"):
            return str(ROOT / clean.lstrip("/"))
        return str(STATIC / clean.lstrip("/"))

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/steam/status":
            json_response(self, 200, steam_status())
            return
        if parsed.path == "/api/hlae/status":
            json_response(self, 200, hlae_status())
            return
        if parsed.path == "/api/audio/status":
            json_response(self, 200, audio_status())
            return
        if parsed.path == "/api/cs2/status":
            json_response(self, 200, cs2_status())
            return
        if parsed.path == "/api/render/status":
            json_response(self, 200, render_status())
            return
        if parsed.path == "/api/select":
            query = urllib.parse.parse_qs(parsed.query)
            kind = query.get("kind", ["demo"])[0]
            json_response(self, 200, choose_path(kind))
            return
        super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/generate":
            payload = read_json(self)
            try:
                data = build_commands(payload)
                timestamp = time.strftime("%Y%m%d-%H%M%S")
                cfg_path = GENERATED / f"record-{timestamp}.cfg"
                ps_path = GENERATED / f"firewall-block-cs2-{timestamp}.ps1"
                cfg_path.write_text(data["cfgText"], encoding="utf-8")
                ps_path.write_text(data["firewallScript"], encoding="utf-8")
                data.update({"cfgPath": str(cfg_path), "firewallPath": str(ps_path)})
                json_response(self, 200, data)
            except Exception as exc:
                json_response(self, 400, {"error": str(exc)})
            return

        if parsed.path == "/api/demo/players":
            payload = read_json(self)
            try:
                json_response(self, 200, inspect_demo_players(payload.get("demoPath", "")))
            except Exception as exc:
                json_response(self, 400, {"error": str(exc), "players": []})
            return

        if parsed.path == "/api/launch-hlae":
            payload = read_json(self)
            try:
                hlae_path = Path(payload.get("hlaePath") or HLAE_EXE).expanduser()
                if not hlae_path.exists():
                    raise FileNotFoundError("HLAE was not found. Install managed HLAE or select hlae.exe manually.")
                commands = build_commands(payload)
                args = [str(hlae_path), *commands["launchArgs"]]
                subprocess.Popen(args, cwd=str(hlae_path.parent))
                json_response(self, 200, {"launched": True, "args": args})
            except Exception as exc:
                json_response(self, 400, {"error": str(exc)})
            return

        if parsed.path == "/api/hlae/install":
            try:
                json_response(self, 200, install_hlae())
            except Exception as exc:
                json_response(self, 400, {"error": str(exc), **hlae_status()})
            return

        if parsed.path == "/api/audio/start":
            payload = read_json(self)
            try:
                json_response(self, 200, start_audio_capture(payload))
            except Exception as exc:
                json_response(self, 400, {"error": str(exc), **audio_status()})
            return

        if parsed.path == "/api/ffmpeg/install":
            try:
                json_response(self, 200, install_ffmpeg())
            except Exception as exc:
                json_response(self, 400, {"error": str(exc), **ffmpeg_status()})
            return

        if parsed.path == "/api/audio/stop":
            try:
                json_response(self, 200, stop_audio_capture())
            except Exception as exc:
                json_response(self, 400, {"error": str(exc), **audio_status()})
            return

        if parsed.path == "/api/auto/start":
            payload = read_json(self)
            try:
                json_response(self, 200, start_auto_recording(payload))
            except Exception as exc:
                json_response(self, 400, {"error": str(exc)})
            return

        if parsed.path == "/api/auto/stop":
            try:
                json_response(self, 200, stop_auto_recording())
            except Exception as exc:
                json_response(self, 400, {"error": str(exc)})
            return

        if parsed.path == "/api/render/encode":
            payload = read_json(self)
            try:
                json_response(self, 200, encode_take(payload))
            except Exception as exc:
                json_response(self, 400, {"error": str(exc), **render_status()})
            return

        json_response(self, 404, {"error": "Not found"})


def main():
    port = int(os.environ.get("PORT", "8020"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"CS2 Demo Tool running at http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
