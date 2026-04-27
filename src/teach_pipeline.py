from __future__ import annotations

import csv
import json
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Optional

import cv2
import yaml

from src.utils import PROJECT_ROOT

YOLO_CONFIG_DIR = PROJECT_ROOT / "data" / "models" / "ultralytics"
YOLO_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("YOLO_CONFIG_DIR", str(YOLO_CONFIG_DIR))

try:
    from ultralytics import YOLO
except Exception:
    YOLO = None


def infer_object_key_from_name(recording_name: str, objects_cfg: dict[str, Any]) -> str:
    name = str(recording_name or "").strip().lower()
    classes = objects_cfg.get("classes", {}) if isinstance(objects_cfg, dict) else {}
    if not name or not isinstance(classes, dict):
        return ""

    for obj_key, obj_def in classes.items():
        if name == str(obj_def.get("default_teach_recording", "")).strip().lower():
            return obj_key

    for obj_key, obj_def in classes.items():
        candidates = [obj_key]
        candidates.extend(obj_def.get("english", []) or [])
        candidates.extend(obj_def.get("chinese", []) or [])
        for candidate in candidates:
            token = str(candidate or "").strip().lower()
            if token and token in name:
                return obj_key
    return ""


def episode_has_data(episode_dir: Path) -> bool:
    if not episode_dir.exists() or not episode_dir.is_dir():
        return False
    if any((episode_dir / "cam1_rgb").glob("*.jpg")):
        return True
    if any((episode_dir / "cam1_depth").glob("*.png")):
        return True
    if any((episode_dir / "cam2_rgb").glob("*.jpg")):
        return True
    if any((episode_dir / "cam2_depth").glob("*.png")):
        return True
    if any((episode_dir / "claw_rgb").glob("*.jpg")):
        return True
    return (episode_dir / "metadata.json").exists()


def next_episode_index(object_dir: Path) -> int:
    max_idx = 0
    for path in object_dir.glob("episode_*"):
        try:
            idx = int(path.name.split("_")[-1])
        except (TypeError, ValueError):
            continue
        if idx > max_idx and episode_has_data(path):
            max_idx = idx
    return max_idx + 1


def _pose_copy(pose: list[int] | None, fallback: list[int] | None = None) -> list[int]:
    src = pose if isinstance(pose, list) and len(pose) >= 6 else fallback or [0, 0, 0, 0, 0, 0]
    return [int(v) for v in src[:6]]


def _extract_gripper_positions(waypoint: dict[str, Any]) -> list[int]:
    direct = waypoint.get("gripper_pos")
    if isinstance(direct, list) and len(direct) == 3:
        try:
            return [int(v) for v in direct]
        except (TypeError, ValueError):
            return []

    matched = waypoint.get("matched_external")
    if isinstance(matched, dict):
        row = matched.get("row")
        if isinstance(row, dict):
            values = [row.get("pos1"), row.get("pos2"), row.get("pos3")]
            if all(v is not None for v in values):
                try:
                    return [int(float(v)) for v in values]
                except (TypeError, ValueError):
                    return []
    return []


