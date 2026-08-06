from __future__ import annotations

import hashlib
import socket
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DeviceType(str, Enum):
    DESKTOP = "desktop"
    MOBILE = "mobile"
    SERVER = "server"
    IOT = "iot"
    UNKNOWN = "unknown"


class DevicePlatform(str, Enum):
    MACOS = "macos"
    WINDOWS = "windows"
    LINUX = "linux"
    ANDROID = "android"
    IOS = "ios"
    UNKNOWN = "unknown"


class TaskPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class TaskStatus(str, Enum):
    PENDING = "pending"
    DISPATCHED = "dispatched"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class ConnectionMethod(str, Enum):
    P2P = "p2p"
    RELAY = "relay"
    CLOUD = "cloud"
    LOCAL = "local"


@dataclass
class DeviceInfo:
    device_id: str
    name: str
    device_type: DeviceType = DeviceType.UNKNOWN
    platform: DevicePlatform = DevicePlatform.UNKNOWN
    host: str = "localhost"
    port: int = 0
    capabilities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    last_seen: float = field(default_factory=time.time)
    connection_method: ConnectionMethod = ConnectionMethod.LOCAL
    trust_score: float = 1.0
    is_online: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "name": self.name,
            "device_type": self.device_type.value,
            "platform": self.platform.value,
            "host": self.host,
            "port": self.port,
            "capabilities": self.capabilities,
            "metadata": self.metadata,
            "last_seen": self.last_seen,
            "connection_method": self.connection_method.value,
            "trust_score": self.trust_score,
            "is_online": self.is_online,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DeviceInfo:
        return cls(
            device_id=data["device_id"],
            name=data["name"],
            device_type=DeviceType(data.get("device_type", "unknown")),
            platform=DevicePlatform(data.get("platform", "unknown")),
            host=data.get("host", "localhost"),
            port=data.get("port", 0),
            capabilities=data.get("capabilities", []),
            metadata=data.get("metadata", {}),
            last_seen=data.get("last_seen", time.time()),
            connection_method=ConnectionMethod(data.get("connection_method", "local")),
            trust_score=data.get("trust_score", 1.0),
            is_online=data.get("is_online", True),
        )

    @property
    def fingerprint(self) -> str:
        raw = f"{self.name}:{self.platform.value}:{self.host}:{self.port}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class BridgeTask:
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    description: str = ""
    source_device: str = ""
    target_device: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = field(default_factory=time.time)
    dispatched_at: float = 0.0
    completed_at: float = 0.0
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    timeout_seconds: float = 60.0
    idempotency_key: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "source_device": self.source_device,
            "target_device": self.target_device,
            "payload": self.payload,
            "priority": self.priority.value,
            "status": self.status.value,
            "created_at": self.created_at,
            "result": self.result,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BridgeTask:
        return cls(
            task_id=data.get("task_id", ""),
            name=data.get("name", ""),
            source_device=data.get("source_device", ""),
            target_device=data.get("target_device", ""),
            payload=data.get("payload", {}),
            priority=TaskPriority(data.get("priority", "normal")),
            status=TaskStatus(data.get("status", "pending")),
            created_at=data.get("created_at", time.time()),
        )


