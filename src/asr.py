"""
Speech-to-Text module supporting breeze-asr and Whisper.

breeze-asr (MediaTek Research): Best for Mandarin Taiwan, code-switching.
Whisper: Good general-purpose fallback.

Usage:
    from src.asr import SpeechRecognizer
    asr = SpeechRecognizer(engine="whisper", model_size="medium")
    text = asr.listen()         # Record from mic and transcribe
    text = asr.transcribe(path) # Transcribe an audio file
"""

import io
import sys
import wave
from pathlib import Path

import numpy as np

try:
    import sounddevice as sd
except ImportError:
    sd = None
    print("[WARN] sounddevice not installed. Mic capture unavailable.")

try:
    import soundfile as sf
except ImportError:
    sf = None

try:
    import whisper
except ImportError:
    whisper = None
    print("[WARN] openai-whisper not installed. ASR unavailable.")

try:
    import torch
except ImportError:
    torch = None

try:
    from transformers import (
        AutomaticSpeechRecognitionPipeline,
        WhisperForConditionalGeneration,
        WhisperProcessor,
    )
except ImportError:
    AutomaticSpeechRecognitionPipeline = None
    WhisperForConditionalGeneration = None
    WhisperProcessor = None

from src.utils import PROJECT_ROOT, load_config


def _safe_print(message: str) -> None:
    """Print without crashing on Windows console encoding mismatches."""
    try:
        print(message)
    except UnicodeEncodeError:
        stream = getattr(sys, "stdout", None)
        encoding = getattr(stream, "encoding", None) or "utf-8"
        fallback = message.encode(encoding, errors="replace").decode(encoding, errors="replace")
        print(fallback)


def _cuda_runtime_supported() -> bool:
    if torch is None or not torch.cuda.is_available():
        return False
    try:
        major, minor = torch.cuda.get_device_capability(0)
        current = f"sm_{major}{minor}"
        supported = set(torch.cuda.get_arch_list() or [])
        if supported and current not in supported:
            _safe_print(
                f"[ASR] CUDA visible but current wheel does not support {current}; "
                "falling back to CPU."
            )
            return False
    except Exception:
        return False
    return True


def _normalize_language_code(language: str | None) -> str | None:
    if not language:
        return None
    code = str(language).strip().lower()
    if not code:
        return None
    if code.startswith("zh"):
        return "zh"
    if code.startswith("en"):
        return "en"
    if code.startswith("ko"):
        return "ko"
    if code.startswith("ja"):
        return "ja"
    return code


