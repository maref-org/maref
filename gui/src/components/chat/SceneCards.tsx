import { Globe, Search, BarChart3, FolderOpen } from "lucide-react";
import type { SceneId } from "@/types";

interface SceneData {
  id: SceneId;
  icon: React.ElementType;
  title: string;
  description: string;
  color: string;
}

const SCENES: SceneData[] = [
  {
    id: "web_reader",
    icon: Globe,
    title: "网页读取",
    description: "研读在线论文/文档，自动抓取、解析、摘要",
    color: "#6366f1",
  },
  {
    id: "research",
    icon: Search,
    title: "调研分析",
    description: "多平台信息聚合、对比、结构化输出",
    color: "#22c55e",
  },
  {
    id: "data_mining",
    icon: BarChart3,
    title: "数据挖掘",
    description: "市场数据抓取、清洗、趋势分析、可视化",
    color: "#f59e0b",
  },
  {
    id: "file_management",
    icon: FolderOpen,
    title: "文件管理",
    description: "本地文件夹整理、批量重命名、清单生成",
    color: "#ef4444",
  },
];

interface Props {
  onSceneSelect: (sceneId: SceneId) => void;
}

export function SceneCards({ onSceneSelect }: Props) {
  return (
    <div className="w-full max-w-[720px] mx-auto px-4">
      <div className="mb-6 text-center">
        <h1 className="text-2xl font-bold text-maref-text mb-1">
          MAREF Agent
          <span className="ml-2 inline-block rounded-full bg-maref-accent/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-maref-accent align-middle">
            BETA
          </span>
        </h1>
        <p className="text-sm text-maref-text-muted">
          多场景办公任务，交给 MAREF 搞定
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {SCENES.map((scene) => {
          const Icon = scene.icon;
          return (
            <button
              key={scene.id}
              onClick={() => onSceneSelect(scene.id)}
              className="group relative flex flex-col items-center gap-2 rounded-xl border border-maref-border bg-maref-surface p-4 text-center transition-all hover:border-maref-accent/50 hover:shadow-sm"
            >
              <span
                className="absolute top-2.5 left-2.5 h-2 w-2 rounded-full"
                style={{ backgroundColor: scene.color }}
              />
              <Icon
                className="h-8 w-8 mt-1 mb-1 transition-transform group-hover:scale-110"
                style={{ color: scene.color }}
              />
              <h3 className="text-[16px] font-bold text-maref-text leading-tight">
                {scene.title}
              </h3>
              <p className="text-xs text-maref-text-muted line-clamp-2 leading-relaxed">
                {scene.description}
              </p>
            </button>
          );
        })}
      </div>
    </div>
  );
}
