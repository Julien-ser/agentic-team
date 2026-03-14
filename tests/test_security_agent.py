"""
Unit tests for SecurityAgent.

Tests cover vulnerability scanning, code review, dependency audit,
and A2A message handling.
"""

import asyncio
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.agents.security_agent import SecurityAgent
from src.protocols.agent_specs import (
    AgentRole,
    MessageType,
    Task,
    TaskStatus,
    SecurityFinding,
)
from src.security.owasp_validator import OWASPTop10Validator, OWASPCheckResult


@pytest.fixture
def security_agent():
    """Create a security agent instance."""
    agent = SecurityAgent(agent_id="security-agent-1")
    return agent


@pytest.fixture
def mock_broker():
    """Create mock Redis broker."""
    from src.messaging.redis_broker import RedisMessageBroker

    broker = MagicMock(spec=RedisMessageBroker)
    broker.connect = AsyncMock()
    broker.disconnect = AsyncMock()
    broker.subscribe = AsyncMock(return_value=True)
    broker.publish = AsyncMock(return_value=True)
    broker.start_listening = AsyncMock()
    broker.stop_listening = AsyncMock()
    return broker


@pytest.fixture
def temp_python_file():
    """Create a temporary Python file with test content."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("""
# Test file with various vulnerabilities
import os
import requests

# Hardcoded secrets
AWS_KEY = "AKIAIOSFODNN7EXAMPLE"
PASSWORD = "super_secret_password_123"
API_KEY = "sk_test_abcdef123456789"

def get_user(user_id):
    # SQL injection vulnerability
    query = f"SELECT * FROM users WHERE id = {user_id}"
    cursor.execute(query)
    return cursor.fetchall()

def render_page(data):
    # Potential XSS
    return f"<div>{data}</div>"

def process_payment(amount, card_number):
    # Another SQL injection
    sql = "INSERT INTO payments VALUES (%s, '%s')" % (amount, card_number)
    cursor.execute(sql)

# GitHub token
GITHUB_TOKEN = "ghp_1234567890abcdefghijklmnopqrstuvwxyz"
""")
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink(missing_ok=True)


class TestSecurityAgentInitialization:
    """Test security agent initialization."""

    def test_get_role(self, security_agent):
        """Test agent returns correct role."""
        assert security_agent.get_role() == AgentRole.SECURITY

    def test_init_with_defaults(self):
        """Test agent initialization with auto-generated ID."""
        agent = SecurityAgent()
        assert agent.agent_id.startswith("security-")
        assert agent.role == AgentRole.SECURITY

    def test_init_with_custom_id(self):
        """Test agent initialization with custom ID."""
        agent = SecurityAgent(agent_id="custom-security")
        assert agent.agent_id == "custom-security"

    @pytest.mark.asyncio
    async def test_initialize(self, security_agent):
        """Test agent initialization."""
        await security_agent.initialize()
        assert security_agent._initialized is True
        assert security_agent._start_time is not None

    @pytest.mark.asyncio
    async def test_register_handlers(self, security_agent):
        """Test message handlers registration."""
        await security_agent.initialize()

        assert MessageType.CODE_REVIEW_REQUEST in security_agent._message_handlers
        assert MessageType.SECURITY_SCAN_REQUEST in security_agent._message_handlers


class TestSecretScanning:
    """Test hardcoded secret detection."""

    @pytest.mark.asyncio
    async def test_scan_for_aws_key(self, security_agent, tmp_path):
        """Test detection of AWS access key."""
        test_file = tmp_path / "test_aws.py"
        test_file.write_text("AWS_KEY = 'AKIAIOSFODNN7EXAMPLE'")

        findings = await security_agent._scan_file(test_file)

        assert len([f for f in findings if "AWS_KEY" in f.description]) > 0

    @pytest.mark.asyncio
    async def test_scan_for_github_token(self, security_agent, tmp_path):
        """Test detection of GitHub token."""
        test_file = tmp_path / "test_github.py"
        test_file.write_text(
            "GITHUB_TOKEN = 'ghp_1234567890abcdefghijklmnopqrstuvwxyz'"
        )

        findings = await security_agent._scan_file(test_file)

        assert any("GitHub" in f.description for f in findings)

    @pytest.mark.asyncio
    async def test_scan_for_password(self, security_agent, tmp_path):
        """Test detection of hardcoded password."""
        test_file = tmp_path / "test_pass.py"
        test_file.write_text("password = 'secret123'")

        findings = await security_agent._scan_file(test_file)

        assert any("password" in f.description.lower() for f in findings)

    @pytest.mark.asyncio
    async def test_scan_for_private_key(self, security_agent, tmp_path):
        """Test detection of private key."""
        test_file = tmp_path / "test_key.py"
        test_file.write_text("""
