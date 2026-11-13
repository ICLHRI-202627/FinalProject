import numpy as np
from reachy_mini import ReachyMini
from reachy_mini.motion.move import Move
from reachy_mini.motion.recorded_move import RecordedMoves

from robot import SetupError

DATASET = "pollen-robotics/reachy-mini-emotions-library"
GREETING_GESTURE = "welcoming1"
# Played while Reachy says each fact, picked by position in the session (never by fact or condition)
FACT_GESTURES = ["attentive1", "thoughtful1", "helpful1", "yes1", "cheerful1"]
GOTO_SECONDS = 0.5
ANTENNA_SCALE = 0.3
NEUTRAL_ANTENNAS = np.array([-0.1745, 0.1745])


class CalmGesture(Move):
    """A recorded gesture without body rotation, and with smaller antenna movements."""

    def __init__(self, move: Move):
        self.move = move

    @property
    def duration(self) -> float:
        return self.move.duration

    def evaluate(self, t: float):
        head, antennas, _ = self.move.evaluate(t)
        if antennas is not None:
            antennas = NEUTRAL_ANTENNAS + (np.asarray(antennas) - NEUTRAL_ANTENNAS) * ANTENNA_SCALE
        return head, antennas, None


class Gestures:
    def __init__(self, mini: ReachyMini):
        self.mini = mini
        self.library = RecordedMoves(DATASET)
        available = self.library.list_moves()
        missing = [name for name in [GREETING_GESTURE, *FACT_GESTURES] if name not in available]
        if missing:
            raise SetupError(f"Unknown gestures {missing} in gestures.py. Available: {sorted(available)}")

    def play(self, name: str) -> None:
        self.mini.play_move(CalmGesture(self.library.get(name)), initial_goto_duration=GOTO_SECONDS, sound=False)