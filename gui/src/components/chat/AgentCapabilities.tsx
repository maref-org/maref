import {
  BookOpen,
  Pencil,
  Terminal,
  Bug,
  type LucideIcon,
} from "lucide-react";
import type { CapabilityType } from "@/types";

const CAPABILITY_CONFIG: Record<CapabilityType, { icon: LucideIcon; label: string }> = {
  "read-code": { icon: BookOpen, label: "读代码：查问题、解释架构" },
  "edit-code": { icon: Pencil, label: "改代码：多文件重构、修 bug…" },
  "run-command": { icon: Terminal, label: "运行命令：构建、测试、lint…" },
  "debug-error": { icon: Bug, label: "排查报错：根据日志和运行结果定位根因" },
};

interface Props {
  capabilities: CapabilityType[];
}

export function AgentCapabilities({ capabilities }: Props) {
  return (
    <div className="ml-10 mt-1 space-y-1.5 mb-2">
      {capabilities.map((cap) => {
        const config = CAPABILITY_CONFIG[cap];
        if (!config) return null;
        return (
          <div
            key={cap}
            className="flex items-center gap-2 rounded-lg bg-maref-surface/50 px-3 py-1.5 text-xs text-maref-text-muted"
          >
            <config.icon className="h-3.5 w-3.5 text-maref-accent flex-shrink-0" />
            <span>{config.label}</span>
          </div>
        );
      })}
    </div>
  );
}