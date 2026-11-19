import ctypes
import random
import signal
import sys
import threading
from typing import Callable

from reachy_mini import ReachyMini

from gestures import FACT_GESTURES, GREETING_GESTURE, Gestures
from speech import Speaker

CONDITIONS = {"real": "True source", "fake": "Fabricated source", "none": "No source"}
GROUPS = {"A": "none", "B": "fake", "C": "real"}
BASE_TRUTH_PATTERN = (True, True, False, False, True, False, True, False, False, True)


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
    print("Group for this session:")
    for group, condition in GROUPS.items():
        print(f"  {group}. {CONDITIONS[condition]}")
    while True:
        group = input(f"Choose {', '.join(GROUPS)}: ").strip().upper()
        if group in GROUPS:
            print(f"Using: group {group} ({CONDITIONS[GROUPS[group]]})\n")
            return GROUPS[group]


def plan_session(data: dict, condition: str, participant_number: int) -> list[dict]:
    shift = (participant_number - 1) % len(BASE_TRUTH_PATTERN)
    truth_pattern = BASE_TRUTH_PATTERN[shift:] + BASE_TRUTH_PATTERN[:shift]
    facts_by_veracity = {
        veracity: [
            {
                "id": fact["id"],
                "fact_order": index + 1,
                "veracity": fact["veracity"],
                "text": phrase(data, index, condition),
                "clip": f"{fact['id']}_{condition}",
            }
            for index, fact in enumerate(data["facts"])
            if fact["veracity"] is veracity
        ]
        for veracity in (True, False)
    }
    for facts in facts_by_veracity.values():
        random.shuffle(facts)

    positions = {True: 0, False: 0}
    facts = []
    for veracity in truth_pattern:
        facts.append(facts_by_veracity[veracity][positions[veracity]])
        positions[veracity] += 1
    return facts


class Robot:
    """The current connection to Reachy, which can be reopened if it drops in the middle of a session."""

    def __init__(self, open_robot: Callable[[], tuple[ReachyMini, Speaker, Gestures]]):
        self.open_robot = open_robot
        self.mini = self.speaker = self.gestures = None

    def start(self) -> None:
        self.mini, self.speaker, self.gestures = self.open_robot()
        self.speaker.__enter__()
        self.mini.enable_motors()
        self.mini.wake_up()

    def close(self) -> None:
        for part in (self.speaker, self.mini):
            if part is not None:
                try:
                    part.__exit__(None, None, None)
                except Exception:
                    pass
        self.mini = self.speaker = self.gestures = None

    def perform(self, clip: str, gesture: str | None) -> None:
        # Checking first avoids starting a line the robot can't finish
        if self.mini is None or not self.mini.client.is_connected():
            raise ConnectionError("Lost connection with Reachy.")
        self.speaker.say(clip)
        try:
            if gesture:
                self.gestures.play(gesture)
        finally:
            self.speaker.wait()

    def reconnect(self) -> None:
        while True:
            self.close()
            print("  Reconnecting to Reachy...")
            try:
                self.start()
                print("  Reconnected.")
                return
            except Exception as error:
                print(f"  Could not reconnect: {error}")
                input("  Check the robot, then press Enter to try again (Ctrl+C stops the session)...")


def run_step(robot: Robot, prompt: str | None, clip: str, gesture: str | None = None, description: str = "",
             can_skip: bool = True) -> bool:
    # Returns False if the researcher skipped the line; with no prompt the line is said straight away
    answer = input(f"{prompt} (Enter to go{', s to skip' if can_skip else ''}) ").strip().lower() if prompt else ""
    while True:
        if answer == "s" and can_skip:
            print("  Skipped.")
            return False
        if description:
            print(description)
        if gesture:
            print(f"  Gesture: {gesture}")
        try:
            robot.perform(clip, gesture)
            return True
        except Exception as error:
            print(f"\n  Reachy stopped responding ({error}).")
            robot.reconnect()
            answer = input(f"  Enter to say it again{', s to skip it' if can_skip else ''}: ").strip().lower()


def ask_response(order: int, total: int) -> str:
    while True:
        answer = input(f"Participant's response (y = yes, n = no, s = skip): ").strip().upper()
        if answer in ("Y", "N", "S"):
            return answer
        print("  Please enter y, n or s.")


def put_to_sleep_on_exit(robot: Robot):
    lock = threading.Lock()
    done = False

    def sleep() -> None:
        nonlocal done
        with lock:
            if done or robot.mini is None:
                return
            done = True
            try:
                robot.mini.goto_sleep()
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


def run_session(open_robot: Callable[[], tuple[ReachyMini, Speaker, Gestures]], facts: list[dict],
                condition: str) -> None:
    robot = Robot(open_robot)
    robot.start()
    sleep = put_to_sleep_on_exit(robot)
    skipped = set()
    responses = {}
    try:
        run_step(robot, "\nReady. Start the session with the greeting?", "greeting", GREETING_GESTURE, can_skip=False)

        for order, fact in enumerate(facts, start=1):
            gesture = FACT_GESTURES[(order - 1) % len(FACT_GESTURES)]
            said = run_step(robot, None, fact["clip"], gesture,
                            f'\nFact {order}/{len(facts)} [{fact["id"]}, {fact["veracity"]}] '
                            f'Reachy: "{fact["text"]}"')
            if not said:
                skipped.add(order)
                continue
            response = ask_response(order, len(facts))
            if response == "S":
                skipped.add(order)
                print("  Skipped.")
            else:
                responses[order] = response

        print("\nSaying goodbye.")
        run_step(robot, None, "farewell", can_skip=False)
        print("\nSession finished.")
        print(f"\nSession plan ({CONDITIONS[condition]}), for the Fact ID and Veracity columns of the "
              "Responses sheet:\n")
        id_width = max(len(fact["id"]) for fact in facts)
        for order, fact in enumerate(facts, start=1):
            print(f"{order:>2}  {fact['id']:<{id_width}}  {str(fact['veracity']):<5}" +
                  ("  (skipped)" if order in skipped else ""))
        print("\nTruth pattern of the facts (T = true, F = false):")
        print("".join("T" if fact["veracity"] else "F" for fact in facts))

        ordered_facts = sorted(enumerate(facts, start=1), key=lambda item: item[1]["fact_order"])
        print("\nSession summary in lines.json fact order:\n")
        print(f"Fact order  Session order  {'Fact ID':<{id_width}}  Veracity  TaskId-ordered Response  Session-order response")
        for asked_order, (session_order, fact) in enumerate(ordered_facts, start=1):
            print(f"{fact['fact_order']:>10}  {session_order:>13}  {fact['id']:<{id_width}}  "
                  f"{str(fact['veracity']):<8}  {responses.get(session_order, ''):<8}  "
                  f"{responses.get(asked_order, ''):<20}" +
                  ("  (skipped)" if session_order in skipped else ""))
        # print("\nTruth pattern in lines.json fact order (T = true, F = false):")
        # print("".join("T" if fact["veracity"] else "F" for _, fact in ordered_facts))
        print("")
    except (KeyboardInterrupt, EOFError):
        print("\nSession stopped.")
    finally:
        sleep()
        robot.close()
