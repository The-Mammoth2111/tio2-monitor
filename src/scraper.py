"""
scraper.py — Събира TiO2 новини от множество източници:
  - Google News RSS (за всяка компания и глобални ключови думи)
  - Официални сайтове на компаниите (press / news секции)
  - PR Newswire и GlobeNewsWire RSS
"""

import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus
import json
import logging
import time
import re
import os

logger = logging.getLogger(__name__)

CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config', 'companies.json')

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def load_config() -> dict:
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def parse_date(date_str: str) -> datetime | None:
    """Опитва различни формати на дата и връща datetime обект."""
    if not date_str:
        return None
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    # feedparser struct_time fallback
    try:
        import calendar
        t = feedparser._parse_date(date_str)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    except Exception:
        pass
    return None


def is_within_days(article_date: datetime | None, days: int) -> bool:
    """Проверява дали статия е в рамките на последните N дни."""
    if article_date is None:
        return True  # ако нямаме дата, включваме статията
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return article_date >= cutoff


def make_article(title: str, url: str, summary: str, source: str,
                 company: str, article_type: str, date: datetime | None) -> dict:
    """Създава стандартизиран речник за статия."""
    return {
        "title": title.strip() if title else "",
        "url": url.strip() if url else "",
        "summary": summary.strip() if summary else "",
        "source": source,
        "company": company,
        "type": article_type,
        "date": date.strftime("%Y-%m-%d") if date else datetime.now().strftime("%Y-%m-%d"),
        "ai_importance": "",   # попълва се от ai_summary.py
    }


# ─────────────────────────────────────────────
# 1. Google News RSS
# ─────────────────────────────────────────────

def fetch_google_news(query: str, company_name: str, article_type: str,
                      days_back: int) -> list[dict]:
    """Търси в Google News по ключова дума и връща списък статии."""
    base_url = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
    url = base_url.format(query=quote_plus(query))
    articles = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            pub_date = parse_date(entry.get('published', ''))
            if not is_within_days(pub_date, days_back):
                continue
            # Изчистваме HTML тагове от summary
            raw_summary = entry.get('summary', '')
            clean_summary = BeautifulSoup(raw_summary, 'html.parser').get_text()[:400]
            articles.append(make_article(
                title=entry.get('title', ''),
                url=entry.get('link', ''),
                summary=clean_summary,
                source="Google News",
                company=company_name,
                article_type=article_type,
                date=pub_date,
            ))
        logger.info(f"  Google News [{query}]: {len(articles)} статии")
    except Exception as e:
        logger.warning(f"  Google News грешка [{query}]: {e}")
    return articles


# ─────────────────────────────────────────────
# 2. RSS от конкретен URL
# ─────────────────────────────────────────────

def fetch_rss(rss_url: str, source_name: str, filter_keywords: list[str],
              company_name: str, days_back: int) -> list[dict]:
    """Взима RSS feed, филтрира по ключови думи и връща статии."""
    articles = []
    try:
        feed = feedparser.parse(rss_url)
        for entry in feed.entries:
            title = entry.get('title', '')
            summary_raw = entry.get('summary', entry.get('description', ''))
            text_to_check = (title + ' ' + summary_raw).lower()
            # Филтрираме само ако има ключова дума
            if filter_keywords and not any(kw.lower() in text_to_check for kw in filter_keywords):
                continue
            pub_date = parse_date(entry.get('published', ''))
            if not is_within_days(pub_date, days_back):
                continue
            clean_summary = BeautifulSoup(summary_raw, 'html.parser').get_text()[:400]
            articles.append(make_article(
                title=title,
                url=entry.get('link', ''),
                summary=clean_summary,
                source=source_name,
                company=company_name,
                article_type="Новини",
                date=pub_date,
            ))
        logger.info(f"  RSS [{source_name}]: {len(articles)} статии")
    except Exception as e:
        logger.warning(f"  RSS грешка [{source_name}]: {e}")
    return articles


# ─────────────────────────────────────────────
# 3. Scrape на уебсайт (прости HTML сайтове)
# ─────────────────────────────────────────────

