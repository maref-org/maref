from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

_OMNI_PARSER_AVAILABLE = False
_COG_AGENT_AVAILABLE = False
_transformers_available = False

try:
    from transformers import AutoModelForCausalLM, AutoProcessor  # noqa: F401

    _transformers_available = True
except ImportError:
    pass


class UIElementType(str, Enum):
    BUTTON = "button"
    TEXT_FIELD = "text_field"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    DROPDOWN = "dropdown"
    LINK = "link"
    IMAGE = "image"
    TAB = "tab"
    MENU_ITEM = "menu_item"
    SLIDER = "slider"
    SCROLL_BAR = "scroll_bar"
    ICON = "icon"
    LABEL = "label"
    WINDOW = "window"
    DIALOG = "dialog"
    UNKNOWN = "unknown"


class InteractionType(str, Enum):
    CLICKABLE = "clickable"
    TYPABLE = "typable"
    SCROLLABLE = "scrollable"
    DRAGGABLE = "draggable"
    HOVERABLE = "hoverable"
    SELECTABLE = "selectable"


@dataclass
class BoundingBox:
    x: int
    y: int
    width: int
    height: int

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)

    @property
    def area(self) -> int:
        return self.width * self.height

    def overlaps(self, other: BoundingBox) -> bool:
        return (
            self.x < other.x + other.width
            and self.x + self.width > other.x
            and self.y < other.y + other.height
            and self.y + self.height > other.y
        )

    def to_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}


@dataclass
class ParsedUIElement:
    element_type: UIElementType
    bbox: BoundingBox
    text: str = ""
    confidence: float = 1.0
    interaction_types: list[InteractionType] = field(default_factory=list)
    element_id: str = ""
    parent_id: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)

    @property
    def is_interactive(self) -> bool:
        return len(self.interaction_types) > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "element_type": self.element_type.value,
            "bbox": self.bbox.to_dict(),
            "text": self.text,
            "confidence": self.confidence,
            "interaction_types": [it.value for it in self.interaction_types],
            "element_id": self.element_id,
            "parent_id": self.parent_id,
            "attributes": self.attributes,
        }


@dataclass
class ScreenParseResult:
    screen_width: int
    screen_height: int
    elements: list[ParsedUIElement] = field(default_factory=list)
    parse_time_ms: float = 0.0
    model_name: str = ""
    raw_output: dict[str, Any] = field(default_factory=dict)

    def find_elements_by_type(self, element_type: UIElementType) -> list[ParsedUIElement]:
        return [e for e in self.elements if e.element_type == element_type]

    def find_elements_by_text(self, text: str, case_sensitive: bool = False) -> list[ParsedUIElement]:
        if case_sensitive:
            return [e for e in self.elements if text in e.text]
        return [e for e in self.elements if text.lower() in e.text.lower()]

    def find_element_by_id(self, element_id: str) -> ParsedUIElement | None:
        for e in self.elements:
            if e.element_id == element_id:
                return e
        return None

    def find_interactive_elements(self) -> list[ParsedUIElement]:
        return [e for e in self.elements if e.is_interactive]

    def to_dict(self) -> dict[str, Any]:
        return {
            "screen_width": self.screen_width,
            "screen_height": self.screen_height,
            "elements": [e.to_dict() for e in self.elements],
            "parse_time_ms": self.parse_time_ms,
            "model_name": self.model_name,
        }


