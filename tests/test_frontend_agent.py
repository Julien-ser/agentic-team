"""
Unit tests for FrontendAgent.

Tests cover component generation, responsive design, accessibility,
API integration, and A2A message handling.
"""

import asyncio
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.agents.frontend_agent import FrontendAgent
from src.protocols.agent_specs import (
    AgentRole,
    MessageType,
    Task,
    ApiSpec,
)
from src.config import config


@pytest.fixture
def frontend_agent():
    """Create a frontend agent instance."""
    agent = FrontendAgent(agent_id="frontend-agent-1")
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
    with patch.object(FrontendAgent, "_call_openrouter") as mock:

        async def mock_call(prompt):
            # Extract component name from prompt if present
            import re

            component_name_match = re.search(r"named '([^']+)'", prompt)
            component_name = (
                component_name_match.group(1) if component_name_match else "Component"
            )

            # Return sample code based on prompt content
            if "Create a modern, production-ready frontend component" in prompt:
                # Return component with name and API fetch integration
                template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{component_name}</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-50 min-h-screen p-4">
    <main class="max-w-4xl mx-auto">
        <div class="bg-white rounded-lg shadow p-6 mt-8">
            <h1 class="text-2xl font-bold text-gray-900 mb-4">{component_name}</h1>
            <div id="loading" class="hidden">Loading...</div>
            <div id="error" class="bg-red-100 p-3 rounded hidden"></div>
            <ul id="dataList" class="space-y-2"></ul>
        </div>
    </main>
    <script>
        async function loadData() {{
            const loading = document.getElementById('loading');
            const error = document.getElementById('error');
            const list = document.getElementById('dataList');

            loading.classList.remove('hidden');
            error.classList.add('hidden');
            list.innerHTML = '';

            try {{
                const token = localStorage.getItem('jwt_token');
                const response = await fetch('/api/v1/data', {{
                    method: 'GET',
                    headers: {{
                        'Content-Type': 'application/json',
                        'Authorization': token ? 'Bearer ' + token : ''
                    }}
                }});

                if (!response.ok) {{
                    throw new Error('HTTP ' + response.status + ': ' + response.statusText);
                }}

                const data = await response.json();
                const items = Array.isArray(data) ? data : data.items || [];

                items.forEach(item => {{
                    const li = document.createElement('li');
                    li.className = 'p-3 border rounded';
                    li.textContent = item.name || item.title || JSON.stringify(item);
                    list.appendChild(li);
                }});

                if (items.length === 0) {{
                    list.innerHTML = '<li class="p-3 text-gray-500">No items found</li>';
                }}
            }} catch (err) {{
                error.textContent = 'Error: ' + err.message;
                error.classList.remove('hidden');
            }} finally {{
                loading.classList.add('hidden');
            }}
        }}

        document.addEventListener('DOMContentLoaded', loadData);
    </script>
</body>
</html>"""
                return template.format(component_name=component_name)
            elif "enhance it to be fully responsive" in prompt:
                return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ResponsiveComponent</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-50 min-h-screen p-4">
    <main class="max-w-4xl mx-auto">
        <div class="bg-white rounded-lg shadow p-4 md:p-6 mt-4 md:mt-8">
            <h1 class="text-xl md:text-2xl font-bold text-gray-900 mb-2 md:mb-4">Responsive Component</h1>
            <form id="testForm" class="space-y-4">
                <div>
                    <label for="email" class="block text-sm font-medium text-gray-700">Email</label>
                    <input 
                        type="email" 
                        id="email" 
                        name="email"
                        class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
                        aria-label="Email address"
                        required
                    >
                </div>
                <button 
                    type="submit"
                    class="w-full sm:w-auto bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded"
                    aria-label="Submit form"
                >
                    Submit
                </button>
            </form>
        </div>
    </main>
</body>
</html>"""
            elif "Create a comprehensive style guide" in prompt:
                import json
                import re

                # Extract component list from prompt (similar to test parsing)
                components = []
                lines = prompt.split("\n")
                in_components_section = False
                for line in lines:
                    if "Components:" in line:
                        in_components_section = True
                    elif in_components_section:
                        line = line.strip()
                        if line.startswith("-"):
                            comp = line[1:].strip()
                            if comp:
                                components.append(comp)
                        elif line and not line.startswith("-"):
                            break

                return json.dumps(
                    {
                        "colors": {
                            "primary": "#3B82F6",
                            "secondary": "#10B981",
                            "accent": "#F59E0B",
                            "neutral": "#6B7280",
                            "background": "#FFFFFF",
                        },
                        "typography": {
                            "font_family": "system-ui, -apple-system, sans-serif",
                            "heading_1": "2.25rem / 2.5rem",
                            "body": "1rem / 1.5rem",
                        },
                        "spacing": {"xs": "0.25rem", "sm": "0.5rem", "md": "1rem"},
                        "components": components,  # Add the required components key
                    }
                )
            elif "Review the following" in prompt:
                return """[
    {
        "severity": "high",
        "category": "accessibility",
        "description": "Form inputs may be missing labels",
        "recommendation": "Ensure all inputs have associated labels",
        "line_number": 15
    },
    {
        "severity": "medium",
        "category": "security",
        "description": "Using innerHTML can lead to XSS",
        "recommendation": "Use textContent or safe DOM methods",
        "line_number": 42
    }
]"""
            elif "Add API integration" in prompt:
                return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>APIIntegration</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-50 p-4">
    <main class="max-w-4xl mx-auto">
        <div class="bg-white rounded-lg shadow p-6">
            <h1 class="text-2xl font-bold mb-4">User List</h1>
            <div id="loading" class="hidden">Loading users...</div>
            <div id="error" class="bg-red-100 p-3 rounded hidden"></div>
            <ul id="userList" class="space-y-2"></ul>
        </div>
    </main>
    <script>
        async function loadUsers() {{
            const loading = document.getElementById('loading');
            const error = document.getElementById('error');
            const userList = document.getElementById('userList');

            loading.classList.remove('hidden');
            error.classList.add('hidden');
            userList.innerHTML = '';

            try {{
                const token = localStorage.getItem('jwt_token');
                const response = await fetch('/api/v1/users', {{
                    method: 'GET',
                    headers: {{
                        'Content-Type': 'application/json',
                        'Authorization': token ? `Bearer ${{token}}` : ''
                    }}
                }});

                if (!response.ok) {{
                    throw new Error(`HTTP ${{response.status}}: ${{response.statusText}}`);
                }}

                const data = await response.json();
                const users = data.users || data;

                users.forEach(user => {{
                    const li = document.createElement('li');
                    li.className = 'p-3 border rounded flex justify-between';
                    li.innerHTML = `
                        <span class="font-medium">${{user.email || user.name}}</span>
                        <span class="text-gray-500">ID: ${{user.id}}</span>
                    `;
                    userList.appendChild(li);
                }});

                if (users.length === 0) {{
                    userList.innerHTML = '<li class="p-3 text-gray-500">No users found</li>';
                }}
            }} catch (err) {{
                error.textContent = 'Error loading users: ' + err.message;
                error.classList.remove('hidden');
            }} finally {{
                loading.classList.add('hidden');
            }}
        }}

        // Load on page load
        document.addEventListener('DOMContentLoaded', loadUsers);
    </script>
