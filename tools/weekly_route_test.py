#!/usr/bin/env python3
from __future__ import annotations

import argparse
import socket
import time
from typing import Any

from pyModbusTCP.client import ModbusClient


def int2dra(i: int) -> list[int]:
    if i < 0:
        return [i + 65536]
    if i < 32767:
        return [i]
    return [0]


def int_l_to_dra(i: int) -> list[int]:
    if i < 0:
        f = i + 4294967296
        b = int(bin(f)[0:18], 2)
        a = int(bin(f)[18:], 2)
        return [a, b]
    if i < 65536:
        return [i, 0]
    f = bin(i)
    a = int(f[-16:], 2)
    b = int(f[:-16], 2)
    return [a, b]


def dra_to_int_l(a1: int, b1: int) -> int:
    out = bin(b1)
    if len(out) < 18:
        out = "0b" + out[2:].zfill(16)
    out2 = bin(a1)[2:]
    if len(out2) < 16:
        out2 = out2.zfill(16)
    f = out + out2
    if f[2] == "1":
        return int(f[3:], 2) - 2147483648
    return int(f, 2)


def probe_tcp(host: str, port: int, timeout_s: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except Exception:
        return False


def reset_alarm(c: ModbusClient):
    c.write_multiple_registers(0x0026, int2dra(1))
    c.write_multiple_registers(0x0026, int2dra(256))
    c.write_multiple_registers(0x0027, int2dra(1))
    c.write_multiple_registers(0x0027, int2dra(256))
    c.write_multiple_registers(0x0020, int2dra(1))
    c.write_multiple_registers(0x0020, int2dra(256))


def read_w(c: ModbusClient, reg: int) -> int | None:
    out = c.read_holding_registers(reg, 1)
    if out is None or len(out) != 1:
        return None
    return int(out[0])


def read_pose_dw(c: ModbusClient, base_reg: int) -> list[int] | None:
    regs = c.read_holding_registers(base_reg, 12)
    if regs is None or len(regs) != 12:
        return None
    pose = []
    for i in range(6):
        pose.append(dra_to_int_l(regs[2 * i], regs[2 * i + 1]))
    return pose


def write_pose_dw(c: ModbusClient, base_reg: int, pose: list[int]):
    for i, v in enumerate(pose):
        c.write_multiple_registers(base_reg + 2 * i, int_l_to_dra(int(v)))


def fmt_pose(pose: list[int] | None) -> str:
    if pose is None:
        return "unavailable"
    scaled = [round(v / 1000.0, 3) for v in pose]
    return str(scaled)


def wait_live(
    c: ModbusClient,
    seconds: float,
    interval: float,
    motion_reg: int,
    inpos_reg: int,
    cur_base: int,
    tgt_base: int,
):
    elapsed = 0.0
    while elapsed < seconds:
        step = min(interval, seconds - elapsed)
        time.sleep(step)
        elapsed += step

        motion = read_w(c, motion_reg)
        inpos = read_w(c, inpos_reg)
        cur = read_pose_dw(c, cur_base)
        tgt = read_pose_dw(c, tgt_base)
        print(
            f"[LIVE] t={elapsed:.1f}/{seconds:.1f}s "
            f"motion={motion} inpos={inpos} "
            f"cur_xyzrpy(mm/deg)={fmt_pose(cur)} "
            f"tgt_xyzrpy(mm/deg)={fmt_pose(tgt)}"
        )


def run_weekly_route(
    host: str,
    port: int,
    unit_id: int,
    speed_percent: int,
    wait_seconds: float,
    live_interval: float,
    target_pose: list[int],
    home_pose: list[int],
    home_only: bool,
    move_home_pose: bool,
    return_to_start: bool,
    skip_home_before: bool,
    skip_home_after: bool,
):
    print(f"[INFO] connect {host}:{port} unit_id={unit_id}")
    if not probe_tcp(host, port, timeout_s=2.0):
        raise RuntimeError(f"TCP not reachable: {host}:{port}")

    c = ModbusClient(host=host, port=port, unit_id=unit_id, auto_open=True)
    c.timeout = 0.8
    if not c.open():
        raise RuntimeError("Modbus open failed")

    motion_reg = 0x0300
    speed_reg = 0x0324
    mode_reg = 0x033E
    target_base = 0x0330
    servo_reg = 0x0010
    inpos_reg = 0x031F
    cur_pose_base = 0x00F0

    try:
        print("[STEP] reset alarm")
        reset_alarm(c)

        print("[STEP] servo on")
        c.write_single_register(servo_reg, 1)
        wait_live(c, 1.0, live_interval, motion_reg, inpos_reg, cur_pose_base, target_base)

        start_pose = read_pose_dw(c, cur_pose_base)
        print(f"[STEP] captured start pose raw={start_pose}")
        print(f"[STEP] captured start pose xyzrpy(mm/deg)={fmt_pose(start_pose)}")

        if home_only:
            print("[STEP] home only (1405)")
            c.write_single_register(motion_reg, 1405)
            wait_live(c, wait_seconds, live_interval, motion_reg, inpos_reg, cur_pose_base, target_base)
            print("[STEP] servo off")
            c.write_single_register(servo_reg, 2)
            print("[DONE] home-only completed")
            return

        if move_home_pose:
            print(f"[STEP] write home pose to {hex(target_base)}")
            print(f"[STEP] home_pose_raw={home_pose}")
            write_pose_dw(c, target_base, home_pose)
            print("[STEP] set mode=3 (joint)")
            c.write_single_register(mode_reg, 3)
            print(f"[STEP] set speed={speed_percent}%")
            c.write_single_register(speed_reg, speed_percent)
            print("[STEP] movp p2p (301) to home pose")
            c.write_single_register(motion_reg, 301)
            wait_live(c, wait_seconds, live_interval, motion_reg, inpos_reg, cur_pose_base, target_base)
            print("[STEP] servo off")
            c.write_single_register(servo_reg, 2)
            print("[DONE] move-home-pose completed")
            return

        if not skip_home_before:
            print("[STEP] home (1405)")
            c.write_single_register(motion_reg, 1405)
            wait_live(c, wait_seconds, live_interval, motion_reg, inpos_reg, cur_pose_base, target_base)
        else:
            print("[STEP] skip home before target move")

        print(f"[STEP] write target pose to {hex(target_base)}")
        print(f"[STEP] target_raw={target_pose}")
        write_pose_dw(c, target_base, target_pose)

        print("[STEP] set mode=3 (joint)")
        c.write_single_register(mode_reg, 3)

        print(f"[STEP] set speed={speed_percent}%")
        c.write_single_register(speed_reg, speed_percent)

        print("[STEP] movp p2p (301)")
        c.write_single_register(motion_reg, 301)
        wait_live(c, wait_seconds, live_interval, motion_reg, inpos_reg, cur_pose_base, target_base)

        if not skip_home_after:
            print("[STEP] home (1405)")
            c.write_single_register(motion_reg, 1405)
            wait_live(c, wait_seconds, live_interval, motion_reg, inpos_reg, cur_pose_base, target_base)
        else:
            print("[STEP] skip home after target move")

        print("[STEP] servo off")
        c.write_single_register(servo_reg, 2)

        print("[DONE] weekly route test completed")

        if return_to_start and start_pose is not None:
            print(f"[STEP] return to start pose -> {start_pose}")
            c.write_single_register(servo_reg, 1)
            wait_live(c, 1.0, live_interval, motion_reg, inpos_reg, cur_pose_base, target_base)
            write_pose_dw(c, target_base, start_pose)
            c.write_single_register(mode_reg, 3)
            c.write_single_register(speed_reg, speed_percent)
            c.write_single_register(motion_reg, 301)
            wait_live(c, wait_seconds, live_interval, motion_reg, inpos_reg, cur_pose_base, target_base)
            c.write_single_register(servo_reg, 2)
            print("[DONE] returned to start pose")
        elif return_to_start:
            print("[WARN] return-to-start requested but failed to read start pose; skipped")
    finally:
        c.close()
        print("[INFO] connection closed")


def parse_pose_csv(s: str) -> list[int]:
    vals = [x.strip() for x in s.split(",") if x.strip()]
    if len(vals) != 6:
        raise ValueError("--target-pose requires 6 comma-separated integers")
    return [int(v) for v in vals]


def main() -> int:
    parser = argparse.ArgumentParser(description="Standalone weekly route tester with live Modbus outputs")
    parser.add_argument("--host", default="127.0.0.1", help="Robot host or tunnel host")
    parser.add_argument("--port", type=int, default=1502, help="Modbus port")
    parser.add_argument("--unit-id", type=int, default=2)
    parser.add_argument("--speed", type=int, default=30)
    parser.add_argument("--wait-seconds", type=float, default=20.0)
    parser.add_argument("--live-interval", type=float, default=0.5)
    parser.add_argument(
        "--target-pose",
        type=str,
        default="644000,269456,344000,0,-89999,179999",
        help="6 ints: x,y,z,rx,ry,rz (um/0.001deg)",
    )
    parser.add_argument(
        "--home-pose",
        type=str,
        default="444000,0,744000,0,-89999,179999",
        help="Home pose as 6 ints: x,y,z,rx,ry,rz (um/0.001deg)",
    )
    parser.add_argument(
        "--home-only",
        action="store_true",
        help="Only send homing command 1405, then stop.",
    )
    parser.add_argument(
        "--move-home-pose",
        action="store_true",
        help="Move to --home-pose using GO 301, then stop.",
    )
    parser.add_argument(
        "--return-to-start",
        action="store_true",
        help="Capture current pose at start and move back to it at the end.",
    )
    parser.add_argument(
        "--skip-home-before",
        action="store_true",
        help="Do not send 1405 before moving to target pose.",
    )
    parser.add_argument(
        "--skip-home-after",
        action="store_true",
        help="Do not send 1405 after moving to target pose.",
    )

    args = parser.parse_args()
    target_pose = parse_pose_csv(args.target_pose)
    home_pose = parse_pose_csv(args.home_pose)

    if args.home_only and args.move_home_pose:
        raise SystemExit("Choose only one of --home-only or --move-home-pose")

    run_weekly_route(
        host=args.host,
        port=args.port,
        unit_id=args.unit_id,
        speed_percent=args.speed,
        wait_seconds=args.wait_seconds,
        live_interval=args.live_interval,
        target_pose=target_pose,
        home_pose=home_pose,
        home_only=args.home_only,
        move_home_pose=args.move_home_pose,
        return_to_start=args.return_to_start,
        skip_home_before=args.skip_home_before,
        skip_home_after=args.skip_home_after,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
