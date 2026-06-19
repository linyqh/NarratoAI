import ipaddress
from typing import Optional
from urllib.parse import urlparse

from app.config import config


TRUSTED_OPENAI_COMPATIBLE_BASE_HOSTS = {
    "api.openai.com",
    "openrouter.ai",
    "api.siliconflow.cn",
    "dashscope.aliyuncs.com",
    "api.deepseek.com",
    "api.moonshot.cn",
    "api.together.xyz",
    "api.cohere.ai",
    "generativelanguage.googleapis.com",
    "open.bigmodel.cn",
    "api.z.ai",
    "ark.cn-beijing.volces.com",
    "ark.cn-shanghai.volces.com",
}

TRUSTED_OPENAI_COMPATIBLE_BASE_SUFFIXES = (
    ".openai.azure.com",
    ".services.ai.azure.com",
    ".cognitiveservices.azure.com",
)

OPENAI_COMPATIBLE_BASE_URL_ERROR = (
    "OpenAI-compatible base_url is not in the trusted provider list. "
    "Use an official provider endpoint or set allow_custom_openai_base_url=true "
    "only if you understand that the configured endpoint receives the API key."
)


def custom_openai_base_url_allowed() -> bool:
    value = config.app.get("allow_custom_openai_base_url", False)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _is_loopback_ollama_url(scheme: str, host: str, port: Optional[int]) -> bool:
    if scheme not in {"http", "https"} or port != 11434:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _is_well_formed_http_base_url(base_url: str) -> bool:
    parsed = urlparse(str(base_url).strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    if parsed.username or parsed.password:
        return False
    try:
        parsed.port
    except ValueError:
        return False
    return True


def is_trusted_openai_compatible_base_url(base_url: Optional[str]) -> bool:
    if not base_url:
        return True

    parsed = urlparse(str(base_url).strip())
    host = (parsed.hostname or "").rstrip(".").lower()
    if not parsed.scheme or not host or parsed.username or parsed.password:
        return False

    try:
        port = parsed.port
    except ValueError:
        return False

    if _is_loopback_ollama_url(parsed.scheme, host, port):
        return True

    if parsed.scheme != "https":
        return False

    if host in TRUSTED_OPENAI_COMPATIBLE_BASE_HOSTS:
        return True

    return any(host.endswith(suffix) for suffix in TRUSTED_OPENAI_COMPATIBLE_BASE_SUFFIXES)


def validate_openai_compatible_base_url(base_url: Optional[str]) -> Optional[str]:
    if not base_url:
        return None

    normalized = str(base_url).strip()
    if is_trusted_openai_compatible_base_url(normalized):
        return normalized
    if custom_openai_base_url_allowed() and _is_well_formed_http_base_url(normalized):
        return normalized

    raise ValueError(OPENAI_COMPATIBLE_BASE_URL_ERROR)
