"""Runtime output config: parse + validate the config itself.

The config is OPERATOR input (not candidate data), so a broken config is a hard
error (ConfigError) — unlike a garbage data source, which we skip. We validate
the config's own shape with pydantic so a typo'd config fails fast and clearly.

Shape:
  {
    "fields": [
      {"path": "...", "from": "...", "type": "...", "required": bool,
       "normalize": "...", "on_missing": "null|omit|error"},
      ...
    ],
    "include_provenance": bool,
    "include_confidence": bool,
    "on_missing": "null|omit|error"
  }

If "fields" is empty/absent, the pipeline emits the FULL canonical profile
(default schema), honoring the include_* toggles.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

OnMissing = Literal["null", "omit", "error"]


class ConfigError(Exception):
    """Raised when the config file is unreadable or structurally invalid."""


class FieldSpec(BaseModel):
    # populate_by_name lets us accept the JSON key "from" (a Python keyword)
    # via the alias while using `from_` in code.
    model_config = ConfigDict(populate_by_name=True)

    path: str                                  # output key (may be dotted to nest)
    from_: str | None = Field(default=None, alias="from")  # canonical source path
    type: str                                  # declared output type (validated later)
    required: bool = False
    normalize: str | None = None               # E164 | canonical | iso2 | yyyy_mm
    on_missing: OnMissing | None = None         # per-field override of global

    @property
    def source_path(self) -> str:
        """Where to read from in the canonical profile (defaults to `path`)."""
        return self.from_ or self.path


class OutputConfig(BaseModel):
    fields: list[FieldSpec] = Field(default_factory=list)
    include_provenance: bool = False
    include_confidence: bool = False
    on_missing: OnMissing = "null"


def load_config(path: str) -> OutputConfig:
    """Read + validate a config file. Raises ConfigError on any problem."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"cannot read config {path}: {exc}") from exc
    try:
        return OutputConfig.model_validate(data)
    except Exception as exc:  # pydantic ValidationError -> friendly message
        raise ConfigError(f"invalid config {path}: {exc}") from exc


# Used when no --config is supplied: emit the full canonical profile.
DEFAULT_CONFIG = OutputConfig(include_provenance=True, include_confidence=True)
