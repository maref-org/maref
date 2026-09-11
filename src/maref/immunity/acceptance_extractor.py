import hashlib
import json
import re
import time
import uuid
from dataclasses import dataclass

AC_CATEGORIES = frozenset({"happy_path", "error", "boundary"})


@dataclass
class AcceptanceCriterion:
    criterion_id: str
    description: str
    category: str
    test_template: str


@dataclass
class IntentHash:
    hash_value: str
    criteria_count: int
    generated_at: float


TEST_TEMPLATES: dict[str, str] = {
    "happy_path": 'def test_{safe_desc}():\n    result = implement({args})\n    assert result is not None\n    assert result["status"] == "success"\n',
    "error": "def test_{safe_desc}():\n    with pytest.raises({exception}):\n        implement({args})\n",
    "boundary": 'def test_{safe_desc}():\n    result = implement({args})\n    assert result is not None\n    assert result["status"] == "success"\n',
}


def _make_test_template(
    description: str, category: str, exception: str = "ValueError", args: str = ""
) -> str:
    safe = re.sub("[^a-zA-Z0-9_]", "_", description.lower())[:40].strip("_")
    if not safe:
        safe = "test_case"
    template = TEST_TEMPLATES.get(category, TEST_TEMPLATES["happy_path"])
    return template.format(safe_desc=safe, exception=exception, args=args)


