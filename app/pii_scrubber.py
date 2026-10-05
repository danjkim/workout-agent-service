# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""PII Scrubbing and Data Sanitization Utilities.

Provides regex-based and rule-based scrubbing for sensitive personally identifiable
information (PII) including emails, phone numbers, credit card numbers, SSNs,
and medical identifiers before logging, telemetry emission, or memory persistence.
"""

from __future__ import annotations

import re
from typing import Any

# Regex patterns for common PII categories
_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_PATTERN = re.compile(
    r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b"
)
_SSN_PATTERN = re.compile(r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b")
_CREDIT_CARD_PATTERN = re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b|\b\d{15,16}\b")
_HEALTH_ID_PATTERN = re.compile(
    r"\b(?:MRN|MED|RX|DOB|PATIENT)[\s:#-]*[A-Z0-9]{6,12}\b", re.IGNORECASE
)


def scrub_pii(text: str) -> str:
    """Scrub sensitive personal information from a string.

    Args:
        text: Raw input string potentially containing PII.

    Returns:
        Sanitized string with sensitive tokens replaced by redaction placeholders.
    """
    if not isinstance(text, str):
        return text

    sanitized = _EMAIL_PATTERN.sub("[REDACTED_EMAIL]", text)
    sanitized = _PHONE_PATTERN.sub("[REDACTED_PHONE]", sanitized)
    sanitized = _SSN_PATTERN.sub("[REDACTED_SSN]", sanitized)
    sanitized = _CREDIT_CARD_PATTERN.sub("[REDACTED_CREDIT_CARD]", sanitized)
    sanitized = _HEALTH_ID_PATTERN.sub("[REDACTED_HEALTH_ID]", sanitized)
    return sanitized


def scrub_dict_pii(data: Any) -> Any:
    """Recursively scrub PII across nested dicts, lists, and primitives.

    Args:
        data: Arbitrary data structure (dict, list, string, or primitive).

    Returns:
        Deep sanitized copy with PII scrubbed from all string values.
    """
    if isinstance(data, dict):
        return {key: scrub_dict_pii(val) for key, val in data.items()}
    elif isinstance(data, list):
        return [scrub_dict_pii(item) for item in data]
    elif isinstance(data, str):
        return scrub_pii(data)
    return data
