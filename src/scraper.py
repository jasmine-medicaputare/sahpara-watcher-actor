"""
SAHPRA Watcher — Core Scraper Module

Scrapes 6 SAHPRA public pages extracts structured data,
implements change detection via Key-Value Store hashing.
"""

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

import requests
from bs4 import BeautifulSoup

from apify import Actor

# ── Source definitions ──────────────────────────────────────────────────────

SOURCES = [
    {
        "id": "safety_alerts",
        "name": "Safety Alerts",
        "url": "https://www.sahpra.org.za/safety-alerts/",
        "category": "safety_signal",
        "update_frequency": "weekly",
        "parser": "latest_post",
    },
    {
        "id": "product_recalls",
        "name": "Product Recalls",
        "url": "https://www.sahpra.org.za/product-recalls/",
        "category": "recall",
        "update_frequency": "monthly",
        "parser": "table_recalls",
    },
    {
        "id": "news",
        "name": "Latest News",
        "url": "https://www.sahpra.org.za/latest-news-updates/",
        "category": "regulatory_change",
        "update_frequency": "weekly",
        "parser": "latest_post",
    },
    {
        "id": "industry_comm",
        "name": "Communication to Industry",
        "url": "https://www.sahpra.org.za/communication-to-industry/",
        "category": "regulatory_change",
        "update_frequency": "monthly",
        "parser": "table_recalls",
    },
    {
        "id": "documents_for_comment",
        "name": "Documents for Comments",
        "url": "https://www.sahpra.org.za/documents-for-comments/",
        "category": "public_comment",
        "update_frequency": "monthly",
        "parser": "table_docs_comment",
    },
    {
        "id": "safety_info",
        "name": "Safety Information",
        "url": "https://www.sahpra.org.za/safety-information-and-updates/",
        "category": "safety_signal",
        "update_frequency": "monthly",
        "parser": "latest_post",
    },
]