def scrape_website_news(company: dict, days_back: int) -> list[dict]:
    """Опитва да scrape-не news секцията на официалния сайт на компанията."""
    articles = []
    news_url = company.get('news_url')
    if not news_url:
        return articles
    try:
        resp = requests.get(news_url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')

        # Търсим всички <a> тагове с текст и href
        links = soup.find_all('a', href=True)
        found = 0
        for link in links:
            href = link['href']
            text = link.get_text(strip=True)
            if len(text) < 20 or len(text) > 300:
                continue
            # Само ако съдържа ключова дума или е в news/press секция
            href_lower = href.lower()
            if not any(x in href_lower for x in ['news', 'press', 'release', 'investor', 'announcement']):
                continue
            # Пълен URL
            if href.startswith('/'):
                from urllib.parse import urlparse
                base = urlparse(news_url)
                href = f"{base.scheme}://{base.netloc}{href}"
            elif not href.startswith('http'):
                continue
            articles.append(make_article(
                title=text,
                url=href,
                summary="",
                source=company['name'],
                company=company['name'],
                article_type="Новини",
                date=None,
            ))
            found += 1
            if found >= 10:
                break

        logger.info(f"  Сайт [{company['name']}]: {found} линка")
    except Exception as e:
        logger.warning(f"  Сайт грешка [{company['name']}]: {e}")
    return articles


# ─────────────────────────────────────────────
# 4. Финансови новини (Yahoo Finance RSS)
# ─────────────────────────────────────────────

def fetch_yahoo_finance_news(ticker: str, company_name: str, days_back: int) -> list[dict]:
    """Взима финансови новини от Yahoo Finance RSS."""
    if not ticker:
        return []
    url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
    articles = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:15]:
            pub_date = parse_date(entry.get('published', ''))
            if not is_within_days(pub_date, days_back):
                continue
            articles.append(make_article(
                title=entry.get('title', ''),
                url=entry.get('link', ''),
                summary=entry.get('summary', '')[:400],
                source="Yahoo Finance",
                company=company_name,
                article_type="Финансови",
                date=pub_date,
            ))
        logger.info(f"  Yahoo Finance [{ticker}]: {len(articles)} статии")
    except Exception as e:
        logger.warning(f"  Yahoo Finance грешка [{ticker}]: {e}")
    return articles


# ─────────────────────────────────────────────
# ГЛАВНА ФУНКЦИЯ
# ─────────────────────────────────────────────

def scrape_all(days_back: int = 7) -> list[dict]:
    """
    Основна функция — събира всички новини от всички източници.
    Връща списък от стандартизирани статии.
    """
    config = load_config()
    all_articles = []

    # ── По компании ──
    for company in config['companies']:
        name = company['name']
        logger.info(f"📡 Обхождане: {name}")

        # Google News за всяка ключова дума на компанията
        for keyword in company.get('keywords', []):
            arts = fetch_google_news(keyword, name, "Новини", days_back)
            all_articles.extend(arts)
            time.sleep(0.5)

        # Yahoo Finance (само за публично търгуваните)
        if company.get('ticker'):
            arts = fetch_yahoo_finance_news(company['ticker'], name, days_back)
            all_articles.extend(arts)
            time.sleep(0.5)

        # Официален сайт
        arts = scrape_website_news(company, days_back)
        all_articles.extend(arts)
        time.sleep(1)

    # ── Глобални ключови думи ──
    logger.info("📡 Глобални ключови думи...")
    for keyword in config.get('global_keywords', []):
        arts = fetch_google_news(keyword, "ОБЩИ", "Новини", days_back)
        all_articles.extend(arts)
        time.sleep(0.5)

    # ── RSS източници (PR Newswire, GlobeNewsWire) ──
    logger.info("📡 RSS агрегатори...")
    all_company_keywords = []
    for c in config['companies']:
        all_company_keywords.extend(c.get('keywords', []))
    all_company_keywords.extend(config.get('global_keywords', []))

    for rss in config.get('rss_sources', []):
        arts = fetch_rss(
            rss_url=rss['url'],
            source_name=rss['name'],
            filter_keywords=rss.get('filter_keywords', []),
            company_name="ОБЩИ",
            days_back=days_back,
        )
        all_articles.extend(arts)
        time.sleep(1)

    logger.info(f"✅ Общо събрани: {len(all_articles)} статии")
    return all_articles