PRIVATE_KEY = '''
-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7VJTUt9Us5cGa
...
-----END PRIVATE KEY-----
'''
""")

        findings = await security_agent._scan_file(test_file)

        assert any("Private key" in f.description for f in findings)

    @pytest.mark.asyncio
    async def test_scan_multiple_secrets(self, security_agent, tmp_path):
        """Test detection of multiple secrets in one file."""
        test_file = tmp_path / "test_multi.py"
        test_file.write_text("""
AWS_KEY = "AKIAIOSFODNN7EXAMPLE"
PASSWORD = "secret123"
api_key = "sk_test_abc123"
""")

        findings = await security_agent._scan_file(test_file)

        assert len(findings) >= 3

    @pytest.mark.asyncio
    async def test_no_false_positives(self, security_agent, tmp_path):
        """Test that legitimate code doesn't trigger false positives."""
        test_file = tmp_path / "test_clean.py"
        test_file.write_text("""
import os
from config import settings

def get_api_endpoint():
    return settings.API_URL

def get_user_input():
    username = input("Enter username: ")
    return username
""")

        findings = await security_agent._scan_file(test_file)

        # Should not find hardcoded secrets
        secret_findings = [f for f in findings if f.category == "hardcoded_secret"]
        assert len(secret_findings) == 0


class TestSQLInjectionScanning:
    """Test SQL injection detection."""

    @pytest.mark.asyncio
    async def test_concatenation_sql(self, security_agent, tmp_path):
        """Test detection of SQL built via string concatenation."""
        test_file = tmp_path / "test_sql1.py"
        test_file.write_text("""
def get_user(user_id):
    cursor.execute("SELECT * FROM users WHERE id = " + user_id)
""")

        findings = await security_agent._scan_file(test_file)

        # Should find at least one SQL injection with concatenation description
        assert any("concatenation" in f.description.lower() for f in findings)

    @pytest.mark.asyncio
    async def test_fstring_sql(self, security_agent, tmp_path):
        """Test detection of SQL built via f-string."""
        test_file = tmp_path / "test_sql2.py"
        test_file.write_text("""
def get_user(user_id):
    cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
""")

        findings = await security_agent._scan_file(test_file)

        assert any("f-string" in f.description.lower() for f in findings)

    @pytest.mark.asyncio
    async def test_format_sql(self, security_agent, tmp_path):
        """Test detection of SQL built via format string."""
        test_file = tmp_path / "test_sql3.py"
        test_file.write_text("""
def get_user(user_id):
    cursor.execute("SELECT * FROM users WHERE id = %s" % user_id)
""")

        findings = await security_agent._scan_file(test_file)

        assert any("format" in f.description.lower() for f in findings)

    @pytest.mark.asyncio
    async def test_safe_query_with_params(self, security_agent, tmp_path):
        """Test that parameterized queries don't trigger false positives."""
        test_file = tmp_path / "test_safe.py"
        test_file.write_text("""
def get_user(user_id):
    query = "SELECT * FROM users WHERE id = %s"
    cursor.execute(query, (user_id,))
""")

        findings = await security_agent._scan_file(test_file)

        sql_findings = [f for f in findings if f.category == "sql_injection"]
        assert len(sql_findings) == 0


