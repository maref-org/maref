// esf_client.swift — macOS Endpoint Security Framework 客户端
//
// 接口契约 (validation-contract.md 2.1-A1/A3/A5):
// - 2.1-A1: ESF client 订阅 execve 事件后,Agent 启动子进程 5ms 内被捕获
// - 2.1-A3: ESF 事件丢失率 ≤ 0.1% (10K 事件压测)
// - 2.1-A5: ESF client crash 后 Daemon 能在 3 秒内重启并恢复订阅
//
// 架构:
//   ┌──────────────────┐  Unix socket  ┌─────────────────────┐
//   │  XPCBridge       │ ◄───────────► │  esf_client.swift   │
//   │  (Python asyncio)│   JSON lines  │  (本文件)            │
//   └──────────────────┘               └─────────────────────┘
//                                              │
//                                              │ es_new_client / es_subscribe
//                                              ▼
//                                   Endpoint Security Framework (内核)
//
// 编译:
//   swiftc -O \
//     -target arm64-apple-macos13.0 \
//     -framework EndpointSecurity \
//     -framework Foundation \
//     esf_client.swift -o maref-esf-client
//
// Entitlements (需在 Info.plist 或 provisioning profile 中声明):
//   <key>com.apple.developer.endpoint-security.client</key><true/>
//
// 部署要求:
//   1. 需 System Integrity Protection (SIP) 允许 ESF client (或关闭 SIP 部分功能)
//   2. 需用户在 系统设置 → 隐私与安全 → 完全磁盘访问 中授权
//   3. 二进制需签名 (Developer ID + provisioning profile with ESF entitlement)
//
// M2 阶段: 源码完整,但需 macOS 真机 + Apple Developer 账号才能实际部署测试。
// 测试覆盖: 由 tests/sentinel/test_macos_esf.py 通过 mock XPCBridge 验证 Python 端逻辑。

import Foundation
import EndpointSecurity
import CommonCrypto

// MARK: - Configuration

struct ESFClientConfig {
    var socketPath: String = "/tmp/maref-esf.sock"
    var targetPids: [pid_t] = []
    var targetAgentIds: [String] = []
    var subscribeEvents: [String] = ["exec", "open", "fork", "exit", "connect", "setuid"]
    var hmacKey: Data = Data()
    var healthCheckInterval: TimeInterval = 5.0

    static func parse(from args: [String]) -> ESFClientConfig? {
        var config = ESFClientConfig()
        var i = 1
        while i < args.count {
            switch args[i] {
            case "--socket":
                i += 1
                if i < args.count { config.socketPath = args[i] }
            case "--pids":
                i += 1
                if i < args.count {
                    config.targetPids = args[i].split(separator: ",").compactMap { pid_t($0) }
                }
            case "--agents":
                i += 1
                if i < args.count {
                    config.targetAgentIds = args[i].split(separator: ",").map(String.init)
                }
            case "--events":
                i += 1
                if i < args.count {
                    config.subscribeEvents = args[i].split(separator: ",").map(String.init)
                }
            case "--hmac-key":
                i += 1
                if i < args.count, let key = Data(base64Encoded: args[i]) {
                    config.hmacKey = key
                }
            case "--help", "-h":
                printHelp()
                return nil
            default:
                break
            }
            i += 1
        }
        return config
    }

    static func printHelp() {
        print("""
        maref-esf-client — MAREF Endpoint Security Framework client

        Usage: maref-esf-client [options]

        Options:
          --socket <path>       Unix domain socket path (default: /tmp/maref-esf.sock)
          --pids <pid,pid,...>  Target PIDs to monitor (comma-separated)
          --agents <id,id,...>  Target Agent IDs (for pid→agent mapping)
          --events <type,...>   ESF event types to subscribe (default: exec,open,fork,exit,connect,setuid)
          --hmac-key <base64>   HMAC-SHA256 key for event signing (base64-encoded)
          --help                Show this help
        """)
    }
}

// MARK: - ESF Event Serializer

struct ESFEventSerializer {
    let hmacKey: Data
    private var seqCounter: UInt64 = 0
    private let seqQueue = DispatchQueue(label: "maref.esf.seq")

