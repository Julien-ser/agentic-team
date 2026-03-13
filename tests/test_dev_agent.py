"""
Unit tests for SoftwareDevAgent.

Tests cover code generation, test generation, formatting, linting,
refactoring, and A2A message handling.
"""

import asyncio
import json
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.agents.dev_agent import SoftwareDevAgent
from src.protocols.agent_specs import (
    AgentRole,
    MessageType,
    Task,
    TaskStatus,
    ApiSpec,
    SecurityFinding,
)
from src.config import config


@pytest.fixture
def dev_agent():
    """Create a software dev agent instance."""
    agent = SoftwareDevAgent(agent_id="dev-agent-1")
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
def mock_openrouter():
    """Mock OpenRouter API calls."""
    with patch.object(SoftwareDevAgent, "_call_openrouter") as mock:

        async def mock_call(prompt):
            # Return sample code based on prompt content
            if "Generate a complete" in prompt:
                return '''from flask import Flask, request, jsonify
import os

app = Flask(__name__)

@app.route('/api/users', methods=['POST'])
def create_user():
    """Create a new user.

    Returns:
        JSON response with user data
    """
    data = request.get_json()
    if not data or 'email' not in data:
        return jsonify({'error': 'Invalid input'}), 400

    # TODO: Save user to database
    return jsonify({'id': 1, 'email': data['email']}), 201
'''
            elif "pytest" in prompt or "unit tests" in prompt:
                return '''import pytest
from flask import Flask

@pytest.fixture
def client():
    app = Flask(__name__)
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_create_user_success(client):
    """Test successful user creation."""
    response = client.post('/api/users', json={'email': 'test@example.com'})
    assert response.status_code in [200, 201]
    data = response.get_json()
    assert data is not None
'''
            elif "Refactor" in prompt or "vulnerabilities" in prompt.lower():
                return '''from flask import Flask, request, jsonify
import os

app = Flask(__name__)

@app.route('/api/users', methods=['POST'])
def create_user():
    """Create a new user.

    Returns:
        JSON response with user data
    """
    data = request.get_json()
    if not data or 'email' not in data:
        return jsonify({'error': 'Invalid input'}), 400

    # Fixed: Use parameterized query if database is added
    return jsonify({'id': 1, 'email': data['email']}), 201
'''
            elif "API specification" in prompt or "RESTful API" in prompt:
                return json.dumps(
                    {
                        "endpoint": "/api/v1/users",
                        "method": "POST",
                        "description": "Create a new user account",
                        "request_schema": {
                            "type": "object",
                            "properties": {
                                "email": {"type": "string"},
                                "password": {"type": "string"},
                            },
                            "required": ["email", "password"],
                        },
                        "response_schema": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "integer"},
                                "email": {"type": "string"},
                            },
                        },
                        "authentication_required": False,
                        "rate_limit": 100,
                    }
                )
            return ""

        mock.side_effect = mock_call
        yield mock


class TestDevAgentInitialization:
    """Test software dev agent initialization."""

    def test_get_role(self, dev_agent):
        """Test agent returns correct role."""
        assert dev_agent.get_role() == AgentRole.SW_DEV

    def test_init_with_defaults(self):
        """Test agent initialization with auto-generated ID."""
        agent = SoftwareDevAgent()
        assert agent.agent_id.startswith("software_developer-")
        assert agent.role == AgentRole.SW_DEV

    def test_init_with_custom_id(self):
        """Test agent initialization with custom ID."""
        agent = SoftwareDevAgent(agent_id="custom-dev")
        assert agent.agent_id == "custom-dev"

    @pytest.mark.asyncio
    async def test_initialize(self, dev_agent):
        """Test agent initialization."""
        await dev_agent.initialize()
        assert dev_agent._initialized is True
        assert dev_agent._start_time is not None

    @pytest.mark.asyncio
    async def test_register_handlers(self, dev_agent):
        """Test message handlers registration."""
        await dev_agent.initialize()

        assert MessageType.CODE_REVIEW_REQUEST in dev_agent._message_handlers
        assert MessageType.API_SPEC_REQUEST in dev_agent._message_handlers
        assert MessageType.SECURITY_ALERT in dev_agent._message_handlers