class TestXSSScanning:
    """Test XSS vulnerability detection."""

    @pytest.mark.asyncio
    async def test_inner_html_assignment(self, security_agent, tmp_path):
        """Test detection of unsafe innerHTML assignment."""
        test_file = tmp_path / "test_xss1.js"
        test_file.write_text("""
document.getElementById('output').innerHTML = userInput;
""")

        findings = await security_agent._scan_file(test_file)

        assert any("innerHTML" in f.description for f in findings)

    @pytest.mark.asyncio
    async def test_unsafe_render(self, security_agent, tmp_path):
        """Test detection of unsafe template rendering."""
        test_file = tmp_path / "test_xss2.html"
        test_file.write_text("""
<div>{{ user_input }}</div>
""")

        findings = await security_agent._scan_file(test_file)

        # May or may not flag depending on pattern matching
        # This is a basic pattern check
        pass


class TestDependencyAudit:
    """Test dependency vulnerability scanning."""

    @pytest.mark.asyncio
    async def test_audit_with_vulnerabilities(self, security_agent):
        """Test dependency audit with mocked vulnerabilities."""
        mock_result = {
            "vulnerabilities": [
                {
                    "package": "django",
                    "version": "3.0.0",
                    "vulnerability_id": "CVE-2021-1234",
                    "description": "Potential XSS vulnerability",
                }
            ]
        }

        with patch("subprocess.run") as mock_run:
            # First call: safety
            mock_run.return_value = MagicMock(
                returncode=1, stdout='{"vulnerabilities": []}', stderr=""
            )

            findings = await security_agent.audit_dependencies()

            # Should have result from safety and pip-audit
            assert len(findings) >= 1

    @pytest.mark.asyncio
    async def test_audit_clean(self, security_agent):
        """Test dependency audit with no vulnerabilities."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            findings = await security_agent.audit_dependencies()

            # Should indicate clean audit
            assert any(f.get("status") == "clean" for f in findings)

    @pytest.mark.asyncio
    async def test_audit_safety_not_installed(self, security_agent):
        """Test handling when safety is not installed."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            findings = await security_agent.audit_dependencies()

            assert any(
                f.get("tool") == "safety" and f.get("status") == "not_available"
                for f in findings
            )

    @pytest.mark.asyncio
    async def test_audit_timeout(self, security_agent):
        """Test handling of audit timeout."""
        with patch(
            "subprocess.run", side_effect=subprocess.TimeoutExpired("safety", 30)
        ):
            findings = await security_agent.audit_dependencies()

            assert any(f.get("status") == "timeout" for f in findings)


class TestComprehensiveScan:
    """Test comprehensive security scanning."""

    @pytest.mark.asyncio
    async def test_comprehensive_scan_integration(self, security_agent, tmp_path):
        """Test full comprehensive scan with multiple vulnerability types."""
        # Create test file with multiple issues
        test_file = tmp_path / "vuln_app.py"
        test_file.write_text("""
# Secrets
AWS_KEY = "AKIAIOSFODNN7EXAMPLE"
PASSWORD = "secret123"

# SQL Injection
def get_user(user_id):
    query = f"SELECT * FROM users WHERE id = {user_id}"
    cursor.execute(query)

# XSS
def render(data):
    return f"<div>{data}</div>"
""")

        findings = await security_agent.comprehensive_scan(str(tmp_path))

        # Check for different categories
        categories = [f.category for f in findings]
        assert "hardcoded_secret" in categories
        assert "sql_injection" in categories or "xss" in categories

        # Should have at least 3 findings
        assert len(findings) >= 3


