from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from maref.supply_chain.sbom_generator import (
    SBOM,
    Component,
    ComponentType,
    LicenseType,
    SBOMGenerator,
    Vulnerability,
    VulnerabilitySeverity,
)


class TestComponent:
    def test_default_fields(self) -> None:
        c = Component(name="pkg", version="1.0", component_type=ComponentType.LIBRARY, purl="pkg:pypi/pkg@1.0", bom_ref="ref1")
        assert c.description is None
        assert c.licenses == []
        assert c.hashes == {}

    def test_with_all_fields(self) -> None:
        c = Component(
            name="pkg", version="2.0", component_type=ComponentType.APPLICATION,
            purl="pkg:pypi/pkg@2.0", bom_ref="ref2", description="desc",
            author="author", publisher="pub", licenses=[LicenseType.MIT],
            copyright="(c) 2024", cpe="cpe:2.3:a:pkg", hashes={"sha256": "abc"},
            dependencies=["dep1"],
        )
        assert c.author == "author"
        assert c.cpe == "cpe:2.3:a:pkg"
        assert c.hashes["sha256"] == "abc"


class TestSBOM:
    def test_to_dict_basic(self) -> None:
        sbom = SBOM(version=1)
        d = sbom.to_dict()
        assert d["bomFormat"] == "CycloneDX"
        assert d["specVersion"] == "1.4"
        assert d["version"] == 1
        assert "serialNumber" in d
        assert "metadata" in d
        assert "components" in d

    def test_to_dict_with_components(self) -> None:
        c = Component(name="pkg", version="1.0", component_type=ComponentType.LIBRARY, purl="pkg:pypi/pkg@1.0", bom_ref="r1")
        sbom = SBOM(components=[c])
        d = sbom.to_dict()
        assert len(d["components"]) == 1
        assert d["components"][0]["name"] == "pkg"

    def test_to_dict_with_vulnerabilities(self) -> None:
        v = Vulnerability(id="CVE-123", source_name="test", severity=VulnerabilitySeverity.HIGH, cvss_score=7.5)
        sbom = SBOM(vulnerabilities=[v])
        d = sbom.to_dict()
        assert "vulnerabilities" in d
        assert d["vulnerabilities"][0]["id"] == "CVE-123"

    def test_to_dict_with_dependencies(self) -> None:
        sbom = SBOM(dependencies=[{"ref": "r1", "dependsOn": ["r2"]}])
        d = sbom.to_dict()
        assert "dependencies" in d
        assert d["dependencies"][0]["ref"] == "r1"

    def test_to_dict_with_compositions(self) -> None:
        sbom = SBOM(compositions=[{"aggregate": "complete"}])
        d = sbom.to_dict()
        assert "compositions" in d

    def test_to_dict_component_detail_fields(self) -> None:
        c = Component(
            name="pkg", version="1.0", component_type=ComponentType.LIBRARY,
            purl="pkg:pypi/pkg@1.0", bom_ref="r1", description="desc",
            author="auth", publisher="pub", licenses=[LicenseType.MIT, LicenseType.APACHE_2_0],
            copyright="(c)", cpe="cpe", swid="swid123",
            hashes={"sha256": "abc123"}, external_references=[{"url": "https://example.com"}],
            properties=[{"key": "val"}], dependencies=["dep1"],
        )
        sbom = SBOM(components=[c])
        d = sbom.to_dict()
        comp = d["components"][0]
        assert comp["description"] == "desc"
        assert comp["author"] == "auth"
        assert comp["publisher"] == "pub"
        assert len(comp["licenses"]) == 2
        assert comp["copyright"] == "(c)"
        assert comp["cpe"] == "cpe"
        assert "swid" in comp
        assert len(comp["hashes"]) == 1
        assert len(comp["externalReferences"]) == 1
        assert len(comp["properties"]) == 1

    def test_to_dict_vulnerability_detail(self) -> None:
        v = Vulnerability(
            id="CVE-456", source_name="NVD", description="desc",
            severity=VulnerabilitySeverity.CRITICAL, cvss_score=9.0, cvss_vector="CVSS:3.1/AV:N/AC:L",
            cwe_ids=["CWE-79"], references=[{"url": "https://nvd.nist.gov"}],
            published_date="2024-01-01", last_updated_date="2024-06-01",
        )
        sbom = SBOM(vulnerabilities=[v])
        d = sbom.to_dict()
        vuln = d["vulnerabilities"][0]
        assert vuln["description"] == "desc"
        assert vuln["ratings"][0]["severity"] == "critical"
        assert vuln["ratings"][0]["score"] == 9.0
        assert vuln["ratings"][0]["vector"] == "CVSS:3.1/AV:N/AC:L"
        assert "cwes" in vuln
        assert "references" in vuln
        assert vuln["published"] == "2024-01-01"
        assert vuln["updated"] == "2024-06-01"

    def test_to_json(self) -> None:
        sbom = SBOM(version=1)
        json_str = sbom.to_json()
        parsed = json.loads(json_str)
        assert parsed["bomFormat"] == "CycloneDX"

    def test_save_and_load_from_file(self) -> None:
        sbom = SBOM(version=1, components=[
            Component(name="pkg", version="1.0", component_type=ComponentType.LIBRARY, purl="pkg:pypi/pkg@1.0", bom_ref="r1"),
        ])
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = f.name
        try:
            sbom.save_to_file(path)
            loaded = SBOM.load_from_file(path)
            assert loaded.bom_format == "CycloneDX"
            assert loaded.version == 1
            assert len(loaded.components) == 1
            assert loaded.components[0].name == "pkg"
        finally:
            os.unlink(path)

    def test_load_from_file_with_vulnerabilities(self) -> None:
        data = {
            "bomFormat": "CycloneDX", "specVersion": "1.4", "version": 1,
            "serialNumber": "urn:uuid:abc", "metadata": {},
            "components": [{"name": "pkg", "version": "1.0", "type": "library", "purl": "pkg:pypi/pkg@1.0", "bom-ref": "r1", "licenses": [{"license": {"id": "MIT"}}]}],
            "vulnerabilities": [{"id": "CVE-1", "source": {"name": "NVD"}, "ratings": [{"severity": "HIGH", "score": 7.5, "vector": "CVSS:3.1/AV:N"}], "description": "test", "cwes": ["CWE-79"], "references": [], "published": "2024-01-01", "updated": "2024-06-01"}],
            "dependencies": [{"ref": "r1", "dependsOn": ["r2"]}],
            "compositions": [{"aggregate": "complete"}],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = f.name
        try:
            loaded = SBOM.load_from_file(path)
            assert len(loaded.components) == 1
            assert loaded.components[0].licenses == [LicenseType.MIT]
            assert len(loaded.vulnerabilities) == 1
            assert loaded.vulnerabilities[0].cvss_score == 7.5
            assert loaded.dependencies == [{"ref": "r1", "dependsOn": ["r2"]}]
            assert loaded.compositions == [{"aggregate": "complete"}]
        finally:
            os.unlink(path)

    def test_load_from_file_unknown_license(self) -> None:
        data = {
            "bomFormat": "CycloneDX", "specVersion": "1.4", "version": 1,
            "serialNumber": "urn:uuid:abc", "metadata": {},
            "components": [{"name": "pkg", "version": "1.0", "type": "library", "purl": "pkg:pypi/pkg@1.0", "bom-ref": "r1", "licenses": [{"license": {"id": "UNKNOWN_LICENSE"}}]}],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = f.name
        try:
            loaded = SBOM.load_from_file(path)
            assert loaded.components[0].licenses == [LicenseType.OTHER]
        finally:
            os.unlink(path)

    def test_to_dict_dependencies_from_components(self) -> None:
        c = Component(name="pkg", version="1.0", component_type=ComponentType.LIBRARY, purl="pkg:pypi/pkg@1.0", bom_ref="r1", dependencies=["dep1"])
        sbom = SBOM(components=[c])
        d = sbom.to_dict()
        assert "dependencies" in d
        assert d["dependencies"][0]["ref"] == "r1"


class TestSBOMGenerator:
    def test_init_defaults(self) -> None:
        gen = SBOMGenerator()
        assert gen.supported_package_managers == ["pip", "poetry", "pipenv", "conda"]

    def test_detect_project_type_pyproject(self, tmp_path: Path) -> None:
        gen = SBOMGenerator()
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname = \"test\"\n")
        assert gen._detect_project_type(tmp_path) == "poetry"

    def test_detect_project_type_pipfile(self, tmp_path: Path) -> None:
        gen = SBOMGenerator()
        (tmp_path / "Pipfile").write_text("")
        assert gen._detect_project_type(tmp_path) == "pipenv"

    def test_detect_project_type_conda_yaml(self, tmp_path: Path) -> None:
        gen = SBOMGenerator()
        (tmp_path / "environment.yml").write_text("")
        assert gen._detect_project_type(tmp_path) == "conda"

    def test_detect_project_type_requirements(self, tmp_path: Path) -> None:
        gen = SBOMGenerator()
        (tmp_path / "requirements.txt").write_text("")
        assert gen._detect_project_type(tmp_path) == "pip"

    def test_detect_project_type_default(self, tmp_path: Path) -> None:
        gen = SBOMGenerator()
        assert gen._detect_project_type(tmp_path) == "pip"

    def test_generate_from_project_no_path(self) -> None:
        gen = SBOMGenerator()
        with pytest.raises(FileNotFoundError):
            gen.generate_from_project("/nonexistent/path")

    def test_get_project_version_default(self, tmp_path: Path) -> None:
        gen = SBOMGenerator()
        assert gen._get_project_version(tmp_path) == "0.0.0"

    def test_get_version_from_pyproject_poetry(self, tmp_path: Path) -> None:
        gen = SBOMGenerator()
        f = tmp_path / "pyproject.toml"
        f.write_text("[tool.poetry]\nversion = \"1.2.3\"\n")
        assert gen._get_version_from_pyproject(f) == "1.2.3"

    def test_get_version_from_pyproject_project(self, tmp_path: Path) -> None:
        gen = SBOMGenerator()
        f = tmp_path / "pyproject.toml"
        f.write_text("[project]\nversion = \"2.0.0\"\n")
        assert gen._get_version_from_pyproject(f) == "2.0.0"

    def test_get_version_from_setup_py(self, tmp_path: Path) -> None:
        gen = SBOMGenerator()
        f = tmp_path / "setup.py"
        f.write_text("from setuptools import setup\nsetup(version='3.0.0')\n")
        assert gen._get_version_from_setup_py(f) == "3.0.0"

    def test_get_version_from_setup_cfg(self, tmp_path: Path) -> None:
        gen = SBOMGenerator()
        f = tmp_path / "setup.cfg"
        f.write_text("[metadata]\nversion = 4.0.0\n")
        assert gen._get_version_from_setup_cfg(f) == "4.0.0"

    def test_get_version_from_init_py(self, tmp_path: Path) -> None:
        gen = SBOMGenerator()
        f = tmp_path / "__init__.py"
        f.write_text("__version__ = '5.0.0'\n")
        assert gen._get_version_from_init_py(f) == "5.0.0"

    def test_get_version_from_version_file(self, tmp_path: Path) -> None:
        gen = SBOMGenerator()
        f = tmp_path / "VERSION"
        f.write_text("6.0.0\n")
        assert gen._get_version_from_version_file(f) == "6.0.0"

    def test_get_version_priority(self, tmp_path: Path) -> None:
        gen = SBOMGenerator()
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nversion = \"7.0.0\"\n")
        (tmp_path / "VERSION").write_text("8.0.0\n")
        assert gen._get_project_version(tmp_path) == "7.0.0"

    def test_parse_pip_freeze_output(self) -> None:
        gen = SBOMGenerator()
        output = "pkg1==1.0.0\npkg2==2.0.0\n# comment\n-e git+https://example.com/repo.git\npkg3==3.0.0; python_version >= '3.6'\n"
        components = gen._parse_pip_freeze_output(output)
        assert len(components) == 3
        assert components[0].name == "pkg1"
        assert components[2].name == "pkg3"

    def test_parse_pip_freeze_output_empty(self) -> None:
        gen = SBOMGenerator()
        assert gen._parse_pip_freeze_output("") == []
        assert gen._parse_pip_freeze_output("# only comment") == []

    def test_parse_pip_freeze_output_at_url(self) -> None:
        gen = SBOMGenerator()
        assert gen._parse_pip_freeze_output("pkg@https://example.com/pkg.tar.gz") == []

    def test_parse_requirements_txt(self) -> None:
        gen = SBOMGenerator()
        lines = ["pkg1==1.0.0", "pkg2>=2.0.0", "pkg3<=3.0.0", "pkg4~=4.0.0", "pkg5", "# comment", "-e git+https://example.com/repo.git"]
        components = gen._parse_requirements_txt(lines)
        assert len(components) == 5

    def test_parse_requirements_txt_at_url(self) -> None:
        gen = SBOMGenerator()
        components = gen._parse_requirements_txt(["pkg@https://example.com/pkg.tar.gz"])
        assert len(components) == 0

    def test_parse_poetry_output(self) -> None:
        gen = SBOMGenerator()
        output = "Warning: some warning\npkg1 1.0.0 First package\npkg2 2.0.0\n"
        components = gen._parse_poetry_output(output)
        assert len(components) == 2
        assert components[0].name == "pkg1"
        assert components[0].version == "1.0.0"

    def test_parse_poetry_output_duplicates(self) -> None:
        gen = SBOMGenerator()
        output = "pkg1 1.0.0\npkg1 1.0.0\n"
        components = gen._parse_poetry_output(output)
        assert len(components) == 1

    def test_parse_pyproject_toml(self, tmp_path: Path) -> None:
        gen = SBOMGenerator()
        f = tmp_path / "pyproject.toml"
        f.write_bytes('[tool.poetry.dependencies]\nrequest = "^2.0"\nflask = "1.0"\n'.encode())
        components = gen._parse_pyproject_toml(tmp_path)
        assert len(components) == 2
        names = {c.name for c in components}
        assert "request" in names
        assert "flask" in names

    def test_parse_pyproject_toml_skips_python(self, tmp_path: Path) -> None:
        gen = SBOMGenerator()
        f = tmp_path / "pyproject.toml"
        f.write_bytes('[tool.poetry.dependencies]\npython = "^3.10"\n'.encode())
        components = gen._parse_pyproject_toml(tmp_path)
        assert len(components) == 0

    def test_parse_pyproject_toml_dict_spec(self, tmp_path: Path) -> None:
        gen = SBOMGenerator()
        f = tmp_path / "pyproject.toml"
        f.write_bytes('[tool.poetry.dependencies]\nrequest = {version = "^2.0"}\n'.encode())
        components = gen._parse_pyproject_toml(tmp_path)
        assert len(components) == 1

    def test_parse_pyproject_toml_no_file(self, tmp_path: Path) -> None:
        gen = SBOMGenerator()
        assert gen._parse_pyproject_toml(tmp_path) == []

    def test_parse_pipenv_graph_output(self) -> None:
        gen = SBOMGenerator()
        data = json.dumps([{"package_name": "pkg1", "installed_version": "1.0.0", "dependencies": []}])
        components = gen._parse_pipenv_graph_output(data)
        assert len(components) == 1
        assert components[0].name == "pkg1"

    def test_parse_pipenv_graph_output_with_deps(self) -> None:
        gen = SBOMGenerator()
        data = json.dumps([{"package_name": "pkg1", "installed_version": "1.0.0", "dependencies": [{"package_name": "dep1"}]}])
        components = gen._parse_pipenv_graph_output(data)
        assert len(components) == 1
        assert components[0].dependencies == ["dep1"]

    def test_parse_pipenv_graph_output_invalid(self) -> None:
        gen = SBOMGenerator()
        assert gen._parse_pipenv_graph_output("not json") == []

    def test_parse_pipfile(self, tmp_path: Path) -> None:
        gen = SBOMGenerator()
        f = tmp_path / "Pipfile"
        f.write_bytes("[[source]]\nurl = \"https://pypi.org/simple\"\n[packages]\npkg1 = \"*\"\npkg2 = {version = \">=1.0\"}\n".encode())
        components = gen._parse_pipfile(tmp_path)
        assert len(components) == 2

    def test_parse_pipfile_no_file(self, tmp_path: Path) -> None:
        gen = SBOMGenerator()
        assert gen._parse_pipfile(tmp_path) == []

    def test_parse_conda_list_output(self) -> None:
        gen = SBOMGenerator()
        data = json.dumps([{"name": "numpy", "version": "1.24.0", "channel": "conda-forge"}])
        components = gen._parse_conda_list_output(data)
        assert len(components) == 1
        assert components[0].name == "numpy"

    def test_parse_conda_list_output_no_channel(self) -> None:
        gen = SBOMGenerator()
        data = json.dumps([{"name": "numpy", "version": "1.24.0"}])
        components = gen._parse_conda_list_output(data)
        assert len(components) == 1
        assert "conda-forge" in components[0].purl

    def test_parse_conda_list_output_invalid(self) -> None:
        gen = SBOMGenerator()
        assert gen._parse_conda_list_output("not json") == []

    def test_parse_environment_yml(self, tmp_path: Path) -> None:
        gen = SBOMGenerator()
        f = tmp_path / "environment.yml"
        f.write_text("dependencies:\n  - numpy=1.24.0\n  - pandas\n")
        components = gen._parse_environment_yml(tmp_path)
        assert len(components) == 2

    def test_parse_environment_yml_no_file(self, tmp_path: Path) -> None:
        gen = SBOMGenerator()
        assert gen._parse_environment_yml(tmp_path) == []

    def test_compare_sboms_added_removed(self) -> None:
        gen = SBOMGenerator()
        c1 = Component(name="pkg1", version="1.0", component_type=ComponentType.LIBRARY, purl="pkg:pypi/pkg1@1.0", bom_ref="r1")
        c2 = Component(name="pkg2", version="2.0", component_type=ComponentType.LIBRARY, purl="pkg:pypi/pkg2@2.0", bom_ref="r2")
        sbom1 = SBOM(components=[c1])
        sbom2 = SBOM(components=[c2])
        result = gen.compare_sboms(sbom1, sbom2)
        assert len(result["added_components"]) == 1
        assert result["added_components"][0]["name"] == "pkg2"
        assert len(result["removed_components"]) == 1
        assert result["removed_components"][0]["name"] == "pkg1"

    def test_compare_sboms_version_changes(self) -> None:
        gen = SBOMGenerator()
        purl = "pkg:pypi/pkg@1.0"
        c1 = Component(name="pkg", version="1.0", component_type=ComponentType.LIBRARY, purl=purl, bom_ref="r1")
        c2 = Component(name="pkg", version="2.0", component_type=ComponentType.LIBRARY, purl=purl, bom_ref="r2")
        sbom1 = SBOM(components=[c1])
        sbom2 = SBOM(components=[c2])
        result = gen.compare_sboms(sbom1, sbom2)
        assert len(result["version_changes"]) == 1
        assert result["version_changes"][0]["old_version"] == "1.0"
        assert result["version_changes"][0]["new_version"] == "2.0"

    def test_compare_sboms_vulnerability_changes(self) -> None:
        gen = SBOMGenerator()
        v1 = Vulnerability(id="CVE-1", source_name="NVD", severity=VulnerabilitySeverity.HIGH)
        v2 = Vulnerability(id="CVE-2", source_name="NVD", severity=VulnerabilitySeverity.LOW)
        sbom1 = SBOM(vulnerabilities=[v1])
        sbom2 = SBOM(vulnerabilities=[v2])
        result = gen.compare_sboms(sbom1, sbom2)
        assert len(result["vulnerability_changes"]) == 2

    def test_generate_from_project_checks_path(self, tmp_path: Path) -> None:
        gen = SBOMGenerator()
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname = \"test\"\n")
        sbom = gen.generate_from_project(tmp_path)
        assert sbom is not None
        assert sbom.serial_number is not None

    def test_generate_sbom_uuid(self) -> None:
        gen = SBOMGenerator()
        c = Component(name="pkg", version="1.0", component_type=ComponentType.LIBRARY, purl="pkg:pypi/pkg@1.0", bom_ref="r1")
        sbom = SBOM(components=[c])
        uuid = gen._generate_sbom_uuid(sbom)
        assert uuid is not None
        assert len(uuid) > 0

    def test_generate_sbom_uuid_deterministic(self) -> None:
        gen = SBOMGenerator()
        c = Component(name="pkg", version="1.0", component_type=ComponentType.LIBRARY, purl="pkg:pypi/pkg@1.0", bom_ref="r1")
        sbom = SBOM(components=[c])
        uuid1 = gen._generate_sbom_uuid(sbom)
        uuid2 = gen._generate_sbom_uuid(sbom)
        assert uuid1 == uuid2

    def test_version_from_setup_py_no_match(self, tmp_path: Path) -> None:
        gen = SBOMGenerator()
        f = tmp_path / "setup.py"
        f.write_text("from setuptools import setup\n")
        assert gen._get_version_from_setup_py(f) is None

    def test_version_from_setup_cfg_no_metadata(self, tmp_path: Path) -> None:
        gen = SBOMGenerator()
        f = tmp_path / "setup.cfg"
        f.write_text("[nosection]\nkey = val\n")
        assert gen._get_version_from_setup_cfg(f) is None

    def test_version_from_init_py_no_match(self, tmp_path: Path) -> None:
        gen = SBOMGenerator()
        f = tmp_path / "__init__.py"
        f.write_text("x = 1\n")
        assert gen._get_version_from_init_py(f) is None

    def test_version_from_version_file_read_error(self) -> None:
        gen = SBOMGenerator()
        assert gen._get_version_from_version_file(Path("/nonexistent/file")) is None

    def test_parse_pyproject_toml_no_tomllib(self, tmp_path: Path) -> None:
        gen = SBOMGenerator()
        assert gen._parse_pyproject_toml(tmp_path) == []

    def test_parse_environment_yml_yaml_import_error(self, tmp_path: Path) -> None:
        gen = SBOMGenerator()
        assert gen._parse_environment_yml(tmp_path) == []

    def test_scan_pip_dependencies_fallback(self, tmp_path: Path) -> None:
        gen = SBOMGenerator()
        (tmp_path / "requirements.txt").write_text("pkg1==1.0.0\n")
        with mock.patch("maref.supply_chain.sbom_generator.subprocess.run", side_effect=subprocess.SubprocessError()):
            components = gen._scan_pip_dependencies(tmp_path)
            assert len(components) == 1
            assert components[0].name == "pkg1"

    def test_scan_pip_dependencies_no_fallback(self, tmp_path: Path) -> None:
        gen = SBOMGenerator()
        with mock.patch("maref.supply_chain.sbom_generator.subprocess.run", side_effect=subprocess.SubprocessError()):
            components = gen._scan_pip_dependencies(tmp_path)
            assert components == []

    def test_scan_poetry_dependencies_fallback(self, tmp_path: Path) -> None:
        gen = SBOMGenerator()
        f = tmp_path / "pyproject.toml"
        f.write_bytes('[tool.poetry.dependencies]\nrequest = "^2.0"\n'.encode())
        with mock.patch("maref.supply_chain.sbom_generator.subprocess.run", side_effect=FileNotFoundError):
            components = gen._scan_poetry_dependencies(tmp_path)
            assert len(components) == 1

    def test_scan_pipenv_dependencies_fallback(self, tmp_path: Path) -> None:
        gen = SBOMGenerator()
        f = tmp_path / "Pipfile"
        f.write_bytes("[packages]\npkg1 = \"*\"\n".encode())
        with mock.patch("maref.supply_chain.sbom_generator.subprocess.run", side_effect=FileNotFoundError):
            components = gen._scan_pipenv_dependencies(tmp_path)
            assert len(components) == 1
