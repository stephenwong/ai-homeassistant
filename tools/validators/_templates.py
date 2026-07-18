"""Shared Jinja2 template detection for validators."""

import re

TEMPLATE_PATTERN = re.compile(r"\{\{.*?\}\}|\{%.*?%\}", re.DOTALL)


def is_jinja_template(value: str) -> bool:
    """True if value contains a ``{{ ... }}`` or ``{% ... %}`` Jinja2 expression.

    Uses ``re.DOTALL`` so multi-line templates are detected. Callers that
    also need to detect HA tags (``!secret``, ``!include``) must check
    ``value.startswith('!')`` separately — this helper is pure Jinja2 detection.
    """
    return bool(TEMPLATE_PATTERN.search(value))
