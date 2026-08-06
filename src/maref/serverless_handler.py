"""MAREF Serverless runtime adapters for AWS Lambda and GCP Cloud Run."""
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ServerlessEvent:
    """Generic serverless event envelope."""
    event_id: str = ''
    action: str = ''
    payload: dict[str, Any] = field(default_factory=dict)
    source: str = ''

@dataclass
class ServerlessResponse:
    status_code: int = 200
    body: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {'statusCode': self.status_code, 'body': json.dumps(self.body), 'headers': self.headers}

class LambdaHandler:
    """AWS Lambda handler adapter for MAREF governance checks."""

    def __init__(self) -> None:
        self._cold_start = True

    def handle(self, event: dict[str, Any], context: Any=None) -> dict[str, Any]:
        was_cold = self._cold_start
        self._cold_start = False
        se = ServerlessEvent(event_id=event.get('event_id', ''), action=event.get('action', 'governance_status'), payload=event.get('payload', {}))
        result = {'action': se.action, 'state': 'HEALTHY', 'cold_start': was_cold}
        resp = ServerlessResponse(body=result)
        return resp.to_dict()

class CloudRunHandler:
    """GCP Cloud Run handler adapter for MAREF governance."""

    def __init__(self) -> None:
        self._ready = True

    def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        action = request.get('action', 'governance_status')
        return {'status': 'ok', 'action': action, 'runtime': 'cloud_run'}
