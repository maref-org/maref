"""
供应链安全模块测试
"""

import unittest
import tempfile
import json
import os
from datetime import datetime
from maref.supply_chain.sbom_generator import (
    SBOMGenerator, SBOM, Component, ComponentType, LicenseType, 
    Vulnerability, VulnerabilitySeverity
)
from maref.supply_chain.vulnerability_scanner import (
    VulnerabilityScanner, ScanResult, ScanStatus, VulnerabilitySource,
    VulnerabilityMatch
)


class TestSBOMGenerator(unittest.TestCase):
    """SBOM生成器测试类"""
    
    def setUp(self):
        """测试前设置"""
        self.generator = SBOMGenerator()
        
        # 创建测试组件
        self.test_component = Component(
            name="test-package",
            version="1.0.0",
            component_type=ComponentType.LIBRARY,
            purl="pkg:pypi/test-package@1.0.0",
            bom_ref="pkg:pypi/test-package@1.0.0",
            description="Test package for unit testing",
            licenses=[LicenseType.MIT]
        )
        
        # 创建测试SBOM
        self.test_sbom = SBOM(
            version=1,
            components=[self.test_component],
            vulnerabilities=[]
        )
    
    def test_sbom_to_dict(self):
        """测试SBOM转换为字典"""
        sbom_dict = self.test_sbom.to_dict()
        
        self.assertEqual(sbom_dict["bomFormat"], "CycloneDX")
        self.assertEqual(sbom_dict["specVersion"], "1.4")
        self.assertEqual(sbom_dict["version"], 1)
        self.assertIn("serialNumber", sbom_dict)
        self.assertIn("metadata", sbom_dict)
        self.assertIn("components", sbom_dict)
        
        # 检查组件
        components = sbom_dict["components"]
        self.assertEqual(len(components), 1)
        self.assertEqual(components[0]["name"], "test-package")
        self.assertEqual(components[0]["version"], "1.0.0")
        self.assertEqual(components[0]["type"], "library")
        self.assertEqual(components[0]["purl"], "pkg:pypi/test-package@1.0.0")
    
    def test_sbom_to_json(self):
        """测试SBOM转换为JSON"""
        json_str = self.test_sbom.to_json()
        
        # 验证JSON可以解析
        data = json.loads(json_str)
        self.assertEqual(data["bomFormat"], "CycloneDX")
        self.assertEqual(len(data["components"]), 1)
    
    def test_sbom_save_load(self):
        """测试SBOM保存和加载"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_file = f.name
        
        try:
            # 保存SBOM
            self.test_sbom.save_to_file(temp_file)
            
            # 验证文件存在且有内容
            self.assertTrue(os.path.exists(temp_file))
            with open(temp_file, 'r') as f:
                content = f.read()
                self.assertGreater(len(content), 0)
                data = json.loads(content)
                self.assertEqual(data["bomFormat"], "CycloneDX")
            
            # 加载SBOM
            loaded_sbom = SBOM.load_from_file(temp_file)
            
            # 验证加载的SBOM
            self.assertEqual(len(loaded_sbom.components), 1)
            self.assertEqual(loaded_sbom.components[0].name, "test-package")
            self.assertEqual(loaded_sbom.components[0].version, "1.0.0")
        
        finally:
            # 清理
            if os.path.exists(temp_file):
                os.unlink(temp_file)
    
    def test_sbom_with_vulnerabilities(self):
        """测试带漏洞的SBOM"""
        # 创建漏洞
        vulnerability = Vulnerability(
            id="CVE-2023-12345",
            source_name="NVD",
            description="Test vulnerability for unit testing",
            severity=VulnerabilitySeverity.HIGH,
            cvss_score=7.5,
            cvss_vector="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N"
        )
        
        # 创建带漏洞的SBOM
        sbom_with_vuln = SBOM(
            version=1,
            components=[self.test_component],
            vulnerabilities=[vulnerability]
        )
        
        sbom_dict = sbom_with_vuln.to_dict()
        
        # 验证漏洞存在
        self.assertIn("vulnerabilities", sbom_dict)
        vulnerabilities = sbom_dict["vulnerabilities"]
        self.assertEqual(len(vulnerabilities), 1)
        self.assertEqual(vulnerabilities[0]["id"], "CVE-2023-12345")
        self.assertEqual(vulnerabilities[0]["ratings"][0]["severity"], "high")
    
    def test_component_creation(self):
        """测试组件创建"""
        component = Component(
            name="another-package",
            version="2.1.3",
            component_type=ComponentType.FRAMEWORK,
            purl="pkg:pypi/another-package@2.1.3",
            bom_ref="pkg:pypi/another-package@2.1.3",
            description="Another test package",
            licenses=[LicenseType.APACHE_2_0],
            author="Test Author",
            publisher="Test Publisher",
            copyright="Copyright 2023 Test",
            cpe="cpe:2.3:a:another-package_project:another-package:2.1.3:*:*:*:*:python:*:*",
            hashes={"sha256": "abcd1234..."},
            external_references=[{"url": "https://example.com"}],
            properties=[{"name": "test", "value": "true"}],
            dependencies=["pkg:pypi/dependency@1.0.0"]
        )
        
        # 验证字段
        self.assertEqual(component.name, "another-package")
        self.assertEqual(component.version, "2.1.3")
        self.assertEqual(component.component_type, ComponentType.FRAMEWORK)
        self.assertEqual(component.purl, "pkg:pypi/another-package@2.1.3")
        self.assertEqual(len(component.licenses), 1)
        self.assertEqual(component.licenses[0], LicenseType.APACHE_2_0)
        self.assertEqual(component.author, "Test Author")
        self.assertIn("sha256", component.hashes)
        self.assertEqual(len(component.dependencies), 1)
    
    def test_generator_initialization(self):
        """测试生成器初始化"""
        self.assertIsNotNone(self.generator)
        self.assertIsNotNone(self.generator.audit_logger)
        self.assertIn("pip", self.generator.supported_package_managers)


class TestVulnerabilityScanner(unittest.TestCase):
    """漏洞扫描器测试类"""
    
    def setUp(self):
        """测试前设置"""
        self.scanner = VulnerabilityScanner()
        
        # 创建测试组件
        self.test_component = Component(
            name="test-package",
            version="1.0.0",
            component_type=ComponentType.LIBRARY,
            purl="pkg:pypi/test-package@1.0.0",
            bom_ref="pkg:pypi/test-package@1.0.0"
        )
        
        # 创建测试漏洞
        self.test_vulnerability = Vulnerability(
            id="CVE-2023-12345",
            source_name="Test",
            description="Test vulnerability",
            severity=VulnerabilitySeverity.HIGH,
            cvss_score=7.5
        )
    
    def test_scanner_initialization(self):
        """测试扫描器初始化"""
        self.assertIsNotNone(self.scanner)
        self.assertIsNotNone(self.scanner.audit_logger)
        
        # 应该至少有一些数据库
        self.assertGreater(len(self.scanner.databases), 0)
        
        # OSV数据库应该默认启用
        self.assertTrue(self.scanner.databases.get("osv", None) is not None)
        if "osv" in self.scanner.databases:
            self.assertTrue(self.scanner.databases["osv"].enabled)
    
    def test_enable_disable_database(self):
        """测试启用/禁用数据库"""
        # 跳过如果没有osv数据库
        if "osv" not in self.scanner.databases:
            self.skipTest("OSV database not available")
        
        # 禁用数据库
        result = self.scanner.disable_database("osv")
        self.assertTrue(result)
        self.assertFalse(self.scanner.databases["osv"].enabled)
        
        # 启用数据库
        result = self.scanner.enable_database("osv")
        self.assertTrue(result)
        self.assertTrue(self.scanner.databases["osv"].enabled)
    
    def test_scan_result_creation(self):
        """测试扫描结果创建"""
        scan_id = "test-scan-001"
        start_time = datetime.now()
        
        # 创建漏洞匹配
        match = VulnerabilityMatch(
            component=self.test_component,
            vulnerability=self.test_vulnerability,
            source=VulnerabilitySource.OSV,
            confidence=0.9,
            evidence={"test": "data"}
        )
        
        # 创建扫描结果
        scan_result = ScanResult(
            scan_id=scan_id,
            status=ScanStatus.COMPLETED,
            start_time=start_time,
            end_time=datetime.now(),
            components_scanned=1,
            vulnerabilities_found=1,
            matches=[match],
            errors=[],
            warnings=["Test warning"]
        )
        
        # 验证字段
        self.assertEqual(scan_result.scan_id, scan_id)
        self.assertEqual(scan_result.status, ScanStatus.COMPLETED)
        self.assertEqual(scan_result.components_scanned, 1)
        self.assertEqual(scan_result.vulnerabilities_found, 1)
        self.assertEqual(len(scan_result.matches), 1)
        self.assertEqual(len(scan_result.warnings), 1)
        
        # 测试转换为字典
        result_dict = scan_result.to_dict()
        self.assertEqual(result_dict["scan_id"], scan_id)
        self.assertEqual(result_dict["status"], "completed")
        self.assertEqual(result_dict["components_scanned"], 1)
        self.assertEqual(result_dict["vulnerabilities_found"], 1)
        self.assertEqual(len(result_dict["matches"]), 1)
        self.assertEqual(result_dict["matches"][0]["component"]["name"], "test-package")
        self.assertEqual(result_dict["matches"][0]["vulnerability"]["id"], "CVE-2023-12345")
    
    def test_vulnerability_match_creation(self):
        """测试漏洞匹配创建"""
        match = VulnerabilityMatch(
            component=self.test_component,
            vulnerability=self.test_vulnerability,
            source=VulnerabilitySource.NVD,
            confidence=0.85,
            evidence={
                "cve_id": self.test_vulnerability.id,
                "cvss_score": self.test_vulnerability.cvss_score
            }
        )
        
        self.assertEqual(match.component.name, "test-package")
        self.assertEqual(match.vulnerability.id, "CVE-2023-12345")
        self.assertEqual(match.source, VulnerabilitySource.NVD)
        self.assertEqual(match.confidence, 0.85)
        self.assertIn("cve_id", match.evidence)
    
    def test_scan_history(self):
        """测试扫描历史"""
        # 初始历史应该为空
        self.assertEqual(len(self.scanner.scan_history), 0)
        
        # 创建一个模拟扫描结果
        scan_result = ScanResult(
            scan_id="test-scan-history",
            status=ScanStatus.COMPLETED,
            start_time=datetime.now(),
            end_time=datetime.now(),
            components_scanned=0,
            vulnerabilities_found=0
        )
        
        self.scanner.scan_history.append(scan_result)
        
        # 验证历史
        self.assertEqual(len(self.scanner.scan_history), 1)
        self.assertEqual(self.scanner.scan_history[0].scan_id, "test-scan-history")
        
        # 测试获取扫描摘要
        summary = self.scanner.get_scan_summary("test-scan-history")
        self.assertIsNotNone(summary)
        self.assertEqual(summary["scan_id"], "test-scan-history")
        
        # 测试获取最近扫描
        recent_scans = self.scanner.get_recent_scans()
        self.assertEqual(len(recent_scans), 1)
        self.assertEqual(recent_scans[0]["scan_id"], "test-scan-history")
    
    def test_clear_cache(self):
        """测试清理缓存"""
        # 跳过如果没有osv数据库
        if "osv" not in self.scanner.databases:
            self.skipTest("OSV database not available")
        
        # 添加一些缓存数据
        self.scanner.databases["osv"].cache["test_key"] = {
            "data": "test",
            "timestamp": datetime.now().timestamp()
        }
        
        # 验证缓存有数据
        self.assertIn("test_key", self.scanner.databases["osv"].cache)
        
        # 清理特定数据库缓存
        self.scanner.clear_cache("osv")
        self.assertEqual(len(self.scanner.databases["osv"].cache), 0)
        
        # 再次添加缓存
        self.scanner.databases["osv"].cache["test_key2"] = {
            "data": "test2",
            "timestamp": datetime.now().timestamp()
        }
        
        # 清理所有缓存
        self.scanner.clear_cache()
        self.assertEqual(len(self.scanner.databases["osv"].cache), 0)


if __name__ == "__main__":
    unittest.main()