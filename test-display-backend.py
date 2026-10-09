#!/usr/bin/env python3
"""Dependency-free display-backend regression tests against patched sources."""

import ast
import contextlib
import dataclasses
import importlib.util
import io
import os
from pathlib import Path
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
            "Path": Path, "dataclass": dataclasses.dataclass, "shutil": shutil,
            "subprocess": subprocess, "PROFILE_ENV": "BOTTLES_PROFILE",
            "TRACE_ENV": "BOTTLES_TRACE", "UmuInstallation": installation_type,
            "UmuProtonCatalog": SimpleNamespace(validate_value=lambda value: value),
            "is_v2_runner": lambda _runner: False,
            "configure_dxvk_environment": lambda *_args: None,
            "configure_display_environment": display.configure_display_environment,
            "UmuDxvkOverrideError": type("DxvkError", (Exception,), {}),
        }
        exec(compile(module, "executor.py", "exec"), namespace)
        executor = namespace["UmuExecutor"](
            installation_type(path=self.root / "umu-run"), data_root=self.root / "data",
            base_environment=environment,
        )
        return executor

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
