"""Checkpointing utility for Raphael training and processing scripts.

Ensures execution can resume automatically after interruptions without
recomputing finished units of work (e.g. per (material, area) pair or fold).
Supports --force to reset and recompute.
"""
import json
import logging
import pickle
import shutil
from pathlib import Path
from typing import Any, Optional, Set


class CheckpointManager:
    """Manages unit-level checkpointing for long-running workflows."""

    def __init__(
        self,
        script_name: str,
        checkpoint_dir: str = "checkpoints",
        force: bool = False,
        logger: Optional[logging.Logger] = None,
    ):
        """Initialize the checkpoint manager.

        Args:
            script_name: Name of the active script (determines checkpoint directory).
            checkpoint_dir: Base directory for checkpoints.
            force: If True, existing checkpoints for this script are wiped.
            logger: Optional logger for emitting checkpoint status.
        """
        self.script_name = Path(script_name).stem
        self.dir = Path(checkpoint_dir) / self.script_name
        self.force = force
        self.logger = logger or logging.getLogger("CheckpointManager")

        if self.force and self.dir.exists():
            self.logger.warning(f"[Force mode] Clearing existing checkpoints in {self.dir}")
            shutil.rmtree(self.dir)

        self.dir.mkdir(parents=True, exist_ok=True)

    def _sanitize_unit_id(self, unit_id: str) -> str:
        """Sanitize unit id for safe filesystem usage."""
        return unit_id.replace("/", "_").replace("\\", "_").replace(" ", "_").replace(":", "_")

    def get_unit_path(self, unit_id: str, extension: str = "pkl") -> Path:
        """Get the file path for a given unit checkpoint."""
        clean_id = self._sanitize_unit_id(unit_id)
        return self.dir / f"{clean_id}.{extension}"

    def is_completed(self, unit_id: str) -> bool:
        """Check if a checkpoint exists for the given unit."""
        if self.force:
            return False
        clean_id = self._sanitize_unit_id(unit_id)
        matches = list(self.dir.glob(f"{clean_id}.*"))
        return len(matches) > 0

    def get_completed_units(self) -> Set[str]:
        """Return a set of all completed unit IDs."""
        if self.force or not self.dir.exists():
            return set()
        return {f.stem for f in self.dir.iterdir() if f.is_file()}

    def save_unit(self, unit_id: str, data: Any, format_type: str = "pkl") -> Path:
        """Save a unit's intermediate or final result to disk.

        Args:
            unit_id: Unique identifier for the work unit (e.g. material_area).
            data: Arbitrary serializable payload.
            format_type: 'pkl' or 'json'.
        """
        file_path = self.get_unit_path(unit_id, extension=format_type)
        temp_path = file_path.with_suffix(f".{format_type}.tmp")

        if format_type == "json":
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        else:
            with open(temp_path, "wb") as f:
                pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)

        # Atomic rename to prevent corrupt files on abrupt termination
        temp_path.replace(file_path)
        return file_path

    def load_unit(self, unit_id: str, format_type: str = "pkl") -> Any:
        """Load a unit's saved checkpoint."""
        file_path = self.get_unit_path(unit_id, extension=format_type)
        if not file_path.exists():
            raise FileNotFoundError(f"Checkpoint not found for unit '{unit_id}' at {file_path}")

        if format_type == "json":
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            with open(file_path, "rb") as f:
                return pickle.load(f)
