"""C36: Port Monitor — 端口检测 + 自愈.

Monitors port availability (TCP connectivity + HTTP functional checks),
integrates with HealthMonitor for scoring, and SelfHealer for auto-recovery.
"""

from __future__ import annotations

import shlex
import socket
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

from maref.life_state.health import HealthMonitor, SelfHealer

if TYPE_CHECKING:
    from maref.life_state.health import HealResult


@dataclass
class PortCheckResult:
    """Result of a single port check."""
    host: str
    port: int
    path: str = ""
    connected: bool = False
    http_status: int | None = None
    latency_ms: float = 0.0
    functional: bool = False
    error: str = ""
    timestamp: float = field(default_factory=time.time)

    @property
    def healthy(self) -> bool:
        """A port is healthy if connected + (functional check passed or no functional check)."""
        if not self.connected:
            return False
        return not (self.path and not self.functional)


@dataclass
class ServiceDef:
    """Service definition for port monitoring."""
    name: str
    host: str
    port: int
    health_path: str = "/health"
    timeout_ms: float = 5000.0
    restart_command: str = ""
    description: str = ""

    @property
    def state_id(self) -> str:
        return f"port_{self.name}_{self.port}"


class PortMonitor:
    """Port availability and functional health monitor.

    Supports:
    - TCP connectivity check (port open?)
    - HTTP functional check (endpoint returns 200 + valid response?)
    - Integration with HealthMonitor for scoring
    - Integration with SelfHealer for auto-recovery
    """

    def __init__(
        self,
        services: list[ServiceDef] | None = None,
        health_monitor: HealthMonitor | None = None,
        self_healer: SelfHealer | None = None,
    ) -> None:
        self.services = services or []
        self.monitor = health_monitor or HealthMonitor()
        self.healer = self_healer or SelfHealer()
        self.history: list[PortCheckResult] = []
        self._on_unhealthy: list[Callable[[PortCheckResult], None]] = []

    def check_tcp(self, host: str, port: int, timeout_ms: float = 5000.0) -> tuple[bool, float, str]:
        """Check TCP connectivity to host:port.

        Returns:
            (connected, latency_ms, error)
        """
        start = time.time()
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout_ms / 1000.0)
            result = sock.connect_ex((host, port))
            latency_ms = (time.time() - start) * 1000
            sock.close()
            if result == 0:
                return True, latency_ms, ""
            return False, latency_ms, f"Connection refused (errno={result})"
        except TimeoutError:
            latency_ms = (time.time() - start) * 1000
            return False, latency_ms, "Connection timed out"
        except Exception as e:
            latency_ms = (time.time() - start) * 1000
            return False, latency_ms, str(e)

    def check_http(self, host: str, port: int, path: str, timeout_ms: float = 5000.0) -> dict[str, Any]:
        """Check HTTP health endpoint.

        Returns:
            {"status": int, "latency_ms": float, "body": dict|None, "functional": bool, "error": str}
        """
        url = f"http://{host}:{port}{path}"
        timeout_s = timeout_ms / 1000.0

        if HAS_HTTPX:
            return self._check_http_httpx(url, timeout_s)
        return self._check_http_curl(url, timeout_s)

    def _check_http_httpx(self, url: str, timeout_s: float) -> dict[str, Any]:
        """HTTP check using httpx."""
        start = time.time()
        try:
            resp = httpx.get(url, timeout=timeout_s)
            latency_ms = (time.time() - start) * 1000
            body = None
            functional = resp.status_code == 200
            try:
                body = resp.json()
                if isinstance(body, dict) and "status" in body:
                    functional = functional and body["status"] in ("ok", "healthy", "UP")
            except Exception:
                pass
            return {
                "status": resp.status_code,
                "latency_ms": latency_ms,
                "body": body,
                "functional": functional,
                "error": "",
            }
        except httpx.TimeoutException:
            return {"status": 0, "latency_ms": timeout_s * 1000, "body": None, "functional": False, "error": "timeout"}
        except Exception as e:
            return {"status": 0, "latency_ms": 0, "body": None, "functional": False, "error": str(e)}

    def _check_http_curl(self, url: str, timeout_s: float) -> dict[str, Any]:
        """HTTP check using curl subprocess (fallback when httpx unavailable)."""
        start = time.time()
        try:
            result = subprocess.run(
                ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", str(timeout_s), url],
                capture_output=True,
                text=True,
                timeout=timeout_s + 5,
            )
            latency_ms = (time.time() - start) * 1000
            status_code = int(result.stdout.strip()) if result.stdout.strip().isdigit() else 0
            functional = status_code == 200
            return {
                "status": status_code,
                "latency_ms": latency_ms,
                "body": None,
                "functional": functional,
                "error": "",
            }
        except subprocess.TimeoutExpired:
            return {"status": 0, "latency_ms": timeout_s * 1000, "body": None, "functional": False, "error": "timeout"}
        except Exception as e:
            return {"status": 0, "latency_ms": 0, "body": None, "functional": False, "error": str(e)}

    def check_service(self, service: ServiceDef) -> PortCheckResult:
        """Run full health check on a service."""
        connected, tcp_latency, tcp_error = self.check_tcp(
            service.host, service.port, service.timeout_ms,
        )
        result = PortCheckResult(
            host=service.host,
            port=service.port,
            path=service.health_path,
            connected=connected,
            latency_ms=tcp_latency,
            error=tcp_error,
        )

        if not connected:
            return result

        if service.health_path:
            http_result = self.check_http(
                service.host, service.port, service.health_path, service.timeout_ms,
            )
            result.http_status = http_result["status"]
            result.latency_ms = http_result["latency_ms"]
            result.functional = http_result["functional"]
            if http_result["error"]:
                result.error = http_result["error"]

        return result

    def check_all(self) -> list[PortCheckResult]:
        """Run health checks on all registered services."""
        results = []
        for svc in self.services:
            result = self.check_service(svc)
            self.history.append(result)

            self.monitor.check(
                state_id=svc.state_id,
                metric="port_connected",
                value=0.0 if result.connected else 1.0,
            )
            if result.latency_ms > 0:
                self.monitor.check(
                    state_id=svc.state_id,
                    metric="latency_ms",
                    value=result.latency_ms,
                )
            if result.http_status is not None:
                self.monitor.check(
                    state_id=svc.state_id,
                    metric="http_status",
                    value=0.0 if result.http_status == 200 else 1.0,
                )

            if not result.healthy:
                for callback in self._on_unhealthy:
                    try:
                        callback(result)
                    except Exception:
                        pass

            results.append(result)
        return results

    def on_unhealthy(self, callback: Callable[[PortCheckResult], None]) -> None:
        """Register callback for unhealthy port events."""
        self._on_unhealthy.append(callback)

    def auto_heal_service(self, service: ServiceDef) -> bool:
        """Attempt to auto-heal an unhealthy service."""
        from maref.life_state.health import HealAction

        if service.restart_command:
            result = self.healer.heal(service.state_id, HealAction.RESTART)
            if result.success:
                return True

        self.healer.heal(service.state_id, HealAction.NOTIFY)
        return False

    def register_restart_handler(self, handler: Callable[[str], HealResult] | None = None) -> None:
        """Register a default restart handler that uses service restart_command."""
        from maref.life_state.health import HealAction

        if handler is not None:
            self.healer.register_action(HealAction.RESTART, handler)
            return

        def default_restart_handler(state_id: str) -> HealResult:
            service = next(
                (s for s in self.services if s.state_id == state_id),
                None,
            )
            if not service or not service.restart_command:
                return HealResult(
                    action=HealAction.RESTART,
                    state_id=state_id,
                    success=False,
                    reason="no_restart_command",
                )
            try:
                subprocess.Popen(
                    shlex.split(service.restart_command),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return HealResult(
                    action=HealAction.RESTART,
                    state_id=state_id,
                    success=True,
                    reason=f"Restart command executed: {service.restart_command[:80]}",
                )
            except Exception as e:
                return HealResult(
                    action=HealAction.RESTART,
                    state_id=state_id,
                    success=False,
                    reason=f"restart_failed: {e}",
                )

        self.healer.register_action(HealAction.RESTART, default_restart_handler)

    def get_status_summary(self) -> dict[str, Any]:
        """Get overall port health summary."""
        if not self.history:
            self.check_all()

        results = self.history[-len(self.services):] if len(self.history) >= len(self.services) else self.history

        total = len(results)
        healthy = sum(1 for r in results if r.healthy)
        unhealthy = total - healthy

        return {
            "total": total,
            "healthy": healthy,
            "unhealthy": unhealthy,
            "services": [
                {
                    "name": svc.name,
                    "host": svc.host,
                    "port": svc.port,
                    "description": svc.description,
                    "healthy": r.healthy,
                    "connected": r.connected,
                    "http_status": r.http_status,
                    "latency_ms": round(r.latency_ms, 2),
                    "error": r.error,
                    "health_score": round(self.monitor.compute_health_score(svc.state_id), 1),
                    "health_status": self.monitor.get_status(svc.state_id).value,
                }
                for svc, r in zip(self.services, results, strict=False)
            ],
            "heal_history": self.healer.to_dict()["recent_history"],
        }

    def generate_health_report(self) -> str:
        """Generate a human-readable health report."""
        summary = self.get_status_summary()
        lines = [
            "=" * 60,
            "MAREF Port Health Report",
            f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Status: {'ALL HEALTHY' if summary['unhealthy'] == 0 else str(summary['unhealthy']) + ' UNHEALTHY'}",
            "=" * 60,
        ]

        for svc in summary["services"]:
            icon = "✅" if svc["healthy"] else "❌"
            lines.append(f"\n{icon} {svc['name']} ({svc['host']}:{svc['port']})")
            lines.append(f"   Description: {svc['description']}")
            lines.append(f"   Connected:   {'Yes' if svc['connected'] else 'No'}")
            if svc["http_status"] is not None:
                lines.append(f"   HTTP Status: {svc['http_status']}")
            lines.append(f"   Latency:     {svc['latency_ms']:.1f}ms")
            lines.append(f"   Health:      {svc['health_status']} ({svc['health_score']}%)")
            if svc["error"]:
                lines.append(f"   Error:       {svc['error']}")

        lines.append("\n" + "=" * 60)
        return "\n".join(lines)
