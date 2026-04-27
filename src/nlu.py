"""
Fuzzy Natural Language Understanding (NLU) for voice/text commands.

Uses:
  1. Text normalization from config/nlu_aliases.yaml
  2. Explicit phrase -> object overrides
  3. Object synonym matching from config/objects.yaml + override aliases
"""

from __future__ import annotations

from typing import Optional

from src.utils import load_config


class IntentResult:
    """Result of intent parsing."""

    def __init__(
        self,
        intent: str,
        object_key: Optional[str],
        confidence: float,
        candidates: list | None = None,
        need_confirmation: bool = False,
        raw_text: str = "",
        matched_phrase: str = "",
        match_source: str = "none",
        normalized_text: str = "",
        normalization_applied: list | None = None,
    ):
        self.intent = intent
        self.object_key = object_key
        self.confidence = confidence
        self.candidates = candidates or []
        self.need_confirmation = need_confirmation
        self.raw_text = raw_text
        self.matched_phrase = matched_phrase
        self.match_source = match_source
        self.normalized_text = normalized_text
        self.normalization_applied = normalization_applied or []

    def __repr__(self):
        return (
            f"IntentResult(intent={self.intent!r}, object={self.object_key!r}, "
            f"conf={self.confidence:.2f}, candidates={self.candidates}, "
            f"matched_phrase={self.matched_phrase!r}, match_source={self.match_source!r})"
        )


