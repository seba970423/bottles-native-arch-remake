# Bottles Native Arch

A thin native Arch/CachyOS packaging layer for the latest upstream Bottles.
It keeps pacman in charge of every installed file, keeps Feral GameMode optional,
enables Bottles outside Flatpak/cpak, and refuses known partial-UI
initialization regressions.

## Install or reinstall the latest release

```bash
git clone https://github.com/seba970423/bottles-native-arch-remake.git
cd bottles-native-arch-remake
./install.sh
```

`install.sh` checks GitHub for the latest stable Bottles release, updates the
PKGBUILD and source checksum when necessary, validates the packaging, and checks
every build/runtime dependency. Missing repository and AUR dependencies are
shown separately with an installation prompt. Repository packages use pacman;
AUR packages use `paru` or `yay`. The Bottles build starts only after a second
dependency check succeeds. Use `./install.sh --no-update` to build the currently
pinned release.

Do not run the script with `sudo`; `makepkg` asks for elevated privileges only
when pacman installs dependencies and the finished package.

## Update without installing

```bash
./update.sh
./test.sh
```

An upstream update is intentionally allowed to fail if `native-arch.patch` no
longer applies. That is a safety feature: inspect the upstream changes and
refresh the patch rather than silently building a broken package.

The package check validates the generated desktop entry and GSettings schema.
It intentionally skips upstream's AppStream style test: Bottles' remote
screenshots and release-description formatting fail current `appstream-util`
style rules even though they do not affect building or running Bottles.

## Last-known-good rollback

The installer builds an upstream update completely before pacman touches the
installed version. Patch, verification, dependency, or build failures leave the
working installation intact and restore the previous `PKGBUILD` automatically.

After installing a candidate, the script offers to launch Bottles and asks for
explicit confirmation. An approved package is copied to:

```text
~/.local/state/bottles-native-arch/known-good
```

The prior approved package is retained as `previous`. Rejecting a future
candidate automatically reinstalls `known-good`. For a regression discovered
later, run:

```bash
./rollback.sh
```

That verifies the preserved package checksum and installs the `previous`
generation. `./rollback.sh --known-good` reinstalls the current checkpoint.

## Optional performance backends

Bottles 64.1 returned from `PreferencesView.__init__()` when GameMode was not
available, before its combo-box signals were connected. Opening a bottle later
called `handler_block_by_func()` for a handler that never existed and raised
`TypeError: nothing connected`.

Current upstream Bottles has fixed that exact GameMode early return. This package
therefore keeps GameMode optional, and `verify-source.sh` guards against the
initialization bug returning. The installer recommends Feral GameMode and also
offers System76 Scheduler while clearly identifying it as an experimental,
persistent system-wide service. On CachyOS, its PipeWire helper has been
observed repeatedly crashing even while the main daemon remains active; Feral
GameMode is therefore the recommended backend.

UMU games can select **Feral GameMode**, **System76 Scheduler**, **Both**, or
**None**. GameMode wraps only that UMU launch. System76 Scheduler receives the
launched process ID through its documented system D-Bus interface. Missing or
inactive backends never prevent the game from launching normally.

Selecting a missing backend in Game Settings opens an explicit confirmation
dialog. After consent, Bottles uses Polkit to run a non-interactive pacman
transaction for only the packages named in the dialog, then verifies their
executables exist before reporting success.

When System76 Scheduler contains an active `pipewire` monitor assignment,
Bottles and the terminal installer explain the known Arch/CachyOS crash risk
and offer to disable only that optional monitor. The change is explicit and
reversible: the original config is preserved as
`/etc/system76-scheduler/config.kdl.bottles-native-arch.backup`. Core scheduler,
process monitoring, D-Bus foreground selection, and static sound-server
assignments remain enabled.

## Native patch scope

UMU-managed games include a per-game MangoHud switch under **Game Settings → Launch**. The switch stores `MANGOHUD=1` in the game environment, so UMU keeps control of the Proton command line. Do not put `gamescope`, `mangohud`, `gamemoderun`, or `%command%` in the Arguments field; that field is passed directly to the Windows executable.

Managed UMU games also provide a separate per-game DXVK selector. The default
continues using the DLLs bundled with the selected Proton runner; WineD3D can
disable DXVK, or an installed Bottles DXVK component can override only D3D8–11.
The runner itself and VKD3D remain untouched. Before replacing any prefix DLL,
Bottles records whether the original was a file, symlink, or absent. Switching
back restores that exact state, and a partial installation triggers immediate
rollback. Custom external prefixes intentionally do not allow DLL replacement.
When WineD3D and MangoHud are both enabled, Bottles automatically uses MangoHud's
OpenGL preload wrapper; DXVK continues using the normal Vulkan-layer environment.

