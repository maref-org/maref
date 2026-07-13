"""
SBOM生成器

支持CycloneDX v1.4标准，自动生成软件物料清单。
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from maref.governance.audit import AuditLogger


class ComponentType(Enum):
    """组件类型 (CycloneDX标准)"""

    APPLICATION = "application"
    FRAMEWORK = "framework"
    LIBRARY = "library"
    CONTAINER = "container"
    OPERATING_SYSTEM = "operating-system"
    DEVICE = "device"
    FILE = "file"
    PLATFORM = "platform"


class VulnerabilitySeverity(Enum):
    """漏洞严重性等级"""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"
    UNKNOWN = "UNKNOWN"


class LicenseType(Enum):
    """许可证类型"""

    APACHE_2_0 = "Apache-2.0"
    MIT = "MIT"
    GPL_2_0 = "GPL-2.0"
    GPL_3_0 = "GPL-3.0"
    LGPL_2_1 = "LGPL-2.1"
    BSD_2_CLAUSE = "BSD-2-Clause"
    BSD_3_CLAUSE = "BSD-3-Clause"
    ISC = "ISC"
    UNLICENSED = "UNLICENSED"
    PROPRIETARY = "PROPRIETARY"
    OTHER = "OTHER"


@dataclass
class Component:
    """SBOM组件"""

    name: str
    version: str
    component_type: ComponentType
    purl: str  # Package URL
    bom_ref: str  # BOM引用ID

    # 可选字段
    description: str | None = None
    author: str | None = None
    publisher: str | None = None
    licenses: list[LicenseType] = field(default_factory=list)
    copyright: str | None = None
    cpe: str | None = None  # CPE标识符
    swid: str | None = None  # 软件标识标签
    hashes: dict[str, str] = field(default_factory=dict)  # 哈希值: algorithm -> hash
    external_references: list[dict[str, str]] = field(default_factory=list)
    properties: list[dict[str, str]] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)  # bom_ref列表


@dataclass
class Vulnerability:
    """漏洞信息"""

    id: str  # CVE-ID或漏洞ID
    source_name: str  # 来源: CVE, OSS, Snyk等
    description: str | None = None
    severity: VulnerabilitySeverity = VulnerabilitySeverity.UNKNOWN
    cvss_score: float | None = None
    cvss_vector: str | None = None
    cwe_ids: list[str] = field(default_factory=list)
    affected_versions: list[str] = field(default_factory=list)
    fixed_versions: list[str] = field(default_factory=list)
    references: list[dict[str, str]] = field(default_factory=list)
    published_date: str | None = None
    last_updated_date: str | None = None


@dataclass
class SBOM:
    """软件物料清单"""

    bom_format: str = "CycloneDX"
    spec_version: str = "1.4"
    version: int = 1
    serial_number: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    components: list[Component] = field(default_factory=list)
    vulnerabilities: list[Vulnerability] = field(default_factory=list)
    dependencies: list[dict[str, Any]] = field(default_factory=list)
    compositions: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式 (CycloneDX JSON)"""

        # 构建metadata
        metadata = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "tools": [{"vendor": "MAREF", "name": "SBOM Generator", "version": "0.25.0"}],
        }

        # 如果有自定义metadata，合并
        if self.metadata:
            metadata.update(self.metadata)

        # 构建组件列表
        components_list = []
        for component in self.components:
            component_dict: dict[str, Any] = {
                "bom-ref": component.bom_ref,
                "type": component.component_type.value,
                "name": component.name,
                "version": component.version,
                "purl": component.purl,
            }

            # 可选字段
            if component.description:
                component_dict["description"] = component.description
            if component.author:
                component_dict["author"] = component.author
            if component.publisher:
                component_dict["publisher"] = component.publisher

            if component.licenses:
                component_dict["licenses"] = [
                    {"license": {"id": lic.value}} for lic in component.licenses
                ]

            if component.copyright:
                component_dict["copyright"] = component.copyright

            if component.cpe:
                component_dict["cpe"] = component.cpe

            if component.swid:
                component_dict["swid"] = component.swid

            if component.hashes:
                component_dict["hashes"] = [
                    {"alg": algorithm, "content": hash_value}
                    for algorithm, hash_value in component.hashes.items()
                ]

            if component.external_references:
                component_dict["externalReferences"] = component.external_references

            if component.properties:
                component_dict["properties"] = component.properties

            components_list.append(component_dict)

        # 构建漏洞列表
        vulnerabilities_list = []
        for vuln in self.vulnerabilities:
            vuln_dict: dict[str, Any] = {
                "id": vuln.id,
                "source": {"name": vuln.source_name},
                "ratings": [],
            }

            if vuln.description:
                vuln_dict["description"] = vuln.description

            # 评分
            rating: dict[str, Any] = {
                "source": {"name": vuln.source_name},
                "severity": vuln.severity.value.lower(),
            }

            if vuln.cvss_score is not None:
                rating["score"] = vuln.cvss_score

            if vuln.cvss_vector:
                rating["vector"] = vuln.cvss_vector

            vuln_dict["ratings"].append(rating)

            if vuln.cwe_ids:
                vuln_dict["cwes"] = vuln.cwe_ids

            if vuln.affected_versions:
                vuln_dict["affects"] = [
                    {
                        "ref": f"pkg:{component.purl.split('/')[-1]}/{component.name}@{component.version}",
                        "versions": [{"range": ver} for ver in vuln.affected_versions],
                    }
                    for component in self.components
                    if component.external_references
                    and any(vuln.id in ref.get("id", "") for ref in component.external_references)
                ]

            if vuln.references:
                vuln_dict["references"] = vuln.references

            if vuln.published_date:
                vuln_dict["published"] = vuln.published_date

            if vuln.last_updated_date:
                vuln_dict["updated"] = vuln.last_updated_date

            vulnerabilities_list.append(vuln_dict)

        # 构建依赖关系
        dependencies_list = []
        for dep_dict in self.dependencies:
            dependencies_list.append(dep_dict)

        # 如果没有依赖关系但组件有依赖项，自动生成
        if not dependencies_list:
            for component in self.components:
                if component.dependencies:
                    dependencies_list.append(
                        {"ref": component.bom_ref, "dependsOn": component.dependencies}
                    )

        # 构建最终SBOM字典
        sbom_dict = {
            "bomFormat": self.bom_format,
            "specVersion": self.spec_version,
            "version": self.version,
            "serialNumber": self.serial_number
            or f"urn:uuid:{hashlib.md5(str(datetime.datetime.now(datetime.timezone.utc)).encode(), usedforsecurity=False).hexdigest()}",
            "metadata": metadata,
            "components": components_list,
        }

        if vulnerabilities_list:
            sbom_dict["vulnerabilities"] = vulnerabilities_list

        if dependencies_list:
            sbom_dict["dependencies"] = dependencies_list

        if self.compositions:
            sbom_dict["compositions"] = self.compositions

        return sbom_dict

    def to_json(self, indent: int = 2) -> str:
        """转换为JSON字符串"""
        return json.dumps(self.to_dict(), indent=indent)

    def save_to_file(self, filepath: str) -> None:
        """保存到文件"""
        with open(filepath, "w") as f:
            f.write(self.to_json())

    @classmethod
    def load_from_file(cls, filepath: str) -> SBOM:
        """从文件加载"""
        with open(filepath) as f:
            data = json.load(f)

        # 创建SBOM对象
        sbom = cls(
            bom_format=data.get("bomFormat", "CycloneDX"),
            spec_version=data.get("specVersion", "1.4"),
            version=data.get("version", 1),
            serial_number=data.get("serialNumber"),
            metadata=data.get("metadata", {}),
        )

        # 解析组件
        for comp_data in data.get("components", []):
            component = Component(
                name=comp_data["name"],
                version=comp_data.get("version", ""),
                component_type=ComponentType(comp_data["type"]),
                purl=comp_data.get("purl", ""),
                bom_ref=comp_data.get("bom-ref", ""),
                description=comp_data.get("description"),
                author=comp_data.get("author"),
                publisher=comp_data.get("publisher"),
                copyright=comp_data.get("copyright"),
                cpe=comp_data.get("cpe"),
                swid=comp_data.get("swid"),
                hashes={
                    hash_data["alg"]: hash_data["content"]
                    for hash_data in comp_data.get("hashes", [])
                },
                external_references=comp_data.get("externalReferences", []),
                properties=comp_data.get("properties", []),
                dependencies=[
                    dep.split("/")[-1] if "/" in dep else dep
                    for dep in comp_data.get("dependsOn", [])
                ],
            )

            # 解析许可证
            licenses = []
            for license_data in comp_data.get("licenses", []):
                if "license" in license_data:
                    license_id = license_data["license"].get("id")
                    if license_id:
                        try:
                            licenses.append(LicenseType(license_id))
                        except ValueError:
                            licenses.append(LicenseType.OTHER)

            component.licenses = licenses
            sbom.components.append(component)

        # 解析漏洞
        for vuln_data in data.get("vulnerabilities", []):
            cvss_score = None
            cvss_vector = None

            # 提取CVSS信息
            for rating in vuln_data.get("ratings", []):
                if "score" in rating:
                    cvss_score = rating["score"]
                if "vector" in rating:
                    cvss_vector = rating["vector"]

            vulnerability = Vulnerability(
                id=vuln_data["id"],
                source_name=vuln_data.get("source", {}).get("name", "unknown"),
                description=vuln_data.get("description"),
                severity=VulnerabilitySeverity(
                    vuln_data.get("ratings", [{}])[0].get("severity", "UNKNOWN").upper()
                ),
                cvss_score=cvss_score,
                cvss_vector=cvss_vector,
                cwe_ids=vuln_data.get("cwes", []),
                references=vuln_data.get("references", []),
                published_date=vuln_data.get("published"),
                last_updated_date=vuln_data.get("updated"),
            )

            sbom.vulnerabilities.append(vulnerability)

        sbom.dependencies = data.get("dependencies", [])
        sbom.compositions = data.get("compositions", [])

        return sbom


