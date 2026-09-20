"""Regression test for firewing/model/loader.py's model-class resolution.

Reproduces the exact bug reported in the field:

    ValueError: Unrecognized configuration class
    <class '...Qwen3OmniMoeConfig'> for this kind of AutoModel:
    AutoModelForCausalLM.

The loader used to hard-code AutoModelForCausalLM for every checkpoint.
Multimodal/omni checkpoints (the default FIREWING base model,
Qwen/Qwen3-Omni-30B-A3B-Instruct) need a different class
(Qwen3OmniMoeForConditionalGeneration) that AutoModelForCausalLM doesn't
know how to resolve. This test builds fake `torch`/`transformers` modules
that reproduce that exact failure mode for AutoModelForCausalLM while
succeeding for the correct class, then asserts `load_model()` picks the
right one — for both a multimodal checkpoint and an ordinary text-only
one. No real torch/transformers/network/weights are needed.
"""

from __future__ import annotations

import sys
import types

import pytest


class _FakeModel:
    """Stands in for a real nn.Module — just enough surface for load_model
    (`.to(device)` / `.eval()`) without pulling in torch."""

    def __init__(self, label: str):
        self.label = label

    def to(self, device):  # noqa: D102 — trivial passthrough
        return self

    def eval(self):  # noqa: D102 — trivial passthrough
        return self

    def __repr__(self) -> str:
        return self.label


class _FakeConfig:
    def __init__(self, architectures):
        self.architectures = architectures


@pytest.fixture
def fake_transformers(monkeypatch):
    """Install fake `torch` + `transformers` modules in sys.modules that
    reproduce the real-world bug, then yield control to the test. Cleans
    up after itself via monkeypatch's automatic sys.modules restoration.
    """
    torch_mod = types.ModuleType("torch")
    torch_mod.bfloat16 = "bfloat16-dtype"
    torch_mod.float32 = "float32-dtype"

    class _CudaNS:
        @staticmethod
        def is_available():
            return False

    torch_mod.cuda = _CudaNS()

    transformers_mod = types.ModuleType("transformers")

    class AutoConfig:
        @staticmethod
        def from_pretrained(model_path, trust_remote_code=False):
            if "omni" in model_path.lower():
                return _FakeConfig(["Qwen3OmniMoeForConditionalGeneration"])
            return _FakeConfig(["Qwen3ForCausalLM"])

    class AutoTokenizer:
        @staticmethod
        def from_pretrained(model_path, trust_remote_code=False):
            return "FAKE_TOKENIZER"

    class AutoModelForCausalLM:
        """Reproduces the real bug: blows up on the omni config, exactly
        like the upstream `transformers` error the user hit."""

        @classmethod
        def from_pretrained(cls, model_path, **kwargs):
            if "omni" in model_path.lower():
                raise ValueError(
                    "Unrecognized configuration class Qwen3OmniMoeConfig for "
                    "this kind of AutoModel: AutoModelForCausalLM."
                )
            return _FakeModel(f"MODEL[AutoModelForCausalLM]({model_path})")

    class Qwen3OmniMoeForConditionalGeneration:
        """The class the loader *should* pick for the omni checkpoint."""

        @classmethod
        def from_pretrained(cls, model_path, **kwargs):
            assert "dtype" in kwargs or "torch_dtype" in kwargs
            return _FakeModel(
                f"MODEL[Qwen3OmniMoeForConditionalGeneration]({model_path})"
            )

    class Qwen3ForCausalLM:
        @classmethod
        def from_pretrained(cls, model_path, **kwargs):
            return _FakeModel(f"MODEL[Qwen3ForCausalLM]({model_path})")

    class AutoProcessor:
        @staticmethod
        def from_pretrained(model_path, trust_remote_code=False):
            raise RuntimeError("no processor in this fake environment")

    transformers_mod.AutoConfig = AutoConfig
    transformers_mod.AutoTokenizer = AutoTokenizer
    transformers_mod.AutoModelForCausalLM = AutoModelForCausalLM
    transformers_mod.Qwen3OmniMoeForConditionalGeneration = (
        Qwen3OmniMoeForConditionalGeneration
    )
    transformers_mod.Qwen3ForCausalLM = Qwen3ForCausalLM
    transformers_mod.AutoProcessor = AutoProcessor

    monkeypatch.setitem(sys.modules, "torch", torch_mod)
    monkeypatch.setitem(sys.modules, "transformers", transformers_mod)

    # firewing.model.loader only imports torch/transformers *inside* its
    # functions, so no reload gymnastics are needed here — the fakes above
    # are picked up on the next call into load_model().
    yield


def test_omni_checkpoint_loads_via_correct_class(fake_transformers):
    from firewing.config.settings import ModelConfig
    from firewing.model.loader import load_model

    cfg = ModelConfig(
        model_path="Qwen/Qwen3-Omni-30B-A3B-Instruct", enable_multimodal=False
    )
    result = load_model(cfg)
    assert result.model.label == (
        "MODEL[Qwen3OmniMoeForConditionalGeneration]"
        "(Qwen/Qwen3-Omni-30B-A3B-Instruct)"
    )


def test_plain_text_checkpoint_still_loads_via_causal_lm(fake_transformers):
    from firewing.config.settings import ModelConfig
    from firewing.model.loader import load_model

    cfg = ModelConfig(model_path="Qwen/Qwen3-8B", enable_multimodal=False)
    result = load_model(cfg)
    assert result.model.label == "MODEL[Qwen3ForCausalLM](Qwen/Qwen3-8B)"
