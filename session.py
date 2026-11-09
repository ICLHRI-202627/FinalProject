import ctypes
import random
import signal
import sys
import threading

from reachy_mini import ReachyMini

from gestures import FACT_GESTURES, GREETING_GESTURE, Gestures
from speech import Speaker

CONDITIONS = ("none", "real", "fake")


def phrase(data: dict, fact: dict, condition: str) -> str:
    text = data["templates"][condition].format(statement=fact["statement"],
                                               source=fact.get(f"{condition}_source", ""))
    return text[0].upper() + text[1:]


def all_clips(data: dict) -> dict[str, str]:
    clips = dict(data["lines"])
    for fact in data["facts"]:
        for condition in CONDITIONS:
            clips[f"{fact['id']}_{condition}"] = phrase(data, fact, condition)
    return clips


def plan_session(data: dict) -> list[dict]:
    offset = random.randrange(len(CONDITIONS))
    facts = []
    for veracity in (True, False):
        group = [fact for fact in data["facts"] if fact["veracity"] == veracity]
        for index, fact in enumerate(group):
            condition = CONDITIONS[(index + offset) % len(CONDITIONS)]
            facts.append({
                "id": fact["id"],
                "veracity": veracity,
                "condition": condition,
                "text": phrase(data, fact, condition),
                "clip": f"{fact['id']}_{condition}",
            })
    random.shuffle(facts)
    return facts


def put_to_sleep_on_exit(mini: ReachyMini):
    lock = threading.Lock()
    done = False

    def sleep() -> None:
        nonlocal done
        with lock:
            if done:
                return
            done = True
            try:
                mini.goto_sleep()
            except Exception as error:
                print(f"\nCould not put Reachy to sleep: {error}")

    if sys.platform == "win32":
        close_events = {2, 5, 6}  # window closed, user logged off, shutdown

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)
        def on_console_event(event: int) -> bool:
            if event in close_events:
                sleep()
            return False

        ctypes.windll.kernel32.SetConsoleCtrlHandler(on_console_event, True)
        sleep.handler = on_console_event  # keeps the callback from being garbage collected
    else:
        for sig in (signal.SIGHUP, signal.SIGTERM):
            signal.signal(sig, lambda *_: sys.exit(1))
    return sleep


def run_session(mini: ReachyMini, speaker: Speaker, gestures: Gestures, facts: list[dict]) -> None:
    sleep = put_to_sleep_on_exit(mini)
    try:
        mini.enable_motors()
        mini.wake_up()

        with speaker:
            input("\nReady. Press Enter to start the session...")
            print(f"  Gesture: {GREETING_GESTURE}")
            speaker.say("greeting")
            gestures.play(GREETING_GESTURE)
            speaker.wait()

            for order, fact in enumerate(facts, start=1):
                input(f"\nFact {order}/{len(facts)}: press Enter when the participant is ready...")
                gesture = FACT_GESTURES[(order - 1) % len(FACT_GESTURES)]
                print(f'  [{fact["id"]}, {fact["condition"]}] Reachy: "{fact["text"]}"')
                print(f"  Gesture: {gesture}")
                speaker.say(fact["clip"])
                gestures.play(gesture)
                speaker.wait()

            input("\nPress Enter to say goodbye...")
            speaker.say("farewell", wait=True)
        print("\nSession finished.")
    except (KeyboardInterrupt, EOFError):
        print("\nSession stopped.")
    finally:
        sleep()