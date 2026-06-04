"""本地模型适配器 — 使用 transformers 运行本地模型。"""

from __future__ import annotations

from typing import Any

from maref.execution.adapters.base import ModelAdapter


class LocalModelAdapter(ModelAdapter):
    """本地 transformers 模型适配器。"""

    def __init__(self, model_name: str = "microsoft/phi-2") -> None:
        self._model_name = model_name
        self._model = None
        self._tokenizer = None

    def _lazy_init(self) -> None:
        if self._model is not None:
            return
        try:
            import transformers
            self._tokenizer = transformers.AutoTokenizer.from_pretrained(self._model_name)
            self._model = transformers.AutoModelForCausalLM.from_pretrained(self._model_name)
        except ImportError:
            raise RuntimeError("transformers not installed")

    def complete(self, prompt: str, **kwargs: Any) -> str:
        self._lazy_init()
        import torch
        inputs = self._tokenizer(prompt, return_tensors="pt")
        max_length = kwargs.get("max_length", 200)
        with torch.no_grad():
            outputs = self._model.generate(**inputs, max_length=max_length)
        return self._tokenizer.decode(outputs[0], skip_special_tokens=True)

    @property
    def model_name(self) -> str:
        return self._model_name

    def count_tokens(self, text: str) -> int:
        self._lazy_init()
        return len(self._tokenizer.encode(text))