The patch removes only upstream's sandbox-only build/startup gates:

- the `/.flatpak-info` Meson requirement;
- the unsupported-native-environment shutdown dialog;
- early returns that leave native views only partly initialized;
- the native executable-picker block.

The UMU installer introduction also displays its managed prefix location. On
the first installation it asks whether to keep the current folder or choose a
folder on another drive. A live change is accepted only while the UMU
repository contains no games and has no active processes; the chosen path is
then stored through Bottles' existing `umu-data-path` setting.

Bottle data can remain in the default location or be placed on secondary
storage. This package does not replace those paths with symlinks or bypass
pacman's ownership database.

### Per-game DXVK and WineD3D selection

Managed UMU games expose a separate graphics-translation selector under
**Game Settings → Launch**. This setting is independent of the selected Proton
runner.

Available modes:

- **Bundled with selected Proton** — uses the DXVK version supplied by Proton
  and remains the recommended default.
- **Installed DXVK version** — replaces only the managed prefix's D3D8–11 DLLs
  while keeping the selected Proton runner and VKD3D.
- **WineD3D** — disables DXVK for D3D8–11 and uses Wine's OpenGL translation
  layer instead. VKD3D remains available for Direct3D 12.

WineD3D may provide better compatibility, input latency, or frame pacing in
some games, but it may perform worse in others. Results depend on the game,
graphics driver, and hardware.

Before applying a custom DXVK version, Bottles records the original DLL state,
including regular files, symbolic links, and missing files. Switching back to
the bundled Proton option restores that state. A failed or incomplete
replacement triggers automatic rollback.

When MangoHud is enabled with WineD3D, Bottles automatically uses MangoHud's
OpenGL preload wrapper. This allows the overlay to appear in the game without
necessarily appearing in launchers or other blacklisted helper processes.

### Per-game synchronization override

UMU games also expose a synchronization selector under **Game Settings →
Launch**. **Proton Default** is recommended and leaves the runner's environment
untouched; recent runners such as DWProton may already select NTSYNC
automatically when the host supports it.

The override modes are intended for compatibility testing:

- **Prefer NTSYNC** — explicitly requests NTSYNC when `/dev/ntsync` exists and
  is accessible, otherwise falls back safely to Fsync.
- **Force Fsync** — disables NTSYNC while retaining Proton's Fsync path.
- **Force Esync** — disables NTSYNC and Fsync.
- **Disable Sync Optimizations** — disables NTSYNC, Fsync, and Esync for
  troubleshooting.

Forced modes remove conflicting Proton synchronization variables before
applying their own settings. Existing games remain on **Proton Default**, and
unsupported NTSYNC never prevents a game from launching. To verify actual
NTSYNC use while a game is running, use `lsof /dev/ntsync`; overlay indicators
alone may be inaccurate.

### Per-game display backend (Wayland / X11)

UMU games expose **Display Backend** under **Game Settings → Launch**. This
selects Wine's display driver; it does not log you out, change your desktop
session, replace GPU drivers, or change the DXVK/WineD3D renderer.

- **Proton Default (Recommended)** — leaves every manual display variable
  unchanged and lets the selected Proton runner decide. Existing games use
  this mode automatically.
- **Native Wayland (Experimental)** — requires an accessible Wayland socket,
  an installed runner with a verified Wayland launcher control, and the actual
  Wine-Wayland driver (`winewayland.so` with its `winewayland.drv` companion,
  or the legacy `winewayland.drv.so` layout). Requests both `PROTON_ENABLE_WAYLAND=1` and
  `PROTON_USE_WAYLAND=1`, plus EGL for native Wayland OpenGL. Supported runner
  versions may retain their own per-executable X11 launcher exceptions.
- **X11 / XWayland** — requests Wine's X11 driver. On a Wayland desktop this
  uses XWayland; on an X11 desktop it uses X11. Both Wayland aliases are set to
  `0`, and launch-local display DLL overrides prevent the Wayland driver from
  winning through a prefix's driver order.

Forced modes remove only conflicting display-driver DLL overrides, the
`wayland` token in Proton compatibility flags, and the per-executable X11
exception override. Other DLL overrides, renderer choices, synchronization,
MangoHud and toolkit variables remain intact. `DISPLAY` and `WAYLAND_DISPLAY`
are not hidden from launchers. Returning to Default restores normal behavior
because overrides are built in a fresh launch environment, not written into
the game environment or prefix registry.

Unavailable native Wayland requests fall back to X11/XWayland when `DISPLAY`
exists, or to Proton Default when there is no X11 display. Settings show the
preflight reason and notify on an unsupported selection; the launch log records
the launch-time fallback. The saved preference remains unchanged. Preflight
checks do not prove runtime driver use or game compatibility, and a `DISPLAY`
value does not guarantee the X server is reachable. The tool never retries a
game automatically after a crash or claims that fallback will repair it.

