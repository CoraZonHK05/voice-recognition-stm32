"""Collect labeled, time-ordered MFCC utterances from the STM32."""

from datetime import datetime
from pathlib import Path
import time

import numpy as np
import serial

from voice_protocol import FrameParser

PORT = "COM11"
BAUDRATE = 9600
COMMANDS = ["left", "right", "stop", "forward"]
BASE_DIR = Path(__file__).resolve().parent
SAVE_DIR = BASE_DIR / "dataset_stm32"
ENERGY_THRESHOLD = 500  # Sum of absolute quantized MFCC values; tune on device.
MIN_FRAMES = 11


def get_key():
    import msvcrt

    if msvcrt.kbhit():
        return msvcrt.getch().decode(errors="ignore").lower()
    return None


def main():
    print("MFCC dataset collector")
    print(f"Commands: {COMMANDS}; output: {SAVE_DIR}")
    print("Enter starts/stops a recording, 1-4 selects a command, q exits.")
    try:
        ser = serial.Serial(PORT, BAUDRATE, timeout=0.05)
    except serial.SerialException as exc:
        print(f"Could not open {PORT}: {exc}")
        return

    parser = FrameParser()
    command_index = 0
    recording = False
    frames = []
    saved_count = 0
    try:
        while True:
            key = get_key()
            if key == "q":
                break
            if key and key in "1234" and not recording:
                command_index = int(key) - 1
                print(f"\nSelected {COMMANDS[command_index]}")
            elif key == "\r":
                if not recording:
                    frames = []
                    recording = True
                    print(f"\nRecording {COMMANDS[command_index]}...")
                else:
                    recording = False
                    if len(frames) < MIN_FRAMES:
                        print(f"Discarded: {len(frames)} frames; need at least {MIN_FRAMES}.")
                    else:
                        label = COMMANDS[command_index]
                        folder = SAVE_DIR / label
                        folder.mkdir(parents=True, exist_ok=True)
                        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                        path = folder / f"{label}_{stamp}.npy"
                        np.save(path, np.stack(frames).astype(np.float32))
                        saved_count += 1
                        print(f"Saved {len(frames)} frames to {path} (utterance {saved_count}).")
                    frames = []

            chunk = ser.read(128)
            for mfcc in parser.feed(chunk):
                energy = float(np.abs(mfcc).sum())
                if recording and energy >= ENERGY_THRESHOLD:
                    frames.append(mfcc)
            time.sleep(0.005)
    except KeyboardInterrupt:
        pass
    finally:
        ser.close()
        print("Collector stopped.")


if __name__ == "__main__":
    main()
