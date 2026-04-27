"""
End-to-end pipeline: Voice/Text → NLU → YOLO Detection → Arm Pick.

This is the main orchestrator that ties together:
  1. Speech recognition (breeze-asr / whisper)
  2. Fuzzy NLU (intent + object parsing)
  3. YOLO object detection (with RealSense depth)
  4. Arm control (Modbus via tunnel)

Usage:
    python -m src.pipeline                    # Interactive mode (text input)
    python -m src.pipeline --voice            # Voice input mode
    python -m src.pipeline --command "拿蘋果"  # One-shot mode
"""

import argparse
import sys
import time
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.nlu import IntentParser, IntentResult
from src.controller import ArmController
from src.utils import load_config


def create_detector():
    """Create object detector (lazy import, needs ultralytics)."""
    try:
        from src.detector import ObjectDetector
        return ObjectDetector()
    except Exception as e:
        print(f"[WARN] Cannot load detector: {e}")
        print("[WARN] Running without YOLO detection (Modbus-only mode).")
        return None


def create_asr():
    """Create speech recognizer (lazy import, needs whisper + mic)."""
    try:
        from src.asr import SpeechRecognizer
        asr = SpeechRecognizer()
        if not asr.available:
            return None
        return asr
    except Exception as e:
        print(f"[WARN] Cannot load ASR: {e}")
        return None