</body>
</html>"""
            elif "Fix the following accessibility issues" in prompt:
                return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Accessible Component</title>
</head>
<body class="bg-gray-50 p-4">
    <main role="main">
        <div class="bg-white rounded-lg shadow p-6 max-w-4xl mx-auto">
            <h1>Accessible Form</h1>
            <img src="image.jpg" alt="A descriptive alt text">
            <form>
                <label for="email" class="block text-sm font-medium text-gray-700">Email address</label>
                <input 
                    type="email" 
                    id="email" 
                    name="email"
                    class="mt-1 block w-full rounded-md border-gray-300 shadow-sm"
                    aria-label="Email address"
                    aria-required="true"
                    required
                >
                <button 
                    type="submit"
                    class="mt-4 bg-blue-500 text-white py-2 px-4 rounded focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
                    aria-label="Submit form"
                >
                    Submit
                </button>
            </form>
        </div>
    </main>
</body>
</html>"""
            elif "Fix the following security vulnerabilities" in prompt:
                return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Secure Component</title>
</head>
<body>
    <div id="app">
        <h1>Secure Form</h1>
        <form id="secureForm">
            <label for="message">Message:</label>
            <textarea id="message" name="message"></textarea>
            <button type="submit">Send</button>
        </form>
    </div>
    <script>
        document.getElementById('secureForm').addEventListener('submit', async (e) => {{
            e.preventDefault();
            const message = document.getElementById('message').value;
            const output = document.createElement('div');
            output.style.padding = '1rem';
            output.textContent = 'Processing...';
            document.getElementById('app').appendChild(output);

            try {{
                const response = await fetch('/api/message', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ message: message }})
                }});
                const data = await response.json();
                output.textContent = 'Success: ' + JSON.stringify(data);
                output.style.backgroundColor = '#d4edda';
            }} catch (error) {{
                output.textContent = 'Error: ' + error.message;
                output.style.backgroundColor = '#f8d7da';
            }}
        }});
    </script>
