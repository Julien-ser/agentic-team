"""
Frontend Agent - UI/UX development specialist.

This agent generates HTML/CSS/JS components, ensures responsive design and
accessibility (WCAG), and integrates with backend APIs using Tailwind CSS.
"""

import asyncio
import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional

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


class FrontendAgent(BaseAgent):
    """
    Frontend development specialist agent with UI/UX capabilities.

    Capabilities:
    - Generate HTML/CSS/JS components from specifications using OpenRouter AI
    - Ensure responsive design using Tailwind CSS (via CDN)
    - Audit and enforce accessibility (WCAG 2.1 AA standards)
    - Integrate frontend components with backend APIs
    - Create component libraries and style guides
    - Handle API_SPEC_REQUEST from self (to request backend specs)
    - Process CODE_REVIEW_REQUEST for frontend code
    - Send COMPONENT_READY when components are complete
    """

    def __init__(self, agent_id=None, broker=None):
        super().__init__(agent_id, broker)
        self._shared_knowledge = {}

    # Accessibility patterns to check/enforce
    ACCESSIBILITY_PATTERNS = {
        "alt_text": {
            "pattern": r'<img[^>]*\s+alt=["\'][^"\']*["\']',
            "description": "Image should have alt attribute",
            "severity": "high",
            "wcag": "1.1.1",
        },
        "aria_label": {
            "pattern": r"(aria-label|aria-labelledby|aria-describedby)",
            "description": "Interactive elements should have ARIA labels",
            "severity": "medium",
            "wcag": "4.1.2",
        },
        "semantic_html": {
            "pattern": r"<(header|nav|main|footer|section|article|aside)",
            "description": "Use semantic HTML elements",
            "severity": "low",
            "wcag": "1.3.1",
        },
        "form_labels": {
            "pattern": r'<label[^>]*for=["\'][^"\']+["\']',
            "description": "Form inputs should have associated labels",
            "severity": "high",
            "wcag": "1.3.1",
        },
        "focus_visible": {
            "pattern": r":focus|:focus-visible",
            "description": "Interactive elements should have visible focus indicator",
            "severity": "medium",
            "wcag": "2.4.7",
        },
        "color_contrast": {
            "pattern": r"text-(red|green|blue|yellow|orange|purple)-(50|100|200)",
            "description": "Consider using higher contrast colors for readability",
            "severity": "medium",
            "wcag": "1.4.3",
        },
    }

    # Responsive design breakpoints (Tailwind standard)
    RESPONSIVE_BREAKPOINTS = {
        "sm": "640px",
        "md": "768px",
        "lg": "1024px",
        "xl": "1280px",
        "2xl": "1536px",
    }

    def get_role(self) -> AgentRole:
        """Return the frontend agent role."""
        return AgentRole.FRONTEND

    async def initialize(self) -> None:
        """Initialize frontend agent resources."""
        await super().initialize()

        # Register message handlers
        self.register_message_handler(
            MessageType.API_SPEC_RESPONSE, self._handle_api_spec_response
        )
        self.register_message_handler(
            MessageType.CODE_REVIEW_REQUEST, self._handle_code_review_request
        )
        self.register_message_handler(
            MessageType.SECURITY_ALERT, self._handle_security_alert
        )
        self.register_message_handler(
            MessageType.COMPONENT_UPDATE, self._handle_component_update
        )

        logger.info(f"Frontend agent {self.agent_id} initialized with handlers")

    async def process_task(self, task: Task) -> Dict[str, Any]:
        """
        Process a frontend development task.

        Args:
            task: Task with description and parameters

        Returns:
            Dict with results including generated component code, specs, etc.
        """
        start_time = asyncio.get_event_loop().time()

        try:
            task.mark_in_progress()
            description = task.description.lower()
            payload = task.payload or {}

            # Early returns for specific task types to avoid keyword conflicts
            if ("responsive" in description or "mobile" in description) and payload.get(
                "component_code"
            ):
                component_code = payload.get("component_code", "")
                enhanced_code = await self._ensure_responsive(component_code)
                return {
                    "success": True,
                    "output": {
                        "original_code": component_code[:200],
                        "responsive_code": enhanced_code,
                        "breakpoints_applied": list(self.RESPONSIVE_BREAKPOINTS.keys()),
                    },
                    "artifacts": [],
                    "execution_time": asyncio.get_event_loop().time() - start_time,
                }

            if any(
                kw in description for kw in ["accessibility", "a11y", "wcag"]
            ) and payload.get("component_code"):
                component_code = payload.get("component_code", "")
                a11y_report = await self._audit_accessibility(component_code)
                fixed_code = await self._fix_accessibility_issues(
                    component_code, a11y_report
                )
                return {
                    "success": True,
                    "output": {
                        "original_code": component_code[:200],
                        "fixed_code": fixed_code,
                        "accessibility_report": a11y_report,
                        "issues_found": len(a11y_report.get("issues", [])),
                        "wcag_compliance": a11y_report.get(
                            "compliance_level", "unknown"
                        ),
                    },
                    "artifacts": [],
                    "execution_time": asyncio.get_event_loop().time() - start_time,
                }

            if any(
                kw in description for kw in ["integrate", "api", "connect", "backend"]
            ) and payload.get("component_code"):
                component_code = payload.get("component_code", "")
                api_spec_dict = payload.get("api_spec")
                api_spec = None
                if api_spec_dict:
                    if isinstance(api_spec_dict, dict):
                        api_spec = ApiSpec(**api_spec_dict)
                    elif isinstance(api_spec_dict, ApiSpec):
                        api_spec = api_spec_dict
                if not api_spec:
                    api_spec_data = self.get_shared_knowledge("latest_api_spec")
                    if api_spec_data:
                        try:
                            api_spec_data = eval(api_spec_data)
                        except:
                            api_spec_data = None
                        if api_spec_data:
                            api_spec = ApiSpec(**api_spec_data)
                integrated_code = await self._integrate_backend_api(
                    component_code, api_spec
                )
                return {
                    "success": True,
                    "output": {
                        "original_code": component_code[:200],
                        "integrated_code": integrated_code,
                        "api_endpoint": api_spec.endpoint if api_spec else None,
                        "integration_method": api_spec.method if api_spec else None,
                    },
                    "artifacts": [],
                    "execution_time": asyncio.get_event_loop().time() - start_time,
                }

            if any(
                kw in description for kw in ["style guide", "design system"]
            ) and payload.get("components"):
                components = payload.get("components", [])
                style_guide = await self._create_style_guide(components)
                return {
                    "success": True,
                    "output": {
                        "style_guide": style_guide,
                        "components_included": components,
                        "tailwind_config": True,
                    },
                    "artifacts": [],
                    "execution_time": asyncio.get_event_loop().time() - start_time,
                }

            # Determine task type
            if any(
                keyword in description
                for keyword in ["generate", "create", "build", "component", "ui"]
            ):
                # UI component generation task
                spec = task.payload.get("spec", {})
                api_spec_dict = task.payload.get("api_spec")
                api_spec = None
                if api_spec_dict:
                    if isinstance(api_spec_dict, dict):
                        api_spec = ApiSpec(**api_spec_dict)
                    elif isinstance(api_spec_dict, ApiSpec):
                        api_spec = api_spec_dict
                component_name = spec.get("component_name", "UnnamedComponent")
                requirements = spec.get("requirements", [])

                # Generate component
                component_code = await self._generate_component(
                    component_name, requirements, api_spec
                )

                # Ensure responsive design
                responsive_code = await self._ensure_responsive(component_code)

                # Check accessibility
                a11y_report = await self._audit_accessibility(responsive_code)

                # Generate style guide/documentation
                style_guide = await self._create_style_guide([component_name])

                result = {
                    "success": True,
                    "output": {
                        "component_name": component_name,
                        "component_code": responsive_code,
                        "accessibility_report": a11y_report,
                        "style_guide": style_guide,
                        "requirements_met": self._check_requirements(
                            responsive_code, requirements
                        ),
                    },
                    "artifacts": [],
                    "execution_time": asyncio.get_event_loop().time() - start_time,
                }

                # Send COMPONENT_READY notification to dev agent
                try:
                    await self.send_message(
                        recipient=AgentRole.SW_DEV,
                        message_type=MessageType.COMPONENT_READY,
                        payload={
                            "component_name": component_name,
                            "code": responsive_code,
                            "accessibility_score": a11y_report.get("score", 0),
                            "requirements": requirements,
                        },
                        correlation_id=f"component-ready-{task.id[:8]}",
                    )
                    logger.info(
                        f"Sent COMPONENT_READY for {component_name} to dev agent"
                    )
                except Exception as e:
                    logger.warning(f"Failed to send COMPONENT_READY: {e}")

                return result

            elif "responsive" in description or "mobile" in description:
                # Responsive design task
                component_code = task.payload.get("component_code", "")
                enhanced_code = await self._ensure_responsive(component_code)

                return {
                    "success": True,
                    "output": {
                        "original_code": component_code[:200],
                        "responsive_code": enhanced_code,
                        "breakpoints_applied": list(self.RESPONSIVE_BREAKPOINTS.keys()),
                    },
                    "artifacts": [],
                    "execution_time": asyncio.get_event_loop().time() - start_time,
                }

            elif any(
                keyword in description for keyword in ["accessibility", "a11y", "wcag"]
            ):
                # Accessibility audit task
                component_code = task.payload.get("component_code", "")
                a11y_report = await self._audit_accessibility(component_code)
                fixed_code = await self._fix_accessibility_issues(
                    component_code, a11y_report
                )

                return {
                    "success": True,
                    "output": {
                        "original_code": component_code[:200],
                        "fixed_code": fixed_code,
                        "accessibility_report": a11y_report,
                        "issues_found": len(a11y_report.get("issues", [])),
                        "wcag_compliance": a11y_report.get(
                            "compliance_level", "unknown"
                        ),
                    },
                    "artifacts": [],
                    "execution_time": asyncio.get_event_loop().time() - start_time,
                }

            elif any(
                keyword in description
                for keyword in ["integrate", "api", "connect", "backend"]
            ):
                # API integration task
                component_code = task.payload.get("component_code", "")
                api_spec = task.payload.get("api_spec")
                if not api_spec:
                    # Try to fetch from shared state
                    api_spec_data = self.get_shared_knowledge("latest_api_spec")
                    if api_spec_data:
                        api_spec = ApiSpec(**eval(api_spec_data))

                integrated_code = await self._integrate_backend_api(
                    component_code, api_spec
                )

                return {
                    "success": True,
                    "output": {
                        "original_code": component_code[:200],
                        "integrated_code": integrated_code,
                        "api_endpoint": api_spec.endpoint if api_spec else None,
                        "integration_method": api_spec.method if api_spec else None,
                    },
                    "artifacts": [],
                    "execution_time": asyncio.get_event_loop().time() - start_time,
                }

            elif "style guide" in description or "design system" in description:
                # Style guide creation task
                components = task.payload.get("components", [])
                style_guide = await self._create_style_guide(components)

                return {
                    "success": True,
                    "output": {
                        "style_guide": style_guide,
                        "components_included": components,
                        "tailwind_config": True,
                    },
                    "artifacts": [],
                    "execution_time": asyncio.get_event_loop().time() - start_time,
                }

            else:
                # Default: treat as component generation
                spec = task.payload.get("spec", {"description": task.description})
                component_code = await self._generate_component(
                    spec.get("component_name", "Component"), [], None
                )

                return {
                    "success": True,
                    "output": {
                        "component_code": component_code,
                        "task_type": "general_component_generation",
                    },
                    "artifacts": [],
                    "execution_time": asyncio.get_event_loop().time() - start_time,
                }

        except Exception as e:
            logger.error(f"Frontend task failed: {e}", exc_info=True)
            raise

    async def _generate_component(
        self,
        component_name: str,
        requirements: List[str],
        api_spec: Optional[Any] = None,
    ) -> str:
        """
        Generate a frontend component using AI.

        Args:
            component_name: Name of the component to generate
            requirements: List of requirements and features
            api_spec: Optional API specification for backend integration

        Returns:
            Generated HTML/CSS/JS code as string
        """
        # Build prompt using existing helper
        prompt = self._build_component_prompt(component_name, requirements, api_spec)

        try:
            code = await self._call_openrouter(prompt)

            # Extract code from markdown blocks if present
            if "```html" in code:
                start = code.find("```html") + 7
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
            logger.error(f"Component generation failed: {e}")
            # Return basic fallback component
            return self._generate_fallback_component(component_name, requirements)

    def _generate_fallback_component(
        self, component_name: str, requirements: List[str]
    ) -> str:
        """Generate a basic fallback component when AI is unavailable."""
        req_text = (
            "\n".join(f"- {req}" for req in requirements)
            if requirements
            else "Standard UI component"
        )

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{component_name}</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-50 min-h-screen p-4">
    <main class="max-w-4xl mx-auto">
        <div class="bg-white rounded-lg shadow p-6">
            <h1 class="text-2xl font-bold text-gray-900 mb-4">{component_name}</h1>
            <p class="text-gray-600 mb-4">This is a generated component with the following requirements:</p>
            <ul class="list-disc pl-5 space-y-2 mb-6">
                {"".join(f"<li>{req}</li>" for req in requirements[:5])}
                {"<li>... and more</li>" if len(requirements) > 5 else ""}
            </ul>
            <div class="p-4 bg-blue-50 border border-blue-200 rounded">
                <p class="text-blue-800"><strong>Note:</strong> Set OPENROUTER_API_KEY to enable AI-powered component generation.</p>
            </div>
        </div>
    </main>
