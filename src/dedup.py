"""
dedup.py — Дедупликация на новини.
Премахва статии с еднакви или много сходни URL / заглавия.
"""

import re
import logging
from datetime import datetime
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


_NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")


def _key_numbers(text: str) -> set[str]:
    """
    Значещите числа в заглавие, нормализирани („15,00“ = „15.00“ = „15“).
    Годините (2000–2100) не се броят — те се срещат навсякъде.
    """
    out = set()
    for raw in _NUM_RE.findall(text or ""):
        try:
            n = float(raw.replace(",", "."))
        except ValueError:
            continue
        if 2000 <= n <= 2100 and n.is_integer():
            continue
        out.add(f"{n:g}")
    return out


_BANKS = ("goldman", "morgan stanley", "jpmorgan", "j.p. morgan", "truist", "citi",
          "bank of america", "bofa", "wells fargo", "ubs", "barclays", "deutsche",
          "mizuho", "rbc", "bmo", "zacks", "alembic", "jefferies", "keybanc", "evercore",
          "citic", "中信", "国泰君安", "华泰", "中邮")


def _banks_in(text: str) -> set[str]:
    t = (text or "").lower()
    return {b for b in _BANKS if b in t}


def _days_apart(d1: str, d2: str) -> int:
    try:
        return abs((datetime.strptime(d1, "%Y-%m-%d") - datetime.strptime(d2, "%Y-%m-%d")).days)
    except (ValueError, TypeError):
        return 999


def same_story(a: dict, b: dict, max_days: int = 7) -> bool:
    """
    Една и съща новина на различни езици / от различни сайтове:
    същата компания, същият тип, поне едно общо значещо число в заглавието
    (напр. целева цена 15.00) и до 7 дни разлика (преводите често излизат дни по-късно).
    Пример: „Mizuho cuts target to USD 15.00 for Chemours“ и
            „Mizuho senkt Ziel für die Chemours-Aktie auf 15,00 USD“.
    """
    if a.get("company") != b.get("company") or a.get("type") != b.get("type"):
        return False
    if a.get("company") in ("", "ОБЩИ"):
        return False  # твърде общо — само заглавието решава
    if _days_apart(a.get("date", ""), b.get("date", "")) > max_days:
        return False
    # Две различни банки с еднаква цел ($16) са две различни новини
    banks_a, banks_b = _banks_in(a.get("title", "")), _banks_in(b.get("title", ""))
    if (banks_a or banks_b) and not (banks_a & banks_b):
        return False
    return bool(_key_numbers(a.get("title", "")) & _key_numbers(b.get("title", "")))


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
            if sim >= title_threshold or same_story(article, existing):
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
