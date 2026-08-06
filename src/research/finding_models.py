import statistics
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StructuredFinding:
    name: str
    value: float
    timestamp: float
    metadata: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.value, (int, float)):
            raise TypeError('value must be numeric')
        if not isinstance(self.timestamp, (int, float)):
            raise TypeError('timestamp must be numeric')

    def to_finding_string(self) -> str:
        return f'{self.name}: {self.value} @ {self.timestamp}'

    def to_dict(self) -> dict[str, Any]:
        return {'name': self.name, 'value': self.value, 'timestamp': self.timestamp, 'metadata': self.metadata, 'tags': self.tags}

def findings_to_strings(findings: list[StructuredFinding]) -> list[str]:
    return [f.to_finding_string() for f in findings]

def extract_structured(data: list[dict[str, Any]]) -> list[StructuredFinding]:
    result: list[StructuredFinding] = []
    for item in data:
        try:
            finding = StructuredFinding(name=str(item['name']), value=float(item['value']), timestamp=float(item['timestamp']), metadata=item.get('metadata', {}), tags=list(item.get('tags', [])))
            result.append(finding)
        except (KeyError, TypeError, ValueError):
            continue
    return result

def mean(findings: list[StructuredFinding]) -> float | None:
    if not findings:
        return None
    values = [f.value for f in findings]
    return statistics.mean(values)

def min(findings: list[StructuredFinding]) -> float | None:
    if not findings:
        return None
    values = [f.value for f in findings]
    return min(values)  # type: ignore[arg-type]

def max(findings: list[StructuredFinding]) -> float | None:
    if not findings:
        return None
    values = [f.value for f in findings]
    return max(values)  # type: ignore[arg-type]

def latest(findings: list[StructuredFinding]) -> StructuredFinding | None:
    if not findings:
        return None
    return max(findings, key=lambda f: f.timestamp)  # type: ignore[call-arg, return-value]
