# 部署验证流程

## 预部署检查
1. 版本标签一致性: `python scripts/check_versions.py`
2. CI 全绿: GitHub Actions status
3. Security scan: TruffleHog + Bandit + Snyk

## 部署步骤
1. `kubectl apply -f k8s/production/`
2. 验证 pod 就绪: `kubectl wait --for=condition=Ready pods -l app=maref -n maref`
3. 健康检查: `curl http://localhost:8080/health`

## 回滚
`bash scripts/rollback.sh --target [前一版本]`
