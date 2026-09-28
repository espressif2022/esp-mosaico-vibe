"""Install MOSGAME v3 bundles into the desktop launcher through ESP-Iris."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import time
from typing import Any

from mosaico_cli.errors import DeviceError, MosaicoError, OutcomeUnknownError, SelectionError
from mosaico_cli.gateway import connected_devices, ensure_gateway, gateway_json, select_device
from mosaico_cli.runtime import RunContext
from mosaico_cli.session_runtime import CURRENT_SCOPE, SessionScope
from mosaico_cli.workspace import load_workspace


SERVICE_ID = "16711"
METHOD_LIST, METHOD_BEGIN, METHOD_CHUNK, METHOD_END, _, METHOD_CANCEL = range(1, 7)
ENTRY_BYTES = 44
PAGE_SIZE = 8
TITLE_BYTES = 40
# Keep in sync with GAME_STORE_DATA_BLOCK_COUNT * DATA_BLOCK_SIZE in game_store.h.
MAX_BUNDLE_SIZE = 135 * 0x10000
MAX_RPC_REQUEST_BYTES = 1024
MAX_RPC_CHUNK_BYTES = MAX_RPC_REQUEST_BYTES - 4
MOSGAME_HEADER_SIZE = 256
END_TIMEOUT_LIST_WINDOW_SECONDS = 30
END_TIMEOUT_LIST_INTERVAL_SECONDS = 2


def _response_bytes(value: Any) -> bytes:
    encoded = value.get("payload_base64") if isinstance(value, dict) else None
    if not isinstance(encoded, str):
        raise DeviceError("ESP-Iris returned an invalid game-store response.")
    try:
        return base64.b64decode(encoded, validate=True)
    except ValueError as error:
        raise DeviceError("ESP-Iris returned malformed game-store response data.") from error


def _valid_title(raw: bytes) -> str:
    try:
        return raw.split(b"\0", 1)[0].decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise DeviceError("The launcher returned a game title that is not valid UTF-8.") from error


class ManagedGatewayRpc:
    """Keep the managed Gateway HTTP session alive across chunk RPC calls."""

    def __init__(self, context: RunContext, session: Any, device_id: str) -> None:
        worker = Path(__file__).with_name("game_store_rpc_worker.py")
        command = [
            str(session.python), str(worker),
            "--iris-tools", str(session.script.parent),
            "--device-id", device_id,
            *session.connection_args,
        ]
        context.note("$ " + " ".join(command))
        self.context = context
        self.stderr = context.log_path.open("a", encoding="utf-8")
        try:
            self.process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=self.stderr,
                text=True,
                bufsize=1,
            )
        except OSError:
            self.stderr.close()
            raise
        assert self.process.stdin is not None and self.process.stdout is not None
        self.stdin = self.process.stdin
        self.stdout = self.process.stdout

    def call(self, method: int, payload: bytes, *, deadline_ms: int = 10000) -> bytes:
        if self.process.poll() is not None:
            raise DeviceError("The persistent ESP-Iris Gateway client exited unexpectedly.")
        request = {
            "service_id": int(SERVICE_ID),
            "method_id": method,
            "deadline_ms": deadline_ms,
            "payload_base64": base64.b64encode(payload).decode("ascii"),
        }
        try:
            self.stdin.write(json.dumps(request, separators=(",", ":")) + "\n")
            self.stdin.flush()
            line = self.stdout.readline()
        except OSError as error:
            raise DeviceError("The persistent ESP-Iris Gateway client failed.") from error
        if not line:
            raise DeviceError("The persistent ESP-Iris Gateway client closed without a response.")
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise DeviceError("The persistent ESP-Iris Gateway client returned invalid JSON.") from error
        if not value.get("ok"):
            message = str(value.get("message") or "ESP-Iris RPC failed.")
            self.context.note("Gateway RPC error: " + message)
            raise DeviceError(message)
        return _response_bytes(value.get("response"))

    def close(self) -> None:
        try:
            if self.process.poll() is None:
                self.stdin.write('{"close":true}\n')
                self.stdin.flush()
                self.stdout.readline()
                self.stdin.close()
                self.process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            self.process.kill()
            self.process.wait()
        finally:
            self.stdin.close()
            self.stdout.close()
            self.stderr.close()

    def __enter__(self) -> "ManagedGatewayRpc":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()


def _list_entries(rpc: ManagedGatewayRpc) -> list[tuple[str, int]]:
    entries: list[tuple[str, int]] = []
    start = 0
    while True:
        response = rpc.call(METHOD_LIST, start.to_bytes(2, "little"))
        if not response:
            raise DeviceError("The launcher returned an empty game-store page.")
        count = response[0]
        if len(response) != 1 + count * ENTRY_BYTES:
            raise DeviceError("The launcher returned a malformed game-store page.")
        for index in range(count):
            entry = response[1 + index * ENTRY_BYTES : 1 + (index + 1) * ENTRY_BYTES]
            size = int.from_bytes(entry[:4], "little")
            title = _valid_title(entry[4:])
            entries.append((title, size))
        start += count
        if count < PAGE_SIZE:
            return entries


def _is_rpc_timeout(error: DeviceError) -> bool:
    message = str(error).lower()
    return any(token in message for token in ("http 504", "device_timeout", "timed out", "timeouterror"))


def install_bundle(
    bundle: bytes,
    context: RunContext,
    *,
    device_id: str | None = None,
    gateway_profile: str | None = None,
) -> dict[str, Any]:
    if len(bundle) < MOSGAME_HEADER_SIZE or not bundle.startswith(b"MOSGAME\x03"):
        raise SelectionError("The selected file is not a MOSGAME v3 bundle.")
    header_size, encoded_size = struct.unpack_from("<II", bundle, 8)
    if header_size != MOSGAME_HEADER_SIZE or encoded_size != len(bundle):
        raise SelectionError("The MOSGAME v3 header size or encoded bundle length is invalid.")
    if not 0 < len(bundle) <= MAX_BUNDLE_SIZE:
        raise SelectionError(f"Bundle size must be between 1 and {MAX_BUNDLE_SIZE} bytes.")

    session = ensure_gateway(context, gateway_profile)
    selected = select_device(connected_devices(context, session), device_id)
    selected_id = str(selected.get("device_id"))
    status = gateway_json(context, session, "status", selected_id)
    status_device = status.get("device", status) if isinstance(status, dict) else {}
    mode = status_device.get("firmware_mode") or selected.get("firmware_mode")
    if mode not in (None, "normal"):
        raise DeviceError("ELF game installation requires the desktop launcher in normal mode.")
    project_name = status_device.get("project_name") or selected.get("project_name")
    if project_name and project_name != "game_launcher":
        raise DeviceError(
            f"ELF games can only be installed while game_launcher is running; found {project_name}."
        )

    digest = hashlib.sha256(bundle).digest()
    expected_title = _valid_title(bundle[20:60])
    title = ""
    entries: list[tuple[str, int]] = []
    end_timed_out_confirmed = False
    device_verified_sha = False
    with ManagedGatewayRpc(context, session, selected_id) as rpc:
        entries_before = _list_entries(rpc)
        begin_response = rpc.call(
            METHOD_BEGIN, len(bundle).to_bytes(4, "little") + digest,
        )
        if len(begin_response) != 4:
            raise DeviceError("The launcher returned an invalid game-store chunk limit.")
        server_chunk_limit = int.from_bytes(begin_response, "little")
        if server_chunk_limit <= 0:
            raise DeviceError("The launcher reported an unusable game-store chunk limit.")
        chunk_limit = min(server_chunk_limit, MAX_RPC_CHUNK_BYTES)

        end_attempted = False
        try:
            for offset in range(0, len(bundle), chunk_limit):
                chunk = bundle[offset : offset + chunk_limit]
                response = rpc.call(
                    METHOD_CHUNK, offset.to_bytes(4, "little") + chunk,
                )
                if response != len(chunk).to_bytes(4, "little"):
                    raise DeviceError(f"The launcher rejected game bundle bytes at offset {offset}.")
                if offset == 0 or offset + len(chunk) == len(bundle) or (offset // chunk_limit) % 32 == 0:
                    context.status(f"game install: sent {min(offset + len(chunk), len(bundle))}/{len(bundle)} bytes")

            end_attempted = True
            try:
                end_response = rpc.call(METHOD_END, b"", deadline_ms=60000)
            except DeviceError as error:
                if not _is_rpc_timeout(error):
                    raise
                # END can finish the flash/catalog commit after Gateway's RPC
                # deadline. Poll with read-only LIST for a bounded window;
                # never replay END.
                expected_entry = (expected_title, len(bundle))
                entries_after_timeout: list[tuple[str, int]] = []
                last_list_error: DeviceError | None = None
                until = time.monotonic() + END_TIMEOUT_LIST_WINDOW_SECONDS
                while time.monotonic() < until:
                    try:
                        entries_after_timeout = _list_entries(rpc)
                        last_list_error = None
                    except DeviceError as list_error:
                        last_list_error = list_error
                    if expected_entry in entries_after_timeout:
                        break
                    time.sleep(END_TIMEOUT_LIST_INTERVAL_SECONDS)
                if expected_entry in entries_after_timeout and expected_entry not in entries_before:
                    title = expected_title
                    entries = entries_after_timeout
                    end_timed_out_confirmed = True
                    context.status(
                        "game install: END timed out, but the new title and size are present in a read-only store listing; bundle contents were not independently verified"
                    )
                else:
                    reason = (
                        "follow-up LIST requests also timed out"
                        if last_list_error is not None and not entries_after_timeout
                        else "LIST does not prove whether this bundle was committed"
                    )
                    raise OutcomeUnknownError(
                        f"Game-store END timed out; {reason}. Do not retry automatically."
                    ) from error
            if title:
                # The LIST probe above confirms a newly appearing title and
                # size, but it cannot attest the contents or uploaded hash.
                pass
            elif len(end_response) != 1 + TITLE_BYTES or end_response[0] != 0:
                raise DeviceError("The launcher failed to commit the game-store bundle.")
            else:
                title = _valid_title(end_response[1:])
                device_verified_sha = True
                entries = _list_entries(rpc)
                if (title, len(bundle)) not in entries:
                    raise DeviceError("The launcher accepted the bundle but it is absent from the game-store listing.")
        except BaseException:
            if not end_attempted:
                try:
                    rpc.call(METHOD_CANCEL, b"")
                except Exception:
                    pass
            raise

    result: dict[str, Any] = {
        "status": "succeeded",
        "device_id": selected_id,
        "title": title,
        "size_bytes": len(bundle),
        "store_entries": len(entries),
        "gateway_started": session.started_local,
        "log": str(context.log_path),
    }
    if device_verified_sha:
        result["bundle_sha256_verified"] = digest.hex()
    if end_timed_out_confirmed:
        result["verification"] = "new_title_and_size_in_list_after_end_timeout"
        result["bundle_contents_verified"] = False
    return result


def main(argv: list[str], *, repository: Path, tool_root: Path) -> int:
    parser = argparse.ArgumentParser(prog="mosaico.py game install")
    parser.add_argument("bundle", type=Path, help="MOSGAME v3 game.bin bundle")
    parser.add_argument("--device-id", help="Live ESP-Mosaico Device ID")
    parser.add_argument("--project", help="Launcher ESP-IDF project for the managed Gateway")
    parser.add_argument("--gateway-profile", help="ESP-Iris Gateway profile")
    parser.add_argument("--workspace", help="Workspace directory or .mosaico.json path")
    parser.add_argument("--json", action="store_true", help="Print JSON result")
    args = parser.parse_args(argv)
    try:
        workspace = load_workspace(tool_root.resolve(), start=repository, explicit=args.workspace)
        bundle_path = args.bundle.expanduser()
        if not bundle_path.is_absolute():
            bundle_path = (Path.cwd() / bundle_path).resolve()
        bundle = bundle_path.read_bytes()
        context = RunContext(workspace, "game-install", json_output=args.json)
        if args.project is None:
            sibling_launcher = repository.parent / "esp-mosaico-game"
            if (sibling_launcher / "CMakeLists.txt").is_file():
                args.project = str(sibling_launcher)
        args.command = "install"
        args.public_command = "game install"
        scope = SessionScope()
        scope.arguments = args
        token = CURRENT_SCOPE.set(scope)
        try:
            result = install_bundle(
                bundle, context, device_id=args.device_id, gateway_profile=args.gateway_profile,
            )
        finally:
            try:
                scope.close()
            finally:
                CURRENT_SCOPE.reset(token)
    except (MosaicoError, OSError) as error:
        details = error.details if isinstance(error, MosaicoError) else {}
        message = str(error)
        if args.json:
            print(json.dumps({"ok": False, "message": message, **details}, sort_keys=True), file=sys.stderr)
        else:
            print(f"mosaico: {message}", file=sys.stderr)
        return error.exit_code if isinstance(error, MosaicoError) else 5
    if args.json:
        print(json.dumps({"ok": True, **result}, sort_keys=True))
    else:
        print(f"game install: {result['title']} ({result['size_bytes']} bytes)")
        print(f"Device: {result['device_id']}")
    return 0
