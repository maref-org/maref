# Skill 版本声明规范

## 要求

所有 Skill 的 `SKILL.md` 文件必须包含以下 YAML frontmatter 元数据：

```yaml
---
name: skill-name
description: Skill 描述
version: 1.0.0          # 语义化版本
created: YYYY-MM-DD     # 创建日期
updated: YYYY-MM-DD     # 最后更新日期
dependencies:           # 依赖列表
  - module.name
  - another.dependency
---
```

## 版本规范

### 语义化版本 (SemVer)

版本号格式：`MAJOR.MINOR.PATCH`

| 部分 | 说明 | 示例 |
|------|------|------|
| MAJOR | 不兼容的 API 变更 | 1.0.0 → 2.0.0 |
| MINOR | 向后兼容的功能新增 | 1.0.0 → 1.1.0 |
| PATCH | 向后兼容的缺陷修复 | 1.0.0 → 1.0.1 |

### 版本更新规则

| 变更类型 | 版本更新 | 说明 |
|---------|---------|------|
| 修复文档错别字 | PATCH | 不影响功能 |
| 新增使用示例 | MINOR | 向后兼容 |
| 修改工作流 API | MAJOR | 可能破坏现有脚本 |
| 添加新平台支持 | MINOR | 向后兼容 |
| 移除已弃用功能 | MAJOR | 不兼容变更 |

### 版本历史表

每个 SKILL.md 文件末尾必须包含版本历史表：

```markdown
## 版本历史

| 版本 | 日期 | 说明 |
|------|------|------|
| 1.0.0 | 2026-06-08 | 初始版本 |
| 1.1.0 | 2026-06-15 | 新增小红书平台支持 |
```

## 审计要求

1. **每次 Skill 变更必须更新版本号** — 否则视为不合规
2. **版本历史不可删除** — 只能追加
3. **重大变更必须记录说明** — 便于追溯
4. **依赖变更必须同步更新** — 确保前置条件准确

## 验证脚本

```bash
#!/bin/bash
# 验证所有 Skill 是否包含版本声明
for skill in .claude/skills/*/SKILL.md; do
  if ! grep -q "^version:" "$skill"; then
    echo "❌ 缺少版本声明: $skill"
  else
    version=$(grep "^version:" "$skill" | cut -d' ' -f2)
    name=$(grep "^name:" "$skill" | cut -d' ' -f2)
    echo "✅ $name v$version"
  fi
done
```
