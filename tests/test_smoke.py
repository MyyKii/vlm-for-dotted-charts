
"""Basic smoke tests for the project environment."""

import importlib.util

import pytest


@pytest.mark.parametrize(
    "module",
    [
        "torch",
        "torchvision",
        "transformers",
        "accelerate",
        "peft",
        "trl",
        "datasets",
        "PIL",
        "qwen_vl_utils",
    ],
)
def test_dependency_available(module):
    """Check that required Python packages are installed."""
    assert importlib.util.find_spec(module) is not None, (
        f"Missing dependency: {module}"
    )


def test_pytorch_cpu():
    """Verify that PyTorch can execute a basic CPU operation."""
    import torch

    tensor = torch.tensor([1.0, 2.0, 3.0], device="cpu")

    assert tensor.sum().item() == 6.0
