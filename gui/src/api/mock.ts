import type { ModelProvider, Session, Message, Skill, Task, FileNode } from "@/types";

const providers: ModelProvider[] = [
  {
    id: "ollama",
    label: "Ollama (Local)",
    models: ["gemma3:4b", "qwen3:7b", "deepseek-r1:8b", "codellama:7b"],
    defaultModel: "qwen3:7b",
  },
  {
    id: "bailian",
    label: "百炼 Pro",
    models: ["deepseek-v4-pro", "qwen3-pro"],
    defaultModel: "deepseek-v4-pro",
  },
  {
    id: "siliconflow",
    label: "硅基流动",
    models: ["deepseek-v3", "qwen3-7b", "gemma-4"],
    defaultModel: "deepseek-v3",
  },
  {
    id: "openai",
    label: "OpenAI",
    models: ["gpt-4o", "gpt-4o-mini"],
    defaultModel: "gpt-4o",
  },
  {
    id: "anthropic",
    label: "Anthropic",
    models: ["claude-3.7-sonnet"],
    defaultModel: "claude-3.7-sonnet",
  },
];

const skills: Skill[] = [
  { id: "file-browser", name: "File Browser", description: "Browse and search project files", version: "1.0.0", installed: true, author: "MAREF" },
  { id: "git-ops", name: "Git Operations", description: "Commit, branch, merge, and review", version: "1.2.0", installed: true, author: "MAREF" },
  { id: "test-runner", name: "Test Runner", description: "Run and analyze test suites", version: "1.0.0", installed: false, author: "MAREF" },
  { id: "deploy-k8s", name: "K8s Deploy", description: "Deploy to Kubernetes clusters", version: "0.8.0", installed: false, author: "Community" },
  { id: "code-reviewer", name: "Code Reviewer", description: "Automated PR review and analysis", version: "1.1.0", installed: false, author: "Community" },
];

const mockSessions: Session[] = [
  {
    id: "sess-1",
    title: "New Agent",
    mode: "agent",
    provider: "bailian",
    model: "deepseek-v4-pro",
    contextPercent: 8,
    status: "idle",
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  },
];

const mockMessages: Record<string, Message[]> = {
  "sess-1": [
    {
      id: "msg-1",
      sessionId: "sess-1",
      role: "system",
      content: "run task",
      timestamp: new Date().toISOString(),
      capabilities: ["read-code", "edit-code", "run-command", "debug-error"],
    },
    {
      id: "msg-2",
      sessionId: "sess-1",
      role: "assistant",
      content:
        "我是 Codex 5.3。\n\n我可以做这些事（在你本机的 Cursor 里）：\n- 读代码、查问题、解释架构\n- 直接改代码（多文件重构、修 bug…）\n- 运行命令（构建、测试、lint…）\n- 排查报错（根据日志和运行结果定位根因）",
      timestamp: new Date().toISOString(),
    },
    {
      id: "msg-3",
      sessionId: "sess-1",
      role: "user",
      content: "你用什么模型",
      timestamp: new Date().toISOString(),
    },
    {
      id: "msg-4",
      sessionId: "sess-1",
      role: "assistant",
      content: "我是 Codex 5.3。",
      timestamp: new Date().toISOString(),
    },
  ],
};

const mockTasks: Task[] = [
  { id: "task-1", name: "run task", description: "", priority: 1, status: "failed", payload: {}, created_at: new Date().toISOString(), updated_at: new Date().toISOString(), started_at: null, completed_at: null, timeout_seconds: null, max_retries: 0, retry_count: 1, error_message: "something went wrong", session_id: "sess-1", tags: [] },
  { id: "task-2", name: "Refactor auth module", description: "", priority: 2, status: "completed", payload: {}, created_at: new Date().toISOString(), updated_at: new Date().toISOString(), started_at: null, completed_at: new Date().toISOString(), timeout_seconds: null, max_retries: 0, retry_count: 0, error_message: null, session_id: "sess-1", tags: [] },
  { id: "task-3", name: "Fix lint errors", description: "", priority: 0, status: "running", payload: {}, created_at: new Date().toISOString(), updated_at: new Date().toISOString(), started_at: new Date().toISOString(), completed_at: null, timeout_seconds: null, max_retries: 0, retry_count: 0, error_message: null, session_id: "sess-1", tags: [] },
];