</body>
</html>"""
            elif (
                "style guide" in prompt.lower()
                or "Create a comprehensive style guide" in prompt
            ):
                import json
                import re

                # Extract component list from the prompt
                components = []
                # Look for the components section
                lines = prompt.split("\n")
                in_components_section = False
                for line in lines:
                    if "Components:" in line:
                        in_components_section = True
                    elif in_components_section:
                        line = line.strip()
                        if line.startswith("-"):
                            comp = line[1:].strip()
                            if comp:
                                components.append(comp)
                        elif line:  # Non-empty line that's not a list item ends section
                            break

                return json.dumps(
                    {
                        "colors": {
                            "primary": "#3B82F6",
                            "secondary": "#10B981",
                            "accent": "#F59E0B",
                            "neutral": "#6B7280",
                            "background": "#FFFFFF",
                        },
                        "typography": {
                            "font_family": "system-ui, sans-serif",
                            "heading_1": "2.25rem",
                            "body": "1rem",
                        },
                        "spacing": {"xs": "0.25rem", "sm": "0.5rem", "md": "1rem"},
                        "components": components,
                    }
                )
            return ""

        mock.side_effect = mock_call
        yield mock


class TestFrontendAgentInitialization:
    """Test frontend agent initialization."""

    def test_get_role(self, frontend_agent):
        """Test agent returns correct role."""
        assert frontend_agent.get_role() == AgentRole.FRONTEND

    def test_init_with_defaults(self):
        """Test agent initialization with auto-generated ID."""
        agent = FrontendAgent()
        assert agent.agent_id.startswith("frontend_developer-")
        assert agent.role == AgentRole.FRONTEND

    def test_init_with_custom_id(self):
        """Test agent initialization with custom ID."""
        agent = FrontendAgent(agent_id="custom-frontend")
        assert agent.agent_id == "custom-frontend"

    @pytest.mark.asyncio
    async def test_initialize(self, frontend_agent):
        """Test agent initialization."""
        await frontend_agent.initialize()
        assert frontend_agent._initialized is True
        assert frontend_agent._start_time is not None

    @pytest.mark.asyncio
    async def test_register_handlers(self, frontend_agent):
        """Test message handlers registration."""
        await frontend_agent.initialize()

        assert MessageType.API_SPEC_RESPONSE in frontend_agent._message_handlers
        assert MessageType.CODE_REVIEW_REQUEST in frontend_agent._message_handlers
        assert MessageType.SECURITY_ALERT in frontend_agent._message_handlers
        assert MessageType.COMPONENT_UPDATE in frontend_agent._message_handlers


class TestComponentGeneration:
    """Test UI component generation."""

    @pytest.mark.asyncio
    async def test_generate_component_with_api_spec(
        self, frontend_agent, mock_openrouter
    ):
        """Test generating component with API specification."""
        api_spec = ApiSpec(
            endpoint="/api/v1/users",
            method="GET",
            description="Get user list",
            response_schema={"type": "array", "items": {"type": "object"}},
            authentication_required=True,
        )
        spec = {
            "component_name": "UserList",
            "requirements": ["display user list", "load from API", "responsive"],
        }

        code = await frontend_agent._generate_component(
            "UserList", ["display user list", "load from API"], api_spec
        )

        assert code is not None
        assert "<!DOCTYPE html>" in code
        assert "tailwind" in code.lower()
        assert "UserList" in code or "user" in code.lower()

    @pytest.mark.asyncio
    async def test_generate_component_without_api(
        self, frontend_agent, mock_openrouter
    ):
        """Test generating component without API integration."""
        code = await frontend_agent._generate_component(
            "SimpleButton", ["primary button", "hover effect"], None
        )

        assert code is not None
        assert "button" in code.lower()

    @pytest.mark.asyncio
    async def test_generate_fallback_component(self, frontend_agent):
        """Test fallback component when AI is unavailable."""
        code = frontend_agent._generate_fallback_component(
            "TestComponent", ["responsive", "accessible"]
        )

        assert code is not None
        assert "<!DOCTYPE html>" in code
        assert "tailwind" in code.lower()
        assert "OPENROUTER_API_KEY" in code

    @pytest.mark.asyncio
    async def test_process_generation_task(self, frontend_agent, mock_openrouter):
        """Test processing a component generation task."""
        task = Task(
            description="Generate responsive login form component",
            role=AgentRole.FRONTEND,
            payload={
                "spec": {
                    "component_name": "LoginForm",
                    "requirements": ["email input", "password field", "submit button"],
                }
            },
        )

        result = await frontend_agent.process_task(task)

        assert result["success"] is True
        assert "component_code" in result["output"]
        assert "accessibility_report" in result["output"]
        assert "style_guide" in result["output"]
        assert result["execution_time"] > 0


class TestResponsiveDesign:
    """Test responsive design capabilities."""

    @pytest.mark.asyncio
    async def test_ensure_responsive_adds_breakpoints(
        self, frontend_agent, mock_openrouter
    ):
        """Test that responsive enhancement adds breakpoints."""
        basic_code = """<!DOCTYPE html>
<html>
<head><title>Test</title></head>
<body>
    <div class="container">Content</div>
</body>
</html>"""

        enhanced = await frontend_agent._ensure_responsive(basic_code)

        assert enhanced is not None
        # Should have added some responsive classes
        assert any(bp in enhanced for bp in ["md:", "lg:", "sm:"])

    @pytest.mark.asyncio
    async def test_ensure_responsive_preserves_existing(
        self, frontend_agent, mock_openrouter
    ):
        """Test that responsive enhancement preserves existing code."""
        responsive_code = """<!DOCTYPE html>
<html>
<head><title>Test</title></head>
<body>
    <div class="hidden md:block">Desktop content</div>
    <div class="md:hidden block">Mobile content</div>
</body>
</html>"""

        enhanced = await frontend_agent._ensure_responsive(responsive_code)

        # Should keep existing responsive classes
        assert "hidden md:block" in enhanced
        assert "md:hidden block" in enhanced


class TestAccessibility:
    """Test accessibility auditing and fixes."""

    @pytest.mark.asyncio
    async def test_audit_accessibility_issues(self, frontend_agent):
        """Test detecting accessibility issues."""
        bad_code = """<!DOCTYPE html>
<html>
<head><title>Test</title></head>
<body>
    <img src="image.jpg">
    <div onclick="alert('hi')">Click me</div>
    <p>Some text</p>
