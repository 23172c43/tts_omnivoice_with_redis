"""Test streaming vs non-streaming, luu file de kiem tra."""

import io
import soundfile as sf
from app.services.omnivoice_service import (
    get_model,
    generate_speech,
    generate_streaming,
    get_voice_config,
)

TEXT = "Xin chào các bạn. Đây là bài test streaming. Tôi hy vọng các bạn thích giọng nói này."
VOICE_ID = "001"
OUTPUT_DIR = "test_output"

import os
os.makedirs(OUTPUT_DIR, exist_ok=True)


def test_non_streaming():
    """Generate full audio, save 1 file."""
    print("=" * 40)
    print("NON-STREAMING")
    print("=" * 40)

    result = generate_speech(text=TEXT, voice_id=VOICE_ID)
    print(f"Status: {result['status']}")
    if result.get("audio_buffer"):
        path = f"{OUTPUT_DIR}/non_streaming.wav"
        with open(path, "wb") as f:
            f.write(result["audio_buffer"])
        print(f"Saved: {path} ({len(result['audio_buffer'])} bytes)")
    else:
        print(f"Error: {result.get('message')}")
    print()


def test_streaming():
    """Generate chunks, save each chunk + merge."""
    print("=" * 40)
    print("STREAMING")
    print("=" * 40)

    model = get_model()
    voice_config = get_voice_config(VOICE_ID)

    chunks = []
    for i, chunk in enumerate(generate_streaming(TEXT, model, VOICE_ID)):
        path = f"{OUTPUT_DIR}/streaming_chunk_{i}.wav"
        with open(path, "wb") as f:
            f.write(chunk)
        print(f"Chunk {i}: {path} ({len(chunk)} bytes)")
        chunks.append(chunk)

    # Merge all chunks
    if chunks:
        all_audio = []
        sample_rate = 24000
        for chunk in chunks:
            data, sr = sf.read(io.BytesIO(chunk))
            all_audio.append(data)

        import numpy as np
        merged = np.concatenate(all_audio)
        merged_path = f"{OUTPUT_DIR}/streaming_merged.wav"
        sf.write(merged_path, merged, sample_rate)
        print(f"Merged: {merged_path} ({len(merged)/sample_rate:.1f}s)")
    print()


if __name__ == "__main__":
    test_non_streaming()
    test_streaming()
    print("Done! Check test_output/ folder.")
