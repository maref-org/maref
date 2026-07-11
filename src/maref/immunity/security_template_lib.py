import ast
import hashlib
import hmac as hmac_lib
import logging
import os
from dataclasses import dataclass, field
from typing import Any
from maref.security.decorators import security_critical
logger = logging.getLogger(__name__)
_HMAC_KEY_ENV = 'MAREF_TEMPLATE_HMAC_KEY'
_EPHEMERAL_KEY: bytes | None = None

def _hmac_key() -> bytes:
    global _EPHEMERAL_KEY
    key = os.environ.get(_HMAC_KEY_ENV)
    if key:
        return key.encode()
    if _EPHEMERAL_KEY is None:
        _EPHEMERAL_KEY = os.urandom(32)
        logger.warning('%s not set — using ephemeral key. HMACs will be invalid across restarts. Set %s for production.', _HMAC_KEY_ENV, _HMAC_KEY_ENV)
    return _EPHEMERAL_KEY

def _compute_hmac(content: str) -> str:
    return hmac_lib.new(_hmac_key(), content.encode('utf-8'), hashlib.sha256).hexdigest()

@dataclass
class SecurityTemplate:
    domain: str
    description: str
    template_code: str
    blocked_keywords: list[str] = field(default_factory=list)
    hmac: str = ''

    def __post_init__(self) -> None:
        if not self.hmac:
            self.hmac = _compute_hmac(self.template_code)

