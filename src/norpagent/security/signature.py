# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Plugin signature / provenance verification (NORP plugin signature protocol v1).

Migrated from the existing application's plugin_system.signature; protocol unchanged:

- algorithm: Ed25519 (cryptography library, lazily loaded on demand);
- signed object: SHA-256 digest of the plugin entry file bytes;
- signature storage: the manifest.json "signature" field / sidecar ``<entry>.sig`` file;
- trust model: built-in official public key + user-configured trusted keys
  (config → plugin_trusted_keys).

Note: ``cryptography`` is an optional dependency (``pip install norpagent[security]``).
When it is not installed, signature verification returns UNAVAILABLE — treated as
"untrusted" (never trusted); the security posture is not relaxed by a missing dependency.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

ALGORITHM = "ed25519"

# NORP Studio official public key (signs official plugins; the private key stays on the developer's machine).
OFFICIAL_PUBLIC_KEY = "199adcb6801cb969212120487df0b1af4c9099f1ec597873cd9f6216cea09178"
# dedicated signature public key for the vision companion (trusted alongside the official key).
VISION_PUBLIC_KEY = "5cefeac5f416786edae0373b8fdff9d07702547441f5cda9a640b79a960c406a"


class SignatureStatus:
    TRUSTED = "trusted"
    UNTRUSTED = "untrusted"
    INVALID = "invalid"
    UNSIGNED = "unsigned"
    DISABLED = "disabled"
    UNAVAILABLE = "unavailable"  # missing cryptography: treated as untrusted


@dataclass
class SignatureResult:
    """The result of one signature verification."""

    status: str
    reason: str = ""
    public_key: str = ""
    signed_files: List[str] = field(default_factory=list)
    verified_files: List[str] = field(default_factory=list)

    @property
    def is_trusted(self) -> bool:
        return self.status == SignatureStatus.TRUSTED

    @property
    def passed(self) -> bool:
        """Whether to "let through": trusted or disabled (verification off) count as passing."""
        return self.status in (SignatureStatus.TRUSTED, SignatureStatus.DISABLED)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "reason": self.reason,
            "public_key": self.public_key,
            "signed_files": self.signed_files,
            "verified_files": self.verified_files,
        }


# ── low-level Ed25519 primitives (lazy imports) ─────────

def _import_ed25519():
    """Lazily import cryptography; returns None on failure (callers treat it as UNAVAILABLE)."""
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # type: ignore
            Ed25519PrivateKey,
            Ed25519PublicKey,
        )
        from cryptography.hazmat.primitives import serialization  # type: ignore

        return Ed25519PrivateKey, Ed25519PublicKey, serialization
    except ImportError:
        return None


def crypto_available() -> bool:
    return _import_ed25519() is not None


def hash_file(path: str) -> bytes:
    """Compute the SHA-256 digest of a file's content."""
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).digest()


def generate_keypair() -> Optional[Tuple[str, str]]:
    """Generate an Ed25519 key pair; returns (public key hex, private key hex). None when the dependency is missing."""
    loaded = _import_ed25519()
    if loaded is None:
        return None
    Ed25519PrivateKey, _, serialization = loaded
    key = Ed25519PrivateKey.generate()
    pub = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    ).hex()
    priv = key.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    ).hex()
    return pub, priv


def sign_bytes(privkey_hex: str, data: bytes) -> bytes:
    """Sign data with an Ed25519 private key (raises RuntimeError when the dependency is missing)."""
    loaded = _import_ed25519()
    if loaded is None:
        raise RuntimeError(
            "plugin signing requires the cryptography library (pip install norpagent[security])"
        )
    Ed25519PrivateKey, _, _ = loaded
    key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(privkey_hex))
    return key.sign(data)


def verify_bytes(pubkey_hex: str, signature_hex: str, data: bytes) -> bool:
    """Verify a signature with an Ed25519 public key (returns False when the dependency is missing)."""
    loaded = _import_ed25519()
    if loaded is None:
        return False
    try:
        _, Ed25519PublicKey, _ = loaded
        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pubkey_hex))
        key.verify(bytes.fromhex(signature_hex), data)
        return True
    except Exception:
        return False


# ── signature storage formats ───────────────────────────

def build_signature_block(pubkey_hex: str, signature_hex: str,
                          signed_files: Optional[List[str]] = None) -> dict:
    """Build a signature block (written to the manifest "signature" field or a .sig file)."""
    block = {
        "algorithm": ALGORITHM,
        "public_key": pubkey_hex,
        "signature": signature_hex,
    }
    if signed_files:
        block["signed_files"] = signed_files
    return block


def sign_plugin_file(entry_path: str, privkey_hex: str) -> dict:
    """Sign a plugin entry file, write the sidecar ``<entry>.sig``, and return the signature block.

    Consistent with the existing application's _sign_plugin.sign_file: the signed
    object is the SHA-256 digest of the entry file bytes; signed_files is fixed to
    [basename of the entry file].
    """
    import os.path

    entry_path = os.path.abspath(entry_path)
    digest = hash_file(entry_path)
    sig_hex = sign_bytes(privkey_hex, digest).hex()
    block = build_signature_block(
        _pubkey_from_priv(privkey_hex), sig_hex,
        signed_files=[os.path.basename(entry_path)],
    )
    _write_sidecar(entry_path + ".sig", block)
    return block


