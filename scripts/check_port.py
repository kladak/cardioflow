from __future__ import annotations

import socket
import sys


def main() -> int:
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8010
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        connection.settimeout(0.25)
        if connection.connect_ex((host, port)) == 0:
            print(
                f"CardioFlow API cannot start: {host}:{port} is already in use.\n"
                "Stop the existing IPv4 listener or set API_PORT and CARDIOFLOW_API_ORIGIN to a free port.",
                file=sys.stderr,
            )
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