class SpeechRecognizer:
    """
    Speech recognition with support for breeze-asr and Whisper.
    """

    def __init__(self, engine: str = None, model_size: str = None,
                 device: str = None):
        """
        Args:
            engine: "whisper" or "breeze-asr". None = load from config.
            model_size: Whisper model size. None = load from config.
            device: "cpu" or "cuda". None = load from config.
        """
        cfg = load_config("voice_config.yaml")
        self.engine = engine or cfg.get("engine", "whisper")
        self.device = self._resolve_device(device, cfg)
        self.language = cfg.get("whisper", {}).get("language", None)
        self.download_root = str(PROJECT_ROOT / "data" / "models" / "whisper")
        self.breeze_download_root = str(PROJECT_ROOT / "data" / "models" / "breeze_asr")
        self.mic_cfg = cfg.get("microphone", {})
        self.sample_rate = self.mic_cfg.get("sample_rate", 16000)
        self.record_seconds = self.mic_cfg.get("record_seconds", 5)
        self.silence_threshold = self.mic_cfg.get("silence_threshold", 0.02)
        self.silence_duration = self.mic_cfg.get("silence_duration_s", 1.5)

        self.model = None
        self.pipeline = None
        self.processor = None
        self._load_model(model_size, cfg)

    def _resolve_device(self, requested: str | None, cfg: dict) -> str:
        if requested:
            candidate = str(requested).strip().lower()
        else:
            if self.engine == "breeze-asr":
                candidate = str(cfg.get("breeze_asr", {}).get("device", "auto")).strip().lower()
            else:
                candidate = str(cfg.get("whisper", {}).get("device", "auto")).strip().lower()
        if candidate == "auto":
            if _cuda_runtime_supported():
                return "cuda"
            return "cpu"
        if candidate == "cuda" and not _cuda_runtime_supported():
            return "cpu"
        return candidate or "cpu"

    def _resolve_breeze_source(self, model_id: str) -> tuple[str, bool]:
        """
        Prefer a fully cached local snapshot so ASR can boot without internet.

        Returns:
            (model_source, local_files_only)
        """
        snapshot_root = (
            Path(self.breeze_download_root)
            / "models--MediaTek-Research--Breeze-ASR-25"
            / "snapshots"
        )
        if snapshot_root.exists():
            snapshots = sorted(
                [p for p in snapshot_root.iterdir() if p.is_dir()],
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            for snapshot in snapshots:
                if (
                    (snapshot / "config.json").exists()
                    and (snapshot / "preprocessor_config.json").exists()
                    and (snapshot / "model.safetensors").exists()
                ):
                    return str(snapshot), True
        return model_id, False

    def _load_whisper_fallback(self, model_size: str, cfg: dict):
        """Load Whisper as a robust fallback ASR engine."""
        if whisper is None:
            print("[ASR] Whisper not installed. Text input only.")
            return

        size = model_size or cfg.get("whisper", {}).get("model_size", "medium")
        print(f"[ASR] Loading whisper-{size}...")
        Path(self.download_root).mkdir(parents=True, exist_ok=True)
        self.model = whisper.load_model(
            size,
            device=self.device,
            download_root=self.download_root,
        )
        self.pipeline = None
        self.engine = "whisper"
        print(f"[ASR] whisper-{size} loaded OK.")

    def _load_model(self, model_size: str, cfg: dict):
        """Load the ASR model."""
        if self.engine == "breeze-asr":
            model_id = cfg.get("breeze_asr", {}).get(
                "model_id", "MediaTek-Research/Breeze-ASR-25"
            )
            try:
                if AutomaticSpeechRecognitionPipeline is None or WhisperProcessor is None or WhisperForConditionalGeneration is None:
                    raise RuntimeError("transformers is not installed. Run: pip install transformers accelerate datasets[audio]")
                if torch is None:
                    raise RuntimeError("torch is not installed. Breeze ASR requires torch")
                model_source, local_only = self._resolve_breeze_source(model_id)
                source_label = model_source if local_only else model_id
                print(f"[ASR] Loading breeze-asr: {source_label}...")
                Path(self.breeze_download_root).mkdir(parents=True, exist_ok=True)
                processor = WhisperProcessor.from_pretrained(
                    model_source,
                    cache_dir=self.breeze_download_root,
                    local_files_only=local_only,
                )
                model = WhisperForConditionalGeneration.from_pretrained(
                    model_source,
                    cache_dir=self.breeze_download_root,
                    local_files_only=local_only,
                )
                if self.device == "cuda" and torch.cuda.is_available():
                    model = model.to("cuda")
                self.model = model.eval()
                self.processor = processor
                self.pipeline = None
                print("[ASR] breeze-asr loaded OK.")
            except Exception as e:
                print(f"[ASR] Failed to load breeze-asr: {e}")
                print("[ASR] Falling back to whisper...")
                self._load_whisper_fallback(model_size, cfg)
        else:
            self._load_whisper_fallback(model_size, cfg)

    def record_audio(self, duration: float = None) -> np.ndarray:
        """
        Record audio from microphone.

        Args:
            duration: Max recording duration in seconds. None = use config.

        Returns:
            Audio as float32 numpy array (mono, sample_rate).
        """
        if sd is None:
            raise RuntimeError("sounddevice not installed. Run: pip install sounddevice")

        dur = duration or self.record_seconds
        print(f"[ASR] Recording... (max {dur}s, press Ctrl+C to stop early)")

        try:
            audio = sd.rec(int(dur * self.sample_rate),
                           samplerate=self.sample_rate, channels=1,
                           dtype="float32")
            sd.wait()
        except KeyboardInterrupt:
            sd.stop()
            print("[ASR] Recording stopped by user.")
            # Get what we recorded so far
            audio = sd.rec(0, samplerate=self.sample_rate, channels=1,
                           dtype="float32")

        audio = audio.flatten()

        # Trim trailing silence
        audio = self._trim_silence(audio)
        print(f"[ASR] Recorded {len(audio) / self.sample_rate:.1f}s of audio.")
        return audio

    def _trim_silence(self, audio: np.ndarray) -> np.ndarray:
        """Trim trailing silence from audio."""
        if len(audio) == 0:
            return audio

        # Find last non-silent sample
        window = int(self.sample_rate * 0.1)  # 100ms window
        threshold = self.silence_threshold

        for end in range(len(audio) - 1, window, -window):
            chunk = audio[max(0, end - window):end]
            if np.abs(chunk).mean() > threshold:
                return audio[:end + window]

        return audio

    def transcribe(
        self,
        audio_path: str = None,
        audio: np.ndarray = None,
        language: str = None,
    ) -> str:
        """
        Transcribe audio to text.

        Args:
            audio_path: Path to audio file.
            audio: Audio as numpy array. If both provided, audio_path is used.

        Returns:
            Transcribed text string.
        """
        if self.model is None:
            return ""

        active_language = _normalize_language_code(language) or _normalize_language_code(self.language)

        if self.engine == "breeze-asr":
            if audio_path:
                if sf is None:
                    raise RuntimeError("soundfile not installed. Breeze ASR file transcription needs soundfile")
                audio, src_rate = sf.read(audio_path, always_2d=False)
                audio = np.asarray(audio, dtype=np.float32)
                if audio.ndim > 1:
                    audio = audio.mean(axis=1)
                audio = self._resample_audio(audio, src_rate)
            elif audio is not None:
                audio = np.asarray(audio, dtype=np.float32)
            else:
                return ""

            if self.processor is None or torch is None:
                return ""

            inputs = self.processor(
                audio,
                sampling_rate=self.sample_rate,
                return_tensors="pt",
            )
            input_features = inputs.input_features
            if self.device == "cuda" and torch.cuda.is_available():
                input_features = input_features.to("cuda")

            generate_kwargs = {}
            if active_language:
                try:
                    forced_ids = self.processor.get_decoder_prompt_ids(
                        language=active_language,
                        task="transcribe",
                    )
                    generate_kwargs["forced_decoder_ids"] = forced_ids
                except Exception:
                    pass

            with torch.no_grad():
                predicted_ids = self.model.generate(input_features, **generate_kwargs)
            text = self.processor.batch_decode(
                predicted_ids,
                skip_special_tokens=True,
            )[0].strip()
            _safe_print(f"[ASR] Recognized (breeze-asr): {text}")
            return text

        transcribe_kwargs = {
            "fp16": self.device == "cuda",
        }
        if active_language:
            transcribe_kwargs["language"] = active_language

        if audio_path:
            result = self.model.transcribe(str(audio_path), **transcribe_kwargs)
        elif audio is not None:
            result = self.model.transcribe(
                np.asarray(audio, dtype=np.float32),
                **transcribe_kwargs,
            )
        else:
            return ""

        text = result.get("text", "").strip()
        language = result.get("language", "unknown")
        _safe_print(f"[ASR] Recognized ({language}): {text}")
        return text

    def _resample_audio(self, audio: np.ndarray, src_rate: int) -> np.ndarray:
        if src_rate <= 0 or src_rate == self.sample_rate or len(audio) == 0:
            return np.asarray(audio, dtype=np.float32)

        duration = len(audio) / float(src_rate)
        target_len = max(1, int(round(duration * self.sample_rate)))
        src_t = np.linspace(0.0, duration, num=len(audio), endpoint=False)
        dst_t = np.linspace(0.0, duration, num=target_len, endpoint=False)
        return np.interp(dst_t, src_t, audio).astype(np.float32)

    def transcribe_wav_bytes(self, wav_bytes: bytes, language: str = None) -> str:
        """Decode PCM WAV bytes and transcribe them without ffmpeg."""
        if not wav_bytes or self.model is None:
            return ""

        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            src_rate = wf.getframerate()
            frames = wf.readframes(wf.getnframes())

        if sampwidth == 1:
            audio = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
        elif sampwidth == 2:
            audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        elif sampwidth == 4:
            audio = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
        else:
            raise RuntimeError(f"Unsupported WAV sample width: {sampwidth}")

        if channels > 1:
            audio = audio.reshape(-1, channels).mean(axis=1)

        audio = self._resample_audio(audio, src_rate)
        return self.transcribe(audio=audio, language=language)

    def listen(self, duration: float = None) -> str:
        """
        Convenience: record from mic and transcribe in one call.

        Returns:
            Transcribed text string.
        """
        audio = self.record_audio(duration)
        if len(audio) < self.sample_rate * 0.3:
            print("[ASR] Audio too short, skipping.")
            return ""
        return self.transcribe(audio=audio)

    def warmup(self) -> None:
        """Trigger one tiny inference so first real transcription is faster."""
        if self.model is None:
            return
        silence = np.zeros(self.sample_rate, dtype=np.float32)
        try:
            self.transcribe(audio=silence)
        except Exception as exc:
            _safe_print(f"[ASR] Warmup skipped: {exc}")

    @property
    def available(self) -> bool:
        """Check if ASR is ready to use."""
        return self.model is not None
