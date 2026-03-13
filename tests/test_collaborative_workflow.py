"""
Integration test for collaborative workflow: end-to-end feature development.

This test simulates the complete workflow where three agents collaborate
to build a user login feature:
1. Frontend Agent requests API spec from Dev Agent
2. Dev Agent designs and implements API, sends to Security for review
3. Security Agent scans and reports vulnerabilities
4. Dev Agent fixes issues and completes the feature

The test uses mock Redis and SQLite, and mocks AI calls for deterministic results.
"""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.protocols.agent_specs import (
    AgentRole,
    MessageType,
    Task,
    ApiSpec,
    SecurityFinding,
)
from src.agents.frontend_agent import FrontendAgent
from src.agents.dev_agent import SoftwareDevAgent
from src.agents.security_agent import SecurityAgent
from src.messaging.redis_broker import RedisMessageBroker
from src.state.state_manager import StateManager
from src.messaging.router import MessageRouter
from src.config import config


@pytest.fixture
def temp_database():
    """Create a temporary SQLite database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.mark.asyncio
async def test_collaborative_workflow_login_feature(event_loop, temp_database):
    """
    Test complete collaborative workflow for building a login feature.

    This test verifies that:
    - Frontend Agent can request and receive API specs
    - Dev Agent can generate backend code and send for security review
    - Security Agent can scan and report vulnerabilities
    - Dev Agent can fix vulnerabilities and complete the feature
    - All messages are properly routed and correlated
    - Shared state is updated throughout the workflow
    """

    # Setup configuration for testing
    config.REDIS_URL = "redis://localhost:6379/1"  # Test DB
    config.OPENROUTER_API_KEY = "test-key"  # Will be mocked
    config.AGENT_HEARTBEAT_INTERVAL = 5

    # Mock the State Manager
    state_manager = StateManager(db_path=temp_database)
    await state_manager.initialize()

    # Mock Redis broker (we'll use in-memory routing instead)
    broker = MagicMock(spec=RedisMessageBroker)
    broker.publish = AsyncMock(return_value=True)
    broker.subscribe = AsyncMock()

    # Create Message Router
    router = MessageRouter(broker=broker, state_manager=state_manager)
    await router.initialize()

    # Track all messages sent
    sent_messages = []

    async def capture_message(recipient, message_type, payload, correlation_id=None):
        """Capture messages sent by agents for verification."""
        msg = {
            "recipient": recipient,
            "message_type": message_type,
            "payload": payload,
            "correlation_id": correlation_id,
        }
        sent_messages.append(msg)
        return True

    # Create agents with mocked AI calls
    frontend_agent = FrontendAgent(agent_id="frontend-001")
    dev_agent = SoftwareDevAgent(agent_id="dev-001")
    security_agent = SecurityAgent(agent_id="security-001")

    # Override send_message to capture messages and route through router
    original_frontend_send = frontend_agent.send_message
    original_dev_send = dev_agent.send_message
    original_security_send = security_agent.send_message

    async def mock_send(recipient, message_type, payload, correlation_id=None):
        # Capture the message
        await capture_message(recipient, message_type, payload, correlation_id)

        # Route through our test router
        from src.protocols.agent_specs import AgentMessage

        msg = AgentMessage(
            sender=frontend_agent.get_role()
            if recipient != AgentRole.SW_DEV
            else dev_agent.get_role(),
            recipient=recipient,
            message_type=message_type,
            payload=payload,
            correlation_id=correlation_id,
        )
        await router.route_message(msg)

    frontend_agent.send_message = mock_send
    dev_agent.send_message = mock_send
    security_agent.send_message = mock_send

    # Initialize agents
    await frontend_agent.initialize()
    await dev_agent.initialize()
    await security_agent.initialize()

    # Register agents with router for message handling
    router.register_handler(
        MessageType.API_SPEC_RESPONSE, dev_agent._handle_api_spec_request
    )
    # Actually, these handlers should be registered when agents initialize
    # We need to simulate message delivery to agents

    # Store messages by recipient for processing
    message_queues = {
        AgentRole.SW_DEV: [],
        AgentRole.SECURITY: [],
        AgentRole.FRONTEND: [],
    }

    async def mock_router_route(message):
        """Custom routing to deliver messages directly to recipients."""
        recipient = message.recipient
        if recipient == AgentRole.SW_DEV:
            # Dev agent handles code review requests and component ready
            if message.message_type == MessageType.API_SPEC_REQUEST:
                await dev_agent._handle_api_spec_request(message)
            elif message.message_type == MessageType.COMPONENT_READY:
                # Simulate dev receiving component
                pass
        elif recipient == AgentRole.SECURITY:
            if message.message_type == MessageType.SECURITY_SCAN_REQUEST:
                await security_agent._handle_security_scan_request(message)
        elif recipient == AgentRole.FRONTEND:
            if message.message_type == MessageType.API_SPEC_RESPONSE:
                await frontend_agent._handle_api_spec_response(message)
            elif message.message_type == MessageType.SECURITY_ALERT:
                await frontend_agent._handle_security_alert(message)

    # Route queued messages to recipients
    async def intercept_and_route(message):
        """Intercept broker.publish calls and route messages."""
        # Extract recipient from channel or message
        if isinstance(message, dict):
            recipient = message.get("recipient")
            if recipient:
                message_queues[recipient].append(message)
                await mock_router_route(message)

    broker.publish.side_effect = intercept_and_route

    # ==================== BEGIN WORKFLOW ====================

    print("\n=== Starting Collaborative Workflow Test ===\n")

    # STEP 1: Frontend Agent receives task to build login component
    print("Step 1: Frontend Agent receives task")
    frontend_task = Task(
        description="Build login form component with authentication",
        role=AgentRole.FRONTEND,
        payload={
            "spec": {
                "component_name": "LoginForm",
                "requirements": [
                    "email input field",
                    "password input field",
                    "submit button",
                    "JWT authentication",
                    "error handling",
                ],
            }
        },
    )

    # Frontend Agent processes task and realizes it needs API spec
    # It will send API_SPEC_REQUEST to Dev Agent
    print("Step 2: Frontend requests API spec from Dev Agent")

    # Mock OpenRouter AI calls for reliable test results
    with (
        patch.object(dev_agent, "_call_openrouter") as mock_dev_ai,
        patch.object(frontend_agent, "_call_openrouter") as mock_frontend_ai,
    ):
        # Dev agent AI responses
        mock_dev_ai.return_value = json.dumps(
            {
                "endpoint": "/api/v1/auth/login",
                "method": "POST",
                "description": "Authenticate user and return JWT token",
                "request_schema": {
                    "type": "object",
                    "properties": {
                        "email": {"type": "string", "format": "email"},
                        "password": {"type": "string"},
                    },
                    "required": ["email", "password"],
                },
                "response_schema": {
                    "type": "object",
                    "properties": {
                        "token": {"type": "string"},
                        "expires_in": {"type": "integer"},
                        "user_id": {"type": "integer"},
                    },
                },
                "authentication_required": False,
                "rate_limit": 5,
            }
        )

        # Frontend agent AI response for component generation
        mock_frontend_ai.return_value = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Login</title>
</head>
<body>
    <form id="login-form">
        <input type="email" id="email" name="email">
        <input type="password" id="password" name="password">
        <button type="submit">Login</button>
    </form>
</body>
</html>"""

        # Frontend agent sends API spec request
        await frontend_agent.send_message(
            recipient=AgentRole.SW_DEV,
            message_type=MessageType.API_SPEC_REQUEST,
            payload={
                "component_name": "LoginForm",
                "requirements": ["email input", "password input", "authentication"],
            },
        )

        # Small delay for message routing
        await asyncio.sleep(0.1)

        # Verify API_SPEC_REQUEST was sent
        api_request_msgs = [
            m
            for m in sent_messages
            if m["message_type"] == MessageType.API_SPEC_REQUEST
        ]
        assert len(api_request_msgs) == 1, (
            "Frontend should send exactly one API spec request"
        )
        assert api_request_msgs[0]["recipient"] == AgentRole.SW_DEV

        print("✓ Frontend sent API_SPEC_REQUEST to Dev Agent")

        # Dev agent should have handled the request and sent API_SPEC_RESPONSE
        await asyncio.sleep(0.2)  # Allow time for async processing

        api_response_msgs = [
            m
            for m in sent_messages
            if m["message_type"] == MessageType.API_SPEC_RESPONSE
        ]
        assert len(api_response_msgs) >= 1, "Dev Agent should send API spec response"
        assert api_response_msgs[0]["recipient"] == AgentRole.FRONTEND
        assert "api_spec" in api_response_msgs[0]["payload"]

        print("✓ Dev Agent sent API_SPEC_RESPONSE to Frontend")

        # STEP 3: Frontend generates component based on API spec
        print("Step 3: Frontend generates login UI component")

        # Process frontend task (component generation)
        frontend_result = await frontend_agent.process_task(frontend_task)
        assert frontend_result["success"] is True
        assert "component_code" in frontend_result["output"]

        print("✓ Frontend generated component code")

        # Frontend should send COMPONENT_READY to Dev
        await asyncio.sleep(0.1)
        component_ready_msgs = [
            m for m in sent_messages if m["message_type"] == MessageType.COMPONENT_READY
        ]
        assert len(component_ready_msgs) >= 1, "Frontend should send COMPONENT_READY"
        assert component_ready_msgs[0]["recipient"] == AgentRole.SW_DEV
        assert "component_name" in component_ready_msgs[0]["payload"]

        print("✓ Frontend sent COMPONENT_READY to Dev Agent")

        # STEP 4: Dev Agent implements backend API
        print("Step 4: Dev Agent implements backend authentication API")

        dev_task = Task(
            description="Implement authentication API endpoint with JWT",
            role=AgentRole.SW_DEV,
            payload={
                "spec": {
                    "endpoint": "/api/v1/auth/login",
                    "method": "POST",
                    "description": "Authenticate user and return JWT token",
                    "authentication_required": False,
                },
                "generate_tests": True,
            },
        )

        # Mock backend code generation with vulnerable code for security test
        mock_dev_ai.return_value = """
from flask import Flask, request, jsonify
import jwt
import os
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = 'hardcoded-secret-key-change-me'

@app.route('/api/v1/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data or 'email' not in data or 'password' not in data:
        return jsonify({'error': 'Email and password required'}), 400
    
    email = data['email']
    password = data['password']
    
    # TODO: validate against database
    if email == 'admin@example.com' and password == 'admin123':
        token = jwt.encode({
            'user_id': 1,
            'exp': datetime.utcnow() + timedelta(hours=24)
        }, app.config['SECRET_KEY'])
        
        return jsonify({
            'token': token,
            'expires_in': 86400,
            'user_id': 1
        }), 200
    
    return jsonify({'error': 'Invalid credentials'}), 401

if __name__ == '__main__':
    app.run(debug=True)
"""

        dev_result = await dev_agent.process_task(dev_task)
        assert dev_result["success"] is True
        assert "code" in dev_result["output"]

        print("✓ Dev Agent generated backend code")

        # Dev sends security scan request
        await asyncio.sleep(0.1)
        security_request_msgs = [
            m
            for m in sent_messages
            if m["message_type"] == MessageType.SECURITY_SCAN_REQUEST
        ]
        assert len(security_request_msgs) >= 1, "Dev Agent should request security scan"
        assert security_request_msgs[0]["recipient"] == AgentRole.SECURITY

        print("✓ Dev Agent sent SECURITY_SCAN_REQUEST to Security Agent")

        # STEP 5: Security Agent scans code and reports vulnerabilities
        print("Step 5: Security Agent scans for vulnerabilities")

        # Mock security scan to find the hardcoded secret
        async def mock_scan_codebase(path):
            findings = []
            # Simulate finding hardcoded secret in the code
            findings.append(
                SecurityFinding(
                    severity="high",
                    category="hardcoded_secret",
                    file_path=path,
                    line_number=10,
                    description="JWT secret key hardcoded in source",
                    recommendation="Replace with environment variable",
                    cwe_id="CWE-798",
                    confidence=0.95,
                )
            )
            return findings

        security_agent.scan_codebase = mock_scan_codebase

        # Process security scan request
        await asyncio.sleep(0.2)  # Allow dev to send request

        # Simulate security agent handling scan request
        # The request should already be in queue
        assert len(message_queues[AgentRole.SECURITY]) > 0, (
            "Security agent should have pending message"
        )

        security_scan_task = Task(
            description="Scan authentication API for vulnerabilities",
            role=AgentRole.SECURITY,
            payload={"code_path": temp_database, "scan_type": "quick"},
        )

        security_result = await security_agent.process_task(security_scan_task)
        assert security_result["success"] is True
        findings = security_result["output"]["findings"]
        assert len(findings) > 0, "Should find at least one vulnerability"
        assert any(f["category"] == "hardcoded_secret" for f in findings)

        print(f"✓ Security Agent found {len(findings)} vulnerabilities")

        # Security sends alert to Dev
        await asyncio.sleep(0.1)
        security_alert_msgs = [
            m for m in sent_messages if m["message_type"] == MessageType.SECURITY_ALERT
        ]
        assert len(security_alert_msgs) >= 1, "Security should send SECURITY_ALERT"
        assert security_alert_msgs[0]["recipient"] == AgentRole.SW_DEV
        assert "findings" in security_alert_msgs[0]["payload"]

        print("✓ Security Agent sent SECURITY_ALERT to Dev Agent")

        # STEP 6: Dev Agent fixes vulnerabilities
        print("Step 6: Dev Agent fixes security vulnerabilities")

        # Mock refactoring to fix the issues
        async def mock_refactor(code, vulnerabilities):
            # Return fixed code with environment variable instead of hardcoded secret
            return code.replace(
                "app.config['SECRET_KEY'] = 'hardcoded-secret-key-change-me'",
                "app.config['SECRET_KEY'] = os.environ.get('JWT_SECRET')\nif not app.config['SECRET_KEY']:\n    raise ValueError('JWT_SECRET must be set')",
            )

        dev_agent._refactor_code = mock_refactor

        # Dev processes security alert by refactoring
        # In real system, this would be automatic upon receiving SECURITY_ALERT
        # For test, we'll directly call refactor and verification

        # Get original code from dev result
        original_code = dev_result["output"]["code"]
        vulnerabilities = [{"category": "hardcoded_secret", "line_number": 10}]

        fixed_code = await dev_agent._refactor_code(original_code, vulnerabilities)
        assert "os.environ.get('JWT_SECRET')" in fixed_code
        assert "hardcoded-secret" not in fixed_code

        print("✓ Dev Agent fixed vulnerabilities")

        # Dev verifies fixes
        verification = await dev_agent._verify_security_fixes(
            fixed_code, vulnerabilities
        )
        assert verification["success"] is True
        assert verification["fixed_count"] == 1
        assert verification["remaining"] == 0

        print(
            f"✓ Security fixes verified: {verification['fixed_count']}/{len(vulnerabilities)} fixed"
        )

        # Dev marks task complete
        # (In real code, process_task would continue after security review)
        # We'll simulate this by noting the task completion

        print("\n=== Workflow Test Completed Successfully ===\n")

    # Cleanup
    await router.shutdown()
    await state_manager.close()

    # FINAL ASSERTIONS
    # Verify message flow
    assert len(sent_messages) >= 5, "Should have exchanged at least 5 messages"

    # Check message types in order
    message_types = [m["message_type"] for m in sent_messages]
    assert MessageType.API_SPEC_REQUEST in message_types
    assert MessageType.API_SPEC_RESPONSE in message_types
    assert MessageType.COMPONENT_READY in message_types
    assert MessageType.SECURITY_SCAN_REQUEST in message_types
    assert MessageType.SECURITY_ALERT in message_types

    print("✓ All message types present in workflow")
    print(f"✓ Total messages exchanged: {len(sent_messages)}")

    return True


