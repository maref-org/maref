# C: 一键复现。所有断言基于决策向量哈希或数值指标，不含易变字段。
#
#   make reproduce     校验全部
#   make snapshot      重新生成 expected 快照（仅在确认行为变化是有意的时候）
#   make holdout       仅校验 holdout
#   make benign        仅校验编码无害负对照
#   make gate          仅校验全量 114 条门禁决策
#   make auditkit      仅校验 AuditKIT 回放 ASR

REPO_ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../..)
MAREF_SRC ?= $(REPO_ROOT)/src
# pick a Python that supports @dataclass(slots=True) (3.10+)
PY        ?= $(shell command -v python3.13 2>/dev/null || command -v python3.12 2>/dev/null || command -v python3.11 2>/dev/null || command -v python3.10 2>/dev/null || echo python3)

export PYTHONPATH := $(MAREF_SRC)

.PHONY: reproduce snapshot holdout benign gate auditkit clean

reproduce:
	@echo "== reproduce: gate + datasets + AuditKIT replay =="
	@$(PY) scripts/reproduce.py

snapshot:
	@$(PY) scripts/reproduce.py --update

holdout:
	@$(PY) scripts/reproduce.py holdout

benign:
	@$(PY) scripts/reproduce.py benign

gate:
	@$(PY) scripts/reproduce.py gate

auditkit:
	@$(PY) scripts/reproduce.py auditkit

clean:
	@rm -rf prep/expected
