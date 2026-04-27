"""
Compose panel PNG frame captures into MP4 files.

This is intended for deferred export after a panel recording session is finished.
Input should be a session under:
    data/panel_recordings/<session_id>/

Expected structure per panel:
    <session_id>/<panel_id>/frames/*.png
    <session_id>/<panel_id>/frame_manifest.csv

The script can either:
- use frame index order (default), or
- use genlock timeline fields from frame_manifest.csv when available.

Examples:
    python tools/panel_frames_to_mp4.py --session-id 2026-04-24T11-30-00-000Z

    python tools/panel_frames_to_mp4.py \
      --session-dir data/panel_recordings/2026-04-24T11-30-00-000Z \
      --fps 4 --prefer-genlock
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import cv2

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PANEL_RECORDINGS_DIR = PROJECT_ROOT / "data" / "panel_recordings"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compose panel frame captures into MP4")
    parser.add_argument("--session-id", default="", help="Recording session id under data/panel_recordings")
    parser.add_argument("--session-dir", default="", help="Explicit session directory path")
    parser.add_argument("--fps", type=float, default=4.0, help="Output mp4 FPS")
    parser.add_argument(
        "--prefer-genlock",
        action="store_true",
        help="Use client_elapsed_ms ordering from frame_manifest.csv when available",
    )
    parser.add_argument(
        "--keep-aspect-resize",
        action="store_true",
        help="Resize frames to first frame size before writing",
    )
    return parser.parse_args()


def resolve_session_dir(args: argparse.Namespace) -> Path:
    if args.session_dir:
        session_dir = Path(args.session_dir)
        if not session_dir.is_absolute():
            session_dir = (Path.cwd() / session_dir).resolve()
        else:
            session_dir = session_dir.resolve()
    elif args.session_id:
        session_dir = (PANEL_RECORDINGS_DIR / args.session_id).resolve()
    else:
        raise SystemExit("Provide one of --session-id or --session-dir")

    if not session_dir.exists() or not session_dir.is_dir():
        raise SystemExit(f"Session dir not found: {session_dir}")
    return session_dir


def read_manifest_order(panel_dir: Path, prefer_genlock: bool) -> list[Path]:
    manifest = panel_dir / "frame_manifest.csv"
    frames_dir = panel_dir / "frames"
    if not manifest.exists() or not prefer_genlock:
        return sorted(frames_dir.glob("*.png"))

    rows: list[tuple[float, int, Path]] = []
    with open(manifest, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = row.get("filename", "")
            if not name:
                continue
            frame_path = frames_dir / name
            if not frame_path.exists():
                continue
            try:
                elapsed_ms = float(row.get("client_elapsed_ms", "nan"))
            except ValueError:
                elapsed_ms = float("nan")
            try:
                frame_idx = int(row.get("frame_index", "0"))
            except ValueError:
                frame_idx = 0
            rows.append((elapsed_ms, frame_idx, frame_path))

    if not rows:
        return sorted(frames_dir.glob("*.png"))

    # Stable fallback to frame index when elapsed_ms is missing/invalid.
    rows.sort(key=lambda item: (item[0] if item[0] == item[0] else float("inf"), item[1]))
    return [item[2] for item in rows]


def write_panel_video(panel_dir: Path, fps: float, prefer_genlock: bool, keep_aspect_resize: bool) -> dict:
    panel_id = panel_dir.name
    frames = read_manifest_order(panel_dir, prefer_genlock)
    if not frames:
        return {"panel_id": panel_id, "ok": False, "error": "no frames"}

    first = cv2.imread(str(frames[0]))
    if first is None:
        return {"panel_id": panel_id, "ok": False, "error": "cannot read first frame"}

    width = int(first.shape[1])
    height = int(first.shape[0])
    width = max(2, width - (width % 2))
    height = max(2, height - (height % 2))

    out_path = panel_dir.parent / f"{panel_id}.mp4"
    writer = cv2.VideoWriter(
        str(out_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        max(1.0, float(fps)),
        (width, height),
    )
    if not writer.isOpened():
        return {"panel_id": panel_id, "ok": False, "error": "cannot open mp4 writer"}

    written = 0
    for frame_path in frames:
        frame = cv2.imread(str(frame_path))
        if frame is None:
            continue
        if frame.shape[1] != width or frame.shape[0] != height:
            if not keep_aspect_resize:
                continue
            frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
        writer.write(frame)
        written += 1
    writer.release()

    if written <= 0:
        return {"panel_id": panel_id, "ok": False, "error": "no readable frames"}

    return {
        "panel_id": panel_id,
        "ok": True,
        "path": str(out_path.relative_to(PROJECT_ROOT)),
        "frames": written,
        "width": width,
        "height": height,
        "ordered_by": "genlock" if prefer_genlock else "frame_index",
    }


def main() -> None:
    args = parse_args()
    session_dir = resolve_session_dir(args)

    panel_dirs = sorted(path for path in session_dir.iterdir() if path.is_dir() and (path / "frames").exists())
    if not panel_dirs:
        raise SystemExit(f"No panel frame dirs found in: {session_dir}")

    ok = []
    errors = []
    for panel_dir in panel_dirs:
        result = write_panel_video(panel_dir, args.fps, args.prefer_genlock, args.keep_aspect_resize)
        if result.get("ok"):
            ok.append(result)
            print(f"[OK] {result['panel_id']}: {result['path']} ({result['frames']} frames)")
        else:
            errors.append(result)
            print(f"[ERR] {result['panel_id']}: {result.get('error', 'unknown error')}")

    print("\nSummary")
    print(f"session: {session_dir}")
    print(f"written: {len(ok)}")
    print(f"errors: {len(errors)}")

    if errors:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