class TestCodeGeneration:
    """Test code generation functionality."""

    @pytest.mark.asyncio
    async def test_generate_code_with_spec(self, dev_agent, mock_openrouter):
        """Test generating code from specification."""
        spec = {
            "endpoint": "/api/users",
            "method": "POST",
            "description": "Create a new user",
            "authentication_required": False,
        }

        code = await dev_agent._generate_code(spec)

        assert code is not None
        assert len(code) > 0
        assert "@app.route" in code
        assert "def " in code

    @pytest.mark.asyncio
    async def test_generate_code_with_missing_api_key(self, dev_agent):
        """Test code generation fails gracefully when API key missing."""
        # Save original config
        original_key = config.OPENROUTER_API_KEY
        config.OPENROUTER_API_KEY = ""

        spec = {"endpoint": "/api/test", "method": "GET"}
        code = await dev_agent._generate_code(spec)

        # Should return fallback code
        assert code is not None
        assert "Not implemented" in code or "fallback" in code.lower()

        # Restore config
        config.OPENROUTER_API_KEY = original_key

    @pytest.mark.asyncio
    async def test_process_code_generation_task(self, dev_agent, mock_openrouter):
        """Test processing a code generation task."""
        task = Task(
            description="Generate API endpoint for user management",
            role=AgentRole.SW_DEV,
            payload={
                "spec": {
                    "endpoint": "/api/users",
                    "method": "POST",
                    "description": "Create a new user",
                },
                "generate_tests": True,
            },
        )

        result = await dev_agent.process_task(task)

        assert result["success"] is True
        assert "code" in result["output"]
        assert "tests" in result["output"]
        assert result["output"]["code"] is not None

    @pytest.mark.asyncio
    async def test_generate_fallback_code(self, dev_agent):
        """Test fallback code generation when AI is unavailable."""
        spec = {"endpoint": "/api/test", "method": "GET"}
        code = dev_agent._generate_fallback_code(spec)

        assert code is not None
        assert "501" in code or "Not implemented" in code


class TestTestGeneration:
    """Test pytest test generation."""

    @pytest.mark.asyncio
    async def test_generate_tests_with_code(self, dev_agent, mock_openrouter):
        """Test generating tests from code."""
        code = """
from flask import Flask
app = Flask(__name__)

@app.route('/api/hello')
def hello():
    return {"message": "Hello"}
"""
        tests = await dev_agent._generate_tests(code, {})

        assert len(tests) > 0
        assert "pytest" in tests[0] or "def test_" in tests[0]

    @pytest.mark.asyncio
    async def test_generate_tests_empty_code(self, dev_agent, mock_openrouter):
        """Test generating tests from empty code."""
        tests = await dev_agent._generate_tests("", {})

        # Should still return something (maybe empty or fallback)
        assert isinstance(tests, list)

    @pytest.mark.asyncio
    async def test_generate_fallback_tests(self, dev_agent):
        """Test fallback test template."""
        spec = {"endpoint": "/api/users"}
        tests = dev_agent._generate_fallback_tests(spec)

        assert "test_" in tests
        assert "pytest" in tests or "Flask" in tests

    @pytest.mark.asyncio
    async def test_process_test_generation_task(self, dev_agent, mock_openrouter):
        """Test processing a test generation task."""
        code = """
from flask import Flask
app = Flask(__name__)

@app.route('/api/test')
def test_endpoint():
    return {"status": "ok"}
"""
        task = Task(
            description="Generate tests for code",
            role=AgentRole.SW_DEV,
            payload={"code": code},
        )

        result = await dev_agent.process_task(task)

        assert result["success"] is True
        assert "tests" in result["output"]
        assert len(result["output"]["tests"]) > 0


