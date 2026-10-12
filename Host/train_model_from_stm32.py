"""Train the command classifier from utterance-level MFCC recordings."""

from pathlib import Path

import numpy as np
import tensorflow as tf
from sklearn.model_selection import train_test_split
from tensorflow.keras import layers, models
from voice_protocol import QUANTIZATION_SCALE

COMMANDS = ["left", "right", "stop", "forward"]
BASE_DIR = Path(__file__).resolve().parent
DATASET_PATH = BASE_DIR / "dataset_stm32"
MODEL_PATH = BASE_DIR / "stm32_model.h5"
SCALER_PATH = BASE_DIR / "stm32_model_scaler.npz"
EPOCHS = 80
BATCH_SIZE = 16
CONTEXT_FRAMES = 11
N_MFCC = 13


def load_utterances(data_path: Path):
    records = []
    for label, command in enumerate(COMMANDS):
        files = sorted((data_path / command).glob("*.npy"))
        print(f"{command}: {len(files)} recording files")
        for path in files:
            values = np.asarray(np.load(path), dtype=np.float32)
            if values.ndim != 2 or values.shape[1] != N_MFCC or len(values) == 0:
                print(f"Skipping incompatible/invalid file (re-record as an utterance matrix): {path}")
                continue
            records.append((values / QUANTIZATION_SCALE, label, path))
    return records


def make_windows(records):
    X, y, groups = [], [], []
    half = CONTEXT_FRAMES // 2
    for sequence, label, path in records:
        # Pad only at utterance boundaries; never construct a window across recordings.
        padded = np.pad(sequence, ((half, half), (0, 0)), mode="edge")
        # One real context window per center frame (stride 2), with edge
        # replication only where an utterance begins or ends.
        starts = range(0, len(sequence), 2)
        for start in starts:
            X.append(padded[start:start + CONTEXT_FRAMES])
            y.append(label)
            groups.append(str(path))
    return np.asarray(X, np.float32), np.asarray(y, np.int64), np.asarray(groups)


def create_model(input_shape, num_classes):
    return models.Sequential([
        layers.Input(shape=input_shape),
        layers.Conv1D(64, 3, activation="relu", padding="same"),
        layers.BatchNormalization(),
        layers.MaxPooling1D(2),
        layers.Dropout(0.1),
        layers.Conv1D(128, 3, activation="relu", padding="same"),
        layers.BatchNormalization(),
        layers.GlobalAveragePooling1D(),
        layers.Dense(64, activation="relu"),
        layers.Dropout(0.1),
        layers.Dense(num_classes, activation="softmax"),
    ])


def main():
    records = load_utterances(DATASET_PATH)
    if not records:
        raise SystemExit(f"No valid recordings found under {DATASET_PATH}.")
    labels = np.asarray([label for _, label, _ in records])
    counts = np.bincount(labels, minlength=len(COMMANDS))
    if np.any(counts < 5):
        missing = [COMMANDS[i] for i, count in enumerate(counts) if count < 5]
        raise SystemExit("Record at least five separate utterances for each class before splitting: " + ", ".join(missing))

    indices = np.arange(len(records))
    trainval_idx, test_idx = train_test_split(
        indices, test_size=0.2, random_state=42, stratify=labels
    )
    train_labels = labels[trainval_idx]
    train_idx, val_idx = train_test_split(
        trainval_idx, test_size=0.25, random_state=43, stratify=train_labels
    )
    train_records = [records[i] for i in train_idx]
    val_records = [records[i] for i in val_idx]
    test_records = [records[i] for i in test_idx]
    X_train, y_train, _ = make_windows(train_records)
    X_val, y_val, _ = make_windows(val_records)
    X_test, y_test, _ = make_windows(test_records)

    # Fit normalization only on training recordings and reuse it during inference.
    mean = X_train.mean(axis=(0, 1), keepdims=True)
    std = X_train.std(axis=(0, 1), keepdims=True)
    std = np.maximum(std, 1e-6)
    X_train = (X_train - mean) / std
    X_val = (X_val - mean) / std
    X_test = (X_test - mean) / std
    np.savez(SCALER_PATH, mean=mean.astype(np.float32), std=std.astype(np.float32))

    model = create_model((CONTEXT_FRAMES, N_MFCC), len(COMMANDS))
    model.compile(
        optimizer=tf.keras.optimizers.Adam(0.001),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )
    callbacks = [
        tf.keras.callbacks.EarlyStopping(patience=12, restore_best_weights=True),
        tf.keras.callbacks.ReduceLROnPlateau(factor=0.5, patience=6, verbose=1),
        tf.keras.callbacks.ModelCheckpoint(str(MODEL_PATH), save_best_only=True),
    ]
    model.fit(
        X_train, y_train, batch_size=BATCH_SIZE, epochs=EPOCHS,
        validation_data=(X_val, y_val), callbacks=callbacks, verbose=1,
    )
    loss, accuracy = model.evaluate(X_test, y_test, verbose=0)
    model.save(MODEL_PATH)
    print(f"Held-out utterance accuracy: {accuracy * 100:.2f}% (loss {loss:.4f})")
    print(f"Saved model: {MODEL_PATH}; normalization: {SCALER_PATH}")


if __name__ == "__main__":
    main()
