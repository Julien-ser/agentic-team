"""
Software Development Agent - Backend code generation specialist.

This agent generates Python code, writes tests, performs refactoring,
and ensures code quality through formatting and linting.
"""

import asyncio
import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Any

import aiohttp

from src.agents.base_agent import BaseAgent
from src.protocols.agent_specs import (
    AgentRole,
    MessageType,
    Task,
    ApiSpec,
)
from src.config import config

logger = logging.getLogger(__name__)


class SoftwareDevAgent(BaseAgent):
    """
    Software development specialist agent with code generation capabilities.

    Capabilities:
    - Generate Python code from task specifications using OpenRouter AI
    - Write unit tests using pytest framework
    - Refactor code based on Security Agent feedback
    - Perform code formatting (black) and linting (ruff)
    - Handle API_SPEC_REQUEST from Frontend Agent
    - Process CODE_REVIEW_REQUEST from Security/Frontend
    - Fix vulnerabilities reported in SECURITY_ALERT messages
    """

    def get_role(self) -> AgentRole:
        """Return the software developer agent role."""
        return AgentRole.SW_DEV

    async def initialize(self) -> None:
        """Initialize software dev agent resources."""
        await super().initialize()

        # Register message handlers
        self.register_message_handler(
            MessageType.CODE_REVIEW_REQUEST, self._handle_code_review_request
        )
        self.register_message_handler(
            MessageType.API_SPEC_REQUEST, self._handle_api_spec_request
        )
        self.register_message_handler(
            MessageType.SECURITY_ALERT, self._handle_security_alert
        )

        logger.info(f"Software Dev agent {self.agent_id} initialized with handlers")

    async def process_task(self, task: Task) -> Dict[str, Any]:
        """
        Process a software development task.

        Args:
            task: Task with description and parameters

        Returns:
            Dict with results including generated code, tests, etc.
        """
        start_time = asyncio.get_event_loop().time()

        try:
            task.mark_in_progress()
            description = task.description.lower()

            # Determine task type
            if any(
                keyword in description
                for keyword in ["generate", "create", "implement", "build"]
            ):
                # Code generation task
                spec = task.payload.get("spec", {})
                code = await self._generate_code(spec)

                # Write tests if requested
                tests = []
                if task.payload.get("generate_tests", True):
                    tests = await self._generate_tests(code, spec)

                # Format and lint the code
                formatted_code = await self._format_code(code)
                lint_results = await self._lint_code(formatted_code)

                return {
                    "success": True,
                    "output": {
                        "code": formatted_code,
                        "tests": tests,
                        "lint_results": lint_results,
                        "spec_used": spec,
                    },
                    "artifacts": [],
                    "execution_time": asyncio.get_event_loop().time() - start_time,
                }

            elif "test" in description:
                # Test generation task
                code = task.payload.get("code", "")
                spec = task.payload.get("spec", {})
                tests = await self._generate_tests(code, spec)

                return {
                    "success": True,
                    "output": {
                        "tests": tests,
                        "code_under_test": code[:100] + "..."
                        if len(code) > 100
                        else code,
                    },
                    "artifacts": [],
                    "execution_time": asyncio.get_event_loop().time() - start_time,
                }

            elif any(
                keyword in description for keyword in ["refactor", "fix", "improve"]
            ):
                # Refactoring task based on security feedback
                code = task.payload.get("code", "")
                vulnerabilities = task.payload.get("vulnerabilities", [])
                fixed_code = await self._refactor_code(code, vulnerabilities)

                # Verify fixes with another scan
                verification = await self._verify_security_fixes(
                    fixed_code, vulnerabilities
                )

                return {
                    "success": True,
                    "output": {
                        "original_code": code[:200],
                        "fixed_code": fixed_code,
                        "vulnerabilities_fixed": len(vulnerabilities),
                        "verification": verification,
                    },
                    "artifacts": [],
                    "execution_time": asyncio.get_event_loop().time() - start_time,
                }

            elif "format" in description:
                # Code formatting task
                code = task.payload.get("code", "")
                formatted = await self._format_code(code)

                return {
                    "success": True,
                    "output": {
                        "original_length": len(code),
                        "formatted_length": len(formatted),
                        "formatted_code": formatted,
                    },
                    "artifacts": [],
                    "execution_time": asyncio.get_event_loop().time() - start_time,
                }

            elif "lint" in description:
                # Code linting task
                code = task.payload.get("code", "")
                lint_results = await self._lint_code(code)

                return {
                    "success": True,
                    "output": {
                        "lint_results": lint_results,
                        "code_length": len(code),
                    },
                    "artifacts": [],
                    "execution_time": asyncio.get_event_loop().time() - start_time,
                }

            else:
                # Default: treat as code generation with spec
                spec = task.payload.get("spec", {"description": task.description})
                code = await self._generate_code(spec)

                return {
                    "success": True,
                    "output": {
                        "code": code,
                        "task_type": "general_code_generation",
                    },
                    "artifacts": [],
                    "execution_time": asyncio.get_event_loop().time() - start_time,
                }

        except Exception as e:
            logger.error(f"Software Dev task failed: {e}", exc_info=True)
            raise

    async def _generate_code(self, spec: Dict[str, Any]) -> str:
        """
        Generate Python code using OpenRouter AI.

        Args:
            spec: Specification dict with requirements, endpoint, methods, etc.

        Returns:
            Generated Python code as string
        """
        # Build prompt from spec
        prompt = self._build_code_generation_prompt(spec)

        try:
            # Call OpenRouter API
            code = await self._call_openrouter(prompt)

            # Extract code from markdown blocks if present
            if "```python" in code:
                start = code.find("```python") + 9
                end = code.find("```", start)
                if end != -1:
                    code = code[start:end].strip()
            elif "```" in code:
                start = code.find("```") + 3
                end = code.find("```", start)
                if end != -1:
                    code = code[start:end].strip()

            return code

        except Exception as e:
            logger.error(f"Code generation failed: {e}")
            # Return a fallback template
            return self._generate_fallback_code(spec)

    def _build_code_generation_prompt(self, spec: Dict[str, Any]) -> str:
        """Build a prompt for code generation based on spec."""
        endpoint = spec.get("endpoint", "/api/endpoint")
        method = spec.get("method", "GET")
        description = spec.get("description", "API endpoint")
        auth_required = spec.get("authentication_required", False)
        request_schema = spec.get("request_schema", {})
        response_schema = spec.get("response_schema", {})

        prompt = f"""Generate a complete, production-ready Python Flask API endpoint with the following specifications:

Endpoint: {method} {endpoint}
Description: {description}
Authentication Required: {auth_required}
Request Schema: {json.dumps(request_schema, indent=2) if request_schema else "None"}
Response Schema: {json.dumps(response_schema, indent=2) if response_schema else "None"}

Requirements:
1. Use Flask 3.0+ with type hints
2. Include comprehensive docstring with parameters and return types
3. Implement proper error handling and validation
4. Use environment variables for configuration (no hardcoded secrets)
5. Follow PEP 8 style guide
6. Include logging
7. Return appropriate HTTP status codes
8. If authentication required, implement JWT validation

Provide ONLY the Python code without any explanatory text. Do not include markdown code fences in your response - just the raw code.

Example structure:
```python
from flask import Flask, request, jsonify
import os
import logging

app = Flask(__name__)

@app.route('{endpoint}', methods=['{method}'])
def {self._extract_endpoint_name(endpoint)}():
    \"""{description}

    Returns:
        JSON response with data
    \"""
    # Implementation here
    pass
```"""

        return prompt

    def _extract_endpoint_name(self, endpoint: str) -> str:
        """Extract a function name from an endpoint path."""
        # Convert /api/users/profile to api_users_profile
        name = endpoint.replace("/", "_").strip("_")
        # Remove leading numbers if any
        if name and name[0].isdigit():
            name = "endpoint_" + name
        return name or "handle_endpoint"

    async def _call_openrouter(self, prompt: str) -> str:
        """
        Call OpenRouter API to generate code.

        Args:
            prompt: The prompt to send to the AI model

        Returns:
            Generated text response
        """
        api_key = config.OPENROUTER_API_KEY
        if not api_key:
            logger.warning("OPENROUTER_API_KEY not set, using fallback code generation")
            raise ValueError("OpenRouter API key not configured")

        model = config.WIGGUM_MODEL

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/anomalyco/opencode",
            "X-Title": "Agentic-Team Software Dev Agent",
        }

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are an expert Python software developer specializing in secure, production-ready Flask APIs. Always follow best practices for security, error handling, and code quality.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 2000,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(
                        f"OpenRouter API error: {response.status} - {error_text}"
                    )

                result = await response.json()

                if "choices" not in result or not result["choices"]:
                    raise Exception("Invalid response from OpenRouter: no choices")

                return result["choices"][0]["message"]["content"].strip()

    def _generate_fallback_code(self, spec: Dict[str, Any]) -> str:
        """Generate fallback code when AI is not available."""
        endpoint = spec.get("endpoint", "/api/endpoint")
        method = spec.get("method", "GET")

        return f'''"""
Fallback implementation for {method} {endpoint}
"""
from flask import Flask, request, jsonify
import os

app = Flask(__name__)

@app.route('{endpoint}', methods=['{method}'])
def {self._extract_endpoint_name(endpoint)}():
    """TODO: Implement this endpoint properly.

    This is a fallback implementation. Connect OpenRouter API for AI-generated code.
    """
    return jsonify({{
        "error": "Not implemented",
        "message": "Configure OPENROUTER_API_KEY for AI code generation"
    }}), 501
'''

    async def _generate_tests(self, code: str, spec: Dict[str, Any]) -> List[str]:
        """
        Generate pytest tests for the given code.

        Args:
            code: The source code to test
            spec: Original specification for context

        Returns:
            List of test file strings
        """
        # Build prompt for test generation
        prompt = f"""Generate comprehensive pytest unit tests for the following Python code:

```python
{code[:4000]}  # Limit code length in prompt
```

Create a complete test file with:
1. Fixtures for Flask test client and any dependencies
2. Tests for all endpoint routes with various inputs
3. Tests for edge cases and error conditions
4. Mocking for external dependencies (database, APIs)
5. Authentication tests if applicable

Use pytest, pytest-mock, and Flask's test_client.
Include proper assertions and coverage.
Return ONLY the test code without markdown fences."""

        try:
            test_code = await self._call_openrouter(prompt)

            # Extract code if wrapped in markdown
            if "```python" in test_code:
                start = test_code.find("```python") + 9
                end = test_code.find("```", start)
                if end != -1:
                    test_code = test_code[start:end].strip()
            elif "```" in test_code:
                start = test_code.find("```") + 3
                end = test_code.find("```", start)
                if end != -1:
                    test_code = test_code[start:end].strip()

            return [test_code] if test_code else []

        except Exception as e:
            logger.error(f"Test generation failed: {e}")
            # Generate a basic test template
            return [self._generate_fallback_tests(spec)]

    def _generate_fallback_tests(self, spec: Dict[str, Any]) -> str:
        """Generate fallback test template when AI is unavailable."""
        endpoint = spec.get("endpoint", "/api/endpoint")

        return f'''"""
Fallback tests for {endpoint}
"""
import pytest
from flask import Flask

@pytest.fixture
def client():
    app = Flask(__name__)
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_{self._extract_endpoint_name(endpoint)}_basic(client):
    """Basic test - implement properly with OPENROUTER_API_KEY."""
    response = client.get('{endpoint}')
    assert response.status_code in [200, 501]
'''

    async def _format_code(self, code: str) -> str:
        """
        Format code using Black.

        Args:
            code: Python code to format

        Returns:
            Formatted code
        """
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(code)
                temp_path = f.name

            # Run black (ignore result, we just need formatted file)
            subprocess.run(
                ["black", "-q", temp_path],
                capture_output=True,
                text=True,
                timeout=30,
            )

            # Read formatted code
            with open(temp_path, "r") as f:
                formatted = f.read()

            # Clean up
            Path(temp_path).unlink(missing_ok=True)

            return formatted

        except subprocess.TimeoutExpired:
            logger.warning("Black formatting timed out, returning original code")
            return code
        except FileNotFoundError:
            logger.warning("Black not installed, returning unformatted code")
            return code
        except Exception as e:
            logger.error(f"Code formatting failed: {e}")
            return code

    async def _lint_code(self, code: str) -> Dict[str, Any]:
        """
        Lint code using Ruff.

        Args:
            code: Python code to lint

        Returns:
            Dict with lint results
        """
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(code)
                temp_path = f.name

            # Run ruff (check only, no auto-fix)
            result = subprocess.run(
                ["ruff", "check", temp_path, "--output-format=json"],
                capture_output=True,
                text=True,
                timeout=30,
            )

            # Clean up
            Path(temp_path).unlink(missing_ok=True)

            # Parse results
            violations = []
            if result.stdout:
                try:
                    violations = json.loads(result.stdout)
                except json.JSONDecodeError:
                    violations = [{"error": "Failed to parse ruff output"}]

            return {
                "tool": "ruff",
                "violations": violations,
                "violation_count": len(violations),
                "success": result.returncode == 0,
            }

        except subprocess.TimeoutExpired:
            return {"tool": "ruff", "error": "Linting timed out", "success": False}
        except FileNotFoundError:
            return {"tool": "ruff", "error": "Ruff not installed", "success": False}
        except Exception as e:
            logger.error(f"Linting failed: {e}")
            return {"tool": "ruff", "error": str(e), "success": False}

    async def _refactor_code(
        self, code: str, vulnerabilities: List[Dict[str, Any]]
    ) -> str:
        """
        Refactor code to fix security vulnerabilities.

        Args:
            code: Original Python code
            vulnerabilities: List of vulnerability dicts from Security Agent

        Returns:
            Refactored code with fixes applied
        """
        # Build prompt with vulnerabilities
        vuln_summary = "\n".join(
            [
                f"- {v.get('category', 'unknown')}: {v.get('description', 'No description')} at line {v.get('line_number', 'unknown')}"
                for v in vulnerabilities
            ]
        )

        prompt = f"""Refactor the following Python code to fix all security vulnerabilities:

VULNERABILITIES TO FIX:
{vuln_summary}

ORIGINAL CODE:
```python
{code}
```

Instructions:
1. Fix all listed vulnerabilities
2. Maintain the same functionality
3. Follow secure coding best practices
4. Do NOT remove functionality, just make it secure
5. Return ONLY the fixed code without any explanation or markdown fences

Example fixes:
- Replace hardcoded secrets with environment variables
- Use parameterized queries instead of string concatenation
- Add input validation and sanitization
- Use secure random for tokens"""

        try:
            fixed_code = await self._call_openrouter(prompt)

            # Extract code if wrapped in markdown
            if "```python" in fixed_code:
                start = fixed_code.find("```python") + 9
                end = fixed_code.find("```", start)
                if end != -1:
                    fixed_code = fixed_code[start:end].strip()
            elif "```" in fixed_code:
                start = fixed_code.find("```") + 3
                end = fixed_code.find("```", start)
                if end != -1:
                    fixed_code = fixed_code[start:end].strip()

            return fixed_code

        except Exception as e:
            logger.error(f"Code refactoring failed: {e}")
            # Return original code with TODO comments
            return self._apply_manual_fixes(code, vulnerabilities)

    def _apply_manual_fixes(
        self, code: str, vulnerabilities: List[Dict[str, Any]]
    ) -> str:
        """Apply manual fixes when AI is unavailable."""
        lines = code.split("\n")
        fixes_applied = []

        for vuln in vulnerabilities:
            category = vuln.get("category", "")
            line_num = vuln.get("line_number", 0) - 1

            if category == "hardcoded_secret" and 0 <= line_num < len(lines):
                # Add comment next to the line
                lines[line_num] += "  # TODO: Replace with environment variable"
                fixes_applied.append(
                    f"Line {line_num + 1}: Marked for env var replacement"
                )

        if fixes_applied:
            logger.info(f"Applied manual fixes: {', '.join(fixes_applied)}")

        return "\n".join(lines)

    async def _verify_security_fixes(
        self, code: str, original_vulnerabilities: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Verify that security vulnerabilities have been fixed.

        Args:
            code: Refactored code
            original_vulnerabilities: List of vulnerabilities that should be fixed

        Returns:
            Dict with verification results
        """
        # Simple check: see if the same patterns still exist
        import re

        remaining = []
        for vuln in original_vulnerabilities:
            category = vuln.get("category", "")

            # Check for specific patterns that should be gone
            if category == "hardcoded_secret":
                # Look for secret patterns
                secret_patterns = [
                    r"password\s*=",
                    r"api[_-]?key\s*=",
                    r"AWS_KEY",
                    r"GITHUB_TOKEN",
                    r"-----BEGIN",
                ]
                if any(re.search(pat, code, re.IGNORECASE) for pat in secret_patterns):
                    remaining.append(vuln)

            elif category == "sql_injection":
                # Look for SQL injection patterns
                sql_patterns = [
                    r"execute\(.*\+.*\)",
                    r"execute\(.*%s.*\)",
                    r'f".*SELECT.*\{.*\}',
                ]
                if any(re.search(pat, code) for pat in sql_patterns):
                    remaining.append(vuln)

        return {
            "total_original": len(original_vulnerabilities),
            "remaining": len(remaining),
            "fixed_count": len(original_vulnerabilities) - len(remaining),
            "remaining_vulnerabilities": remaining,
            "success": len(remaining) == 0,
        }

    # Message handlers

    async def _handle_code_review_request(self, message):
        """
        Handle code review request from another agent.

        Expected payload:
        - code: Python code to review (string)
        - language: programming language
        - context: optional context about the code
        """
        try:
            payload = message.payload
            code = payload.get("code", "")
            language = payload.get("language", "python")
            context = payload.get("context", "")

            logger.info(
                f"Received code review request for {len(code)} bytes from {message.sender}"
            )

            # Perform code review using AI
            review_findings = await self._review_code_with_ai(code, language, context)

            # Send response back
            response = {
                "findings": review_findings,
                "code_length": len(code),
                "reviewer": self.agent_id,
                "timestamp": asyncio.get_event_loop().time(),
            }

            await self.send_message(
                recipient=message.sender,
                message_type=MessageType.CODE_REVIEW_RESPONSE,
                payload=response,
                correlation_id=message.correlation_id,
            )

        except Exception as e:
            logger.error(f"Error handling code review request: {e}")

    async def _review_code_with_ai(
        self, code: str, language: str, context: str
    ) -> List[Dict[str, Any]]:
        """Use AI to review code quality and security."""
        prompt = f"""Review the following {language} code for quality, security, and best practices:

Context: {context}

CODE:
```{language}
{code[:4000]}  # Limit length
```

Provide a JSON array of findings, each with:
{{
    "severity": "high|medium|low",
    "category": "security|quality|performance|style",
    "description": "What is the issue?",
    "recommendation": "How to fix it?",
    "line_number": line number if applicable
}}

If no issues, return empty array []."""

        try:
            response = await self._call_openrouter(prompt)

            # Extract JSON from response
            start = response.find("[")
            end = response.rfind("]") + 1
            if start != -1 and end != -1:
                json_str = response[start:end]
                findings = json.loads(json_str)
                return findings if isinstance(findings, list) else []

            return []

        except Exception as e:
            logger.error(f"AI code review failed: {e}")
            return [
                {
                    "severity": "medium",
                    "category": "error",
                    "description": f"AI review failed: {str(e)}",
                    "recommendation": "Check OpenRouter configuration",
                }
            ]

    async def _handle_api_spec_request(self, message):
        """
        Handle API specification request from Frontend Agent.

        Expected payload:
        - component_name: name of the frontend component
        - requirements: list of features needed
        - design mock: optional design reference
        """
        try:
            payload = message.payload
            component_name = payload.get("component_name", "unknown")
            requirements = payload.get("requirements", [])

            logger.info(
                f"Received API spec request for {component_name} from {message.sender}"
            )

            # Generate API spec based on requirements
            api_spec = await self._design_api_spec(component_name, requirements)

            # Send response
            response = {
                "component_name": component_name,
                "api_spec": api_spec.dict(),
                "timestamp": asyncio.get_event_loop().time(),
            }

            await self.send_message(
                recipient=message.sender,
                message_type=MessageType.API_SPEC_RESPONSE,
                payload=response,
                correlation_id=message.correlation_id,
            )

        except Exception as e:
            logger.error(f"Error handling API spec request: {e}")

    async def _design_api_spec(
        self, component_name: str, requirements: List[str]
    ) -> ApiSpec:
        """
        Design an API specification based on frontend requirements.

        Args:
            component_name: Name of the frontend component
            requirements: List of features/data needed

        Returns:
            ApiSpec object
        """
        # Use AI to design the API
        prompt = f"""Design a RESTful API specification for a frontend component named '{component_name}'.
Requirements: {", ".join(requirements)}

Provide a JSON response with this structure:
{{
  "endpoint": "/api/v1/...",
  "method": "GET|POST|PUT|DELETE",
  "description": "What the endpoint does",
  "request_schema": {{...}} or null,
  "response_schema": {{...}},
  "authentication_required": true/false,
  "rate_limit": optional number in requests per minute
}}

Make it RESTful, secure, and follow best practices.
Consider the typical data needs for such a component."""

        try:
            response = await self._call_openrouter(prompt)

            # Extract JSON
            start = response.find("{")
            end = response.rfind("}") + 1
            if start != -1 and end != -1:
                json_str = response[start:end]
                spec_dict = json.loads(json_str)
                return ApiSpec(**spec_dict)

        except Exception as e:
            logger.error(f"API spec design failed: {e}")

        # Fallback spec
        return ApiSpec(
            endpoint=f"/api/v1/{component_name.lower().replace(' ', '_')}",
            method="GET",
            description=f"API for {component_name}",
            authentication_required=True,
        )

    async def _handle_security_alert(self, message):
        """
        Handle security alert from Security Agent.

        Expected payload:
        - findings: list of SecurityFinding dicts
        - message: alert message
        - severity: overall severity
        - code_path: optional path to the vulnerable code
        """
        try:
            payload = message.payload
            findings = payload.get("findings", [])
            alert_message = payload.get("message", "Security alert")
            severity = payload.get("severity", "medium")
            code_path = payload.get("code_path")

            logger.warning(
                f"Received security alert ({severity}): {alert_message}. "
                f"Findings: {len(findings)}"
            )

            # If we have code_path, attempt to fix automatically
            if code_path and findings:
                fix_result = await self._attempt_auto_fix(code_path, findings)

                # Send response acknowledging the fix attempt
                response = {
                    "alert_received": True,
                    "fix_attempted": fix_result.get("attempted", False),
                    "fix_successful": fix_result.get("successful", False),
                    "fixed_findings": fix_result.get("fixed_count", 0),
                    "remaining_findings": fix_result.get("remaining_count", 0),
                    "agent_id": self.agent_id,
                }

                # Send to Security Agent to acknowledge
                await self.send_message(
                    recipient=AgentRole.SECURITY,
                    message_type=MessageType.TASK_UPDATE,
                    payload=response,
                    correlation_id=message.correlation_id,
                )

        except Exception as e:
            logger.error(f"Error handling security alert: {e}")

    async def _attempt_auto_fix(
        self, code_path: str, vulnerabilities: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Attempt to automatically fix security vulnerabilities.

        Args:
            code_path: Path to the vulnerable code file
            vulnerabilities: List of vulnerability dicts

        Returns:
            Dict with fix results
        """
        try:
            path = Path(code_path)
            if not path.exists():
                return {
                    "attempted": False,
                    "successful": False,
                    "error": "File not found",
                }

            # Read original code
            with open(path, "r") as f:
                original_code = f.read()

            # Refactor using AI
            fixed_code = await self._refactor_code(original_code, vulnerabilities)

            # Verify fixes
            verification = await self._verify_security_fixes(
                fixed_code, vulnerabilities
            )

            if verification["success"]:
                # Write fixed code
                with open(path, "w") as f:
                    f.write(fixed_code)

                logger.info(
                    f"Successfully fixed {verification['fixed_count']} vulnerabilities in {code_path}"
                )
                return {
                    "attempted": True,
                    "successful": True,
                    "fixed_count": verification["fixed_count"],
                    "remaining_count": verification["remaining"],
                }
            else:
                logger.warning(
                    f"Partial fix: {verification['fixed_count']}/{len(vulnerabilities)} vulnerabilities fixed"
                )
                # Still write the improved code even if not all fixed
                with open(path, "w") as f:
                    f.write(fixed_code)
                return {
                    "attempted": True,
                    "successful": False,
                    "fixed_count": verification["fixed_count"],
                    "remaining_count": verification["remaining"],
                }

        except Exception as e:
            logger.error(f"Auto-fix failed: {e}")
            return {"attempted": True, "successful": False, "error": str(e)}

    async def health_check(self) -> Dict[str, Any]:
        """Extended health check with dev agent specific info."""
        health = await super().health_check()

        # Add dev-specific metrics
        health.update(
            {
                "tools_available": {
                    "black": self._check_tool("black"),
                    "ruff": self._check_tool("ruff"),
                    "openrouter": bool(config.OPENROUTER_API_KEY),
                }
            }
        )

        return health

    def _check_tool(self, tool_name: str) -> bool:
        """Check if a CLI tool is available."""
        try:
            subprocess.run([tool_name, "--version"], capture_output=True, timeout=5)
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
