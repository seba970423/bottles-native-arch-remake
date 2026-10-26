#!/usr/bin/env python3
"""Dependency-free display and Gamescope regression tests against patched sources."""

import ast
import contextlib
import dataclasses
import importlib.util
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

SOURCE_ROOT = Path(sys.argv.pop(1) if len(sys.argv) > 1 else ".").resolve()


def load_module(name, relative_path):
    spec = importlib.util.spec_from_file_location(name, SOURCE_ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


display = load_module("native_display_test", "bottles/backend/umu/display_backend.py")
models = load_module("native_models_test", "bottles/backend/umu/models.py")
gamescope = load_module("native_gamescope_test", "bottles/backend/umu/gamescope.py")


def make_executor(root, environment):
    # Execute the actual executor classes while stubbing only unavailable
    # GI/application imports. No production launch logic is reimplemented.
    tree = ast.parse((SOURCE_ROOT / "bottles/backend/umu/executor.py").read_text())
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    assignments = [node for node in tree.body if isinstance(node, ast.Assign)]
    future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
    module = ast.fix_missing_locations(ast.Module(body=[future, *assignments, *classes], type_ignores=[]))
    installation_type = dataclasses.make_dataclass("Installation", [("path", Path)])
    namespace = {
        "os": os, "re": __import__("re"), "sys": sys, "threading": threading,
        "Path": Path, "dataclass": dataclasses.dataclass, "shutil": shutil, "shlex": shlex,
        "subprocess": subprocess, "PROFILE_ENV": "BOTTLES_PROFILE",
        "TRACE_ENV": "BOTTLES_TRACE", "UmuInstallation": installation_type,
        "UmuProtonCatalog": SimpleNamespace(validate_value=lambda value: value),
        "is_v2_runner": lambda _runner: False,
        "configure_display_environment": display.configure_display_environment,
        "resolve_gamescope": gamescope.resolve_gamescope,
        "wrap_gamescope": gamescope.wrap_gamescope,
    }
    dxvk_tree = ast.parse((SOURCE_ROOT / "bottles/backend/umu/dxvk_override.py").read_text())
    dxvk_tree.body = [node for node in dxvk_tree.body if not (
        isinstance(node, ast.ImportFrom) and (node.module or "").startswith("bottles.")
    )]
    dxvk_namespace = {"UmuGame": models.UmuGame, "Paths": SimpleNamespace(dxvk=root / "dxvk")}
    exec(compile(dxvk_tree, "dxvk_override.py", "exec"), dxvk_namespace)
    for key in ("configure_dxvk_environment", "UmuDxvkOverrideError"):
        namespace[key] = dxvk_namespace[key]
    exec(compile(module, "executor.py", "exec"), namespace)
    return namespace["UmuExecutor"](
        installation_type(path=root / "umu-run"), data_root=root / "data",
        base_environment=environment,
    )


class DisplayBackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runner = self.root / "runner with spaces"
        self.runner.mkdir()
        (self.runner / "proton").write_text(
            'self.check_environment("PROTON_ENABLE_WAYLAND", "wayland")\n'
        )
        self.driver = self.runner / "files/lib64/wine/x86_64-unix/winewayland.so"
        self.driver.parent.mkdir(parents=True)
        self.driver.touch()
        self.pe_driver = self.runner / "files/lib64/wine/x86_64-windows/winewayland.drv"
        self.pe_driver.parent.mkdir(parents=True)
        self.pe_driver.touch()
        self.socket_path = self.root / "wayland-0"
        # Unit-test the socket metadata without opening a compositor connection
        # or requiring socket creation in restricted build/test containers.
        self.socket_path.touch()
        original_stat = Path.stat

        def fixture_stat(path, *args, **kwargs):
            if path == self.socket_path:
                return SimpleNamespace(st_mode=stat.S_IFSOCK | 0o600)
            return original_stat(path, *args, **kwargs)

        fixture = patch.object(display.Path, "stat", fixture_stat)
        fixture.start()
        self.addCleanup(fixture.stop)
        self.environment = {
            "PROTONPATH": str(self.runner), "DISPLAY": ":0",
            "WAYLAND_DISPLAY": "wayland-0", "XDG_RUNTIME_DIR": str(self.root),
            "PROTON_NO_NTSYNC": "1", "PROTON_USE_WINED3D": "1",
            "SDL_VIDEODRIVER": "wayland", "QT_QPA_PLATFORM": "wayland",
            "GDK_BACKEND": "wayland", "MANGOHUD": "1", "CUSTOM": "keep",
        }

    def configure(self, mode, environment=None):
        environment = self.environment.copy() if environment is None else environment
        return display.configure_display_environment(mode, environment), environment

    def test_default_and_unknown_modes_are_exact_noops(self):
        for mode in ("proton", "invalid", None, [], {}):
            with self.subTest(mode=mode):
                environment = {**self.environment, "PROTON_USE_WAYLAND": "0",
                               "WINEDLLOVERRIDES": "winex11.drv=;dxgi=n,b"}
                original = environment.copy()
                result, updated = self.configure(mode, environment)
                self.assertEqual(result.backend, "proton")
                self.assertEqual(updated, original)

    def test_native_wayland_and_alias_cleanup(self):
        environment = {**self.environment, "PROTON_ENABLE_WAYLAND": "0",
                       "PROTON_USE_WAYLAND": "0", "WINE_GRAPHICS_DRIVER": "x11",
                       "PROTON_USE_X11_EXCLUSIVE": "game.exe"}
        result, environment = self.configure("wayland", environment)
        self.assertFalse(result.fallback)
        self.assertEqual(environment["PROTON_ENABLE_WAYLAND"], "1")
        self.assertEqual(environment["PROTON_USE_WAYLAND"], "1")
        self.assertEqual(environment["WINE_GRAPHICS_DRIVER"], "wayland")
        self.assertEqual(environment["WINE_USE_EGL"], "1")
        self.assertNotIn("PROTON_USE_X11_EXCLUSIVE", environment)
        self.assertNotIn("WINEDLLOVERRIDES", environment)

    def test_x11_forces_driver_without_hiding_session(self):
        result, environment = self.configure("x11")
        self.assertFalse(result.fallback)
        self.assertEqual(environment["PROTON_ENABLE_WAYLAND"], "0")
        self.assertEqual(environment["PROTON_USE_WAYLAND"], "0")
        self.assertEqual(environment["WINE_GRAPHICS_DRIVER"], "x11")
        self.assertEqual(environment["WINEDLLOVERRIDES"], "winewayland.drv=;winex11.drv=b")
        self.assertEqual(environment["DISPLAY"], ":0")
        self.assertEqual(environment["WAYLAND_DISPLAY"], "wayland-0")

    def test_renderer_sync_overlay_and_toolkit_variables_survive(self):
        for mode in ("wayland", "x11"):
            with self.subTest(mode=mode):
                _, environment = self.configure(mode)
                for key in self.environment:
                    self.assertEqual(environment[key], self.environment[key])

    def test_mixed_dll_entries_preserve_other_libraries(self):
        environment = {**self.environment,
                       "WINEDLLOVERRIDES": "dxgi=n,b;WINEX11.DRV,foo=n;winewayland.drv=;bar=b"}
        _, environment = self.configure("wayland", environment)
        self.assertEqual(environment["WINEDLLOVERRIDES"], "dxgi=n,b;foo=n;bar=b")

    def test_compat_flags_remove_only_wayland(self):
        environment = {**self.environment, "PROTON_ADD_CONFIG": "nofsync, wayland ,wined3d",
                       "STEAM_COMPAT_CONFIG": "wayland,foo=bar"}
        _, environment = self.configure("x11", environment)
        self.assertEqual(environment["PROTON_ADD_CONFIG"], "nofsync,wined3d")
        self.assertEqual(environment["STEAM_COMPAT_CONFIG"], "foo=bar")

    def test_missing_wayland_display_falls_back_to_x11(self):
        environment = self.environment.copy()
        environment.pop("WAYLAND_DISPLAY")
        result, environment = self.configure("wayland", environment)
        self.assertEqual(result.backend, "x11")
        self.assertTrue(result.reason)
        self.assertEqual(environment["PROTON_ENABLE_WAYLAND"], "0")

    def test_missing_socket_or_regular_file_is_not_a_session(self):
        for name in ("missing", "regular"):
            (self.root / "regular").touch()
            with self.subTest(name=name):
                result, _ = self.configure("wayland", {**self.environment, "WAYLAND_DISPLAY": name})
                self.assertEqual(result.backend, "x11")

    def test_socket_permissions_are_checked(self):
        with patch.object(display.os, "access", return_value=False):
            result, _ = self.configure("wayland")
        self.assertEqual(result.backend, "x11")

    def test_absolute_wayland_socket_does_not_need_runtime_directory(self):
        environment = {**self.environment, "WAYLAND_DISPLAY": str(self.socket_path)}
        environment.pop("XDG_RUNTIME_DIR")
        result, _ = self.configure("wayland", environment)
        self.assertEqual(result.backend, "wayland")

    def test_missing_or_relative_runtime_falls_back(self):
        for runtime in ("", "relative"):
            result, _ = self.configure("wayland", {**self.environment, "XDG_RUNTIME_DIR": runtime})
            self.assertEqual(result.backend, "x11")

    def test_missing_launcher_or_driver_is_not_supported(self):
        self.driver.unlink()
        result, _ = self.configure("wayland")
        self.assertEqual(result.backend, "x11")

    def test_modern_unix_driver_without_pe_companion_is_not_supported(self):
        self.pe_driver.unlink()
        result, _ = self.configure("wayland")
        self.assertEqual(result.backend, "x11")
        (self.runner / "proton").unlink()
        result, _ = self.configure("wayland")
        self.assertEqual(result.backend, "x11")

    def test_launcher_without_known_controls_is_not_supported(self):
        (self.runner / "proton").write_text("# ordinary Proton launcher\n")
        result, _ = self.configure("wayland")
        self.assertEqual(result.backend, "x11")

    def test_newer_use_alias_is_supported(self):
        (self.runner / "proton").write_text("self.check_environment('PROTON_USE_WAYLAND', 'wayland')")
        result, _ = self.configure("wayland")
        self.assertEqual(result.backend, "wayland")

    def test_automatic_runner_is_not_assumed_supported(self):
        for proton in ("GE-Proton", "UMU-Proton", "ProtoSoda"):
            result, _ = self.configure("wayland", {**self.environment, "PROTONPATH": proton})
            self.assertEqual(result.backend, "x11")

    def test_classic_and_wow64_runner_layouts(self):
        self.driver.unlink()
        for path in ("dist/lib64/wine/winewayland.drv.so",
                     "files/lib/wine/i386-unix/winewayland.drv.so",
                     "files/lib/wine/x86_64-unix/winewayland.drv.so",
                     "files/lib/wine/x86_64-unix/winewayland.so"):
            with self.subTest(path=path):
                driver = self.runner / path
                driver.parent.mkdir(parents=True, exist_ok=True)
                driver.touch()
                result, _ = self.configure("wayland")
                self.assertEqual(result.backend, "wayland")
                driver.unlink()

    def test_no_x11_fallback_uses_default_without_mutating_environment(self):
        environment = {**self.environment, "WAYLAND_DISPLAY": "missing"}
        environment.pop("DISPLAY")
        for mode in ("x11", "wayland"):
            original = environment.copy()
            result, environment = self.configure(mode, environment)
            self.assertEqual(result.backend, "proton")
            self.assertTrue(result.fallback)
            self.assertEqual(environment, original)

    def test_wayland_only_session_is_supported(self):
        environment = self.environment.copy()
        environment.pop("DISPLAY")
        result, _ = self.configure("wayland", environment)
        self.assertEqual(result.backend, "wayland")

    def test_settings_resolver_is_read_only(self):
        original = self.environment.copy()
        display.resolve_display_backend("wayland", self.environment)
        self.assertEqual(self.environment, original)

    def test_per_game_metadata_roundtrip_and_legacy_default(self):
        game = models.UmuGame(id=uuid4(), name="Test", executable=self.root / "game.exe",
                              prefix=models.UmuPrefix(path="prefixes/game"), proton=str(self.runner),
                              extra={"display_backend": "wayland", "sync_backend": "ntsync"})
        restored = models.UmuGame.from_dict(game.to_dict())
        self.assertEqual(restored.extra, game.extra)
        legacy = game.to_dict()
        legacy.pop("display_backend")
        self.assertEqual(models.UmuGame.from_dict(legacy).extra.get("display_backend", "proton"), "proton")

    def executor(self, environment):
        return make_executor(self.root, environment)

    def test_actual_executor_integration_and_prefix_preparation(self):
        for mode in ("proton", "wayland", "x11"):
            with self.subTest(mode=mode):
                game = models.UmuGame(
                    id=uuid4(), name="Test", executable=self.root / "game.exe",
                    prefix=models.UmuPrefix(path="prefixes/game"), proton=str(self.runner),
                    extra={"display_backend": mode, "performance_backend": "none"},
                )
                executor = self.executor(self.environment)
                with contextlib.redirect_stderr(io.StringIO()):
                    command = executor.prepare(game)
                self.assertEqual(command.argv, (str(self.root / "umu-run"), str(game.executable)))
                if mode == "proton":
                    self.assertNotIn("WINE_GRAPHICS_DRIVER", command.env)
                else:
                    self.assertEqual(command.env["WINE_GRAPHICS_DRIVER"], mode)
                self.assertEqual(executor.base_environment, self.environment)
                self.assertEqual(game.environment, {})
                prefix_command = executor.prepare_prefix(game)
                self.assertNotIn("WINE_GRAPHICS_DRIVER", prefix_command.env)

    def test_actual_executor_logs_fallback_without_claiming_active_backend(self):
        environment = {**self.environment, "WAYLAND_DISPLAY": "missing"}
        game = models.UmuGame(
            id=uuid4(), name="Test", executable=self.root / "game.exe",
            prefix=models.UmuPrefix(path="prefixes/game"), proton=str(self.runner),
            extra={"display_backend": "wayland", "performance_backend": "none"},
        )
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            command = self.executor(environment).prepare(game)
        self.assertEqual(command.env["WINE_GRAPHICS_DRIVER"], "x11")
        self.assertIn("Using X11/XWayland", output.getvalue())
        self.assertEqual(game.extra["display_backend"], "wayland")


class GamescopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gamescope tests ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin with spaces"
        self.bin.mkdir()
        for name in ("gamescope", "mangoapp", "mangohud", "gamemoderun"):
            self.script(self.bin / name, "pass\n")
        self.environment = {
            "PATH": str(self.bin), "DISPLAY": ":0", "WAYLAND_DISPLAY": "wayland-0",
            "MANGOHUD": "1", "CUSTOM": "keep", "PROTON_USE_WAYLAND": "1",
            "PROTON_ENABLE_WAYLAND": "1", "PROTON_NO_FSYNC": "1",
            "WINEDLLOVERRIDES": "winewayland.drv=b;dxgi=n,b",
        }
        self.settings = {
            "enabled": True, "game_resolution": "1280x720",
            "output_resolution": "1920x1080", "filter": "fsr", "sharpness": 3,
            "fps_limit": 60, "fullscreen": True,
        }

    @staticmethod
    def script(path, source):
        path.write_text(f"#!{sys.executable}\n" + source)
        path.chmod(0o755)

    def game(self, **extra):
        return models.UmuGame(
            id=uuid4(), name="Test", executable=self.root / "game's folder/game.exe",
            prefix=models.UmuPrefix(path="prefixes/game"), proton="UMU-Proton",
            arguments=("--message", "literal $() `text` ; with spaces"),
            environment={"GAME_VARIABLE": "keep"},
            extra={"gamescope": self.settings, "performance_backend": "gamemode", **extra},
        )

    def prepare(self, game=None, environment=None):
        game = self.game() if game is None else game
        environment = self.environment if environment is None else environment
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            command = make_executor(self.root, environment).prepare(game)
        return command, output.getvalue()

    def test_legacy_and_disabled_settings_do_not_enable_gamescope(self):
        for value in (None, True, [], "on", {}, {"enabled": False},
                      {"enabled": "true"}, {"enabled": 1},
                      {"enabled": False, "game_resolution": "broken"}):
            with self.subTest(value=value):
                result = gamescope.resolve_gamescope(value, self.environment)
                self.assertFalse(result.active)
                self.assertFalse(result.reason)

    def test_resolution_validation_and_normalization(self):
        for text in ("1280x720", " 1280 X 720 ", "1280×720"):
            settings = gamescope.GamescopeSettings.from_dict({"game_resolution": text})
            self.assertEqual(settings.to_dict()["game_resolution"], "1280x720")
        for value in (None, [], "0x720", "1920x0", "16385x720", "1920", "-w 1",
                      "1280x720; touch pwned", "$(echo 1280)x720", "1280x720\n--foo"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                gamescope.parse_resolution(value)

    def test_existing_resolutions_select_presets_or_preserve_custom_sizes(self):
        for value in ("", *gamescope.GAMESCOPE_RESOLUTION_PRESETS, "1500x900", "2400×1350"):
            with self.subTest(value=value):
                preset = gamescope.resolution_preset(value)
                restored = gamescope.resolution_from_preset(preset, value)
                self.assertEqual(restored, value.replace("×", "x"))
                self.assertEqual(preset == "custom", value in ("1500x900", "2400×1350"))
        self.assertEqual(gamescope.resolution_preset(" 1280 X 720 "), "1280x720")

    def test_preset_ignores_hidden_custom_text_but_custom_requires_a_valid_size(self):
        self.assertEqual(gamescope.resolution_from_preset("1280x720", "invalid"), "1280x720")
        self.assertEqual(gamescope.resolution_from_preset("", "invalid"), "")
        for preset, value in (("custom", ""), ("custom", "invalid"), ("--help", ""),
                               (None, ""), ([], "")):
            with self.subTest(preset=preset, value=value), self.assertRaises(ValueError):
                gamescope.resolution_from_preset(preset, value)

    def test_malformed_enabled_settings_fall_back_without_mutation(self):
        for key, value in (("game_resolution", []), ("output_resolution", "bad"),
                           ("filter", []), ("filter", "--help"), ("sharpness", True),
                           ("sharpness", 21), ("sharpness", -1), ("fps_limit", "60"),
                           ("fps_limit", 1001), ("fps_limit", -1), ("fullscreen", "true")):
            settings = {**self.settings, key: value}
            with self.subTest(key=key, value=value):
                original = self.environment.copy()
                result = gamescope.resolve_gamescope(settings, self.environment)
                self.assertFalse(result.active)
                self.assertTrue(result.reason)
                self.assertEqual(original, self.environment)

    def test_command_contains_validated_options_and_single_separator(self):
        command, _ = self.prepare()
        boundary = command.argv.index("--")
        self.assertEqual(command.argv[:boundary], (
            str(self.bin / "gamescope"), "-w", "1280", "-h", "720",
            "-W", "1920", "-H", "1080", "-F", "fsr", "--sharpness", "3",
            "-r", "60", "-f", "--mangoapp",
        ))
        self.assertEqual(command.argv[boundary + 1:], (
            str(self.bin / "gamemoderun"), str(self.root / "umu-run"),
            str(self.game().executable), *self.game().arguments,
        ))
        self.assertNotIn("%command%", command.argv)

    def test_all_scalers_and_optional_options(self):
        for scaler in gamescope.GAMESCOPE_FILTER_IDS:
            value = {"enabled": True, "filter": scaler, "fullscreen": False}
            result = gamescope.resolve_gamescope(value, self.environment)
            with self.subTest(scaler=scaler):
                self.assertTrue(result.active)
                for flag in ("-w", "-h", "-W", "-H", "-r", "-f"):
                    self.assertNotIn(flag, result.arguments)
                self.assertEqual("--sharpness" in result.arguments, scaler in ("fsr", "nis"))
                if scaler == "integer":
                    self.assertEqual(result.arguments[-4:], ("-S", "integer", "-F", "nearest"))
                else:
                    self.assertIn(scaler, result.arguments)

    def test_missing_gamescope_restores_selected_display_and_overlay(self):
        (self.bin / "gamescope").unlink()
        game = self.game(display_backend="x11", dxvk_override="wined3d")
        command, output = self.prepare(game)
        self.assertNotIn("--mangoapp", command.argv)
        self.assertEqual(command.argv[:2], (str(self.bin / "mangohud"), "--dlsym"))
        self.assertEqual(command.env["WINE_GRAPHICS_DRIVER"], "x11")
        self.assertIn("Launching without Gamescope", output)
        self.assertTrue(game.extra["gamescope"]["enabled"])

    def test_no_desktop_falls_back_without_forcing_a_driver(self):
        environment = {k: v for k, v in self.environment.items()
                       if k not in ("DISPLAY", "WAYLAND_DISPLAY")}
        command, output = self.prepare(environment=environment)
        self.assertNotIn(str(self.bin / "gamescope"), command.argv)
        self.assertNotIn("WINE_GRAPHICS_DRIVER", command.env)
        self.assertIn("No desktop display", output)

    def test_wayland_only_host_uses_nested_x11_without_fake_host_display(self):
        environment = self.environment.copy()
        environment.pop("DISPLAY")
        command, _ = self.prepare(self.game(display_backend="wayland"), environment)
        self.assertEqual(command.env["WINE_GRAPHICS_DRIVER"], "x11")
        self.assertEqual(command.env["PROTON_USE_WAYLAND"], "0")
        self.assertEqual(command.env["PROTON_ENABLE_WAYLAND"], "0")
        self.assertEqual(command.env["WINEDLLOVERRIDES"], "dxgi=n,b;winewayland.drv=;winex11.drv=b")
        self.assertNotIn("DISPLAY", command.env)
        self.assertEqual(environment["PROTON_USE_WAYLAND"], "1")

    def test_both_renderers_use_mangoapp_without_direct_overlay_injection(self):
        for renderer in ("proton", "wined3d"):
            with self.subTest(renderer=renderer):
                command, _ = self.prepare(self.game(dxvk_override=renderer))
                self.assertIn("--mangoapp", command.argv)
                self.assertNotIn(str(self.bin / "mangohud"), command.argv)
                self.assertNotIn("MANGOHUD", command.env)
                self.assertEqual(command.env["PROTON_NO_FSYNC"], "1")
                self.assertEqual(command.env["GAME_VARIABLE"], "keep")
                if renderer == "wined3d":
                    self.assertEqual(command.env["PROTON_USE_WINED3D"], "1")

    def test_forced_synchronization_survives_gamescope(self):
        for mode, expected in (("fsync", {"PROTON_NO_NTSYNC": "1"}),
                               ("esync", {"PROTON_NO_NTSYNC": "1", "PROTON_NO_FSYNC": "1"}),
                               ("disabled", {"PROTON_NO_NTSYNC": "1", "PROTON_NO_FSYNC": "1", "PROTON_NO_ESYNC": "1"})):
            with self.subTest(mode=mode):
                command, _ = self.prepare(self.game(sync_backend=mode))
                for key, value in expected.items():
                    self.assertEqual(command.env[key], value)
                self.assertIn(str(self.bin / "gamescope"), command.argv)

    def test_custom_dxvk_preparation_and_restoration_remain_outside_gamescope(self):
        prefix_log = self.root / "prefix.json"
        self.script(self.root / "umu-run", (
            "import json, os, sys\n"
            "with open(os.environ['PREFIX_LOG'], 'w') as f:\n"
            "    json.dump({'arguments': sys.argv[1:], 'driver': os.getenv('WINE_GRAPHICS_DRIVER')}, f)\n"
        ))
        dlls = ("d3d8.dll", "d3d9.dll", "d3d10core.dll", "d3d11.dll", "dxgi.dll")
        for architecture in ("x64", "x32"):
            component = self.root / "dxvk/custom" / architecture
            component.mkdir(parents=True)
            for dll in dlls:
                (component / dll).write_bytes(b"custom DXVK")
        game = self.game(dxvk_override="custom")
        prefix = game.prefix.resolve(self.root / "data")
        original = prefix / "drive_c/windows/system32/d3d11.dll"
        original.parent.mkdir(parents=True)
        original.write_bytes(b"bundled Proton DLL")
        command, _ = self.prepare(game, {**self.environment, "PREFIX_LOG": str(prefix_log)})
        self.assertEqual(original.read_bytes(), b"custom DXVK")
        self.assertEqual(json.loads(prefix_log.read_text()), {"arguments": [""], "driver": None})
        self.assertIn("d3d8,d3d9,d3d10core,d3d11,dxgi=n,b", command.env["WINEDLLOVERRIDES"])
        self.assertEqual(command.argv[0], str(self.bin / "gamescope"))
        self.prepare(dataclasses.replace(game, extra={**game.extra, "dxvk_override": "wined3d"}))
        self.assertEqual(original.read_bytes(), b"bundled Proton DLL")
        self.assertFalse((prefix / "drive_c/windows/system32/dxgi.dll").exists())

    def test_missing_or_disabled_overlay_never_blocks_gamescope(self):
        (self.bin / "mangoapp").unlink()
        command, output = self.prepare()
        self.assertEqual(command.argv[0], str(self.bin / "gamescope"))
        self.assertNotIn("--mangoapp", command.argv)
        self.assertNotIn("MANGOHUD", command.env)
        self.assertIn("mangoapp is missing", output)
        command, output = self.prepare(environment={**self.environment, "MANGOHUD": "0"})
        self.assertNotIn("--mangoapp", command.argv)
        self.assertNotIn("mangoapp is missing", output)

    def test_switching_off_restores_normal_launch_environment(self):
        executor = make_executor(self.root, self.environment)
        with contextlib.redirect_stderr(io.StringIO()):
            inside = executor.prepare(self.game(display_backend="proton"))
            outside = executor.prepare(self.game(gamescope={"enabled": False}))
        self.assertNotIn("MANGOHUD", inside.env)
        self.assertEqual(outside.env["MANGOHUD"], "1")
        self.assertEqual(outside.env["PROTON_USE_WAYLAND"], "1")
        self.assertNotIn("WINE_GRAPHICS_DRIVER", outside.env)
        self.assertNotIn(str(self.bin / "gamescope"), outside.argv)
        self.assertEqual(executor.base_environment, self.environment)

    def test_prefix_setup_and_winetricks_are_never_wrapped(self):
        game = self.game()
        executor = make_executor(self.root, self.environment)
        for command in (executor.prepare_prefix(game), executor.prepare_winetricks(game, ["corefonts"])):
            self.assertEqual(command.argv[0], str(self.root / "umu-run"))
            self.assertNotIn(str(self.bin / "gamescope"), command.argv)
            self.assertNotIn("WINE_GRAPHICS_DRIVER", command.env)
        self.assertEqual(game.extra["gamescope"], self.settings)

    def test_per_game_settings_survive_metadata_roundtrip(self):
        game = self.game()
        restored = models.UmuGame.from_dict(json.loads(json.dumps(game.to_dict())))
        self.assertEqual(restored.extra["gamescope"], self.settings)

    def test_prepared_command_executes_with_literal_arguments_and_child_display(self):
        scope_log, game_log = self.root / "scope.json", self.root / "game.json"
        self.script(self.bin / "gamescope", (
            "import json, os, sys\n"
            "split = sys.argv.index('--')\n"
            "with open(os.environ['SCOPE_LOG'], 'w') as f:\n"
            "    json.dump({'options': sys.argv[1:split], 'overlay': os.getenv('MANGOHUD')}, f)\n"
            "os.environ['DISPLAY'] = ':77'\n"
            "os.execvpe(sys.argv[split+1], sys.argv[split+1:], os.environ)\n"
        ))
        self.script(self.bin / "gamemoderun", "import os, sys\nos.execvpe(sys.argv[1], sys.argv[1:], os.environ)\n")
        self.script(self.root / "umu-run", (
            "import json, os, sys\n"
            "with open(os.environ['GAME_LOG'], 'w') as f:\n"
            "    json.dump({'argv': sys.argv[1:], 'display': os.getenv('DISPLAY'), "
            "'driver': os.getenv('WINE_GRAPHICS_DRIVER'), 'custom': os.getenv('GAME_VARIABLE')}, f)\n"
        ))
        game = self.game()
        command, _ = self.prepare(game, {**self.environment, "SCOPE_LOG": str(scope_log), "GAME_LOG": str(game_log)})
        subprocess.run(command.argv, env=command.env, check=True, timeout=10)
        observed = json.loads(game_log.read_text())
        self.assertEqual(observed["argv"], [str(game.executable), *game.arguments])
        self.assertEqual(observed["display"], ":77")
        self.assertEqual(observed["driver"], "x11")
        self.assertEqual(observed["custom"], "keep")
        self.assertIsNone(json.loads(scope_log.read_text())["overlay"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