class OmniParserInterface:
    """Multi-backend screen parsing interface.

    Supports three pluggable backends:
    - omni_parser: Microsoft OmniParser v2 (local, via HuggingFace transformers)
    - cog_agent: THUDM CogAgent (grounding vision-language model)
    - mock: Deterministic fake elements for testing without GPU
    """

    SUPPORTED_BACKENDS = ("omni_parser", "cog_agent", "mock", "auto")

    def __init__(self, backend: str = "auto", model_config: dict[str, Any] | None = None) -> None:
        if backend not in self.SUPPORTED_BACKENDS:
            raise ValueError(
                f"Unsupported backend '{backend}'. Use one of: {self.SUPPORTED_BACKENDS}"
            )
        self._backend = backend
        self._config = model_config or {}
        self._initialized = False
        self._model: Any = None
        self._processor: Any = None
        self._backend_info: dict[str, Any] = {}
        self._actual_backend = backend

    @property
    def backend(self) -> str:
        return self._backend

    @property
    def actual_backend(self) -> str:
        return self._actual_backend

    @property
    def backend_info(self) -> dict[str, Any]:
        return dict(self._backend_info)

    @property
    def initialized(self) -> bool:
        return self._initialized

    def initialize(self) -> bool:
        if self._backend == "auto":
            return self._initialize_auto()
        if self._backend == "mock":
            self._initialized = True
            self._actual_backend = "mock"
            self._backend_info = {"backend": "mock", "loaded": True, "model": "mock-v0"}
            return True
        try:
            if self._backend == "omni_parser":
                self._init_omni_parser()
            elif self._backend == "cog_agent":
                self._init_cog_agent()
            self._initialized = True
            self._actual_backend = self._backend
            return True
        except Exception as exc:
            self._initialized = False
            self._backend_info = {"backend": self._backend, "loaded": False, "error": str(exc)}
            return False

    def _initialize_auto(self) -> bool:
        import logging

        _logger = logging.getLogger(__name__)

        if not _transformers_available:
            _logger.warning(
                "transformers not installed. Falling back to mock backend. "
                "Install with: pip install maref[ml]"
            )
            self._initialized = True
            self._actual_backend = "mock"
            self._backend_info = {
                "backend": "auto",
                "loaded": True,
                "model": "mock-v0",
                "fallback_reason": "transformers not installed",
            }
            return True

        model_id = self._config.get("model_id", "microsoft/OmniParser-v2.0")
        if not self._is_model_cached(model_id):
            _logger.warning(
                "OmniParser model not cached locally. Falling back to mock backend."
            )
            self._initialized = True
            self._actual_backend = "mock"
            self._backend_info = {
                "backend": "auto",
                "loaded": True,
                "model": "mock-v0",
                "fallback_reason": f"model {model_id} not cached",
            }
            return True

        try:
            self._init_omni_parser()
            self._initialized = True
            self._actual_backend = "omni_parser"
            return True
        except Exception as exc:
            _logger.warning(
                "OmniParser initialization failed: %s. Falling back to mock backend.", exc
            )
            self._initialized = True
            self._actual_backend = "mock"
            self._backend_info = {
                "backend": "auto",
                "loaded": True,
                "model": "mock-v0",
                "fallback_reason": str(exc),
            }
            return True

    @staticmethod
    def _is_model_cached(model_id: str) -> bool:
        try:
            import os as _os

            from huggingface_hub import try_to_load_from_cache

            for fname in ("config.json", "preprocessor_config.json"):
                cached = try_to_load_from_cache(model_id, fname)
                if cached and _os.path.exists(cached):
                    return True
            return False
        except (ImportError, Exception):
            import os as _os

            cache_path = _os.path.expanduser(f"~/.cache/huggingface/hub/models--{model_id.replace('/', '--')}")
            return _os.path.isdir(cache_path)

    def parse(
        self, screenshot_path: str, screen_width: int = 0, screen_height: int = 0
    ) -> ScreenParseResult:
        if not self._initialized:
            raise RuntimeError("OmniParserInterface not initialized. Call initialize() first.")
        backend = self._actual_backend
        if backend == "mock":
            return self._mock_parse(screen_width or 1920, screen_height or 1080)
        if backend == "omni_parser":
            return self._omni_parser_parse(screenshot_path, screen_width, screen_height)
        if backend == "cog_agent":
            return self._cog_agent_parse(screenshot_path, screen_width, screen_height)
        raise ValueError(f"Unknown backend: {backend}")

    # ── OmniParser (Microsoft) backend ──────────────────────────────────

    def _init_omni_parser(self) -> None:
        global _OMNI_PARSER_AVAILABLE
        if not _transformers_available:
            raise RuntimeError(
                "transformers library required for OmniParser. "
                "Install with: pip install maref[ml]"
            )

        model_id = self._config.get("model_id", "microsoft/OmniParser-v2.0")
        device = self._config.get("device", "cpu")
        torch_dtype = self._config.get("torch_dtype", "auto")

        self._processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)
        self._model = AutoModelForCausalLM.from_pretrained(
            model_id,
            trust_remote_code=True,
            torch_dtype=torch_dtype,
        ).to(device)
        self._model.eval()
        _OMNI_PARSER_AVAILABLE = True
        self._backend_info = {
            "backend": "omni_parser",
            "loaded": True,
            "model": model_id,
            "device": device,
        }

    def _omni_parser_parse(
        self, screenshot_path: str, screen_width: int, screen_height: int
    ) -> ScreenParseResult:
        if not _OMNI_PARSER_AVAILABLE or self._model is None:
            return self._mock_parse(screen_width, screen_height)

        import time as _time

        try:
            from PIL import Image as PILImage
        except ImportError:
            return self._mock_parse(screen_width, screen_height)

        t0 = _time.time()
        image = PILImage.open(screenshot_path).convert("RGB")
        if screen_width <= 0:
            screen_width = image.width
        if screen_height <= 0:
            screen_height = image.height

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {
                        "type": "text",
                        "text": (
                            "Detect all interactive UI elements in this screenshot. "
                            "For each element output: type, text, bbox [x1,y1,x2,y2], "
                            "interaction (clickable/typable/scrollable). "
                            "Output as JSON array."
                        ),
                    },
                ],
            }
        ]

        prompt = self._processor.apply_chat_template(messages, add_generation_prompt=True)
        inputs = self._processor(images=image, text=prompt, return_tensors="pt").to(
            self._model.device if hasattr(self._model, "device") else "cpu"
        )

        import torch

        with torch.no_grad():
            generated_ids = self._model.generate(**inputs, max_new_tokens=1024)

        generated_ids = generated_ids[:, inputs["input_ids"].shape[-1] :]
        raw_output = self._processor.batch_decode(generated_ids, skip_special_tokens=True)[0]

        elements = self._parse_omni_output(raw_output, screen_width, screen_height)
        elapsed = (_time.time() - t0) * 1000

        return ScreenParseResult(
            screen_width=screen_width,
            screen_height=screen_height,
            elements=elements,
            parse_time_ms=elapsed,
            model_name=self._backend_info.get("model", "omni-parser"),
            raw_output={"text": raw_output},
        )

    @staticmethod
    def _parse_omni_output(
        raw: str, screen_width: int, screen_height: int
    ) -> list[ParsedUIElement]:
        elements: list[ParsedUIElement] = []
        json_text = raw
        json_match = re.search(r"\[[\s\S]*\]", raw)
        if json_match:
            json_text = json_match.group(0)
        try:
            items = json.loads(json_text)
        except json.JSONDecodeError:
            items = OmniParserInterface._parse_omni_lines(raw)

        for idx, item in enumerate(items):
            elem_type = UIElementType.UNKNOWN
            type_str = str(item.get("type", item.get("element_type", ""))).lower()
            for et in UIElementType:
                if et.value in type_str or type_str == et.value:
                    elem_type = et
                    break

            text = str(item.get("text", item.get("label", "")))
            confidence = float(item.get("confidence", item.get("score", 0.95)))

            bbox_data = item.get("bbox", item.get("box", [0, 0, 0, 0]))
            if isinstance(bbox_data, str):
                bbox_data = [int(v) for v in bbox_data.replace("[", "").replace("]", "").split(",")]
            x1, y1, x2, y2 = (int(v) for v in bbox_data[:4])
            bbox = BoundingBox(x=x1, y=y1, width=max(1, x2 - x1), height=max(1, y2 - y1))

            interactions: list[InteractionType] = []
            inter_raw = item.get("interaction", item.get("interaction_types", []))
            if isinstance(inter_raw, str):
                inter_raw = [inter_raw]
            for it_str in inter_raw:
                val = str(it_str).lower().replace("_", "")
                if "click" in val:
                    interactions.append(InteractionType.CLICKABLE)
                if "type" in val or "input" in val or "text" in val:
                    interactions.append(InteractionType.TYPABLE)
                if "scroll" in val:
                    interactions.append(InteractionType.SCROLLABLE)
                if "drag" in val:
                    interactions.append(InteractionType.DRAGGABLE)
                if "hover" in val:
                    interactions.append(InteractionType.HOVERABLE)
                if "select" in val:
                    interactions.append(InteractionType.SELECTABLE)

            elements.append(
                ParsedUIElement(
                    element_type=elem_type,
                    bbox=bbox,
                    text=text,
                    confidence=confidence,
                    interaction_types=interactions,
                    element_id=str(item.get("id", item.get("element_id", f"elem_{idx:04d}"))),
                )
            )
        return elements

    @staticmethod
    def _parse_omni_lines(raw: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for line in raw.strip().split("\n"):
            line = line.strip().lstrip("- ").lstrip("* ")
            if not line:
                continue
            bbox_match = re.findall(r"\[?\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\]?", line)
            type_match = re.search(
                r"\b(button|text.?field|checkbox|radio|dropdown|link|image|tab"
                r"|menu.?item|slider|scroll.?bar|icon|label|window|dialog)\b",
                line,
                re.IGNORECASE,
            )
            text_match = re.search(r'"([^"]*)"', line)
            items.append(
                {
                    "type": type_match.group(1) if type_match else "unknown",
                    "text": text_match.group(1) if text_match else "",
                    "bbox": bbox_match[0] if bbox_match else [0, 0, 100, 40],
                    "confidence": 0.85,
                }
            )
        return items

    # ── CogAgent (THUDM) backend ────────────────────────────────────────

    def _init_cog_agent(self) -> None:
        global _COG_AGENT_AVAILABLE
        if not _transformers_available:
            raise RuntimeError(
                "transformers library required for CogAgent. "
                "Install with: pip install maref[ml]"
            )

        model_id = self._config.get("model_id", "THUDM/cogagent-vqa-hf")
        device = self._config.get("device", "cpu")

        self._processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)
        self._model = AutoModelForCausalLM.from_pretrained(
            model_id,
            trust_remote_code=True,
            torch_dtype=self._config.get("torch_dtype", "auto"),
        ).to(device)
        self._model.eval()
        _COG_AGENT_AVAILABLE = True
        self._backend_info = {
            "backend": "cog_agent",
            "loaded": True,
            "model": model_id,
            "device": device,
        }

    def _cog_agent_parse(
        self, screenshot_path: str, screen_width: int, screen_height: int
    ) -> ScreenParseResult:
        if not _COG_AGENT_AVAILABLE or self._model is None:
            return self._mock_parse(screen_width, screen_height)

        import time as _time

        try:
            from PIL import Image as PILImage
        except ImportError:
            return self._mock_parse(screen_width, screen_height)

        t0 = _time.time()
        image = PILImage.open(screenshot_path).convert("RGB")
        if screen_width <= 0:
            screen_width = image.width
        if screen_height <= 0:
            screen_height = image.height

        query = "What interactive UI elements are visible? Return JSON."
        inputs = self._model.build_conversation_input_ids(
            self._processor, query=query, history=[], images=[image]
        )
        inputs = {k: v.to(self._model.device) if hasattr(v, "to") else v for k, v in inputs.items()}

        import torch

        with torch.no_grad():
            outputs = self._model.generate(**inputs, max_new_tokens=1024)

        raw_output = self._processor.decode(outputs[0], skip_special_tokens=True)
        elements = self._parse_omni_output(raw_output, screen_width, screen_height)
        elapsed = (_time.time() - t0) * 1000

        return ScreenParseResult(
            screen_width=screen_width,
            screen_height=screen_height,
            elements=elements,
            parse_time_ms=elapsed,
            model_name=self._backend_info.get("model", "cog-agent"),
            raw_output={"text": raw_output},
        )

    # ── Mock backend ────────────────────────────────────────────────────

    def _mock_parse(self, screen_width: int, screen_height: int) -> ScreenParseResult:
        return ScreenParseResult(
            screen_width=screen_width,
            screen_height=screen_height,
            elements=[
                ParsedUIElement(
                    element_type=UIElementType.BUTTON,
                    bbox=BoundingBox(x=100, y=200, width=120, height=40),
                    text="Submit",
                    confidence=0.98,
                    interaction_types=[InteractionType.CLICKABLE],
                    element_id="btn_001",
                ),
                ParsedUIElement(
                    element_type=UIElementType.TEXT_FIELD,
                    bbox=BoundingBox(x=100, y=100, width=300, height=30),
                    text="Enter name...",
                    confidence=0.95,
                    interaction_types=[InteractionType.TYPABLE, InteractionType.CLICKABLE],
                    element_id="txt_001",
                ),
                ParsedUIElement(
                    element_type=UIElementType.CHECKBOX,
                    bbox=BoundingBox(x=100, y=300, width=20, height=20),
                    text="I agree",
                    confidence=0.99,
                    interaction_types=[InteractionType.CLICKABLE],
                    element_id="chk_001",
                ),
            ],
            parse_time_ms=5.0,
            model_name="mock-omni-parser-v0",
        )

    def benchmark(self, screenshot_path: str = "", num_runs: int = 5) -> dict[str, Any]:
        """Run a quick benchmark: returns avg latency and element count."""
        if not self._initialized:
            self.initialize()

        latencies: list[float] = []
        element_counts: list[int] = []

        for _ in range(num_runs):
            result = self.parse(screenshot_path, 0, 0)
            latencies.append(result.parse_time_ms)
            element_counts.append(len(result.elements))

        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        p99_latency = sorted(latencies)[int(len(latencies) * 0.99)] if len(latencies) > 1 else (latencies[0] if latencies else 0)

        return {
            "backend": self._actual_backend,
            "num_runs": num_runs,
            "avg_latency_ms": round(avg_latency, 1),
            "p99_latency_ms": round(p99_latency, 1),
            "avg_elements": sum(element_counts) / len(element_counts) if element_counts else 0,
            "model": self._backend_info.get("model", "unknown"),
        }
