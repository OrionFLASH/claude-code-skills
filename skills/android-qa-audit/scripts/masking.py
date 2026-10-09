#!/usr/bin/env python3
"""Masking of secrets and personal data in logcat, UI texts, findings and drafts (references/safety-rules.md §5).

  from masking import mask, find_unmasked        mask(text, secrets=(token,)) — also every exact known secret
  python3 masking.py FILE [--in-place]      mask a text file (logcat dump) and print or rewrite it

e-mail -> a***@d***.tld; tokens/keys/JWT -> first 4 chars + …(length); URL parameters token/key/session/code/
state/password/auth -> ***; Bearer/Basic values -> ***; phone numbers -> last 2 digits; IMEI-like 15 digits -> ***;
android_id / advertising id values -> ***. Standard library only.
"""
import re
import sys
from pathlib import Path

EMAIL = re.compile(r"\b([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9])[A-Za-z0-9.-]*\.([A-Za-z]{2,})\b")
JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")
TOKEN = re.compile(r"\b(?=[A-Za-z0-9_\-]*\d)(?=[A-Za-z0-9_\-]*[A-Za-z])[A-Za-z0-9_\-]{32,}\b")
AUTH_HDR = re.compile(r"(?i)\b(authorization|bearer|basic|x-api-key|api[_-]?key|access[_-]?token|refresh[_-]?token|"
                      r"client[_-]?secret|password|passwd|secret)(\"?\s*[:=]\s*\"?|\s+)((?:bearer|basic|token)\s+)?([^\s\"',;&]{4,})")
URL_PARAM = re.compile(r"(?i)([?&](?:token|access_token|id_token|key|api_key|session|sid|code|state|password|auth|signature|sig)=)[^&#\s\"']+")
# token=… / grpc.token=… / auth_token: … (the emulator discovery file, gRPC errors): only with ":" or "=" — «token is
# invalid» is a message, not a value
TOKEN_KV = re.compile(r"(?i)\b((?:grpc[._-]|auth[_-]?|id[_-]?|session[_-]?|console[_-]?)?token)(\"?\s*[:=]\s*\"?)([^\s\"',;&]{4,})")
# international (+…) or Russian 8 (9xx) … numbers only: plain digit runs in logcat are PIDs, ids and timestamps
PHONE = re.compile(r"(?<![\w.:])(?:\+\d{1,3}|\b8)[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}(?![\w.])")
IMEI = re.compile(r"\b\d{15}\b")
DEVICE_ID = re.compile(r"(?i)\b(android_id|advertising_?id|gaid|adid|device_?id|imei|serial(?:no)?)(\"?\s*[:=]\s*\"?)([0-9a-f-]{8,})")


def _slug(s):
    parts = s.split("-")
    return len(parts) >= 3 and all(len(x) <= 16 for x in parts)


def _short(s):
    return f"{s[:4]}…({len(s)})"


def _flag(value):
    """password="false" in a uiautomator dump is a flag, not a secret."""
    return value.lower() in ("true", "false", "null", "none")


def mask(text, secrets=()):
    """Mask secrets and personal data. secrets — exact values known to the caller (a gRPC token read from the
    emulator discovery file, a password from env): every occurrence becomes `abcd…(N)` whatever the context."""
    if not text:
        return text
    for s in sorted({str(x) for x in secrets if x and len(str(x)) >= 4}, key=len, reverse=True):
        text = text.replace(s, _short(s))
    text = JWT.sub(lambda m: _short(m.group(0)), text)
    text = AUTH_HDR.sub(lambda m: m.group(0) if _flag(m.group(4)) else f"{m.group(1)}{m.group(2)}{m.group(3) or ''}***", text)
    text = TOKEN_KV.sub(lambda m: m.group(0) if _flag(m.group(3)) or m.group(3).startswith("***") or "…(" in m.group(3)
                        else f"{m.group(1)}{m.group(2)}***", text)
    text = URL_PARAM.sub(lambda m: m.group(1) + "***", text)
    text = DEVICE_ID.sub(lambda m: f"{m.group(1)}{m.group(2)}***", text)
    text = EMAIL.sub(lambda m: f"{m.group(1)}***@{m.group(2)}***.{m.group(3)}", text)
    text = TOKEN.sub(lambda m: m.group(0) if _slug(m.group(0)) else _short(m.group(0)), text)
    text = IMEI.sub("***", text)

    def phone(m):
        digits = re.sub(r"\D", "", m.group(0))
        if len(digits) < 10 or len(digits) > 15:
            return m.group(0)
        return "***" + digits[-2:]
    return PHONE.sub(phone, text)


def find_unmasked(text):
    """Warnings for values that look like secrets or personal data (for validate_findings.py)."""
    out = []
    for m in EMAIL.finditer(text or ""):
        if "***" not in m.group(0):
            out.append(f"e-mail без маскирования: {m.group(0)[:3]}…")
    for m in TOKEN.finditer(text or ""):
        if not _slug(m.group(0)) and not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", m.group(0)):  # sha1/sha256: not secrets
            out.append(f"похоже на немаскированный токен: {m.group(0)[:4]}…({len(m.group(0))})")
    for m in JWT.finditer(text or ""):
        out.append("похоже на немаскированный JWT")
    for m in AUTH_HDR.finditer(text or ""):
        if not m.group(4).startswith("***") and not _flag(m.group(4)):
            out.append(f"значение {m.group(1)} без маскирования")
    for m in TOKEN_KV.finditer(text or ""):
        if not m.group(3).startswith("***") and "…(" not in m.group(3) and not _flag(m.group(3)):
            out.append(f"значение {m.group(1)} без маскирования")
    return out


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    p = Path(sys.argv[1])
    masked = mask(p.read_text(encoding="utf-8", errors="replace"))
    if "--in-place" in sys.argv:
        p.write_text(masked, encoding="utf-8")
    else:
        sys.stdout.write(masked)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