</body>
</html>"""

        report = await frontend_agent._audit_accessibility(bad_code)

        assert "issues" in report
        assert report["total_issues"] > 0
        # Should detect missing alt
        assert any("alt_text" in str(issue) for issue in report["issues"])

    @pytest.mark.asyncio
    async def test_audit_accessibility_good_code(self, frontend_agent):
        """Test that good code has fewer issues."""
        good_code = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Accessible</title>
</head>
<body>
    <header>
        <h1>Main Title</h1>
        <nav aria-label="Main navigation">
            <ul><li><a href="#">Link</a></li></ul>
        </nav>
    </header>
    <main>
        <label for="email">Email:</label>
        <input type="email" id="email" aria-label="Email address">
        <img src="photo.jpg" alt="Description of photo">
    </main>
</body>
</html>"""

        report = await frontend_agent._audit_accessibility(good_code)

        assert report["score"] > 50
        assert report["compliance_level"] == "AA" or report["score"] >= 90

    @pytest.mark.asyncio
    async def test_fix_accessibility_issues(self, frontend_agent, mock_openrouter):
        """Test fixing accessibility issues."""
        bad_code = """<!DOCTYPE html>
<html>
<body>
    <img src="image.jpg">
    <button onclick="submit()">Submit</button>
</body>
</html>"""

        initial_report = await frontend_agent._audit_accessibility(bad_code)
        fixed_code = await frontend_agent._fix_accessibility_issues(
            bad_code, initial_report
        )

        assert fixed_code is not None
        assert "alt=" in fixed_code
        assert "aria-label" in fixed_code or "<label" in fixed_code

    @pytest.mark.asyncio
    async def test_check_requirements_accessibility(self, frontend_agent):
        """Test requirement checking for accessibility."""
        code = '<img src="test.jpg" alt="test"> <label for="field">Field</label>'
        requirements = ["accessible", "WCAG compliant"]

        results = frontend_agent._check_requirements(code, requirements)

        assert results["accessible"] is True or results["WCAG compliant"] is True


class TestAPIIntegration:
    """Test backend API integration."""

    @pytest.mark.asyncio
    async def test_integrate_backend_api_with_spec(
        self, frontend_agent, mock_openrouter
    ):
        """Test integrating component with API spec."""
        component = """<!DOCTYPE html>
<html>
<body>
    <div id="app">
        <h1>Users</h1>
        <div id="content"></div>
    </div>
</body>
</html>"""

        api_spec = ApiSpec(
            endpoint="/api/v1/users",
            method="GET",
            description="Get user list",
            response_schema={
                "type": "object",
                "properties": {"users": {"type": "array"}},
            },
            authentication_required=False,
        )

        integrated = await frontend_agent._integrate_backend_api(component, api_spec)

        assert integrated is not None
        assert "fetch(" in integrated
        assert "/api/v1/users" in integrated
        assert "addEventListener" in integrated or "DOMContentLoaded" in integrated

    @pytest.mark.asyncio
    async def test_integrate_backend_api_with_auth(
        self, frontend_agent, mock_openrouter
    ):
        """Test integrating API with authentication."""
        component = """<!DOCTYPE html>
<html>
<body><div id="data"></div></body>
</html>"""

        api_spec = ApiSpec(
            endpoint="/api/v1/protected",
            method="GET",
            description="Get protected data",
            authentication_required=True,
        )

        integrated = await frontend_agent._integrate_backend_api(component, api_spec)

        assert integrated is not None
        assert "Authorization" in integrated or "Bearer" in integrated
        assert "localStorage" in integrated or "cookie" in integrated.lower()

    @pytest.mark.asyncio
    async def test_integrate_backend_api_no_spec(self, frontend_agent):
        """Test integration with no API spec returns unchanged."""
        component = """<!DOCTYPE html><html><body>Test</body></html>"""

        result = await frontend_agent._integrate_backend_api(component, None)

        assert result == component


class TestStyleGuide:
    """Test style guide creation."""

    @pytest.mark.asyncio
    async def test_create_style_guide(self, frontend_agent, mock_openrouter):
        """Test generating a style guide."""
        components = ["Button", "Input", "Card"]

        guide = await frontend_agent._create_style_guide(components)

        assert isinstance(guide, dict)
        assert "colors" in guide
        assert "typography" in guide
        assert "spacing" in guide
        assert "components" in guide

    @pytest.mark.asyncio
    async def test_create_style_guide_empty(self, frontend_agent, mock_openrouter):
        """Test style guide with empty components."""
        guide = await frontend_agent._create_style_guide([])

        assert isinstance(guide, dict)
        assert len(guide.get("colors", {})) > 0

    @pytest.mark.asyncio
    async def test_create_style_guide_fallback(self, frontend_agent):
        """Test style guide fallback when AI fails."""
        with patch.object(
            frontend_agent, "_call_openrouter", side_effect=Exception("API error")
        ):
            guide = await frontend_agent._create_style_guide(["Button"])

        assert guide is not None
        assert "colors" in guide
        assert "primary" in guide["colors"]