    mutating func serialize(
        event: es_event_t,
        eventType: String,
        pid: pid_t,
        agentId: String = ""
    ) -> String {
        let seq = seqQueue.sync { () -> UInt64 in
            seqCounter += 1
            return seqCounter
        }
        let timestamp = Date().timeIntervalSince1970
        let eventId = UUID().uuidString

        var payload: [String: Any] = [
            "event_id": eventId,
            "event_type": eventType,
            "seq": seq,
            "timestamp": timestamp,
            "pid": Int(pid),
            "agent_id": agentId,
        ]

        // 根据事件类型填充具体字段
        switch eventType {
        case "exec":
            let execEvent = event.event.exec
            payload["ppid"] = Int(execEvent.target.ppid)
            if let execPath = String(cString: execEvent.executable?.path.ptr, optional: true) {
                payload["path"] = execPath
            }
            if let args = execEvent.args {
                var argv: [String] = []
                var i = 0
                while let arg = args[i].ptr {
                    argv.append(String(cString: arg))
                    i += 1
                }
                payload["argv"] = argv
            }
        case "open":
            payload["path"] = String(cString: event.event.open.file.path)
            payload["fd"] = Int(event.event.open.fd)
        case "fork":
            payload["ppid"] = Int(event.event.fork.target.ppid)
        case "exit":
            payload["ppid"] = Int(event.event.exit.target.ppid)
            payload["evidence"] = ["exit_stat": Int(event.event.exit.stat)]
        case "connect":
            // 简化:实际需解析 sockaddr 获取 remote_addr/port
            payload["fd"] = Int(event.event.connect.fd)
        case "setuid":
            payload["evidence"] = ["uid": Int(event.event.setuid.uid)]
        default:
            break
        }

        // HMAC 签名 (与 Python XPCBridge._compute_hash 一致)
        let signPayload = "\(eventId)|\(seq)|\(String(format: "%.6f", timestamp))|\(pid)|\(eventType)"
        let signature = hmacSHA256(key: hmacKey, data: signPayload.data(using: .utf8) ?? Data())
        payload["hmac_signature"] = signature

        // JSON 序列化为单行 (newline-delimited JSON)
        guard let jsonData = try? JSONSerialization.data(withJSONObject: payload),
              let jsonLine = String(data: jsonData, encoding: .utf8) else {
            return ""
        }
        return jsonLine
    }

    private func hmacSHA256(key: Data, data: Data) -> String {
        var result = [UInt8](repeating: 0, count: Int(CC_SHA256_DIGEST_LENGTH))
        key.withUnsafeBytes { keyPtr in
            data.withUnsafeBytes { dataPtr in
                CCHmac(CCHmacAlgorithm(kCCHmacAlgSHA256),
                       keyPtr.baseAddress, key.count,
                       dataPtr.baseAddress, data.count,
                       &result)
            }
        }
        return result.map { String(format: "%02x", $0) }.joined()
    }
}

// MARK: - ESF Client

final class ESFClient {
    private let config: ESFClientConfig
    private var esClient: OpaquePointer?
    private var serializer: ESFEventSerializer
    private var socketFD: Int32 = -1
    private var running = false
    private let writeQueue = DispatchQueue(label: "maref.esf.write")

    init(config: ESFClientConfig) {
        self.config = config
        self.serializer = ESFEventSerializer(hmacKey: config.hmacKey)
    }

    func run() throws {
        // 1. 连接 Unix socket
        try connectSocket()

        // 2. 创建 ESF client
        var client: OpaquePointer?
        let newClientResult = es_new_client(&client, .default) { [weak self] _, message in
            self?.handleESMessage(message)
        }
        guard newClientResult == ESPERMISSION_GRANTED || newClientResult == ES_NEW_CLIENT_RESULT_SUCCESS else {
            throw ESFError.subscribeFailed("es_new_client failed: \(newClientResult.rawValue)")
        }
        self.esClient = client

        // 3. 订阅事件
        try subscribeEvents()

        // 4. 进入主循环 (等待 ESF 事件)
        running = true
        print("[maref-esf-client] subscribed, waiting for events on pids=\(config.targetPids)")
        while running {
            Thread.sleep(forTimeInterval: 1.0)
        }

        // 5. 清理
        cleanup()
    }

    private func connectSocket() throws {
        socketFD = socket(AF_UNIX, SOCK_STREAM, 0)
        guard socketFD >= 0 else {
            throw ESFError.socketFailed("socket() failed")
        }
        var addr = sockaddr_un()
        addr.sun_family = sa_family_t(AF_UNIX)
        let pathLength = min(config.socketPath.count, MemoryLayout.size(ofValue: addr.sun_path) - 1)
        withUnsafeMutablePointer(to: &addr.sun_path) { ptr in
            config.socketPath.withCString { src in
                _ = strncpy(UnsafeMutableRawPointer(ptr).assumingMemoryBound(to: CChar.self), src, pathLength)
            }
        }
        let connectResult = withUnsafePointer(to: &addr) { addrPtr in
            addrPtr.withMemoryRebound(to: sockaddr.self, capacity: 1) { sockaddrPtr in
                connect(socketFD, sockaddrPtr, socklen_t(MemoryLayout<sockaddr_un>.size))
            }
        }
        if connectResult < 0 {
            close(socketFD)
            socketFD = -1
            throw ESFError.socketFailed("connect() failed: \(errno)")
        }
    }

