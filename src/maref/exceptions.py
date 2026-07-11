from enum import Enum
from typing import Any

class ErrorCode(str, Enum):
    UNKNOWN = 'E0000'
    NOT_FOUND = 'E0001'
    VALIDATION_ERROR = 'E0002'
    PERMISSION_DENIED = 'E0003'
    RATE_LIMITED = 'E0004'
    INTERNAL_ERROR = 'E0005'
    NOT_IMPLEMENTED = 'E0006'
    CONFLICT = 'E0007'
    UNAUTHORIZED = 'E0008'
    QUOTA_EXCEEDED = 'E0009'
    SANDBOX_VIOLATION = 'E1001'
    GOVERNANCE_REJECTED = 'E1002'
    SAFETY_GATE_BLOCKED = 'E1003'
    CIRCUIT_BREAKER_OPEN = 'E1004'
    TRUST_CHAIN_BROKEN = 'E1005'
    TRANSITION_INVALID = 'E2001'
    EVOLUTION_FAILED = 'E2002'
    OBSERVATION_FAILED = 'E3001'
    MCP_ERROR = 'E4001'
    A2A_ERROR = 'E4002'
ERROR_HTTP_MAP: dict[ErrorCode, int] = {ErrorCode.UNKNOWN: 500, ErrorCode.NOT_FOUND: 404, ErrorCode.VALIDATION_ERROR: 400, ErrorCode.PERMISSION_DENIED: 403, ErrorCode.RATE_LIMITED: 429, ErrorCode.INTERNAL_ERROR: 500, ErrorCode.NOT_IMPLEMENTED: 501, ErrorCode.CONFLICT: 409, ErrorCode.UNAUTHORIZED: 401, ErrorCode.QUOTA_EXCEEDED: 429, ErrorCode.SANDBOX_VIOLATION: 403, ErrorCode.GOVERNANCE_REJECTED: 403, ErrorCode.SAFETY_GATE_BLOCKED: 403, ErrorCode.CIRCUIT_BREAKER_OPEN: 503, ErrorCode.TRUST_CHAIN_BROKEN: 403, ErrorCode.TRANSITION_INVALID: 400, ErrorCode.EVOLUTION_FAILED: 500, ErrorCode.OBSERVATION_FAILED: 500, ErrorCode.MCP_ERROR: 502, ErrorCode.A2A_ERROR: 502}

class MAREFError(Exception):

    def __init__(self, code: ErrorCode=ErrorCode.UNKNOWN, message: str='', details: dict[str, Any] | None=None) -> None:
        self.code = code
        self.http_status = ERROR_HTTP_MAP.get(code, 500)
        self.message = message or code.value
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        return {'error': {'code': self.code.value, 'message': self.message, 'details': self.details}}

    @classmethod
    def from_exception(cls, exc: Exception, code: ErrorCode=ErrorCode.INTERNAL_ERROR) -> MAREFError:
        return cls(code=code, message=str(exc))