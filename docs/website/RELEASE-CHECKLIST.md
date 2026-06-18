# Website Version Release Checklist

每次发布新版本时，按此清单更新网站。

## Pre-Release

- [ ] 更新 `docusaurus.config.ts` 中的版本标签 (`versions.current.label`)
- [ ] 更新 `src/components/HomepageHeader.tsx` 中的版本徽章
- [ ] 同步中文翻译（如有版本相关文案）
- [ ] 更新根目录 `AGENTS.md` 版本号

## Build & Verify

- [ ] `npx docusaurus build` 编译通过
- [ ] `npx docusaurus start` 本地预览确认所有页面正常
- [ ] 检查无 broken links

## Post-Release

- [ ] 确认 GitHub Release 页面版本信息同步
- [ ] 确认 PyPI 包版本同步
