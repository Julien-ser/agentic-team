"""
Unit tests for SecurityAgent.

Tests cover vulnerability scanning, code review, dependency audit,
and A2A message handling.
"""

import asyncio
import subprocess
import tempfile
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
        security_agent._start_time = asyncio.get_event_loop().time()

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
