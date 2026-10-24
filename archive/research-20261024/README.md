# research 域归档（2026-10-24）

- 内容: `src/research/`（15 个源文件）+ `tests/research/`（14 个测试文件，8197 行）
- 冻结原因: 与当前 `maref` / `maref_lite` API 全面漂移，9 个测试模块 collection error；长期靠 `pytest --ignore=tests/research` 跳过，从未进入 CI 与覆盖率口径。
- 冻结后的排除: hatch `packages` 已移除 `src/research`；pytest `testpaths=["tests"]` + `--ignore=archive`；ruff `exclude=["archive"]`。
- 解冻方式: 整体迁回 `src/research` 与 `tests/research`，逐模块对齐 API 后恢复 CI；不要只迁回一半。
