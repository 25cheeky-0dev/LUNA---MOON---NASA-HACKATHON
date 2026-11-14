"""Operator-configured dataset registry; API callers cannot supply filesystem paths."""

import json
import os
import threading
from pathlib import Path

from .errors import DatasetError
from .loader import ParquetDataset


class DatasetRegistry:
    def __init__(self, entries=()):
        self.entries, self.loaded, self.lock = {}, {}, threading.RLock()
        if len(entries) > 128:
            raise DatasetError(
                "REGISTRY_BUDGET_EXCEEDED", "At most 128 registered datasets per process"
            )
        for entry in entries:
            if (
                not isinstance(entry, dict)
                or not isinstance(entry.get("root"), str)
                or not entry["root"]
            ):
                raise DatasetError(
                    "INVALID_REGISTRY", "Each dataset needs an explicit nonempty directory root"
                )
            for name in ("max_cells", "max_tiles", "cached_tiles"):
                if name in entry and (type(entry[name]) is not int or entry[name] < 1):
                    raise DatasetError(
                        "INVALID_REGISTRY", "Dataset resource budgets must be positive integers"
                    )
            dataset_id = entry["dataset_id"]
            if not isinstance(dataset_id, str) or not dataset_id or dataset_id in self.entries:
                raise DatasetError(
                    "INVALID_REGISTRY", "Registry dataset IDs must be unique strings"
                )
            if set(entry) - {
                "dataset_id",
                "root",
                "adapter",
                "max_cells",
                "max_tiles",
                "cached_tiles",
            }:
                raise DatasetError("INVALID_REGISTRY", "Unknown registry configuration field")
            self.entries[dataset_id] = dict(entry)

    @classmethod
    def from_environment(cls):
        configured = os.getenv("WISPR_DATASETS_CONFIG")
        if not configured:
            return cls()
        try:
            path = Path(configured).resolve()
            config = json.loads(path.read_bytes())
            if config.get("schema_version") != "1.0":
                raise DatasetError(
                    "UNSUPPORTED_REGISTRY_VERSION", "Registry schema_version must be 1.0"
                )
            entries = []
            for entry in config["datasets"]:
                entries.append(entry | {"root": str((path.parent / entry["root"]).resolve())})
            return cls(entries)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            if isinstance(exc, DatasetError):
                raise
            raise DatasetError(
                "REGISTRY_UNAVAILABLE", "Dataset registry could not be read", 503
            ) from exc

    def get(self, dataset_id):
        with self.lock:
            if dataset_id not in self.entries:
                raise DatasetError("DATASET_NOT_FOUND", "Dataset ID is not registered", 404)
            if dataset_id not in self.loaded:
                entry = self.entries[dataset_id]
                self.loaded[dataset_id] = ParquetDataset(**entry)
            return self.loaded[dataset_id]

    def discover(self):
        results = []
        for dataset_id in self.entries:
            try:
                results.append(self.get(dataset_id).describe())
            except DatasetError as exc:
                results.append(
                    dict(
                        dataset_id=dataset_id,
                        status="UNAVAILABLE",
                        error_code=exc.code,
                        detail=exc.detail,
                    )
                )
        return dict(contract_version="1.0", datasets=results)
