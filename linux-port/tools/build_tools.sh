#!/bin/sh
# Builds build/titbit-tools: the import wizard and Titbit Studio as one x86-64
# executable (PyInstaller), so the Linux package needs no Python on the player's side.
#   sh tools/build_tools.sh            needs python3, python3-venv, python3-tk
set -e
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
venv=${XDG_CACHE_HOME:-$HOME/.cache}/titbit/tools-venv
work=${XDG_CACHE_HOME:-$HOME/.cache}/titbit/tools-work
python3 -c 'import tkinter' 2>/dev/null || { echo "Install python3-tk first (the import wizard window uses Tk)." >&2; exit 1; }
[ -x "$venv/bin/python" ] || python3 -m venv "$venv"
"$venv/bin/python" -m pip install -q -r "$root/requirements-tools.txt"
"$venv/bin/python" -m PyInstaller --noconfirm --clean --onefile --name titbit-tools \
  --distpath "$root/build" --workpath "$work" --specpath "$work" \
  --paths "$root/tools" --paths "$root/editor" --paths "$root/../tools" \
  --add-data "$root/editor/web:web" --add-data "$root/config/assets.json:config" \
  --add-data "$root/../config/mods.json:config" \
  --add-data "$root/../tools/widescreen_native_contours.json:tools" \
  --hidden-import server --hidden-import formats --hidden-import exporters \
  --hidden-import animation --hidden-import scene_runtime \
  --hidden-import titbit_setup --hidden-import start_studio \
  --hidden-import titbit_launcher --hidden-import titbit_profiles --hidden-import titbit_mods --hidden-import titbit_gate \
  --hidden-import widescreen --hidden-import widescreen_menu --hidden-import widescreen_exits \
  --hidden-import widescreen_foreground --hidden-import widescreen_occluders \
  --hidden-import widescreen_native_overlays --hidden-import widescreen_native_masks \
  --exclude-module numpy \
  "$root/tools/titbit_tools.py"
site=$("$venv/bin/python" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')
rm -rf "$root/build/tools-licenses"
python3 "$root/tools/collect_tool_licenses.py" "$work" "$site" "$root/build/tools-licenses"
echo "OK: $root/build/titbit-tools"
