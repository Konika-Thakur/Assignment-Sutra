import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from utils.url_security import assert_safe_url


def ingest(url, max_pages=5, allow_local=False):
    try:
        assert_safe_url(url, allow_local=allow_local)
    except ValueError as exc:
        return [{
            "text": f"URL blocked for safety: {exc}",
            "source": "website",
            "reference": url
        }]

    visited = set()
    queue = [url]
    chunks = []

    while queue and len(visited) < max_pages:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)

        try:
            assert_safe_url(current, allow_local=allow_local)
            response = requests.get(current, timeout=10, allow_redirects=False)
            response.raise_for_status()
        except Exception:
            chunks.append({
                "text": f"URL not accessible: {current}",
                "source": "website",
                "reference": current
            })
            continue

        soup = BeautifulSoup(response.text, "html.parser")

        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        text = soup.get_text(separator="\n").strip()
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if lines:
            chunks.append({
                "text": "\n".join(lines),
                "source": "website",
                "reference": current
            })

        base = urlparse(url).netloc
        for a in soup.find_all("a", href=True):
            link = urljoin(current, a["href"])
            if urlparse(link).netloc == base and link not in visited:
                queue.append(link)

    return chunks
