import argparse
import logging
import os
import time
from contextlib import contextmanager
from pathlib import Path

# Hides harmless RTP errors on the wireless robot; must be set before reachy_mini starts GStreamer
os.environ.setdefault("GST_DEBUG", "rtpsession:0")

from reachy_mini import ReachyMini

from gestures import Gestures
from session import load_session, run_session
from speech import Speaker

ROOT = Path(__file__).parent
LINES_PATH = ROOT / "lines.json"
AUDIO_DIR = ROOT / "audio"
VOICE_PATH = ROOT / "models" / "speech" / "en_US-lessac-high.onnx"
QUIET_LOGGERS = ("reachy_mini.media.device_detection", "reachy_mini.media.audio_gstreamer",
                 "reachy_mini.media.webrtc_client_gstreamer")

CONNECTIONS = {
    "wireless": {"connection_mode": "network", "host": "reachy-mini.local"},
    "local": {"connection_mode": "localhost_only"},
    "onboard": {"connection_mode": "localhost_only"},
}


@contextmanager
def loading(message: str):
    print(f"{message}...", end=" ", flush=True)
    start = time.perf_counter()
    yield
    print(f"done ({time.perf_counter() - start:.1f}s)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one participant session of the source-citation study.")
    parser.add_argument("--target", choices=CONNECTIONS, default="local",
                        help="How to reach the robot (default: local, for the simulator).")
    parser.add_argument("--host", help="Robot hostname or IP address for wireless (default: reachy-mini.local).")
    args = parser.parse_args()
    args.connection = dict(CONNECTIONS[args.target])
    if args.host:
        args.connection["host"] = args.host
    return args


def print_settings(args: argparse.Namespace) -> None:
    print("Settings:")
    print(f"  Target:      {args.target} {args.connection}")
    print(f"  Voice:       {VOICE_PATH.name}")
    print()


def run(args: argparse.Namespace) -> None:
    lines, facts = load_session(LINES_PATH)

    with loading("Connecting to Reachy Mini"):
        mini = ReachyMini(media_backend="default", **args.connection)

    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.ERROR)

    with mini:
        with loading("Preparing speech"):
            speaker = Speaker(mini, VOICE_PATH, AUDIO_DIR,
                              {**lines, **{fact["clip"]: fact["text"] for fact in facts}})
        with loading("Loading gestures"):
            gestures = Gestures(mini)

        run_session(mini, speaker, gestures, facts)


def main() -> None:
    args = parse_args()
    print_settings(args)
    run(args)


if __name__ == "__main__":
    main()