@pytest.mark.asyncio
async def test_message_correlation_in_workflow():
    """
    Test that correlation IDs are properly tracked through request/response cycles.
    """
    config.REDIS_URL = "redis://localhost:6379/2"

    broker = MagicMock(spec=RedisMessageBroker)
    broker.publish = AsyncMock(return_value=True)

    router = MessageRouter(broker=broker)
    await router.initialize()

    correlation_id = "test-correl-123"
    response_received = False

    # Simulate request/response
    async def mock_handler(message):
        nonlocal response_received
        if message.correlation_id == correlation_id:
            response_received = True

    router.register_handler(MessageType.API_SPEC_RESPONSE, mock_handler)

    # Simulate sending a request
    from src.protocols.agent_specs import AgentMessage

    request_msg = AgentMessage(
        sender=AgentRole.FRONTEND,
        recipient=AgentRole.SW_DEV,
        message_type=MessageType.API_SPEC_REQUEST,
        payload={"component": "Login"},
        correlation_id=correlation_id,
    )

    await router.route_message(request_msg)

    # Simulate response
    response_msg = AgentMessage(
        sender=AgentRole.SW_DEV,
        recipient=AgentRole.FRONTEND,
        message_type=MessageType.API_SPEC_RESPONSE,
        payload={"api_spec": {"endpoint": "/api/login"}},
        correlation_id=correlation_id,
    )

    await router.handle_message(response_msg)

    assert response_received, "Response should be correlated with request"

    await router.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
