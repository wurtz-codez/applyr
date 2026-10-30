import html
import ipaddress
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.hidden = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag in {"p", "li", "div", "br", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        if tag in {"p", "li", "div", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, value):
        if not self.hidden:
            self.parts.append(value)


def text(value, limit=100000):
    if not isinstance(value, str):
        return ""
    parser = TextParser()
    parser.feed(html.unescape(value[:200000]))
    return "\n".join(
        " ".join(line.split()) for line in "".join(parser.parts).splitlines() if line.strip()
    )[:limit]


def canonical_url(value: str) -> str:
    if not isinstance(value, str) or len(value) > 2000 or any(ord(c) < 32 for c in value):
        raise ValueError("Invalid URL")
    url = urlsplit(value)
    host = (url.hostname or "").lower().rstrip(".")
    if url.scheme != "https" or not host or url.username is not None or url.port not in {None, 443}:
        raise ValueError("Only public HTTPS URLs are accepted")
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise ValueError("Private URL")
    try:
        if not ipaddress.ip_address(host).is_global:
            raise ValueError("Private URL")
    except ValueError as error:
        if str(error) == "Private URL":
            raise
        if "." not in host or ":" in host:
            raise ValueError("Invalid host") from None
    query = sorted(
        (k, v)
        for k, v in parse_qsl(url.query, keep_blank_values=True)
        if not k.lower().startswith("utm_")
        and k.lower()
        not in {
            "gclid",
            "fbclid",
            "mc_cid",
            "mc_eid",
        }
    )
    netloc = f"[{host}]" if ":" in host else host
    path = url.path or "/"
    return urlunsplit(("https", netloc, path, urlencode(query), ""))


def date(value):
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return datetime.fromtimestamp(value, UTC)
        if isinstance(value, str) and value.strip():
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return result.replace(tzinfo=UTC) if result.tzinfo is None else result.astimezone(UTC)
    except (ValueError, TypeError, OverflowError, OSError):
        pass
    return None


def tags(values):
    if not isinstance(values, list):
        return []
    return sorted(
        {
            text(value, 100).casefold()
            for value in values
            if isinstance(value, str) and text(value, 100).strip()
        }
    )[:50]


def employment(value):
    if isinstance(value, list):
        value = " ".join(str(item) for item in value)
    value = text(value, 80).casefold().replace("_", " ").replace("-", " ")
    for needle, result in [
        ("full", "Full-time"),
        ("part", "Part-time"),
        ("contract", "Contract"),
        ("intern", "Internship"),
        ("freelance", "Freelance"),
        ("tempor", "Temporary"),
    ]:
        if needle in value:
            return result
    return None