class TestTaskProcessing:
    """Test different task processing scenarios."""

    @pytest.mark.asyncio
    async def test_process_generate_component_task(
        self, frontend_agent, mock_openrouter
    ):
        """Test processing a component generation task."""
        task = Task(
            description="Create a responsive login form",
            role=AgentRole.FRONTEND,
            payload={
                "spec": {
                    "component_name": "LoginForm",
                    "requirements": ["email", "password", "submit", "responsive"],
                }
            },
        )

        result = await frontend_agent.process_task(task)

        assert result["success"] is True
        assert "component_code" in result["output"]
        assert "accessibility_report" in result["output"]
        assert result["output"]["component_code"] is not None

    @pytest.mark.asyncio
    async def test_process_responsive_task(self, frontend_agent, mock_openrouter):
        """Test processing a responsive design task."""
        component_code = "<div class='container'>Content</div>"
        task = Task(
            description="Make component responsive for mobile",
            role=AgentRole.FRONTEND,
            payload={"component_code": component_code},
        )

        result = await frontend_agent.process_task(task)

        assert result["success"] is True
        assert "responsive_code" in result["output"]

    @pytest.mark.asyncio
    async def test_process_accessibility_audit_task(
        self, frontend_agent, mock_openrouter
    ):
        """Test processing an accessibility audit task."""
        component_code = """<!DOCTYPE html>
<html>
<body>
    <img src="test.jpg">
    <button onclick="alert('hi')">Click</button>
</body>
</html>"""

        task = Task(
            description="Audit accessibility and fix issues",
            role=AgentRole.FRONTEND,
            payload={"component_code": component_code},
        )

        result = await frontend_agent.process_task(task)

        assert result["success"] is True
        assert "accessibility_report" in result["output"]
        assert "fixed_code" in result["output"]
        assert result["output"]["issues_found"] >= 0

    @pytest.mark.asyncio
    async def test_process_api_integration_task(self, frontend_agent, mock_openrouter):
        """Test processing an API integration task."""
        component_code = """<!DOCTYPE html>
<html>
<body>
    <div id="data"></div>
</body>
</html>"""

        api_spec = ApiSpec(
            endpoint="/api/data",
            method="GET",
            description="Get data",
            authentication_required=False,
        )

        task = Task(
            description="Integrate with backend API to fetch data",
            role=AgentRole.FRONTEND,
            payload={"component_code": component_code, "api_spec": api_spec.dict()},
        )

        result = await frontend_agent.process_task(task)

        assert result["success"] is True
        assert "integrated_code" in result["output"]
        assert "fetch(" in result["output"]["integrated_code"]

    @pytest.mark.asyncio
    async def test_process_style_guide_task(self, frontend_agent, mock_openrouter):
        """Test processing a style guide creation task."""
        task = Task(
            description="Create style guide for component library",
            role=AgentRole.FRONTEND,
            payload={"components": ["Button", "Input", "Card", "Modal"]},
        )

        result = await frontend_agent.process_task(task)

        assert result["success"] is True
        assert "style_guide" in result["output"]
        assert result["output"]["components_included"] == [
            "Button",
            "Input",
            "Card",
            "Modal",
        ]

    @pytest.mark.asyncio
    async def test_process_unknown_task_type(self, frontend_agent, mock_openrouter):
        """Test processing task with unclear type."""
        task = Task(
            description="Do something mysterious",
            role=AgentRole.FRONTEND,
            payload={},
        )

        result = await frontend_agent.process_task(task)

        assert result["success"] is True
        assert "task_type" in result["output"]

    @pytest.mark.asyncio
    async def test_process_task_with_exception(self, frontend_agent):
        """Test task processing with exception."""
        task = Task(
            description="Invalid task that will fail",
            role=AgentRole.FRONTEND,
            payload={"spec": {"component_name": "Test"}},
        )

        with patch.object(
            frontend_agent, "_generate_component", side_effect=Exception("Test error")
        ):
            with pytest.raises(Exception):
                await frontend_agent.process_task(task)