class DeviceDiscovery:
    """Local network device discovery via mDNS/Bonjour + direct connection.

    Supports:
    - mDNS service advertisement/browsing (simulated in dry-run)
    - Direct IP:port registration
    - Heartbeat-based online status tracking
    """

    def __init__(self, device_id: str = "maref-desktop", port: int = 9090) -> None:
        self.device_id = device_id
        self.port = port
        self._discovered: dict[str, DeviceInfo] = {}
        self._local_device = DeviceInfo(
            device_id=device_id,
            name=socket.gethostname(),
            device_type=DeviceType.DESKTOP,
            platform=DevicePlatform.MACOS,
            host="0.0.0.0",
            port=port,
            connection_method=ConnectionMethod.LOCAL,
        )

    @property
    def local_device(self) -> DeviceInfo:
        return self._local_device

    def register_device(self, device: DeviceInfo) -> None:
        self._discovered[device.device_id] = device

    def unregister_device(self, device_id: str) -> None:
        self._discovered.pop(device_id, None)

    def discover(self) -> list[DeviceInfo]:
        return list(self._discovered.values())

    def discover_by_type(self, device_type: DeviceType) -> list[DeviceInfo]:
        return [d for d in self._discovered.values() if d.device_type == device_type]

    def discover_by_capability(self, capability: str) -> list[DeviceInfo]:
        return [d for d in self._discovered.values() if capability in d.capabilities]

    def get_device(self, device_id: str) -> DeviceInfo | None:
        return self._discovered.get(device_id)

    def check_online(self, timeout: float = 3.0) -> dict[str, bool]:
        status: dict[str, bool] = {}
        for device_id, device in self._discovered.items():
            try:
                s = socket.create_connection((device.host, device.port), timeout=timeout)
                s.close()
                device.is_online = True
                device.last_seen = time.time()
                status[device_id] = True
            except (TimeoutError, ConnectionRefusedError, OSError):
                device.is_online = False
                status[device_id] = False
        return status

    def get_online_devices(self) -> list[DeviceInfo]:
        return [d for d in self._discovered.values() if d.is_online]

    def start_mdns_advertisement(self) -> bool:
        try:
            from zeroconf import ServiceInfo, Zeroconf
            self._zeroconf = Zeroconf()
            service_type = "_maref._tcp.local."
            service_name = f"{self.device_id}.{service_type}"
            info = ServiceInfo(
                service_type,
                service_name,
                addresses=[socket.inet_aton(socket.gethostbyname(socket.gethostname()))],
                port=self.port,
                properties={
                    "device_id": self.device_id,
                    "device_type": "desktop",
                    "platform": self._local_device.platform.value,
                },
            )
            self._zeroconf.register_service(info)
            self._mdns_active = True
            return True
        except ImportError:
            self._mdns_active = False
            return False

    def stop_mdns_advertisement(self) -> None:
        if getattr(self, "_zeroconf", None):
            self._zeroconf.close()
        self._mdns_active = False

    def start_mdns_discovery(self, timeout: float = 5.0) -> list[DeviceInfo]:
        discovered: list[DeviceInfo] = []
        _discovered_map = self._discovered
        try:
            from zeroconf import ServiceBrowser, Zeroconf

            zc = Zeroconf()

            class MAREFListener:
                def add_service(self, _zc, service_type, name):
                    info = _zc.get_service_info(service_type, name)
                    if info and info.properties:
                        props = {k.decode(): v.decode() for k, v in info.properties.items()}
                        device_type = DeviceType(props.get("device_type", "unknown"))
                        platform = DevicePlatform(props.get("platform", "unknown"))
                        device = DeviceInfo(
                            device_id=props.get("device_id", name),
                            name=name,
                            device_type=device_type,
                            platform=platform,
                            host=socket.inet_ntoa(info.addresses[0])
                            if info.addresses
                            else "localhost",
                            port=info.port,
                        )
                        if device.device_id not in {d.device_id for d in discovered}:
                            discovered.append(device)
                            _discovered_map[device.device_id] = device

            ServiceBrowser(zc, "_maref._tcp.local.", MAREFListener())
            time.sleep(timeout)
            zc.close()
        except ImportError:
            pass
        return discovered

    @property
    def mdns_active(self) -> bool:
        return getattr(self, "_mdns_active", False)


