"""Create and build MicroPixel Guest games with the pinned upstream SDK."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
from typing import Any

from .errors import BuildError, OperationError, SelectionError
from .runtime import RunContext


LOCK_RELATIVE_PATH = Path("projects/micropixel-host/runtime.lock.json")
MICROPIXEL_RELATIVE_PATH = Path("submodule/micropixel")
GAMES_RELATIVE_PATH = Path("games")


def _load_runtime_lock(repository: Path) -> dict[str, Any]:
    path = repository / LOCK_RELATIVE_PATH
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise BuildError(
            "The MicroPixel runtime lock is missing or invalid.",
            details={"path": str(path), "reason": str(error)},
        ) from error
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise BuildError(
            "The MicroPixel runtime lock has an unsupported schema.",
            details={"path": str(path)},
        )
    revision = value.get("revision")
    if not isinstance(revision, str) or re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise BuildError(
            "The MicroPixel runtime lock does not contain a full Git revision.",
            details={"path": str(path)},
        )
    if value.get("target") != "esp32s31" or value.get("aot_arch") != "riscv32-ilp32f":
        raise BuildError(
            "The MicroPixel runtime lock is not an ESP-Mosaico Guest target.",
            details={"path": str(path)},
        )
    return value


def _resolve_game_path(repository: Path, requested: str, cwd: Path, *, create: bool) -> Path:
    raw = Path(requested).expanduser()
    candidate = (raw if raw.is_absolute() else cwd / raw).resolve()
    games_root = (repository / GAMES_RELATIVE_PATH).resolve()
    if not candidate.is_relative_to(games_root) or candidate == games_root:
        raise SelectionError(
            "MicroPixel games must be child directories of the repository games directory.",
            details={"games_root": str(games_root), "requested": str(candidate)},
        )
    if create:
        if candidate.exists() and not candidate.is_dir():
            raise SelectionError(f"The game path is not a directory: {candidate}")
        if (candidate / "app.json").exists():
            raise SelectionError(f"A MicroPixel game already exists at: {candidate}")
    elif not (candidate / "app.json").is_file():
        raise SelectionError(f"No MicroPixel app.json was found at: {candidate}")
    return candidate


def _decode_tool_result(output: str, action: str) -> dict[str, Any]:
    lines = [line for line in output.splitlines() if line.strip()]
    try:
        value = json.loads(lines[-1])
    except (IndexError, json.JSONDecodeError) as error:
        raise BuildError(
            f"MicroPixel {action} returned invalid structured output."
        ) from error
    if not isinstance(value, dict):
        raise BuildError(f"MicroPixel {action} returned an invalid result.")
    return value


def _micropixel_tool(repository: Path) -> Path:
    tool = repository / MICROPIXEL_RELATIVE_PATH / "tools/micropixel"
    if not tool.is_file():
        raise BuildError(
            "The MicroPixel submodule is not initialized.",
            details={
                "path": str(tool),
                "hint": "Run 'git submodule update --init submodule/micropixel'.",
            },
        )
    return tool


def _verify_micropixel_revision(
    repository: Path, context: RunContext, lock: dict[str, Any]
) -> Path:
    root = repository / MICROPIXEL_RELATIVE_PATH
    tool = _micropixel_tool(repository)
    result = context.run(
        ["git", "-C", root, "rev-parse", "HEAD"], timeout=10.0
    )
    actual = result.stdout.strip() if result.returncode == 0 else ""
    expected = str(lock["revision"])
    if actual != expected:
        raise BuildError(
            "The MicroPixel submodule revision does not match the runtime lock.",
            details={"expected": expected, "actual": actual or "unavailable"},
        )
    return tool


def create_game(
    repository: Path, arguments: Any, context: RunContext, cwd: Path | None = None
) -> dict[str, Any]:
    working_directory = cwd or Path.cwd()
    project = _resolve_game_path(
        repository, arguments.path, working_directory, create=True
    )
    lock = _load_runtime_lock(repository)
    tool = _verify_micropixel_revision(repository, context, lock)
    command = [
        sys.executable,
        "-X",
        "utf8",
        tool,
        "--json",
        "init",
        project,
        "--app-id",
        arguments.app_id,
        "--title",
        arguments.title,
    ]
    context.status(f"game: creating {project}")
    result = context.run(command, timeout=30.0)
    value = _decode_tool_result(result.stdout, "init")
    if result.returncode or value.get("ok") is not True:
        error = value.get("error") if isinstance(value.get("error"), dict) else {}
        raise OperationError(
            "MicroPixel game creation failed.",
            details={"tool_error": error, "path": str(project)},
        )
    return {
        "command": "game create",
        "status": "succeeded",
        "project": str(project),
        "app_id": arguments.app_id,
        "runtime_revision": lock["revision"],
    }


def build_game(
    repository: Path, arguments: Any, context: RunContext, cwd: Path | None = None
) -> dict[str, Any]:
    working_directory = cwd or Path.cwd()
    project = _resolve_game_path(
        repository, arguments.path, working_directory, create=False
    )
    lock = _load_runtime_lock(repository)
    tool = _verify_micropixel_revision(repository, context, lock)
    output_dir = project / "build"
    command: list[str | os.PathLike[str]] = [
        sys.executable,
        "-X",
        "utf8",
        tool,
        "--json",
        "package",
        project,
        "--profile",
        arguments.profile,
        "--aot-target",
        str(lock["aot_arch"]),
        "--output-dir",
        output_dir,
    ]
    if arguments.force:
        command.append("--force")
    context.status(
        f"game: building {project.name} for {lock['target']} ({lock['aot_arch']})"
    )
    result = context.run(command, timeout=arguments.timeout)
    value = _decode_tool_result(result.stdout, "package")
    if result.returncode or value.get("ok") is not True:
        error = value.get("error") if isinstance(value.get("error"), dict) else {}
        raise BuildError(
            "MicroPixel game build failed.",
            details={"tool_error": error, "project": str(project)},
        )
    payload = value.get("result")
    artifacts = payload.get("artifacts") if isinstance(payload, dict) else None
    bundle_items = [
        item
        for item in artifacts or []
        if isinstance(item, dict)
        and item.get("kind") == "bundle"
        and item.get("target") == lock["aot_arch"]
    ]
    if len(bundle_items) != 1:
        raise BuildError(
            "MicroPixel did not report exactly one ESP-Mosaico Bundle artifact.",
            details={"artifacts": artifacts or []},
        )
    bundle = Path(str(bundle_items[0].get("path", ""))).resolve()
    if not bundle.is_relative_to(output_dir.resolve()) or not bundle.is_file():
        raise BuildError(
            "MicroPixel reported an invalid Bundle artifact path.",
            details={"bundle": str(bundle), "output_dir": str(output_dir)},
        )
    try:
        app = json.loads((project / "app.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise BuildError("The game manifest became unreadable after the build.") from error
    digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
    manifest = {
        "schema_version": 1,
        "app_id": app.get("app_id"),
        "app_version": app.get("version"),
        "target": lock["target"],
        "aot_arch": lock["aot_arch"],
        "aot_format": lock["aot_format"],
        "bundle_format": lock["bundle_format"],
        "runtime_revision": lock["revision"],
        "sdk_version": payload.get("sdk_version") if isinstance(payload, dict) else None,
        "toolchain_id": payload.get("toolchain_id") if isinstance(payload, dict) else None,
        "bundle": bundle.name,
        "size_bytes": bundle.stat().st_size,
        "sha256": digest,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "build-manifest.json"
    temporary = manifest_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, manifest_path)
    context.status(f"bundle: {bundle} ({bundle.stat().st_size} bytes)")
    return {
        "command": "game build",
        "status": "succeeded",
        "project": str(project),
        "bundle": str(bundle),
        "build_manifest": str(manifest_path),
        "sha256": digest,
        "target": lock["target"],
        "aot_arch": lock["aot_arch"],
        "runtime_revision": lock["revision"],
    }


def _scenario(path: Path) -> tuple[str, list[str], dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SelectionError("The simulator scenario is missing or invalid JSON.", details={"path": str(path)}) from error
    if not isinstance(value, dict) or value.get("schema_version") != 1 or value.get("fixed_step_us") != 16667:
        raise SelectionError("The simulator scenario schema or fixed step is unsupported.")
    encoded: list[str] = []
    previous = -1
    for event in value.get("events", []):
        if not isinstance(event, dict) or event.get("action") not in {"left", "right", "jump", "restart"} or event.get("state") not in {"down", "up"}:
            raise SelectionError("The simulator scenario contains an invalid event.")
        frame = event.get("frame")
        if not isinstance(frame, int) or frame < previous or frame < 0:
            raise SelectionError("Scenario event frames must be non-negative and sorted.")
        previous = frame
        encoded.append(f"{frame}:{event['action']}:{event['state']}")
    expect = value.get("expect", {})
    if not isinstance(expect, dict) or not isinstance(expect.get("required_logs", []), list):
        raise SelectionError("The simulator scenario expect object is invalid.")
    return ";".join(encoded), [str(item) for item in expect.get("required_logs", [])], expect


def simulate_game(
    repository: Path, arguments: Any, context: RunContext, cwd: Path | None = None
) -> dict[str, Any]:
    project = _resolve_game_path(repository, arguments.path, cwd or Path.cwd(), create=False)
    try:
        app_manifest = json.loads((project / "app.json").read_text(encoding="utf-8"))
        app_id = str(app_manifest["app_id"])
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError) as error:
        raise SelectionError("The game app.json does not contain a valid App ID.") from error
    lock = _load_runtime_lock(repository)
    tool = _verify_micropixel_revision(repository, context, lock)
    runtime = repository / MICROPIXEL_RELATIVE_PATH
    wamr = runtime / "firmware/espressif/components/wasm-micro-runtime"
    if not (wamr / "core/iwasm/include/wasm_export.h").is_file():
        raise BuildError("The locked WAMR submodule is not initialized.", details={"hint": "git -C submodule/micropixel submodule update --init firmware/espressif/components/wasm-micro-runtime"})
    if shutil.which("cmake") is None or shutil.which("pkg-config") is None:
        raise BuildError("The simulator requires cmake and pkg-config.")
    sdl = context.run(["pkg-config", "--modversion", "sdl2"], timeout=10.0)
    if sdl.returncode:
        raise BuildError("SDL2 development files were not found (pkg-config sdl2).")

    scenario_path = Path(arguments.scenario).resolve() if arguments.scenario else project / "scenarios/complete.json"
    events, required_logs, expect = _scenario(scenario_path)
    output_dir = project / "build"
    wasm = output_dir / f"{project.name}.wasm"
    digest_input = hashlib.sha256()
    source_files = [project / "app.json", *(path for path in sorted(project.glob("src/**/*")) if path.is_file())]
    for path in source_files:
        digest_input.update(path.relative_to(project).as_posix().encode("utf-8") + b"\0")
        digest_input.update(path.read_bytes())
    source_digest = digest_input.hexdigest()
    sim_manifest = output_dir / "sim-build-manifest.json"
    reusable = False
    if arguments.skip_build and wasm.is_file() and sim_manifest.is_file():
        try:
            old = json.loads(sim_manifest.read_text(encoding="utf-8"))
            reusable = old.get("runtime_revision") == lock["revision"] and old.get("source_sha256") == source_digest
        except (OSError, json.JSONDecodeError):
            pass
        if not reusable:
            raise BuildError("--skip-build requires a complete WASM matching sources and runtime revision.")
    if not reusable:
        context.status(f"game: building {project.name} WASM")
        built = context.run([sys.executable, "-X", "utf8", tool, "--json", "build", project,
                             "--profile", "release", "--aot-target", str(lock["aot_arch"]),
                             "--output-dir", output_dir, "--wasm-only"], timeout=arguments.timeout)
        value = _decode_tool_result(built.stdout, "WASM build")
        if built.returncode or value.get("ok") is not True or not wasm.is_file():
            raise BuildError("MicroPixel WASM build failed.", details={"output": built.stdout[-2000:]})
        output_dir.mkdir(parents=True, exist_ok=True)
        sim_manifest.write_text(json.dumps({"schema_version": 1, "runtime_revision": lock["revision"], "source_sha256": source_digest}, indent=2) + "\n", encoding="utf-8")

    sim_build = repository / "build/micropixel-sim"
    context.status("sim: building Linux WAMR/SDL2 host")
    configured = context.run(["cmake", "-S", runtime / "simulator", "-B", sim_build], timeout=arguments.timeout)
    if configured.returncode:
        raise BuildError("MicroPixel simulator configuration failed.", details={"output": configured.stdout[-2000:]})
    compiled = context.run(["cmake", "--build", sim_build, "-j2"], timeout=arguments.timeout)
    if compiled.returncode:
        raise BuildError("MicroPixel simulator build failed.", details={"output": compiled.stdout[-2000:]})

    state_dir = output_dir / "sim-state"
    if arguments.reset_storage and state_dir.exists():
        shutil.rmtree(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    dump = Path(arguments.dump_ppm).resolve() if arguments.dump_ppm else output_dir / "sim-final.ppm"
    report_path = Path(arguments.report).resolve() if arguments.report else output_dir / "sim-report.json"
    audio_dump = output_dir / "sim-audio.pcm"
    env = os.environ.copy()
    env.update({"LD_LIBRARY_PATH": str(sim_build), "MICROPIXEL_SIM_HEADLESS": "1" if arguments.headless else "0",
                "MICROPIXEL_SIM_EVENTS": events, "MICROPIXEL_SIM_MAX_FRAMES": str(arguments.frames),
                "MICROPIXEL_SIM_DUMP": str(dump), "MICROPIXEL_SIM_AUDIO": str(audio_dump),
                "MICROPIXEL_SIM_STATE": str(state_dir)})
    command = [sim_build / "micropixel-iwasm", f"--native-lib={sim_build / 'libmicropixel_sim_host.so'}", "-f", "__micropixel_start", wasm]
    context.status(f"sim: running {project.name} ({'headless' if arguments.headless else 'SDL'})")
    ran = context.run(command, timeout=arguments.timeout, env=env)
    logs = [line.split(" ", 2)[2] for line in ran.stdout.splitlines() if line.startswith("GUEST_LOG ") and len(line.split(" ", 2)) == 3]
    missing = [item for item in required_logs if not any(item in line for line in logs)]
    meta_match = re.search(r"SIM_META frames=(\d+) presented=(\d+) exit=([a-z_]+)", ran.stdout)
    completed = any("level_complete" in line for line in logs)
    exit_reason = "level_complete" if completed else (meta_match.group(3) if meta_match else "trap")
    frame_hash = hashlib.sha256(dump.read_bytes()).hexdigest() if dump.is_file() else ""
    audio_hash = hashlib.sha256(audio_dump.read_bytes()).hexdigest() if audio_dump.is_file() else ""
    storage_file = state_dir / "completions"
    completion_count = int.from_bytes(storage_file.read_bytes()[:4], "little") if storage_file.is_file() else 0
    hashes_match = frame_hash == expect.get("frame_sha256", frame_hash) and audio_hash == expect.get("audio_sha256", audio_hash)
    passed = ran.returncode == 0 and bool(frame_hash) and bool(audio_hash) and hashes_match and not missing and exit_reason == expect.get("exit_reason", exit_reason)
    report = {"schema_version": 1, "status": "passed" if passed else "failed",
              "app_id": app_id, "runtime_revision": lock["revision"],
              "frames": int(meta_match.group(1)) if meta_match else 0, "exit_reason": exit_reason,
              "frame_sha256": frame_hash, "audio_sha256": audio_hash, "logs": logs,
              "storage": {"completion_count": completion_count}}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not passed:
        raise OperationError("MicroPixel simulator acceptance failed.", details={"report": str(report_path), "missing_logs": missing, "hashes_match": hashes_match, "guest_exit": ran.returncode})
    return {"command": "game sim", "status": "passed", "project": str(project), "report": str(report_path), "dump_ppm": str(dump), **report}
