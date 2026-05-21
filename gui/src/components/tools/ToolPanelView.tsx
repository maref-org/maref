import { useState } from "react";
import { Wrench, ChevronDown, ChevronRight, Shield, CheckCircle, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";

interface ToolInfo {
  name: string;
  description: string;
  version: string;
  tools: string[];
  security_controls: string[];
  installed: boolean;
}

const BUILTIN_TOOLS: ToolInfo[] = [
  {
    name: "file",
    description: "File system operations with path sandbox",
    version: "0.27.0",
    tools: ["read_file", "write_file", "list_directory", "delete_file", "copy_file", "move_file", "get_file_info"],
    security_controls: ["PathSandbox", "FileSizeLimit"],
    installed: true,
  },
  {
    name: "shell",
    description: "Shell command execution with command whitelist and timeout",
    version: "0.27.0",
    tools: ["run_command", "get_shell_help"],
    security_controls: ["CommandWhitelist", "Timeout", "OutputLimit", "MetacharacterBlock"],
    installed: true,
  },
  {
    name: "git",
    description: "Git repository operations with repo whitelist and write mode gate",
    version: "0.27.0",
    tools: ["git_status", "git_log", "git_diff", "git_branch", "git_commit", "git_push"],
    security_controls: ["RepoWhitelist", "WriteModeGate"],
    installed: true,
  },
  {
    name: "browser",
    description: "Web page fetching and link extraction with domain whitelist",
    version: "0.27.0",
    tools: ["browser_open", "browser_screenshot", "browser_get_html", "browser_get_links"],
    security_controls: ["DomainWhitelist", "URLValidation", "ContentSizeLimit"],
    installed: true,
  },
  {
    name: "email",
    description: "Email sending and listing with recipient whitelist and sensitive word filter",
    version: "0.27.0",
    tools: ["email_send", "email_list", "email_read", "email_search"],
    security_controls: ["RecipientWhitelist", "SensitiveWordFilter", "WriteModeGate"],
    installed: true,
  },
];

const SECURITY_CONTROL_DESCRIPTIONS: Record<string, string> = {
  PathSandbox: "限制文件操作在沙箱路径范围内",
  FileSizeLimit: "限制最大读写文件大小",
  CommandWhitelist: "仅允许白名单内的命令执行",
  Timeout: "命令执行超时自动终止",
  OutputLimit: "限制命令输出大小",
  MetacharacterBlock: "阻止 shell 元字符注入",
  RepoWhitelist: "仅允许操作白名单内的仓库",
  WriteModeGate: "写操作需要显式开启写入模式",
  DomainWhitelist: "仅允许访问白名单内的域名",
  URLValidation: "验证 URL 格式和安全性",
  ContentSizeLimit: "限制获取内容的最大大小",
  RecipientWhitelist: "仅允许发送到白名单内的收件人",
  SensitiveWordFilter: "过滤敏感词内容",
};

function ToolDetailRow({ tool, expanded }: { tool: ToolInfo; expanded: boolean }) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-2 text-xs">
        <span className="text-maref-text-muted">子命令</span>
        <span className="col-span-2 flex flex-wrap gap-1">
          {tool.tools.map((t) => (
            <span
              key={t}
              className="rounded bg-maref-accent/10 px-1.5 py-0.5 text-[11px] text-maref-accent font-mono"
            >
              {t}
            </span>
          ))}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-2 text-xs">
        <span className="text-maref-text-muted">安全控制</span>
        <span className="col-span-2 flex flex-col gap-1.5">
          {tool.security_controls.map((sc) => (
            <div key={sc} className="flex items-start gap-2">
              <Shield className="h-3.5 w-3.5 text-maref-warning mt-0.5 flex-shrink-0" />
              <div>
                <span className="text-maref-text font-medium">{sc}</span>
                <p className="text-[11px] text-maref-text-muted mt-0.5">
                  {SECURITY_CONTROL_DESCRIPTIONS[sc] || "—"}
                </p>
              </div>
            </div>
          ))}
        </span>
      </div>
    </div>
  );
}