class TestCodeFormatting:
    """Test code formatting with Black."""

    @pytest.mark.asyncio
    async def test_format_code_with_black(self, dev_agent):
        """Test formatting code with black."""
        # Code with bad formatting
        bad_code = """
def hello(  name):
    return {"message":"Hello "+name}
"""

        formatted = await dev_agent._format_code(bad_code)

        # Black might reformat or return something still valid
        assert formatted is not None
        assert isinstance(formatted, str)

    @pytest.mark.asyncio
    async def test_format_code_black_not_installed(self, dev_agent):
        """Test formatting when black is not available."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            code = "def test(): pass"
            formatted = await dev_agent._format_code(code)
            # Should return original code
            assert formatted == code

    @pytest.mark.asyncio
    async def test_format_code_black_timeout(self, dev_agent):
        """Test formatting when black times out."""
        with patch(
            "subprocess.run", side_effect=subprocess.TimeoutExpired("black", 30)
        ):
            code = "def test(): pass"
            formatted = await dev_agent._format_code(code)
            # Should return original code
            assert formatted == code

    @pytest.mark.asyncio
    async def test_process_format_task(self, dev_agent):
        """Test processing a formatting task."""
        code = "def test(  x):\n  return x*2"
        task = Task(
            description="Format code",
            role=AgentRole.SW_DEV,
            payload={"code": code},
        )

        result = await dev_agent.process_task(task)

        assert result["success"] is True
        assert "formatted_code" in result["output"]


class TestCodeLinting:
    """Test code linting with Ruff."""

    @pytest.mark.asyncio
    async def test_lint_code_with_ruff(self, dev_agent):
        """Test linting code with ruff."""
        # Code with potential issues
        code = """
import os
import sys

def unused_import(x):
    return x * 2
"""

        result = await dev_agent._lint_code(code)

        assert "tool" in result
        assert result["tool"] == "ruff"
        assert "violation_count" in result
        assert "success" in result

    @pytest.mark.asyncio
    async def test_lint_code_ruff_not_installed(self, dev_agent):
        """Test linting when ruff is not available."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            code = "def test(): pass"
            result = await dev_agent._lint_code(code)
            assert result["success"] is False
            assert "not installed" in result["error"]

    @pytest.mark.asyncio
    async def test_lint_code_ruff_timeout(self, dev_agent):
        """Test linting when ruff times out."""
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("ruff", 30)):
            code = "def test(): pass"
            result = await dev_agent._lint_code(code)
            assert result["success"] is False
            assert "timed out" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_process_lint_task(self, dev_agent):
        """Test processing a linting task."""
        code = "def test():\n    return 1+1"
        task = Task(
            description="Lint code",
            role=AgentRole.SW_DEV,
            payload={"code": code},
        )

        result = await dev_agent.process_task(task)

        assert result["success"] is True
        assert "lint_results" in result["output"]