class TestMessaging:
    """Test A2A message handling."""

    @pytest.mark.asyncio
    async def test_handle_api_spec_response(
        self, frontend_agent, mock_broker, mock_openrouter
    ):
        """Test handling API spec response from dev agent."""
        from src.protocols.agent_specs import AgentMessage

        api_spec = ApiSpec(
            endpoint="/api/v1/users",
            method="GET",
            description="Get user list",
            response_schema={"type": "array"},
        )

        message = AgentMessage(
            sender=AgentRole.SW_DEV,
            recipient=AgentRole.FRONTEND,
            message_type=MessageType.API_SPEC_RESPONSE,
            payload={
                "component_name": "UserList",
                "api_spec": api_spec.dict(),
                "timestamp": asyncio.get_event_loop().time(),
            },
            correlation_id="test-corr-api",
        )

        frontend_agent.broker = mock_broker
        await frontend_agent.initialize()

        await frontend_agent._handle_api_spec_response(message)

        # Should store in shared knowledge
        assert mock_broker.publish.called is False  # Just stores, doesn't publish

    @pytest.mark.asyncio
    async def test_handle_code_review_request(
        self, frontend_agent, mock_broker, mock_openrouter
    ):
        """Test handling code review request."""
        code = """<!DOCTYPE html>
<html>
<body>
    <button onclick="alert('hi')">Click</button>
</body>
</html>"""

        from src.protocols.agent_specs import AgentMessage

        message = AgentMessage(
            sender=AgentRole.SECURITY,
            recipient=AgentRole.FRONTEND,
            message_type=MessageType.CODE_REVIEW_REQUEST,
            payload={
                "code": code,
                "language": "html",
                "context": "Review for security and accessibility",
            },
            correlation_id="test-corr-review",
        )

        frontend_agent.broker = mock_broker
        await frontend_agent.initialize()

        await frontend_agent._handle_code_review_request(message)

        # Should send CODE_REVIEW_RESPONSE
        assert mock_broker.publish.called
        call_args = mock_broker.publish.call_args
        sent_message = (
            call_args[0][1] if len(call_args[0]) > 1 else call_args[1]["message"]
        )
        assert sent_message["message_type"] == MessageType.CODE_REVIEW_RESPONSE
        assert "findings" in sent_message["payload"]

    @pytest.mark.asyncio
    async def test_handle_security_alert_with_file(
        self, frontend_agent, mock_broker, tmp_path
    ):
        """Test handling security alert and fixing vulnerabilities."""
        # Create vulnerable file
        test_file = tmp_path / "vuln.html"
        test_file.write_text(
            """<!DOCTYPE html>
<html>
<body>
    <div onclick="eval(userInput)">Click</div>
    <script>
        document.write(location.hash);
    </script>
</body>
</html>"""
        )

        from src.protocols.agent_specs import AgentMessage

        message = AgentMessage(
            sender=AgentRole.SECURITY,
            recipient=AgentRole.FRONTEND,
            message_type=MessageType.SECURITY_ALERT,
            payload={
                "findings": [
                    {"category": "xss", "description": "eval() usage is dangerous"}
                ],
                "message": "XSS vulnerability detected",
                "severity": "high",
                "code_path": str(test_file),
            },
            correlation_id="test-corr-sec",
        )

        frontend_agent.broker = mock_broker
        await frontend_agent.initialize()

        with patch.object(
            frontend_agent,
            "_fix_security_vulnerabilities",
            return_value="<html><body>Fixed</body></html>",
        ):
            await frontend_agent._handle_security_alert(message)

        # Should send TASK_UPDATE response
        assert mock_broker.publish.called

    @pytest.mark.asyncio
    async def test_handle_security_alert_without_file(
        self, frontend_agent, mock_broker
    ):
        """Test handling security alert without file path."""
        from src.protocols.agent_specs import AgentMessage

        message = AgentMessage(
            sender=AgentRole.SECURITY,
            recipient=AgentRole.FRONTEND,
            message_type=MessageType.SECURITY_ALERT,
            payload={
                "findings": [],
                "message": "General security notice",
                "severity": "low",
            },
            correlation_id="test-corr-sec2",
        )

        frontend_agent.broker = mock_broker
        await frontend_agent.initialize()

        # Should not crash
        await frontend_agent._handle_security_alert(message)

    @pytest.mark.asyncio
    async def test_handle_component_update(
        self, frontend_agent, mock_broker, mock_openrouter
    ):
        """Test handling component update from another agent."""
        from src.protocols.agent_specs import AgentMessage

        message = AgentMessage(
            sender=AgentRole.SW_DEV,
            recipient=AgentRole.FRONTEND,
            message_type=MessageType.COMPONENT_UPDATE,
            payload={
                "component_name": "Button",
                "updated_code": "<button class='bg-blue-500'>Click</button>",
                "changes": ["Added disabled state", "Improved styling"],
                "version": "1.2",
            },
            correlation_id="test-corr-update",
        )

        frontend_agent.broker = mock_broker
        await frontend_agent.initialize()

        await frontend_agent._handle_component_update(message)

        # Should store in shared knowledge
        stored_value = frontend_agent.get_shared_knowledge("component:Button")
        assert stored_value is not None
        assert "button" in stored_value.lower()


class TestHealthCheck:
    """Test health check functionality."""

    @pytest.mark.asyncio
    async def test_health_check(self, frontend_agent):
        """Test health check returns frontend-specific info."""
        frontend_agent._running = True
        frontend_agent._initialized = True
        frontend_agent._start_time = datetime.utcnow()

        health = await frontend_agent.health_check()

        assert health["healthy"] is True
        assert "tools_available" in health
        assert health["tools_available"]["tailwind_ready"] is True
        assert "accessibility_checks_loaded" in health
        assert "responsive_breakpoints" in health

    @pytest.mark.asyncio
    async def test_check_tool_available(self, frontend_agent):
        """Test checking tool availability."""
        # Should always return True for tailwind since we use CDN
        assert frontend_agent._check_tool("tailwind") is False  # Not a CLI tool


class TestFrontendPatterns:
    """Test specific frontend pattern detection and generation."""

    @pytest.mark.asyncio
    async def test_tailwind_cdn_included(self, frontend_agent, mock_openrouter):
        """Test that generated components include Tailwind CDN."""
        code = await frontend_agent._generate_component("Test", [], None)

        assert "cdn.tailwindcss.com" in code

    @pytest.mark.asyncio
    async def test_semantic_html_encouraged(self, frontend_agent, mock_openrouter):
        """Test that generated components use semantic HTML."""
        code = await frontend_agent._generate_component("SemanticTest", [], None)

        # Should have semantic elements
        has_semantic = any(
            tag in code
            for tag in ["<main", "<header", "<footer", "<section", "<nav", "<article"]
        )
        assert has_semantic or "main" in code

    @pytest.mark.asyncio
    async def test_responsive_classes_added(self, frontend_agent, mock_openrouter):
        """Test that responsive classes are included."""
        requirements = ["responsive", "mobile-friendly"]
        code = await frontend_agent._generate_component(
            "ResponsiveComp", requirements, None
        )

        # Should have some responsive breakpoint classes
        has_responsive = any(f"{bp}:" in code for bp in ["sm", "md", "lg", "xl"])
        assert has_responsive


