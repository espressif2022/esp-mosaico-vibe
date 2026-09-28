"""Persistent HTTP transport for managed ESP-Iris raw RPC calls.

This is launched with the Python interpreter and Gateway profile selected by
the repository's supported ESP-Iris CLI. It uses that CLI's profile, TLS,
authentication, and HTTP response helpers, while reusing one HTTP session.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys
import uuid


async def _serve(arguments: argparse.Namespace) -> int:
    sys.path.insert(0, str(arguments.iris_tools.resolve()))
    from aiohttp import ClientSession, ClientTimeout  # type: ignore[import-not-found]
    from iris_gateway.cli import _client_ssl, _headers, _profile, _response_json

    _, profile = _profile(arguments)
    base = str(profile["url"]).rstrip("/")
    ssl_value = _client_ssl(profile, arguments.insecure)
    async with ClientSession(headers=_headers(profile)) as session:
        for line in sys.stdin:
            try:
                request = json.loads(line)
                if request.get("close"):
                    print(json.dumps({"ok": True}), flush=True)
                    return 0
                method_id = int(request["method_id"])
                body = {
                    "service_id": int(request["service_id"]),
                    "method_id": method_id,
                    "deadline_ms": int(request["deadline_ms"]),
                    "payload_base64": request["payload_base64"],
                }
                url = base + f"/v1/devices/{arguments.device_id}/rpc/raw"
                async with session.post(
                    url,
                    json=body,
                    headers={"X-Operation-ID": str(uuid.uuid4())},
                    ssl=ssl_value,
                    timeout=ClientTimeout(total=max(15, body["deadline_ms"] / 1000 + 5)),
                ) as response:
                    value = await _response_json(response)
                print(json.dumps({"ok": True, "response": value}), flush=True)
            except Exception as error:
                print(json.dumps({"ok": False, "message": str(error)}), flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iris-tools", type=Path, required=True)
    parser.add_argument("--device-id", required=True)
    parser.add_argument("--profile")
    parser.add_argument("--url")
    parser.add_argument("--ca")
    parser.add_argument("--fingerprint")
    parser.add_argument("--insecure", action="store_true")
    return asyncio.run(_serve(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