class Pipeline:
    """
    Main orchestrator for the voice-controlled pick system.
    """

    def __init__(self, use_voice: bool = False, use_detector: bool = True,
                 dry_run: bool = False):
        """
        Args:
            use_voice: Whether to use voice input (requires mic + ASR).
            use_detector: Whether to use YOLO detection (requires cameras).
            dry_run: If True, don't execute arm motions.
        """
        self.dry_run = dry_run
        self.nlu = IntentParser()
        self.arm = None
        self.detector = None
        self.asr = None

        # Load detector if requested
        if use_detector:
            self.detector = create_detector()

        # Load ASR if voice mode
        if use_voice:
            self.asr = create_asr()
            if self.asr is None:
                print("[WARN] Voice mode requested but ASR unavailable. Using text input.")

        # Load arm controller
        if not dry_run:
            self.arm = ArmController()

        # Load object config for fallback poses
        self.objects_cfg = load_config("objects.yaml")

    def get_input(self) -> str:
        """Get user input (voice or text)."""
        if self.asr is not None:
            print("\n[MIC] Press Enter to start recording, or type a command:")
            user = input("> ").strip()
            if user:
                return user
            # Empty input = use voice
            return self.asr.listen()
        else:
            return input("\n指令 (輸入 q 離開) > ").strip()

    def handle_intent(self, result: IntentResult) -> bool:
        """
        Process a parsed intent.

        Returns:
            True to continue, False to quit.
        """
        if result.intent == "quit":
            print("再見！")
            return False

        if result.intent == "home":
            print("[ACTION] 回到原點")
            if not self.dry_run and self.arm:
                if self.arm.connect():
                    self.arm.reset_alarms()
                    self.arm.servo_on()
                    self.arm.go_home()
                    self.arm.servo_off()
                    self.arm.disconnect()
            return True

        if result.need_confirmation:
            # Ambiguous — ask for clarification
            prompt = self.nlu.get_disambiguation_prompt(result)
            print(f"\n[NLU] {prompt}")
            clarification = input("> ").strip()
            if clarification:
                result = self.nlu.parse(clarification)
                if result.object_key:
                    return self._execute_pick(result.object_key)
            print("[NLU] 無法辨識，請再試一次。")
            return True

        if result.object_key:
            return self._execute_pick(result.object_key)

        print("[NLU] 無法辨識指令，請再試一次。")
        print(f"[NLU] 支援的物品:\n{self.nlu.list_objects()}")
        return True

    def _execute_pick(self, object_key: str) -> bool:
        """Execute a pick operation for the given object."""
        obj_def = self.objects_cfg.get("classes", {}).get(object_key, {})
        zh_name = obj_def.get("chinese", [object_key])[0] if obj_def else object_key

        print(f"\n[ACTION] 正在拿取: {zh_name} ({object_key})")

        # Try to detect object with YOLO if available
        robot_xyz_mm = None

        if self.detector:
            robot_xyz_mm = self._detect_object(object_key)

        if robot_xyz_mm is None:
            print("[WARN] 無法偵測到物品位置。無法執行。")
            print("[HINT] 請確認:")
            print("  1. 攝影機已連接且校正完成")
            print("  2. 物品在攝影機視野範圍內")
            print("  3. 光線充足")
            return True

        # Execute pick
        if self.dry_run:
            print(f"[DRY RUN] Would pick {object_key} at {robot_xyz_mm}")
        else:
            if self.arm is None:
                self.arm = ArmController()
            if self.arm.connect():
                self.arm.execute_pick_sequence(robot_xyz_mm, object_key)
                self.arm.disconnect()

        return True

    def _detect_object(self, object_key: str) -> list:
        """
        Detect object using YOLO + camera and return robot coordinates.
        Returns [X, Y, Z] in mm or None.
        """
        if self.detector is None:
            return None

        cam_cfg = load_config("camera_calibration.yaml")
        serial_overrides = {}
        for cam_id in (1, 2):
            serial = str(cam_cfg.get(f"camera{cam_id}", {}).get("serial") or "").strip()
            if serial:
                serial_overrides[cam_id] = serial

        print(f"[DETECT] Searching for {object_key} in camera view...")
        best = self.detector.detect_from_cameras(
            target_object=object_key,
            confidence_threshold=0.3,
            camera_ids=(1, 2),
            serial_overrides=serial_overrides,
        )

        if best is None:
            print(f"[DETECT] No valid detection for {object_key}.")
            return None

        robot_xyz_mm = best.get("robot_xyz_mm")
        if robot_xyz_mm is None:
            print(f"[DETECT] {object_key} detected but depth/transform is invalid.")
            return None

        conf = best.get("confidence", 0.0)
        cam_id = best.get("camera_id", "?")
        serial = best.get("camera_serial", "")
        print(
            f"[DETECT] Found {object_key} from cam{cam_id}"
            f" (serial={serial}) conf={conf:.2f}"
        )
        print(
            f"[DETECT] robot_xyz_mm="
            f"[{robot_xyz_mm[0]:.1f}, {robot_xyz_mm[1]:.1f}, {robot_xyz_mm[2]:.1f}]"
        )
        return robot_xyz_mm

    def run(self):
        """Main interactive loop."""
        print("=" * 60)
        print("語音/文字控制機械手臂撿取系統")
        print("Voice/Text Controlled Robotic Arm Pick System")
        print("=" * 60)
        print(f"模式: {'語音' if self.asr else '文字輸入'}")
        print(f"偵測: {'YOLO' if self.detector else '關閉'}")
        print(f"執行: {'乾跑模式 (不動手臂)' if self.dry_run else '真實執行'}")
        print(f"\n支援的物品:\n{self.nlu.list_objects()}")
        print(f"\n指令範例: 拿蘋果 / Pick the apple / 幫我拿盒子")
        print(f"輸入 q 離開 | 輸入 home 回原點")
        print("-" * 60)

        while True:
            try:
                text = self.get_input()
                if not text:
                    continue

                result = self.nlu.parse(text)
                print(f"[NLU] 意圖={result.intent}, 物品={result.object_key}, "
                      f"信心={result.confidence:.2f}")

                if not self.handle_intent(result):
                    break

            except KeyboardInterrupt:
                print("\n再見！")
                break
            except Exception as e:
                print(f"[ERROR] {e}")
                continue

        # Cleanup
        if self.arm and self.arm._connected:
            self.arm.disconnect()
        if self.detector and hasattr(self.detector, "close"):
            self.detector.close()


def main():
    parser = argparse.ArgumentParser(
        description="Voice/Text controlled robotic arm pick system."
    )
    parser.add_argument("--voice", action="store_true",
                        help="Enable voice input (requires microphone + ASR)")
    parser.add_argument("--no-detector", action="store_true",
                        help="Disable YOLO detection (text/modbus only)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview mode: don't execute arm motions")
    parser.add_argument("--command", type=str, default=None,
                        help="One-shot command (skip interactive loop)")
    args = parser.parse_args()

    pipeline = Pipeline(
        use_voice=args.voice,
        use_detector=not args.no_detector,
        dry_run=args.dry_run,
    )

    try:
        if args.command:
            result = pipeline.nlu.parse(args.command)
            print(f"[NLU] {result}")
            pipeline.handle_intent(result)
        else:
            pipeline.run()
    finally:
        if pipeline.detector and hasattr(pipeline.detector, "close"):
            pipeline.detector.close()


if __name__ == "__main__":
    main()