export default function ToolPanelView() {
  const [expandedTool, setExpandedTool] = useState<string | null>(null);

  const toggleExpand = (name: string) => {
    setExpandedTool((prev) => (prev === name ? null : name));
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex-shrink-0 border-b border-maref-border bg-maref-surface px-6 py-4">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-maref-text">
          <Wrench className="h-4 w-4 text-maref-accent" />
          工具面板
        </h2>
        <p className="mt-0.5 text-xs text-maref-text-muted">
          管理和监控已安装的 MCP 工具
        </p>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        <div className="overflow-hidden rounded-lg border border-maref-border">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-maref-border bg-maref-surface-alt">
                <th className="px-4 py-2.5 text-left font-medium text-maref-text-muted w-8" />
                <th className="px-4 py-2.5 text-left font-medium text-maref-text-muted">名称</th>
                <th className="px-4 py-2.5 text-left font-medium text-maref-text-muted">描述</th>
                <th className="px-4 py-2.5 text-left font-medium text-maref-text-muted">版本</th>
                <th className="px-4 py-2.5 text-left font-medium text-maref-text-muted">安全控制</th>
                <th className="px-4 py-2.5 text-left font-medium text-maref-text-muted">状态</th>
              </tr>
            </thead>
            <tbody>
              {BUILTIN_TOOLS.map((tool) => {
                const isExpanded = expandedTool === tool.name;
                return (
                  <tr key={tool.name} className="border-b border-maref-border last:border-0">
                    <td colSpan={6} className="p-0">
                      <div
                        className={cn(
                          "border-b border-maref-border last:border-0",
                          isExpanded && "bg-maref-surface-alt/20"
                        )}
                      >
                        <button
                          onClick={() => toggleExpand(tool.name)}
                          className="flex w-full items-center gap-2 px-4 py-3 text-left hover:bg-maref-surface-alt/30 transition-colors"
                        >
                          <span className="text-maref-text-muted w-4">
                            {isExpanded ? (
                              <ChevronDown className="h-3.5 w-3.5" />
                            ) : (
                              <ChevronRight className="h-3.5 w-3.5" />
                            )}
                          </span>
                          <span className="w-24 font-medium text-maref-text font-mono">
                            {tool.name}
                          </span>
                          <span className="flex-1 text-maref-text-muted truncate">
                            {tool.description}
                          </span>
                          <span className="w-16 text-maref-text-muted font-mono">
                            {tool.version}
                          </span>
                          <span className="w-24 flex flex-wrap gap-1">
                            {tool.security_controls.map((sc) => (
                              <span
                                key={sc}
                                className="rounded bg-maref-warning/10 px-1.5 py-0.5 text-[10px] text-maref-warning"
                              >
                                {sc}
                              </span>
                            ))}
                          </span>
                          <span className="w-16">
                            <span
                              className={cn(
                                "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium",
                                tool.installed
                                  ? "bg-green-400/10 text-green-400 border-green-400/20"
                                  : "bg-gray-400/10 text-gray-400 border-gray-400/20"
                              )}
                            >
                              {tool.installed ? (
                                <CheckCircle className="h-3 w-3" />
                              ) : (
                                <XCircle className="h-3 w-3" />
                              )}
                              {tool.installed ? "已安装" : "未安装"}
                            </span>
                          </span>
                        </button>
                        {isExpanded && (
                          <div className="border-t border-maref-border px-4 py-4 pl-10">
                            <ToolDetailRow tool={tool} expanded={isExpanded} />
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {BUILTIN_TOOLS.length === 0 && (
          <div className="flex flex-col items-center justify-center py-20 text-maref-text-muted">
            <Wrench className="h-8 w-8 opacity-30 mb-2" />
            <span className="text-sm">暂无工具</span>
          </div>
        )}
      </div>
    </div>
  );
}