from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import statistics

@dataclass
class StructuredFinding:
    name: str
    value: float
    timestamp: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.value, (int, float)):
            raise TypeError('value must be numeric')
        if not isinstance(self.timestamp, (int, float)):
            raise TypeError('timestamp must be numeric')

    def to_finding_string(self) -> str:
        return f'{self.name}: {self.value} @ {self.timestamp}'

    def to_dict(self) -> Dict[str, Any]:
        return {'name': self.name, 'value': self.value, 'timestamp': self.timestamp, 'metadata': self.metadata, 'tags': self.tags}

def findings_to_strings(findings: List[StructuredFinding]) -> List[str]:
    return [f.to_finding_string() for f in findings]

def extract_structured(data: List[Dict[str, Any]]) -> List[StructuredFinding]:
    result: List[StructuredFinding] = []
    for item in data:
        try:
            finding = StructuredFinding(name=str(item['name']), value=float(item['value']), timestamp=float(item['timestamp']), metadata=item.get('metadata', {}), tags=list(item.get('tags', [])))
            result.append(finding)
        except (KeyError, TypeError, ValueError):
            continue
    return result

def mean(findings: List[StructuredFinding]) -> Optional[float]:
    if not findings:
        return None
    values = [f.value for f in findings]
    return statistics.mean(values)

def min(findings: List[StructuredFinding]) -> Optional[float]:
    if not findings:
        return None
    values = [f.value for f in findings]
    return min(values)

def max(findings: List[StructuredFinding]) -> Optional[float]:
    if not findings:
        return None
    values = [f.value for f in findings]
    return max(values)

def latest(findings: List[StructuredFinding]) -> Optional[StructuredFinding]:
    if not findings:
        return None
    return max(findings, key=lambda f: f.timestamp)