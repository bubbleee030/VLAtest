"""
Probe OpenCV camera indices on Windows.

Usage:
    python tools/probe_cameras.py
    python tools/probe_cameras.py --max-index 15
"""

from __future__ import annotations

import argparse

import cv2


def probe_backend(name: str, backend: int, max_index: int) -> list[dict]:
    rows: list[dict] = []
    print(f"=== {name} ===")
    for index in range(max_index + 1):
        cap = cv2.VideoCapture(index, backend)
        opened = cap.isOpened()
        ok, frame = cap.read()
        shape = None if frame is None else tuple(frame.shape)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        cap.release()

        row = {
            "index": index,
            "opened": opened,
            "ok": ok,
            "shape": shape,
            "width": width,
            "height": height,
            "fps": fps,
        }
        rows.append(row)
        print(
            f"{index}: opened={opened} ok={ok} "
            f"shape={shape} size={width}x{height} fps={fps:.1f}"
        )
    print()
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe local camera indices with OpenCV")
    parser.add_argument("--max-index", type=int, default=10, help="highest camera index to test")
    args = parser.parse_args()

    backends = [
        ("DSHOW", cv2.CAP_DSHOW),
        ("MSMF", cv2.CAP_MSMF),
        ("ANY", cv2.CAP_ANY),
    ]

    all_rows: dict[str, list[dict]] = {}
    for name, backend in backends:
        try:
            all_rows[name] = probe_backend(name, backend, args.max_index)
        except Exception as exc:
            print(f"=== {name} ===")
            print(f"probe failed: {exc}\n")

    hits: list[str] = []
    for name, rows in all_rows.items():
        for row in rows:
            if row["opened"] or row["ok"]:
                hits.append(
                    f"{name} index {row['index']} "
                    f"shape={row['shape']} size={row['width']}x{row['height']}"
                )

    print("=== Summary ===")
    if hits:
        for hit in hits:
            print(hit)
    else:
        print("No camera indices opened successfully.")
        print("If your demo server is already running, stop it first and probe again.")


if __name__ == "__main__":
    main()
