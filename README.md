# Source Citation Study: Reachy Mini

Human–Robot Interaction, Final Project.

Reachy Mini tells the participant a series of true and false facts. The study is between-subjects: each participant is in one condition, True source, Fabricated source or No source, and hears every fact phrased that way. Responses are recorded manually by the researcher; the program only says the lines.

## 1. Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.12 | Newer versions may not have prebuilt wheels for every dependency. |
| [uv](https://docs.astral.sh/uv/) | Recommended for creating the environment. |
| Reachy Mini | The MuJoCo simulator (installed with the requirements) or a physical robot. |

## 2. Installation

```bash
uv venv --python 3.12
uv pip install -r requirements.txt
uv run python -m piper.download_voices en_US-lessac-high --data-dir models/speech
```

`requirements.txt` installs `reachy-mini[mujoco]` (the SDK plus the MuJoCo simulator, so the study can be tested without the physical robot) and `piper-tts` for the voice. The last command downloads the voice into `models/speech`.

Then generate the speech for every line once, so no session has to wait for it (no robot needed):

```bash
uv run python main.py --prepare
```

Run it again whenever `lines.json` changes; only the lines that changed are regenerated.

## 3. Running a session

### With the simulator (day-to-day testing)

Start the simulator in its own terminal and wait for `Daemon started successfully`:

```bash
uv run reachy-mini-daemon --sim
```

Then, in a second terminal:

```bash
uv run python main.py --number 1
```

The simulator plays Reachy's voice through the computer's speakers, and the head, antennas and gestures move in the MuJoCo window, so the whole session can be checked without the robot. Leave the simulator running between test sessions; it doesn't need restarting.

### With the physical robot

The daemon already runs on the robot, so there's nothing to start:

```bash
uv run python main.py --target wireless
```

### Before connecting

With either target, the program first checks the daemon over its API and fixes the two states that otherwise make a session fail: it starts the backend if it is stopped, and takes back the audio hardware if another program (for example one connected with `no_media`) left it released. If the daemon can't be reached at all, it says how to start it.

Right after launching, the program asks for the participant number (1-6) and which condition to use (1 True source, 2 Fabricated source, 3 No source). The participant number selects a cyclic shift of the ten-slot truth pattern `T T F F T F T F F T`; each pattern contains five true and five false facts. The facts are shuffled within their veracity groups, so the truth/false pattern stays fixed while the specific fact in each slot changes. After the session finishes, the terminal prints the session plan: one line per fact with its order, fact ID and veracity, for filling in the responses spreadsheet.

The researcher presses Enter before each fact and before the farewell, so the pace follows the participant. The terminal shows each fact's id, veracity and text as Reachy says it, to help with manual logging. While Reachy says each fact it also plays a gesture, and its head sways gently with its voice.

The first run downloads the gestures (Pollen's emotions library) from Hugging Face, so it needs internet once.

If the program is stopped early (Ctrl+C, an error, or closing the terminal window), Reachy still goes to sleep before it exits.

## 4. Arguments

| Argument | Default | Description |
|---|---|---|
| `--target` | `local` | `local` (simulator or Lite), `wireless` (script on your computer, daemon on the robot) or `onboard` (script running on the robot). |
| `--host` | `reachy-mini.local` | Robot hostname or IP address, for `wireless`. Use the IP if the name doesn't resolve. |
| `--prepare` | off | Generate the speech for every line in every condition, then exit. Doesn't connect to the robot. |
| `--number` | required for sessions | Participant number from 1 to 6. Selects the cyclic truth pattern; omit with `--prepare`. |

## 5. Lines (`lines.json`)

| Key | What it holds |
|---|---|
| `lines` | Fixed lines said in every condition (`greeting`, `farewell`). |
| `templates` | A list of phrasings for each condition, with `{statement}` and `{source}` filled in. Each phrasing ends with its own punctuation (`.` or `?`), and the statement's full stop is dropped. The facts take turns through the list (1st fact the 1st phrasing, 2nd fact the 2nd, and so on), so a fact always has the same wording, and `real` and `fake` should keep matching lists so the source is the only difference between them. |
| `facts` | One entry per fact: `id`, `veracity`, `statement` (lowercase start, so it fits after "According to X,"), `real_source` and `fake_source`. |

## 6. Speech

At start-up, Piper turns every line the session needs into a WAV file in `audio/`, and each one is then played with the Reachy SDK's `play_sound()`, so the voice comes out of the robot's speaker. All lines use the same voice and settings, so the source phrase is the only difference between conditions. Piper is slow, so each file is kept and reused on later runs; a line is only synthesised again when its text or the voice changes. Run `--prepare` before a study day so every line already exists; otherwise a session generates any missing lines itself before connecting, which can take a minute.

## 7. Other settings in the code

| File | Constant(s) | What it controls |
|---|---|---|
| `main.py` | `VOICE_PATH` | Piper voice file. Any [Piper voice](https://rhasspy.github.io/piper-samples/) works. |
| `speech.py` | `WOBBLE_SCALE` | How much the head sways while Reachy talks, relative to the SDK's default (1.0). |
| `speech.py` | `SENTENCE_PAUSE_SECONDS` | Pause between sentences in a line. |
| `speech.py` | `PRONUNCIATIONS` | Respellings so Piper says words correctly (e.g. "Reachy" as "Reechee"). |
| `gestures.py` | `GREETING_GESTURE`, `FACT_GESTURES` | Recorded gestures from Pollen's emotions library: one during the greeting, and one while each fact is said, picked by the fact's position in the session (never by fact or condition). The program lists every available name if one is wrong. |
| `gestures.py` | `ANTENNA_SCALE` | Gestures are played without turning the body, and with antenna movements scaled by this factor (1.0 is the original amount). |

## 8. Project structure

```
main.py        Command-line arguments, setting up speech and gestures, and error reporting
robot.py       Connecting to Reachy (simulator or robot), checking and fixing the daemon's state first
session.py     Asks for the condition, sets the fact order, runs the session, and puts Reachy to sleep on exit
speech.py      Piper text-to-speech, played through Reachy Mini's speaker with a scaled head sway
gestures.py    Recorded gestures, played without body rotation and with calmer antennas
lines.json     Everything Reachy says
models/        Piper voice files
audio/         Cached WAV files generated by Piper (safe to delete; they are regenerated)
```

## 9. Troubleshooting

Setup problems are reported as a single `Error:` line saying what to do, instead of a traceback.

| Problem | Fix |
|---|---|
| `No Reachy Mini daemon is running on this computer` | Start the simulator (`uv run reachy-mini-daemon --sim`) and wait for `Daemon started successfully`. For the robot, add `--target wireless`. |
| `Can't reach Reachy at http://...:8000` | The computer can't see the robot. Check it is on and on the same Wi-Fi, or pass its IP address with `--host` (the robot's IP is in `GET /api/daemon/status` at `http://reachy-mini.local:8000/docs`). |
| `The daemon is in an error state` / `did not start` / `running without audio` / `the connection failed` | The error says what to restart: the simulator (Ctrl+C in its terminal, then start it again) or the robot (switch it off and on). |
| `Voice file ... not found` | Run the download command it prints (step 2). |
| `Unknown gestures ...` | A name in `FACT_GESTURES` or `GREETING_GESTURE` is wrong; the error lists every valid name. |
| The head doesn't move | Check `GET /api/motors/status` on the `/docs` page says `enabled`, and that your SDK version matches the robot's (`version` in `GET /api/daemon/status`). |