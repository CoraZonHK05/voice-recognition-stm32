"""Receive serial MFCC frames and classify four voice commands."""

from pathlib import Path

import numpy as np
import serial
import tensorflow as tf

from voice_protocol import FrameParser, QUANTIZATION_SCALE

PORT = "COM11"
BAUDRATE = 9600
COMMANDS = ["left", "right", "stop", "forward"]
CONTEXT_FRAMES = 11
ENERGY_THRESHOLD = 500
CONFIDENCE_THRESHOLD = 0.7
BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "stm32_model.h5"
SCALER_PATH = BASE_DIR / "stm32_model_scaler.npz"


class MFCCRecognizer:
    def __init__(self):
        self.model = tf.keras.models.load_model(MODEL_PATH)
        scaler = np.load(SCALER_PATH)
        self.mean = scaler["mean"]
        self.std = np.maximum(scaler["std"], 1e-6)
        self.frames = []

    @staticmethod
    def is_speech(mfcc):
        # Match the collector's threshold in quantized units.
        return float(np.abs(mfcc).sum()) >= ENERGY_THRESHOLD

    def push(self, mfcc):
        if not self.is_speech(mfcc):
            self.frames.clear()
            return None, 0.0
        self.frames.append(mfcc / QUANTIZATION_SCALE)
        if len(self.frames) < CONTEXT_FRAMES:
            return None, 0.0
        self.frames = self.frames[-CONTEXT_FRAMES:]
        window = np.asarray(self.frames, np.float32)[None, ...]
        window = (window - self.mean) / self.std
        probs = self.model.predict(window, verbose=0)[0]
        idx = int(np.argmax(probs))
        confidence = float(probs[idx])
        if confidence < CONFIDENCE_THRESHOLD:
            return "unknown", confidence
        return COMMANDS[idx], confidence


def main():
    if not MODEL_PATH.is_file() or not SCALER_PATH.is_file():
        raise SystemExit("Train the model first; expected stm32_model.h5 and stm32_model_scaler.npz beside this script.")
    recognizer = MFCCRecognizer()
    parser = FrameParser()
    frame_count = 0
    try:
        with serial.Serial(PORT, BAUDRATE, timeout=0.2) as ser:
            print(f"Listening on {PORT} at {BAUDRATE} baud")
            while True:
                for mfcc in parser.feed(ser.read(128)):
                    frame_count += 1
                    command, confidence = recognizer.push(mfcc)
                    if command is not None:
                        print(f"{command}: {confidence:.2f} (frame {frame_count})")
    except KeyboardInterrupt:
        print("Stopped.")
    except serial.SerialException as exc:
        print(f"Serial error: {exc}")


if __name__ == "__main__":
    main()
