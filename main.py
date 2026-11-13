import argparse
import json
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path

# Hides harmless RTP errors on the wireless robot; must be set before reachy_mini starts GStreamer
os.environ.setdefault("GST_DEBUG", "rtpsession:0")

from gestures import Gestures
from robot import CONNECTIONS, SetupError, connect
from session import all_clips, ask_condition, plan_session, run_session
from speech import Speaker, synthesize

ROOT = Path(__file__).parent
LINES_PATH = ROOT / "lines.json"
AUDIO_DIR = ROOT / "audio"
VOICE_PATH = ROOT / "models" / "speech" / "en_US-lessac-high.onnx"


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
    parser.add_argument("--prepare", action="store_true",
                        help="Generate the speech for every line and condition, then exit. No robot needed.")
    parser.add_argument("--number", type=int, choices=range(1, 7),
                        help="Participant number in the group (1-6), used to select the fact pattern.")
    args = parser.parse_args()
    return args


def print_settings(args: argparse.Namespace) -> None:
    print("Settings:")
    print(f"  Target:      {'none (preparing speech)' if args.prepare else args.target}")
    if args.host:
        print(f"  Host:        {args.host}")
    print(f"  Voice:       {VOICE_PATH.name}")
    print()


def run(args: argparse.Namespace) -> None:
    data = json.loads(LINES_PATH.read_text(encoding="utf-8"))

    if args.prepare:
        clips = all_clips(data)
        with loading(f"Generating speech for {len(clips)} lines"):
            synthesize(VOICE_PATH, AUDIO_DIR, clips)
        return

    condition = ask_condition()
    facts = plan_session(data, condition, args.number)
    with loading("Preparing speech"):
        clip_paths = synthesize(VOICE_PATH, AUDIO_DIR,
                                {**data["lines"], **{fact["clip"]: fact["text"] for fact in facts}})

    with loading("Connecting to Reachy Mini"):
        mini = connect(args.target, args.host)

    with mini:
        with loading("Uploading speech"):
            speaker = Speaker(mini, clip_paths)
        with loading("Loading gestures"):
            gestures = Gestures(mini)

        run_session(mini, speaker, gestures, facts, condition)


def main() -> None:
    args = parse_args()
    print_settings(args)
    try:
        run(args)
    except SetupError as error:
        print(f"\n\nError: {error}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()