class TestRefactoring:
    """Test code refactoring and security fixes."""

    @pytest.mark.asyncio
    async def test_refactor_code_with_vulnerabilities(self, dev_agent, mock_openrouter):
        """Test refactoring code to fix vulnerabilities."""
        vulnerable_code = """
AWS_KEY = "AKIAIOSFODNN7EXAMPLE"
PASSWORD = "secret123"

def get_user(user_id):
    query = f"SELECT * FROM users WHERE id = {user_id}"
    cursor.execute(query)
    return cursor.fetchall()
"""

        vulnerabilities = [
            {
                "category": "hardcoded_secret",
                "description": "Hardcoded AWS access key",
                "line_number": 1,
            },
            {
                "category": "sql_injection",
                "description": "SQL injection via f-string",
                "line_number": 5,
            },
        ]

        fixed_code = await dev_agent._refactor_code(vulnerable_code, vulnerabilities)

        assert fixed_code is not None
        assert (
            "TODO" in fixed_code
            or "os.environ" in fixed_code.lower()
            or fixed_code != vulnerable_code
        )

    @pytest.mark.asyncio
    async def test_refactor_code_ai_fails(self, dev_agent):
        """Test refactoring when AI call fails."""
        vulnerable_code = "AWS_KEY = 'secret123'"
        vulnerabilities = [{"category": "hardcoded_secret", "line_number": 1}]

        with patch.object(
            dev_agent, "_call_openrouter", side_effect=Exception("API error")
        ):
            fixed_code = await dev_agent._refactor_code(
                vulnerable_code, vulnerabilities
            )

        # Should apply manual fixes
        assert "TODO" in fixed_code or fixed_code == vulnerable_code

    @pytest.mark.asyncio
    async def test_apply_manual_fixes(self, dev_agent):
        """Test manual fix application."""
        code = "PASSWORD = 'secret123'\nAWS_KEY = 'AKIA123'"
        vulnerabilities = [
            {"category": "hardcoded_secret", "line_number": 1},
            {"category": "hardcoded_secret", "line_number": 2},
        ]

        fixed = dev_agent._apply_manual_fixes(code, vulnerabilities)

        assert "TODO" in fixed
        assert fixed.count("TODO") >= 2

    @pytest.mark.asyncio
    async def test_verify_security_fixes(self, dev_agent):
        """Test verification of security fixes."""
        original_vulns = [
            {"category": "hardcoded_secret", "description": "password"},
            {"category": "sql_injection", "description": "f-string SQL"},
        ]

        # Code with vulnerabilities still present
        code_with_vulns = "PASSWORD = 'secret'\ndef q(id): execute(f'SELECT * FROM users WHERE id = {id}')"

        result = await dev_agent._verify_security_fixes(code_with_vulns, original_vulns)

        assert "total_original" in result
        assert "fixed_count" in result
        assert "remaining" in result
        assert result["total_original"] == 2
        assert result["remaining"] > 0  # Still has issues

        # Code with vulnerabilities fixed
        fixed_code = (
            "import os\ndef q(id): execute('SELECT * FROM users WHERE id = ?', (id,))"
        )
        result2 = await dev_agent._verify_security_fixes(fixed_code, original_vulns)
        assert result2["remaining"] == 0 or result2["fixed_count"] > 0

    @pytest.mark.asyncio
    async def test_process_refactor_task(self, dev_agent, mock_openrouter):
        """Test processing a refactoring task."""
        vulnerable_code = """
API_KEY = "sk_test_123"
def query(user_id):
    sql = f"SELECT * FROM data WHERE id = {user_id}"
    cursor.execute(sql)
"""
        task = Task(
            description="Refactor code to fix security issues",
            role=AgentRole.SW_DEV,
            payload={
                "code": vulnerable_code,
                "vulnerabilities": [
                    {
                        "category": "hardcoded_secret",
                        "description": "Hardcoded API key",
                        "line_number": 1,
                    },
                    {
                        "category": "sql_injection",
                        "description": "SQL injection via f-string",
                        "line_number": 3,
                    },
                ],
            },
        )

        result = await dev_agent.process_task(task)

        assert result["success"] is True
        assert "original_code" in result["output"]
        assert "fixed_code" in result["output"]
        assert "verification" in result["output"]