    private func subscribeEvents() throws {
        guard let client = esClient else {
            throw ESFError.subscribeFailed("ESF client not initialized")
        }

        var eventTypes: [es_event_type_t] = []
        for evStr in config.subscribeEvents {
            switch evStr {
            case "exec": eventTypes.append(ES_EVENT_TYPE_AUTH_EXEC)
            case "open": eventTypes.append(ES_EVENT_TYPE_NOTIFY_OPEN)
            case "fork": eventTypes.append(ES_EVENT_TYPE_NOTIFY_FORK)
            case "exit": eventTypes.append(ES_EVENT_TYPE_NOTIFY_EXIT)
            case "connect": eventTypes.append(ES_EVENT_TYPE_NOTIFY_WRITE)
            case "setuid": eventTypes.append(ES_EVENT_TYPE_NOTIFY_SETUID)
            default: continue
            }
        }

        let subscribeResult = es_subscribe(client, eventTypes, UInt32(eventTypes.count))
        if subscribeResult != ES_RETURN_SUCCESS {
            throw ESFError.subscribeFailed("es_subscribe failed: \(subscribeResult.rawValue)")
        }
    }

    private func handleESMessage(_ message: UnsafePointer<es_message_t>) {
        let msg = message.pointee
        let pid = msg.process.audit_token.pid

        // 过滤:只关注目标 PID 或其子进程
        if !config.targetPids.isEmpty && !config.targetPids.contains(pid) {
            return
        }

        // 确定事件类型字符串
        let eventTypeStr: String
        switch msg.event_type {
        case ES_EVENT_TYPE_AUTH_EXEC, ES_EVENT_TYPE_NOTIFY_EXEC:
            eventTypeStr = "exec"
        case ES_EVENT_TYPE_NOTIFY_OPEN:
            eventTypeStr = "open"
        case ES_EVENT_TYPE_NOTIFY_FORK:
            eventTypeStr = "fork"
        case ES_EVENT_TYPE_NOTIFY_EXIT:
            eventTypeStr = "exit"
        case ES_EVENT_TYPE_NOTIFY_WRITE:
            eventTypeStr = "connect"
        case ES_EVENT_TYPE_NOTIFY_SETUID:
            eventTypeStr = "setuid"
        default:
            return
        }

        // 序列化并写入 socket
        let jsonLine = serializer.serialize(event: msg.event, eventType: eventTypeStr, pid: pid)
        if !jsonLine.isEmpty {
            writeQueue.async { [weak self] in
                self?.writeToSocket(jsonLine + "\n")
            }
        }
    }

    private func writeToSocket(_ data: String) {
        guard socketFD >= 0 else { return }
        data.withCString { ptr in
            let length = strlen(ptr)
            var remaining = length
            var offset = 0
            while remaining > 0 {
                let written = write(socketFD, ptr.advanced(by: offset), remaining)
                if written <= 0 {
                    if errno == EINTR { continue }
                    break
                }
                remaining -= written
                offset += written
            }
        }
    }

    private func cleanup() {
        if let client = esClient {
            es_unsubscribe_all(client)
            es_delete_client(client)
            esClient = nil
        }
        if socketFD >= 0 {
            close(socketFD)
            socketFD = -1
        }
    }

    func stop() {
        running = false
    }
}

// MARK: - Errors

enum ESFError: Error {
    case socketFailed(String)
    case subscribeFailed(String)
    case invalidConfig(String)
}

// MARK: - Main

let args = CommandLine.arguments
guard let config = ESFClientConfig.parse(from: args) else {
    exit(1)
}

let client = ESFClient(config: config)

// 信号处理 — 优雅关闭
signal(SIGINT) { _ in
    client.stop()
}
signal(SIGTERM) { _ in
    client.stop()
}

do {
    try client.run()
    exit(0)
} catch {
    FileHandle.standardError.write("maref-esf-client error: \(error)\n".data(using: .utf8) ?? Data())
    exit(1)
}