class SBOMGenerator:
    """
    SBOM生成器

    支持自动扫描Python项目依赖并生成CycloneDX v1.4格式的SBOM。
    """

    def __init__(self, audit_logger: AuditLogger | None = None):
        self.audit_logger = audit_logger or AuditLogger()
        self.supported_package_managers = ["pip", "poetry", "pipenv", "conda"]

    def generate_from_project(self, project_path: str | Path) -> SBOM:
        """
        从项目路径生成SBOM

        自动检测项目类型，扫描依赖并生成SBOM。
        """
        resolved_path = Path(project_path).resolve()

        if not resolved_path.exists():
            raise FileNotFoundError(f"Project path not found: {resolved_path}")

        # 检测项目类型
        project_type = self._detect_project_type(resolved_path)

        # 扫描依赖
        components = self._scan_dependencies(resolved_path, project_type)

        # 创建SBOM
        sbom = SBOM(
            metadata={
                "component": {
                    "bom-ref": f"project-{resolved_path.name}",
                    "type": "application",
                    "name": resolved_path.name,
                    "version": self._get_project_version(resolved_path),
                    "purl": f"pkg:pypi/{resolved_path.name}",
                }
            }
        )

        sbom.components = components

        # 设置序列号
        sbom.serial_number = f"urn:uuid:{self._generate_sbom_uuid(sbom)}"

        # 审计日志
        self.audit_logger.log(
            event_type="sbom_generated",
            actor="SBOMGenerator",
            action="generate_from_project",
            details=f"Generated SBOM for project: {project_path}",
            metadata={
                "project_path": str(project_path),
                "project_type": project_type,
                "num_components": len(components),
                "sbom_serial": sbom.serial_number,
            },
        )

        return sbom

    def _detect_project_type(self, project_path: Path) -> str:
        """检测项目类型"""
        # 检查常见的配置文件
        if (project_path / "pyproject.toml").exists():
            with open(project_path / "pyproject.toml") as f:
                content = f.read()
                if "[tool.poetry]" in content:
                    return "poetry"
                elif "[tool.pipenv]" in content:
                    return "pipenv"
                else:
                    return "poetry"  # 默认假设是poetry

        if (project_path / "Pipfile").exists():
            return "pipenv"

        if (project_path / "environment.yml").exists() or (
            project_path / "environment.yaml"
        ).exists():
            return "conda"

        if (project_path / "requirements.txt").exists():
            return "pip"

        # 默认
        return "pip"

    def _scan_dependencies(self, project_path: Path, project_type: str) -> list[Component]:
        """扫描依赖"""
        components = []

        if project_type == "poetry":
            components = self._scan_poetry_dependencies(project_path)
        elif project_type == "pipenv":
            components = self._scan_pipenv_dependencies(project_path)
        elif project_type == "conda":
            components = self._scan_conda_dependencies(project_path)
        else:  # pip
            components = self._scan_pip_dependencies(project_path)

        return components

    def _scan_poetry_dependencies(self, project_path: Path) -> list[Component]:
        """扫描Poetry依赖"""
        try:
            # 尝试使用poetry命令
            result = subprocess.run(
                ["poetry", "show", "--tree", "--no-ansi"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                return self._parse_poetry_output(result.stdout)
        except (subprocess.SubprocessError, FileNotFoundError):
            pass

        # 回退到解析pyproject.toml
        return self._parse_pyproject_toml(project_path)

    def _scan_pipenv_dependencies(self, project_path: Path) -> list[Component]:
        """扫描Pipenv依赖"""
        try:
            result = subprocess.run(
                ["pipenv", "graph", "--json"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                return self._parse_pipenv_graph_output(result.stdout)
        except (subprocess.SubprocessError, FileNotFoundError):
            pass

        # 回退到解析Pipfile
        return self._parse_pipfile(project_path)

    def _scan_conda_dependencies(self, project_path: Path) -> list[Component]:
        """扫描Conda依赖"""
        try:
            result = subprocess.run(
                ["conda", "list", "--json"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                return self._parse_conda_list_output(result.stdout)
        except (subprocess.SubprocessError, FileNotFoundError):
            pass

        # 回退到解析environment.yml
        return self._parse_environment_yml(project_path)

    def _scan_pip_dependencies(self, project_path: Path) -> list[Component]:
        """扫描Pip依赖"""
        try:
            # 使用pip freeze
            result = subprocess.run(
                [sys.executable, "-m", "pip", "freeze"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                components = self._parse_pip_freeze_output(result.stdout)

                # 如果没有依赖，尝试解析requirements.txt
                if not components and (project_path / "requirements.txt").exists():
                    with open(project_path / "requirements.txt") as f:
                        lines = f.readlines()
                    return self._parse_requirements_txt(lines)

                return components

        except subprocess.SubprocessError:
            pass

        # 回退到解析requirements.txt
        if (project_path / "requirements.txt").exists():
            with open(project_path / "requirements.txt") as f:
                lines = f.readlines()
            return self._parse_requirements_txt(lines)

        return []

    def _parse_poetry_output(self, output: str) -> list[Component]:
        """解析poetry show输出"""
        components = []
        seen_packages = set()

        for line in output.split("\n"):
            line = line.strip()
            if not line or line.startswith("Warning:"):
                continue

            # Poetry输出格式: package version description
            match = re.match(r"^([a-zA-Z0-9_.-]+)\s+([^\s]+)(?:\s+(.*))?$", line)
            if match:
                name = match.group(1)
                version = match.group(2)

                if name in seen_packages:
                    continue

                seen_packages.add(name)

                component = Component(
                    name=name,
                    version=version,
                    component_type=ComponentType.LIBRARY,
                    purl=f"pkg:pypi/{name}@{version}",
                    bom_ref=f"pkg:pypi/{name}@{version}",
                    description=match.group(3) if match.group(3) else None,
                )

                components.append(component)

        return components

    def _parse_pyproject_toml(self, project_path: Path) -> list[Component]:
        """解析pyproject.toml"""
        components = []

        try:
            try:
                import tomllib  # type: ignore[import-not-found]
            except ImportError:
                import tomli as tomllib  # tomli fallback for Python<3.11
            with open(project_path / "pyproject.toml", "rb") as f:
                data = tomllib.load(f)

            # 获取依赖
            dependencies = {}
            tool_data = data.get("tool", {})

            if "poetry" in tool_data:
                dependencies.update(tool_data["poetry"].get("dependencies", {}))

            # 解析依赖
            for name, spec in dependencies.items():
                if name == "python":
                    continue

                version = "*"
                if isinstance(spec, dict):
                    version = spec.get("version", "*")
                elif isinstance(spec, str):
                    version = spec

                component = Component(
                    name=name,
                    version=version,
                    component_type=ComponentType.LIBRARY,
                    purl=f"pkg:pypi/{name}@{version}",
                    bom_ref=f"pkg:pypi/{name}@{version}",
                )

                components.append(component)

        except (ImportError, FileNotFoundError, KeyError):
            pass

        return components

    def _parse_pipenv_graph_output(self, output: str) -> list[Component]:
        """解析pipenv graph输出"""
        try:
            data = json.loads(output)
            components = []

            for item in data:
                name = item.get("package_name")
                version = item.get("installed_version")
                dependencies = item.get("dependencies", [])

                if name and version:
                    component = Component(
                        name=name,
                        version=version,
                        component_type=ComponentType.LIBRARY,
                        purl=f"pkg:pypi/{name}@{version}",
                        bom_ref=f"pkg:pypi/{name}@{version}",
                        dependencies=[dep["package_name"] for dep in dependencies],
                    )

                    components.append(component)

            return components

        except json.JSONDecodeError:
            return []

    def _parse_pipfile(self, project_path: Path) -> list[Component]:
        """解析Pipfile"""
        components = []

        try:
            try:
                import tomllib
            except ImportError:
                import tomli as tomllib
            with open(project_path / "Pipfile", "rb") as f:
                data = tomllib.load(f)

            # 获取依赖
            packages = data.get("packages", {})

            for name, spec in packages.items():
                version = "*"
                if isinstance(spec, dict):
                    version = spec.get("version", "*")
                elif isinstance(spec, str):
                    version = spec

                component = Component(
                    name=name,
                    version=version,
                    component_type=ComponentType.LIBRARY,
                    purl=f"pkg:pypi/{name}@{version}",
                    bom_ref=f"pkg:pypi/{name}@{version}",
                )

                components.append(component)

        except (ImportError, FileNotFoundError, KeyError):
            pass

        return components

    def _parse_conda_list_output(self, output: str) -> list[Component]:
        """解析conda list输出"""
        try:
            data = json.loads(output)
            components = []

            for item in data:
                name = item.get("name")
                version = item.get("version")
                channel = (
                    item.get("channel", "").split("/")[-1] if "channel" in item else "conda-forge"
                )

                if name and version:
                    component = Component(
                        name=name,
                        version=version,
                        component_type=ComponentType.LIBRARY,
                        purl=f"pkg:conda/{channel}/{name}@{version}",
                        bom_ref=f"pkg:conda/{channel}/{name}@{version}",
                    )

                    components.append(component)

            return components

        except json.JSONDecodeError:
            return []

    def _parse_environment_yml(self, project_path: Path) -> list[Component]:
        """解析environment.yml"""
        components = []

        env_files = ["environment.yml", "environment.yaml"]
        env_file = None

        for file in env_files:
            if (project_path / file).exists():
                env_file = project_path / file
                break

        if not env_file:
            return components

        try:
            import yaml

            with open(env_file) as f:
                data = yaml.safe_load(f)

            dependencies = data.get("dependencies", [])

            for dep in dependencies:
                if isinstance(dep, str):
                    # 格式: package=version
                    if "=" in dep:
                        name, version = dep.split("=", 1)
                    else:
                        name, version = dep, "*"

                    component = Component(
                        name=name.strip(),
                        version=version.strip(),
                        component_type=ComponentType.LIBRARY,
                        purl=f"pkg:conda/{name.strip()}@{version.strip()}",
                        bom_ref=f"pkg:conda/{name.strip()}@{version.strip()}",
                    )

                    components.append(component)

        except (ImportError, FileNotFoundError, KeyError, yaml.YAMLError):
            pass

        return components

    def _parse_pip_freeze_output(self, output: str) -> list[Component]:
        """解析pip freeze输出"""
        components = []

        for line in output.split("\n"):
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-e") or line.startswith("git+"):
                continue

            # 格式: package==version
            if "==" in line:
                name, version = line.split("==", 1)
            elif "@" in line:
                # 格式: package@url
                continue
            else:
                continue

            # 清理版本号
            version = version.split(";")[0].strip()

            component = Component(
                name=name.strip(),
                version=version,
                component_type=ComponentType.LIBRARY,
                purl=f"pkg:pypi/{name.strip()}@{version}",
                bom_ref=f"pkg:pypi/{name.strip()}@{version}",
            )

            components.append(component)

        return components

    def _parse_requirements_txt(self, lines: list[str]) -> list[Component]:
        """解析requirements.txt"""
        components = []

        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-e") or line.startswith("git+"):
                continue

            # 格式: package==version
            # 也可能有: package>=version, package~=version等
            if "==" in line:
                parts = line.split("==")
                name = parts[0].strip()
                version = parts[1].split(";")[0].strip() if len(parts) > 1 else "*"
            elif ">=" in line:
                parts = line.split(">=")
                name = parts[0].strip()
                version = parts[1].split(";")[0].strip() + "+" if len(parts) > 1 else "*"
            elif "<=" in line:
                parts = line.split("<=")
                name = parts[0].strip()
                version = parts[1].split(";")[0].strip() + "-" if len(parts) > 1 else "*"
            elif "~=" in line:
                parts = line.split("~=")
                name = parts[0].strip()
                version = parts[1].split(";")[0].strip() + "~" if len(parts) > 1 else "*"
            elif "@" in line:
                # 格式: package@url
                continue
            else:
                name = line.split(";")[0].strip()
                version = "*"

            component = Component(
                name=name,
                version=version,
                component_type=ComponentType.LIBRARY,
                purl=f"pkg:pypi/{name}@{version}",
                bom_ref=f"pkg:pypi/{name}@{version}",
            )

            components.append(component)

        return components

    def _get_project_version(self, project_path: Path) -> str:
        """获取项目版本"""
        version_files = [
            ("pyproject.toml", self._get_version_from_pyproject),
            ("setup.py", self._get_version_from_setup_py),
            ("setup.cfg", self._get_version_from_setup_cfg),
            ("__init__.py", self._get_version_from_init_py),
            ("VERSION", self._get_version_from_version_file),
            ("version.txt", self._get_version_from_version_file),
        ]

        for filename, extractor in version_files:
            filepath = project_path / filename
            if filepath.exists():
                try:
                    version = extractor(filepath)
                    if version:
                        return version
                except Exception:
                    continue

        return "0.0.0"

    def _get_version_from_pyproject(self, filepath: Path) -> str | None:
        """从pyproject.toml获取版本"""
        try:
            try:
                import tomllib as tomli
            except ImportError:
                import tomli
            with open(filepath, "rb") as f:
                data = tomli.load(f)

            if "project" in data and "version" in data["project"]:
                return data["project"]["version"]

            tool_data = data.get("tool", {})
            if "poetry" in tool_data and "version" in tool_data["poetry"]:
                return tool_data["poetry"]["version"]

        except (ImportError, KeyError):
            pass

        return None

    def _get_version_from_setup_py(self, filepath: Path) -> str | None:
        """从setup.py获取版本"""
        try:
            with open(filepath) as f:
                content = f.read()

            # 简单正则匹配 version=
            match = re.search(r'version\s*=\s*[\'"]([^\'"]+)[\'"]', content)
            if match:
                return match.group(1)

        except Exception:
            pass

        return None

    def _get_version_from_setup_cfg(self, filepath: Path) -> str | None:
        """从setup.cfg获取版本"""
        try:
            with open(filepath) as f:
                content = f.read()

            # 匹配 [metadata] 下的 version
            lines = content.split("\n")
            in_metadata = False
            for line in lines:
                line = line.strip()
                if line.startswith("["):
                    in_metadata = line == "[metadata]"
                elif in_metadata and line.startswith("version"):
                    parts = line.split("=", 1)
                    if len(parts) > 1:
                        return parts[1].strip()

        except Exception:
            pass

        return None

    def _get_version_from_init_py(self, filepath: Path) -> str | None:
        """从__init__.py获取版本"""
        try:
            with open(filepath) as f:
                content = f.read()

            # 匹配 __version__
            match = re.search(r'__version__\s*=\s*[\'"]([^\'"]+)[\'"]', content)
            if match:
                return match.group(1)

        except Exception:
            pass

        return None

    def _get_version_from_version_file(self, filepath: Path) -> str | None:
        """从版本文件获取版本"""
        try:
            with open(filepath) as f:
                return f.read().strip()
        except Exception:
            return None

    def _generate_sbom_uuid(self, sbom: SBOM) -> str:
        """生成SBOM UUID"""
        import uuid

        # 根据组件信息生成确定性UUID
        components_str = ""
        for component in sorted(sbom.components, key=lambda c: c.name):
            components_str += f"{component.name}:{component.version}:{component.purl}"

        return str(uuid.uuid5(uuid.NAMESPACE_DNS, components_str))

    def compare_sboms(self, sbom1: SBOM, sbom2: SBOM) -> dict[str, Any]:
        """比较两个SBOM"""
        result = {
            "added_components": [],
            "removed_components": [],
            "version_changes": [],
            "vulnerability_changes": [],
        }

        # 创建组件映射
        sbom1_components = {comp.purl: comp for comp in sbom1.components}
        sbom2_components = {comp.purl: comp for comp in sbom2.components}

        # 找出新增的组件
        for purl, component in sbom2_components.items():
            if purl not in sbom1_components:
                result["added_components"].append(
                    {"purl": purl, "name": component.name, "version": component.version}
                )

        # 找出删除的组件
        for purl, component in sbom1_components.items():
            if purl not in sbom2_components:
                result["removed_components"].append(
                    {"purl": purl, "name": component.name, "version": component.version}
                )

        # 找出版本变更
        for purl, comp1 in sbom1_components.items():
            if purl in sbom2_components:
                comp2 = sbom2_components[purl]
                if comp1.version != comp2.version:
                    result["version_changes"].append(
                        {
                            "purl": purl,
                            "name": comp1.name,
                            "old_version": comp1.version,
                            "new_version": comp2.version,
                        }
                    )

        # 比较漏洞
        sbom1_vulns = {vuln.id: vuln for vuln in sbom1.vulnerabilities}
        sbom2_vulns = {vuln.id: vuln for vuln in sbom2.vulnerabilities}

        # 新增漏洞
        for vuln_id, vuln in sbom2_vulns.items():
            if vuln_id not in sbom1_vulns:
                result["vulnerability_changes"].append(
                    {"type": "added", "id": vuln_id, "severity": vuln.severity.value}
                )

        # 修复的漏洞
        for vuln_id, vuln in sbom1_vulns.items():
            if vuln_id not in sbom2_vulns:
                result["vulnerability_changes"].append(
                    {"type": "removed", "id": vuln_id, "severity": vuln.severity.value}
                )

        return result
