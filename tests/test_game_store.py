from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path
import base64
import io
import json
import struct
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
TOOL_ROOT = ROOT / "submodule/esp-mosaico-utils/mosaico-tools/tools"
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(TOOL_ROOT))

from game_store import ManagedGatewayRpc, install_bundle, main  # noqa: E402
from mosaico_cli.session_runtime import CURRENT_SCOPE  # noqa: E402
from mosaico_cli.errors import DeviceError, OutcomeUnknownError, SelectionError  # noqa: E402


class GameStoreInstallTests(unittest.TestCase):
    def test_streams_bundle_and_verifies_store_listing(self) -> None:
        payload = bytes(range(256)) * 20
        bundle = b"MOSGAME\x03" + struct.pack("<II", 256, 256 + len(payload)) + bytes(240) + payload
        context = Mock()
        context.log_path = Path("run.log")
        session = Mock(started_local=False)
        calls = []

        class FakeRpc:
            def __init__(self):
                self.deadlines = []

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def call(self, method, payload, *, deadline_ms=10000):
                calls.append((method, payload))
                self.deadlines.append(deadline_ms)
                if method == 1:
                    return b"\x01" + len(bundle).to_bytes(4, "little") + b"Sky Hop" + bytes(33)
                if method == 2:
                    return (2044).to_bytes(4, "little")
                if method == 3:
                    return (len(payload) - 4).to_bytes(4, "little")
                if method == 4:
                    return b"\0Sky Hop" + bytes(33)
                if method == 1:
                    return b"\x01" + len(bundle).to_bytes(4, "little") + b"Sky Hop" + bytes(33)
                raise AssertionError(f"unexpected RPC method {method}")

        fake_rpc = FakeRpc()
        with (
            patch("game_store.ensure_gateway", return_value=session),
            patch("game_store.connected_devices", return_value=[{"device_id": "dev-1", "connected": True}]),
            patch("game_store.select_device", return_value={"device_id": "dev-1", "firmware_mode": "normal"}),
            patch("game_store.gateway_json", return_value={"device": {"firmware_mode": "normal"}}),
            patch("game_store.ManagedGatewayRpc", return_value=fake_rpc),
        ):
            result = install_bundle(bundle, context)

        self.assertEqual(result["title"], "Sky Hop")
        self.assertEqual(result["size_bytes"], len(bundle))
        self.assertEqual(result["device_id"], "dev-1")
        self.assertEqual([method for method, _ in calls], [1, 2, 3, 3, 3, 3, 3, 3, 4, 1])
        self.assertLessEqual(max(len(payload) for method, payload in calls if method == 3), 1024)
        self.assertIn(60000, fake_rpc.deadlines)

    def _install_patches(self, fake_rpc):
        stack = ExitStack()
        stack.enter_context(patch("game_store.ensure_gateway", return_value=Mock(started_local=False)))
        stack.enter_context(patch("game_store.connected_devices", return_value=[{"device_id": "dev-1", "connected": True}]))
        stack.enter_context(patch("game_store.select_device", return_value={"device_id": "dev-1", "firmware_mode": "normal", "project_name": "game_launcher"}))
        stack.enter_context(patch("game_store.gateway_json", return_value={"device": {"firmware_mode": "normal", "project_name": "game_launcher"}}))
        stack.enter_context(patch("game_store.ManagedGatewayRpc", return_value=fake_rpc))
        return stack

    @staticmethod
    def _list_page(entries):
        return bytes([len(entries)]) + b"".join(
            size.to_bytes(4, "little") + title.encode().ljust(40, b"\0")
            for title, size in entries
        )

    @staticmethod
    def _bundle(payload=b"ELF"):
        title = b"New Game".ljust(40, b"\0")
        body = bytes(4) + title + bytes(196) + payload
        return b"MOSGAME\x03" + struct.pack("<II", 256, 256 + len(payload)) + body

    def test_chunk_failure_cancels_open_store_session(self) -> None:
        bundle = self._bundle()
        methods = []

        class FakeRpc:
            def __enter__(self): return self
            def __exit__(self, *_args): return None
            def call(self, method, payload, *, deadline_ms=10000):
                methods.append(method)
                if method == 1: return b"\0"
                if method == 2: return (2044).to_bytes(4, "little")
                if method == 3: raise DeviceError("injected chunk failure")
                if method == 6: return b"\0"
                raise AssertionError(method)

        with self._install_patches(FakeRpc()):
            with self.assertRaisesRegex(DeviceError, "injected chunk failure"):
                install_bundle(bundle, Mock())
        self.assertEqual(methods, [1, 2, 3, 6])

    def test_end_timeout_confirms_only_a_new_title_and_size(self) -> None:
        bundle = self._bundle()
        calls = []
        entry = ("New Game", len(bundle))

        class FakeRpc:
            def __init__(self): self.deadlines = []
            def __enter__(self): return self
            def __exit__(self, *_args): return None
            def call(self, method, payload, *, deadline_ms=10000):
                calls.append(method)
                self.deadlines.append((method, deadline_ms))
                if method == 1:
                    return self._list_calls()
                if method == 2: return (2044).to_bytes(4, "little")
                if method == 3: return (len(payload) - 4).to_bytes(4, "little")
                if method == 4: raise DeviceError("HTTP 504: device_timeout")
                raise AssertionError(method)
            def _list_calls(self):
                return GameStoreInstallTests._list_page([] if calls.count(1) == 1 else [entry])

        fake_rpc = FakeRpc()
        with self._install_patches(fake_rpc), patch("game_store.time.sleep"):
            result = install_bundle(bundle, Mock())
        self.assertEqual(result["verification"], "new_title_and_size_in_list_after_end_timeout")
        self.assertFalse(result["bundle_contents_verified"])
        self.assertNotIn("bundle_sha256_verified", result)
        self.assertEqual(calls, [1, 2, 3, 4, 1])
        self.assertIn((4, 60000), fake_rpc.deadlines)

    def test_end_timeout_with_existing_same_size_title_remains_unknown(self) -> None:
        bundle = self._bundle()
        entry = ("New Game", len(bundle))

        class FakeRpc:
            def __enter__(self): return self
            def __exit__(self, *_args): return None
            def call(self, method, payload, *, deadline_ms=10000):
                if method == 1: return GameStoreInstallTests._list_page([entry])
                if method == 2: return (2044).to_bytes(4, "little")
                if method == 3: return (len(payload) - 4).to_bytes(4, "little")
                if method == 4: raise DeviceError("HTTP 504: device_timeout")
                raise AssertionError(method)

        with self._install_patches(FakeRpc()), patch("game_store.time.sleep"):
            with self.assertRaises(OutcomeUnknownError):
                install_bundle(bundle, Mock())

    def test_rejects_non_mosgame_before_gateway_access(self) -> None:
        with self.assertRaises(SelectionError):
            install_bundle(b"not a game", Mock())

    def test_rejects_bad_encoded_bundle_length_before_gateway_access(self) -> None:
        bundle = b"MOSGAME\x03" + struct.pack("<II", 256, 999) + bytes(240)
        with self.assertRaises(SelectionError):
            install_bundle(bundle, Mock())

    def test_rejects_native_project_even_when_firmware_mode_is_normal(self) -> None:
        bundle = b"MOSGAME\x03" + struct.pack("<II", 256, 256) + bytes(240)
        with (
            patch("game_store.ensure_gateway", return_value=Mock()),
            patch("game_store.connected_devices", return_value=[{"device_id": "dev-1"}]),
            patch("game_store.select_device", return_value={"device_id": "dev-1", "project_name": "sky_hop"}),
            patch("game_store.gateway_json", return_value={"device": {"firmware_mode": "normal"}}),
        ):
            with self.assertRaises(DeviceError):
                install_bundle(bundle, Mock())

    def test_cli_uses_launcher_project_and_managed_gateway_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "esp-mosaico-vibe"
            repository.mkdir()
            launcher = root / "esp-mosaico-game"
            launcher.mkdir()
            (launcher / "CMakeLists.txt").write_text("project(game_launcher)")
            bundle = root / "game.bin"
            bundle.write_bytes(b"bundle")
            scope = Mock()

            def check_scope(_bundle, _context, **_kwargs):
                self.assertIs(CURRENT_SCOPE.get(), scope)
                self.assertEqual(scope.arguments.project, str(launcher))
                self.assertEqual(scope.arguments.public_command, "game install")
                return {"title": "Sky Hop", "size_bytes": 6, "device_id": "dev-1"}

            with (
                patch("game_store.load_workspace", return_value=Mock()),
                patch("game_store.RunContext", return_value=Mock()),
                patch("game_store.SessionScope", return_value=scope),
                patch("game_store.install_bundle", side_effect=check_scope),
            ):
                self.assertEqual(main([str(bundle), "--json"], repository=repository, tool_root=root), 0)
            scope.close.assert_called_once()
            self.assertIsNone(CURRENT_SCOPE.get())

    def test_persistent_worker_uses_gateway_raw_rpc_json_protocol(self) -> None:
        payload = b"\x01\x02\xff"
        class FakeProcess:
            def __init__(self):
                self.stdin = io.StringIO()
                self.stdout = io.StringIO(
                    json.dumps({"ok": True, "response": {"payload_base64": base64.b64encode(b"ok").decode()}}) + "\n"
                    + '{"ok":true}\n'
                )

            def poll(self):
                return None

            def wait(self, timeout=None):
                return 0

        with tempfile.TemporaryDirectory() as temporary:
            context = Mock()
            context.log_path = Path(temporary) / "raw.log"
            session = Mock(python=Path("python"), script=Path("/iris/tools/esp_iris.py"), connection_args=("--profile", "default"))
            process = FakeProcess()
            with patch("game_store.subprocess.Popen", return_value=process) as popen:
                client = ManagedGatewayRpc(context, session, "dev-1")
                self.assertEqual(client.call(3, payload), b"ok")
                sent_data = process.stdin.getvalue()
                client.close()

        command = popen.call_args.args[0]
        self.assertEqual(command[-2:], ["--profile", "default"])
        request = json.loads(sent_data.splitlines()[0])
        self.assertEqual(request["service_id"], 16711)
        self.assertEqual(request["method_id"], 3)
        self.assertEqual(base64.b64decode(request["payload_base64"]), payload)


if __name__ == "__main__":
    unittest.main()
