#!/usr/bin/env python3
"""
Teach Mode Recorder - Record and replay arm waypoints.

Usage:
    # Record: manually position arm, press keys to save waypoints
    python tools/teach_recorder.py --name pick_scissors_v1 \\
        --host 127.0.0.1 --port 1502

    # Replay a saved recording
    python tools/teach_recorder.py --replay pick_scissors_v1 \\
        --host 127.0.0.1 --port 1502

    # List recordings
    python tools/teach_recorder.py --list

Keys during recording:
    SPACE  = save current pose as waypoint
    g      = mark gripper CLOSE at this waypoint
    o      = mark gripper OPEN at this waypoint
    s      = change speed (prompts for value)
    q      = stop and save
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils import load_config


_GRIPPER_ACTIVE_BASE_URL: str | None = None


def _gripper_endpoint_candidates(demo_cfg: dict) -> list[tuple[str, str]]:
    grip = demo_cfg.get("gripper", {})
    candidates: list[tuple[str, str]] = []
    seen: set[tuple[str, int]] = set()

    for idx, item in enumerate(grip.get("endpoints", [])):
        if not isinstance(item, dict):
            continue
        host = str(item.get("host", "")).strip()
        port = int(item.get("port", grip.get("agx_port", 5000)))
        if not host:
            continue
        key = (host, port)
        if key in seen:
            continue
        seen.add(key)
        label = str(item.get("label", f"gripper_{idx + 1}"))
        candidates.append((label, f"http://{host}:{port}"))

    host = str(grip.get("agx_ip", "")).strip()
    port = int(grip.get("agx_port", 5000))
    if host and (host, port) not in seen:
        candidates.append(("gripper_fallback", f"http://{host}:{port}"))
    return candidates


def _gripper_request(
    demo_cfg: dict,
    method: str,
    path: str,
    *,
    payload: dict | None = None,
    timeout: float = 1.0,
):
    global _GRIPPER_ACTIVE_BASE_URL

    import requests

    candidates = _gripper_endpoint_candidates(demo_cfg)
    if _GRIPPER_ACTIVE_BASE_URL:
        candidates = [("gripper_active", _GRIPPER_ACTIVE_BASE_URL)] + [
            item for item in candidates if item[1] != _GRIPPER_ACTIVE_BASE_URL
        ]

    last_error = "no gripper endpoints configured"
    for label, base_url in candidates:
        try:
            if method == "GET":
                resp = requests.get(f"{base_url}{path}", timeout=timeout)
            else:
                resp = requests.post(f"{base_url}{path}", json=payload, timeout=timeout)
            resp.raise_for_status()
            _GRIPPER_ACTIVE_BASE_URL = base_url
            return resp
        except Exception as e:
            last_error = f"{label}: {e}"
            if base_url == _GRIPPER_ACTIVE_BASE_URL:
                _GRIPPER_ACTIVE_BASE_URL = None
    raise RuntimeError(last_error)


def _gripper_base_url(demo_cfg: dict) -> str | None:
    grip = demo_cfg.get("gripper", {})
    if not grip.get("enabled", False):
        return None
    candidates = _gripper_endpoint_candidates(demo_cfg)
    if _GRIPPER_ACTIVE_BASE_URL:
        return _GRIPPER_ACTIVE_BASE_URL
    return candidates[0][1] if candidates else None


def _gripper_state(demo_cfg: dict) -> dict | None:
    base_url = _gripper_base_url(demo_cfg)
    if not base_url:
        return None
    try:
        resp = _gripper_request(demo_cfg, "GET", "/state", timeout=1.0)
        data = resp.json()
        return data if isinstance(data, dict) else None
    except Exception as e:
        print(f"\n  Gripper state read failed: {e}")
        return None


def _gripper_set_position(demo_cfg: dict, positions: list[int]) -> bool:
    base_url = _gripper_base_url(demo_cfg)
    if not base_url:
        return False
    try:
        _gripper_request(
            demo_cfg,
            "POST",
            "/set_position",
            payload={"positions": [int(v) for v in positions]},
            timeout=2.0,
        )
        return True
    except Exception as e:
        print(f"  Gripper set_position error: {e}")
        return False


def _positions_from_waypoint(wp: dict) -> list[int] | None:
    direct = wp.get("gripper_pos")
    if isinstance(direct, list) and len(direct) == 3:
        try:
            return [int(v) for v in direct]
        except (TypeError, ValueError):
            return None

    matched = wp.get("matched_external")
    if isinstance(matched, dict):
        row = matched.get("row")
        if isinstance(row, dict):
            values = [row.get("pos1"), row.get("pos2"), row.get("pos3")]
            if all(v is not None for v in values):
                try:
                    return [int(float(v)) for v in values]
                except (TypeError, ValueError):
                    return None
    return None


def _replay_gripper_timeline(demo_cfg: dict, timeline: list[dict], replay_start: float) -> None:
    last_positions = None
    for sample in timeline:
        positions = sample.get("positions")
        if not isinstance(positions, list) or len(positions) != 3:
            continue
        try:
            positions = [int(v) for v in positions]
            target_sec = max(0.0, float(sample.get("t_ms", 0)) / 1000.0)
        except (TypeError, ValueError):
            continue
        wait_sec = target_sec - (time.time() - replay_start)
        if wait_sec > 0:
            time.sleep(wait_sec)
        if positions == last_positions:
            continue
        _gripper_set_position(demo_cfg, positions)
        last_positions = positions


def _wait_until_replay_t(replay_start: float, target_ms) -> None:
    try:
        target_sec = max(0.0, float(target_ms) / 1000.0)
    except (TypeError, ValueError):
        return

    wait_sec = target_sec - (time.time() - replay_start)
    if wait_sec > 0:
        time.sleep(wait_sec)


def get_key_nonblocking() -> str:
    """Read a single keypress without blocking (Unix only)."""
    import select
    import termios
    import tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        if select.select([sys.stdin], [], [], 0.1)[0]:
            return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return ""


def record(name: str, host: str, port: int, unit_id: int):
    """Record arm waypoints interactively."""
    from src.controller import ArmController

    demo_cfg = load_config("demo_config.yaml")
    save_dir = PROJECT_ROOT / demo_cfg.get("teach", {}).get(
        "save_dir", "data/teach_recordings")
    save_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*50}")
    print(f"Teach Recorder: {name}")
    print(f"{'='*50}")
    print(f"Connecting to {host}:{port} ...")

    arm = ArmController(host=host, port=port, unit_id=unit_id)
    if not arm.connect():
        print("ERROR: Cannot connect to arm")
        return

    print("Connected!")
    print("\nKeys:")
    print("  SPACE = save waypoint")
    print("  g     = save waypoint + gripper CLOSE")
    print("  o     = save waypoint + gripper OPEN")
    print("  s     = change speed")
    print("  q     = stop and save")
    print()

    waypoints = []
    current_speed = 30
    start_time = time.time()

    try:
        while True:
            # Read current pose
            try:
                raw = arm.read_current_pose()
                if raw and len(raw) >= 6:
                    mm_deg = [v / 1000.0 for v in raw]
                    pose_str = (f"X={mm_deg[0]:8.2f} Y={mm_deg[1]:8.2f} "
                                f"Z={mm_deg[2]:8.2f}")
                    sys.stdout.write(f"\r  {pose_str} | "
                                     f"WP:{len(waypoints)} SPD:{current_speed}% ")
                    sys.stdout.flush()
            except Exception:
                pass

            key = get_key_nonblocking()
            if not key:
                continue

            if key == "q":
                print("\n\nStopping...")
                break
            elif key == "s":
                print()
                try:
                    new_speed = int(input("  New speed %: "))
                    current_speed = max(1, min(100, new_speed))
                    print(f"  Speed set to {current_speed}%")
                except (ValueError, EOFError):
                    pass
            elif key in (" ", "g", "o"):
                gripper = "none"
                if key == "g":
                    gripper = "close"
                elif key == "o":
                    gripper = "open"

                try:
                    raw = arm.read_current_pose()
                except Exception:
                    raw = None

                if raw and len(raw) >= 6:
                    wp = {
                        "t_ms": int((time.time() - start_time) * 1000),
                        "pose": list(raw),
                        "gripper": gripper,
                        "speed": current_speed,
                    }
                    grip_state = _gripper_state(demo_cfg)
                    if isinstance(grip_state, dict):
                        current_pos = grip_state.get("current_pos")
                        if isinstance(current_pos, list) and len(current_pos) == 3:
                            try:
                                wp["gripper_pos"] = [int(v) for v in current_pos]
                            except (TypeError, ValueError):
                                pass
                        if "server_time_unix" in grip_state:
                            wp["gripper_server_time_unix"] = grip_state.get("server_time_unix")
                        if "tactile_data" in grip_state:
                            wp["tactile_data"] = grip_state.get("tactile_data")
                    waypoints.append(wp)
                    mm = [v / 1000.0 for v in raw]
                    extra = f" grip_pos={wp['gripper_pos']}" if "gripper_pos" in wp else ""
                    print(f"\n  Waypoint {len(waypoints)}: "
                          f"[{mm[0]:.1f}, {mm[1]:.1f}, {mm[2]:.1f}] "
                          f"gripper={gripper} speed={current_speed}%{extra}")
                else:
                    print("\n  Cannot read pose!")

    except KeyboardInterrupt:
        print("\n\nInterrupted")

    arm.disconnect()

    if not waypoints:
        print("No waypoints recorded.")
        return

    data = {
        "name": name,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "start_unix": start_time,
        "waypoints": waypoints,
    }
    path = save_dir / f"{name}.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"\nSaved {len(waypoints)} waypoints to {path}")


def replay(name: str, host: str, port: int, unit_id: int):
    """Replay a recorded waypoint sequence."""
    from src.controller import ArmController

    demo_cfg = load_config("demo_config.yaml")
    save_dir = PROJECT_ROOT / demo_cfg.get("teach", {}).get(
        "save_dir", "data/teach_recordings")
    path = save_dir / f"{name}.json"

    if not path.exists():
        print(f"Recording not found: {path}")
        return

    with open(path) as f:
        data = json.load(f)

    waypoints = data.get("waypoints", [])
    print(f"\nReplaying: {name} ({len(waypoints)} waypoints)")

    # Safety check
    safety = demo_cfg.get("safety_boundary", {})
    for i, wp in enumerate(waypoints):
        pose = wp["pose"]
        for axis_idx, axis in enumerate(["x", "y", "z"]):
            lo = safety.get(f"{axis}_min", -999999999)
            hi = safety.get(f"{axis}_max", 999999999)
            if pose[axis_idx] < lo or pose[axis_idx] > hi:
                print(f"SAFETY REJECT: Waypoint {i+1} "
                      f"{axis.upper()}={pose[axis_idx]} outside [{lo},{hi}]")
                return

    arm = ArmController(host=host, port=port, unit_id=unit_id)
    if not arm.connect():
        print("ERROR: Cannot connect to arm")
        return

    try:
        arm.reset_alarms()
        arm.servo_on()
        timeline = data.get("external_timeline", [])
        timeline_thread = None
        replay_start = time.time()
        use_original_timing = all("t_ms" in wp for wp in waypoints)
        timeline_end_sec = 0.0
        if isinstance(timeline, list) and timeline:
            try:
                timeline_end_sec = max(
                    max(0.0, float(sample.get("t_ms", 0)) / 1000.0)
                    for sample in timeline
                )
            except (TypeError, ValueError):
                timeline_end_sec = 0.0
            print(f"  -> Streaming external gripper timeline ({len(timeline)} samples)")
            import threading
            timeline_thread = threading.Thread(
                target=_replay_gripper_timeline,
                args=(demo_cfg, timeline, replay_start),
                daemon=True,
            )
            timeline_thread.start()
        if use_original_timing:
            print(f"  -> Replay follows recorded timing span ~{float(waypoints[-1].get('t_ms', 0)) / 1000.0:.1f}s")

        for i, wp in enumerate(waypoints):
            if use_original_timing:
                _wait_until_replay_t(replay_start, wp.get("t_ms", 0))
            pose = wp["pose"]
            speed = wp.get("speed", 30)
            gripper = wp.get("gripper", "none")
            gripper_pos = _positions_from_waypoint(wp)
            mm = [v / 1000.0 for v in pose[:3]]
            print(f"  [{i+1}/{len(waypoints)}] "
                  f"[{mm[0]:.1f}, {mm[1]:.1f}, {mm[2]:.1f}] "
                  f"speed={speed}% gripper={gripper}")
            arm.move_to(pose, speed=speed, wait_seconds=2.0)

            if timeline_thread is not None:
                continue
            if gripper_pos is not None:
                print(f"  -> Gripper POSITION {gripper_pos}")
                _gripper_set_position(demo_cfg, gripper_pos)
            elif gripper == "close":
                print("  -> Gripper CLOSE")
                # Send gripper command via HTTP if configured
                _gripper_http(demo_cfg, "close")
            elif gripper == "open":
                print("  -> Gripper OPEN")
                _gripper_http(demo_cfg, "open")
            elif gripper not in {"", "none", None}:
                print(f"  -> Gripper CMD {gripper}")
                _gripper_http(demo_cfg, str(gripper), raw=True)

        if timeline_thread is not None:
            remaining_sec = timeline_end_sec - (time.time() - replay_start)
            timeline_thread.join(timeout=max(0.0, remaining_sec) + 2.0)
        arm.servo_off()
        print("\nReplay complete!")

    except Exception as e:
        print(f"\nReplay error: {e}")
        try:
            arm.servo_off()
        except Exception:
            pass
    finally:
        arm.disconnect()


def _gripper_http(demo_cfg: dict, action: str, *, raw: bool = False):
    """Send gripper command via AGX HTTP API."""
    grip = demo_cfg.get("gripper", {})
    if not grip.get("enabled", False):
        return
    try:
        if raw:
            cmd = action
            delay = 0.0
        else:
            cmd = grip.get("close_command" if action == "close" else "open_command", action[0])
            delay = grip.get("close_delay_s" if action == "close" else "open_delay_s", 1.0)
        _gripper_request(
            demo_cfg,
            "POST",
            "/command",
            payload={"action": cmd},
            timeout=2.0,
        )
        if delay > 0:
            time.sleep(delay)
    except Exception as e:
        print(f"  Gripper HTTP error: {e}")


def list_recordings():
    """List all saved recordings."""
    demo_cfg = load_config("demo_config.yaml")
    save_dir = PROJECT_ROOT / demo_cfg.get("teach", {}).get(
        "save_dir", "data/teach_recordings")

    if not save_dir.exists():
        print("No recordings directory found.")
        return

    files = sorted(save_dir.glob("*.json"))
    if not files:
        print("No recordings found.")
        return

    print(f"\nRecordings in {save_dir}:")
    print(f"{'Name':<30} {'Waypoints':>10} {'Created':<20}")
    print("-" * 62)
    for p in files:
        try:
            with open(p) as f:
                data = json.load(f)
            name = data.get("name", p.stem)
            count = len(data.get("waypoints", []))
            created = data.get("created", "?")
            print(f"{name:<30} {count:>10} {created:<20}")
        except Exception:
            print(f"{p.stem:<30} {'error':>10}")


def main():
    parser = argparse.ArgumentParser(description="Teach Mode Recorder")
    parser.add_argument("--name", type=str, help="Recording name")
    parser.add_argument("--replay", type=str, help="Replay a recording by name")
    parser.add_argument("--list", action="store_true", help="List recordings")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1502)
    parser.add_argument("--unit-id", type=int, default=2)
    args = parser.parse_args()

    if args.list:
        list_recordings()
    elif args.replay:
        replay(args.replay, args.host, args.port, args.unit_id)
    elif args.name:
        record(args.name, args.host, args.port, args.unit_id)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
