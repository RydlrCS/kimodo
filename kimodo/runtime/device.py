"""Card 9 runtime device bootstrap helpers (AMD/ROCm-friendly)."""

from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass
from typing import Optional

import torch

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class RuntimeHealthReport:
    """Runtime/backend detection report for startup health checks."""

    requested_device: str
    selected_device: str
    backend: str
    cuda_available: bool
    rocm_available: bool
    mps_available: bool
    strict_mode: bool
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _normalize_requested_device(requested: Optional[str]) -> str:
    value = requested or os.environ.get("KIMODO_DEVICE") or os.environ.get("DEVICE") or "auto"
    return str(value).strip().lower()


def _has_mps() -> bool:
    backends = getattr(torch, "backends", None)
    mps = getattr(backends, "mps", None)
    if mps is None:
        return False
    is_available = getattr(mps, "is_available", None)
    if callable(is_available):
        try:
            return bool(is_available())
        except Exception:  # pragma: no cover
            return False
    return False


def _backend_name(cuda_available: bool, rocm_available: bool, mps_available: bool) -> str:
    if rocm_available:
        return "rocm"
    if cuda_available:
        return "cuda"
    if mps_available:
        return "mps"
    return "cpu"


def select_runtime_device(requested: Optional[str] = None) -> str:
    """Resolve runtime device with ROCm/CUDA/CPU fallback.

    Resolution order:
    - explicit requested argument
    - environment variable KIMODO_DEVICE (or DEVICE)
    - auto

    If KIMODO_STRICT_DEVICE=true and requested accelerator is unavailable, raises ValueError.
    """
    LOGGER.info("card9.select_runtime_device.start requested=%s", requested)
    strict_mode = _env_bool("KIMODO_STRICT_DEVICE", default=False)
    req = _normalize_requested_device(requested)

    cuda_available = bool(torch.cuda.is_available())
    rocm_available = cuda_available and bool(getattr(torch.version, "hip", None))
    mps_available = _has_mps()

    accelerator_aliases = {"cuda", "cuda:0", "gpu", "rocm", "hip", "amd"}

    if req == "cpu":
        selected = "cpu"
        reason = "explicit_cpu"
    elif req in ("mps", "apple"):
        if mps_available:
            selected = "mps"
            reason = "explicit_mps"
        elif strict_mode:
            raise ValueError("Requested MPS device but MPS backend is unavailable")
        else:
            selected = "cpu"
            reason = "mps_unavailable_fallback_cpu"
    elif req in accelerator_aliases:
        if cuda_available:
            selected = "cuda:0"
            reason = "explicit_accelerator_available"
        elif strict_mode:
            raise ValueError(f"Requested accelerator '{req}' but no torch accelerator is available")
        else:
            selected = "cpu"
            reason = "accelerator_unavailable_fallback_cpu"
    elif req == "auto":
        if cuda_available:
            selected = "cuda:0"
            reason = "auto_accelerator"
        elif mps_available:
            selected = "mps"
            reason = "auto_mps"
        else:
            selected = "cpu"
            reason = "auto_cpu"
    else:
        # Preserve explicit torch device strings (e.g. cuda:1, cpu) when possible.
        if req.startswith("cuda"):
            if cuda_available:
                selected = req
                reason = "explicit_cuda_index"
            elif strict_mode:
                raise ValueError(f"Requested device '{req}' but CUDA/ROCm backend is unavailable")
            else:
                selected = "cpu"
                reason = "explicit_cuda_unavailable_fallback_cpu"
        else:
            if strict_mode:
                raise ValueError(f"Unknown device specifier '{req}'")
            selected = "cpu"
            reason = "unknown_device_fallback_cpu"

    LOGGER.info("card9.select_runtime_device.exit selected=%s reason=%s", selected, reason)
    return selected


def runtime_health_report(requested: Optional[str] = None) -> RuntimeHealthReport:
    """Return a startup runtime report suitable for health checks and logs."""
    LOGGER.info("card9.runtime_health_report.start requested=%s", requested)

    strict_mode = _env_bool("KIMODO_STRICT_DEVICE", default=False)
    req = _normalize_requested_device(requested)
    cuda_available = bool(torch.cuda.is_available())
    rocm_available = cuda_available and bool(getattr(torch.version, "hip", None))
    mps_available = _has_mps()

    selected = select_runtime_device(req)
    reason = "ok"
    if selected == "cpu" and req in {"cuda", "cuda:0", "gpu", "rocm", "hip", "amd"}:
        reason = "fallback_cpu"

    report = RuntimeHealthReport(
        requested_device=req,
        selected_device=selected,
        backend=_backend_name(cuda_available, rocm_available, mps_available),
        cuda_available=cuda_available,
        rocm_available=rocm_available,
        mps_available=mps_available,
        strict_mode=strict_mode,
        reason=reason,
    )
    LOGGER.info(
        "card9.runtime_health_report.exit requested=%s selected=%s backend=%s reason=%s",
        report.requested_device,
        report.selected_device,
        report.backend,
        report.reason,
    )
    return report