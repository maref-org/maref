"""
供应链安全模块测试
"""

import unittest
import tempfile
import json
import os
from datetime import datetime
from pathlib import Path
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



class TestSBOMExtended(unittest.TestCase):
    """Extended SBOM tests for edge cases and complex serialization."""

    def test_sbom_to_dict_with_compositions(self):
        sbom = SBOM(version=2, components=[], vulnerabilities=[],
                    compositions=[{"aggregate": "complete", "assemblies": []}])
        d = sbom.to_dict()
        self.assertIn("compositions", d)
        self.assertEqual(d["compositions"][0]["aggregate"], "complete")

    def test_sbom_to_dict_auto_serial_number(self):
        sbom = SBOM(version=1, components=[], vulnerabilities=[])
        d = sbom.to_dict()
        self.assertIn("serialNumber", d)
        self.assertTrue(d["serialNumber"].startswith("urn:uuid:"))

    def test_sbom_load_from_file_with_full_data(self):
        data = {
            "bomFormat": "CycloneDX", "specVersion": "1.4", "version": 1,
            "serialNumber": "urn:uuid:test-0000-0000-0000-000000000001",
            "metadata": {"timestamp": "2026-01-01T00:00:00Z"},
            "components": [{
                "type": "library", "name": "libx", "version": "1.0",
                "purl": "pkg:pypi/libx@1.0",
                "bom-ref": "pkg:pypi/libx@1.0",
                "licenses": [{"license": {"id": "MIT"}}],
                "hashes": [{"alg": "SHA-256", "content": "abc"}],
            }],
            "vulnerabilities": [{
                "id": "CVE-2024-0001", "source": {"name": "NVD"},
                "ratings": [{"severity": "high", "score": 7.5, "method": "CVSSv3"}],
                "description": "Test vuln",
                "cwes": [{"cweId": 79}],
            }],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            tmp = f.name
        try:
            sbom = SBOM.load_from_file(tmp)
            self.assertEqual(len(sbom.components), 1)
            self.assertEqual(sbom.components[0].name, "libx")
            self.assertEqual(sbom.components[0].hashes.get("SHA-256"), "abc")
            self.assertIn(LicenseType.MIT, sbom.components[0].licenses)
            self.assertEqual(len(sbom.vulnerabilities), 1)
            self.assertEqual(sbom.vulnerabilities[0].id, "CVE-2024-0001")
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def test_sbom_to_dict_with_dependencies_from_field(self):
        comp = Component(
            name="a", version="1", component_type=ComponentType.LIBRARY,
            purl="pkg:pypi/a@1", bom_ref="pkg:pypi/a@1",
        )
        sbom = SBOM(version=1, components=[comp], dependencies=[{"ref": comp.bom_ref, "dependsOn": []}])
        d = sbom.to_dict()
        self.assertIn("dependencies", d)
        self.assertEqual(d["dependencies"][0]["ref"], comp.bom_ref)

    def test_sbom_to_dict_omit_optional_fields(self):
        comp = Component(
            name="minimal", version="1", component_type=ComponentType.LIBRARY,
            purl="pkg:pypi/minimal@1", bom_ref="pkg:pypi/minimal@1",
        )
        sbom = SBOM(version=1, components=[comp])
        d = sbom.to_dict()
        c = d["components"][0]
        self.assertNotIn("description", c)
        self.assertNotIn("author", c)


class TestSBOMGeneratorParsers(unittest.TestCase):
    """Tests for SBOMGenerator parser and version detection methods."""

    def setUp(self):
        """Use a generator instance to access private methods."""
        self.generator = SBOMGenerator()

    def test_parse_requirements_txt_simple(self):
        lines = ["requests==2.28.0", "flask>=2.0", "click", "numpy~=1.24"]
        components = self.generator._parse_requirements_txt(lines)
        names = {c.name for c in components}
        self.assertIn("requests", names)
        self.assertIn("flask", names)
        self.assertIn("click", names)
        self.assertIn("numpy", names)

    def test_parse_requirements_txt_skips_comments_and_urls(self):
        lines = ["# comment", "  ", "git+https://github.com/x/y.git@main", "pkg==1.0"]
        components = self.generator._parse_requirements_txt(lines)
        self.assertEqual(len(components), 1)
        self.assertEqual(components[0].name, "pkg")

    def test_parse_requirements_txt_env_markers(self):
        lines = ["dep==1.0; python_version >= '3.8'", "other==2.0"]
        components = self.generator._parse_requirements_txt(lines)
        self.assertEqual(len(components), 2)

    def test_parse_pip_freeze_output(self):
        output = "requests==2.28.0\nflask==2.2.0\nclick==8.1.0\n"
        components = self.generator._parse_pip_freeze_output(output)
        self.assertEqual(len(components), 3)
        self.assertEqual(components[0].name, "requests")
        self.assertEqual(components[0].version, "2.28.0")

    def test_parse_pip_freeze_skips_editable(self):
        output = "-e git+https://github.com/x/y.git@main#egg=xyz\nnormal==1.0\n"
        components = self.generator._parse_pip_freeze_output(output)
        self.assertEqual(len(components), 1)
        self.assertEqual(components[0].name, "normal")

    def test_parse_pip_freeze_handles_at_format(self):
        output = "pkg @ https://example.com/pkg-1.0.tar.gz\nnormal==1.0\n"
        components = self.generator._parse_pip_freeze_output(output)
        self.assertEqual(len(components), 1)
        self.assertEqual(components[0].name, "normal")

    def _mkdtemp(self):
        return Path(tempfile.mkdtemp())

    def test_parse_pyproject_toml_with_poetry(self):
        tmp_path = self._mkdtemp()
        path = tmp_path / "pyproject.toml"
        path.write_text(
            '[tool.poetry.dependencies]\n'
            'python = "^3.10"\n'
            'requests = "^2.28"\n'
            'flask = { version = "^2.0", extras = ["async"] }\n'
        )
        components = self.generator._parse_pyproject_toml(tmp_path)
        names = {c.name for c in components}
        self.assertIn("requests", names)
        self.assertIn("flask", names)
        self.assertNotIn("python", names)

    def test_detect_project_type_poetry(self):
        tmp_path = self._mkdtemp()
        (tmp_path / "pyproject.toml").write_text('[tool.poetry.dependencies]\nx = "^1.0"')
        result = self.generator._detect_project_type(tmp_path)
        self.assertEqual(result, "poetry")

    def test_detect_project_type_pip(self):
        tmp_path = self._mkdtemp()
        (tmp_path / "requirements.txt").write_text("x==1.0")
        result = self.generator._detect_project_type(tmp_path)
        self.assertEqual(result, "pip")

    def test_detect_project_type_pipenv(self):
        tmp_path = self._mkdtemp()
        (tmp_path / "Pipfile").write_text("[packages]\nx = \"*\"")
        result = self.generator._detect_project_type(tmp_path)
        self.assertEqual(result, "pipenv")

    def test_detect_project_type_conda(self):
        tmp_path = self._mkdtemp()
        (tmp_path / "environment.yml").write_text("dependencies:\n  - python=3.10")
        result = self.generator._detect_project_type(tmp_path)
        self.assertEqual(result, "conda")

    def test_get_version_from_pyproject_toml(self):
        tmp_path = self._mkdtemp()
        filepath = tmp_path / "pyproject.toml"
        filepath.write_text('[project]\nversion = "1.2.3"\n')
        v = self.generator._get_version_from_pyproject(filepath)
        self.assertEqual(v, "1.2.3")

    def test_get_version_from_pyproject_poetry(self):
        tmp_path = self._mkdtemp()
        filepath = tmp_path / "pyproject.toml"
        filepath.write_text('[tool.poetry]\nversion = "2.0.0"\n')
        v = self.generator._get_version_from_pyproject(filepath)
        self.assertEqual(v, "2.0.0")

    def test_get_version_from_setup_py(self):
        tmp_path = self._mkdtemp()
        path = tmp_path / "setup.py"
        path.write_text('from setuptools import setup\nsetup(version="3.0.0")\n')
        v = self.generator._get_version_from_setup_py(path)
        self.assertEqual(v, "3.0.0")

    def test_get_version_from_setup_cfg(self):
        tmp_path = self._mkdtemp()
        path = tmp_path / "setup.cfg"
        path.write_text("[metadata]\nversion = 4.0.0\n")
        v = self.generator._get_version_from_setup_cfg(path)
        self.assertEqual(v, "4.0.0")

    def test_get_version_from_init_py(self):
        tmp_path = self._mkdtemp()
        path = tmp_path / "__init__.py"
        path.write_text('__version__ = "5.0.0"\n')
        v = self.generator._get_version_from_init_py(path)
        self.assertEqual(v, "5.0.0")

    def test_get_version_from_version_file(self):
        tmp_path = self._mkdtemp()
        path = tmp_path / "VERSION"
        path.write_text("6.0.0\n")
        v = self.generator._get_version_from_version_file(path)
        self.assertEqual(v, "6.0.0")

    def test_get_project_version_falls_back(self):
        tmp_path = self._mkdtemp()
        v = self.generator._get_project_version(tmp_path)
        self.assertEqual(v, "0.0.0")

    def test_generate_sbom_uuid_deterministic(self):
        sbom1 = SBOM(version=1, components=[
            Component(name="a", version="1", component_type=ComponentType.LIBRARY,
                      purl="pkg:pypi/a@1", bom_ref="a"),
        ])
        sbom2 = SBOM(version=1, components=[
            Component(name="a", version="1", component_type=ComponentType.LIBRARY,
                      purl="pkg:pypi/a@1", bom_ref="a"),
        ])
        uuid1 = self.generator._generate_sbom_uuid(sbom1)
        uuid2 = self.generator._generate_sbom_uuid(sbom2)
        self.assertEqual(uuid1, uuid2)

    def test_compare_sboms_identical(self):
        comp = Component(
            name="a", version="1", component_type=ComponentType.LIBRARY,
            purl="pkg:pypi/a@1", bom_ref="pkg:pypi/a@1",
        )
        s1 = SBOM(version=1, components=[comp])
        s2 = SBOM(version=1, components=[comp])
        diff = self.generator.compare_sboms(s1, s2)
        self.assertEqual(len(diff["added_components"]), 0)
        self.assertEqual(len(diff["removed_components"]), 0)
        self.assertEqual(len(diff["version_changes"]), 0)

    def test_compare_sboms_added_removed(self):
        comp_a = Component(
            name="a", version="1", component_type=ComponentType.LIBRARY,
            purl="pkg:pypi/a@1", bom_ref="a",
        )
        comp_b = Component(
            name="b", version="1", component_type=ComponentType.LIBRARY,
            purl="pkg:pypi/b@1", bom_ref="b",
        )
        s1 = SBOM(version=1, components=[comp_a])
        s2 = SBOM(version=1, components=[comp_b])
        diff = self.generator.compare_sboms(s1, s2)
        self.assertEqual(len(diff["removed_components"]), 1)
        self.assertEqual(diff["removed_components"][0]["name"], "a")
        self.assertEqual(len(diff["added_components"]), 1)
        self.assertEqual(diff["added_components"][0]["name"], "b")

    def test_compare_sboms_version_changed(self):
        comp_old = Component(
            name="a", version="1.0", component_type=ComponentType.LIBRARY,
            purl="pkg:pypi/a@1.0", bom_ref="a",
        )
        comp_new = Component(
            name="a", version="2.0", component_type=ComponentType.LIBRARY,
            purl="pkg:pypi/a@1.0", bom_ref="a",
        )
        s1 = SBOM(version=1, components=[comp_old])
        s2 = SBOM(version=1, components=[comp_new])
        diff = self.generator.compare_sboms(s1, s2)
        self.assertEqual(len(diff["version_changes"]), 1)
        self.assertEqual(diff["version_changes"][0]["old_version"], "1.0")
        self.assertEqual(diff["version_changes"][0]["new_version"], "2.0")


class TestVulnerabilityScannerExtended(unittest.TestCase):
    """Extended VulnerabilityScanner tests for utility methods."""

    def setUp(self):
        self.scanner = VulnerabilityScanner()

    def test_ecosystem_from_purl_pypi(self):
        result = self.scanner._get_ecosystem_from_purl("pkg:pypi/requests@2.28")
        self.assertEqual(result, "PyPI")

    def test_ecosystem_from_purl_npm(self):
        result = self.scanner._get_ecosystem_from_purl("pkg:npm/express@4.18")
        self.assertEqual(result, "npm")

    def test_ecosystem_from_purl_maven(self):
        result = self.scanner._get_ecosystem_from_purl("pkg:maven/org.example/foo@1.0")
        self.assertEqual(result, "Maven")

    def test_ecosystem_from_purl_nuget(self):
        result = self.scanner._get_ecosystem_from_purl("pkg:nuget/Newtonsoft.Json@12.0")
        self.assertEqual(result, "NuGet")

    def test_ecosystem_from_purl_golang(self):
        result = self.scanner._get_ecosystem_from_purl("pkg:golang/github.com/foo/bar@v1")
        self.assertEqual(result, "Go")

    def test_ecosystem_from_purl_cargo(self):
        result = self.scanner._get_ecosystem_from_purl("pkg:cargo/serde@1.0")
        self.assertEqual(result, "crates.io")

    def test_ecosystem_from_purl_gem(self):
        result = self.scanner._get_ecosystem_from_purl("pkg:gem/rails@7.0")
        self.assertEqual(result, "RubyGems")

    def test_ecosystem_from_purl_unknown(self):
        result = self.scanner._get_ecosystem_from_purl("pkg:unknown/foo@1")
        self.assertIsNone(result)

    def test_ecosystem_from_purl_invalid(self):
        result = self.scanner._get_ecosystem_from_purl("not-a-valid-purl")
        self.assertIsNone(result)

    def test_snyk_ecosystem_from_purl_pip(self):
        result = self.scanner._get_snyk_ecosystem_from_purl("pkg:pypi/django@4.0")
        self.assertEqual(result, "pip")

    def test_snyk_ecosystem_from_purl_npm(self):
        result = self.scanner._get_snyk_ecosystem_from_purl("pkg:npm/react@18")
        self.assertEqual(result, "npm")

    def test_snyk_ecosystem_from_purl_golang(self):
        result = self.scanner._get_snyk_ecosystem_from_purl("pkg:golang/foo@v1")
        self.assertEqual(result, "golang")

    def test_generate_cpe_for_component_python(self):
        comp = Component(
            name="requests", version="2.28.0", component_type=ComponentType.LIBRARY,
            purl="pkg:pypi/requests@2.28.0", bom_ref="r",
        )
        cpe = self.scanner._generate_cpe_for_component(comp)
        self.assertIsNotNone(cpe)
        self.assertIn("requests", cpe)
        self.assertIn("python", cpe)

    def test_generate_cpe_for_component_npm(self):
        comp = Component(
            name="express", version="4.18.0", component_type=ComponentType.LIBRARY,
            purl="pkg:npm/express@4.18.0", bom_ref="e",
        )
        cpe = self.scanner._generate_cpe_for_component(comp)
        self.assertIsNotNone(cpe)
        self.assertIn("node.js", cpe)

    def test_generate_cpe_for_component_unknown(self):
        comp = Component(
            name="foo", version="1", component_type=ComponentType.LIBRARY,
            purl="pkg:unknown/foo@1", bom_ref="f",
        )
        result = self.scanner._generate_cpe_for_component(comp)
        self.assertIsNone(result)

    def test_respect_rate_limit_no_sleep(self):
        db = self.scanner.databases.get("osv")
        if not db:
            self.skipTest("OSV database not initialized")
        db.last_request_time = None
        db.rate_limit_rpm = 99999
        try:
            import asyncio
            asyncio.run(self.scanner._respect_rate_limit(db))
        except Exception:
            self.fail("rate limit raised unexpectedly")

    def test_parse_osv_vulnerability_valid(self):
        data = {
            "id": "CVE-2024-0001",
            "summary": "Test vuln",
            "details": "A" * 600,
            "aliases": ["GHSA-xxxx"],
            "severity": [{"type": "CVSS_V3", "score": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N"}],
            "database_specific": {"severity": "HIGH"},
            "references": [{"url": "https://example.com"}],
            "published": "2024-01-01",
            "modified": "2024-01-02",
        }
        vuln = self.scanner._parse_osv_vulnerability(data)
        self.assertIsNotNone(vuln)
        self.assertEqual(vuln.id, "CVE-2024-0001")
        self.assertLessEqual(len(vuln.description), 500)
        self.assertEqual(vuln.description, "Test vuln")

    def test_parse_osv_vulnerability_minimal(self):
        vuln = self.scanner._parse_osv_vulnerability({"id": "GHSA-xxxx"})
        self.assertIsNotNone(vuln)
        self.assertEqual(vuln.id, "GHSA-xxxx")
        self.assertEqual(vuln.severity, VulnerabilitySeverity.UNKNOWN)

    def test_add_database(self):
        from maref.supply_chain.vulnerability_scanner import VulnerabilityDatabase
        new_db = VulnerabilityDatabase(
            name="CustomDB", api_url="https://example.com", enabled=True,
        )
        self.scanner.add_database(new_db)
        self.assertIn("customdb", self.scanner.databases)
        self.assertTrue(self.scanner.databases["customdb"].enabled)

    def test_disable_database_not_found(self):
        result = self.scanner.disable_database("nonexistent")
        self.assertFalse(result)

    def test_get_scan_summary_not_found(self):
        result = self.scanner.get_scan_summary("nonexistent")
        self.assertIsNone(result)

    def test_get_recent_scans_empty(self):
        self.assertEqual(len(self.scanner.get_recent_scans()), 0)

    def test_scan_sbom_empty(self):
        sbom = SBOM(version=1, components=[])
        result = self.scanner.scan_sbom(sbom)
        self.assertIn(result.status, (ScanStatus.COMPLETED, ScanStatus.PARTIAL))


if __name__ == "__main__":
    unittest.main()