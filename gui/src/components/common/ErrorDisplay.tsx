import { useMemo } from "react";

const ERROR_MAP: Record<string, { title: string; description: string }> = {
  ERR_AUTH_001: { title: "身份验证失败", description: "请重新连接后重试" },
  ERR_AUTH_002: { title: "权限不足", description: "无权限执行此操作" },
  ERR_GOV_001: { title: "治理规则拒绝", description: "此操作被治理规则阻止" },
  ERR_GOV_002: { title: "请求过于频繁", description: "请稍后再试" },
  ERR_GOV_003: { title: "熔断保护中", description: "系统暂时不可用" },
  ERR_AGENT_001: { title: "Agent 参数无效", description: "请检查输入参数" },
  ERR_AGENT_002: { title: "Agent 不可用", description: "Agent 不存在或已离线" },
  ERR_AGENT_003: { title: "Agent 执行异常", description: "请查看详细日志" },
  ERR_DESKTOP_001: { title: "桌面操作参数无效", description: "请检查操作参数" },
  ERR_DESKTOP_002: { title: "桌面操作被拦截", description: "安全门阻止了此操作" },
  ERR_DESKTOP_003: { title: "桌面操作失败", description: "无法执行桌面操作" },
  ERR_MCP_001: { title: "MCP 请求无效", description: "请检查请求参数" },
  ERR_MCP_002: { title: "MCP 资源不存在", description: "请求的工具或资源不可用" },
  ERR_MCP_003: { title: "MCP 执行错误", description: "MCP 调用返回异常" },
  ERR_SYS_001: { title: "系统内部错误", description: "请联系技术支持" },
  ERR_SYS_002: { title: "服务不可用", description: "服务暂不可用，请稍后重试" },
};

interface ErrorDisplayProps {
  code?: string;
  message?: string;
  details?: string;
}

export function ErrorDisplay({ code, message, details }: ErrorDisplayProps) {
  const mapped = useMemo(() => {
    if (code && ERROR_MAP[code]) return ERROR_MAP[code];
    return null;
  }, [code]);

  if (!mapped && !message) return null;

  return (
    <div className="rounded-lg border border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-950 p-3 text-sm">
      <div className="flex items-start gap-2">
        <span className="mt-0.5 text-red-500">⚠</span>
        <div className="flex-1 min-w-0">
          <p className="font-medium text-red-700 dark:text-red-300">
            {mapped?.title ?? (code ?? "Error")}
          </p>
          <p className="mt-1 text-red-600 dark:text-red-400">
            {mapped?.description ?? message ?? "An unknown error occurred"}
          </p>
          {details && (
            <pre className="mt-2 max-h-20 overflow-auto rounded bg-red-100 dark:bg-red-900 p-2 text-xs text-red-700 dark:text-red-300">
              {details}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}
