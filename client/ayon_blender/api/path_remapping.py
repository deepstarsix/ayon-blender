"""Cross-platform path remapping for Blender assets.

Remaps image, library, cache, volume, and movie clip paths between
Linux and Windows mount points when a .blend file is opened.

The path mapping rules are read from AYON's project settings
under Core > Disk Mapping.
"""
import os
import sys
import bpy

from ayon_core.lib import Logger
from ayon_core.settings import get_project_settings
from ayon_core.pipeline import get_current_project_name

log = Logger.get_logger(__name__)


def _get_path_rules() -> list[tuple[str, str]]:
    try:
        project_name = get_current_project_name()
        if not project_name:
            return []
        project_settings = get_project_settings(project_name)
    except Exception:
        return []

    disk_mapping = (
        project_settings
        .get("core", {})
        .get("disk_mapping", {})
    )

    rules = []
    if sys.platform == "win32":
        win_mappings = disk_mapping.get("windows", [])
        for mapping in win_mappings:
            source = mapping.get("source", "")
            destination = mapping.get("destination", "")
            if source and destination:
                rules.append((source, destination))
    else:
        linux_mappings = disk_mapping.get("linux", [])
        for mapping in linux_mappings:
            source = mapping.get("source", "")
            destination = mapping.get("destination", "")
            if source and destination:
                rules.append((source, destination))

    rules.sort(key=lambda r: len(r[0]), reverse=True)
    return rules


def _remap_path(filepath: str, rules: list[tuple[str, str]]) -> str:
    # Normalize to forward slashes for comparison
    normalized = filepath.replace("\\", "/")

    for from_prefix, to_prefix in rules:
        normalized_prefix = from_prefix.replace("\\", "/")
        if normalized.lower().startswith(normalized_prefix.lower()):
            remainder = normalized[len(normalized_prefix):]
            result = to_prefix + remainder
            return result.replace("/", os.sep)

    return filepath


def remap_all_paths():
    rules = _get_path_rules()

    print(f"[AYON Path Remap] Platform: '{sys.platform}', "
          f"Rules: {rules}", flush=True)

    if not rules:
        print("[AYON Path Remap] No rules found, skipping.", flush=True)
        return

    remapped_count = 0

    for image in bpy.data.images:
        if not image.filepath:
            continue
        abs_path = bpy.path.abspath(image.filepath)
        new_path = _remap_path(abs_path, rules)
        if new_path != abs_path:
            print(f"[AYON Path Remap] Image: '{abs_path}' -> '{new_path}'",
                  flush=True)
            image.filepath = new_path
            remapped_count += 1

    for lib in bpy.data.libraries:
        if not lib.filepath:
            continue
        abs_path = bpy.path.abspath(lib.filepath)
        new_path = _remap_path(abs_path, rules)
        if new_path != abs_path:
            print(f"[AYON Path Remap] Library: '{abs_path}' -> '{new_path}'",
                  flush=True)
            lib.filepath = new_path
            remapped_count += 1

    for cache in bpy.data.cache_files:
        if not cache.filepath:
            continue
        abs_path = bpy.path.abspath(cache.filepath)
        new_path = _remap_path(abs_path, rules)
        if new_path != abs_path:
            print(f"[AYON Path Remap] Cache: '{abs_path}' -> '{new_path}'",
                  flush=True)
            cache.filepath = new_path
            remapped_count += 1

    for obj in bpy.data.objects:
        if obj.type != 'VOLUME':
            continue
        volume = obj.data
        if not volume.filepath:
            continue
        abs_path = bpy.path.abspath(volume.filepath)
        new_path = _remap_path(abs_path, rules)
        if new_path != abs_path:
            print(f"[AYON Path Remap] Volume: '{abs_path}' -> '{new_path}'",
                  flush=True)
            volume.filepath = new_path
            remapped_count += 1

    for clip in bpy.data.movieclips:
        if not clip.filepath:
            continue
        abs_path = bpy.path.abspath(clip.filepath)
        new_path = _remap_path(abs_path, rules)
        if new_path != abs_path:
            print(f"[AYON Path Remap] Clip: '{abs_path}' -> '{new_path}'",
                  flush=True)
            clip.filepath = new_path
            remapped_count += 1

    for font in bpy.data.fonts:
        if not font.filepath or font.filepath == "<builtin>":
            continue
        abs_path = bpy.path.abspath(font.filepath)
        new_path = _remap_path(abs_path, rules)
        if new_path != abs_path:
            print(f"[AYON Path Remap] Font: '{abs_path}' -> '{new_path}'",
                  flush=True)
            font.filepath = new_path
            remapped_count += 1

    for sound in bpy.data.sounds:
        if not sound.filepath:
            continue
        abs_path = bpy.path.abspath(sound.filepath)
        new_path = _remap_path(abs_path, rules)
        if new_path != abs_path:
            print(f"[AYON Path Remap] Sound: '{abs_path}' -> '{new_path}'",
                  flush=True)
            sound.filepath = new_path
            remapped_count += 1

    print(f"[AYON Path Remap] Done. Remapped {remapped_count} path(s).",
          flush=True)
    sys.stdout.flush()