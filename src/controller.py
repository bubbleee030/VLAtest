"""
Modbus arm controller for the robot arm.

Handles connection (direct or via SSH tunnel), servo on/off,
alarm reset, P2P motion, and live pose reading.

Usage:
    from src.controller import ArmController
    arm = ArmController()       # Uses config/modbus_config.yaml
    arm.connect()
    arm.servo_on()
    arm.move_to([500000, 0, 400000, 0, -89999, 179999], speed=20)
    arm.go_home()
    arm.servo_off()
    arm.disconnect()
"""

import socket
import threading
import time
from src.utils import (
    load_config, int_to_register, int32_to_registers,
    read_current_pose_from_registers, pose_to_mm_deg,
)

try:
    from pyModbusTCP.client import ModbusClient
except ImportError:
    ModbusClient = None
    print("[WARN] pyModbusTCP not installed. Run: pip install pyModbusTCP")


class ArmController:
    """
    Robot arm controller via Modbus TCP.
    Supports direct connection and SSH tunnel mode.
    """

    def __init__(self, host: str = None, port: int = None,
                 unit_id: int = None, config_path: str = None):
        """
        Args:
            host: Modbus host. None = from config.
            port: Modbus port. None = from config.
            unit_id: Modbus unit ID. None = from config.
        """
        if ModbusClient is None:
            raise RuntimeError("pyModbusTCP not installed. Run: pip install pyModbusTCP")

        # Try to load config, fallback to defaults if missing
        try:
            self.cfg = load_config(config_path or "modbus_config.yaml")
        except Exception:
            print("[WARN] modbus_config.yaml not found, using internal defaults.")
            self.cfg = self._get_default_config()

        conn = self.cfg.get("connection", {})
        self.host = host or conn.get("host", "127.0.0.1")
        self.port = port or conn.get("port", 502)
        self.unit_id = unit_id or conn.get("unit_id", 2)
        self.timeout = conn.get("timeout_s", 1.0)
        self.retries = conn.get("connect_retries", 3)
        self.retry_delay = conn.get("connect_retry_delay_s", 2.0)

        self.regs = self.cfg["registers"]
        self.cmds = self.cfg["commands"]
        self.motion = self.cfg["motion"]
        self.safety = self.cfg["safety"]

        self.client = None
        self._connected = False
        self._io_lock = threading.RLock()

    def _get_default_config(self) -> dict:
        """Internal default register map for the robot controller."""
        return {
            "connection": {"host": "127.0.0.1", "port": 502, "unit_id": 2},
            "registers": {
                "alarm_reset_1": 1400, "alarm_reset_2": 1401, "alarm_reset_3": 1402,
                "group_error_reset": 384,
                "servo_on_off": 16, "current_pose_base": 240,
                "robot_speed_override": 582,
                "motion_command": 768,
                "acceleration": 778,
                "in_position_flag": 799,
                "speed_percent": 804,
                "target_pose_base": 816,
                "user_frame": 828,
                "target_posture": 829,
                "move_mode": 830,
                "tool_frame": 831,
            },
            "commands": {"p2p_move": 1, "motion_stop": 1000, "home": 1405},
            "motion": {
                "default_speed_percent": 20,
                "settle_wait_s": 2.0,
                "move_mode": 1,
                "set_robot_speed_override": True,
                "robot_speed_override_percent": 100,
                "set_acceleration": False,
                "acceleration_raw": 0,
                "set_target_posture": False,
                "target_posture": 0,
                "set_frames": False,
                "user_frame": 0,
                "tool_frame": 0,
                "verify_speed_write": True,
            },
            "safety": {"max_speed_percent": 100}
        }

    def probe(self) -> bool:
        """Test TCP connectivity before Modbus connection."""
        try:
            s = socket.socket()
            s.settimeout(2.0)
            s.connect((self.host, self.port))
            s.close()
            print(f"[ARM] TCP probe {self.host}:{self.port} OK")
            return True
        except Exception as e:
            print(f"[ARM] TCP probe {self.host}:{self.port} FAIL: {e}")
            return False

    def connect(self) -> bool:
        """Connect to the robot arm controller."""
        with self._io_lock:
            print(f"[ARM] Connecting to {self.host}:{self.port} (unit={self.unit_id})...")

            if not self.probe():
                return False

            self.client = ModbusClient(
                host=self.host, port=self.port,
                unit_id=self.unit_id, auto_open=True
            )
            self.client.timeout = self.timeout

            for attempt in range(1, self.retries + 1):
                if self.client.open():
                    print(f"[ARM] Connected (attempt {attempt}).")
                    self._connected = True
                    return True
                print(f"[ARM] Connect attempt {attempt}/{self.retries} failed, retrying...")
                time.sleep(self.retry_delay)

            print("[ARM] Failed to connect after all retries.")
            return False

    def disconnect(self):
        """Close the Modbus connection."""
        with self._io_lock:
            if self.client:
                self.client.close()
                self._connected = False
                print("[ARM] Disconnected.")

    def reset_alarms(self):
        """Reset controller alarms (same sequence as weekly_maintenence.py)."""
        with self._io_lock:
            print("[ARM] Resetting alarms...")
            for reg in [self.regs["alarm_reset_1"],
                        self.regs["alarm_reset_2"],
                        self.regs["alarm_reset_3"]]:
                self.client.write_multiple_registers(reg, int_to_register(1))
                self.client.write_multiple_registers(reg, int_to_register(256))
            group_reg = self.regs.get("group_error_reset")
            if group_reg is not None:
                self.client.write_multiple_registers(group_reg, int_to_register(1))
                self.client.write_multiple_registers(group_reg, int_to_register(0))

    def servo_on(self):
        """Turn servo ON and wait for settle."""
        with self._io_lock:
            print("[ARM] Servo ON")
            self.client.write_single_register(self.regs["servo_on_off"], 1)
            time.sleep(self.motion.get("servo_settle_s", 1.0))

    def servo_off(self):
        """Turn servo OFF."""
        with self._io_lock:
            print("[ARM] Servo OFF")
            self.client.write_single_register(self.regs["servo_on_off"], 2)

    def motion_stop(self):
        """Issue controller motion stop command."""
        with self._io_lock:
            stop_cmd = int(self.cmds.get("motion_stop", 1000))
            print(f"[ARM] Motion STOP ({stop_cmd})")
            self.client.write_single_register(self.regs["motion_command"], stop_cmd)

    def read_current_pose(self) -> list:
        """Read current Cartesian pose from controller."""
        with self._io_lock:
            return read_current_pose_from_registers(
                self.client, self.regs["current_pose_base"]
            )

    def read_current_pose_mm_deg(self) -> list:
        """Read current pose in mm and degrees."""
        return pose_to_mm_deg(self.read_current_pose())

    def read_register(self, reg: int) -> int | None:
        """Read one holding register."""
        with self._io_lock:
            out = self.client.read_holding_registers(reg, 1)
            if out is None or len(out) != 1:
                return None
            return int(out[0])

    def write_target_pose(self, pose: list):
        """
        Write target pose to controller registers.

        Args:
            pose: [X, Y, Z, RX, RY, RZ] in controller units (mm*1000, deg*1000).
        """
        with self._io_lock:
            base = self.regs["target_pose_base"]
            for i, v in enumerate(pose):
                self.client.write_multiple_registers(
                    base + 2 * i, int32_to_registers(int(v))
                )

    def move_to(self, pose: list, speed: int = None,
                wait: bool = True, wait_seconds: float = None):
        """
        Move arm to a target pose using P2P motion.

        Args:
            pose: [X, Y, Z, RX, RY, RZ] in controller units.
            speed: Speed percentage (1-100). None = from config.
            wait: Whether to wait after sending command.
            wait_seconds: How long to wait. None = from config.
        """
        requested_speed = int(speed or self.motion["default_speed_percent"])
        protocol_max_speed = int(self.motion.get("protocol_max_speed_percent", 100))
        max_speed = min(int(self.safety.get("max_speed_percent", 100)), protocol_max_speed)
        speed = max(1, min(requested_speed, max_speed))
        wait_s = wait_seconds or self.motion["settle_wait_s"]

        with self._io_lock:
            if speed != requested_speed:
                print(
                    f"[ARM] Move to {pose} @ {speed}% speed "
                    f"(requested {requested_speed}%, max {max_speed}%)"
                )
            else:
                print(f"[ARM] Move to {pose} @ {speed}% speed")

            # Write target pose
            self.write_target_pose(pose)

            # Set mode and speed
            override_reg = self.regs.get("robot_speed_override")
            if self.motion.get("set_robot_speed_override", False) and override_reg is not None:
                override_percent = float(self.motion.get("robot_speed_override_percent", 100))
                override_raw = max(1, min(int(round(override_percent * 10)), 1000))
                self.client.write_single_register(override_reg, override_raw)

            acc_reg = self.regs.get("acceleration")
            if self.motion.get("set_acceleration", False) and acc_reg is not None:
                acc_raw = max(0, int(self.motion.get("acceleration_raw", 0)))
                self.client.write_single_register(acc_reg, acc_raw)

            user_frame_reg = self.regs.get("user_frame")
            tool_frame_reg = self.regs.get("tool_frame")
            if self.motion.get("set_frames", False):
                if user_frame_reg is not None:
                    self.client.write_single_register(
                        user_frame_reg, int(self.motion.get("user_frame", 0))
                    )
                if tool_frame_reg is not None:
                    self.client.write_single_register(
                        tool_frame_reg, int(self.motion.get("tool_frame", 0))
                    )

            posture_reg = self.regs.get("target_posture")
            if self.motion.get("set_target_posture", False) and posture_reg is not None:
                self.client.write_single_register(
                    posture_reg, int(self.motion.get("target_posture", 0))
                )

            self.client.write_single_register(self.regs["move_mode"],
                                              self.motion["move_mode"])
            self.client.write_single_register(self.regs["speed_percent"], speed)
            if self.motion.get("verify_speed_write", True):
                actual_speed = self.read_register(self.regs["speed_percent"])
                actual_mode = self.read_register(self.regs["move_mode"])
                actual_override = self.read_register(override_reg) if override_reg is not None else None
                actual_acc = self.read_register(acc_reg) if acc_reg is not None else None
                actual_posture = self.read_register(posture_reg) if posture_reg is not None else None
                actual_user_frame = self.read_register(user_frame_reg) if user_frame_reg is not None else None
                actual_tool_frame = self.read_register(tool_frame_reg) if tool_frame_reg is not None else None
                if actual_speed != speed or actual_mode != self.motion["move_mode"]:
                    print(
                        "[ARM-WARN] Motion config readback mismatch: "
                        f"mode wrote {self.motion['move_mode']} read {actual_mode}; "
                        f"speed wrote {speed}% read {actual_speed}%; "
                        f"override read {actual_override}; "
                        f"acc read {actual_acc}; posture read {actual_posture}; "
                        f"user_frame read {actual_user_frame}; tool_frame read {actual_tool_frame}"
                    )
                else:
                    override_msg = ""
                    if actual_override is not None:
                        override_msg = f" override={actual_override / 10.0:.1f}%"
                    extra_msg = (
                        f" acc={actual_acc}"
                        f" posture={actual_posture}"
                        f" user_frame={actual_user_frame}"
                        f" tool_frame={actual_tool_frame}"
                    )
                    print(
                        f"[ARM] Motion config OK: mode={actual_mode} "
                        f"speed={actual_speed}%{override_msg}{extra_msg}"
                    )

            # Trigger move
            self.client.write_single_register(self.regs["motion_command"],
                                              self.cmds["p2p_move"])

            if wait:
                self._wait_with_live_output("move", wait_s)

    def go_home(self, wait: bool = True):
        """Send arm to home position."""
        home = self.cfg.get("home_pose", [444000, 0, 744000, 0, -89999, 179999])
        print(f"[ARM] Going home: {home}")
        self.move_to(home, speed=20, wait=wait, wait_seconds=5.0)

    def go_home_native(self, wait: bool = True, wait_seconds: float = 20.0, verify_timeout_s: float | None = None):
        """Send controller-native home command (1405)."""
        with self._io_lock:
            home_cmd = int(self.cmds.get("home", 1405))
            print(f"[ARM] Going home via native command: {home_cmd}")
            self.client.write_single_register(self.regs["motion_command"], home_cmd)

        if wait:
            self._wait_for_in_position(
                timeout_s=verify_timeout_s or wait_seconds,
                fallback_wait_s=wait_seconds,
                label="home_native",
            )

    def wait_until_in_position(self, timeout_s: float = 20.0, fallback_wait_s: float | None = None, label: str = "move"):
        """Wait until controller reports in-position."""
        self._wait_for_in_position(
            timeout_s=timeout_s,
            fallback_wait_s=fallback_wait_s or timeout_s,
            label=label,
        )

    def pick_at(self, robot_xyz_mm: list, orientation: list = None,
                approach_height_mm: float = 80,
                lift_height_mm: float = 100,
                speed: int = 20):
        """
        Execute a pick sequence at the given 3D position.

        Args:
            robot_xyz_mm: [X, Y, Z] in mm (robot base frame).
            orientation: [RX, RY, RZ] in controller units. None = default.
            approach_height_mm: Height above object for approach.
            lift_height_mm: Height to lift after pick.
            speed: Speed percentage.
        """
        objects_cfg = load_config("objects.yaml")
        defaults = objects_cfg.get("pick_defaults", {})
        approach_h = approach_height_mm or defaults.get("approach_height_mm", 80)
        lift_h = lift_height_mm or defaults.get("lift_height_mm", 100)

        # Default orientation (pointing down)
        if orientation is None:
            orientation = [0, -89999, 179999]

        # Convert mm to controller units (mm * 1000)
        x = int(robot_xyz_mm[0] * 1000)
        y = int(robot_xyz_mm[1] * 1000)
        z = int(robot_xyz_mm[2] * 1000)
        approach_z = int((robot_xyz_mm[2] + approach_h) * 1000)
        lift_z = int((robot_xyz_mm[2] + lift_h) * 1000)

        steps = [
            ("approach", [x, y, approach_z] + orientation),
            ("descend",  [x, y, z] + orientation),
            # TODO: gripper close here
            ("lift",     [x, y, lift_z] + orientation),
        ]

        for step_name, pose in steps:
            print(f"[ARM] Pick step: {step_name}")
            self.move_to(pose, speed=speed)

    def _wait_with_live_output(self, label: str, duration: float):
        """Wait with periodic live pose output."""
        start = time.time()
        interval = 0.5

        while time.time() - start < duration:
            elapsed = time.time() - start
            pose = self.read_current_pose_mm_deg()
            print(f"  [{label}] {elapsed:.1f}/{duration:.1f}s "
                  f"pose(mm/deg)={[round(v, 1) for v in pose]}")
            time.sleep(interval)

    def _wait_for_in_position(self, timeout_s: float, fallback_wait_s: float, label: str = "move"):
        """Wait until controller reports in-position, with live-output fallback."""
        flag_reg = self.regs.get("in_position_flag")
        if flag_reg is None:
            self._wait_with_live_output(label, fallback_wait_s)
            return

        start = time.time()
        interval = 0.5
        while time.time() - start < max(timeout_s, interval):
            elapsed = time.time() - start
            flag = self.read_register(flag_reg)
            pose = self.read_current_pose_mm_deg()
            print(
                f"  [{label}] {elapsed:.1f}/{timeout_s:.1f}s "
                f"inpos={flag} pose(mm/deg)={[round(v, 1) for v in pose]}"
            )
            if flag == 1:
                return
            time.sleep(interval)

        self._wait_with_live_output(label, min(fallback_wait_s, 2.0))

    def execute_pick_sequence(self, robot_xyz_mm: list,
                              object_name: str = "unknown"):
        """
        Full pick sequence: home → approach → pick → lift → home.

        Args:
            robot_xyz_mm: [X, Y, Z] in mm.
            object_name: For display only.
        """
        print(f"\n{'='*50}")
        print(f"[ARM] Picking: {object_name}")
        print(f"[ARM] Target position: {robot_xyz_mm}")
        print(f"{'='*50}")

        if self.safety.get("require_confirmation", True):
            resp = input("[SAFETY] Execute pick? [y/N]: ").strip().lower()
            if resp != "y":
                print("[ARM] Cancelled by user.")
                return False

        self.reset_alarms()
        self.servo_on()

        if self.safety.get("home_before_task", True):
            self.go_home()

        self.pick_at(robot_xyz_mm)

        if self.safety.get("home_after_task", True):
            self.go_home()

        self.servo_off()
        print(f"[ARM] Pick complete: {object_name}")
        return True