def _pubkey_from_priv(privkey_hex: str) -> str:
    loaded = _import_ed25519()
    if loaded is None:
        raise RuntimeError(
            "plugin signing requires the cryptography library (pip install norpagent[security])"
        )
    Ed25519PrivateKey, _, serialization = loaded
    key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(privkey_hex))
    return key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    ).hex()


def _write_sidecar(sig_path: str, block: dict) -> None:
    with open(sig_path, "w", encoding="utf-8") as fh:
        json.dump(block, fh, ensure_ascii=False, indent=2)


def _load_sig_sidecar(entry_path: str) -> Optional[dict]:
    sig_path = entry_path + ".sig"
    if not os.path.isfile(sig_path):
        return None
    try:
        with open(sig_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _extract_signature_block(entry_path: str,
                             manifest: Optional[dict]) -> Optional[dict]:
    if manifest:
        sig = manifest.get("signature")
        if isinstance(sig, dict) and sig.get("signature"):
            return sig
    return _load_sig_sidecar(entry_path)


# ── signature verifier ──────────────────────────────────


class SignatureVerifier:
    """Plugin signature verifier."""

    def __init__(self, config: Optional[dict] = None) -> None:
        config = config or {}
        self.enabled: bool = bool(config.get("plugin_signature_verify", True))
        self._trusted_keys: List[str] = [OFFICIAL_PUBLIC_KEY, VISION_PUBLIC_KEY]
        user_keys = config.get("plugin_trusted_keys", [])
        if isinstance(user_keys, (list, tuple)):
            for k in user_keys:
                if isinstance(k, str) and k.strip():
                    self._trusted_keys.append(k.strip())

    @property
    def trusted_keys(self) -> List[str]:
        return list(self._trusted_keys)

    def add_trusted_key(self, pubkey_hex: str) -> None:
        if pubkey_hex and pubkey_hex not in self._trusted_keys:
            self._trusted_keys.append(pubkey_hex)

    def is_trusted_key(self, pubkey_hex: str) -> bool:
        return pubkey_hex in self._trusted_keys

    def verify(self, entry_path: str,
               manifest: Optional[dict] = None) -> SignatureResult:
        """Verify the signature of a plugin entry file; returns a SignatureResult."""
        if not self.enabled:
            return SignatureResult(
                status=SignatureStatus.DISABLED, reason="signature verification is disabled",
            )
        if not crypto_available():
            return SignatureResult(
                status=SignatureStatus.UNAVAILABLE,
                reason="cryptography is not installed (pip install norpagent[security]); signatures treated as untrusted",
            )

        block = _extract_signature_block(entry_path, manifest)
        if not block:
            return SignatureResult(
                status=SignatureStatus.UNSIGNED,
                reason="plugin is not signed (manifest.signature or .sig file missing)",
            )
        pubkey = block.get("public_key", "")
        signature = block.get("signature", "")
        algorithm = block.get("algorithm", ALGORITHM)
        if not pubkey or not signature:
            return SignatureResult(
                status=SignatureStatus.INVALID,
                reason="signature block is missing the public_key or signature field",
            )
        if algorithm != ALGORITHM:
            return SignatureResult(
                status=SignatureStatus.INVALID,
                reason=f"unsupported signature algorithm: {algorithm}",
            )

        signed_files = block.get("signed_files") or []
        if not signed_files:
            signed_files = [os.path.basename(entry_path)]

        verified = []
        entry_dir = os.path.dirname(os.path.abspath(entry_path))
        for rel_name in signed_files:
            full = rel_name if os.path.isabs(rel_name) else os.path.join(entry_dir, rel_name)
            if not os.path.isfile(full):
                return SignatureResult(
                    status=SignatureStatus.INVALID,
                    reason=f"file listed in the signature manifest does not exist: {rel_name}",
                    public_key=pubkey,
                    signed_files=signed_files,
                )
            digest = hash_file(full)
            if not verify_bytes(pubkey, signature, digest):
                return SignatureResult(
                    status=SignatureStatus.INVALID,
                    reason=f"signature verification failed: file tampered or signature mismatch ({rel_name})",
                    public_key=pubkey,
                    signed_files=signed_files,
                    verified_files=verified,
                )
            verified.append(rel_name)

        if self.is_trusted_key(pubkey):
            return SignatureResult(
                status=SignatureStatus.TRUSTED,
                reason="signature valid and public key trusted",
                public_key=pubkey,
                signed_files=signed_files,
                verified_files=verified,
            )
        return SignatureResult(
            status=SignatureStatus.UNTRUSTED,
            reason="signature valid but public key not in the trusted-key list",
            public_key=pubkey,
            signed_files=signed_files,
            verified_files=verified,
        )