class TestIntegration:
    """Integration tests for full frontend workflows."""

    @pytest.mark.asyncio
    async def test_full_component_workflow(self, frontend_agent, mock_openrouter):
        """Test complete workflow: generate -> enhance -> audit."""
        # 1. Generate component with API spec
        api_spec = ApiSpec(
            endpoint="/api/items",
            method="GET",
            description="Get items",
            response_schema={"type": "array"},
        )

        spec = {
            "component_name": "ItemList",
            "requirements": ["display items", "load from API", "responsive"],
        }

        task = Task(
            description="Generate ItemList component",
            role=AgentRole.FRONTEND,
            payload={"spec": spec, "api_spec": api_spec.dict()},
        )

        result = await frontend_agent.process_task(task)

        assert result["success"] is True
        component_code = result["output"]["component_code"]

        # 2. Check responsive
        assert any(bp in component_code for bp in ["md:", "lg:"])

        # 3. Check accessibility report
        assert "accessibility_report" in result["output"]
        assert "score" in result["output"]["accessibility_report"]

        # 4. Check API integration
        assert "fetch(" in component_code
        assert "/api/items" in component_code

    @pytest.mark.asyncio
    async def test_code_review_workflow(
        self, frontend_agent, mock_broker, mock_openrouter
    ):
        """Test code review workflow via A2A."""
        from src.protocols.agent_specs import AgentMessage

        code = """<!DOCTYPE html>
<html>
<body>
    <div onclick="eval(location.hash)">Click</div>
</body>
</html>"""

        message = AgentMessage(
            sender=AgentRole.SECURITY,
            recipient=AgentRole.FRONTEND,
            message_type=MessageType.CODE_REVIEW_REQUEST,
            payload={"code": code, "language": "html"},
            correlation_id="review-frontend-123",
        )

        frontend_agent.broker = mock_broker
        await frontend_agent.initialize()

        await frontend_agent._handle_code_review_request(message)

        # Should send response with findings
        assert mock_broker.publish.called

    @pytest.mark.asyncio
    async def test_api_spec_request_to_dev_workflow(
        self, frontend_agent, mock_broker, mock_openrouter
    ):
        """Test frontend requesting API spec from dev (this would normally be initiated by frontend)."""
        # This tests that frontend can receive and process an API spec response
        from src.protocols.agent_specs import AgentMessage

        api_spec = ApiSpec(
            endpoint="/api/v1/items",
            method="POST",
            description="Create item",
            request_schema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
            },
        )

        message = AgentMessage(
            sender=AgentRole.SW_DEV,
            recipient=AgentRole.FRONTEND,
            message_type=MessageType.API_SPEC_RESPONSE,
            payload={
                "component_name": "ItemForm",
                "api_spec": api_spec.dict(),
                "timestamp": asyncio.get_event_loop().time(),
            },
            correlation_id="spec-response-123",
        )

        frontend_agent.broker = mock_broker
        await frontend_agent.initialize()
        frontend_agent.set_shared_knowledge = MagicMock()

        await frontend_agent._handle_api_spec_response(message)

        # Should store spec in shared knowledge
        frontend_agent.set_shared_knowledge.assert_called()


