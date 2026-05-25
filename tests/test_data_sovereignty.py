"""
数据主权管理器测试
"""

import unittest

from maref.compliance.data_sovereignty import (
    CountryCode,
    DataCategory,
    DataClass,
    DataSovereigntyManager,
    DataSovereigntyStatus,
    DataTransferRequest,
    GeographicRestriction,
)


class TestDataSovereigntyManager(unittest.TestCase):
    """数据主权管理器测试类"""

    def setUp(self):
        """测试前设置"""
        self.manager = DataSovereigntyManager()

        # 创建测试数据类
        self.test_data_class = DataClass(
            id="test_confidential",
            name="Test Confidential Data",
            category=DataCategory.CONFIDENTIAL,
            classification_level="CONFIDENTIAL",
            cross_border_allowed=True,
            allowed_jurisdictions=[]  # 不设置地域限制，允许所有地区
        )

        self.manager.register_data_class(self.test_data_class)

    def test_initialization(self):
        """测试初始化"""
        self.assertIsNotNone(self.manager)
        self.assertGreater(len(self.manager.data_classes), 0)
        self.assertGreater(len(self.manager.geographic_restrictions), 0)

    def test_register_data_class(self):
        """测试注册数据类"""
        new_data_class = DataClass(
            id="test_new",
            name="Test New Data",
            category=DataCategory.INTERNAL,
            classification_level="INTERNAL"
        )

        self.manager.register_data_class(new_data_class)
        self.assertIn("test_new", self.manager.data_classes)
        self.assertEqual(self.manager.data_classes["test_new"].name, "Test New Data")

    def test_add_geographic_restriction(self):
        """测试添加地理限制"""
        new_restriction = GeographicRestriction(
            id="test_restriction",
            name="Test Restriction",
            countries_allowed=[CountryCode.US, CountryCode.CA],
            countries_blocked=[CountryCode.CN],
            data_categories_affected=[DataCategory.CONFIDENTIAL]
        )

        self.manager.add_geographic_restriction(new_restriction)
        self.assertIn("test_restriction", self.manager.geographic_restrictions)

    def test_evaluate_data_transfer_allowed(self):
        """测试评估允许的数据转移"""
        # 使用INTERNAL数据类，不受US export control影响
        internal_data_class = DataClass(
            id="test_internal",
            name="Test Internal Data",
            category=DataCategory.INTERNAL,
            classification_level="INTERNAL",
            cross_border_allowed=True,
            allowed_jurisdictions=[]
        )
        self.manager.register_data_class(internal_data_class)

        request = DataTransferRequest(
            request_id="test_request_1",
            data_classes=[internal_data_class],
            source_country=CountryCode.US,
            destination_country=CountryCode.CA,
            transfer_purpose="Business operations"
        )

        decision = self.manager.evaluate_data_transfer(request)

        self.assertEqual(decision.request_id, "test_request_1")
        self.assertEqual(decision.status, DataSovereigntyStatus.COMPLIANT)
        self.assertTrue(decision.allowed)
        self.assertEqual(len(decision.restrictions), 0)

    def test_evaluate_data_transfer_blocked_by_restriction(self):
        """测试评估被限制阻止的数据转移"""
        # 添加一个阻止CN的测试限制
        restriction = GeographicRestriction(
            id="block_china",
            name="Block China Transfers",
            countries_allowed=[CountryCode.US, CountryCode.CA],
            countries_blocked=[CountryCode.CN],
            data_categories_affected=[DataCategory.CONFIDENTIAL]
        )
        self.manager.add_geographic_restriction(restriction)

        # 尝试转移到中国
        request = DataTransferRequest(
            request_id="test_request_2",
            data_classes=[self.test_data_class],
            source_country=CountryCode.US,
            destination_country=CountryCode.CN,
            transfer_purpose="Business operations"
        )

        decision = self.manager.evaluate_data_transfer(request)

        self.assertEqual(decision.status, DataSovereigntyStatus.NON_COMPLIANT)
        self.assertFalse(decision.allowed)
        self.assertGreater(len(decision.restrictions), 0)

    def test_evaluate_data_transfer_gdpr_restriction(self):
        """测试GDPR限制下的数据转移"""
        # 使用个人数据类 (GDPR受限)
        personal_data = DataClass(
            id="personal_gdpr",
            name="GDPR Personal Data",
            category=DataCategory.PERSONAL,
            classification_level="PERSONAL",
            cross_border_allowed=False  # GDPR限制跨境传输
        )
        self.manager.register_data_class(personal_data)

        # 从德国(欧盟)到中国
        request = DataTransferRequest(
            request_id="test_request_3",
            data_classes=[personal_data],
            source_country=CountryCode.DE,
            destination_country=CountryCode.CN,
            transfer_purpose="Data processing"
        )

        decision = self.manager.evaluate_data_transfer(request)

        # GDPR个人数据不应允许跨境传输
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.status, DataSovereigntyStatus.NON_COMPLIANT)

    def test_evaluate_data_transfer_requires_approval(self):
        """测试需要批准的数据转移"""
        # 创建一个需要批准的地理限制
        restriction = GeographicRestriction(
            id="requires_approval_test",
            name="Test Approval Requirement",
            countries_allowed=[CountryCode.US, CountryCode.CA],
            data_categories_affected=[DataCategory.CONFIDENTIAL],
            requires_approval=True
        )
        self.manager.add_geographic_restriction(restriction)

        request = DataTransferRequest(
            request_id="test_request_4",
            data_classes=[self.test_data_class],
            source_country=CountryCode.US,
            destination_country=CountryCode.CA,
            transfer_purpose="Business operations"
        )

        decision = self.manager.evaluate_data_transfer(request)

        self.assertEqual(decision.status, DataSovereigntyStatus.REQUIRES_APPROVAL)
        self.assertTrue(decision.approval_required)
        self.assertIsNotNone(decision.approval_authority)

    def test_get_cross_border_compliance_report(self):
        """测试获取跨境合规报告"""
        report = self.manager.get_cross_border_compliance_report(
            CountryCode.US,
            CountryCode.CN
        )

        self.assertEqual(report["source_country"], "US")
        self.assertEqual(report["destination_country"], "CN")
        self.assertIn("applicable_restrictions", report)
        self.assertIn("affected_data_categories", report)
        self.assertIn("recommendations", report)

        # 应该包含关于中国数据本地化的建议
        recommendations = report["recommendations"]
        cn_recommendations = [r for r in recommendations if "China" in r]
        self.assertGreater(len(cn_recommendations), 0)

    def test_export_policy_configuration(self):
        """测试导出策略配置"""
        config = self.manager.export_policy_configuration()

        self.assertIn("data_classes", config)
        self.assertIn("geographic_restrictions", config)
        self.assertIn("compliance_policies", config)
        self.assertIn("export_timestamp", config)

        # 应该包含我们注册的测试数据类
        data_class_ids = [dc["id"] for dc in config["data_classes"]]
        self.assertIn("test_confidential", data_class_ids)

    def test_import_policy_configuration(self):
        """测试导入策略配置"""
        # 首先导出配置
        config = self.manager.export_policy_configuration()

        # 创建一个新的管理器
        new_manager = DataSovereigntyManager()

        # 初始应该是空的
        self.assertEqual(len(new_manager.data_classes), 7)  # 默认的7个

        # 导入配置
        new_manager.import_policy_configuration(config)

        # 应该包含我们注册的测试数据类
        self.assertIn("test_confidential", new_manager.data_classes)

        # 应该包含原配置中的地理限制
        self.assertGreaterEqual(
            len(new_manager.geographic_restrictions),
            len(self.manager.geographic_restrictions)
        )

    def test_get_transfer_history(self):
        """测试获取转移历史"""
        # 先执行一些转移
        request1 = DataTransferRequest(
            request_id="history_test_1",
            data_classes=[self.test_data_class],
            source_country=CountryCode.US,
            destination_country=CountryCode.CA,
            transfer_purpose="Test"
        )
        self.manager.evaluate_data_transfer(request1)

        request2 = DataTransferRequest(
            request_id="history_test_2",
            data_classes=[self.test_data_class],
            source_country=CountryCode.US,
            destination_country=CountryCode.CN,
            transfer_purpose="Test"
        )
        self.manager.evaluate_data_transfer(request2)

        # 获取历史
        history = self.manager.get_transfer_history()

        self.assertGreaterEqual(len(history), 2)

        # 检查历史记录包含我们的请求
        request_ids = [h["request_id"] for h in history]
        self.assertIn("history_test_1", request_ids)
        self.assertIn("history_test_2", request_ids)

    def test_data_class_cross_border_not_allowed(self):
        """测试数据类不允许跨境传输"""
        # 创建一个不允许跨境的数据类
        no_cross_border_class = DataClass(
            id="no_cross_border",
            name="No Cross-Border Data",
            category=DataCategory.RESTRICTED,
            classification_level="RESTRICTED",
            cross_border_allowed=False  # 关键: 不允许跨境
        )
        self.manager.register_data_class(no_cross_border_class)

        request = DataTransferRequest(
            request_id="test_no_cross_border",
            data_classes=[no_cross_border_class],
            source_country=CountryCode.US,
            destination_country=CountryCode.CA,  # 不同国家
            transfer_purpose="Test"
        )

        decision = self.manager.evaluate_data_transfer(request)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.status, DataSovereigntyStatus.NON_COMPLIANT)

        # 应该包含关于不允许跨境的限制
        restrictions_text = " ".join(decision.restrictions)
        self.assertIn("does not allow cross-border transfer", restrictions_text)

    def test_multiple_data_classes_mixed_compliance(self):
        """测试多个数据类的混合合规状态"""
        # 创建一个允许的数据类
        allowed_class = DataClass(
            id="allowed_class",
            name="Allowed Data",
            category=DataCategory.PUBLIC,
            classification_level="PUBLIC",
            cross_border_allowed=True
        )

        # 创建一个不允许的数据类
        blocked_class = DataClass(
            id="blocked_class",
            name="Blocked Data",
            category=DataCategory.RESTRICTED,
            classification_level="RESTRICTED",
            cross_border_allowed=False
        )

        self.manager.register_data_class(allowed_class)
        self.manager.register_data_class(blocked_class)

        # 同时传输两种数据
        request = DataTransferRequest(
            request_id="test_mixed",
            data_classes=[allowed_class, blocked_class],
            source_country=CountryCode.US,
            destination_country=CountryCode.CA,
            transfer_purpose="Mixed data transfer"
        )

        decision = self.manager.evaluate_data_transfer(request)

        # 因为有一个数据类不允许跨境，所以应该是不合规的
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.status, DataSovereigntyStatus.NON_COMPLIANT)

        # 应该有针对blocked_class的限制
        self.assertEqual(len(decision.restrictions), 1)
        self.assertIn("does not allow cross-border transfer", decision.restrictions[0])


if __name__ == "__main__":
    unittest.main()
