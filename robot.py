import json
import logging
import time
import urllib.error
import urllib.request

from reachy_mini import ReachyMini

DAEMON_PORT = 8000
LOCAL_HOST = "127.0.0.1"
START_TIMEOUT_SECONDS = 60
QUIET_LOGGERS = ("reachy_mini.media.device_detection", "reachy_mini.media.audio_gstreamer",
                 "reachy_mini.media.webrtc_client_gstreamer")

CONNECTIONS = {
    "wireless": {"connection_mode": "network", "host": "reachy-mini.local"},
    "local": {"connection_mode": "localhost_only"},
    "onboard": {"connection_mode": "localhost_only"},
}


class SetupError(Exception):
    pass


def restart_advice(host: str) -> str:
    if host == LOCAL_HOST:
        return "Stop the simulator (Ctrl+C in its terminal) and start it again."
    return "Switch the robot off and on, wait a minute, and try again."


def call_daemon(host: str, method: str, path: str) -> dict:
    request = urllib.request.Request(f"http://{host}:{DAEMON_PORT}/api{path}", method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read() or "{}")
    except urllib.error.HTTPError as error:
        raise SetupError(f"The daemon returned an error for {method} {path} ({error.code}: {error.read().decode()}).")
    except (urllib.error.URLError, TimeoutError) as error:
        if host == LOCAL_HOST:
            raise SetupError("No Reachy Mini daemon is running on this computer. For the simulator, start "
                             "`uv run reachy-mini-daemon --sim` in another terminal first and wait for "
                             "`Daemon started successfully`; for the robot, use --target wireless.")
        raise SetupError(f"Can't reach Reachy at http://{host}:{DAEMON_PORT} ({error}). Check the robot is on "
                         "and on the same Wi-Fi as this computer, or pass its IP address with --host.")


def prepare_daemon(host: str) -> None:
    status = call_daemon(host, "GET", "/daemon/status")
    if status["state"] == "error":
        raise SetupError(f"The daemon is in an error state ({status['error']}). {restart_advice(host)}")

    if status["state"] != "running":
        print(f"\n  Backend is {status['state']}, starting it...", end=" ", flush=True)
        if status["state"] in ("stopped", "not_initialized"):
            call_daemon(host, "POST", "/daemon/start?wake_up=false")
        deadline = time.monotonic() + START_TIMEOUT_SECONDS
        while (status := call_daemon(host, "GET", "/daemon/status"))["state"] != "running":
            if status["state"] == "error" or time.monotonic() > deadline:
                raise SetupError(f"The backend did not start (state: {status['state']}, error: "
                                 f"{status['error']}). {restart_advice(host)}")
            time.sleep(1)
        print("started.", end=" ", flush=True)

    media = call_daemon(host, "GET", "/media/status")
    if media["no_media"]:
        raise SetupError(f"The daemon is running without audio, so Reachy can't speak. {restart_advice(host)}")
    if media["released"]:
        call_daemon(host, "POST", "/media/acquire")


def connect(target: str, host: str | None) -> ReachyMini:
    connection = dict(CONNECTIONS[target])
    if host:
        connection["host"] = host
    daemon_host = connection.get("host", LOCAL_HOST)
    prepare_daemon(daemon_host)

    try:
        mini = ReachyMini(media_backend="default", **connection)
    except ConnectionError as error:
        raise SetupError(f"The daemon is running but the connection failed ({error}). {restart_advice(daemon_host)}")

    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.ERROR)
    return mini