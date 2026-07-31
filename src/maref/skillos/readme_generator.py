#!/usr/bin/env python3
"""
SkillOS README Template Generator — README 模板自动生成 + 发布检查清单

为 SkillOS 模块自动生成标准化的 README.md 模板，包含：
  - 项目概述与徽章
  - 架构文档
  - 快速开始指南
  - API 文档框架
  - 发布检查清单

用法:
    python3 scripts/readme_template_generator.py init <project-name> [--dir ./output]
    python3 scripts/readme_template_generator.py checklist [--type release|pr|audit]
    python3 scripts/readme_template_generator.py validate <readme-path>
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] SkillOS: %(message)s")
logger = logging.getLogger("skillos_readme")

# ── 模板引擎 ────────────────────────────────────────────────

SKILLOS_README_TEMPLATE = """# {project_name}

> {tagline}

[![Stars](https://img.shields.io/github/stars/maref-org/{repo_name}?style=for-the-badge&color=gold)](https://github.com/maref-org/{repo_name}/stargazers)
[![License](https://img.shields.io/github/license/maref-org/{repo_name}?style=for-the-badge&color=blue)](LICENSE)
[![Release](https://img.shields.io/github/v/release/maref-org/{repo_name}?style=for-the-badge&color=red)](https://github.com/maref-org/{repo_name}/releases)
[![CI](https://img.shields.io/github/actions/workflow/status/maref-org/{repo_name}/ci.yml?style=for-the-badge&color=green)](https://github.com/maref-org/{repo_name}/actions)

---

## 📋 项目概述

{description}

### 核心特性

- {feature_1}
- {feature_2}
- {feature_3}

---

## 🏗 架构

```
{repo_name}/
├── src/                 # 源代码
│   ├── core/           # 核心逻辑
│   ├── cli/            # CLI 入口
│   ├── api/            # API 接口
│   └── utils/          # 工具函数
├── tests/              # 测试
│   ├── unit/           # 单元测试
│   └── integration/    # 集成测试
├── docs/               # 文档
├── examples/           # 示例
├── scripts/            # 工具脚本
├── configs/            # 配置文件
├── deploy/             # 部署配置
└── requirements.txt    # 依赖管理
```

### 模块说明

| 模块 | 说明 | 职责 |
|------|------|------|
| `core` | {module_core_desc} | 核心算法与数据结构 |
| `cli` | {module_cli_desc} | 命令行交互入口 |
| `api` | {module_api_desc} | 外部系统集成接口 |

---

## 🚀 快速开始

### 前置要求

- Python 3.11+
- {dependency_1}
- {dependency_2}

### 安装

```bash
# 克隆仓库
git clone https://github.com/maref-org/{repo_name}.git
cd {repo_name}

# 安装依赖
pip install -r requirements.txt

# 安装开发依赖
pip install -r requirements-dev.txt
```

### 快速使用

```bash
# 基本用法
python3 -m {module_name} --help

# 示例
{python} -m {module_name} {example_args}

# 查看输出
cat output/{example_output}
```

### 配置

创建 `config.yaml`:

```yaml
{config_example}
```

---

## 📖 API 文档

### `{module_name}.core`

```python
from {module_name}.core import {api_class}

# 初始化
agent = {api_class}(config={{...}})

# 执行
result = agent.run(input_data)
```

### `{module_name}.cli`

```bash
python3 -m {module_name} {cli_command} --help
```

---

## 🧪 测试

```bash
# 运行所有测试
pytest tests/

# 运行单元测试
pytest tests/unit/

# 运行集成测试
pytest tests/integration/

# 测试覆盖率
pytest --cov={module_name} tests/
```

---

## 📊 检查清单

### 发布检查
- [ ] 版本号已更新 (VERSION / pyproject.toml)
- [ ] CHANGELOG.md 已更新
- [ ] 所有测试通过
- [ ] 文档已同步
- [ ] API 兼容性已验证
- [ ] 安全扫描无高危漏洞
- [ ] 许可证信息正确
- [ ] README 徽章链接正确

### PR 检查
- [ ] 代码符合规范 (pylint score ≥ 8)
- [ ] 新增代码有单元测试覆盖
- [ ] 公共 API 有文档字符串
- [ ] 类型注解完整
- [ ] 无调试代码或硬编码密钥

### 审计检查
- [ ] 依赖无已知漏洞
- [ ] 敏感信息无硬编码
- [ ] 日志无隐私数据
- [ ] 权限声明最小化

---

## 🤝 贡献

欢迎贡献！请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。

1. Fork 项目
2. 创建特性分支 (`git checkout -b feat/amazing-feature`)
3. 提交更改 (`git commit -m 'feat: add amazing feature'`)
4. 推送到分支 (`git push origin feat/amazing-feature`)
5. 提交 Pull Request

---

## 📄 许可证

{license_name} — 详见 [LICENSE](LICENSE)。

---

## 📬 联系方式

- 项目维护者: {maintainer}
- GitHub Issues: [github.com/maref-org/{repo_name}/issues](https://github.com/maref-org/{repo_name}/issues)
- 讨论区: [github.com/maref-org/{repo_name}/discussions](https://github.com/maref-org/{repo_name}/discussions)

---

*由 SkillOS README Template Generator 自动生成 · {generated_at}*
"""


def generate_readme(project_name: str, output_dir: str = ".", **kwargs) -> str:
    """生成标准化的 README.md"""
    repo_name = project_name.lower().replace(" ", "-").replace("_", "-")

    defaults = {
        "project_name": project_name,
        "repo_name": repo_name,
        "tagline": kwargs.get("tagline", f"{project_name} — SkillOS 模块"),
        "description": kwargs.get("description", f"{project_name} 是 MAREF 生态中的一个 SkillOS 模块，提供标准化的能力集成。"),
        "feature_1": kwargs.get("feature_1", "标准化接口 — 统一的模块接入规范"),
        "feature_2": kwargs.get("feature_2", "可插拔设计 — 支持动态加载和热替换"),
        "feature_3": kwargs.get("feature_3", "开箱即用 — 完整的 CLI 和 API 支持"),
        "module_core_desc": kwargs.get("module_core_desc", "核心业务逻辑"),
        "module_cli_desc": kwargs.get("module_cli_desc", "命令行界面"),
        "module_api_desc": kwargs.get("module_api_desc", "外部集成接口"),
        "dependency_1": kwargs.get("dependency_1", "Git 2.30+"),
        "dependency_2": kwargs.get("dependency_2", "Make 3.8+"),
        "module_name": repo_name.replace("-", "_"),
        "example_args": kwargs.get("example_args", "--input sample.json --output ./out"),
        "example_output": kwargs.get("example_output", "result.json"),
        "python": "python3",
        "api_class": kwargs.get("api_class", "Agent"),
        "cli_command": kwargs.get("cli_command", "run"),
        "license_name": kwargs.get("license_name", "Apache 2.0"),
        "maintainer": kwargs.get("maintainer", "MAREF Team"),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "config_example": kwargs.get("config_example", f"""# {repo_name} 配置
version: '1.0'
mode: production
log_level: info"""),
    }

    readme = SKILLOS_README_TEMPLATE.format(**defaults)

    output_path = Path(output_dir) / "README.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(readme)
    logger.info("✅ README.md 已生成: %s", output_path.resolve())
    return str(output_path.resolve())


# ── 检查清单 ────────────────────────────────────────────────

RELEASE_CHECKLIST = {
    "pre_release": [
        {"id": "REL-01", "check": "版本号已更新 (VERSION / pyproject.toml)", "severity": "blocker"},
        {"id": "REL-02", "check": "CHANGELOG.md 已更新，包含本次变更", "severity": "blocker"},
        {"id": "REL-03", "check": "所有自动化测试通过", "severity": "blocker"},
        {"id": "REL-04", "check": "文档已同步最新功能", "severity": "high"},
        {"id": "REL-05", "check": "API 兼容性已验证（无 break change）", "severity": "blocker"},
    ],
    "security": [
        {"id": "SEC-01", "check": "依赖项安全扫描无高危漏洞", "severity": "blocker"},
        {"id": "SEC-02", "check": "代码中无硬编码密钥或令牌", "severity": "blocker"},
        {"id": "SEC-03", "check": "日志输出无敏感信息", "severity": "high"},
    ],
    "quality": [
        {"id": "QLT-01", "check": "代码规范检查通过 (pylint ≥ 8 / ruff)", "severity": "high"},
        {"id": "QLT-02", "check": "类型注解完整性检查", "severity": "medium"},
        {"id": "QLT-03", "check": "公共 API 有完整文档字符串", "severity": "high"},
    ],
    "deploy": [
        {"id": "DEP-01", "check": "Docker 镜像构建成功", "severity": "high"},
        {"id": "DEP-02", "check": "部署配置已更新", "severity": "high"},
        {"id": "DEP-03", "check": "数据库迁移脚本已验证", "severity": "medium"},
    ],
}

PR_CHECKLIST = {
    "code_quality": [
        {"id": "PR-01", "check": "代码符合项目规范", "severity": "blocker"},
        {"id": "PR-02", "check": "新增代码有单元测试覆盖", "severity": "high"},
        {"id": "PR-03", "check": "公共 API 有文档字符串", "severity": "high"},
        {"id": "PR-04", "check": "类型注解完整", "severity": "medium"},
        {"id": "PR-05", "check": "无调试代码或 print 语句", "severity": "blocker"},
    ],
    "testing": [
        {"id": "TST-01", "check": "单元测试通过", "severity": "blocker"},
        {"id": "TST-02", "check": "集成测试通过（如适用）", "severity": "high"},
        {"id": "TST-03", "check": "测试覆盖率未下降", "severity": "medium"},
    ],
}

AUDIT_CHECKLIST = {
    "security": [
        {"id": "AUD-01", "check": "依赖无已知安全漏洞", "severity": "blocker"},
        {"id": "AUD-02", "check": "敏感信息无硬编码", "severity": "blocker"},
        {"id": "AUD-03", "check": "日志无隐私数据泄露风险", "severity": "high"},
        {"id": "AUD-04", "check": "权限声明最小化", "severity": "high"},
    ],
    "governance": [
        {"id": "AUD-05", "check": "许可证信息正确", "severity": "blocker"},
        {"id": "AUD-06", "check": "贡献者协议已签署", "severity": "high"},
        {"id": "AUD-07", "check": "出口管制合规", "severity": "medium"},
    ],
}


def print_checklist(checklist_type: str = "release"):
    """打印指定类型的检查清单"""
    checklists = {
        "release": ("📦 发布检查清单", RELEASE_CHECKLIST),
        "pr": ("🔀 PR 检查清单", PR_CHECKLIST),
        "audit": ("🔍 审计检查清单", AUDIT_CHECKLIST),
    }

    title, checklist = checklists.get(checklist_type, ("未知", {}))
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

    total = 0
    blocker = 0
    for category, items in checklist.items():
        print(f"\n  [{category.upper()}]")
        for item in items:
            sev = {"blocker": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
            print(f"  {sev[item['severity']]} {item['check']}")
            total += 1
            if item["severity"] == "blocker":
                blocker += 1

    print(f"\n  总计: {total} 项检查 (blocker: {blocker})")
    return checklist


# ── README 验证 ─────────────────────────────────────────────

def validate_readme(readme_path: str) -> dict:
    """验证 README.md 的完整性和质量"""
    path = Path(readme_path)
    if not path.exists():
        return {"valid": False, "errors": [f"文件不存在: {readme_path}"]}

    content = path.read_text()
    errors = []
    warnings = []

    # 检查必备元素
    required_sections = ["# ", "## ", "安装", "快速开始", "API", "贡献", "许可证"]
    for section in required_sections:
        if section not in content:
            warnings.append(f"缺少推荐章节: {section}")

    # 检查徽章
    if "shields.io" not in content and "badge" not in content.lower():
        warnings.append("缺少项目徽章 (shields.io)")

    # 检查代码示例
    code_blocks = content.count("```")
    if code_blocks < 2:
        warnings.append("缺少代码示例 (建议 ≥2 个代码块)")

    # 检查文档长度
    lines = len(content.splitlines())
    if lines < 30:
        errors.append(f"README 过短 ({lines} 行, 建议 ≥50 行)")
    elif lines < 50:
        warnings.append(f"README 偏短 ({lines} 行, 建议 ≥50 行)")

    # 检查许可证引用
    if "LICENSE" not in content:
        warnings.append("缺少许可证引用")

    # 检查目录
    if "## 目录" in content or "## 📋" in content or "- [" in content:
        has_toc = True
    else:
        warnings.append("缺少目录导航")
        has_toc = False

    return {
        "valid": len(errors) == 0,
        "path": readme_path,
        "lines": lines,
        "code_blocks": code_blocks // 2,
        "has_toc": has_toc,
        "errors": errors,
        "warnings": warnings,
        "score": max(0, 100 - len(errors) * 20 - len(warnings) * 5),
    }


# ── CLI ─────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]

    if cmd == "init":
        if len(sys.argv) < 3:
            print("用法: readme_template_generator.py init <project-name> [--dir ./output] [options]")
            sys.exit(1)
        project = sys.argv[2]
        output = "./"
        kwargs = {}
        for i, arg in enumerate(sys.argv[3:]):
            if arg == "--dir" and i + 4 < len(sys.argv):
                output = sys.argv[i + 4]
            elif arg.startswith("--"):
                key = arg.lstrip("-").replace("-", "_")
                val = sys.argv[i + 4] if i + 4 < len(sys.argv) else ""
                if not val.startswith("--"):
                    kwargs[key] = val

        path = generate_readme(project, output, **kwargs)
        print(f"\n📄 README.md 已生成: {path}")
        print("\n📋 发布检查清单:")
        print_checklist("release")

    elif cmd == "checklist":
        ctype = sys.argv[2] if len(sys.argv) > 2 else "release"
        print_checklist(ctype)

    elif cmd == "validate":
        if len(sys.argv) < 3:
            print("用法: readme_template_generator.py validate <readme-path>")
            sys.exit(1)
        result = validate_readme(sys.argv[2])
        print(f"\n📊 README 质量评分: {result['score']}/100")
        if result["errors"]:
            for e in result["errors"]:
                print(f"  ❌ {e}")
        if result["warnings"]:
            for w in result["warnings"]:
                print(f"  ⚠️  {w}")
        if result["valid"]:
            print(f"\n✅ README 验证通过! ({result['lines']} 行, {result['code_blocks']} 个代码示例)")

    else:
        print(f"未知命令: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