For automatic `UMU-Proton`/`GE-Proton` selections, Bottles cannot inspect the
runner before UMU resolves it. Native Wayland therefore falls back rather than
guessing. Select a specific installed, Wayland-capable runner such as DWProton
to use native Wayland. Detection is based on files and controls, not branding.

Close **all game and launcher processes using the prefix** before switching.
Native Wayland is experimental; input, controllers, multi-monitor behavior,
launchers and OpenGL/WineD3D compatibility depend on the runner and game.
No universal performance improvement is promised.

To verify the actual game window in KDE, open KWin's Debug Console
(`qdbus6 org.kde.KWin /KWin org.kde.KWin.showDebugConsole`) and inspect the
game under its Wayland or X11 windows, not merely its launcher. On Hyprland,
`hyprctl clients` reports whether a window uses XWayland. A Proton variable or
loaded driver file alone is not conclusive, especially with mixed-backend
launcher exceptions.

The dependency-free regression suite runs from `verify-source.sh` during
`makepkg` preparation. For a manually patched upstream checkout:

```bash
./test.sh /path/to/patched/Bottles-67.4
```

### Per-game Gamescope

UMU games expose a **Gamescope** switch under **Game Settings → Launch**.
It starts disabled for existing games. Enabling it reveals controls for:

- **Game Resolution** and **Output Resolution**, such as `1280x720` → `1920x1080`.
- **Linear**, **AMD FSR 1**, **NIS**, **Integer**, or **Nearest Neighbour** scaling.
- **Sharpness** for FSR 1/NIS: `0` is sharpest, `20` is softest.
- **FPS Limit** (`0` leaves it unlimited) and **Fullscreen**.

Blank game resolution follows the output resolution. Blank output resolution
uses Gamescope's own default; it does not detect your monitor's native resolution.
For upscaling, set both resolutions explicitly and select the lower resolution
inside the game if it ignores the advertised display mode. The FPS control uses
Gamescope's nested refresh setting (`-r`); games that bypass synchronization may
also need VSync or their own FPS limiter.

Gamescope provides a private XWayland display. While it is active, Bottles
requests Wine's X11 driver inside that display and suspends the saved **Display
Backend** override for this launch. The saved selection returns when Gamescope
is disabled or unavailable. Close all game and launcher processes using the
prefix before changing this setting.

MangoHud uses Gamescope's **mangoapp** overlay for both DXVK and WineD3D; it is
not injected into Gamescope or wrapped around UMU on this path. On Arch,
`mangoapp` is included in the `mangohud` package. Feral GameMode wraps UMU inside
Gamescope. Synchronization and DXVK settings still apply to the game. Prefix
creation and Winetricks never run inside Gamescope.

The installer offers Gamescope as an optional dependency. Enabling Gamescope in
Game Settings also offers to install missing `gamescope`/`mangohud` packages with
explicit confirmation through Polkit and pacman. Declining keeps the preference
saved. If Gamescope is missing, no desktop display is available, or saved options
are invalid, the launch log explains the normal-launch fallback. Missing
`mangoapp` disables only the overlay for that launch. These checks do not prove
Vulkan, compositor, or game compatibility; a Gamescope startup failure is logged
without automatically relaunching the game.

All options are validated and passed as separate command arguments. They never
become Windows executable arguments or prefix registry changes. Lower rendering
resolutions may help GPU-bound games; enabling Gamescope at the same resolution
does not guarantee higher FPS or lower latency. Real GPU/game benchmarking is
still required, including NIKKE cursor response with WineD3D.

The dependency-free regression suite covers Gamescope options, malformed
metadata, legacy/off behaviour, missing dependencies, Wayland-only hosts,
overlay and GameMode composition, prefix operations, metadata persistence, and
an executable command-chain fixture. Run `./test.sh /path/to/patched/Bottles-67.4`.

#### Tested WineD3D example

Goddess of Victory: NIKKE was tested with DWProton and WineD3D on an AMD
RX 6600 and Intel UHD 620. On both systems, WineD3D eliminated observable
cursor lag and produced smooth 60 FPS frame delivery. Results with other games
and hardware may differ.

## Remove

Run the interactive uninstaller without `sudo`:

```bash
./uninstall.sh
```

It removes only the application package by default. Bottle data, UMU prefixes,
game files, settings, and rollback checkpoints are preserved. GameMode and
System76 Scheduler require separate confirmation because other applications may
use them; the persistent System76 service can be stopped without uninstalling
its package.

## Support boundary

This package is an unofficial native build. Bottles upstream officially targets
its sandboxed distributions, so native-only problems belong in this packaging
project rather than upstream unless reproduced in an official build.
