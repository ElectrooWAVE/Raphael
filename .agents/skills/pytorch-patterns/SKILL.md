---
name: pytorch-patterns
description: PyTorch deep learning patterns and best practices for building robust, efficient, and reproducible training pipelines, model architectures, and data loading. Use when writing or reviewing PyTorch training loops, model architectures, or data loading, or when a run will not reproduce.
metadata:
  origin: ECC
---

# PyTorch Development Patterns

Idiomatic PyTorch patterns and best practices for building robust, efficient, and reproducible deep learning applications.

## Core Principles

1. **Device-Agnostic Code**:
   ```python
   device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
   ```
   Never hardcode `.cuda()` when CPU fallback or device selection is needed.
2. **Reproducibility**: Set `torch.manual_seed`, `torch.cuda.manual_seed_all`, `np.random.seed`, and `random.seed` when deterministic runs are required.
3. **Explicit Shape Management**: Document and verify tensor shapes at module and pipeline boundaries.

## Inference & Evaluation Best Practices

- Always call `model.eval()` and wrap inference in `@torch.no_grad()` or `with torch.no_grad():` so dropout is disabled and no autograd graph is allocated.
- Load pretrained models once at startup / resource cache rather than per request.
- Use `torch.load(..., map_location="cpu", weights_only=True)` when loading checkpoints.
- Move models to `device` once before loops, not inside iteration loops.
- Call `.item()` only for logging/scalar extraction after computation, never before `.backward()`.

## Training & Performance

- Use `optimizer.zero_grad(set_to_none=True)`.
- Use `torch.amp.autocast("cuda")` + `GradScaler` for mixed-precision training on CUDA.
- Use `DataLoader(..., pin_memory=True, num_workers=...)` for GPU data transfer.
- Avoid in-place operations (`inplace=True`, `+=`) on tensors that require gradients.
