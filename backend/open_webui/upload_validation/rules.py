"""Configurable sensitivity detection rules (defaults + optional JSON merge)."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

log = logging.getLogger(__name__)


@dataclass
class CompiledPattern:
    name: str
    pattern: re.Pattern


@dataclass
class DetectionRules:
    """Extend by editing JSON or subclassing merge_defaults."""

    metadata_blocked_substrings: list[str] = field(default_factory=list)
    filename_blocked_substrings: list[str] = field(default_factory=list)
    content_keywords: list[str] = field(default_factory=list)
    patterns: list[CompiledPattern] = field(default_factory=list)

    def merge_from_dict(self, data: dict[str, Any]) -> None:
        if mb := data.get("metadata_blocked_substrings"):
            self.metadata_blocked_substrings = self._norm_str_list(mb)
        if fb := data.get("filename_blocked_substrings"):
            self.filename_blocked_substrings = self._norm_str_list(fb)
        if ck := data.get("content_keywords"):
            self.content_keywords = self._norm_str_list(ck)
        if plist := data.get("content_patterns"):
            compiled: list[CompiledPattern] = []
            for item in plist:
                if isinstance(item, dict) and item.get("name") and item.get("pattern"):
                    try:
                        compiled.append(
                            CompiledPattern(
                                name=str(item["name"]),
                                pattern=re.compile(
                                    str(item["pattern"]), re.IGNORECASE | re.MULTILINE
                                ),
                            )
                        )
                    except re.error as e:
                        log.warning("Invalid regex in rules %s: %s", item.get("name"), e)
            if compiled:
                self.patterns = compiled

    @staticmethod
    def _norm_str_list(items: Iterable[Any]) -> list[str]:
        out = []
        for x in items:
            s = str(x).strip()
            if s:
                out.append(s)
        return out


def default_rules_dict() -> dict[str, Any]:
    """Baseline rules — conservative keyword/pattern lists (extend via JSON)."""
    return {
        "metadata_blocked_substrings": [
            "bank",
            "account",
            "aadhaar",
            "ssn",
            "social security",
            "confidential",
            "restricted",
            "classified",
            "top secret",
            "secret",
            "cui",
            "controlled unclassified",
            "phi",
            "protected health",
            "hipaa",
            "itar",
            "export controlled",
            "proprietary",
            "internal only",
            "do not distribute",
            "no foreign nationals",
            "law enforcement sensitive",
            "fouo",
            "sbu",
        ],
        "filename_blocked_substrings": [
            "bank",
            "account",
            "aadhaar",
            "ssn",
            "social security",
            "confidential",
            "classified",
            "secret",
            "restricted",
            "phi",
            "hipaa",
            "pii",
        ],
        "content_keywords": [
            "social security number",
            "ssn:",
            "credit card number",
            "cvv",
            "bank routing",
            "routing number",
            "bank account",
            "account number",
            "aadhaar",
            "ifsc",
            "sort code",
            "swift code",
            "-----begin rsa private key-----",
            "-----begin openssh private key-----",
            "api_key=",
            "apikey=",
            "password=",
            "patient ssn",
            "diagnosis:",
            "mrn:",
        ],
        "content_patterns": [
            {"name": "ssn_us_dashed", "pattern": r"\b\d{3}-\d{2}-\d{4}\b"},
        ],
    }


def rules_from_defaults() -> DetectionRules:
    r = DetectionRules()
    raw = default_rules_dict()
    r.metadata_blocked_substrings = DetectionRules._norm_str_list(
        raw["metadata_blocked_substrings"]
    )
    r.filename_blocked_substrings = DetectionRules._norm_str_list(
        raw["filename_blocked_substrings"]
    )
    r.content_keywords = DetectionRules._norm_str_list(raw["content_keywords"])
    r.merge_from_dict({"content_patterns": raw["content_patterns"]})
    return r


def load_rules(optional_json_path: str | None) -> DetectionRules:
    """Defaults merged with optional JSON file (same keys as default_rules_dict)."""
    rules = rules_from_defaults()
    if not optional_json_path:
        return rules
    path = Path(optional_json_path)
    if not path.is_file():
        log.debug("Sensitivity rules file not found: %s", path)
        return rules
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            rules.merge_from_dict(data)
            log.info("Loaded upload sensitivity rules from %s", path)
    except Exception as e:
        log.warning("Could not load sensitivity rules %s: %s", path, e)
    return rules


def load_rules_from_env() -> DetectionRules:
    return load_rules(os.environ.get("UPLOAD_SENSITIVITY_RULES_PATH", "").strip() or None)
