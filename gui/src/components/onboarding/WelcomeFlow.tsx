import { useState, useCallback, useEffect } from "react";
import { Monitor, Shield, Terminal, Lock, ArrowRight, Check, ChevronLeft } from "lucide-react";
import { checkBackendHealth, detectBackend } from "@/api/client";
import { useUIStore } from "@/stores/uiStore";
import { useSessionStore } from "@/stores/sessionStore";

const CAPABILITIES = [
  {
    icon: Monitor,
    title: "桌面操控",
    description: "截图→解析→键鼠→验证 全闭环",
  },
  {
    icon: Shield,
    title: "Agent治理",
    description: "Gray Code 状态机 + 四级安全决策树",
  },
  {
    icon: Terminal,
    title: "终端原生",
    description: "XTerm.js + 多Tab + 真实Shell",
  },
  {
    icon: Lock,
    title: "安全沙箱",
    description: "文件保护 + 网络白名单 + 操作审计",
  },
];

interface Props {
  onComplete: () => void;
}

export function WelcomeFlow({ onComplete }: Props) {
  const [step, setStep] = useState(0);
  const [backendHealthy, setBackendHealthy] = useState<boolean | null>(null);
  const [checkingHealth, setCheckingHealth] = useState(false);
  const { completeOnboarding } = useUIStore();
  const { addSession } = useSessionStore();

  const handleComplete = useCallback(() => {
    completeOnboarding();
    onComplete();
  }, [completeOnboarding, onComplete]);

  const handleSkip = useCallback(() => {
    completeOnboarding();
    onComplete();
  }, [completeOnboarding, onComplete]);

  const handleCheckHealth = useCallback(async () => {
    setCheckingHealth(true);
    const healthy = await checkBackendHealth();
    setBackendHealthy(healthy);
    await detectBackend();
    setCheckingHealth(false);
  }, []);

  const handleStartAgent = useCallback(() => {
    addSession({
      id: `sess-${Date.now()}`,
      title: "新 Agent",
      mode: "agent",
      provider: "bailian",
      model: "deepseek-v4-pro",
      contextPercent: 0,
      status: "idle",
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    });
    handleComplete();
  }, [addSession, handleComplete]);

  useEffect(() => {
    handleCheckHealth();
  }, [handleCheckHealth]);

  return (
    <div className="flex h-screen w-screen items-center justify-center bg-maref-bg">
      <div className="w-full max-w-lg rounded-xl border border-maref-border bg-maref-surface p-8 shadow-2xl">
        <div className="mb-8 text-center">
          <h1 className="mb-1 text-2xl font-bold tracking-tight text-maref-accent">
            MAREF
          </h1>
          <p className="text-sm text-maref-text-muted">Agent Governance OS</p>
        </div>

        {step === 0 && (
          <div className="flex flex-col items-center gap-6">
            <div className="flex h-20 w-20 items-center justify-center rounded-2xl bg-maref-accent/10">
              <Shield className="h-10 w-10 text-maref-accent" />
            </div>
            <div className="text-center">
              <h2 className="mb-2 text-lg font-semibold text-maref-text">
                欢迎来到 MAREF
              </h2>
              <p className="text-sm text-maref-text-muted leading-relaxed">
                MAREF 是一个 Agent 治理操作系统，
                <br />
                为 AI Agent 提供安全、可控、可审计的运行环境。
              </p>
            </div>
            <button
              onClick={() => setStep(1)}
              className="flex items-center gap-2 rounded-lg bg-maref-accent px-6 py-2.5 text-sm font-medium text-white hover:opacity-90 transition-opacity"
            >
              开始使用
              <ArrowRight className="h-4 w-4" />
            </button>
          </div>
        )}

        {step === 1 && (
          <div className="flex flex-col gap-4">
            <h2 className="text-center text-lg font-semibold text-maref-text">
              核心能力
            </h2>
            <div className="grid grid-cols-2 gap-3">
              {CAPABILITIES.map((cap) => (
                <div
                  key={cap.title}
                  className="flex flex-col items-center gap-2 rounded-lg border border-maref-border bg-maref-bg p-4 text-center"
                >
                  <cap.icon className="h-7 w-7 text-maref-accent" />
                  <span className="text-sm font-medium text-maref-text">
                    {cap.title}
                  </span>
                  <span className="text-[11px] text-maref-text-muted leading-relaxed">
                    {cap.description}
                  </span>
                </div>
              ))}
            </div>
            <div className="flex items-center justify-between">
              <button
                onClick={() => setStep(0)}
                className="flex items-center gap-1 rounded-lg px-3 py-2 text-sm text-maref-text-muted hover:text-maref-text transition-colors"
              >
                <ChevronLeft className="h-4 w-4" />
                返回
              </button>
              <button
                onClick={() => setStep(2)}
                className="flex items-center gap-2 rounded-lg bg-maref-accent px-6 py-2.5 text-sm font-medium text-white hover:opacity-90 transition-opacity"
              >
                下一步
                <ArrowRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="flex flex-col gap-5">
            <h2 className="text-center text-lg font-semibold text-maref-text">
              环境检测
            </h2>

            <div className="rounded-lg border border-maref-border bg-maref-bg p-4">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-sm font-medium text-maref-text">
                    Backend 连接
                  </span>
                  <p className="text-[11px] text-maref-text-muted mt-0.5">
                    maref serve (localhost:8000)
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {backendHealthy === null ? (
                    <button
                      onClick={handleCheckHealth}
                      disabled={checkingHealth}
                      className="rounded bg-maref-accent px-3 py-1.5 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50 transition-opacity"
                    >
                      {checkingHealth ? "检测中..." : "检测连接"}
                    </button>
                  ) : backendHealthy ? (
                    <span className="flex items-center gap-1 text-xs text-maref-success">
                      <Check className="h-3.5 w-3.5" />
                      已连接
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-xs text-maref-warning">
                      模拟模式
                    </span>
                  )}
                </div>
              </div>
            </div>

            <div className="rounded-lg border border-maref-border bg-maref-bg p-4">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-sm font-medium text-maref-text">
                    macOS 辅助功能权限
                  </span>
                  <p className="text-[11px] text-maref-text-muted mt-0.5">
                    系统偏好设置 → 隐私与安全性 → 辅助功能
                  </p>
                </div>
                {backendHealthy === null ? (
                  <span className="text-[11px] text-maref-text-muted">等待检测…</span>
                ) : backendHealthy ? (
                  <span className="flex items-center gap-1 text-xs text-maref-success">
                    <Check className="h-3.5 w-3.5" />
                    已连接
                  </span>
                ) : (
                  <span className="flex items-center gap-1 text-xs text-maref-warning">
                    <Shield className="h-3.5 w-3.5" />
                    需开启
                  </span>
                )}
              </div>
            </div>

            <div className="rounded-lg border border-maref-border bg-maref-bg p-4">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-sm font-medium text-maref-text">
                    文件系统访问
                  </span>
                  <p className="text-[11px] text-maref-text-muted mt-0.5">
                    工作目录读写权限
                  </p>
                </div>
                {backendHealthy === null ? (
                  <span className="text-[11px] text-maref-text-muted">等待检测…</span>
                ) : backendHealthy ? (
                  <span className="flex items-center gap-1 text-xs text-maref-success">
                    <Check className="h-3.5 w-3.5" />
                    已授权
                  </span>
                ) : (
                  <span className="text-xs text-maref-text-muted">
                    {checkingHealth ? "检测中…" : "模拟模式"}
                  </span>
                )}
              </div>
            </div>

            <div className="flex items-center justify-between">
              <button
                onClick={() => setStep(1)}
                className="flex items-center gap-1 rounded-lg px-3 py-2 text-sm text-maref-text-muted hover:text-maref-text transition-colors"
              >
                <ChevronLeft className="h-4 w-4" />
                返回
              </button>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleCheckHealth}
                  disabled={checkingHealth}
                  className="rounded-lg border border-maref-border px-3 py-2 text-xs text-maref-text-muted hover:text-maref-text hover:bg-maref-surface-alt transition-colors disabled:opacity-50"
                >
                  {checkingHealth ? "检测中…" : "重新检测"}
                </button>
                <button
                  onClick={() => setStep(3)}
                  className="flex items-center gap-2 rounded-lg bg-maref-accent px-6 py-2.5 text-sm font-medium text-white hover:opacity-90 transition-opacity"
                >
                  下一步
                  <ArrowRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="flex flex-col items-center gap-6">
            <div className="flex h-20 w-20 items-center justify-center rounded-full bg-maref-success/10">
              <Check className="h-10 w-10 text-maref-success" />
            </div>
            <div className="text-center">
              <h2 className="mb-2 text-lg font-semibold text-maref-text">
                一切就绪！
              </h2>
              <p className="text-sm text-maref-text-muted leading-relaxed">
                MAREF 已完成初始化配置。
                <br />
                现在可以启动你的第一个 Agent 了。
              </p>
            </div>
            <button
              onClick={handleStartAgent}
              className="flex items-center gap-2 rounded-lg bg-maref-accent px-6 py-2.5 text-sm font-medium text-white hover:opacity-90 transition-opacity"
            >
              启动我的第一个 Agent
              <ArrowRight className="h-4 w-4" />
            </button>
          </div>
        )}

        <div className="mt-6 flex items-center justify-center gap-2">
          {[0, 1, 2, 3].map((i) => (
            <button
              key={i}
              onClick={() => setStep(i)}
              className={`h-2 rounded-full transition-all ${
                i === step
                  ? "w-6 bg-maref-accent"
                  : "w-2 bg-maref-border hover:bg-maref-text-muted"
              }`}
            />
          ))}
        </div>

        <button
          onClick={handleSkip}
          className="mt-3 w-full text-center text-[11px] text-maref-text-muted hover:text-maref-text transition-colors"
        >
          跳过引导，直接进入
        </button>
      </div>
    </div>
  );
}
