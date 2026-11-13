import ctypes
import random
import signal
import sys
import threading

from reachy_mini import ReachyMini

from gestures import FACT_GESTURES, GREETING_GESTURE, Gestures
from speech import Speaker

CONDITIONS = {"real": "True source", "fake": "Fabricated source", "none": "No source"}


def phrase(data: dict, index: int, condition: str) -> str:
    # Each fact keeps the same wording in every session, so true and fabricated sources only differ by the source
    fact = data["facts"][index]
    templates = data["templates"][condition]
    # Templates add the final punctuation, so a question can end with "?"
    text = templates[index % len(templates)].format(statement=fact["statement"].rstrip("."),
                                                    source=fact.get(f"{condition}_source", ""))
    return text[0].upper() + text[1:]


def all_clips(data: dict) -> dict[str, str]:
    clips = dict(data["lines"])
    for index, fact in enumerate(data["facts"]):
        for condition in CONDITIONS:
            clips[f"{fact['id']}_{condition}"] = phrase(data, index, condition)
    return clips


def ask_condition() -> str:
    options = list(CONDITIONS)
    print("Condition for this session:")
    for number, condition in enumerate(options, start=1):
        print(f"  {number}. {CONDITIONS[condition]}")
    while True:
        choice = input("Choose 1-3: ").strip()
        if choice in {str(number) for number in range(1, len(options) + 1)}:
            condition = options[int(choice) - 1]
            print(f"Using: {CONDITIONS[condition]}\n")
            return condition


def plan_session(data: dict, condition: str) -> list[dict]:
    facts = [{
        "id": fact["id"],
        "veracity": fact["veracity"],
        "text": phrase(data, index, condition),
        "clip": f"{fact['id']}_{condition}",
    } for index, fact in enumerate(data["facts"])]
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


def run_session(mini: ReachyMini, speaker: Speaker, gestures: Gestures, facts: list[dict], condition: str) -> None:
    sleep = put_to_sleep_on_exit(mini)
    try:
        mini.enable_motors()
        mini.wake_up()

        print(f"\nSession plan ({CONDITIONS[condition]}), for the Fact ID and Veracity columns of the "
              "Responses sheet:\n")
        for order, fact in enumerate(facts, start=1):
            print(f"{order}\t{fact['id']}\t{fact['veracity']}")

        with speaker:
            input("\nReady. Press Enter to start the session...")
            print(f"  Gesture: {GREETING_GESTURE}")
            speaker.say("greeting")
            gestures.play(GREETING_GESTURE)
            speaker.wait()

            for order, fact in enumerate(facts, start=1):
                input(f"\nFact {order}/{len(facts)}: press Enter when the participant is ready...")
                gesture = FACT_GESTURES[(order - 1) % len(FACT_GESTURES)]
                print(f'  [{fact["id"]}, {fact["veracity"]}] Reachy: "{fact["text"]}"')
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