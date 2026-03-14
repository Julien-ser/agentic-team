"""
Security Agent - vulnerability scanning and code review specialist.

This agent performs automated security analysis on code and dependencies,
detecting common vulnerabilities and sending alerts to other agents.
"""

import asyncio
import logging
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

from src.agents.base_agent import BaseAgent
from src.messaging.redis_broker import RedisMessageBroker
from src.state.state_manager import StateManager
from src.protocols.agent_specs import (
    AgentRole,
    MessageType,
    Task,
    SecurityFinding,
    Result,
    TaskStatus,
)
from src.security.owasp_validator import OWASPTop10Validator


logger = logging.getLogger(__name__)


class SecurityAgent(BaseAgent):
    """
    Security specialist agent with vulnerability scanning capabilities.

    Capabilities:
    - Scan code for hardcoded secrets and sensitive patterns
    - Detect SQL injection and XSS vulnerabilities
    - Audit dependencies for known CVEs using safety/pip-audit
    - Perform comprehensive OWASP Top 10 2021 compliance validation
    - Send security alerts and recommendations to other agents
    """

    # Secret detection patterns (CWE-798: Use of Hard-coded Credentials)
    SECRET_PATTERNS = {
        "AWS_KEY": {
            "pattern": r"AKIA[0-9A-Z]{16}",
            "description": "AWS Access Key ID",
            "severity": "critical",
            "cwe": "CWE-798",
        },
        "AWS_SECRET": {
            "pattern": r"[0-9a-zA-Z/+]{40}",
            "description": "AWS Secret Access Key",
            "severity": "critical",
            "cwe": "CWE-798",
            "context": ["secret", "password", "key"],
        },
        "GITHUB_TOKEN": {
            "pattern": r"ghp_[0-9a-zA-Z]{36}|gho_[0-9a-zA-Z]{36}|ghu_[0-9a-zA-Z]{36}|ghs_[0-9a-zA-Z]{36}|ghr_[0-9a-zA-Z]{36}",
            "description": "GitHub Personal Access Token",
            "severity": "critical",
            "cwe": "CWE-798",
        },
        "GITHUB_OAUTH": {
            "pattern": r"gho_[0-9a-zA-Z]{36}",
            "description": "GitHub OAuth Token",
            "severity": "critical",
            "cwe": "CWE-798",
        },
        "PASSWORD": {
            "pattern": r'(?i)password\s*=\s*[\'"][^\'"]+[\'"]',
            "description": "Hardcoded password",
            "severity": "high",
            "cwe": "CWE-798",
        },
        "API_KEY": {
            "pattern": r'(?i)(api[_-]?key|apikey)\s*[=:]\s*[\'"][^\'"]{8,}[\'"]',
            "description": "Hardcoded API key",
            "severity": "high",
            "cwe": "CWE-798",
        },
        "DATABASE_URL": {
            "pattern": r"(?i)(postgresql|mysql|mongodb)://[^\s]+:[^\s]+@[^\s]+",
            "description": "Database connection string with credentials",
            "severity": "high",
            "cwe": "CWE-798",
        },
        "PRIVATE_KEY": {
            "pattern": r"-----BEGIN (RSA )?PRIVATE KEY-----",
            "description": "Private key material",
            "severity": "critical",
            "cwe": "CWE-798",
        },
        "JWT_SECRET": {
            "pattern": r'(?i)(jwt|token).*(secret|key).*[\'"][^\'"]{8,}[\'"]',
            "description": "JWT secret key",
            "severity": "critical",
            "cwe": "CWE-798",
        },
    }

    # SQL injection patterns
    SQL_INJECTION_PATTERNS = {
        "raw_sql_concat": {
            "pattern": r"execute\(.*\+.*\)",
            "description": "SQL query built via string concatenation",
            "severity": "high",
            "cwe": "CWE-89",
        },
        "raw_sql_format": {
            "pattern": r"execute\(.*%s.*\)",
            "description": "SQL query using format strings",
            "severity": "high",
            "cwe": "CWE-89",
        },
        "fstring_sql": {
            "pattern": r'(?i)f[\'"][^\'"]*(SELECT|INSERT|UPDATE|DELETE)[^\'"]*\{[^}]+\}[\'"]',
            "description": "SQL query built with f-string",
            "severity": "high",
            "cwe": "CWE-89",
        },
    }

    # XSS patterns
    XSS_PATTERNS = {
        "unsafe_render": {
            "pattern": r"\.html\(.*\)\s*(?!.*safe)",
            "description": "Rendering template without safe filter",
            "severity": "medium",
            "cwe": "CWE-79",
        },
        "innerHTML_assign": {
            "pattern": r"innerHTML\s*=",
            "description": "Direct innerHTML assignment (possible XSS)",
            "severity": "medium",
            "cwe": "CWE-79",
        },
    }

    def get_role(self) -> AgentRole:
        """Return the security agent role."""
        return AgentRole.SECURITY

    def __init__(
        self,
        agent_id: Optional[str] = None,
        broker: Optional[RedisMessageBroker] = None,
        state_manager: Optional[StateManager] = None,
    ):
        """Initialize security agent with OWASP validator."""
        super().__init__(agent_id=agent_id, broker=broker, state_manager=state_manager)
        self.owasp_validator = OWASPTop10Validator()

    async def initialize(self) -> None:
        """Initialize security agent resources."""
        await super().initialize()

        # Register message handlers
        self.register_message_handler(
            MessageType.CODE_REVIEW_REQUEST, self._handle_code_review_request
        )
        self.register_message_handler(
            MessageType.SECURITY_SCAN_REQUEST, self._handle_security_scan_request
        )

        logger.info(f"Security agent {self.agent_id} initialized with handlers")

    async def process_task(self, task: Task) -> Dict[str, Any]:
        """
        Process a security-related task.

        Args:
            task: Task with description and parameters

        Returns:
            Dict with results including any security findings
        """
        start_time = asyncio.get_event_loop().time()

        try:
            task.mark_in_progress()

            # Parse task description to determine action
            description = task.description.lower()

            if "code review" in description or "scan code" in description:
                # CODE_REVIEW_REQUEST type task
                code_path = task.payload.get("code_path", ".")
                findings = await self.scan_codebase(code_path)

                # Send findings to SW_DEV if critical/high severity
                if any(f.severity in ["critical", "high"] for f in findings):
                    await self.send_security_alert(
                        findings=[
                            f for f in findings if f.severity in ["critical", "high"]
                        ],
                        message=f"Critical vulnerabilities found in {code_path}",
                    )

                return {
                    "success": True,
                    "output": {
                        "findings": [f.dict() for f in findings],
                        "total_findings": len(findings),
                        "critical_count": sum(
                            1 for f in findings if f.severity == "critical"
                        ),
                        "high_count": sum(1 for f in findings if f.severity == "high"),
                    },
                    "artifacts": [],
                    "execution_time": asyncio.get_event_loop().time() - start_time,
                }

            elif (
                "dependency" in description
                or "cve" in description
                or "audit" in description
            ):
                # Dependency audit task
                findings = await self.audit_dependencies()

                return {
                    "success": True,
                    "output": {
                        "findings": findings,
                        "audit_complete": True,
                    },
                    "execution_time": asyncio.get_event_loop().time() - start_time,
                }

            else:
                # Default comprehensive security scan
                code_path = task.payload.get("code_path", ".")
                findings = await self.comprehensive_scan(code_path)

                return {
                    "success": True,
                    "output": {
                        "findings": [f.dict() for f in findings],
                        "scan_type": "comprehensive",
                        "total_findings": len(findings),
                    },
                    "execution_time": asyncio.get_event_loop().time() - start_time,
                }

        except Exception as e:
            logger.error(f"Security task failed: {e}", exc_info=True)
            raise

    async def scan_codebase(self, path: str) -> List[SecurityFinding]:
        """
        Scan codebase for all security vulnerabilities.

        Args:
            path: Path to scan (file or directory)

        Returns:
            List of SecurityFinding objects
        """
        findings = []
        scan_path = Path(path)

        if not scan_path.exists():
            logger.error(f"Scan path does not exist: {path}")
            return findings

        # Determine files to scan
        files_to_scan = []
        if scan_path.is_file() and scan_path.suffix == ".py":
            files_to_scan = [scan_path]
        elif scan_path.is_dir():
            files_to_scan = list(scan_path.rglob("*.py"))
        else:
            files_to_scan = [scan_path]

        # Scan each file
        for file_path in files_to_scan:
            try:
                findings.extend(await self._scan_file(file_path))
            except Exception as e:
                logger.warning(f"Error scanning {file_path}: {e}")

        return findings

    async def _scan_file(self, file_path: Path) -> List[SecurityFinding]:
        """
        Scan a single file for vulnerabilities.

        Args:
            file_path: Path to file

        Returns:
            List of SecurityFinding objects
        """
        findings = []

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                lines = content.split("\n")
        except Exception as e:
            logger.warning(f"Cannot read file {file_path}: {e}")
            return findings

        # Check for secrets
        findings.extend(await self._scan_for_secrets(str(file_path), content, lines))

        # Check for SQL injection
        findings.extend(
            await self._scan_for_sql_injection(str(file_path), content, lines)
        )

        # Check for XSS
        findings.extend(await self._scan_for_xss(str(file_path), content, lines))

        return findings

    async def _scan_for_secrets(
        self, file_path: str, content: str, lines: List[str]
    ) -> List[SecurityFinding]:
        """Detect hardcoded secrets and credentials."""
        findings = []

        for secret_type, config in self.SECRET_PATTERNS.items():
            pattern = re.compile(config["pattern"])

            for line_num, line in enumerate(lines, start=1):
                matches = pattern.findall(line)
                if matches:
                    # Check context if needed
                    if "context" in config:
                        line_lower = line.lower()
                        if not any(ctx in line_lower for ctx in config["context"]):
                            continue  # Skip if context doesn't match

                    finding = SecurityFinding(
                        severity=config["severity"],
                        category="hardcoded_secret",
                        file_path=file_path,
                        line_number=line_num,
                        description=f"Potential {config['description']} detected: {secret_type}",
                        recommendation="Remove hardcoded credentials. Use environment variables or secure secret management.",
                        cwe_id=config.get("cwe"),
                        confidence=0.85,
                    )
                    findings.append(finding)
                    logger.warning(f"Found {secret_type} in {file_path}:{line_num}")

        return findings

    async def _scan_for_sql_injection(
        self, file_path: str, content: str, lines: List[str]
    ) -> List[SecurityFinding]:
        """Detect potential SQL injection vulnerabilities."""
        findings = []

        for vuln_type, config in self.SQL_INJECTION_PATTERNS.items():
            pattern = re.compile(config["pattern"])

            for line_num, line in enumerate(lines, start=1):
                if pattern.search(line):
                    finding = SecurityFinding(
                        severity=config["severity"],
                        category="sql_injection",
                        file_path=file_path,
                        line_number=line_num,
                        description=f"Potential SQL injection: {config['description']}",
                        recommendation="Use parameterized queries or ORM. Never concatenate user input into SQL strings.",
                        cwe_id=config.get("cwe"),
                        confidence=0.75,
                    )
                    findings.append(finding)
                    logger.warning(
                        f"Found SQL injection pattern in {file_path}:{line_num}"
                    )

        return findings

    async def _scan_for_xss(
        self, file_path: str, content: str, lines: List[str]
    ) -> List[SecurityFinding]:
        """Detect potential XSS vulnerabilities."""
        findings = []

        for vuln_type, config in self.XSS_PATTERNS.items():
            pattern = re.compile(config["pattern"])

            for line_num, line in enumerate(lines, start=1):
                if pattern.search(line):
                    finding = SecurityFinding(
                        severity=config["severity"],
                        category="xss",
                        file_path=file_path,
                        line_number=line_num,
                        description=f"Potential XSS: {config['description']}",
                        recommendation="Use safe template rendering. Escape user input before rendering.",
                        cwe_id=config.get("cwe"),
                        confidence=0.70,
                    )
                    findings.append(finding)
                    logger.warning(f"Found XSS pattern in {file_path}:{line_num}")

        return findings

    async def audit_dependencies(self) -> List[Dict[str, Any]]:
        """
        Audit Python dependencies for known CVEs.

        Uses safety and pip-audit to check for vulnerable packages.

        Returns:
            List of vulnerability dictionaries
        """
        findings = []

        try:
            # Check if safety is available
            result = subprocess.run(
                ["safety", "check", "--json"],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                findings.append(
                    {"tool": "safety", "status": "clean", "vulnerabilities": []}
                )
            else:
                # Parse JSON output
                import json

                try:
                    vulns = json.loads(result.stdout)
                    findings.append(
                        {
                            "tool": "safety",
                            "status": "vulnerabilities_found",
                            "vulnerabilities": vulns,
                        }
                    )

                    # Send alert for vulnerabilities
                    if vulns:
                        await self.send_security_alert(
                            findings=[],
                            message=f"Found {len(vulns)} vulnerabilities in dependencies (safety)",
                            severity="high",
                        )
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse safety output: {result.stdout}")

        except FileNotFoundError:
            logger.warning("Safety not installed, skipping dependency audit")
            findings.append(
                {
                    "tool": "safety",
                    "status": "not_available",
                    "error": "safety package not installed",
                }
            )
        except subprocess.TimeoutExpired:
            logger.error("Safety check timed out")
            findings.append(
                {
                    "tool": "safety",
                    "status": "timeout",
                    "error": "Audit timed out after 30 seconds",
                }
            )
        except Exception as e:
            logger.error(f"Error running safety: {e}")
            findings.append({"tool": "safety", "status": "error", "error": str(e)})

        # Also try pip-audit if available
        try:
            result = subprocess.run(
                ["pip-audit", "--format", "json"],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                findings.append(
                    {"tool": "pip-audit", "status": "clean", "vulnerabilities": []}
                )
            else:
                import json

                try:
                    audit_data = json.loads(result.stdout)
                    vulns = []
                    for vuln in audit_data.get("vulnerabilities", []):
                        vulns.append(
                            {
                                "package": vuln.get("package", {}).get(
                                    "name", "unknown"
                                ),
                                "version": vuln.get("package", {}).get(
                                    "version", "unknown"
                                ),
                                "vulnerability_id": vuln.get("id", "unknown"),
                                "description": vuln.get("description", ""),
                            }
                        )

                    findings.append(
                        {
                            "tool": "pip-audit",
                            "status": "vulnerabilities_found",
                            "vulnerabilities": vulns,
                        }
                    )

                except json.JSONDecodeError:
                    logger.error(f"Failed to parse pip-audit output")

        except FileNotFoundError:
            logger.debug("pip-audit not installed, skipping")
            findings.append(
                {
                    "tool": "pip-audit",
                    "status": "not_available",
                    "error": "pip-audit package not installed",
                }
            )
        except Exception as e:
            logger.error(f"Error running pip-audit: {e}")
            findings.append({"tool": "pip-audit", "status": "error", "error": str(e)})

        return findings

    async def comprehensive_scan(self, path: str) -> List[SecurityFinding]:
        """
        Perform comprehensive security scan including code and dependencies.

        Args:
            path: Path to scan

        Returns:
            List of SecurityFinding objects
        """
        findings = []

        # Scan code
        code_findings = await self.scan_codebase(path)
        findings.extend(code_findings)

        # Audit dependencies
        dep_findings = await self.audit_dependencies()

        # Create summary findings for dependency audit
        for tool_result in dep_findings:
            if tool_result.get("status") == "vulnerabilities_found":
                vulns = tool_result.get("vulnerabilities", [])
                finding = SecurityFinding(
                    severity="medium",
                    category="vulnerable_dependency",
                    file_path="requirements.txt",
                    line_number=None,
                    description=f"Found {len(vulns)} vulnerabilities in dependencies (via {tool_result.get('tool')})",
                    recommendation="Update vulnerable packages to latest secure versions. Use dependabot or similar.",
                    cwe_id="CWE-1104",
                    confidence=0.9,
                )
                findings.append(finding)

        return findings

    async def validate_owasp_top10(self, path: str) -> Dict[str, Any]:
        """
        Perform OWASP Top 10 2021 compliance validation.

        Args:
            path: Path to scan (file or directory)

        Returns:
            Dictionary with compliance report and findings as SecurityFinding objects
        """
        scan_path = Path(path)
        if not scan_path.exists():
            return {
                "success": False,
                "error": f"Path does not exist: {path}",
                "compliance": False,
                "findings": [],
            }

        # Run OWASP validator
        if scan_path.is_dir():
            owasp_results = await self.owasp_validator.validate_directory(scan_path)
        else:
            owasp_results = await self.owasp_validator.validate_file(scan_path)

        # Convert OWASPCheckResult to SecurityFinding
        findings = []
        for result in owasp_results:
            finding = SecurityFinding(
                severity=result.severity,
                category=f"owasp_{result.category_id.lower()}",
                file_path=result.file_path or path,
                line_number=result.line_number,
                description=f"[OWASP {result.category_id}] {result.check_name}: {result.evidence[0] if result.evidence else 'No evidence'}",
                recommendation=result.recommendation,
                cwe_id=result.cwe_id,
                confidence=0.8,
            )
            findings.append(finding)

        # Generate compliance report
        compliance_report = self.owasp_validator.generate_compliance_report(
            owasp_results
        )

        # Determine overall compliance
        is_compliant = compliance_report.get("overall_compliance", False)

        # Count by severity
        severity_counts = {
            "critical": sum(1 for f in findings if f.severity == "critical"),
            "high": sum(1 for f in findings if f.severity == "high"),
            "medium": sum(1 for f in findings if f.severity == "medium"),
            "low": sum(1 for f in findings if f.severity == "low"),
        }

        return {
            "success": True,
            "compliance": is_compliant,
            "overall_compliance": is_compliant,
            "compliance_report": compliance_report,
            "findings": [f.dict() for f in findings],
            "total_findings": len(findings),
            "severity_counts": severity_counts,
            "scan_type": "owasp_top10_2021",
            "target": path,
        }

    async def send_security_alert(
        self, findings: List[SecurityFinding], message: str, severity: str = "high"
    ) -> bool:
        """
        Send security alert to software development agent.

        Args:
            findings: List of security findings
            message: Alert message
            severity: Overall severity level

        Returns:
            True if sent successfully
        """
        payload = {
            "message": message,
            "severity": severity,
            "findings": [f.dict() for f in findings],
            "agent_id": self.agent_id,
            "timestamp": asyncio.get_event_loop().time(),
        }

        return await self.send_message(
            recipient=AgentRole.SW_DEV,
            message_type=MessageType.SECURITY_ALERT,
            payload=payload,
        )

    # Message handlers

    async def _handle_code_review_request(self, message):
        """
        Handle code review request from another agent.

        Expected payload:
        - code_path: path to code to review
        - code: (optional) direct code content
        """
        try:
            payload = message.payload
            code_path = payload.get("code_path", ".")

            logger.info(
                f"Received code review request for {code_path} from {message.sender}"
            )

            # Perform the scan
            findings = await self.scan_codebase(code_path)

            # Send response back
            response = {
                "findings": [f.dict() for f in findings],
                "total_findings": len(findings),
                "code_path": code_path,
                "reviewer": self.agent_id,
            }

            await self.send_message(
                recipient=message.sender,
                message_type=MessageType.CODE_REVIEW_RESPONSE,
                payload=response,
                correlation_id=message.correlation_id,
            )

        except Exception as e:
            logger.error(f"Error handling code review request: {e}")

    async def _handle_security_scan_request(self, message):
        """
        Handle security scan request from another agent.

        Expected payload:
        - scan_type: 'quick' | 'comprehensive'
        - target: path or component name
        """
        try:
            payload = message.payload
            scan_type = payload.get("scan_type", "quick")
            target = payload.get("target", ".")

            logger.info(
                f"Received security scan request ({scan_type}) for {target} from {message.sender}"
            )

            owasp_metadata = None
            if scan_type == "comprehensive":
                findings = await self.comprehensive_scan(target)
            elif scan_type == "owasp":
                owasp_result = await self.validate_owasp_top10(target)
                findings = [
                    SecurityFinding(**f) for f in owasp_result.get("findings", [])
                ]
                owasp_metadata = {
                    "compliance": owasp_result.get("compliance"),
                    "compliance_report": owasp_result.get("compliance_report"),
                }
            else:
                findings = await self.scan_codebase(target)

            response = {
                "findings": [f.dict() for f in findings],
                "scan_type": scan_type,
                "target": target,
                "total_findings": len(findings),
                "severity_counts": {
                    "critical": sum(1 for f in findings if f.severity == "critical"),
                    "high": sum(1 for f in findings if f.severity == "high"),
                    "medium": sum(1 for f in findings if f.severity == "medium"),
                    "low": sum(1 for f in findings if f.severity == "low"),
                },
            }
            if owasp_metadata:
                response.update(owasp_metadata)

            await self.send_message(
                recipient=message.sender,
                message_type=MessageType.SECURITY_REPORT,
                payload=response,
                correlation_id=message.correlation_id,
            )

        except Exception as e:
            logger.error(f"Error handling security scan request: {e}")

    async def health_check(self) -> Dict[str, Any]:
        """Extended health check with security-specific info."""
        health = await super().health_check()

        # Add security-specific metrics
        health["patterns_loaded"] = (
            len(self.SECRET_PATTERNS)
            + len(self.SQL_INJECTION_PATTERNS)
            + len(self.XSS_PATTERNS)
        )

        return health