class SecurityTemplateLib:
    DOMAINS = ('password_storage', 'sql_query', 'https_request')

    def __init__(self) -> None:
        self._templates: dict[str, SecurityTemplate] = {}
        self._init_builtins()

    def _init_builtins(self) -> None:
        bcrypt_tmpl = SecurityTemplate(domain='password_storage', description='Password storage: use bcrypt.hashpw + bcrypt.checkpw', template_code='import bcrypt\ndef hash_password(password: str) -> str:\n    salt = bcrypt.gensalt()\n    return bcrypt.hashpw(password.encode(), salt).decode()\ndef verify_password(password: str, hashed: str) -> bool:\n    return bcrypt.checkpw(password.encode(), hashed.encode())\n', blocked_keywords=['hashlib.md5', 'hashlib.sha1', 'crypt.md5', 'md5(password'])
        sql_tmpl = SecurityTemplate(domain='sql_query', description='SQL queries: use parameterized statements', template_code='# Safe: parameterized query\ncursor.execute(\n    "SELECT * FROM users WHERE id = ?",\n    (user_id,)\n)\n', blocked_keywords=['f"', "f'", '.format(', ' % '])
        https_tmpl = SecurityTemplate(domain='https_request', description='HTTPS requests: verify=True required', template_code='import requests\nresponse = requests.get(\n    "https://api.example.com/data",\n    verify=True,\n    timeout=30,\n)\n', blocked_keywords=['verify=False'])
        for t in (bcrypt_tmpl, sql_tmpl, https_tmpl):
            self.register_template(t)

    @security_critical
    def register_template(self, template: SecurityTemplate) -> None:
        template.hmac = _compute_hmac(template.template_code)
        self._templates[template.domain] = template

    def verify_integrity(self) -> bool:
        return all((t.hmac == _compute_hmac(t.template_code) for t in self._templates.values()))

    def get_template(self, domain: str) -> str | None:
        t = self._templates.get(domain)
        return t.template_code if t else None

    def check_code(self, code: str, domain: str) -> list[dict[str, Any]]:
        template = self._templates.get(domain)
        if template is None:
            return [{'domain': domain, 'message': f'Unknown domain: {domain}', 'line': 0, 'suggestion': ''}]
        violations: list[dict[str, Any]] = []
        for kw in template.blocked_keywords:
            if kw in code:
                violations.append({'domain': domain, 'message': f"Blocked pattern '{kw}' detected", 'suggestion': f'Use the security template:\n{template.template_code}', 'line': self._find_line(code, kw)})
        if domain == 'password_storage':
            violations.extend(self._check_password_usage(code, template))
        elif domain == 'sql_query':
            violations.extend(self._check_sql_construction(code, template))
        elif domain == 'https_request':
            violations.extend(self._check_https_verify(code, template))
        return violations

    def check_all(self, code: str) -> list[dict[str, Any]]:
        all_violations: list[dict[str, Any]] = []
        for domain in self.DOMAINS:
            all_violations.extend(self.check_code(code, domain))
        return all_violations

    def _find_line(self, code: str, pattern: str) -> int:
        for (i, line) in enumerate(code.splitlines(), 1):
            if pattern in line:
                return i
        return 0

    def _check_password_usage(self, code: str, template: SecurityTemplate) -> list[dict[str, Any]]:
        violations: list[dict[str, Any]] = []
        code_lower = code.lower()
        if not any((kw in code_lower for kw in ('password', 'passwd', 'hash_password', 'verify_password'))):
            return violations
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return violations
        uses_bcrypt = False
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [n.name for n in node.names]
                if isinstance(node, ast.ImportFrom) and node.module:
                    names.append(node.module)
                if any(('bcrypt' in n for n in names)):
                    uses_bcrypt = True
                    break
            if isinstance(node, ast.Call):
                name = ast.unparse(node.func)
                if any((f in name for f in ('hashpw', 'checkpw', 'gensalt'))):
                    uses_bcrypt = True
                    break
        if not uses_bcrypt:
            violations.append({'domain': 'password_storage', 'message': 'Password handling without bcrypt — must use bcrypt.hashpw', 'suggestion': f'Use the bcrypt template:\n{template.template_code}', 'line': 0})
        return violations

    def _check_sql_construction(self, code: str, template: SecurityTemplate) -> list[dict[str, Any]]:
        violations: list[dict[str, Any]] = []
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return violations
        _SQL_KEYWORDS = ('SELECT ', 'INSERT ', 'UPDATE ', 'DELETE ', 'CREATE ', 'DROP ', 'ALTER ')
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func_name = ast.unparse(node.func)
                if 'execute' not in func_name.lower():
                    continue
                if not node.args:
                    continue
                sql_arg = node.args[0]
                if isinstance(sql_arg, (ast.JoinedStr, ast.BinOp)):
                    violations.append({'domain': 'sql_query', 'message': 'SQL query constructed via f-string or concatenation — use parameterized query', 'suggestion': f'Use parameterized template:\n{template.template_code}', 'line': getattr(sql_arg, 'lineno', 0)})
            if isinstance(node, (ast.BinOp, ast.JoinedStr)):
                snippet = ast.unparse(node)
                is_sql_construction = any((kw in snippet.upper() for kw in _SQL_KEYWORDS))
                if is_sql_construction and isinstance(node, ast.BinOp):
                    violations.append({'domain': 'sql_query', 'message': 'SQL query constructed via string concatenation — use parameterized query', 'suggestion': f'Use parameterized template:\n{template.template_code}', 'line': getattr(node, 'lineno', 0)})
                elif is_sql_construction and isinstance(node, ast.JoinedStr):
                    violations.append({'domain': 'sql_query', 'message': 'SQL query constructed via f-string — use parameterized query', 'suggestion': f'Use parameterized template:\n{template.template_code}', 'line': getattr(node, 'lineno', 0)})
        return violations

    def _check_https_verify(self, code: str, template: SecurityTemplate) -> list[dict[str, Any]]:
        violations: list[dict[str, Any]] = []
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return violations
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func_name = ast.unparse(node.func)
            if 'requests.' not in func_name:
                continue
            if not node.args:
                continue
            first_arg = node.args[0]
            if not (isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str)):
                continue
            if not first_arg.value.startswith('https://'):
                continue
            has_verify = False
            verify_false = False
            for kw in node.keywords:
                if kw.arg == 'verify':
                    has_verify = True
                    val = kw.value
                    if isinstance(val, ast.Constant) and val.value is False or (isinstance(val, ast.Name) and val.id == 'False'):
                        verify_false = True
            if verify_false:
                violations.append({'domain': 'https_request', 'message': 'HTTPS request with verify=False — security risk', 'suggestion': f'Use verify=True:\n{template.template_code}', 'line': getattr(node, 'lineno', 0)})
            elif not has_verify:
                violations.append({'domain': 'https_request', 'message': 'HTTPS request without explicit verify=True', 'suggestion': f'Add verify=True:\n{template.template_code}', 'line': getattr(node, 'lineno', 0)})
        return violations