#!/usr/bin/env python3
from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any

import yaml
from pyModbusTCP.client import ModbusClient

from weekly_route_test import (
    fmt_pose,
    probe_tcp,
    read_pose_dw,
    read_w,
    reset_alarm,
    wait_live,
    write_pose_dw,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


PHASE_ORDER = [
    ("ready", "ready_pose", "fast_percent"),
    ("hover", "hover_pose", "fast_percent"),
    ("pregrasp", "pregrasp_pose", "pregrasp_percent"),
    ("grasp", "grasp_pose", "grasp_percent"),
    ("lift", "lift_pose", "lift_percent"),
    ("place_hover", "place_hover_pose", "place_percent"),
    ("place", "place_pose", "place_descend_percent"),
    ("place_lift", "place_lift_pose", "place_percent"),
]


def load_phase(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Invalid phase YAML: {path}")
    return data


def move_pose_weekly_style(
    c: ModbusClient,
    *,
    label: str,
    pose: list[int],
    speed: int,
    mode: int,
    acc_raw: int | None,
    posture: int | None,
    user_frame: int | None,
    tool_frame: int | None,
    wait_seconds: float,
    live_interval: float,
) -> None:
    motion_reg = 0x0300
    acc_reg = 0x030A
    speed_reg = 0x0324
    user_frame_reg = 0x033C
    posture_reg = 0x033D
    mode_reg = 0x033E
    tool_frame_reg = 0x033F
    target_base = 0x0330
    inpos_reg = 0x031F
    cur_pose_base = 0x00F0

    speed = max(1, min(int(speed), 100))
    print(f"[STEP] {label}: write target pose to {hex(target_base)}")
    print(f"[STEP] {label}: target_raw={pose}")
    write_pose_dw(c, target_base, pose)

    if acc_raw is not None:
        print(f"[STEP] {label}: set acc_raw={acc_raw}")
        c.write_single_register(acc_reg, max(0, int(acc_raw)))

    if user_frame is not None:
        print(f"[STEP] {label}: set user_frame={user_frame}")
        c.write_single_register(user_frame_reg, int(user_frame))

    if posture is not None:
        print(f"[STEP] {label}: set posture={posture}")
        c.write_single_register(posture_reg, int(posture))

    print(f"[STEP] {label}: set mode={mode}")
    c.write_single_register(mode_reg, int(mode))

    if tool_frame is not None:
        print(f"[STEP] {label}: set tool_frame={tool_frame}")
        c.write_single_register(tool_frame_reg, int(tool_frame))

    print(f"[STEP] {label}: set speed={speed}%")
    c.write_single_register(speed_reg, speed)

    mode_read = read_w(c, mode_reg)
    speed_read = read_w(c, speed_reg)
    acc_read = read_w(c, acc_reg)
    posture_read = read_w(c, posture_reg)
    user_frame_read = read_w(c, user_frame_reg)
    tool_frame_read = read_w(c, tool_frame_reg)
    print(
        f"[READBACK] {label}: mode={mode_read} speed={speed_read}% "
        f"acc={acc_read} posture={posture_read} "
        f"user_frame={user_frame_read} tool_frame={tool_frame_read}"
    )

    print(f"[STEP] {label}: movp p2p (301)")
    c.write_single_register(motion_reg, 301)
    wait_live(c, wait_seconds, live_interval, motion_reg, inpos_reg, cur_pose_base, target_base)


def run(
    *,
    host: str,
    port: int,
    unit_id: int,
    phase_path: Path,
    mode: int,
    acc_raw: int | None,
    posture: int | None,
    user_frame: int | None,
    tool_frame: int | None,
    wait_seconds: float,
    live_interval: float,
    home_before: bool,
    return_ready: bool,
    servo_off: bool,
) -> None:
    phase = load_phase(phase_path)
    speed_cfg = phase.get("speed", {}) or {}

    print(f"[INFO] connect {host}:{port} unit_id={unit_id}")
    if not probe_tcp(host, port, timeout_s=2.0):
        raise RuntimeError(f"TCP not reachable: {host}:{port}")

    c = ModbusClient(host=host, port=port, unit_id=unit_id, auto_open=True)
    c.timeout = 0.8
    if not c.open():
        raise RuntimeError("Modbus open failed")

    try:
        print(f"[INFO] phase={phase_path}")
        print("[STEP] reset alarm")
        reset_alarm(c)

        print("[STEP] servo on")
        c.write_single_register(0x0010, 1)
        wait_live(c, 1.0, live_interval, 0x0300, 0x031F, 0x00F0, 0x0330)

        start_pose = read_pose_dw(c, 0x00F0)
        print(f"[STEP] captured start pose raw={start_pose}")
        print(f"[STEP] captured start pose xyzrpy(mm/deg)={fmt_pose(start_pose)}")

        if home_before:
            print("[STEP] home before route (1405)")
            c.write_single_register(0x0300, 1405)
            wait_live(c, wait_seconds, live_interval, 0x0300, 0x031F, 0x00F0, 0x0330)

        for label, pose_key, speed_key in PHASE_ORDER:
            pose = phase.get(pose_key)
            if not isinstance(pose, list) or len(pose) != 6:
                print(f"[SKIP] {label}: missing {pose_key}")
                continue
            speed = int(speed_cfg.get(speed_key, speed_cfg.get("fast_percent", 80)))
            move_pose_weekly_style(
                c,
                label=label,
                pose=[int(v) for v in pose],
                speed=speed,
                mode=mode,
                acc_raw=acc_raw,
                posture=posture,
                user_frame=user_frame,
                tool_frame=tool_frame,
                wait_seconds=wait_seconds,
                live_interval=live_interval,
            )

        if return_ready:
            ready = phase.get("ready_pose")
            if isinstance(ready, list) and len(ready) == 6:
                move_pose_weekly_style(
                    c,
                    label="return_ready",
                    pose=[int(v) for v in ready],
                    speed=int(speed_cfg.get("fast_percent", 80)),
                    mode=mode,
                    acc_raw=acc_raw,
                    posture=posture,
                    user_frame=user_frame,
                    tool_frame=tool_frame,
                    wait_seconds=wait_seconds,
                    live_interval=live_interval,
                )

        if servo_off:
            print("[STEP] servo off")
            c.write_single_register(0x0010, 2)
        print("[DONE] trapezoid weekly phase test completed")
    finally:
        c.close()
        print("[INFO] connection closed")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Low-level trapezoid phase test using weekly_route_test-style Modbus writes."
    )
    parser.add_argument("--host", default="192.168.1.232")
    parser.add_argument("--port", type=int, default=502)
    parser.add_argument("--unit-id", type=int, default=2)
    parser.add_argument(
        "--phase",
        default=str(PROJECT_ROOT / "data/teach_recordings/trapezoid_v1.merged.phases.yaml"),
        help="Phase YAML to replay as arm-only waypoints.",
    )
    parser.add_argument("--mode", type=int, default=3, help="0x033E value; weekly scripts use 3.")
    parser.add_argument(
        "--acc-raw",
        type=int,
        default=None,
        help="Optional 0x030A acceleration raw value from the Modbus manual.",
    )
    parser.add_argument(
        "--posture",
        type=int,
        default=None,
        help="Optional 0x033D target posture, e.g. 0=RNU/right-hand family.",
    )
    parser.add_argument("--user-frame", type=int, default=None, help="Optional 0x033C UserFrame.")
    parser.add_argument("--tool-frame", type=int, default=None, help="Optional 0x033F ToolFrame.")
    parser.add_argument("--wait-seconds", type=float, default=8.0)
    parser.add_argument("--live-interval", type=float, default=0.5)
    parser.add_argument("--home-before", action="store_true")
    parser.add_argument("--no-return-ready", action="store_true")
    parser.add_argument("--keep-servo-on", action="store_true")
    args = parser.parse_args()

    run(
        host=args.host,
        port=args.port,
        unit_id=args.unit_id,
        phase_path=Path(args.phase),
        mode=args.mode,
        acc_raw=args.acc_raw,
        posture=args.posture,
        user_frame=args.user_frame,
        tool_frame=args.tool_frame,
        wait_seconds=args.wait_seconds,
        live_interval=args.live_interval,
        home_before=args.home_before,
        return_ready=not args.no_return_ready,
        servo_off=not args.keep_servo_on,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