</body>
</html>"""

    async def _generate_login_form(
        self,
        api_spec: Optional[ApiSpec] = None,
        custom_validations: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Generate a production-ready responsive login form component.

        Args:
            api_spec: Optional API specification for authentication endpoint
            custom_validations: Optional custom validation rules (e.g., password requirements)

        Returns:
            Generated login form HTML/CSS/JS code as string
        """
        component_name = "LoginForm"
        requirements = [
            "responsive design",
            "accessible (WCAG 2.1 AA)",
            "form validation",
            "password visibility toggle",
            "remember me option",
            "authentication API integration",
            "loading states",
            "error handling",
            "keyboard navigation",
        ]

        if custom_validations:
            req_text = "\n".join(f"- {req}" for req in requirements)
            req_text += "\n- Custom validations: " + str(custom_validations)
        else:
            req_text = "\n".join(f"- {req}" for req in requirements)

        prompt = f"""Create a modern, production-ready login form component using HTML, CSS, and vanilla JavaScript.

Component: {component_name}

Requirements:
{req_text}

Technical Specifications:
1. Use Tailwind CSS via CDN: <script src="https://cdn.tailwindcss.com"></script>
2. Fully responsive with mobile-first approach
3. WCAG 2.1 AA compliant:
   - All form inputs have associated <label> elements
   - Proper ARIA attributes for error messages and hints
   - Keyboard accessible (Tab, Enter, Escape)
   - Visible focus indicators (2px solid blue ring)
   - Sufficient color contrast (minimum 4.5:1)
   - Error messages announced to screen readers with aria-live
4. Form fields:
   - Email input (required, type=email, autocomplete=username)
   - Password input (required, with show/hide toggle, autocomplete=current-password)
   - Remember me checkbox (optional)
   - Submit button with loading state
5. Client-side validation:
   - Email format validation (HTML5 + JS)
   - Password strength indicator (min 8 chars, uppercase, lowercase, number)
   - Real-time validation feedback
   - Error display with clear messages
6. API integration:
   - Submit form data via fetch() POST request
   - Handle authentication errors (401, 403, 429)
   - Store JWT token in localStorage on success
   - Redirect to dashboard on success
   - Show user-friendly error messages
7. UX features:
   - Smooth transitions and micro-interactions
   - Loading spinner during API call
   - Password strength meter with color coding
   - "Forgot password?" link placeholder
   - "Sign up" link placeholder
   - Auto-focus on email field on page load
8. Security:
   - Sanitize inputs to prevent XSS
   - Use textContent instead of innerHTML where possible
   - No inline event handlers (use addEventListener)
   - Proper escaping of dynamic content

Structure:
- Start with <!DOCTYPE html>
- Include Tailwind CDN, custom styles in <head>
- Use semantic HTML: <main>, <form>, <label>, <input>, <button>
- Add meta viewport for mobile
- Write clean, indented code with comments
- All JavaScript in <script> at end of body
- Include comprehensive error handling

Return ONLY the complete HTML code without any explanatory text. Do not include markdown fences."""

        try:
            code = await self._call_openrouter(prompt)

            # Extract code from markdown blocks if present
            if "```html" in code:
                start = code.find("```html") + 7
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
            logger.error(f"Login form generation failed: {e}")
            return self._generate_fallback_login_form(custom_validations)

    async def _generate_fallback_login_form(
        self, custom_validations: Optional[Dict[str, Any]] = None
    ) -> str:
        """Generate fallback login form when AI is unavailable."""
        val_rules = ""
        if custom_validations:
            val_rules = f"<li>Custom: {custom_validations}</li>"

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .password-toggle {{
            position: absolute;
            right: 12px;
            top: 50%;
            transform: translateY(-50%);
            cursor: pointer;
        }}
        .input-wrapper {{
            position: relative;
        }}
        .error-message {{
            color: #DC2626;
            font-size: 0.875rem;
            margin-top: 0.25rem;
        }}
        .success-message {{
            color: #059669;
            background: #D1FAE5;
            padding: 0.75rem;
            border-radius: 0.375rem;
            margin-bottom: 1rem;
        }}
        .loading-spinner {{
            border: 2px solid #E5E7EB;
            border-top: 2px solid #3B82F6;
            border-radius: 50%;
            width: 20px;
            height: 20px;
            animation: spin 1s linear infinite;
            display: inline-block;
            margin-right: 0.5rem;
        }}
        @keyframes spin {{
            0% {{ transform: rotate(0deg); }}
            100% {{ transform: rotate(360deg); }}
        }}
        .strength-meter {{
            height: 4px;
            border-radius: 2px;
            margin-top: 0.25rem;
            transition: all 0.3s ease;
        }}
        .strength-weak {{ background: #EF4444; width: 33%; }}
        .strength-medium {{ background: #F59E0B; width: 66%; }}
        .strength-strong {{ background: #10B981; width: 100%; }}
    </style>
</head>
<body class="bg-gradient-to-br from-blue-50 to-indigo-100 min-h-screen flex items-center justify-center p-4">
    <main class="w-full max-w-md">
        <div class="bg-white rounded-lg shadow-lg p-8">
            <div class="text-center mb-8">
                <h1 class="text-2xl font-bold text-gray-900">Welcome Back</h1>
                <p class="text-gray-600 mt-2">Sign in to your account</p>
            </div>

            <div id="errorContainer" class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4 hidden" role="alert" aria-live="polite"></div>
            <div id="successContainer" class="success-message hidden" role="status" aria-live="polite"></div>

            <form id="loginForm" novalidate>
                <div class="mb-6">
                    <label for="email" class="block text-sm font-medium text-gray-700 mb-2">
                        Email Address <span class="text-red-500" aria-label="required">*</span>
                    </label>
                    <input
                        type="email"
                        id="email"
                        name="email"
                        autocomplete="username"
                        required
                        aria-required="true"
                        aria-describedby="emailHelp emailError"
                        class="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition duration-200"
                        placeholder="you@example.com"
                    >
                    <p id="emailHelp" class="text-gray-500 text-sm mt-1">We'll never share your email</p>
                    <div id="emailError" class="error-message" role="alert" aria-live="polite"></div>
                </div>

                <div class="mb-4">
                    <label for="password" class="block text-sm font-medium text-gray-700 mb-2">
                        Password <span class="text-red-500" aria-label="required">*</span>
                    </label>
                    <div class="input-wrapper">
                        <input
                            type="password"
                            id="password"
                            name="password"
                            autocomplete="current-password"
                            required
                            aria-required="true"
                            aria-describedby="passwordHelp passwordError strengthMeter"
                            class="w-full px-4 py-3 pr-12 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition duration-200"
                            placeholder="Enter your password"
                        >
                        <button
                            type="button"
                            class="password-toggle text-gray-500 hover:text-gray-700"
                            aria-label="Toggle password visibility"
                            tabindex="0"
                        >
                            <svg id="eyeIcon" class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                            </svg>
                        </button>
                    </div>
                    <div class="strength-meter mt-2" id="strengthMeter" role="progressbar" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100"></div>
                    <p id="passwordHelp" class="text-gray-500 text-sm mt-1">Min 8 chars, uppercase, lowercase, number</p>
                    <div id="passwordError" class="error-message" role="alert" aria-live="polite"></div>
                </div>

                <div class="mb-6 flex items-center">
                    <input
                        type="checkbox"
                        id="rememberMe"
                        name="rememberMe"
                        class="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                    >
                    <label for="rememberMe" class="ml-2 block text-sm text-gray-700">
                        Remember me
                    </label>
                </div>

                <button
                    type="submit"
                    id="submitBtn"
                    class="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 px-4 rounded-lg focus:ring-4 focus:ring-blue-200 transition duration-200 focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed"
                >
                    <span id="btnText">Sign In</span>
                    <span id="btnLoading" class="loading-spinner hidden"></span>
                </button>
            </form>

            <div class="mt-6 text-center">
                <p class="text-sm text-gray-600">
                    Don't have an account?
                    <a href="/signup" class="text-blue-600 hover:text-blue-800 font-medium">Sign up</a>
                </p>
                <p class="text-sm text-gray-600 mt-2">
                    <a href="/forgot-password" class="text-blue-600 hover:text-blue-800">Forgot password?</a>
                </p>
            </div>
        </div>

        <p class="text-center text-gray-500 text-xs mt-4">
            Protected by industry-standard security
        </p>
    </main>

    <script>
        (function() {{
            const emailInput = document.getElementById('email');
            const passwordInput = document.getElementById('password');
            const emailError = document.getElementById('emailError');
            const passwordError = document.getElementById('passwordError');
            const errorContainer = document.getElementById('errorContainer');
            const successContainer = document.getElementById('successContainer');
            const strengthMeter = document.getElementById('strengthMeter');
            const submitBtn = document.getElementById('submitBtn');
            const btnText = document.getElementById('btnText');
            const btnLoading = document.getElementById('btnLoading');
            const passwordToggle = document.querySelector('.password-toggle');
            const eyeIcon = document.getElementById('eyeIcon');
            const loginForm = document.getElementById('loginForm');

            let passwordVisible = false;

            // Auto-focus email field
            document.addEventListener('DOMContentLoaded', () => {{
                emailInput.focus();
            }});

            // Password visibility toggle
            passwordToggle.addEventListener('click', () => {{
                passwordVisible = !passwordVisible;
                passwordInput.type = passwordVisible ? 'text' : 'password';

                if (passwordVisible) {{
                    eyeIcon.innerHTML = `
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                    `;
                }} else {{
                    eyeIcon.innerHTML = `
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                    `;
                }}
            }});

            // Password strength checker
            function calculatePasswordStrength(password) {{
                let score = 0;
                if (!password) return 0;

                if (password.length >= 8) score += 25;
                if (/[a-z]/.test(password)) score += 25;
                if (/[A-Z]/.test(password)) score += 25;
                if (/[0-9]/.test(password)) score += 25;

                return score;
            }}

            function updateStrengthMeter(password) {{
                const strength = calculatePasswordStrength(password);
                strengthMeter.className = 'strength-meter';

                if (strength < 50) {{
                    strengthMeter.classList.add('strength-weak');
                    strengthMeter.setAttribute('aria-valuenow', '33');
                    strengthMeter.title = 'Weak password';
                }} else if (strength < 100) {{
                    strengthMeter.classList.add('strength-medium');
                    strengthMeter.setAttribute('aria-valuenow', '66');
                    strengthMeter.title = 'Medium strength';
                }} else {{
                    strengthMeter.classList.add('strength-strong');
                    strengthMeter.setAttribute('aria-valuenow', '100');
                    strengthMeter.title = 'Strong password';
                }}
            }}

            passwordInput.addEventListener('input', () => {{
                updateStrengthMeter(passwordInput.value);
                validatePassword();
            }});

            // Email validation
            function validateEmail(email) {{
                const re = /^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$/;
                return re.test(email);
            }}

            function setFieldError(input, message) {{
                const errorEl = document.getElementById(input.id + 'Error');
                input.classList.add('border-red-500', 'focus:border-red-500', 'focus:ring-red-500');
                input.classList.remove('border-gray-300');
                errorEl.textContent = message;
                errorEl.classList.remove('hidden');
            }}

            function clearFieldError(input) {{
                const errorEl = document.getElementById(input.id + 'Error');
                input.classList.remove('border-red-500', 'focus:border-red-500', 'focus:ring-red-500');
                input.classList.add('border-gray-300');
                errorEl.classList.add('hidden');
                errorEl.textContent = '';
            }}

            function validateEmail() {{
                const email = emailInput.value.trim();
                if (!email) {{
                    setFieldError(emailInput, 'Email is required');
                    return false;
                }}
                if (!validateEmail(email)) {{
                    setFieldError(emailInput, 'Please enter a valid email address');
                    return false;
                }}
                clearFieldError(emailInput);
                return true;
            }}

            function validatePassword() {{
                const password = passwordInput.value;
                if (!password) {{
                    setFieldError(passwordInput, 'Password is required');
                    return false;
                }}
                if (password.length < 8) {{
                    setFieldError(passwordInput, 'Password must be at least 8 characters');
                    return false;
                }}
                if (!/[a-z]/.test(password)) {{
                    setFieldError(passwordInput, 'Password must contain a lowercase letter');
                    return false;
                }}
                if (!/[A-Z]/.test(password)) {{
                    setFieldError(passwordInput, 'Password must contain an uppercase letter');
                    return false;
                }}
                if (!/[0-9]/.test(password)) {{
                    setFieldError(passwordInput, 'Password must contain a number');
                    return false;
                }}
                clearFieldError(passwordInput);
                strengthMeter.classList.remove('strength-weak', 'strength-medium', 'strength-strong');
                return true;
            }}

            // Clear errors on input
            emailInput.addEventListener('input', validateEmail);
            passwordInput.addEventListener('input', validatePassword);

            // Form submission
            loginForm.addEventListener('submit', async (e) => {{
                e.preventDefault();

                const isEmailValid = validateEmail();
                const isPasswordValid = validatePassword();

                if (!isEmailValid || !isPasswordValid) {{
                    // Focus first invalid field
                    if (!isEmailValid) emailInput.focus();
                    else if (!isPasswordValid) passwordInput.focus();
                    return;
                }}

                const formData = {{
                    email: emailInput.value.trim(),
                    password: passwordInput.value,
                    remember_me: document.getElementById('rememberMe').checked
                }};

                // Disable form during submission
                submitBtn.disabled = true;
                btnText.textContent = 'Signing in...';
                btnLoading.classList.remove('hidden');
                errorContainer.classList.add('hidden');
                successContainer.classList.add('hidden');

                try {{
                    const response = await fetch('/api/v1/auth/login', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json',
                        }},
                        body: JSON.stringify(formData)
                    }});

                    const data = await response.json();

                    if (!response.ok) {{
                        if (response.status === 401) {{
                            throw new Error('Invalid email or password');
                        }} else if (response.status === 429) {{
                            throw new Error('Too many attempts. Please try again later.');
                        }} else {{
                            throw new Error(data.error || 'Authentication failed');
                        }}
                    }}

                    // Store JWT token
                    if (data.token) {{
                        localStorage.setItem('jwt_token', data.token);
                        localStorage.setItem('user', JSON.stringify(data.user));
                    }}

                    // Show success
                    successContainer.textContent = 'Login successful! Redirecting...';
                    successContainer.classList.remove('hidden');
                    errorContainer.classList.add('hidden');

                    // Redirect after short delay
                    setTimeout(() => {{
                        window.location.href = data.redirect_to || '/dashboard';
                    }}, 1000);

                }} catch (error) {{
                    errorContainer.textContent = error.message;
                    errorContainer.classList.remove('hidden');
                    successContainer.classList.add('hidden');
                }} finally {{
                    submitBtn.disabled = false;
                    btnText.textContent = 'Sign In';
                    btnLoading.classList.add('hidden');
                }}
            }});

            // Keyboard accessibility for password toggle
            passwordToggle.addEventListener('keydown', (e) => {{
                if (e.key === 'Enter' || e.key === ' ') {{
                    e.preventDefault();
                    passwordToggle.click();
                }}
            }});
        }})();
    </script>
</body>
</html>"""

    def _build_component_prompt(
        self,
        component_name: str,
        requirements: List[str],
        api_spec: Optional[Any],
    ) -> str:
        """Build a prompt for component generation."""
        req_text = (
            "\n".join(f"- {req}" for req in requirements) if requirements else "None"
        )

        api_integration = ""
        if api_spec:
            # Extract api_spec attributes - handle both ApiSpec object and dict
            if isinstance(api_spec, dict):
                endpoint = api_spec.get("endpoint", "N/A")
                method = api_spec.get("method", "N/A")
                response_schema = api_spec.get("response_schema")
                auth_required = api_spec.get("authentication_required", False)
            else:
                endpoint = getattr(api_spec, "endpoint", "N/A")
                method = getattr(api_spec, "method", "N/A")
                response_schema = getattr(api_spec, "response_schema", None)
                auth_required = getattr(api_spec, "authentication_required", False)

            api_integration = f"""
API Integration Required:
- Endpoint: {endpoint}
- Method: {method}
- Response Schema: {response_schema or "None"}
- Authentication: {"Yes" if auth_required else "No"}
"""
        else:
            api_integration = "No specific API integration required."

        prompt = f"""Create a modern, production-ready frontend component named '{component_name}' using HTML, CSS, and vanilla JavaScript.

Requirements:
{req_text}

{api_integration}

Technical Specifications:
1. Use Tailwind CSS via CDN: <script src="https://cdn.tailwindcss.com"></script>
2. Make it responsive (mobile-first approach)
3. Follow WCAG 2.1 AA accessibility guidelines:
   - All interactive elements must be keyboard accessible
   - Use semantic HTML tags
   - Include proper ARIA labels where needed
   - Ensure sufficient color contrast
4. Include proper error handling and loading states
5. Use modern JavaScript (ES6+) with no external dependencies except Tailwind
6. Add comments explaining complex logic
7. Make it self-contained in a single HTML file

Structure:
- Start with <!DOCTYPE html>
- Include Tailwind CDN in <head>
- Use <main> as container
- Add title and meta viewport
- Write clean, indented code
- If API integration needed, use fetch() with proper error handling

Return ONLY the complete HTML code without any explanatory text. Do not include markdown fences."""

        return prompt

    async def _ensure_responsive(self, component_code: str) -> str:
        """
        Enhance component to ensure responsive design.

        Args:
            component_code: HTML/CSS/JS code

        Returns:
            Enhanced code with responsive design patterns
        """
        # Check if already using Tailwind responsive classes
        has_responsive = any(
            f"md:{cls}" in component_code or f"lg:{cls}" in component_code
            for cls in ["hidden", "block", "flex", "grid", "text-", "p-", "m-"]
        )

        if has_responsive:
            return component_code

        # Use AI to add responsive design
        prompt = f"""Review this HTML/CSS component and enhance it to be fully responsive using Tailwind CSS.

Current code:
```html
{component_code[:4000]}
```

Requirements:
1. Add responsive breakpoints (sm, md, lg, xl) where appropriate
2. Use relative units (rem, %, vw, vh) instead of fixed pixels where possible
3. Ensure the layout adapts gracefully from mobile to desktop
4. Add mobile-first approach: default styles for mobile, override for larger screens
5. Keep all existing functionality intact

Return ONLY the enhanced HTML code without markdown fences."""

        try:
            enhanced = await self._call_openrouter(prompt)

            # Extract code if wrapped in markdown
            if "```html" in enhanced:
                start = enhanced.find("```html") + 7
                end = enhanced.find("```", start)
                if end != -1:
                    enhanced = enhanced[start:end].strip()
            elif "```" in enhanced:
                start = enhanced.find("```") + 3
                end = enhanced.find("```", start)
                if end != -1:
                    enhanced = enhanced[start:end].strip()

            return enhanced or component_code

        except Exception as e:
            logger.error(f"Responsive enhancement failed: {e}")
            return component_code

    async def _audit_accessibility(self, component_code: str) -> Dict[str, Any]:
        """
        Audit component for accessibility issues.

        Args:
            component_code: HTML/CSS/JS code

        Returns:
            Dictionary with accessibility report
        """
        issues = []
        compliance_level = "AA"  # Default target
        score = 100

        # Check using patterns
        for check_name, config in self.ACCESSIBILITY_PATTERNS.items():
            pattern = re.compile(config["pattern"])
            matches = pattern.findall(component_code)

            if not matches and check_name in [
                "alt_text",
                "form_labels",
                "aria_label",
            ]:
                # These should be present, so missing is an issue
                issues.append(
                    {
                        "category": check_name,
                        "description": config["description"],
                        "severity": config["severity"],
                        "wcag": config["wcag"],
                        "remediation": f"Add {check_name} to relevant elements",
                    }
                )
                score -= 20

        # Additional checks
        # Check for heading hierarchy (h1 should be first, don't skip levels)
        headings = re.findall(r"<h([1-6])", component_code)
        if headings:
            if "h1" not in headings[0]:
                issues.append(
                    {
                        "category": "heading_hierarchy",
                        "description": "Page should start with h1",
                        "severity": "medium",
                        "wcag": "1.3.1",
                        "remediation": "Add <h1> as first heading",
                    }
                )
                score -= 10

        # Check for skip links or navigation landmark
        if "<nav" in component_code or 'role="navigation"' in component_code:
            # Good, has navigation
            pass
        else:
            issues.append(
                {
                    "category": "navigation",
                    "description": "Consider adding skip links or navigation landmarks",
                    "severity": "low",
                    "wcag": "2.4.1",
                    "remediation": "Add <nav> element or skip links",
                }
            )
            score -= 5

        # Check color contrast by looking for potentially low-contrast colors
        low_contrast_patterns = [
            (r"text-gray-50", "light gray on white may have poor contrast"),
            (r"text-gray-100", "light gray on white may have poor contrast"),
            (r"bg-white.*text-gray-200", "white background with light gray text"),
        ]
        for pattern, desc in low_contrast_patterns:
            if re.search(pattern, component_code):
                issues.append(
                    {
                        "category": "color_contrast",
                        "description": f"Potential low contrast: {desc}",
                        "severity": "medium",
                        "wcag": "1.4.3",
                        "remediation": "Use higher contrast text colors or darker backgrounds",
                    }
                )
                score -= 10

        # Ensure score is within bounds
        score = max(0, min(100, score))

        return {
            "issues": issues,
            "score": score,
            "compliance_level": compliance_level if score >= 90 else "Partial",
            "total_issues": len(issues),
            "critical_issues": len([i for i in issues if i["severity"] == "high"]),
        }

    async def _fix_accessibility_issues(
        self, component_code: str, a11y_report: Dict[str, Any]
    ) -> str:
        """
        Fix accessibility issues in component code.

        Args:
            component_code: Original code
            a11y_report: Accessibility audit report

        Returns:
            Fixed code with accessibility improvements
        """
        if a11y_report["total_issues"] == 0:
            return component_code

        # Build prompt with issues to fix
        issues_list = "\n".join(
            f"- {issue['category']}: {issue['description']} (WCAG {issue['wcag']})"
            for issue in a11y_report["issues"]
        )

        prompt = f"""Fix the following accessibility issues in this HTML component:

Issues to fix:
{issues_list}

Original code:
```html
{component_code[:4000]}
```

Instructions:
1. Add missing alt attributes to images
2. Add ARIA labels to interactive elements without visible text
3. Ensure form inputs have associated labels
4. Add semantic HTML structure if missing (header, main, footer, etc.)
5. Add visible focus indicators (outline or ring)
6. Maintain all existing functionality and styling
7. Keep Tailwind CSS classes intact

Return ONLY the fixed HTML code without markdown fences."""

        try:
            fixed = await self._call_openrouter(prompt)

            # Extract code if wrapped
            if "```html" in fixed:
                start = fixed.find("```html") + 7
                end = fixed.find("```", start)
                if end != -1:
                    fixed = fixed[start:end].strip()
            elif "```" in fixed:
                start = fixed.find("```") + 3
                end = fixed.find("```", start)
                if end != -1:
                    fixed = fixed[start:end].strip()

            return fixed or component_code

        except Exception as e:
            logger.error(f"Accessibility fix failed: {e}")
            return component_code

    async def _integrate_backend_api(
        self, component_code: str, api_spec: Optional[Any]
    ) -> str:
        """
        Integrate frontend component with backend API.

        Args:
            component_code: Component HTML/JS
            api_spec: API specification (ApiSpec object or dict)

        Returns:
            Integrated code with API calls
        """
        # Convert dict to ApiSpec if needed
        if api_spec and isinstance(api_spec, dict):
            try:
                api_spec = ApiSpec(**api_spec)
            except Exception as e:
                logger.warning(f"Failed to convert api_spec dict to ApiSpec: {e}")
                api_spec = None

        if not api_spec:
            return component_code

        # Build integration instructions
        prompt = f"""Add API integration to this frontend component to connect with the backend:

API Specification:
- Endpoint: {api_spec.endpoint}
- Method: {api_spec.method}
- Response Schema: {api_spec.response_schema or "None"}
- Authentication Required: {api_spec.authentication_required}

Current component code:
```html
{component_code[:4000]}
```

Requirements:
1. Add JavaScript functions to call the API using fetch()
2. Include proper error handling and loading states
3. Parse response according to response_schema
4. Display data appropriately in the component
5. If authentication required, include JWT token in Authorization header (get from localStorage or cookie)
6. Show user-friendly error messages
7. Add loading indicator while API call is in progress

Return ONLY the enhanced HTML code with integrated JavaScript. Do not include markdown fences."""

        try:
            integrated = await self._call_openrouter(prompt)

            # Extract code
            if "```html" in integrated:
                start = integrated.find("```html") + 7
                end = integrated.find("```", start)
                if end != -1:
                    integrated = integrated[start:end].strip()
            elif "```" in integrated:
                start = integrated.find("```") + 3
                end = integrated.find("```", start)
                if end != -1:
                    integrated = integrated[start:end].strip()

            return integrated or component_code

        except Exception as e:
            logger.error(f"API integration failed: {e}")
            return component_code

    async def _create_style_guide(self, components: List[str]) -> Dict[str, Any]:
        """
        Create a style guide for component library.

        Args:
            components: List of component names or specs

        Returns:
            Style guide dictionary
        """
        # Build prompt for style guide generation
        components_text = (
            "\n".join(f"- {c}" for c in components) if components else "All components"
        )

        prompt = f"""Create a comprehensive style guide for the following frontend components:

Components:
{components_text}

The style guide should include:
1. Color palette (primary, secondary, accent, neutral, semantic colors)
2. Typography scale (headings, body, captions)
3. Spacing system (based on 4px or 8px grid)
4. Component usage guidelines with examples
5. Accessibility notes
6. Responsive behavior guidelines

Format the response as a JSON object with these keys:
- colors: dict of color names and hex values
- typography: dict with font families and sizes
- spacing: dict with spacing scale
- components: list of component usage guidelines
- accessibility: dict with a11y requirements"""

        try:
            response = await self._call_openrouter(prompt)

            # Extract JSON from response
            start = response.find("{")
            end = response.rfind("}") + 1
            if start != -1 and end != -1:
                json_str = response[start:end]
                import json

                guide = json.loads(json_str)
                return guide

        except Exception as e:
            logger.error(f"Style guide creation failed: {e}")

        # Fallback style guide
        return {
            "colors": {
                "primary": "#3B82F6",
                "secondary": "#10B981",
                "accent": "#F59E0B",
                "neutral": "#6B7280",
                "background": "#FFFFFF",
                "text": "#111827",
                "error": "#EF4444",
                "success": "#10B981",
            },
            "typography": {
                "font_family": "system-ui, -apple-system, sans-serif",
                "heading_1": "2.25rem / 2.5rem (bold)",
                "heading_2": "1.875rem / 2.25rem (bold)",
                "heading_3": "1.5rem / 1.75rem (semibold)",
                "body": "1rem / 1.5rem (normal)",
                "small": "0.875rem / 1.25rem (normal)",
            },
            "spacing": {
                "xs": "0.25rem (4px)",
                "sm": "0.5rem (8px)",
                "md": "1rem (16px)",
                "lg": "1.5rem (24px)",
                "xl": "2rem (32px)",
                "2xl": "3rem (48px)",
            },
            "components": components,
            "accessibility": {
                "min_contrast_ratio": "4.5:1",
                "focus_indicator": "2px solid primary color",
                "touch_target_min": "44x44px",
                "keyboard_navigation": "Required for all interactive elements",
            },
        }

    def _check_requirements(
        self, component_code: str, requirements: List[str]
    ) -> Dict[str, bool]:
        """Check if component meets specified requirements."""
        results = {}

        for req in requirements:
            req_lower = req.lower()
            if "responsive" in req_lower or "mobile" in req_lower:
                results[req] = any(
                    f"{bp}:" in component_code
                    for bp in self.RESPONSIVE_BREAKPOINTS.keys()
                )
            elif "accessible" in req_lower or "a11y" in req_lower:
                results[req] = any(
                    pattern in component_code
                    for pattern in ["aria-", "alt=", "<label", "<main", "<nav"]
                )
            elif "tailwind" in req_lower:
                results[req] = "tailwind" in component_code.lower()
            elif "api" in req_lower or "fetch" in req_lower:
                results[req] = "fetch(" in component_code or "axios" in component_code
            else:
                results[req] = True  # Assume met by default

        return results

    def _check_tool(self, tool_name: str) -> bool:
        """Check if a CLI tool is available."""
        try:
            subprocess.run([tool_name, "--version"], capture_output=True, timeout=5)
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    async def health_check(self) -> Dict[str, Any]:
        """Extended health check with frontend-specific info."""
        health = await super().health_check()

        health.update(
            {
                "tools_available": {
                    "tailwind_ready": True,  # Using CDN, so always available
                    "openrouter": bool(config.OPENROUTER_API_KEY),
                },
                "accessibility_checks_loaded": len(self.ACCESSIBILITY_PATTERNS),
                "responsive_breakpoints": list(self.RESPONSIVE_BREAKPOINTS.keys()),
            }
        )

        return health

    # Message handlers

    async def _handle_api_spec_response(self, message):
        """
        Handle API spec response from Software Dev Agent.

        Expected payload:
        - component_name: name of the component
        - api_spec: ApiSpec object as dict
        - timestamp: when spec was generated
        """
        try:
            payload = message.payload
            component_name = payload.get("component_name", "unknown")
            api_spec_dict = payload.get("api_spec", {})

            logger.info(f"Received API spec for {component_name} from {message.sender}")

            # Store API spec in shared knowledge
            api_spec = ApiSpec(**api_spec_dict)
            self.set_shared_knowledge(
                f"api_spec:{component_name}", str(api_spec_dict), message.sender.value
            )
            self.set_shared_knowledge("latest_api_spec", str(api_spec_dict), "sw_dev")

            # If we have a pending task for this component, could trigger generation
            # For now, just store the spec

        except Exception as e:
            logger.error(f"Error handling API spec response: {e}")

    async def _handle_code_review_request(self, message):
        """
        Handle code review request from another agent.

        Expected payload:
        - code: HTML/CSS/JS code to review
        - language: programming language (should be html, css, or javascript)
        - context: optional context about the component
        """
        try:
            payload = message.payload
            code = payload.get("code", "")
            language = payload.get("language", "html")
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
                "language": language,
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

    async def _handle_security_alert(self, message):
        """
        Handle security alert from Security Agent.

        Expected payload:
        - findings: list of security findings
        - message: alert message
        - severity: overall severity
        - code_path: optional path to vulnerable code
        """
        try:
            payload = message.payload
            findings = payload.get("findings", [])
            alert_message = payload.get("message", "Security alert")
            severity = payload.get("severity", "medium")
            code_path = payload.get("code_path")

            logger.warning(
                f"Received frontend security alert ({severity}): {alert_message}. "
                f"Findings: {len(findings)}"
            )

            # If we have code_path, attempt to fix frontend-specific vulnerabilities
            if code_path and findings:
                try:
                    path = Path(code_path)
                    if path.exists():
                        with open(path, "r") as f:
                            code = f.read()

                        # Fix issues (XSS, inline scripts, etc.)
                        fixed_code = await self._fix_security_vulnerabilities(
                            code, findings
                        )

                        # Write back
                        with open(path, "w") as f:
                            f.write(fixed_code)

                        # Send acknowledgment
                        response = {
                            "alert_received": True,
                            "fix_attempted": True,
                            "fix_successful": True,
                            "agent_id": self.agent_id,
                        }

                        await self.send_message(
                            recipient=AgentRole.SECURITY,
                            message_type=MessageType.TASK_UPDATE,
                            payload=response,
                            correlation_id=message.correlation_id,
                        )
                except Exception as e:
                    logger.error(f"Failed to fix security vulnerabilities: {e}")

        except Exception as e:
            logger.error(f"Error handling security alert: {e}")

    async def _handle_component_update(self, message):
        """
        Handle component update from another agent (e.g., dev agent updating shared component).

        Expected payload:
        - component_name: name of the component
        - updated_code: new component code
        - changes: description of what changed
        - version: optional version number
        """
        try:
            payload = message.payload
            component_name = payload.get("component_name", "unknown")
            updated_code = payload.get("updated_code", "")
            changes = payload.get("changes", [])

            logger.info(
                f"Received component update for {component_name} from {message.sender}"
            )

            # Store updated component in shared knowledge
            self.set_shared_knowledge(
                f"component:{component_name}", updated_code, message.sender.value
            )

            # Could trigger re-render or integration testing

        except Exception as e:
            logger.error(f"Error handling component update: {e}")

    async def _review_code_with_ai(
        self, code: str, language: str, context: str
    ) -> List[Dict[str, Any]]:
        """Use AI to review frontend code quality, accessibility, and security."""
        prompt = f"""Review the following {language} frontend code for quality, accessibility, security, and best practices.

Context: {context}

CODE:
```{language}
{code[:4000]}
```

Provide a JSON array of findings, each with:
{{
    "severity": "high|medium|low",
    "category": "accessibility|security|quality|performance|usability",
    "description": "What is the issue?",
    "recommendation": "How to fix it?",
    "line_number": line number if applicable
}}

Focus on:
- WCAG 2.1 AA compliance (alt text, ARIA, keyboard navigation)
- XSS vulnerabilities (innerHTML, eval, unsafe event handlers)
- Responsive design issues
- Code quality and maintainability
- Performance (unoptimized images, large bundles)
- Browser compatibility

If no issues, return empty array []."""

        try:
            response = await self._call_openrouter(prompt)

            # Extract JSON from response
            start = response.find("[")
            end = response.rfind("]") + 1
            if start != -1 and end != -1:
                json_str = response[start:end]
                import json

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

    async def _fix_security_vulnerabilities(
        self, code: str, vulnerabilities: List[Dict[str, Any]]
    ) -> str:
        """Fix security vulnerabilities in frontend code."""
        vuln_summary = "\n".join(
            f"- {v.get('category', 'unknown')}: {v.get('description', 'No description')}"
            for v in vulnerabilities
        )

        prompt = f"""Fix the following security vulnerabilities in this HTML/JavaScript code:

VULNERABILITIES:
{vuln_summary}

Original code:
```html
{code[:4000]}
```

Fix these common frontend issues:
1. XSS: Replace innerHTML with textContent or safe DOM methods
2. Inline event handlers (onclick, onerror, etc.) - use addEventListener instead
3. eval() or Function() constructor - remove and use safer alternatives
4. Unsafe data URLs - sanitize or avoid
5. Mixed content (HTTP URLs on HTTPS page) - use protocol-relative or HTTPS
6. Missing CSRF protection if forms exist - add tokens or use same-origin

Return ONLY the fixed code. Do not include markdown fences."""

        try:
            fixed = await self._call_openrouter(prompt)

            if "```html" in fixed:
                start = fixed.find("```html") + 7
                end = fixed.find("```", start)
                if end != -1:
                    fixed = fixed[start:end].strip()
            elif "```" in fixed:
                start = fixed.find("```") + 3
                end = fixed.find("```", start)
                if end != -1:
                    fixed = fixed[start:end].strip()

            return fixed or code

        except Exception as e:
            logger.error(f"Security fix failed: {e}")
            return code

    async def _call_openrouter(self, prompt: str) -> str:
        """
        Call OpenRouter API for AI code generation.

        Args:
            prompt: The prompt to send to the AI model

        Returns:
            Generated text response
        """
        api_key = config.OPENROUTER_API_KEY
        if not api_key:
            logger.warning("OPENROUTER_API_KEY not set, using fallback generation")
            raise ValueError("OpenRouter API key not configured")

        model = config.WIGGUM_MODEL

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/anomalyco/opencode",
            "X-Title": "Agentic-Team Frontend Agent",
        }

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are an expert frontend developer specializing in accessible, responsive UI components with Tailwind CSS. Always follow WCAG guidelines and best practices for security and performance.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 4000,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=90),
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

    def _generate_fallback_component(
        self, component_name: str, requirements: List[str]
    ) -> str:
        """Generate fallback component when AI is unavailable."""
        reqs = ", ".join(requirements) if requirements else "basic UI"

        return f"""<!DOCTYPE html>
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
            <p class="text-gray-600 mb-4">Requirements: {reqs}</p>
            <div class="bg-yellow-100 border-l-4 border-yellow-500 p-4 mb-4">
                <p class="text-yellow-700">
                    <strong>Note:</strong> Configure OPENROUTER_API_KEY for AI-generated components.
                </p>
            </div>
            <!-- Component content will be generated here -->
            <div class="mt-4">
                <button class="bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded">
                    Example Button
                </button>
            </div>
        </div>
    </main>
</body>
</html>"""