class IntentParser:
    """
    Parse voice/text input into structured intent + object.
    Supports Mandarin Taiwan, English, and mixed input.
    """

    PICK_KEYWORDS_ZH = ["拿", "拿起", "撿", "撿起", "抓", "抓起", "取", "拿給我",
                        "幫我拿", "幫我撿", "pick", "拿起來", "拿一下"]
    PICK_KEYWORDS_EN = ["pick", "grab", "take", "get", "fetch", "grasp",
                        "pick up", "grab me", "get me"]
    PLACE_KEYWORDS_ZH = ["放", "放下", "放到", "放在"]
    PLACE_KEYWORDS_EN = ["place", "put", "put down", "set down"]
    HOME_KEYWORDS = ["home", "回家", "回原點", "歸位", "reset"]
    QUIT_KEYWORDS = ["quit", "exit", "bye", "結束", "離開", "停止", "q"]

    def __init__(self, objects_cfg: Optional[dict] = None, aliases_cfg: Optional[dict] = None):
        self.objects_cfg = objects_cfg if objects_cfg is not None else load_config("objects.yaml")
        try:
            self.aliases_cfg = aliases_cfg if aliases_cfg is not None else (load_config("nlu_aliases.yaml") or {})
        except Exception:
            self.aliases_cfg = {}
        self._build_phrase_map()
        self._build_synonym_map()

    def _build_phrase_map(self):
        phrase_map_cfg = self.aliases_cfg.get("phrase_map", {}) if isinstance(self.aliases_cfg, dict) else {}
        self.phrase_map = {}
        for phrase, obj_key in phrase_map_cfg.items():
            if not phrase or not obj_key:
                continue
            self.phrase_map[str(phrase).strip().lower()] = str(obj_key).strip()
        self._sorted_phrase_map = sorted(self.phrase_map.keys(), key=len, reverse=True)

    def _collect_object_aliases(self, obj_key: str, obj_def: dict) -> list[str]:
        aliases = [obj_key.lower()]
        for syn in obj_def.get("chinese", []) or []:
            if syn:
                aliases.append(str(syn).strip().lower())
        for syn in obj_def.get("english", []) or []:
            if syn:
                aliases.append(str(syn).strip().lower())

        override_map = self.aliases_cfg.get("object_alias_overrides", {}) if isinstance(self.aliases_cfg, dict) else {}
        override = override_map.get(obj_key, {}) if isinstance(override_map, dict) else {}
        if isinstance(override, dict):
            for syn in override.get("chinese", []) or []:
                if syn:
                    aliases.append(str(syn).strip().lower())
            for syn in override.get("english", []) or []:
                if syn:
                    aliases.append(str(syn).strip().lower())
            for syn in override.get("aliases", []) or []:
                if syn:
                    aliases.append(str(syn).strip().lower())
        return aliases

    def _build_synonym_map(self):
        self.synonym_to_object = {}
        self.object_to_synonyms = {}

        for obj_key, obj_def in self.objects_cfg.get("classes", {}).items():
            synonyms = self._collect_object_aliases(obj_key, obj_def)
            deduped = sorted(set(synonyms), key=len, reverse=True)
            for syn in deduped:
                self.synonym_to_object[syn] = obj_key
            self.object_to_synonyms[obj_key] = deduped

        self._sorted_synonyms = sorted(self.synonym_to_object.keys(), key=len, reverse=True)

    def _normalize_text(self, text: str) -> tuple[str, list[str]]:
        normalized = text
        applied: list[str] = []
        norm_cfg = self.aliases_cfg.get("global_normalization", {}) if isinstance(self.aliases_cfg, dict) else {}
        replacements = []
        if isinstance(norm_cfg, dict):
            for src, dst in norm_cfg.items():
                if not src:
                    continue
                replacements.append((str(src), str(dst)))
        replacements.sort(key=lambda item: len(item[0]), reverse=True)

        for src, dst in replacements:
            if src in normalized:
                normalized = normalized.replace(src, dst)
                applied.append(f"{src}->{dst}")
        return normalized, applied

    def parse(self, text: str) -> IntentResult:
        if not text or not text.strip():
            return IntentResult("unknown", None, 0.0, raw_text=text)

        text_clean = text.strip()
        text_lower = text_clean.lower()
        normalized_text, normalization_applied = self._normalize_text(text_lower)

        for kw in self.QUIT_KEYWORDS:
            if kw in normalized_text:
                return IntentResult(
                    "quit", None, 1.0,
                    raw_text=text_clean,
                    normalized_text=normalized_text,
                    normalization_applied=normalization_applied,
                )

        for kw in self.HOME_KEYWORDS:
            if kw in normalized_text:
                return IntentResult(
                    "home", None, 1.0,
                    raw_text=text_clean,
                    normalized_text=normalized_text,
                    normalization_applied=normalization_applied,
                )

        intent = self._detect_intent(normalized_text)
        obj_key, candidates, conf, matched_phrase, match_source = self._extract_object(normalized_text)

        if obj_key and len(candidates) == 1:
            return IntentResult(
                intent, obj_key, conf, candidates, False, text_clean,
                matched_phrase=matched_phrase,
                match_source=match_source,
                normalized_text=normalized_text,
                normalization_applied=normalization_applied,
            )
        if len(candidates) > 1:
            return IntentResult(
                intent, None, conf * 0.5, candidates, True, text_clean,
                matched_phrase=matched_phrase,
                match_source=match_source,
                normalized_text=normalized_text,
                normalization_applied=normalization_applied,
            )
        return IntentResult(
            intent, None, 0.3, [], True, text_clean,
            matched_phrase=matched_phrase,
            match_source=match_source,
            normalized_text=normalized_text,
            normalization_applied=normalization_applied,
        )

    def _detect_intent(self, text: str) -> str:
        for kw in self.PLACE_KEYWORDS_ZH + self.PLACE_KEYWORDS_EN:
            if kw in text:
                return "place"
        for kw in self.PICK_KEYWORDS_ZH + self.PICK_KEYWORDS_EN:
            if kw in text:
                return "pick"
        return "pick"

    def _extract_object(self, text: str) -> tuple[Optional[str], list[str], float, str, str]:
        phrase_hits: list[tuple[str, str]] = []
        for phrase in self._sorted_phrase_map:
            if phrase in text:
                phrase_hits.append((phrase, self.phrase_map[phrase]))

        if phrase_hits:
            max_len = max(len(phrase) for phrase, _ in phrase_hits)
            phrase_hits = [(phrase, obj_key) for phrase, obj_key in phrase_hits if len(phrase) == max_len]
            unique_objects = []
            seen = set()
            for _, obj_key in phrase_hits:
                if obj_key not in seen:
                    unique_objects.append(obj_key)
                    seen.add(obj_key)
            if len(unique_objects) == 1:
                return unique_objects[0], unique_objects, 0.99, phrase_hits[0][0], "phrase_override"
            return None, unique_objects, 0.7, phrase_hits[0][0], "phrase_override"

        matched_objects = []
        seen = set()
        best_phrase = ""
        for synonym in self._sorted_synonyms:
            if synonym in text:
                obj_key = self.synonym_to_object[synonym]
                if not best_phrase:
                    best_phrase = synonym
                if obj_key in seen:
                    continue
                matched_objects.append(obj_key)
                seen.add(obj_key)

        if len(matched_objects) == 1:
            return matched_objects[0], matched_objects, 0.95, best_phrase, "alias"
        if len(matched_objects) > 1:
            return None, matched_objects, 0.5, best_phrase, "ambiguous"
        return None, [], 0.0, "", "none"

    def get_disambiguation_prompt(self, result: IntentResult) -> str:
        if not result.candidates:
            all_objects = list(self.objects_cfg.get("classes", {}).keys())
            names_zh = []
            for obj in all_objects:
                zh_names = self.objects_cfg["classes"][obj].get("chinese", [obj])
                names_zh.append(zh_names[0] if zh_names else obj)
            return f"我沒有聽懂要拿什麼。桌上有: {', '.join(names_zh)}。請再說一次？"

        names_zh = []
        for obj in result.candidates:
            zh_names = self.objects_cfg["classes"].get(obj, {}).get("chinese", [obj])
            names_zh.append(zh_names[0] if zh_names else obj)
        return f"你說的可能是 {' 或 '.join(names_zh)}，請問要拿哪一個？"

    def list_objects(self) -> str:
        lines = []
        for obj_key, obj_def in self.objects_cfg.get("classes", {}).items():
            zh = obj_def.get("chinese", ["?"])[0]
            en = obj_def.get("english", ["?"])[0]
            lines.append(f"  {zh} / {en}")
        return "\n".join(lines)

    def extract_focus_keywords(self, text: str, result: IntentResult | None = None) -> list[str]:
        if not text:
            return []

        normalized_text, _ = self._normalize_text(text.strip().lower())
        keywords: list[str] = []

        intent_groups = [
            self.PICK_KEYWORDS_ZH + self.PICK_KEYWORDS_EN,
            self.PLACE_KEYWORDS_ZH + self.PLACE_KEYWORDS_EN,
            self.HOME_KEYWORDS,
            self.QUIT_KEYWORDS,
        ]
        for group in intent_groups:
            for kw in sorted(group, key=len, reverse=True):
                if kw in normalized_text:
                    keywords.append(kw)
                    break

        if result is not None and result.matched_phrase:
            keywords.append(result.matched_phrase)

        candidates: list[str] = []
        if result is not None:
            if result.object_key:
                candidates.append(result.object_key)
            candidates.extend(result.candidates)

        seen_objects = set()
        for synonym in self._sorted_synonyms:
            if synonym in normalized_text:
                obj_key = self.synonym_to_object[synonym]
                if obj_key in seen_objects:
                    continue
                seen_objects.add(obj_key)
                keywords.append(synonym)

        for obj_key in candidates:
            for syn in self.object_to_synonyms.get(obj_key, []):
                if syn in normalized_text:
                    keywords.append(syn)
                    break

        deduped: list[str] = []
        seen = set()
        for kw in keywords:
            if kw in seen:
                continue
            seen.add(kw)
            deduped.append(kw)
        return deduped[:6]
