"""Backward-compatibility shim — logic lives in services/pipeline/."""

from services.pipeline.runner import run_pipeline_stages

__all__ = ["run_pipeline_stages"]