class PhaseSpecManager:
    def __init__(self, demo_cfg: dict[str, Any], objects_cfg: dict[str, Any], save_dir: Path):
        self.demo_cfg = demo_cfg
        self.objects_cfg = objects_cfg
        self.save_dir = save_dir
        teach_cfg = demo_cfg.get("teach", {}) if isinstance(demo_cfg, dict) else {}
        self.templates = teach_cfg.get("phase_templates", {}) if isinstance(teach_cfg, dict) else {}
        self.generation_cfg = teach_cfg.get("phase_generation", {}) if isinstance(teach_cfg, dict) else {}

    def phase_path(self, recording_name: str) -> Path:
        return self.save_dir / f"{recording_name}.phases.yaml"

    def has_phase_yaml(self, recording_name: str) -> bool:
        return self.phase_path(recording_name).exists()

    def load_phase_spec(self, recording_name: str) -> Optional[dict[str, Any]]:
        path = self.phase_path(recording_name)
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data if isinstance(data, dict) else None

    def _template_for_object(self, object_key: str) -> dict[str, Any]:
        default_tpl = self.templates.get("default", {}) if isinstance(self.templates, dict) else {}
        overrides = self.templates.get("object_overrides", {}) if isinstance(self.templates, dict) else {}
        merged: dict[str, Any] = {}
        if isinstance(default_tpl, dict):
            merged.update(default_tpl)
        if object_key and isinstance(overrides, dict):
            obj_override = overrides.get(object_key, {})
            if isinstance(obj_override, dict):
                merged.update(obj_override)
        return merged

    def generate_phase_spec(self, recording_name: str, recording: dict[str, Any]) -> dict[str, Any]:
        waypoints = recording.get("waypoints", []) if isinstance(recording, dict) else []
        if not isinstance(waypoints, list) or not waypoints:
            raise ValueError("Recording has no waypoints")

        object_key = infer_object_key_from_name(recording_name, self.objects_cfg)
        template = self._template_for_object(object_key)

        ready_pose = _pose_copy(self.demo_cfg.get("ready_pose"))
        poses = [_pose_copy(wp.get("pose")) for wp in waypoints if isinstance(wp, dict)]
        grasp_idx = min(range(len(poses)), key=lambda idx: poses[idx][2])
        grasp_pose = _pose_copy(poses[grasp_idx])

        before_grasp = poses[: grasp_idx + 1] or [poses[0]]
        hover_seed = max(before_grasp, key=lambda pose: pose[2])
        hover_pose = _pose_copy(hover_seed, fallback=ready_pose)

        hover_offset = int(template.get("hover_z_offset_um", 180000))
        pregrasp_offset = int(template.get("pregrasp_z_offset_um", 35000))
        lift_offset = int(template.get("lift_z_offset_um", 200000))

        pregrasp_pose = _pose_copy(grasp_pose)
        pregrasp_pose[2] = max(pregrasp_pose[2], grasp_pose[2] + pregrasp_offset)

        hover_pose = _pose_copy(hover_pose)
        hover_pose[0] = grasp_pose[0]
        hover_pose[1] = grasp_pose[1]
        hover_pose[3:] = grasp_pose[3:]
        hover_pose[2] = max(hover_pose[2], grasp_pose[2] + hover_offset, ready_pose[2])

        lift_pose = _pose_copy(hover_pose)
        lift_pose[2] = max(lift_pose[2], grasp_pose[2] + lift_offset)

        close_positions = []
        for idx in range(grasp_idx, len(waypoints)):
            positions = _extract_gripper_positions(waypoints[idx])
            if positions:
                close_positions = positions
                break

        open_positions = []
        for idx in range(0, grasp_idx + 1):
            positions = _extract_gripper_positions(waypoints[idx])
            if positions:
                open_positions = positions
                break

        close_mode = "command"
        if close_positions:
            close_mode = "positions"

        open_mode = "command"
        if open_positions:
            open_mode = "positions"

        return {
            "phase_version": 1,
            "target_object": object_key,
            "source_recording": recording_name,
            "source_recording_json": f"{recording_name}.json",
            "ready_pose": ready_pose,
            "hover_pose": hover_pose,
            "pregrasp_pose": pregrasp_pose,
            "grasp_pose": grasp_pose,
            "lift_pose": lift_pose,
            "speed": {
                "fast_percent": int(template.get("fast_percent", 70)),
                "slow_percent": int(template.get("slow_percent", 25)),
                "pregrasp_percent": int(template.get("pregrasp_percent", template.get("slow_percent", 25))),
                "grasp_percent": int(template.get("grasp_percent", template.get("slow_percent", 25))),
                "lift_percent": int(template.get("lift_percent", 60)),
            },
            "timing": {
                "settle_s": float(template.get("settle_s", 0.4)),
                "grip_hold_s": float(template.get("grip_hold_s", 0.8)),
                "prepare_open_s": float(template.get("prepare_open_s", 0.2)),
                "move_timeout_s": float(template.get("move_timeout_s", 12.0)),
            },
            "z_offsets": {
                "hover_z_offset_um": hover_offset,
                "pregrasp_z_offset_um": pregrasp_offset,
                "lift_z_offset_um": lift_offset,
            },
            "return_pose": str(template.get("return_pose", "ready")),
            "gripper": {
                "open_at_start": bool(template.get("open_at_start", True)),
                "open_mode": open_mode,
                "open_command": str(
                    template.get(
                        "open_command",
                        self.demo_cfg.get("gripper", {}).get("open_command", "o"),
                    )
                ),
                "open_positions": open_positions,
                "position_move_mode": str(template.get("gripper_position_move_mode", "stepped")),
                "open_step_ticks": int(template.get("gripper_open_step_ticks", 24)),
                "open_step_delay_s": float(template.get("gripper_open_step_delay_s", 0.015)),
                "close_mode": close_mode,
                "close_command": str(
                    template.get(
                        "close_command",
                        self.demo_cfg.get("gripper", {}).get("close_command", "c"),
                    )
                ),
                "close_positions": close_positions,
                "close_step_ticks": int(template.get("gripper_close_step_ticks", 10)),
                "close_step_delay_s": float(template.get("gripper_close_step_delay_s", 0.03)),
                "open_after_replay": bool(template.get("open_after_replay", False)),
            },
            "seed": {
                "grasp_waypoint_index": grasp_idx,
                "hover_seed_pose": hover_seed,
                "inferred_object_key": object_key,
            },
        }

    def save_phase_spec(self, recording_name: str, recording: dict[str, Any]) -> Path:
        spec = self.generate_phase_spec(recording_name, recording)
        path = self.phase_path(recording_name)
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(spec, f, sort_keys=False, allow_unicode=True)
        return path