class TaskQueue:
    """Priority task queue for mobile→desktop task dispatch.

    Supports deduplication via idempotency keys, priority ordering,
    and timeout-based cancellation.
    """

    def __init__(self, max_queue_size: int = 1000) -> None:
        self._queue: list[BridgeTask] = []
        self._completed: dict[str, BridgeTask] = {}
        self._idempotency_keys: set[str] = set()
        self.max_queue_size = max_queue_size

    def enqueue(self, task: BridgeTask) -> bool:
        if len(self._queue) >= self.max_queue_size:
            return False
        if task.idempotency_key and task.idempotency_key in self._idempotency_keys:
            return False
        self._queue.append(task)
        if task.idempotency_key:
            self._idempotency_keys.add(task.idempotency_key)
        self._queue.sort(
            key=lambda t: {"urgent": 3, "high": 2, "normal": 1, "low": 0}[t.priority.value],
            reverse=True,
        )
        return True

    def dequeue(self) -> BridgeTask | None:
        if not self._queue:
            return None
        return self._queue.pop(0)

    def peek(self) -> BridgeTask | None:
        return self._queue[0] if self._queue else None

    def complete(self, task_id: str, result: dict[str, Any]) -> None:
        for task in self._queue:
            if task.task_id == task_id:
                task.status = TaskStatus.COMPLETED
                task.result = result
                task.completed_at = time.time()
                self._completed[task_id] = task
                self._queue.remove(task)
                return

    def fail(self, task_id: str, error: str) -> None:
        for task in self._queue:
            if task.task_id == task_id:
                task.status = TaskStatus.FAILED
                task.error = error
                task.completed_at = time.time()
                self._completed[task_id] = task
                self._queue.remove(task)
                return

    def cancel(self, task_id: str) -> bool:
        for task in self._queue:
            if task.task_id == task_id:
                task.status = TaskStatus.CANCELLED
                self._completed[task_id] = task
                self._queue.remove(task)
                return True
        return False

    def get_pending(self) -> list[BridgeTask]:
        return list(self._queue)

    def get_completed(self) -> list[BridgeTask]:
        return list(self._completed.values())

    def get_by_source(self, source_device: str) -> list[BridgeTask]:
        return [t for t in self._queue if t.source_device == source_device] + [
            t for t in self._completed.values() if t.source_device == source_device
        ]

    @property
    def size(self) -> int:
        return len(self._queue)