class TestMessageHandlers:
    """Test A2A message handling."""

    @pytest.mark.asyncio
    async def test_handle_code_review_request(
        self, dev_agent, mock_broker, mock_openrouter
    ):
        """Test handling code review request."""
        code = "def test():\n    return 1+1"

        from src.protocols.agent_specs import AgentMessage

        message = AgentMessage(
            sender=AgentRole.SECURITY,
            recipient=AgentRole.SW_DEV,
            message_type=MessageType.CODE_REVIEW_REQUEST,
            payload={"code": code, "language": "python", "context": "API endpoint"},
            correlation_id="test-corr-123",
        )

        dev_agent.broker = mock_broker
        await dev_agent.initialize()

        await dev_agent._handle_code_review_request(message)

        # Should send response
        mock_broker.publish.assert_called()

    @pytest.mark.asyncio
    async def test_handle_api_spec_request(
        self, dev_agent, mock_broker, mock_openrouter
    ):
        """Test handling API spec request from frontend."""
        from src.protocols.agent_specs import AgentMessage

        message = AgentMessage(
            sender=AgentRole.FRONTEND,
            recipient=AgentRole.SW_DEV,
            message_type=MessageType.API_SPEC_REQUEST,
            payload={
                "component_name": "UserList",
                "requirements": ["list users", "pagination", "filter by email"],
            },
            correlation_id="test-corr-456",
        )

        dev_agent.broker = mock_broker
        await dev_agent.initialize()

        await dev_agent._handle_api_spec_request(message)

        # Should send API_SPEC_RESPONSE
        mock_broker.publish.assert_called()
        call_args = mock_broker.publish.call_args
        sent_message = (
            call_args[0][1] if len(call_args[0]) > 1 else call_args[1]["message"]
        )
        assert sent_message["message_type"] == MessageType.API_SPEC_RESPONSE
        assert "api_spec" in sent_message["payload"]

    @pytest.mark.asyncio
    async def test_handle_security_alert_with_code_path(
        self, dev_agent, mock_broker, tmp_path
    ):
        """Test handling security alert with file path."""
        # Create a vulnerable file
        test_file = tmp_path / "vuln.py"
        test_file.write_text("PASSWORD = 'secret123'\ndef query(id): return id")

        from src.protocols.agent_specs import AgentMessage

        message = AgentMessage(
            sender=AgentRole.SECURITY,
            recipient=AgentRole.SW_DEV,
            message_type=MessageType.SECURITY_ALERT,
            payload={
                "findings": [
                    {
                        "category": "hardcoded_secret",
                        "description": "Hardcoded password",
                        "line_number": 1,
                    }
                ],
                "message": "Critical vulnerability found",
                "severity": "high",
                "code_path": str(test_file),
            },
            correlation_id="test-corr-789",
        )

        dev_agent.broker = mock_broker
        await dev_agent.initialize()

        # Mock refactor to avoid AI dependency
        with patch.object(dev_agent, "_refactor_code", return_value="FIXED CODE"):
            with patch.object(
                dev_agent,
                "_verify_security_fixes",
                return_value={
                    "total_original": 1,
                    "fixed_count": 1,
                    "remaining": 0,
                    "success": True,
                },
            ):
                await dev_agent._handle_security_alert(message)

        # Should send TASK_UPDATE response to Security agent
        mock_broker.publish.assert_called()

    @pytest.mark.asyncio
    async def test_handle_security_alert_without_code_path(
        self, dev_agent, mock_broker
    ):
        """Test handling security alert without file path."""
        from src.protocols.agent_specs import AgentMessage

        message = AgentMessage(
            sender=AgentRole.SECURITY,
            recipient=AgentRole.SW_DEV,
            message_type=MessageType.SECURITY_ALERT,
            payload={
                "findings": [],
                "message": "General alert",
                "severity": "medium",
            },
            correlation_id="test-corr-999",
        )

        dev_agent.broker = mock_broker
        await dev_agent.initialize()

        # Should not crash, just log warning
        await dev_agent._handle_security_alert(message)

        # Should not send response since no code_path
        # mock_broker.publish might still be called for other reasons, so we don't assert call count

    @pytest.mark.asyncio
    async def test_design_api_spec_with_ai(self, dev_agent, mock_openrouter):
        """Test designing API spec with AI."""
        spec = await dev_agent._design_api_spec(
            "UserLogin", ["email", "password", "JWT token"]
        )

        assert isinstance(spec, ApiSpec)
        assert spec.endpoint is not None
        assert spec.method in ["GET", "POST", "PUT", "DELETE"]
        assert spec.description is not None

    @pytest.mark.asyncio
    async def test_design_api_spec_fallback(self, dev_agent):
        """Test API spec fallback when AI fails."""
        with patch.object(
            dev_agent, "_call_openrouter", side_effect=Exception("API error")
        ):
            spec = await dev_agent._design_api_spec("TestComponent", ["feature1"])

        assert isinstance(spec, ApiSpec)
        assert "testcomponent" in spec.endpoint.lower()
        assert spec.method == "GET"  # Default fallback

    @pytest.mark.asyncio
    async def test_auto_fix_success(self, dev_agent, tmp_path, mock_openrouter):
        """Test automatic vulnerability fix."""
        test_file = tmp_path / "vuln.py"
        test_file.write_text("PASSWORD = 'secret123'")

        result = await dev_agent._attempt_auto_fix(
            str(test_file), [{"category": "hardcoded_secret", "line_number": 1}]
        )

        assert result["attempted"] is True
        assert result["successful"] is True
        assert result["fixed_count"] >= 1

        # Check file was modified (content changed, not contains secret)
        content = test_file.read_text()
        assert "PASSWORD = 'secret123'" not in content

    @pytest.mark.asyncio
    async def test_auto_fix_file_not_found(self, dev_agent):
        """Test auto fix with nonexistent file."""
        result = await dev_agent._attempt_auto_fix(
            "/nonexistent/file.py", [{"category": "hardcoded_secret"}]
        )

        assert result["attempted"] is False
        assert result["successful"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_auto_fix_with_ai_failure(self, dev_agent, tmp_path):
        """Test auto fix when AI fails."""
        test_file = tmp_path / "vuln.py"
        test_file.write_text("PASSWORD = 'secret123'")

        with patch.object(
            dev_agent, "_call_openrouter", side_effect=Exception("AI error")
        ):
            result = await dev_agent._attempt_auto_fix(
                str(test_file), [{"category": "hardcoded_secret", "line_number": 1}]
            )

        assert result["attempted"] is True
        # Manual fix adds TODO comment but doesn't actually fix the vulnerability pattern
        # So verification will report it's not fully successful
        assert result["successful"] is False
        assert result["fixed_count"] == 0  # Pattern still present


class TestHealthCheck:
    """Test health check functionality."""

    @pytest.mark.asyncio
    async def test_health_check(self, dev_agent):
        """Test health check returns dev agent specific info."""
        dev_agent._running = True
        dev_agent._initialized = True
        dev_agent._start_time = datetime.utcnow()

        health = await dev_agent.health_check()

        assert health["healthy"] is True
        assert "tools_available" in health
        assert "black" in health["tools_available"]
        assert "ruff" in health["tools_available"]
        assert "openrouter" in health["tools_available"]

    @pytest.mark.asyncio
    async def test_check_tool_available(self, dev_agent):
        """Test checking tool availability."""
        # black should be installed from requirements.txt
        available = dev_agent._check_tool("black")
        # Depends on system, just verify it returns bool
        assert isinstance(available, bool)

    @pytest.mark.asyncio
    async def test_check_tool_not_available(self, dev_agent):
        """Test checking unavailable tool."""
        available = dev_agent._check_tool("nonexistent_tool_xyz")
        assert available is False


class TestTaskProcessing:
    """Test different task processing scenarios."""

    @pytest.mark.asyncio
    async def test_process_generate_task(self, dev_agent, mock_openrouter):
        """Test processing a generate task."""
        task = Task(
            description="Generate Python code for user authentication",
            role=AgentRole.SW_DEV,
            payload={"spec": {"endpoint": "/api/auth/login", "method": "POST"}},
        )

        result = await dev_agent.process_task(task)

        assert result["success"] is True
        assert "code" in result["output"]
        assert result["output"]["spec_used"] is not None

    @pytest.mark.asyncio
    async def test_process_test_task(self, dev_agent, mock_openrouter):
        """Test processing a test generation task."""
        task = Task(
            description="Write tests for authentication module",
            role=AgentRole.SW_DEV,
            payload={"code": "def login():\n    return True"},
        )

        result = await dev_agent.process_task(task)

        assert result["success"] is True
        assert "tests" in result["output"]

    @pytest.mark.asyncio
    async def test_process_refactor_task(self, dev_agent, mock_openrouter):
        """Test processing a refactor task."""
        task = Task(
            description="Refactor code to be more secure",
            role=AgentRole.SW_DEV,
            payload={
                "code": "API_KEY = 'secret123'",
                "vulnerabilities": [{"category": "hardcoded_secret", "line_number": 1}],
            },
        )

        result = await dev_agent.process_task(task)

        assert result["success"] is True
        assert "original_code" in result["output"]
        assert "fixed_code" in result["output"]

    @pytest.mark.asyncio
    async def test_process_format_task(self, dev_agent):
        """Test processing a format task."""
        task = Task(
            description="Format this code",
            role=AgentRole.SW_DEV,
            payload={"code": "def test(  a,b  ):  return a+b"},
        )

        result = await dev_agent.process_task(task)

        assert result["success"] is True
        assert "formatted_code" in result["output"]

    @pytest.mark.asyncio
    async def test_process_lint_task(self, dev_agent):
        """Test processing a lint task."""
        task = Task(
            description="Lint this code",
            role=AgentRole.SW_DEV,
            payload={"code": "import os,sys\ndef test():\n    pass"},
        )

        result = await dev_agent.process_task(task)

        assert result["success"] is True
        assert "lint_results" in result["output"]

    @pytest.mark.asyncio
    async def test_process_unknown_task_type(self, dev_agent, mock_openrouter):
        """Test processing task with unclear type."""
        task = Task(
            description="Do something mysterious",
            role=AgentRole.SW_DEV,
            payload={},
        )

        result = await dev_agent.process_task(task)

        assert result["success"] is True
        assert "task_type" in result["output"]

    @pytest.mark.asyncio
    async def test_process_task_with_exception(self, dev_agent):
        """Test task processing with exception."""
        task = Task(
            description="Invalid task that will fail",
            role=AgentRole.SW_DEV,
            payload={"spec": {"endpoint": "/api/test"}},
        )

        with patch.object(
            dev_agent, "_generate_code", side_effect=Exception("Test error")
        ):
            with pytest.raises(Exception):
                await dev_agent.process_task(task)


class TestIntegration:
    """Integration tests for full workflows."""

    @pytest.mark.asyncio
    async def test_full_generate_format_lint_workflow(self, dev_agent, mock_openrouter):
        """Test workflow: generate -> format -> lint."""
        # Generate code
        spec = {
            "endpoint": "/api/test",
            "method": "GET",
            "description": "Test endpoint",
        }
        code = await dev_agent._generate_code(spec)
        assert code is not None

        # Format code
        formatted = await dev_agent._format_code(code)
        assert formatted is not None

        # Lint formatted code
        lint_result = await dev_agent._lint_code(formatted)
        assert "tool" in lint_result
        assert "violation_count" in lint_result

    @pytest.mark.asyncio
    async def test_code_review_workflow(self, dev_agent, mock_broker, mock_openrouter):
        """Test code review workflow via A2A."""
        code = """def insecure_function():
    exec(user_input)
"""

        from src.protocols.agent_specs import AgentMessage

        message = AgentMessage(
            sender=AgentRole.FRONTEND,
            recipient=AgentRole.SW_DEV,
            message_type=MessageType.CODE_REVIEW_REQUEST,
            payload={"code": code, "language": "python"},
            correlation_id="review-123",
        )

        dev_agent.broker = mock_broker
        await dev_agent.initialize()

        await dev_agent._handle_code_review_request(message)

        # Check that response was sent with findings
        assert mock_broker.publish.called
        # Could add more assertions about the response content

    @pytest.mark.asyncio
    async def test_api_spec_to_code_workflow(
        self, dev_agent, mock_broker, mock_openrouter
    ):
        """Test workflow: frontend requests spec, backend generates code."""
        from src.protocols.agent_specs import AgentMessage

        # Frontend sends API_SPEC_REQUEST
        request_msg = AgentMessage(
            sender=AgentRole.FRONTEND,
            recipient=AgentRole.SW_DEV,
            message_type=MessageType.API_SPEC_REQUEST,
            payload={
                "component_name": "ProductList",
                "requirements": [
                    "list products",
                    "filter by category",
                    "sort by price",
                ],
            },
            correlation_id="spec-123",
        )

        dev_agent.broker = mock_broker
        await dev_agent.initialize()

        await dev_agent._handle_api_spec_request(request_msg)

        # Should send API_SPEC_RESPONSE
        assert mock_broker.publish.called
        # In real scenario, frontend would then use spec and request code generation
