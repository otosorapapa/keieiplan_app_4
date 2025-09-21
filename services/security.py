"""Security related utilities (transport enforcement, sanitisation)."""
from __future__ import annotations

import streamlit as st


HTTPS_REDIRECT_SCRIPT = """
<script>
(function() {
  const proto = window.location.protocol;
  if (proto !== 'https:' && window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
    const target = 'https:' + window.location.href.substring(proto.length);
    window.location.replace(target);
  }
})();
</script>
"""

SECURITY_META_TAGS = """
<meta name="referrer" content="strict-origin" />
<meta http-equiv="Permissions-Policy" content="camera=(), microphone=(), geolocation=()" />
"""


def enforce_https() -> None:
    """Inject a client-side guard that redirects HTTP access to HTTPS."""

    st.markdown(HTTPS_REDIRECT_SCRIPT, unsafe_allow_html=True)
    st.markdown(SECURITY_META_TAGS, unsafe_allow_html=True)


def mask_email(email: str) -> str:
    """Return an email address with the local part partially masked."""

    local, _, domain = email.partition("@")
    if not local:
        return email
    visible = local[:2]
    return f"{visible}{'*' * max(1, len(local) - len(visible))}@{domain}" if domain else email


def safe_filename(name: str, *, default: str = "export") -> str:
    """Return a filesystem safe filename based on *name*."""

    cleaned = "".join(ch if ch.isalnum() else "_" for ch in name.strip())
    cleaned = cleaned.strip("_")
    return cleaned or default


__all__ = ["enforce_https", "mask_email", "safe_filename"]