class SessionManager:
    """Multi-device session isolation for one-phone→N-desktop topology.

    Each (source_device, target_device) pair gets its own session.
    Sessions maintain independent task queues, capability contexts,
    and trust scores.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}
        self._device_pairs: set[tuple[str, str]] = set()

    def create_session(
        self, source_id: str, target_id: str, context: dict[str, Any] | None = None
    ) -> str:
        session_id = f"{source_id}->{target_id}-{uuid.uuid4().hex[:6]}"
        self._sessions[session_id] = {
            "source_id": source_id,
            "target_id": target_id,
            "created_at": time.time(),
            "context": context or {},
            "task_queue": TaskQueue(),
            "active": True,
        }
        self._device_pairs.add((source_id, target_id))
        return session_id

    def close_session(self, session_id: str) -> bool:
        if session_id in self._sessions:
            self._sessions[session_id]["active"] = False
            return True
        return False

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        return self._sessions.get(session_id)

    def find_sessions_by_source(self, source_id: str) -> list[str]:
        return [
            sid for sid, s in self._sessions.items() if s["source_id"] == source_id and s["active"]
        ]

    def find_sessions_by_target(self, target_id: str) -> list[str]:
        return [
            sid for sid, s in self._sessions.items() if s["target_id"] == target_id and s["active"]
        ]

    def get_active_sessions(self) -> list[str]:
        return [sid for sid, s in self._sessions.items() if s["active"]]

    def get_device_pairs(self) -> list[tuple[str, str]]:
        return list(self._device_pairs)

    def get_queue_for_session(self, session_id: str) -> TaskQueue | None:
        session = self._sessions.get(session_id)
        if session and session["active"]:
            return session["task_queue"]
        return None


class MobileBridge:
    """Mobile→Desktop task bridge for cross-device agent orchestration.

    Reference: Claude Dispatch (2026.3), Trae Solo device management.

    Architecture:
        Mobile Device  ──mDNS/WebSocket──>  Desktop MAREF Agent
           │                                      │
           │  Task + Payload                      │  Screenshot→Parse→Execute→Verify
           │  Priority + Timeout                  │  Result + Status
           │                                      │
           └─────────── SSE Push ─────────────────┘
    """

    def __init__(
        self,
        device_id: str = "maref-desktop",
        port: int = 9090,
    ) -> None:
        self.device_id = device_id
        self.discovery = DeviceDiscovery(device_id=device_id, port=port)
        self.sessions = SessionManager()
        self._global_queue = TaskQueue()
        self._event_log: list[dict[str, Any]] = []

    def register_mobile_device(self, device: DeviceInfo) -> None:
        self.discovery.register_device(device)
        self._log_event("device_registered", {"device": device.to_dict()})

    def create_bridge_session(self, source_device_id: str, target_device_id: str) -> str:
        session_id = self.sessions.create_session(source_device_id, target_device_id)
        self._log_event(
            "session_created",
            {"session_id": session_id, "source": source_device_id, "target": target_device_id},
        )
        return session_id

    def dispatch_task(
        self,
        source_device: str,
        target_device: str,
        task_name: str,
        payload: dict[str, Any],
        priority: TaskPriority = TaskPriority.NORMAL,
        idempotency_key: str = "",
    ) -> BridgeTask:
        task = BridgeTask(
            name=task_name,
            source_device=source_device,
            target_device=target_device,
            payload=payload,
            priority=priority,
            idempotency_key=idempotency_key,
        )
        self._global_queue.enqueue(task)

        sessions = self.sessions.find_sessions_by_target(target_device)
        for sid in sessions:
            queue = self.sessions.get_queue_for_session(sid)
            if queue:
                queue.enqueue(task)

        self._log_event(
            "task_dispatched",
            {"task_id": task.task_id, "source": source_device, "target": target_device},
        )
        return task

    def complete_task(self, task_id: str, result: dict[str, Any]) -> None:
        self._global_queue.complete(task_id, result)
        self._log_event("task_completed", {"task_id": task_id, "result": result})

    def fail_task(self, task_id: str, error: str) -> None:
        self._global_queue.fail(task_id, error)
        self._log_event("task_failed", {"task_id": task_id, "error": error})

    def get_device_topology(self) -> dict[str, Any]:
        return {
            "local": self.discovery.local_device.to_dict(),
            "discovered": [d.to_dict() for d in self.discovery.discover()],
            "active_sessions": len(self.sessions.get_active_sessions()),
            "device_pairs": self.sessions.get_device_pairs(),
            "pending_tasks": self._global_queue.size,
        }

    def get_event_log(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._event_log[-limit:]

    def _log_event(self, event_type: str, data: dict[str, Any]) -> None:
        self._event_log.append(
            {
                "timestamp": time.time(),
                "event_type": event_type,
                "data": data,
            }
        )

    def enable_real_mode(self, host: str = "0.0.0.0", port: int | None = None) -> dict[str, Any]:
        port = port or self.discovery.port
        self.discovery._local_device.host = host
        self.discovery._local_device.port = port

        mdns_ok = self.discovery.start_mdns_advertisement()

        self._heartbeat_active = True
        self._tcp_server = None

        try:
            server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_sock.bind((host, port))
            server_sock.listen(5)
            server_sock.settimeout(1.0)
            self._tcp_server = server_sock

            def _accept_loop():
                while getattr(self, "_heartbeat_active", False):
                    try:
                        server = self._tcp_server
                        if server is None:
                            break
                        conn, addr = server.accept()
                        self._log_event("tcp_connection", {"addr": str(addr)})
                        conn.close()
                    except TimeoutError:
                        continue
                    except OSError:
                        break

            threading.Thread(target=_accept_loop, daemon=True).start()
            server_bound = True
        except OSError:
            server_bound = False

        self._log_event(
            "real_mode_enabled",
            {
                "host": host,
                "port": port,
                "mdns_advertising": mdns_ok,
                "tcp_server_bound": server_bound,
            },
        )

        return {
            "enabled": True,
            "host": host,
            "port": port,
            "mdns_advertising": mdns_ok,
            "tcp_server_bound": server_bound,
        }

    def disable_real_mode(self) -> None:
        self._heartbeat_active = False
        self.discovery.stop_mdns_advertisement()
        tcp_server = getattr(self, "_tcp_server", None)
        if tcp_server is not None:
            try:
                tcp_server.close()
            except OSError:
                pass
            self._tcp_server = None
        self._log_event("real_mode_disabled", {})
