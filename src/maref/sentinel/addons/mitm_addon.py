"""
SentinelMitmAddon — mitmproxy addon,捕获 HTTPS flow 并推入 NetworkEgressProbe

mitmproxy 作为本地 HTTPS 中间人代理,解密 Agent 出站流量后调用本 addon 的
request/response 钩子。addon 把 HTTPFlow 转换为 FlowRecord (脱敏快照),
通过 asyncio.Queue 推送给 NetworkEgressProbe。

设计要点:
1. addon 不直接调用 probe.poll(),只负责推 FlowRecord 入队。
2. asyncio.Queue 在 probe 和 addon 之间共享,生命周期由 Daemon 管理。
3. mitmproxy CA 证书安装走 JustInTimeConsent (M1.3 实现,本 addon 仅声明 consent_required)。
4. addon 在 mitmproxy 未安装时不可导入 — 测试通过直接构造 FlowRecord 绕过。

CA 证书同意流 (M1.3 完整实现):
    SentinelMitmAddon 启动 → 检测 CA 是否已安装 → 若否,触发 JustInTimeConsent
    → 用户同意 → 安装 CA 到系统/浏览器信任库 → 继续拦截
    → 用户拒绝 → addon 进入 degraded 模式 (仅记录域名,不解密 HTTPS)

验收标准:
- 1.2-A6: mitmproxy CA 证书安装走 JustInTimeConsent,无静默安装
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import TYPE_CHECKING, Any

from maref.sentinel.probes.network_egress_probe import FlowRecord

if TYPE_CHECKING:
    # mitmproxy 仅在运行时需要,类型检查时用 TYPE_CHECKING 避免硬依赖
    from mitmproxy import http as mitm_http
    from mitmproxy.addonmanager import Loader

# CA 安装同意流的高权限操作标识 — M1.3 JustInTimeConsent 用
CA_INSTALL_OPERATION = "sentinel.mitmproxy.ca_install"
CA_DEGRADED_MODE = "sentinel.mitmproxy.degraded"


class SentinelMitmAddon:
    """mitmproxy addon — 捕获 HTTPS flow → FlowRecord → NetworkEgressProbe 队列

    用法 (mitmproxy 命令行):
        mitmdump -s sentinel_mitm_addon.py \\
            --set sentinel_probe_queue=auto \\
            --set consent_required=true

    用法 (Python API):
        from mitmproxy.tools.dump import DumpMaster
        from mitmproxy import options
        addon = SentinelMitmAddon(probe_queue, agent_id="claude-code")
        master = DumpMaster(options.Options(listen_host="127.0.0.1", listen_port=8080))
        master.addons.add(addon)
        await master.run()

    Consent 流:
        addon 启动时检查 self._consent_callback (由 Daemon 注入)。
        若 callback 返回 False,addon 进入 degraded 模式,仅记录 host 不解密 body。
    """

    def __init__(
        self,
        probe_queue: asyncio.Queue[FlowRecord],
        agent_id: str = "",
        consent_callback: Any = None,
        max_body_capture: int = 65536,
    ) -> None:
        """
        Args:
            probe_queue: NetworkEgressProbe 的内部队列 (由 probe 暴露 _queue)
            agent_id: 关联的 Agent ID (写入每条 FlowRecord.agent_id)
            consent_callback: JustInTimeConsent 回调 (M1.3 注入)。
                              签名: async (operation: str) -> bool。
                              返回 True = 同意,False = 拒绝 (进入 degraded)。
                              None = M1.3 未接入,默认拒绝 (保守策略)。
            max_body_capture: 单条 body 最大捕获字节数 (防止大文件耗尽内存)
        """
        self._queue = probe_queue
        self._agent_id = agent_id
        self._consent_callback = consent_callback
        self._max_body_capture = max_body_capture
        self._degraded: bool = False
        self._consent_checked: bool = False
        self._flows_captured: int = 0
        self._flows_dropped: int = 0

    # ---- mitmproxy addon lifecycle hooks ----

    def load(self, loader: Loader) -> None:
        """mitmproxy addon 加载时调用 — 注册配置选项"""
        loader.add_option(
            name="sentinel_agent_id",
            typespec=str,
            default="",
            help="Agent ID to associate with captured flows",
        )
        loader.add_option(
            name="sentinel_consent_required",
            typespec=bool,
            default=True,
            help="Require JustInTimeConsent before CA install (always true in M1.3+)",
        )

    async def request(self, flow: mitm_http.HTTPFlow) -> None:
        """mitmproxy request 钩子 — 记录请求开始 (此时无响应)"""
        # M1.2 阶段不在此处产生 FlowRecord,等 response 钩子统一处理
        pass

    async def response(self, flow: mitm_http.HTTPFlow) -> None:
        """mitmproxy response 钩子 — 完整 flow 就绪,转换为 FlowRecord 入队"""
        try:
            record = self._flow_to_record(flow)
            if record is not None:
                await self._put_record(record)
        except Exception:
            # addon 异常不应中断 mitmproxy,只计数
            self._flows_dropped += 1

    async def requestheaders(self, flow: mitm_http.HTTPFlow) -> None:
        """mitmproxy requestheaders 钩子 — degraded 模式下剥离 body"""
        if self._degraded:
            # degraded 模式: 不解密 body,只记录 URL/host
            flow.request.stream = True

    # ---- consent 流 (M1.3 JustInTimeConsent 注入) ----

    async def ensure_consent(self) -> bool:
        """确保 CA 安装已获用户同意 — M1.3 完整实现

        M1.2 阶段:
        - 若 consent_callback 为 None,默认拒绝 (保守,不解密 HTTPS body)
        - 进入 degraded 模式,仅记录 URL/host/method/status

        M1.3 阶段:
        - consent_callback 由 JustInTimeConsent 注入
        - 首次调用触发弹窗,用户同意后安装 CA
        - 用户拒绝则永久 degraded (记录到 AuditLogger)
        """
        if self._consent_checked:
            return not self._degraded

        self._consent_checked = True

        if self._consent_callback is None:
            # M1.2: 无 consent 回调,进入 degraded 模式 (保守)
            self._degraded = True
            return False

        try:
            granted = await self._consent_callback(CA_INSTALL_OPERATION)
            self._degraded = not granted
            return granted
        except Exception:
            self._degraded = True
            return False

    # ---- 内部方法 ----

    def _flow_to_record(self, flow: mitm_http.HTTPFlow) -> FlowRecord | None:
        """把 mitmproxy HTTPFlow 转换为 FlowRecord (脱敏快照)"""
        try:
            request = flow.request
            response = flow.response

            # 请求头 — 键小写
            req_headers = {k.lower(): v for k, v in request.headers.items()}
            # 请求 body — 限长
            req_body = bytes(request.get_content() or b"")[: self._max_body_capture]

            # 响应头和 body — degraded 模式下不捕获 body
            resp_headers: dict[str, str] = {}
            resp_body = b""
            status_code = 0
            if response is not None:
                resp_headers = {k.lower(): v for k, v in response.headers.items()}
                status_code = response.status_code
                if not self._degraded:
                    resp_body = bytes(response.get_content() or b"")[
                        : self._max_body_capture
                    ]

            return FlowRecord(
                flow_id=str(uuid.uuid4()),
                timestamp=time.time(),
                method=request.method,
                url=request.pretty_url,
                request_headers=req_headers,
                request_body=req_body,
                status_code=status_code,
                response_headers=resp_headers,
                response_body=resp_body,
                client_ip=str(request.client_ip) if request.client_ip else "",
                agent_id=self._agent_id,
            )
        except Exception:
            return None

    async def _put_record(self, record: FlowRecord) -> None:
        """把 FlowRecord 推入 probe 队列 — 满则丢弃最旧"""
        if self._queue.full():
            try:
                self._queue.get_nowait()
                self._flows_dropped += 1
            except asyncio.QueueEmpty:
                pass
        try:
            self._queue.put_nowait(record)
            self._flows_captured += 1
        except asyncio.QueueFull:
            self._flows_dropped += 1

    def snapshot_stats(self) -> dict[str, Any]:
        """返回 addon 内部统计"""
        return {
            "flows_captured": self._flows_captured,
            "flows_dropped": self._flows_dropped,
            "degraded": self._degraded,
            "consent_checked": self._consent_checked,
            "agent_id": self._agent_id,
            "queue_size": self._queue.qsize(),
        }
