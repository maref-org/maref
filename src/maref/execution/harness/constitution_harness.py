"""ConstitutionHarness — constitutional compliance verification for evolution changes."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SeverityLevel(Enum):
    PASS = "pass"
    WARN = "warn"       # Logged but does NOT block evolution
    BLOCK = "block"     # Blocks the evolution change


@dataclass
class ConstitutionCheckResult:
    rule_id: str
    description: str
    severity: SeverityLevel
    detail: str = ""
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def is_blocking(self) -> bool:
        return self.severity == SeverityLevel.BLOCK


@dataclass
class SyncCheckResult:
    valid: bool
    direction: str  # "A->B" or "unknown"
    detail: str = ""


@dataclass
class ExfiltrationCheckResult:
    clean: bool
    flagged_items: list[str] = field(default_factory=list)
    detail: str = ""


class ConstitutionHarness:
    """Constitutional compliance verifier for evolution changes.

    Implements six constitutional red lines from Athena Constitution v1.4:
    - Red Line 1: Authorized remote only (frankiehot-tech/Athena)
    - Red Line 2: No unauthorized remote additions
    - Red Line 3: No push to unauthorized remote
    - Red Line 4: No gh CLI push to unauthorized remote
    - Red Line 5: No pre-push hook bypass
    - Red Line 6: Authorized remote changes require human approval

    Plus A->B sync direction verification and T3/T2 content exfiltration checks.
    """

    AUTHORIZED_REMOTE_PATTERN = re.compile(r"frankiehot-tech/Athena")

    # T3/T2 keywords that should not leak (constitutional data classification)
    EXFILTRATION_KEYWORDS = [
        "api_key", "api_secret", "private_key", "password",
        "token_secret", "credential",
    ]

    # T3-level content markers (highest sensitivity)
    T3_MARKERS = [
        "宪法修正案草案",
        "T3-内部策略",
        "内部密钥",
    ]

    def check_red_lines(self, change: CodeChange) -> list[ConstitutionCheckResult]:
        """Check all six constitutional red lines against a code change."""
        results: list[ConstitutionCheckResult] = []

        results.extend(self._check_remote_safety(change))
        results.extend(self._check_push_safety(change))
        results.extend(self._check_hook_integrity(change))
        results.extend(self._check_human_approval_requirement(change))

        return results

    def check_sync_direction(self, change: CodeChange) -> SyncCheckResult:
        """Verify A->B unidirectional sync principle (Constitution Article 2)."""
        # Changes to Track B (public/) should not flow back to Track A (openclaw/public/)
        # The constitution defines A->B one-way sync only.
        if change.target_path and "public/" in str(change.target_path):
            # If this change modifies public/ in the source repo,
            # it's a legitimate A->B sync preparation
            return SyncCheckResult(
                valid=True,
                direction="A->B",
                detail="Change targets public/ directory — A→B sync eligible",
            )

        if change.source_path and "public/" in str(change.source_path):
            return SyncCheckResult(
                valid=False,
                direction="B->A",
                detail="Source path indicates B→A flow — violates one-way sync principle",
            )

        return SyncCheckResult(
            valid=True,
            direction="internal",
            detail="No public/ directory involvement — internal change",
        )

    def check_exfiltration(self, content: str) -> ExfiltrationCheckResult:
        """Check for T3/T2 content leakage in change content."""
        flagged: list[str] = []
        content_lower = content.lower()

        # Check for T3 markers
        for marker in self.T3_MARKERS:
            if marker in content:
                flagged.append(f"T3 marker detected: {marker}")

        # Check for credential patterns
        for keyword in self.EXFILTRATION_KEYWORDS:
            if keyword in content_lower:
                flagged.append(f"Credential keyword detected: {keyword}")

        # Check for file paths that may contain secrets
        secret_path_patterns = [".env", "credentials.json", ".key", ".pem"]
        for pattern in secret_path_patterns:
            if pattern in content_lower:
                flagged.append(f"Secret file path detected: {pattern}")

        return ExfiltrationCheckResult(
            clean=len(flagged) == 0,
            flagged_items=flagged,
            detail="Content exfiltration check " + ("PASSED" if not flagged else f"FLAGGED: {flagged}"),
        )

    # ─── Internal Red Line Checks ───

    def _check_remote_safety(self, change: CodeChange) -> list[ConstitutionCheckResult]:
        """Red Lines 1-2: Authorized remote only, no unauthorized additions."""
        results: list[ConstitutionCheckResult] = []

        # Check if the change modifies git remote configuration
        if change.modified_files:
            for f in change.modified_files:
                f_str = str(f).lower()
                if "git" in f_str and "config" in f_str:
                    # Git config change — verify remote
                    results.append(ConstitutionCheckResult(
                        rule_id="RL-1",
                        description="Git remote configuration change detected",
                        severity=SeverityLevel.WARN,
                        detail=f"File {f} modifies git config — verify remote is authorized",
                    ))

        # Verify remote if git is available
        try:
            import subprocess
            result = subprocess.run(
                ["git", "remote", "-v"],
                capture_output=True, text=True, timeout=10,
            )
            remote_lines = result.stdout.strip().split("\n")
            for line in remote_lines:
                if line.strip() and not self.AUTHORIZED_REMOTE_PATTERN.search(line):
                    results.append(ConstitutionCheckResult(
                        rule_id="RL-2",
                        description="Unauthorized remote detected",
                        severity=SeverityLevel.BLOCK,
                        detail=f"Remote line does not match authorized pattern: {line.strip()}",
                    ))
        except Exception:
            results.append(ConstitutionCheckResult(
                rule_id="RL-2",
                description="Cannot verify git remote (git unavailable)",
                severity=SeverityLevel.WARN,
                detail="Git not available for remote verification",
            ))

        if not results:
            results.append(ConstitutionCheckResult(
                rule_id="RL-1/2",
                description="Remote safety verified",
                severity=SeverityLevel.PASS,
                detail="All remotes match authorized pattern",
            ))

        return results

    def _check_push_safety(self, change: CodeChange) -> list[ConstitutionCheckResult]:
        """Red Lines 3-4: No push to unauthorized remote."""
        results: list[ConstitutionCheckResult] = []

        # Check if change contains push commands to non-authorized remotes
        if change.diff_content:
            push_patterns = [
                r"git\s+push\s+(?!origin\s|frankiehot-tech)",
                r"gh\s+(repo|pr)\s+.*\s+(?!frankiehot-tech)",
            ]
            for pattern in push_patterns:
                matches = re.findall(pattern, change.diff_content)
                if matches:
                    results.append(ConstitutionCheckResult(
                        rule_id="RL-3/4",
                        description="Potentially unauthorized push command detected",
                        severity=SeverityLevel.BLOCK,
                        detail=f"Pattern matched: {pattern}",
                    ))

        if not results:
            results.append(ConstitutionCheckResult(
                rule_id="RL-3/4",
                description="Push safety verified",
                severity=SeverityLevel.PASS,
                detail="No unauthorized push commands detected",
            ))

        return results

    def _check_hook_integrity(self, change: CodeChange) -> list[ConstitutionCheckResult]:
        """Red Line 5: No pre-push hook bypass."""
        results: list[ConstitutionCheckResult] = []

        if change.diff_content:
            bypass_patterns = [
                r"--no-verify",
                r"--no-hooks",
                r"bypass.*hook",
                r"skip.*pre.push",
            ]
            for pattern in bypass_patterns:
                if re.search(pattern, change.diff_content, re.IGNORECASE):
                    results.append(ConstitutionCheckResult(
                        rule_id="RL-5",
                        description="Pre-push hook bypass attempt detected",
                        severity=SeverityLevel.BLOCK,
                        detail=f"Pattern matched: {pattern}",
                    ))

        # Check if .git/hooks/pre-push was modified
        if change.modified_files:
            for f in change.modified_files:
                if "pre-push" in str(f).lower():
                    results.append(ConstitutionCheckResult(
                        rule_id="RL-5",
                        description="Pre-push hook file modified",
                        severity=SeverityLevel.WARN,
                        detail=f"File {f} modifies pre-push hook — verify integrity",
                    ))

        if not results:
            results.append(ConstitutionCheckResult(
                rule_id="RL-5",
                description="Hook integrity verified",
                severity=SeverityLevel.PASS,
                detail="No hook bypass detected",
            ))

        return results

    def _check_human_approval_requirement(self, change: CodeChange) -> list[ConstitutionCheckResult]:
        """Red Line 6: Authorized remote changes require human approval."""
        results: list[ConstitutionCheckResult] = []

        # Changes to constitution files or remote config require human approval
        requires_approval = False
        approval_reasons: list[str] = []

        if change.modified_files:
            for f in change.modified_files:
                f_str = str(f).lower()
                if "宪法" in f_str or "constitution" in f_str:
                    requires_approval = True
                    approval_reasons.append(f"Constitution file: {f}")
                if "remote" in f_str and "config" in f_str:
                    requires_approval = True
                    approval_reasons.append(f"Remote config: {f}")

        if requires_approval:
            results.append(ConstitutionCheckResult(
                rule_id="RL-6",
                description="Human approval required",
                severity=SeverityLevel.BLOCK,
                detail="Change requires human approval: " + "; ".join(approval_reasons),
            ))
        else:
            results.append(ConstitutionCheckResult(
                rule_id="RL-6",
                description="No human approval required",
                severity=SeverityLevel.PASS,
                detail="Change does not require human approval",
            ))

        return results


@dataclass
class CodeChange:
    """Represents a code change to be verified."""
    description: str
    modified_files: list[str] = field(default_factory=list)
    diff_content: str = ""
    source_path: str | None = None
    target_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
