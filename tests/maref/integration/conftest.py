"""Conftest for maref.integration tests.

历史遗留的 sys.modules MagicMock 注入已移除：经实证 27 个子模块均可
独立正常 import，不触发 circular import。无条件 mock 真实模块导致
integration 目录自身测试(HITLTier/aip_adapter 等)测到 mock 而非真实
实现(如 HITLTier.P2_LOG.value 返回 MagicMock)，是 CI 里 aip_adapter
mock 泄漏的根源。
"""