DETECTED_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# ── HTTP helpers ────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def fetch_page(url: str, timeout: int = 30) -> str | None:
    """Fetch a page's HTML content. Returns None on failure."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as exc:
        Actor.log.warning("Failed to fetch %s: %s", url, exc)
        return None


# ── Parser: latest_post pattern (Safety Alerts, Latest News, Safety Info) ──


def _parse_date_latest_post(raw: str) -> str:
    """Convert '06Jun2025' -> '2025-06-06'."""
    raw = raw.strip()
    if not raw:
        return ""
    try:
        return datetime.strptime(raw, "%d%b%Y").strftime("%Y-%m-%d")
    except ValueError:
        return raw


def parse_latest_post(html: str, source_id: str, base_url: str, category: str, max_items: int = 25) -> list[dict]:
    """
    Parse SAHPRA pages using div.latest_post_holder > div.latest_post.
    Used by: Safety Alerts, Latest News, Safety Information.
    """
    soup = BeautifulSoup(html, "lxml")
    holder = soup.find("div", class_="latest_post_holder")
    if not holder:
        Actor.log.warning("No latest_post_holder found for %s", source_id)
        return []

    posts = holder.find_all("div", class_="latest_post")
    items: list[dict] = []

    for post in posts[:max_items]:
        # Title + link
        title_el = post.find(["h5", "h4", "h3"], class_="latest_post_title")
        if not title_el:
            title_el = post.find("a")
        link = title_el.find("a") if title_el and title_el.name != "a" else title_el
        if not link:
            continue

        title = link.get_text(strip=True)
        href = link.get("href", "")
        if not title or not href:
            continue

        # Date
        date_el = post.find(class_="latest_post_date")
        date_raw = date_el.get_text(strip=True) if date_el else ""
        published = _parse_date_latest_post(date_raw)

        # Summary (inside latest_post_text, after the title)
        text_el = post.find(class_="latest_post_text")
        summary = ""
        if text_el:
            # Remove date and title text to get the actual summary
            for cls in ("latest_post_date", "latest_post_title"):
                tag = text_el.find(class_=cls)
                if tag:
                    tag.extract()
            summary = text_el.get_text(strip=True, separator=" ")[:500]

        items.append(_make_item(source_id, title, href, published, summary, category))

    return items


# ── Parser: table_recalls (Product Recalls, Communication to Industry) ──────


def _parse_date_table(date_str: str) -> str:
    """Convert '03/06/2026' -> '2026-06-03'."""
    date_str = date_str.strip()
    if not date_str:
        return ""
    try:
        return datetime.strptime(date_str, "%d/%m/%Y").strftime("%Y-%m-%d")
    except ValueError:
        pass
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        return date_str


def parse_table_recalls(html: str, source_id: str, base_url: str, category: str, max_items: int = 25) -> list[dict]:
    """
    Parse SAHPRA tables with columns: Document Number, Title, Categories, Date Updated, ...
    Used by: Product Recalls, Communication to Industry.
    """
    soup = BeautifulSoup(html, "lxml")
    tables = soup.find_all("table")
    if not tables:
        Actor.log.warning("No tables found for %s", source_id)
        return []

    # Find the right table - usually the first or second one with enough rows
    target_table = None
    for table in tables:
        rows = table.find_all("tr")
        # Header row + at least 1 data row
        if len(rows) >= 2:
            target_table = table
            break

    if target_table is None:
        return []

    items: list[dict] = []
    rows = target_table.find_all("tr")

    # Find column indices from header
    header_cells = rows[0].find_all(["th", "td"])
    col_map = {}
    for i, cell in enumerate(header_cells):
        text = cell.get_text(strip=True).lower()
        if "title" in text:
            col_map["title"] = i
        elif "document" in text and "number" in text:
            col_map["doc_num"] = i
        elif "date" in text:
            col_map["date"] = i
        elif "categorie" in text:
            col_map["category"] = i
        elif "link" in text or "download" in text:
            col_map["link"] = i

    if "title" not in col_map:
        # Fallback: title is first column
        col_map["title"] = 0
    if "date" not in col_map and len(header_cells) > 1:
        col_map["date"] = min(3, len(header_cells) - 1)

    for row in rows[1:]:
        if len(items) >= max_items:
            break
        cells = row.find_all(["td", "th"])

        title_idx = col_map.get("title", 0)
        if title_idx >= len(cells):
            continue

        # Title
        cell = cells[title_idx]
        link = cell.find("a")
        title = link.get_text(strip=True) if link else cell.get_text(strip=True)
        if not title:
            continue

        # URL
        href = link.get("href", "") if link else ""
        if href and not href.startswith("http"):
            href = base_url.rstrip("/") + "/" + href.lstrip("/")

        # Date
        date_idx = col_map.get("date", 1)
        date_raw = cells[date_idx].get_text(strip=True) if date_idx < len(cells) else ""
        published = _parse_date_table(date_raw)

        # Category tag
        cat_tag = ""
        cat_idx = col_map.get("category", 2)
        if cat_idx < len(cells):
            cat_tag = cells[cat_idx].get_text(strip=True)

        summary = f"Category: {cat_tag}" if cat_tag else title
        if col_map.get("doc_num", -1) < len(cells):
            doc_num = cells[col_map["doc_num"]].get_text(strip=True)
            if doc_num:
                summary = f"[{doc_num}] {summary}"

        items.append(_make_item(source_id, title, href, published, summary[:500], category))

    return items


# ── Parser: table_docs_comment (Documents for Comments) ─────────────────────


def parse_table_docs_comment(html: str, source_id: str, base_url: str, category: str, max_items: int = 25) -> list[dict]:
    """
    Parse the Documents for Comments table.
    Columns: Document Name, Description, Date Published, Comments Deadline date, ...
    """
    soup = BeautifulSoup(html, "lxml")
    tables = soup.find_all("table")
    if not tables:
        return []

    target_table = None
    for table in tables:
        rows = table.find_all("tr")
        if len(rows) >= 2:
            target_table = table
            break

    if target_table is None:
        return []

    items: list[dict] = []
    rows = target_table.find_all("tr")

    # Column mapping from header
    header_cells = rows[0].find_all(["th", "td"])
    col_map = {}
    for i, cell in enumerate(header_cells):
        text = cell.get_text(strip=True).lower()
        if "document name" in text:
            col_map["title"] = i
        elif "description" in text:
            col_map["description"] = i
        elif "date published" in text:
            col_map["date"] = i
        elif "deadline" in text or "comments deadline" in text:
            col_map["deadline"] = i
        elif "submit" in text:
            col_map["submit_to"] = i
        elif "comment form" in text:
            col_map["form"] = i

    if "title" not in col_map:
        col_map["title"] = 0

    for row in rows[1:]:
        if len(items) >= max_items:
            break
        cells = row.find_all(["td", "th"])

        title_idx = col_map.get("title", 0)
        if title_idx >= len(cells):
            continue

        cell = cells[title_idx]
        link = cell.find("a")
        title = link.get_text(strip=True) if link else cell.get_text(strip=True)
        if not title:
            continue

        href = link.get("href", "") if link else ""
        if href and not href.startswith("http"):
            href = base_url.rstrip("/") + "/" + href.lstrip("/")

        # Description
        desc = ""
        desc_idx = col_map.get("description", 1)
        if desc_idx < len(cells):
            desc = cells[desc_idx].get_text(strip=True)

        # Date published
        date_raw = ""
        date_idx = col_map.get("date", 2)
        if date_idx < len(cells):
            date_raw = cells[date_idx].get_text(strip=True)

        # Try multiple date formats
        published = date_raw
        for fmt in ("%d %B %Y", "%d %b %Y", "%Y-%m-%d", "%d/%m/%Y"):
            try:
                published = datetime.strptime(date_raw.strip(), fmt).strftime("%Y-%m-%d")
                break
            except (ValueError, AttributeError):
                continue

        # Deadline
        deadline = ""
        deadline_idx = col_map.get("deadline", 3)
        if deadline_idx < len(cells):
            deadline = cells[deadline_idx].get_text(strip=True)

        summary = desc
        if deadline:
            if summary:
                summary += f" | Deadline: {deadline}"
            else:
                summary = f"Comment deadline: {deadline}"

        items.append(_make_item(source_id, title, href, published, summary[:500], category))

    return items


# ── Helper ──────────────────────────────────────────────────────────────────


def _make_item(source_id: str, title: str, url: str, published_date: str, summary: str, category: str) -> dict:
    """Build a single output item conforming to the schema."""
    return {
        "source": source_id,
        "title": title.strip(),
        "url": url.strip(),
        "published_date": published_date.strip() if published_date else "",
        "detected_date": DETECTED_DATE,
        "summary": summary.strip()[:500] if summary else "",
        "category": category,
        "products_affected": [],
        "is_new": True,
        "change_type": "new",
    }


# ── Change detection ────────────────────────────────────────────────────────


def compute_hash(items: list[dict]) -> str:
    """SHA256 of concatenated titles + published_dates + urls for change detection."""
    raw = "|".join(
        f"{i.get('title', '')}|{i.get('published_date', '')}|{i.get('url', '')}"
        for i in items
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def detect_changes(source_id: str, current_items: list[dict]) -> list[dict]:
    """
    Compare current scrape against the last known state stored in KVS.

    Returns only new/changed items.  On first run, all items are 'new'.
    """
    state_key = f"state_{source_id}"
    previous_state = await Actor.get_value(state_key)
    current_hash = compute_hash(current_items)

    if previous_state is None:
        # First run — everything is new
        await Actor.set_value(state_key, {
            "hash": current_hash,
            "item_count": len(current_items),
            "last_run": DETECTED_DATE,
            "items": current_items,
        })
        for item in current_items:
            item["is_new"] = True
            item["change_type"] = "new"
        return current_items

    prev_hash = previous_state.get("hash", "")
    prev_items = previous_state.get("items", [])

    if current_hash == prev_hash:
        Actor.log.info("No changes detected for %s", source_id)
        return []

    # Hash differs — find new/updated items by URL
    new_items: list[dict] = []
    prev_by_url = {i.get("url", ""): i for i in prev_items}

    for item in current_items:
        url = item.get("url", "")
        prev = prev_by_url.get(url)
        if prev is None:
            item["is_new"] = True
            item["change_type"] = "new"
            new_items.append(item)
        elif prev.get("title", "") != item.get("title", "") or prev.get("published_date", "") != item.get("published_date", ""):
            item["is_new"] = False
            item["change_type"] = "update"
            new_items.append(item)

    # Update stored state
    await Actor.set_value(state_key, {
        "hash": current_hash,
        "item_count": len(current_items),
        "last_run": DETECTED_DATE,
        "items": current_items,
    })

    Actor.log.info(
        "Source %s: %d new/changed items out of %d total",
        source_id,
        len(new_items),
        len(current_items),
    )
    return new_items


# ── Dispatcher ──────────────────────────────────────────────────────────────


PARSERS = {
    "latest_post": parse_latest_post,
    "table_recalls": parse_table_recalls,
    "table_docs_comment": parse_table_docs_comment,
}


async def scrape_all(
    sources_to_scrape: list[str] | None = None,
    max_items: int = 25,
) -> list[dict]:
    """
    Scrape all requested SAHPRA sources and return changed items.

    Args:
        sources_to_scrape: List of source IDs to scrape (None = all).
        max_items: Max items per source.

    Returns:
        List of all new/changed items across sources.
    """
    if sources_to_scrape is None:
        sources_to_scrape = [s["id"] for s in SOURCES]

    all_new_items: list[dict] = []

    for source_def in SOURCES:
        sid = source_def["id"]
        if sid not in sources_to_scrape:
            continue

        Actor.log.info("Scraping %s (%s) …", source_def["name"], source_def["url"])

        html = fetch_page(source_def["url"])
        if html is None:
            Actor.log.warning("Skipping %s — page not reachable", sid)
            continue

        parser_id = source_def["parser"]
        parser_fn = PARSERS.get(parser_id)
        if not parser_fn:
            Actor.log.warning("No parser found for %s (parser: %s)", sid, parser_id)
            continue

        items = parser_fn(
            html=html,
            source_id=sid,
            base_url=source_def["url"],
            category=source_def["category"],
            max_items=max_items,
        )

        Actor.log.info("  → %d items found for %s", len(items), sid)

        if not items:
            Actor.log.warning("  No items extracted from %s — page structure may have changed", sid)
            continue

        changed = await detect_changes(sid, items)
        all_new_items.extend(changed)

    return all_new_items
