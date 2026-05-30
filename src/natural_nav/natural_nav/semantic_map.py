"""
In-memory semantic map: label -> 2D pose in the map frame.

Producer: semantic_detector publishes a JSON snapshot on /natural_nav/semantic_map.
Consumer: task_executor maintains a local SemanticMap and queries by label.

A label can resolve to multiple observed positions over time (the robot may
see the same object from different angles). We keep a small ring of recent
observations and return their running mean as the canonical pose.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Iterable


MAX_OBSERVATIONS_PER_LABEL = 10


@dataclass
class LabelEntry:
    label: str
    observations: list[tuple[float, float, float]] = field(default_factory=list)

    def add(self, x: float, y: float, confidence: float) -> None:
        self.observations.append((x, y, confidence))
        if len(self.observations) > MAX_OBSERVATIONS_PER_LABEL:
            self.observations = self.observations[-MAX_OBSERVATIONS_PER_LABEL:]

    def pose(self) -> tuple[float, float] | None:
        if not self.observations:
            return None
        total_w = sum(o[2] for o in self.observations) or 1.0
        x = sum(o[0] * o[2] for o in self.observations) / total_w
        y = sum(o[1] * o[2] for o in self.observations) / total_w
        return (x, y)

    def best_confidence(self) -> float:
        return max((o[2] for o in self.observations), default=0.0)


class SemanticMap:
    def __init__(self):
        self._entries: dict[str, LabelEntry] = {}

    def update(self, label: str, x: float, y: float, confidence: float = 1.0) -> None:
        label = label.strip().lower()
        if label not in self._entries:
            self._entries[label] = LabelEntry(label=label)
        self._entries[label].add(x, y, confidence)

    def lookup(self, label: str) -> tuple[float, float] | None:
        """Exact lookup of a label's canonical pose. Case-insensitive."""
        entry = self._entries.get(label.strip().lower())
        return entry.pose() if entry else None

    def fuzzy_lookup(self, query: str) -> tuple[str, tuple[float, float]] | None:
        """Substring match for natural-language queries like 'red box near workstation'.
        Returns (matched_label, pose) of the highest-confidence partial match, or None."""
        q = query.strip().lower()
        candidates: list[tuple[float, str, tuple[float, float]]] = []
        for label, entry in self._entries.items():
            if label in q or q in label or any(w in label for w in q.split()):
                pose = entry.pose()
                if pose is not None:
                    candidates.append((entry.best_confidence(), label, pose))
        if not candidates:
            return None
        candidates.sort(reverse=True)
        _, label, pose = candidates[0]
        return label, pose

    def labels(self) -> Iterable[str]:
        return self._entries.keys()

    def to_dict(self) -> dict:
        return {
            label: {
                'pose': list(entry.pose()) if entry.pose() else None,
                'confidence': entry.best_confidence(),
                'observation_count': len(entry.observations),
            }
            for label, entry in self._entries.items()
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def load_dict(self, data: dict) -> None:
        """Replace contents from a snapshot dict (as produced by to_dict)."""
        self._entries.clear()
        for label, info in data.items():
            pose = info.get('pose')
            if pose is None:
                continue
            self.update(label, float(pose[0]), float(pose[1]),
                        confidence=float(info.get('confidence', 1.0)))

    @classmethod
    def from_json(cls, raw: str) -> 'SemanticMap':
        m = cls()
        m.load_dict(json.loads(raw))
        return m

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, label: str) -> bool:
        return label.strip().lower() in self._entries

    def distance(self, label: str, x: float, y: float) -> float | None:
        pose = self.lookup(label)
        if pose is None:
            return None
        return math.hypot(pose[0] - x, pose[1] - y)