class TeachDatasetRecorder:
    def __init__(self, demo_cfg: dict[str, Any]):
        teach_cfg = demo_cfg.get("teach", {}) if isinstance(demo_cfg, dict) else {}
        self.capture_cfg = teach_cfg.get("dataset_capture", {}) if isinstance(teach_cfg, dict) else {}
        self.auto_label_cfg = teach_cfg.get("auto_label", {}) if isinstance(teach_cfg, dict) else {}
        self.demo_cfg = demo_cfg
        self.enabled = bool(self.capture_cfg.get("enabled", False))
        self.active = False
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.cam_mgr: Any = None
        self.arm_mgr: Any = None
        self.recording_name = ""
        self.object_key = ""
        self.episode_dir: Optional[Path] = None
        self.start_unix = 0.0
        self.frame_counters: dict[str, int] = {}
        self.session_meta: dict[str, Any] = {}
        self.waypoints: list[dict[str, Any]] = []
        self.last_error = ""
        self.frame_manifest_file = None
        self.frame_manifest_writer = None
        self.trajectory_file = None
        self.trajectory_writer = None
        self.gripper_file = None
        self.gripper_writer = None
        self.stream_dirs: dict[str, Path] = {}

    def _selected_streams(self) -> list[str]:
        configured = self.capture_cfg.get("camera_streams", [])
        if isinstance(configured, list) and configured:
            return [str(item) for item in configured]
        return ["cam1_rgb", "cam1_depth", "cam2_rgb", "cam2_depth", "claw_rgb"]

    def _make_episode_dir(self, object_key: str) -> Path:
        output_root = (PROJECT_ROOT / str(self.capture_cfg.get("output_root", "data/recordings"))).resolve()
        object_name = object_key or "unknown_object"
        object_dir = output_root / object_name
        object_dir.mkdir(parents=True, exist_ok=True)
        episode_idx = next_episode_index(object_dir)
        episode_dir = object_dir / f"episode_{episode_idx:03d}"
        episode_dir.mkdir(parents=True, exist_ok=True)
        return episode_dir

    def _open_writers(self) -> None:
        assert self.episode_dir is not None
        streams = self._selected_streams()
        for stream in streams:
            stream_dir = self.episode_dir / stream
            stream_dir.mkdir(parents=True, exist_ok=True)
            self.stream_dirs[stream] = stream_dir
            self.frame_counters[stream] = 0

        self.frame_manifest_file = open(self.episode_dir / "frame_manifest.csv", "w", newline="", encoding="utf-8")
        self.frame_manifest_writer = csv.writer(self.frame_manifest_file)
        self.frame_manifest_writer.writerow(
            ["stream", "frame_index", "timestamp_unix", "relative_path", "width", "height", "labels_json"]
        )

        self.trajectory_file = open(self.episode_dir / "trajectory.csv", "w", newline="", encoding="utf-8")
        self.trajectory_writer = csv.writer(self.trajectory_file)
        self.trajectory_writer.writerow(["timestamp_unix", "x_mm", "y_mm", "z_mm", "rx_deg", "ry_deg", "rz_deg"])

        self.gripper_file = open(self.episode_dir / "gripper_stream.csv", "w", newline="", encoding="utf-8")
        self.gripper_writer = csv.writer(self.gripper_file)
        self.gripper_writer.writerow(
            ["timestamp_unix", "server_time_unix", "pos1", "pos2", "pos3", "tactile_data", "error"]
        )

    def start(
        self,
        recording_name: str,
        object_key: str,
        session_meta: dict[str, Any],
        cam_mgr: Any,
        arm_mgr: Any,
    ) -> Optional[Path]:
        if not self.enabled:
            return None
        if self.active:
            self.stop(result="aborted", failure_reason="new session started")

        self.recording_name = recording_name
        self.object_key = object_key or ""
        self.session_meta = dict(session_meta or {})
        self.cam_mgr = cam_mgr
        self.arm_mgr = arm_mgr
        self.episode_dir = self._make_episode_dir(self.object_key)
        self.start_unix = time.time()
        self.stop_event.clear()
        self.active = True
        self.waypoints = []
        self.last_error = ""
        self.stream_dirs = {}
        self.frame_counters = {}
        self._open_writers()
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()
        return self.episode_dir

    def note_waypoint(self, waypoint: dict[str, Any]) -> None:
        if not self.active:
            return
        self.waypoints.append(json.loads(json.dumps(waypoint)))

    def _write_frame(self, stream: str, timestamp_unix: float, frame, labels: list[str] | None = None) -> None:
        if frame is None or stream not in self.stream_dirs:
            return
        idx = self.frame_counters.get(stream, 0)
        ext = ".png" if stream.endswith("_depth") else ".jpg"
        filename = f"frame_{idx:06d}{ext}"
        path = self.stream_dirs[stream] / filename
        ok = cv2.imwrite(str(path), frame)
        if not ok:
            raise RuntimeError(f"failed to write frame {path}")
        self.frame_counters[stream] = idx + 1
        if self.frame_manifest_writer is not None:
            height, width = frame.shape[:2]
            rel_path = str(path.relative_to(self.episode_dir))
            self.frame_manifest_writer.writerow(
                [
                    stream,
                    idx,
                    f"{timestamp_unix:.6f}",
                    rel_path,
                    width,
                    height,
                    json.dumps(labels or [], ensure_ascii=False),
                ]
            )

    def _poll_arm_pose(self) -> None:
        if self.trajectory_writer is None:
            return
        pose = getattr(self.arm_mgr, "current_pose_mm_deg", None)
        if not pose or len(pose) < 6:
            return
        self.trajectory_writer.writerow([f"{time.time():.6f}"] + [f"{float(v):.6f}" for v in pose[:6]])

    def _poll_gripper(self) -> None:
        if self.gripper_writer is None:
            return
        try:
            state = self.arm_mgr.get_gripper_state(silent=True)
        except Exception as exc:
            self.gripper_writer.writerow([f"{time.time():.6f}", "", "", "", "", "", str(exc)])
            return
        if not isinstance(state, dict):
            self.gripper_writer.writerow([f"{time.time():.6f}", "", "", "", "", "", "unavailable"])
            return
        pos = state.get("current_pos") if isinstance(state.get("current_pos"), list) else []
        tactile = state.get("tactile_data", "")
        self.gripper_writer.writerow(
            [
                f"{time.time():.6f}",
                state.get("server_time_unix", ""),
                pos[0] if len(pos) > 0 else "",
                pos[1] if len(pos) > 1 else "",
                pos[2] if len(pos) > 2 else "",
                tactile,
                "",
            ]
        )

    def _capture_loop(self) -> None:
        image_hz = max(1.0, float(self.capture_cfg.get("image_fps", 6.0)))
        telemetry_hz = max(1.0, float(self.capture_cfg.get("telemetry_hz", 10.0)))
        next_image = 0.0
        next_telemetry = 0.0
        selected = set(self._selected_streams())

        while not self.stop_event.is_set():
            now = time.time()
            try:
                if now >= next_image:
                    for cam_key in ("cam1", "cam2", "claw"):
                        snapshot = self.cam_mgr.get_snapshot(cam_key) if self.cam_mgr is not None else None
                        if not isinstance(snapshot, dict):
                            continue
                        ts = float(snapshot.get("timestamp_unix", now))
                        if cam_key in ("cam1", "cam2"):
                            rgb_stream = f"{cam_key}_rgb"
                            depth_stream = f"{cam_key}_depth"
                            if rgb_stream in selected:
                                self._write_frame(rgb_stream, ts, snapshot.get("rgb"))
                            if depth_stream in selected:
                                self._write_frame(depth_stream, ts, snapshot.get("depth_raw"))
                        elif cam_key == "claw" and "claw_rgb" in selected:
                            self._write_frame("claw_rgb", ts, snapshot.get("rgb"), snapshot.get("labels"))
                    next_image = now + (1.0 / image_hz)

                if now >= next_telemetry:
                    self._poll_arm_pose()
                    self._poll_gripper()
                    next_telemetry = now + (1.0 / telemetry_hz)
            except Exception as exc:
                self.last_error = str(exc)
            time.sleep(0.01)

    def _close_writers(self) -> None:
        for handle_name in ("frame_manifest_file", "trajectory_file", "gripper_file"):
            handle = getattr(self, handle_name, None)
            if handle:
                try:
                    handle.close()
                except Exception:
                    pass
                setattr(self, handle_name, None)
        self.frame_manifest_writer = None
        self.trajectory_writer = None
        self.gripper_writer = None

    def _export_auto_labels(self) -> dict[str, Any]:
        summary = {"enabled": False, "streams": [], "error": ""}
        if not self.auto_label_cfg.get("enabled", False):
            return summary
        if YOLO is None:
            summary["error"] = "ultralytics unavailable"
            return summary
        assert self.episode_dir is not None
        model_path = PROJECT_ROOT / str(
            self.auto_label_cfg.get(
                "model_path",
                self.demo_cfg.get("cameras", {}).get("claw", {}).get("model_path", "data/models/yolo/yolo12sbest.pt"),
            )
        )
        if not model_path.exists():
            summary["error"] = f"model missing: {model_path}"
            return summary

        streams = self.auto_label_cfg.get("streams", ["claw_rgb"])
        conf = float(self.auto_label_cfg.get("conf", self.demo_cfg.get("cameras", {}).get("claw", {}).get("conf", 0.5)))
        export_root = self.episode_dir / "cvat_yolo"
        export_root.mkdir(parents=True, exist_ok=True)
        model = YOLO(str(model_path))
        names = model.names if isinstance(model.names, dict) else {}
        class_names = [names[idx] for idx in sorted(names.keys())] if names else []

        for stream in streams:
            stream_dir = self.stream_dirs.get(stream)
            if stream_dir is None or not stream_dir.exists():
                continue
            out_dir = export_root / stream
            data_dir = out_dir / "obj_train_data"
            data_dir.mkdir(parents=True, exist_ok=True)

            image_paths = sorted(stream_dir.glob("*.jpg"))
            train_txt_lines: list[str] = []
            labeled = 0
            for image_path in image_paths:
                dest_image = data_dir / image_path.name
                shutil.copy2(image_path, dest_image)
                frame = cv2.imread(str(image_path))
                if frame is None:
                    continue
                results = model(frame, conf=conf, verbose=False)
                lines: list[str] = []
                if results and results[0].boxes is not None:
                    h, w = frame.shape[:2]
                    for box in results[0].boxes:
                        xywh = box.xywhn[0].tolist()
                        cls = int(box.cls[0])
                        lines.append(f"{cls} {xywh[0]:.6f} {xywh[1]:.6f} {xywh[2]:.6f} {xywh[3]:.6f}")
                label_path = data_dir / f"{image_path.stem}.txt"
                label_path.write_text("\n".join(lines), encoding="utf-8")
                train_txt_lines.append(f"obj_train_data/{image_path.name}")
                if lines:
                    labeled += 1

            (out_dir / "obj.names").write_text("\n".join(class_names), encoding="utf-8")
            (out_dir / "train.txt").write_text("\n".join(train_txt_lines), encoding="utf-8")
            (out_dir / "obj.data").write_text(
                f"classes = {len(class_names)}\ntrain = train.txt\nnames = obj.names\nbackup = backup/\n",
                encoding="utf-8",
            )
            (out_dir / "provenance.json").write_text(
                json.dumps(
                    {
                        "source_episode": str(self.episode_dir.relative_to(PROJECT_ROOT)),
                        "stream": stream,
                        "model_path": str(model_path.relative_to(PROJECT_ROOT)),
                        "confidence_threshold": conf,
                        "export_time_unix": time.time(),
                        "total_images": len(train_txt_lines),
                        "labeled_images": labeled,
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            summary["streams"].append(
                {
                    "stream": stream,
                    "export_dir": str(out_dir.relative_to(PROJECT_ROOT)),
                    "images": len(train_txt_lines),
                    "labeled_images": labeled,
                }
            )

        summary["enabled"] = True
        return summary

    def stop(self, result: str = "recorded", failure_reason: str = "") -> dict[str, Any]:
        if not self.active:
            return {"enabled": False}

        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=3.0)
        self._close_writers()

        assert self.episode_dir is not None
        teach_waypoints_path = self.episode_dir / "teach_waypoints.json"
        teach_waypoints_path.write_text(
            json.dumps(self.waypoints, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        try:
            auto_label_summary = self._export_auto_labels()
        except Exception as exc:
            auto_label_summary = {"enabled": False, "streams": [], "error": str(exc)}
        metadata = {
            "episode_id": str(self.episode_dir.relative_to(PROJECT_ROOT)),
            "recording_name": self.recording_name,
            "object_key": self.object_key,
            "requested_text": self.session_meta.get("requested_text", ""),
            "asr_text": self.session_meta.get("asr_text", ""),
            "operator_selected_object": self.session_meta.get("operator_selected_object", self.object_key),
            "mode": "teach",
            "start_unix": self.start_unix,
            "end_unix": time.time(),
            "result": result,
            "failure_reason": failure_reason,
            "streams": sorted(self.stream_dirs.keys()),
            "waypoint_count": len(self.waypoints),
            "teach_waypoints_json": str(teach_waypoints_path.relative_to(PROJECT_ROOT)),
            "auto_label": auto_label_summary,
            "capture_error": self.last_error,
        }
        metadata_path = self.episode_dir / "metadata.json"
        metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

        self.active = False
        return {
            "enabled": True,
            "episode_dir": str(self.episode_dir.relative_to(PROJECT_ROOT)),
            "metadata_path": str(metadata_path.relative_to(PROJECT_ROOT)),
            "auto_label": auto_label_summary,
            "capture_error": self.last_error,
        }