const mockFileTree: FileNode[] = [
  {
    path: "gui",
    name: "gui",
    type: "directory",
    children: [
      {
        path: "gui/src",
        name: "src",
        type: "directory",
        children: [
          {
            path: "gui/src/App.tsx",
            name: "App.tsx",
            type: "file",
            extension: ".tsx",
          },
          {
            path: "gui/src/main.tsx",
            name: "main.tsx",
            type: "file",
            extension: ".tsx",
          },
          {
            path: "gui/src/index.css",
            name: "index.css",
            type: "file",
            extension: ".css",
          },
          {
            path: "gui/src/api",
            name: "api",
            type: "directory",
            children: [
              {
                path: "gui/src/api/client.ts",
                name: "client.ts",
                type: "file",
                extension: ".ts",
              },
              {
                path: "gui/src/api/mock.ts",
                name: "mock.ts",
                type: "file",
                extension: ".ts",
              },
            ],
          },
          {
            path: "gui/src/components",
            name: "components",
            type: "directory",
            children: [
              {
                path: "gui/src/components/chat",
                name: "chat",
                type: "directory",
                children: [
                  {
                    path: "gui/src/components/chat/ChatInput.tsx",
                    name: "ChatInput.tsx",
                    type: "file",
                    extension: ".tsx",
                  },
                  {
                    path: "gui/src/components/chat/MessageBubble.tsx",
                    name: "MessageBubble.tsx",
                    type: "file",
                    extension: ".tsx",
                  },
                  {
                    path: "gui/src/components/chat/MessageList.tsx",
                    name: "MessageList.tsx",
                    type: "file",
                    extension: ".tsx",
                  },
                ],
              },
              {
                path: "gui/src/components/layout",
                name: "layout",
                type: "directory",
                children: [
                  {
                    path: "gui/src/components/layout/Sidebar.tsx",
                    name: "Sidebar.tsx",
                    type: "file",
                    extension: ".tsx",
                  },
                  {
                    path: "gui/src/components/layout/ChatPanel.tsx",
                    name: "ChatPanel.tsx",
                    type: "file",
                    extension: ".tsx",
                  },
                ],
              },
            ],
          },
          {
            path: "gui/src/stores",
            name: "stores",
            type: "directory",
            children: [
              {
                path: "gui/src/stores/chatStore.ts",
                name: "chatStore.ts",
                type: "file",
                extension: ".ts",
              },
              {
                path: "gui/src/stores/sessionStore.ts",
                name: "sessionStore.ts",
                type: "file",
                extension: ".ts",
              },
              {
                path: "gui/src/stores/uiStore.ts",
                name: "uiStore.ts",
                type: "file",
                extension: ".ts",
              },
            ],
          },
          {
            path: "gui/src/types",
            name: "types",
            type: "directory",
            children: [
              {
                path: "gui/src/types/index.ts",
                name: "index.ts",
                type: "file",
                extension: ".ts",
              },
            ],
          },
          {
            path: "gui/src/hooks",
            name: "hooks",
            type: "directory",
            children: [
              {
                path: "gui/src/hooks/useSession.ts",
                name: "useSession.ts",
                type: "file",
                extension: ".ts",
              },
              {
                path: "gui/src/hooks/useKeyboard.ts",
                name: "useKeyboard.ts",
                type: "file",
                extension: ".ts",
              },
            ],
          },
          {
            path: "gui/src/lib",
            name: "lib",
            type: "directory",
            children: [
              {
                path: "gui/src/lib/utils.ts",
                name: "utils.ts",
                type: "file",
                extension: ".ts",
              },
            ],
          },
        ],
      },
      {
        path: "gui/package.json",
        name: "package.json",
        type: "file",
        extension: ".json",
      },
      {
        path: "gui/tsconfig.json",
        name: "tsconfig.json",
        type: "file",
        extension: ".json",
      },
    ],
  },
  {
    path: "README.md",
    name: "README.md",
    type: "file",
    extension: ".md",
  },
];

function delay(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

export const mockApi = {
  async getProviders() {
    await delay(200);
    return { providers };
  },

  async getSkills() {
    await delay(150);
    return { skills };
  },

  async createSession(body: { title: string; mode: string; provider: string; model: string }) {
    await delay(200);
    const [provider] = providers.filter((p) => p.id === body.provider);
    const session: Session = {
      id: `sess-${Date.now()}`,
      title: body.title,
      mode: body.mode as Session["mode"],
      provider: body.provider as Session["provider"],
      model: body.model || provider?.defaultModel || "gpt-4o",
      contextPercent: 0,
      status: "idle",
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };
    mockSessions.push(session);
    mockMessages[session.id] = [];
    return session;
  },

  async getSessions() {
    await delay(100);
    return { sessions: mockSessions };
  },

  async getSession(id: string) {
    await delay(100);
    const s = mockSessions.find((s) => s.id === id);
    if (!s) throw new Error("Session not found");
    return s;
  },

  async sendMessage(sessionId: string, content: string) {
    await delay(300);
    const msg: Message = {
      id: `msg-${Date.now()}`,
      sessionId,
      role: "user",
      content,
      timestamp: new Date().toISOString(),
    };
    mockMessages[sessionId] = [...(mockMessages[sessionId] ?? []), msg];
    return msg;
  },

  async getMessages(sessionId: string) {
    await delay(150);
    return { messages: mockMessages[sessionId] ?? [] };
  },

  getStreamUrl(sessionId: string) {
    return `/api/sessions/${sessionId}/stream`;
  },

  getTerminalUrl(sessionId: string) {
    return `ws://localhost:8000/api/sessions/${sessionId}/terminal`;
  },

  async getTasks() {
    await delay(100);
    return { tasks: mockTasks };
  },

  async getFileTree() {
    await delay(120);
    return { tree: mockFileTree };
  },
};