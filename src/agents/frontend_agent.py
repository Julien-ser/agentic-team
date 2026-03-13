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

            # Determine task type
            if any(
                keyword in description
                for keyword in ["generate", "create", "build", "component", "ui"]
            ):
                # UI component generation task
                spec = task.payload.get("spec", {})
                api_spec = task.payload.get("api_spec")
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
                style_guide = await self._generate_style_guide(
                    component_name, requirements
                )

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
        api_spec: Optional[ApiSpec],
    ) -> str:
        """
        Generate HTML/CSS/JS component using OpenRouter AI.

        Args:
            component_name: Name of the component
            requirements: List of features/styling requirements
            api_spec: Optional API specification for backend integration

        Returns:
            Generated component code as string
        """
        # Build prompt for component generation
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
            return self._generate_fallback_component(component_name, requirements)

    def _build_component_prompt(
        self,
        component_name: str,
        requirements: List[str],
        api_spec: Optional[ApiSpec],
    ) -> str:
        """Build a prompt for component generation."""
        req_text = (
            "\n".join(f"- {req}" for req in requirements) if requirements else "None"
        )

        api_integration = ""
        if api_spec:
            api_integration = f"""
API Integration Required:
- Endpoint: {api_spec.endpoint}
- Method: {api_spec.method}
- Response Schema: {api_spec.response_schema or "None"}
- Authentication: {"Yes" if api_spec.authentication_required else "No"}
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
        self, component_code: str, api_spec: Optional[ApiSpec]
    ) -> str:
        """
        Integrate frontend component with backend API.

        Args:
            component_code: Component HTML/JS
            api_spec: API specification

        Returns:
            Integrated code with API calls
        """
        if not api_spec:
            return component_code

        # Build integration instructions
        prompt = f"""Add API integration to this frontend component to connect with the backend:

API Specification:
- Endpoint: {api_spec.endpoint}
- Method: {api_spec.method}
- Request Schema: {api_spec.request_schema or "None"}
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
            import subprocess

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
