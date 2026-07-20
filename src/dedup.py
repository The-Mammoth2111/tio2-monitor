"""
dedup.py — Дедупликация на новини.
Премахва статии с еднакви или много сходни URL / заглавия.
"""

import re
import logging
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)


def normalize_url(url: str) -> str:
    """Нормализира URL — премахва utm параметри и trailing slashes."""
    try:
        parsed = urlparse(url)
        # Премахваме query string (utm_source, utm_campaign и т.н.)
        clean = urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))
        return clean.rstrip('/')
    except Exception:
        return url.strip()


def normalize_title(title: str) -> str:
    """Нормализира заглавие за сравнение."""
    title = title.lower()
    title = re.sub(r'[^a-z0-9\u0400-\u04FF\s]', '', title)  # запазва кирилица
    title = re.sub(r'\s+', ' ', title).strip()
    return title


def title_similarity(t1: str, t2: str) -> float:
    """
    Груба оценка на сходство между две заглавия (0.0 – 1.0).
    Използва Jaccard similarity върху думи.
    """
    words1 = set(normalize_title(t1).split())
    words2 = set(normalize_title(t2).split())
    if not words1 or not words2:
        return 0.0
    intersection = words1 & words2
    union = words1 | words2
    return len(intersection) / len(union)


def deduplicate(articles: list[dict], title_threshold: float = 0.75) -> list[dict]:
    """
    Премахва дублиращи се статии по:
    1. Еднакъв нормализиран URL
    2. Много сходни заглавия (Jaccard > threshold)

    Запазва статията с по-пълно резюме (по-дълъг текст).
    """
    seen_urls: set[str] = set()
    unique_articles: list[dict] = []

    for article in articles:
        norm_url = normalize_url(article.get('url', ''))
        title = article.get('title', '')

        # 1. Проверка по URL
        if norm_url and norm_url in seen_urls:
            continue

        # 2. Проверка по заглавие спрямо вече приети статии
        is_duplicate = False
        for existing in unique_articles:
            sim = title_similarity(title, existing.get('title', ''))
            if sim >= title_threshold:
                # Запазваме тази с по-дълго резюме
                if len(article.get('summary', '')) > len(existing.get('summary', '')):
                    unique_articles.remove(existing)
                    seen_urls.discard(normalize_url(existing.get('url', '')))
                    break
                else:
                    is_duplicate = True
                    break

        if not is_duplicate:
            unique_articles.append(article)
            if norm_url:
                seen_urls.add(norm_url)

    removed = len(articles) - len(unique_articles)
    logger.info(f"🧹 Дедупликация: {len(articles)} → {len(unique_articles)} ({removed} премахнати)")
    return unique_articles