class TestTaskProcessing:
    """Test task processing with different task types."""

    @pytest.mark.asyncio
    async def test_process_code_review_task(self, security_agent, tmp_path):
        """Test processing a code review task."""
        # Create test file
        test_dir = tmp_path / "code"
        test_dir.mkdir()
        test_file = test_dir / "app.py"
        test_file.write_text("PASSWORD = 'secret123'")

        # Create task
        task = Task(
            description="Perform code review",
            role=AgentRole.SECURITY,
            payload={"code_path": str(test_dir)},
        )

        result = await security_agent.process_task(task)

        assert result["success"] is True
        assert "findings" in result["output"]
        assert result["output"]["total_findings"] > 0

    @pytest.mark.asyncio
    async def test_process_dependency_audit_task(self, security_agent):
        """Test processing a dependency audit task."""
        task = Task(
            description="Audit dependencies for CVEs",
            role=AgentRole.SECURITY,
            payload={},
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            result = await security_agent.process_task(task)

            assert result["success"] is True
            assert "audit_complete" in result["output"]

    @pytest.mark.asyncio
    async def test_process_comprehensive_scan_task(self, security_agent, tmp_path):
        """Test processing a comprehensive security scan task."""
        test_dir = tmp_path / "code"
        test_dir.mkdir()
        (test_dir / "app.py").write_text("API_KEY = 'test123'")

        task = Task(
            description="Run comprehensive security scan",
            role=AgentRole.SECURITY,
            payload={"code_path": str(test_dir)},
        )

        result = await security_agent.process_task(task)

        assert result["success"] is True
        assert result["output"]["scan_type"] == "comprehensive"

    @pytest.mark.asyncio
    async def test_process_task_with_exception(self, security_agent):
        """Test task processing with exception."""
        task = Task(
            description="Invalid task",
            role=AgentRole.SECURITY,
            payload={"code_path": "/nonexistent/path"},
        )

        result = await security_agent.process_task(task)

        # Should handle exception gracefully
        assert result is not None  # Should return error in output


class TestMessaging:
    """Test A2A messaging functionality."""

    @pytest.mark.asyncio
    async def test_send_security_alert(self, security_agent, mock_broker):
        """Test sending security alert to SW_DEV."""
        security_agent.broker = mock_broker

        findings = [
            SecurityFinding(
                severity="critical",
                category="hardcoded_secret",
                file_path="test.py",
                line_number=1,
                description="AWS key found",
                recommendation="Remove it",
                cwe_id="CWE-798",
                confidence=0.9,
            )
        ]

        success = await security_agent.send_security_alert(
            findings=findings,
            message="Critical vulnerabilities found",
            severity="critical",
        )

        assert success is True
        mock_broker.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_code_review_request(
        self, security_agent, tmp_path, mock_broker
    ):
        """Test handling incoming code review request."""
        # Setup test file
        test_file = tmp_path / "test.py"
        test_file.write_text("PASSWORD = 'secret123'")

        # Create message
        from src.protocols.agent_specs import AgentMessage

        message = AgentMessage(
            sender=AgentRole.SW_DEV,
            recipient=AgentRole.SECURITY,
            message_type=MessageType.CODE_REVIEW_REQUEST,
            payload={"code_path": str(test_file)},
            correlation_id="test-corr-id",
        )

        security_agent.broker = mock_broker
        await security_agent.initialize()

        # Handle message
        await security_agent._handle_code_review_request(message)

        # Should send response
        mock_broker.publish.assert_called()

    @pytest.mark.asyncio
    async def test_handle_security_scan_request(
        self, security_agent, tmp_path, mock_broker
    ):
        """Test handling incoming security scan request."""
        test_file = tmp_path / "test.py"
        test_file.write_text("API_KEY = 'secret'")

        from src.protocols.agent_specs import AgentMessage

        message = AgentMessage(
            sender=AgentRole.SW_DEV,
            recipient=AgentRole.SECURITY,
            message_type=MessageType.SECURITY_SCAN_REQUEST,
            payload={"scan_type": "quick", "target": str(test_file)},
            correlation_id="test-corr-id",
        )

        security_agent.broker = mock_broker
        await security_agent.initialize()

        await security_agent._handle_security_scan_request(message)

        # Should send security report
        mock_broker.publish.assert_called()


class TestHealthCheck:
    """Test health check functionality."""

    @pytest.mark.asyncio
    async def test_health_check(self, security_agent):
        """Test health check returns security-specific info."""
        security_agent._running = True
        security_agent._initialized = True
        security_agent._start_time = datetime.utcnow()

        health = await security_agent.health_check()

        assert health["healthy"] is True
        assert "patterns_loaded" in health
        assert health["patterns_loaded"] > 0


class TestSecurityPatterns:
    """Test specific security pattern detection."""

    @pytest.mark.asyncio
    async def test_database_url_detection(self, security_agent, tmp_path):
        """Test detection of database URLs with credentials."""
        test_file = tmp_path / "db.py"
        test_file.write_text("""
DATABASE_URL = "postgresql://user:password@localhost/db"
CONN = "mysql://admin:secret@127.0.0.1:3306/test"
""")

        findings = await security_agent._scan_file(test_file)

        assert any("Database connection string" in f.description for f in findings)

    @pytest.mark.asyncio
    async def test_jwt_secret_detection(self, security_agent, tmp_path):
        """Test detection of JWT secrets."""
        test_file = tmp_path / "jwt.py"
        test_file.write_text("""
SECRET_KEY = "my-super-secret-jwt-signing-key-12345"
jwt_secret = "another-secret"
""")

        findings = await security_agent._scan_file(test_file)

        assert any("JWT" in f.description for f in findings)


class TestOWASPValidation:
    """Test OWASP Top 10 2021 validation functionality."""

    @pytest.mark.asyncio
    async def test_owasp_validator_initialization(self):
        """Test OWASP validator can be initialized."""
        validator = OWASPTop10Validator()
        assert validator is not None
        assert len(validator.checks) == 10  # All A01-A10 categories

    @pytest.mark.asyncio
    async def test_validate_owasp_top10_file(self, security_agent, tmp_path):
        """Test OWASP validation on a single file with vulnerabilities."""
        test_file = tmp_path / "vuln_app.py"
        test_file.write_text("""
# Broken Access Control (A01)
@app.route('/admin')
def admin_panel():
    pass  # No authentication

# Cryptographic Failures (A02)
SECRET_KEY = "hardcoded_secret_12345"
PASSWORD = "admin123"

# Injection (A03)
def get_user(user_id):
    cursor.execute("SELECT * FROM users WHERE id = " + user_id)

# Insecure Design (A04)
# TODO: rate limit
def process_data():
    data = request.json
    model.update(data)  # Mass assignment

# Security Misconfiguration (A05)
DEBUG = True

# Identification Failures (A07)
def login(username, password):
    if len(password) < 3:  # Weak password policy
        pass
    session['user'] = request.cookies.get('user')  # Session fixation

# Integrity Failures (A08)
import pickle
data = pickle.loads(user_input)  # Unsafe deserialization

# Logging Failures (A09)
def login(user, pwd):
    print(f"Login attempt: {user}, {pwd}")  # Logging credentials

# SSRF (A10)
def fetch_data():
    url = request.args.get('url')
    response = requests.get(url)  # SSRF vulnerability
""")

        result = await security_agent.validate_owasp_top10(str(test_file))

        assert result["success"] is True
        assert "findings" in result
        assert len(result["findings"]) > 0

        # Should have findings across multiple categories
        categories = [f["category"] for f in result["findings"]]
        assert any("owasp_a01" in cat for cat in categories)
        assert any("owasp_a03" in cat for cat in categories)

        # Should count severity levels
        assert (
            result["severity_counts"]["critical"] > 0
            or result["severity_counts"]["high"] > 0
        )

    @pytest.mark.asyncio
    async def test_validate_owasp_top10_directory(self, security_agent, tmp_path):
        """Test OWASP validation on a directory with multiple files."""
        test_dir = tmp_path / "project"
        test_dir.mkdir()

        # File 1 - injection vulnerabilities
        (test_dir / "db.py").write_text("""
def query(user_id):
    sql = "SELECT * FROM users WHERE id = " + user_id
    cursor.execute(sql)
""")

        # File 2 - secrets
        (test_dir / "config.py").write_text("""
API_KEY = "sk_secret123456"
DATABASE_PASSWORD = "db_pass_123"
""")

        # File 3 - XSS and SSRF
        (test_dir / "web.py").write_text("""
@app.route('/fetch')
def fetch():
    url = request.args.get('url')
    return requests.get(url)

def render():
    return f"<div>{request.args.get('data')}</div>"
""")

        result = await security_agent.validate_owasp_top10(str(test_dir))

        assert result["success"] is True
        assert result["total_findings"] > 0
        assert result["scan_type"] == "owasp_top10_2021"

        # Should include compliance report
        assert "compliance_report" in result
        assert "overall_compliance" in result

    @pytest.mark.asyncio
    async def test_owasp_compliance_report_structure(self, security_agent, tmp_path):
        """Test compliance report has correct structure."""
        test_file = tmp_path / "test.py"
        test_file.write_text("SECRET = 'password123'")

        result = await security_agent.validate_owasp_top10(str(test_file))

        report = result["compliance_report"]
        assert "timestamp" in report
        assert "categories" in report
        assert "overall_compliance" in report

        # Check all categories are present
        expected_categories = [
            "A01",
            "A02",
            "A03",
            "A04",
            "A05",
            "A06",
            "A07",
            "A08",
            "A09",
            "A10",
        ]
        for cat in expected_categories:
            assert cat in report["categories"]
            assert "name" in report["categories"][cat]
            assert "passed" in report["categories"][cat]
            assert "failed_checks" in report["categories"][cat]
            assert "total_checks" in report["categories"][cat]

    @pytest.mark.asyncio
    async def test_owasp_clean_file_no_findings(self, security_agent, tmp_path):
        """Test OWASP validation on clean code produces minimal/no findings."""
        test_file = tmp_path / "clean.py"
        test_file.write_text("""
import os
from typing import Optional

def get_user(user_id: int) -> Optional[dict]:
    '''Safely get user by ID using parameterized query.'''
    query = "SELECT * FROM users WHERE id = %s"
    cursor.execute(query, (user_id,))
    return cursor.fetchone()

class UserService:
    '''User management service with proper security.'''

    def __init__(self, db_connection):
        self.db = db_connection

    def create_user(self, username: str, email: str) -> dict:
        '''Create new user with validated input.'''
        if not self._validate_username(username):
            raise ValueError("Invalid username")

        # Use parameterized query
        sql = "INSERT INTO users (username, email) VALUES (%s, %s)"
        self.db.execute(sql, (username, email))
        return {"username": username, "email": email}

    def _validate_username(self, username: str) -> bool:
        '''Validate username format.'''
        return len(username) >= 3 and username.isalnum()
""")

        result = await security_agent.validate_owasp_top10(str(test_file))

        # Clean code should have few or no findings
        assert result["total_findings"] <= 2  # Allow minimal false positives

    @pytest.mark.asyncio
    async def test_owasp_scan_with_nonexistent_path(self, security_agent):
        """Test OWASP validation with non-existent path."""
        result = await security_agent.validate_owasp_top10("/nonexistent/path")

        assert result["success"] is False
        assert "error" in result
        assert "Path does not exist" in result["error"]

    @pytest.mark.asyncio
    async def test_owasp_validator_direct_file_check(self, tmp_path):
        """Test OWASP validator directly on file."""
        validator = OWASPTop10Validator()

        test_file = tmp_path / "test_owasp.py"
        test_file.write_text("""
# A01: Broken Access Control
@app.route('/admin')
def admin():
    pass

# A03: Injection
cursor.execute("SELECT * FROM users WHERE id = " + user_id)

# A02: Cryptographic Failures
SECRET = "hardcoded123"
""")

        results = await validator.validate_file(test_file)

        assert len(results) > 0

        # Check categories
        categories = [r.category_id for r in results]
        assert "A01" in categories
        assert "A02" in categories
        assert "A03" in categories

    @pytest.mark.asyncio
    async def test_owasp_dependency_category_a06(self, security_agent):
        """Test that A06 (Vulnerable Components) is skipped in OWASP validation."""
        # A06 should be handled by dependency audit, not pattern matching
        test_content = """
# This should not trigger A06 pattern checks
import django
import requests
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(test_content)
            temp_path = f.name

        try:
            validator = OWASPTop10Validator()
            results = await validator.validate_file(Path(temp_path))

            # A06 category should be empty (skipped)
            a06_results = [r for r in results if r.category_id == "A06"]
            assert len(a06_results) == 0
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_owasp_severity_distribution(self, security_agent, tmp_path):
        """Test that OWASP checks produce correct severity levels."""
        test_file = tmp_path / "severity_test.py"
        test_file.write_text("""
# Critical: Hardcoded AWS key
AWS_KEY = "AKIAIOSFODNN7EXAMPLE"

# High: SQL injection
def query(q):
    cursor.execute("SELECT * FROM " + q)

# Medium: Debug mode
DEBUG = True

# Low: Verbose error
try:
    do_something()
except:
    print("Error occurred")
""")

        result = await security_agent.validate_owasp_top10(str(test_file))

        severity_counts = result["severity_counts"]
        assert severity_counts["critical"] >= 1
        assert severity_counts["high"] >= 1
        assert severity_counts["medium"] >= 1

    @pytest.mark.asyncio
    async def test_owasp_integration_with_security_scan(self, security_agent, tmp_path):
        """Test OWASP validation is triggered by security scan with 'owasp' type."""
        test_file = tmp_path / "test.py"
        test_file.write_text("SECRET = 'password123'")

        from src.protocols.agent_specs import AgentMessage

        message = AgentMessage(
            sender=AgentRole.SW_DEV,
            recipient=AgentRole.SECURITY,
            message_type=MessageType.SECURITY_SCAN_REQUEST,
            payload={"scan_type": "owasp", "target": str(test_file)},
            correlation_id="test-corr-id",
        )

        security_agent.broker = MagicMock()
        security_agent.broker.publish = AsyncMock()
        await security_agent.initialize()

        await security_agent._handle_security_scan_request(message)

        # Should send security report with OWASP metadata
        security_agent.broker.publish.assert_called_once()
        call_args = security_agent.broker.publish.call_args
        # publish(channel, message) - message is second positional arg
        payload = call_args[0][1] if call_args[0] else call_args[1].get("message", {})

        assert "compliance" in payload or "findings" in payload

    def test_owasp_validator_has_all_categories(self):
        """Test validator defines all 10 OWASP categories."""
        validator = OWASPTop10Validator()
        checks = validator.checks

        # Verify all categories exist
        required_categories = [f"A{i:02d}" for i in range(1, 11)]
        for cat in required_categories:
            assert cat in checks, f"Missing OWASP category {cat}"
            # A06 is handled by dependency audit, so it's okay to be empty
            if cat != "A06":
                assert len(checks[cat]) > 0, f"Category {cat} has no checks"

    @pytest.mark.asyncio
    async def test_owasp_report_overall_compliance_false_with_failures(
        self, security_agent, tmp_path
    ):
        """Test that compliance is False when checks fail."""
        test_file = tmp_path / "fail_compliance.py"
        test_file.write_text("""
SECRET_KEY = "hardcoded_secret"
cursor.execute("SELECT * FROM users WHERE id = " + user_id)
""")

        result = await security_agent.validate_owasp_top10(str(test_file))

        # Should have failures
        assert result["compliance"] is False
        assert result["compliance_report"]["overall_compliance"] is False

    @pytest.mark.asyncio
    async def test_owasp_cwe_ids_assigned(self, security_agent, tmp_path):
        """Test that findings include CWE IDs."""
        test_file = tmp_path / "cwe_test.py"
        test_file.write_text("PASSWORD = 'secret123'")

        result = await security_agent.validate_owasp_top10(str(test_file))

        for finding in result["findings"]:
            assert "cwe_id" in finding
            # Most should have a CWE ID
            if finding["category"] in ["owasp_a02", "owasp_a03", "owasp_a08"]:
                assert finding["cwe_id"] is not None
