"""
OWASP Top 10 2021 Checklist Validator.

This module provides comprehensive security validation against the OWASP Top 10
most critical security risks. It integrates with the SecurityAgent to provide
automated compliance checking.
"""

import asyncio
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Tuple

logger = logging.getLogger(__name__)


@dataclass
class OWASPCheckResult:
    """Result of a single OWASP check."""

    category_id: str  # e.g., "A01", "A02"
    category_name: str
    check_name: str
    passed: bool
    evidence: List[str]
    recommendation: str
    severity: str
    cwe_id: Optional[str] = None
    line_number: Optional[int] = None
    file_path: Optional[str] = None


class OWASPTop10Validator:
    """
    Validates code against OWASP Top 10 2021 security categories.

    Each category has specific checks designed to identify common vulnerabilities
    and security anti-patterns in Python codebases.
    """

    def __init__(self):
        """Initialize validator with OWASP check rules."""
        self.checks = self._define_checks()

    def _define_checks(self) -> Dict[str, List[Dict[str, Any]]]:
        """Define all OWASP Top 10 checks and their patterns."""
        return {
            # A01: Broken Access Control
            "A01": [
                {
                    "name": "Missing authentication decorators",
                    "pattern": r"@app\.route|def\s+\w+\(.*\):\s*(?!.*@.*auth|.*@.*login|.*@.*require)",
                    "description": "Endpoint lacks authentication requirement",
                    "severity": "high",
                    "recommendation": "Add authentication decorators to all sensitive endpoints",
                    "file_pattern": r".*\.py$",
                    "context": ["flask", "fastapi", "django", "route", "endpoint"],
                },
                {
                    "name": "Missing authorization checks",
                    "pattern": r"if\s+.*user\.(is_admin|is_authenticated|role):\s*pass",
                    "description": "Authorization check present but not enforced",
                    "severity": "high",
                    "recommendation": "Implement proper authorization checks for all actions",
                },
                {
                    "name": "Direct object references",
                    "pattern": r"SELECT.*WHERE.*id.*=.*request\.(args|form|json)",
                    "description": "Potential IDOR via direct object reference",
                    "severity": "high",
                    "recommendation": "Use indirect references and validate user permissions",
                    "cwe": "CWE-639",
                },
            ],
            # A02: Cryptographic Failures
            "A02": [
                {
                    "name": "Hardcoded secrets",
                    "pattern": r"(?i)(?:password|secret|key|token|api_key)\s*[=:]\s*['\"][^'\"]{4,}['\"]",
                    "description": "Hardcoded credentials detected",
                    "severity": "critical",
                    "recommendation": "Use environment variables or secure vault for secrets",
                    "cwe": "CWE-798",
                },
                {
                    "name": "Weak cryptographic algorithms",
                    "pattern": r"(?:md5|sha1|DES|RC4|BLOWFISH)\b",
                    "description": "Use of weak or broken cryptographic algorithm",
                    "severity": "high",
                    "recommendation": "Use SHA-256, AES-256, or modern cryptographic primitives",
                    "cwe": "CWE-327",
                },
                {
                    "name": "Plaintext transmission",
                    "pattern": r"http://(?!localhost|127\.0\.0\.1)",
                    "description": "Unencrypted HTTP connection",
                    "severity": "medium",
                    "recommendation": "Use HTTPS for all external communications",
                    "cwe": "CWE-319",
                },
            ],
            # A03: Injection
            "A03": [
                {
                    "name": "SQL injection via string concatenation",
                    "pattern": r"(?:execute|cursor\.execute)\(.*\+.*\)",
                    "description": "SQL query built via string concatenation",
                    "severity": "critical",
                    "recommendation": "Use parameterized queries or ORM",
                    "cwe": "CWE-89",
                },
                {
                    "name": "SQL injection via format strings",
                    "pattern": r"(?:execute|cursor\.execute)\(.*%.*\)",
                    "description": "SQL query using format strings",
                    "severity": "critical",
                    "recommendation": "Use parameterized queries",
                    "cwe": "CWE-89",
                },
                {
                    "name": "Command injection",
                    "pattern": r"(?:os\.system|subprocess\.call|subprocess\.run|exec|eval)\s*\(.*input.*\)",
                    "description": "Potential command injection via user input",
                    "severity": "critical",
                    "recommendation": "Validate and sanitize all user input; use safe APIs",
                    "cwe": "CWE-78",
                },
                {
                    "name": "XSS via template rendering",
                    "pattern": r"\.render\(.*\)|\.format\(.*\)",
                    "description": "Template rendering without auto-escaping",
                    "severity": "medium",
                    "recommendation": "Use auto-escaping templates or escape user input",
                    "cwe": "CWE-79",
                },
                {
                    "name": "Unsafe deserialization",
                    "pattern": r"pickle\.load|yaml\.load\s*(?!.*Loader=yaml\.SafeLoader)",
                    "description": "Unsafe deserialization of untrusted data",
                    "severity": "high",
                    "recommendation": "Use json.loads or yaml.safe_load",
                    "cwe": "CWE-502",
                },
            ],
            # A04: Insecure Design
            "A04": [
                {
                    "name": "Missing rate limiting",
                    "pattern": r"#\s*TODO.*rate|pass\s*#\s*rate.*limit",
                    "description": "Rate limiting not implemented (incomplete)",
                    "severity": "medium",
                    "recommendation": "Implement rate limiting on all public endpoints",
                    "cwe": "CWE-770",
                },
                {
                    "name": "No input validation",
                    "pattern": r"def\s+\w+\(.*\):\s*(?!.*validate|.*schema|.*check).*\n\s+.*process",
                    "description": "Function processes input without validation",
                    "severity": "high",
                    "recommendation": "Add input validation before processing",
                    "cwe": "CWE-20",
                },
                {
                    "name": "Mass assignment vulnerability",
                    "pattern": r"model\.update\(.*request\.(json|form)",
                    "description": "Direct assignment from user input to model",
                    "severity": "high",
                    "recommendation": "Use explicit field whitelisting for updates",
                    "cwe": "CWE-915",
                },
            ],
            # A05: Security Misconfiguration
            "A05": [
                {
                    "name": "Debug mode enabled",
                    "pattern": r"debug\s*=\s*True|DEBUG\s*=\s*True",
                    "description": "Debug mode is enabled in code",
                    "severity": "medium",
                    "recommendation": "Disable debug mode in production",
                    "cwe": "CWE-489",
                },
                {
                    "name": "Verbose error messages",
                    "pattern": r"except.*:\s*print\(.*\)|except.*:\s*logging\.debug\(.*\)",
                    "description": "Exception may leak sensitive information",
                    "severity": "low",
                    "recommendation": "Log errors without exposing details to users",
                    "cwe": "CWE-209",
                },
                {
                    "name": "Default credentials",
                    "pattern": r"(?:admin|password|user)\s*[=:]\s*['\"]?(?:admin|password|12345|qwerty)['\"]?",
                    "description": "Default or weak credentials",
                    "severity": "high",
                    "recommendation": "Change default credentials and enforce strong passwords",
                    "cwe": "CWE-521",
                },
            ],
            # A06: Vulnerable and Outdated Components (handled by dependency audit)
            "A06": [
                # Dependency check is separate
            ],
            # A07: Identification and Authentication Failures
            "A07": [
                {
                    "name": "Weak password policy",
                    "pattern": r"min_length\s*[<:=]\s*[1-7]|len\(password\)\s*[<:=]",
                    "description": "Password policy too weak",
                    "severity": "medium",
                    "recommendation": "Enforce minimum 8 characters with complexity requirements",
                    "cwe": "CWE-521",
                },
                {
                    "name": "Missing multi-factor authentication",
                    "pattern": r"def\s+login\(.*\):\s*(?!.*mfa|.*2fa|.*totp)",
                    "description": "Login without MFA consideration",
                    "severity": "medium",
                    "recommendation": "Implement multi-factor authentication",
                    "cwe": "CWE-308",
                },
                {
                    "name": "Session fixation",
                    "pattern": r"session\[.*\]\s*=\s*request\.(cookies|args)",
                    "description": "Session value set from untrusted input",
                    "severity": "high",
                    "recommendation": "Regenerate session on login and validate session data",
                    "cwe": "CWE-384",
                },
            ],
            # A08: Software and Data Integrity Failures
            "A08": [
                {
                    "name": "Insecure deserialization",
                    "pattern": r"pickle\.loads|yaml\.load\s*(?!.*SafeLoader)|marshal\.loads",
                    "description": "Unsafe deserialization of untrusted data",
                    "severity": "critical",
                    "recommendation": "Use safe deserialization methods",
                    "cwe": "CWE-502",
                },
                {
                    "name": "No integrity checks",
                    "pattern": r"#\s*TODO.*signature|#\s*TODO.*hash|#\s*FIXME.*integrity",
                    "description": "Missing integrity verification (incomplete)",
                    "severity": "medium",
                    "recommendation": "Add digital signatures or checksums for critical data",
                    "cwe": "CWE-353",
                },
                {
                    "name": "Unvalidated uploads",
                    "pattern": r"save\(.*request\.files|upload\(.*\)",
                    "description": "File upload without validation",
                    "severity": "high",
                    "recommendation": "Validate file types, sizes, and scan for malware",
                    "cwe": "CWE-434",
                },
            ],
            # A09: Security Logging and Monitoring Failures
            "A09": [
                {
                    "name": "No logging of security events",
                    "pattern": r"def\s+(login|logout|password|auth|permission).*:\s*(?!.*log|logger)",
                    "description": "Security-critical action not logged",
                    "severity": "medium",
                    "recommendation": "Log all authentication and authorization events",
                    "cwe": "CWE-778",
                },
                {
                    "name": "Logging sensitive data",
                    "pattern": r"(?:log|logger|print)\(.*password.*\)|(?:log|logger|print)\(.*token.*\)",
                    "description": "Sensitive data may be logged",
                    "severity": "medium",
                    "recommendation": "Never log passwords, tokens, or PII",
                    "cwe": "CWE-532",
                },
                {
                    "name": "No audit trail",
                    "pattern": r"#\s*TODO.*audit|#\s*TODO.*monitor",
                    "description": "Audit logging not implemented (incomplete)",
                    "severity": "low",
                    "recommendation": "Implement comprehensive audit logging",
                    "cwe": "CWE-837",
                },
            ],
            # A10: Server-Side Request Forgery (SSRF)
            "A10": [
                {
                    "name": "Unvalidated URL fetching",
                    "pattern": r"(?:requests\.get|urllib|httpx)\(.*request\.(args|json|form)",
                    "description": "URL from user input used in request",
                    "severity": "high",
                    "recommendation": "Validate and whitelist allowed URLs",
                    "cwe": "CWE-918",
                },
                {
                    "name": "Unrestricted file access",
                    "pattern": r"open\(.*request\.(args|json|form)",
                    "description": "File path from user input used directly",
                    "severity": "high",
                    "recommendation": "Validate file paths and use safe wrappers",
                    "cwe": "CWE-22",
                },
                {
                    "name": "No SSRF protection",
                    "pattern": r"#\s*TODO.*ssrf|#\s*FIXME.*ssrf",
                    "description": "SSRF protection not implemented (incomplete)",
                    "severity": "medium",
                    "recommendation": "Validate URLs against private IP ranges",
                    "cwe": "CWE-918",
                },
            ],
        }

    async def validate_file(
        self, file_path: Path, content: str = None
    ) -> List[OWASPCheckResult]:
        """
        Validate a single file against OWASP Top 10 checks.

        Args:
            file_path: Path to the file
            content: Optional file content (if not provided, file will be read)

        Returns:
            List of OWASPCheckResult for any findings
        """
        if content is None:
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except Exception as e:
                logger.warning(f"Cannot read file {file_path}: {e}")
                return []

        results = []
        lines = content.split("\n")

        # Run all checks for this file
        for category_id, checks in self.checks.items():
            for check in checks:
                # Skip A06 as it's handled separately by dependency audit
                if category_id == "A06":
                    continue

                # Apply file pattern filter if specified
                if "file_pattern" in check:
                    if not re.match(check["file_pattern"], str(file_path)):
                        continue

                pattern = re.compile(check["pattern"])
                matches = pattern.findall(content)

                if matches:
                    # Find first line number where pattern appears
                    line_num = None
                    for i, line in enumerate(lines, start=1):
                        if pattern.search(line):
                            line_num = i
                            break

                    result = OWASPCheckResult(
                        category_id=category_id,
                        category_name=self._get_category_name(category_id),
                        check_name=check["name"],
                        passed=False,
                        evidence=[str(m) for m in matches[:3]],  # First 3 matches
                        recommendation=check["recommendation"],
                        severity=check["severity"],
                        cwe_id=check.get("cwe"),
                        line_number=line_num,
                        file_path=str(file_path),
                    )
                    results.append(result)
                    logger.debug(
                        f"OWASP {category_id} check failed: {check['name']} in {file_path}"
                    )

        return results

    async def validate_directory(self, directory: Path) -> List[OWASPCheckResult]:
        """
        Validate all Python files in a directory.

        Args:
            directory: Root directory to scan

        Returns:
            List of all OWASPCheckResults
        """
        all_results = []
        if not directory.exists():
            logger.error(f"Directory does not exist: {directory}")
            return all_results

        # Find all Python files
        python_files = list(directory.rglob("*.py"))

        # Scan files concurrently with limited parallelism
        semaphore = asyncio.Semaphore(10)

        async def scan_file(file_path):
            async with semaphore:
                return await self.validate_file(file_path)

        tasks = [scan_file(fp) for fp in python_files]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        for results in results_list:
            if isinstance(results, Exception):
                logger.warning(f"Error scanning file: {results}")
                continue
            all_results.extend(results)

        return all_results

    def generate_compliance_report(
        self, results: List[OWASPCheckResult]
    ) -> Dict[str, Any]:
        """
        Generate a compliance report summarizing OWASP Top 10 coverage.

        Args:
            results: List of check results

        Returns:
            Dictionary with compliance summary
        """
        categories = {
            "A01": "Broken Access Control",
            "A02": "Cryptographic Failures",
            "A03": "Injection",
            "A04": "Insecure Design",
            "A05": "Security Misconfiguration",
            "A06": "Vulnerable and Outdated Components",
            "A07": "Identification and Authentication Failures",
            "A08": "Software and Data Integrity Failures",
            "A09": "Security Logging and Monitoring Failures",
            "A10": "Server-Side Request Forgery",
        }

        report = {
            "timestamp": asyncio.get_event_loop().time(),
            "total_checks": len(results),
            "categories": {},
            "overall_compliance": True,
        }

        # Group by category
        for cat_id, cat_name in categories.items():
            cat_results = [r for r in results if r.category_id == cat_id]

            failed_checks = [r for r in cat_results if not r.passed]
            passed = len(failed_checks) == 0

            report["categories"][cat_id] = {
                "name": cat_name,
                "passed": passed,
                "failed_checks": len(failed_checks),
                "total_checks": len(cat_results),
                "findings": [
                    {
                        "check": r.check_name,
                        "severity": r.severity,
                        "file": r.file_path,
                        "line": r.line_number,
                        "recommendation": r.recommendation,
                    }
                    for r in failed_checks
                ],
            }

            if not passed:
                report["overall_compliance"] = False

        return report

    def _get_category_name(self, category_id: str) -> str:
        """Get human-readable category name."""
        names = {
            "A01": "Broken Access Control",
            "A02": "Cryptographic Failures",
            "A03": "Injection",
            "A04": "Insecure Design",
            "A05": "Security Misconfiguration",
            "A06": "Vulnerable and Outdated Components",
            "A07": "Identification and Authentication Failures",
            "A08": "Software and Data Integrity Failures",
            "A09": "Security Logging and Monitoring Failures",
            "A10": "Server-Side Request Forgery",
        }
        return names.get(category_id, "Unknown")