class TestLoginFormGeneration:
    """Test login form generation capabilities."""

    @pytest.mark.asyncio
    async def test_generate_login_form_fallback(self, frontend_agent):
        """Test generating login form using fallback method (no AI)."""
        login_form = await frontend_agent._generate_login_form()

        assert login_form is not None
        assert isinstance(login_form, str)
        assert "<!DOCTYPE html>" in login_form
        assert "Login" in login_form or "login" in login_form
        assert "tailwind" in login_form.lower()
        assert "form" in login_form.lower()

    @pytest.mark.asyncio
    async def test_generate_login_form_with_custom_validations(self, frontend_agent):
        """Test generating login form with custom validation rules."""
        custom_validations = {
            "min_password_length": 12,
            "require_special_char": True,
            "block_common_passwords": True,
        }
        login_form = await frontend_agent._generate_login_form(
            custom_validations=custom_validations
        )

        assert login_form is not None
        assert "custom" in login_form.lower() or "Custom" in login_form
        assert "password" in login_form.lower()

    @pytest.mark.asyncio
    async def test_login_form_has_required_elements(self, frontend_agent):
        """Test that generated login form contains all required elements."""
        login_form = await frontend_agent._generate_login_form()

        # Check for essential form elements
        assert "<form" in login_form
        assert 'type="email"' in login_form or 'type="text"' in login_form
        assert 'type="password"' in login_form
        assert "submit" in login_form.lower() or "button" in login_form.lower()

        # Check for responsive meta tag
        assert "viewport" in login_form

        # Check for Tailwind CSS
        assert "cdn.tailwindcss.com" in login_form

    @pytest.mark.asyncio
    async def test_login_form_has_accessibility_features(self, frontend_agent):
        """Test that generated login form includes WCAG accessibility features."""
        login_form = await frontend_agent._generate_login_form()

        # Check for labels
        assert "<label" in login_form

        # Check for ARIA attributes
        has_aria = any(
            attr in login_form
            for attr in [
                "aria-label",
                "aria-labelledby",
                "aria-describedby",
                "aria-live",
            ]
        )
        assert has_aria, "Should include ARIA attributes for accessibility"

        # Check for semantic HTML
        has_semantic = any(
            tag in login_form for tag in ["<main", "<header", "<footer", "<section"]
        )
        assert has_semantic, "Should use semantic HTML elements"

        # Check for error handling with role="alert" or aria-live
        has_error_handling = 'role="alert"' in login_form or "aria-live" in login_form
        assert has_error_handling, (
            "Should have proper error announcement for screen readers"
        )

    @pytest.mark.asyncio
    async def test_login_form_has_responsive_design(self, frontend_agent):
        """Test that generated login form is responsive."""
        login_form = await frontend_agent._generate_login_form()

        # Check for responsive classes
        responsive_classes = [
            "max-w-",
            "sm:",
            "md:",
            "lg:",
            "xl:",
            "flex",
            "grid",
            "p-4",
            "p-",
        ]
        has_responsive = any(cls in login_form for cls in responsive_classes)
        assert has_responsive, "Should include responsive design classes"

        # Check viewport meta tag
        assert 'name="viewport"' in login_form

    @pytest.mark.asyncio
    async def test_login_form_has_password_toggle(self, frontend_agent):
        """Test that generated login form includes password visibility toggle."""
        login_form = await frontend_agent._generate_login_form()

        # Check for password toggle mechanism
        has_toggle = "password" in login_form.lower() and (
            "toggle" in login_form.lower() or "visibility" in login_form.lower()
        )
        assert has_toggle, "Should have password visibility toggle"

    @pytest.mark.asyncio
    async def test_login_form_has_validation(self, frontend_agent):
        """Test that generated login form includes client-side validation."""
        login_form = await frontend_agent._generate_login_form()

        # Check for validation attributes
        has_required = "required" in login_form
        has_email_type = 'type="email"' in login_form or 'type="text"' in login_form
        has_validation = (
            "validate" in login_form.lower() or "valid" in login_form.lower()
        )

        assert has_required or has_email_type or has_validation, (
            "Should include form validation"
        )

    @pytest.mark.asyncio
    async def test_login_form_has_api_integration_structure(self, frontend_agent):
        """Test that login form includes API integration structure."""
        login_form = await frontend_agent._generate_login_form()

        # Check for fetch API or localStorage
        has_api_structure = any(
            keyword in login_form
            for keyword in ["fetch", "localStorage", "API", "post", "submit"]
        )
        assert has_api_structure, "Should include API integration structure"

    @pytest.mark.asyncio
    async def test_login_form_has_error_handling(self, frontend_agent):
        """Test that login form includes error handling."""
        login_form = await frontend_agent._generate_login_form()

        # Check for error messages or error display
        has_error_handling = any(
            keyword in login_form.lower()
            for keyword in ["error", "invalid", "failed", "catch", "try"]
        )
        assert has_error_handling, "Should include error handling"

    @pytest.mark.asyncio
    async def test_process_login_form_task(self, frontend_agent, mock_openrouter):
        """Test processing a login form generation task through process_task."""
        task = Task(
            description="Build responsive login form component",
            role=AgentRole.FRONTEND,
            payload={
                "spec": {
                    "component_name": "LoginForm",
                    "requirements": [
                        "email input",
                        "password field",
                        "submit button",
                        "responsive design",
                        "accessible",
                    ],
                }
            },
        )

        result = await frontend_agent.process_task(task)

        assert result["success"] is True
        assert "component_code" in result["output"]
        assert "accessibility_report" in result["output"]
        assert "style_guide" in result["output"]
        assert result["execution_time"] > 0

        # Check that component code was generated
        component_code = result["output"]["component_code"]
        assert component_code is not None
        assert len(component_code) > 0

    @pytest.mark.asyncio
    async def test_fallback_login_form_structure(self, frontend_agent):
        """Test the structure and completeness of the fallback login form."""
        login_form = frontend_agent._generate_fallback_login_form()

        # Parse and check structure
        assert "<!DOCTYPE html>" in login_form
        assert "<html" in login_form
        assert "<head>" in login_form
        assert "<body>" in login_form
        assert "</html>" in login_form

        # Check head elements
        assert "charset" in login_form
        assert "viewport" in login_form
        assert "tailwindcss.com" in login_form

        # Check body structure
        assert "<main" in login_form or "main" in login_form
        assert "form" in login_form.lower()

        # Check for essential controls
        assert "email" in login_form.lower()
        assert "password" in login_form.lower()
        assert "button" in login_form.lower() or "<button" in login_form

        # Check for JavaScript functionality
        assert "<script>" in login_form or "<script " in login_form
        assert "addEventListener" in login_form or "DOMContentLoaded" in login_form
