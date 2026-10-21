# Modern Windows compatibility layer

`TITBIT_COMPAT` enables the modern layer; `tools/build_original.py` leaves it off.
Game call sites include `compat.h` behind that flag. Platform adaptations live
here; the settings launcher is a separate executable.

Build from the repository root with LLVM-MinGW and Visual Studio 2022 C++ Build
Tools/Windows SDK as described in [BUILD.md](../../docs/BUILD.md):

```powershell
$env:TITBIT_LLVM = 'C:\tools\llvm-mingw'
python tools/build_modern.py --fresh
```

The output is `build/modern-portable/`. Put your own `QUEST.ezd` and all 18 AVI files
beside `TitbitModern.exe`. `TitbitSettings.exe` changes display mode, window
size and aspect ratio, then can launch the game. Volume is changed in the
original in-game settings screen. Saves are not copied automatically.
See [BUILD.md](../../docs/BUILD.md) and [VALIDATION.md](../../docs/VALIDATION.md).

## Configuration

Settings are read from `[compat]` in `titbit_compat.ini` next to the EXE.
Environment variables `TITBIT_COMPAT_<KEY>` override individual values.

| Key | Default | Behaviour |
|---|---|---|
| `display` | `fullscreen` | Covers the current monitor without changing its desktop mode. `windowed` and `borderless` use the requested size. `exclusive` keeps the legacy mode-switch path. Alt+Enter/F11 toggle fullscreen and windowed. |
| `resolution` | `1024x768` | Window client size (`WIDTHxHEIGHT` or `auto`), bounded by the monitor work area. Fullscreen uses the current desktop resolution. |
| `aspect` | `fit` | Preserves original 4:3 with bars; `stretch` fills the window. Experimental `widescreen` expands the world in scenes listed by the local outpaint mod. |
| `widescreen_ratio` | `auto` | With `aspect=widescreen`: `16:9` or `16:10`; `auto` selects from the window aspect. The interface keeps its central 1024×768 canvas. |
| `setup` | `modern` | Skips the old registry-backed startup dialog. `legacy` keeps it available. |
| `cd` | `folder` | With local `QUEST.ezd`, satisfies the original drive check without mounted media. `disc` keeps the original check. |
| `video` | `auto` | Tries VfW first, then the fallback decoder. `internal` skips VfW. |
| `log` | `0` | `1` writes compatibility events to `titbit_compat.log` and the debugger. |

`compat_replay.cpp` also contains optional development-only input/clock replay.
It is off by default and is not required for normal play.

The experimental widescreen path reads a newline-separated list of scene filenames
from `widescreen-scenes.txt` beside the executable, or `TITBIT_WIDESCREEN_SCENES`.
The local mod pipeline creates this list together with the extended background
textures and geometry. Missing entries keep the original 4:3 projection, including
menus and minigames. Changing only the presentation option does not generate
missing artwork. Original data files are never modified by the display layer.
The in-game pointer alone can cross the central canvas into the wide side fields;
HUD panels and dialogs remain clipped to the original canvas.

For automated scene-render checks only, a process on a hidden Windows desktop
can set `TITBIT_WIDESCREEN_VALIDATION=1` and `TITBIT_VALIDATE_SCENE=scene.xml` to
start directly in an archive scene. Only a plain XML basename is accepted.
On the interactive desktop this override is ignored. Direct scene loading does
not initialize the normal startup's persistent interface or game progression;
these captures establish scene rendering, not a successful gameplay walkthrough.

## Components

- `compat_display.cpp`, `display_geometry.h`: DPI awareness, viewport, monitor
  fullscreen and mouse conversion. Original scene/UI coordinates stay 1024x768;
  3D is rendered into the physical viewport. The default path preserves the
  original artwork and field of view; widescreen changes only the horizontal field.
- `compat_volume.cpp`: the original two master-volume script functions control
  the game's Core Audio session when the old WinMM speaker mixer is unavailable.
  The system endpoint master volume is not changed.
- `compat_cd.cpp`: local-data alternative to the original CD-ROM check.
- `compat_video.cpp`: MP42/MPG4 and MP43 use Windows decoder DMOs; CRAM/MSVC
  (Microsoft Video 1, 16-bit) has a project decoder. Old codec installers are not
  bundled. Missing Windows media components, including on some N editions, can
  leave black video frames.
- `launcher.cpp`: standalone Unicode/DPI-aware display settings utility.
- `source_entry.cpp`: initializes compatibility before the VC6 CRT/application
  startup chain; normal operation leaves replay disabled.

## Scope of verification

The public source build and its menu/new-game/first-street smoke test are recorded
in [VALIDATION.md](../../docs/VALIDATION.md). This is not a full walkthrough,
whole-EXE byte comparison, or a guarantee for every Windows/GPU configuration.
The source in `tests/` documents focused decoder, volume and display checks;
it is not an automatically executed test suite of the public build driver.
