# Copyright (c) 2026 xingluosama121, MIT Licensed
"""norpagent.security — plugin security suite (zero-dependency core + optional cryptography).

Migrated from the existing application's plugin_system / jailbreak_guard, reorganized
as a pip library:

- ``audit``: AST source auditing (dangerous calls / imports / reflection-bypass detection);
- ``network_policy``: plugin network policy / SSRF protection;
- ``approval``: human approval policy (native tool confirmation + plugin tool approval);
- ``guard``: jailbreak / prompt injection protection + system prompt hardening;
- ``signature``: Ed25519 plugin signatures (``norpagent[security]`` provides cryptography).

The full load pipeline (discover → signature verify → audit → import restrictions → register)
is documented in norpagent.plugins.loader.
"""

from norpagent.security.audit import (
    DANGEROUS_CALLS,
    DANGEROUS_FUNC_NAMES,
    DANGEROUS_IMPORTS,
    SecurityIssue,
    Severity,
    SourceAuditor,
    PluginSecurity,
)
from norpagent.security.approval import ApprovalLevel, ApprovalPolicy
from norpagent.security.guard import (
    CRITICAL_PATTERNS,
    WARNING_PATTERNS,
    ZERO_WIDTH_CHARS,
    harden_system_prompt,
    is_jailbreak_attempt,
    scan_message,
)
from norpagent.security.network_policy import (
    NetworkDecision,
    NetworkPolicy,
    is_internal_host,
)
from norpagent.security.signature import (
    SignatureResult,
    SignatureStatus,
    SignatureVerifier,
    crypto_available,
    generate_keypair,
    sign_plugin_file,
    verify_bytes,
)

__all__ = [
    "DANGEROUS_CALLS",
    "DANGEROUS_FUNC_NAMES",
    "DANGEROUS_IMPORTS",
    "SecurityIssue",
    "Severity",
    "SourceAuditor",
    "PluginSecurity",
    "ApprovalLevel",
    "ApprovalPolicy",
    "CRITICAL_PATTERNS",
    "WARNING_PATTERNS",
    "ZERO_WIDTH_CHARS",
    "harden_system_prompt",
    "is_jailbreak_attempt",
    "scan_message",
    "NetworkDecision",
    "NetworkPolicy",
    "is_internal_host",
    "SignatureResult",
    "SignatureStatus",
    "SignatureVerifier",
    "crypto_available",
    "generate_keypair",
    "sign_plugin_file",
    "verify_bytes",
]