class AcceptanceExtractor:
    def __init__(self) -> None:
        pass

    def extract_ac(self, description: str) -> list[AcceptanceCriterion]:
        desc_lower = description.lower()
        criteria: list[AcceptanceCriterion] = []
        if any(kw in desc_lower for kw in ("登录", "login", "sign in", "signin")):
            criteria.extend(self._login_criteria(description))
        elif any(kw in desc_lower for kw in ("注册", "register", "sign up", "signup")):
            criteria.extend(self._register_criteria(description))
        elif any(kw in desc_lower for kw in ("搜索", "search", "查询", "query")):
            criteria.extend(self._search_criteria(description))
        elif any(kw in desc_lower for kw in ("上传", "upload", "导入", "import")):
            criteria.extend(self._upload_criteria(description))
        else:
            criteria.extend(self._generic_criteria(description))
        seen: set[str] = set()
        unique: list[AcceptanceCriterion] = []
        for c in criteria:
            if c.description not in seen:
                seen.add(c.description)
                unique.append(c)
        return unique

    def compute_intent_hash(self, criteria: list[AcceptanceCriterion]) -> IntentHash:
        data = [
            {"description": c.description, "category": c.category, "template": c.test_template}
            for c in sorted(criteria, key=lambda x: x.description)
        ]
        raw = json.dumps(data, sort_keys=True, ensure_ascii=False)
        hash_value = hashlib.sha256(raw.encode()).hexdigest()
        return IntentHash(
            hash_value=hash_value, criteria_count=len(criteria), generated_at=time.time()
        )

    def _login_criteria(self, description: str) -> list[AcceptanceCriterion]:
        return [
            AcceptanceCriterion(
                criterion_id=str(uuid.uuid4()),
                description="有效用户名和密码可成功登录",
                category="happy_path",
                test_template=_make_test_template(
                    "有效用户名和密码可成功登录",
                    "happy_path",
                    args='username="admin", password="correct_password"',
                ),
            ),
            AcceptanceCriterion(
                criterion_id=str(uuid.uuid4()),
                description="无效密码应返回错误提示",
                category="error",
                test_template=_make_test_template(
                    "无效密码应返回错误提示",
                    "error",
                    exception="AuthenticationError",
                    args='username="admin", password="wrong_password"',
                ),
            ),
            AcceptanceCriterion(
                criterion_id=str(uuid.uuid4()),
                description="连续5次失败后应锁定账户",
                category="boundary",
                test_template=_make_test_template(
                    "连续5次失败后应锁定账户",
                    "boundary",
                    args='username="admin", password="wrong_password", attempts=5',
                ),
            ),
            AcceptanceCriterion(
                criterion_id=str(uuid.uuid4()),
                description="空用户名或密码应拒绝请求",
                category="error",
                test_template=_make_test_template(
                    "空用户名或密码应拒绝请求",
                    "error",
                    exception="ValidationError",
                    args='username="", password=""',
                ),
            ),
        ]

    def _register_criteria(self, description: str) -> list[AcceptanceCriterion]:
        return [
            AcceptanceCriterion(
                criterion_id=str(uuid.uuid4()),
                description="新用户可以成功注册",
                category="happy_path",
                test_template=_make_test_template(
                    "新用户可以成功注册",
                    "happy_path",
                    args='username="newuser", password="P@ssw0rd", email="a@b.com"',
                ),
            ),
            AcceptanceCriterion(
                criterion_id=str(uuid.uuid4()),
                description="重复用户名应返回注册失败",
                category="error",
                test_template=_make_test_template(
                    "重复用户名应返回注册失败",
                    "error",
                    exception="UserExistsError",
                    args='username="existing", password="P@ssw0rd"',
                ),
            ),
            AcceptanceCriterion(
                criterion_id=str(uuid.uuid4()),
                description="密码长度小于8位应拒绝",
                category="boundary",
                test_template=_make_test_template(
                    "密码长度小于8位应拒绝", "boundary", args='username="newuser", password="Ab1"'
                ),
            ),
            AcceptanceCriterion(
                criterion_id=str(uuid.uuid4()),
                description="无效邮箱格式应返回验证错误",
                category="error",
                test_template=_make_test_template(
                    "无效邮箱格式应返回验证错误",
                    "error",
                    exception="ValidationError",
                    args='username="newuser", password="P@ssw0rd", email="invalid"',
                ),
            ),
        ]

    def _search_criteria(self, description: str) -> list[AcceptanceCriterion]:
        return [
            AcceptanceCriterion(
                criterion_id=str(uuid.uuid4()),
                description="关键字搜索返回匹配结果",
                category="happy_path",
                test_template=_make_test_template(
                    "关键字搜索应返回匹配结果", "happy_path", args='query="keyword"'
                ),
            ),
            AcceptanceCriterion(
                criterion_id=str(uuid.uuid4()),
                description="空关键字应返回空结果",
                category="boundary",
                test_template=_make_test_template(
                    "空关键字应返回空结果", "boundary", args='query=""'
                ),
            ),
            AcceptanceCriterion(
                criterion_id=str(uuid.uuid4()),
                description="超长关键字应截断或返回错误",
                category="boundary",
                test_template=_make_test_template(
                    "超长关键字应截断或返回错误", "boundary", args='query="x" * 1000'
                ),
            ),
            AcceptanceCriterion(
                criterion_id=str(uuid.uuid4()),
                description="SQL注入关键字应被转义",
                category="error",
                test_template=_make_test_template(
                    "SQL注入关键字应被转义",
                    "error",
                    exception="SecurityError",
                    args='query="\' OR 1=1 --"',
                ),
            ),
        ]

    def _upload_criteria(self, description: str) -> list[AcceptanceCriterion]:
        return [
            AcceptanceCriterion(
                criterion_id=str(uuid.uuid4()),
                description="有效文件可以上传成功",
                category="happy_path",
                test_template=_make_test_template(
                    "有效文件可以上传成功", "happy_path", args="file=valid_file()"
                ),
            ),
            AcceptanceCriterion(
                criterion_id=str(uuid.uuid4()),
                description="超过大小限制的文件应被拒绝",
                category="boundary",
                test_template=_make_test_template(
                    "超过大小限制的文件应被拒绝", "boundary", args="file=oversized_file()"
                ),
            ),
            AcceptanceCriterion(
                criterion_id=str(uuid.uuid4()),
                description="不支持的文件格式应被拒绝",
                category="error",
                test_template=_make_test_template(
                    "不支持的文件格式应被拒绝",
                    "error",
                    exception="ValidationError",
                    args="file=invalid_format_file()",
                ),
            ),
            AcceptanceCriterion(
                criterion_id=str(uuid.uuid4()),
                description="空文件应被拒绝",
                category="boundary",
                test_template=_make_test_template(
                    "空文件应被拒绝", "boundary", args="file=empty_file()"
                ),
            ),
        ]

    def _generic_criteria(self, description: str) -> list[AcceptanceCriterion]:
        return [
            AcceptanceCriterion(
                criterion_id=str(uuid.uuid4()),
                description=f"正常输入下{description}应成功执行",
                category="happy_path",
                test_template=_make_test_template(
                    f"正常输入下{description}应成功执行", "happy_path"
                ),
            ),
            AcceptanceCriterion(
                criterion_id=str(uuid.uuid4()),
                description="无效输入应返回错误提示",
                category="error",
                test_template=_make_test_template("无效输入应返回错误提示", "error"),
            ),
            AcceptanceCriterion(
                criterion_id=str(uuid.uuid4()),
                description="边界条件: 空输入应被正确处理",
                category="boundary",
                test_template=_make_test_template("边界条件空输入应被正确处理", "boundary"),
            ),
        ]
