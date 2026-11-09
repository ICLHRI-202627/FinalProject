import hashlib
import queue
import threading
import time
import wave
from pathlib import Path

import numpy as np
from piper import PiperVoice
from reachy_mini import ReachyMini
from reachy_mini.io.protocol import SetSpeechOffsetsCmd
from reachy_mini.motion.speech_tapper import HOP_MS, SwayRollRT

from robot import SetupError

SENTENCE_PAUSE_SECONDS = 0.25
PRONUNCIATIONS = {"Reachy": "Reechee"}
WOBBLE_SCALE = 0.5
ZERO_OFFSETS = [0.0] * 6


def synthesize(voice_path: Path, audio_dir: Path, clips: dict[str, str]) -> dict[str, Path]:
    # Piper is slow, so each WAV is reused until its line or the voice changes
    audio_dir.mkdir(exist_ok=True)
    voice = None
    paths = {}
    for clip, text in clips.items():
        for word, respelling in PRONUNCIATIONS.items():
            text = text.replace(word, respelling)
        key = hashlib.sha1(f"{voice_path.name}|{SENTENCE_PAUSE_SECONDS}|{text}".encode()).hexdigest()[:10]
        paths[clip] = path = audio_dir / f"{clip}_{key}.wav"
        if path.exists():
            continue

        if voice is None:
            if not voice_path.exists():
                raise SetupError(f"Voice file {voice_path} not found. Download it with: uv run python -m "
                                 f"piper.download_voices {voice_path.stem} --data-dir {voice_path.parent}")
            voice = PiperVoice.load(str(voice_path))

        pause = np.zeros(int(SENTENCE_PAUSE_SECONDS * voice.config.sample_rate), dtype=np.float32)
        parts = []
        for chunk in voice.synthesize(text):
            parts += [chunk.audio_float_array.astype(np.float32), pause]
        audio = np.concatenate(parts)

        for old in audio_dir.glob(f"{clip}_*.wav"):
            old.unlink()
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(voice.config.sample_rate)
            wav.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
    return paths


class Speaker:
    def __init__(self, mini: ReachyMini, clip_paths: dict[str, Path]):
        self.mini = mini
        self.clips = {}
        for clip, path in clip_paths.items():
            with wave.open(str(path)) as wav:
                sample_rate = wav.getframerate()
                audio = np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16).astype(np.float32) / 32767

            # The same head sway the SDK computes from the audio, scaled down, one offset per hop
            wobble = [[hop["x_mm"] / 1000 * WOBBLE_SCALE, hop["y_mm"] / 1000 * WOBBLE_SCALE,
                       hop["z_mm"] / 1000 * WOBBLE_SCALE, hop["roll_rad"] * WOBBLE_SCALE,
                       hop["pitch_rad"] * WOBBLE_SCALE, hop["yaw_rad"] * WOBBLE_SCALE]
                      for hop in SwayRollRT(sample_rate=sample_rate).feed(audio)]

            remote_path = mini.media.audio.upload_sound(str(path.resolve()))
            self.clips[clip] = (remote_path, len(audio) / sample_rate, wobble)

        self.queue = queue.Queue()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def say(self, clip: str, wait: bool = False) -> None:
        self.queue.put(clip)
        if wait:
            self.wait()

    def wait(self) -> None:
        self.queue.join()

    def _run(self) -> None:
        while (clip := self.queue.get()) is not None:
            path, duration, wobble = self.clips[clip]
            self.mini.media.play_sound(path)
            start = time.monotonic()
            for index, offsets in enumerate(wobble):
                time.sleep(max(0.0, start + index * HOP_MS / 1000 - time.monotonic()))
                self.mini.client.send_command(SetSpeechOffsetsCmd(offsets=offsets))
            self.mini.client.send_command(SetSpeechOffsetsCmd(offsets=ZERO_OFFSETS))
            time.sleep(max(0.0, start + duration - time.monotonic()))
            self.queue.task_done()
        self.queue.task_done()

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.queue.put(None)
        self.thread.join(timeout=10)
