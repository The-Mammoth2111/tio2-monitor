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

    # ── Суровини ──
    logger.info("📡 Цени на суровини (сяра, сярна киселина, илменит)...")
    commodity_arts = fetch_commodity_prices(config, days_back)
    all_articles.extend(commodity_arts)

    # ── Макроикономически индикатори ──
    logger.info("📡 Лихвени проценти (Fed, ECB, BOJ, PBOC)...")
    macro_arts = fetch_macro_indicators(config, days_back)
    all_articles.extend(macro_arts)

    # ── Валутни курсове ──
    logger.info("📡 Валутни курсове (EUR/USD, USD/CNY, USD/JPY)...")
    fx_arts = fetch_currency_rates(config, days_back)
    all_articles.extend(fx_arts)

    # ── 1. Енергия ──
    logger.info("📡 Енергийни цени (TTF газ, ток, Brent)...")
    all_articles.extend(fetch_energy_prices(config, days_back))

    # ── 2. Търсене (downstream) ──
    logger.info("📡 Индикатори на търсенето (бои, строителство, авто)...")
    all_articles.extend(fetch_demand_indicators(config, days_back))

    # ── 3. Логистика ──
    logger.info("📡 Логистика и навла...")
    all_articles.extend(fetch_logistics(config, days_back))

    # ── 4. Капацитет ──
    logger.info("📡 Затваряния и рестарти на капацитет...")
    all_articles.extend(fetch_capacity_changes(config, days_back))

    # ── 5. Търговски разследвания ──
    logger.info("📡 Търговски разследвания (ранни сигнали)...")
    all_articles.extend(fetch_trade_investigations(config, days_back))

    logger.info(f"✅ Общо събрани: {len(all_articles)} статии")
    return all_articles


# ─────────────────────────────────────────────
# 5. Суровини — Сяра, Сярна киселина, Илменит
# ─────────────────────────────────────────────

def fetch_commodity_prices(config: dict, days_back: int) -> list[dict]:
    """
    Търси новини за цените на ключовите суровини:
    сяра, сярна киселина, илменит/рутил.
    """
    articles = []
    for commodity in config.get("commodities", []):
        name = commodity["name"]
        for keyword in commodity.get("keywords", []):
            arts = fetch_google_news(keyword, name, "Суровини", days_back)
            articles.extend(arts)
            time.sleep(0.4)
    logger.info(f"  Суровини: {len(articles)} статии намерени")
    return articles


# ─────────────────────────────────────────────
# 6. Макроикономически индикатори — Лихвени проценти
# ─────────────────────────────────────────────

def fetch_macro_indicators(config: dict, days_back: int) -> list[dict]:
    """
    Търси новини за лихвените проценти на Fed, ECB, BOJ и PBOC.
    Лихвите влияят пряко на строителство, автомобилен сектор и
    потребление на бои — основните пазари за TiO₂.
    """
    articles = []
    for indicator in config.get("macro_indicators", []):
        name = indicator["name"]
        region = indicator.get("region", "")
        for keyword in indicator.get("keywords", []):
            arts = fetch_google_news(keyword, f"{region} {name}", "Макро", days_back)
            articles.extend(arts)
            time.sleep(0.4)
    logger.info(f"  Макро индикатори: {len(articles)} статии намерени")
    return articles


# ─────────────────────────────────────────────
# 7. Валутни курсове — EUR/USD, USD/CNY, USD/JPY
# ─────────────────────────────────────────────

def fetch_currency_rates(config: dict, days_back: int) -> list[dict]:
    """
    Търси новини за ключовите валутни двойки.

    Логика на влиянието:
      - Силен долар (EUR/USD надолу) → европейският износ става
        по-конкурентен на изток и в САЩ.
      - Слаб долар (EUR/USD нагоре) → европейският износ поскъпва,
        американските и азиатските производители печелят предимство.
    """
    articles = []
    for pair in config.get("currency_pairs", []):
        name = f"{pair['pair']} ({pair['name']})"
        for keyword in pair.get("keywords", []):
            arts = fetch_google_news(keyword, name, "Валути", days_back)
            articles.extend(arts)
            time.sleep(0.4)
    logger.info(f"  Валутни курсове: {len(articles)} статии намерени")
    return articles


# ═════════════════════════════════════════════
#  РАЗШИРЕНИ ИНДИКАТОРИ (5 нови измерения)
# ═════════════════════════════════════════════

# ── 1. ЕНЕРГИЯ ────────────────────────────────

def fetch_energy_prices(config: dict, days_back: int) -> list[dict]:
    """
    Енергийни цени — TTF газ, електроенергия, Brent.

    Хлоридният метод изисква температури над 1000°C. Високите
    енергийни цени в Европа бяха основната причина за затварянето
    на Venator Greatham и Tronox Botlek. Този индикатор показва
    кога европейските производители влизат в зоната на загубата
    ПРЕДИ да го обявят официално.
    """
    articles = []
    for ind in config.get("energy_indicators", []):
        for keyword in ind.get("keywords", []):
            arts = fetch_google_news(keyword, ind["name"], "Енергия", days_back)
            articles.extend(arts)
            time.sleep(0.4)
    logger.info(f"  Енергия: {len(articles)} статии")
    return articles


# ── 2. ТЪРСЕНЕ (downstream) ───────────────────

def fetch_demand_indicators(config: dict, days_back: int) -> list[dict]:
    """
    Индикатори на ТЪРСЕНЕТО, не само на разходите.

    TiO₂ се продава чрез бои → строителство и автомобили.
    Отчетите на PPG, Sherwin-Williams, AkzoNobel и Jotun показват
    какво реално се търси 1-2 тримесечия напред от TiO₂ поръчките.
    """
    articles = []
    for group in config.get("demand_indicators", []):
        category = group.get("category", "Търсене")

        # Отделни търсения за всеки производител на бои
        for company in group.get("companies", []):
            query = f"{company['name']} results outlook 2026"
            arts = fetch_google_news(query, f"Търсене — {company['name']}", "Търсене", days_back)
            articles.extend(arts)
            time.sleep(0.4)

            # Yahoo Finance за публичните
            if company.get("ticker"):
                arts = fetch_yahoo_finance_news(company["ticker"], f"Търсене — {company['name']}", days_back)
                articles.extend(arts)
                time.sleep(0.3)

        # Общи ключови думи за категорията
        for keyword in group.get("keywords", []):
            arts = fetch_google_news(keyword, f"Търсене — {category}", "Търсене", days_back)
            articles.extend(arts)
            time.sleep(0.4)

    logger.info(f"  Търсене: {len(articles)} статии")
    return articles


# ── 3. ЛОГИСТИКА ──────────────────────────────

def fetch_logistics(config: dict, days_back: int) -> list[dict]:
    """
    Морски навла и логистични прекъсвания.

    Китайският TiO₂ е конкурентен само ако доставката е евтина.
    При скок в контейнерните навла Шанхай→Ротердам, китайското
    ценово предимство в Европа изчезва без никаква промяна в
    заводската цена.
    """
    articles = []
    for ind in config.get("logistics_indicators", []):
        for keyword in ind.get("keywords", []):
            arts = fetch_google_news(keyword, ind["name"], "Логистика", days_back)
            articles.extend(arts)
            time.sleep(0.4)
    logger.info(f"  Логистика: {len(articles)} статии")
    return articles


# ── 4. КАПАЦИТЕТ ──────────────────────────────

def fetch_capacity_changes(config: dict, days_back: int) -> list[dict]:
    """
    Обявени затваряния и рестарти на производствен капацитет.

    Това е най-силният ценови сигнал в индустрията. Над 1.1 млн.
    тона (≈11% от световния пазар) излязоха от производство през
    2025-2026. Всяко обявено затваряне или рестарт променя
    баланса търсене/предлагане месеци напред.
    """
    tracker = config.get("capacity_tracker", {})
    articles = []
    for keyword in tracker.get("keywords", []):
        arts = fetch_google_news(keyword, "Капацитет", "Капацитет", days_back)
        articles.extend(arts)
        time.sleep(0.4)
    logger.info(f"  Капацитет: {len(articles)} статии")
    return articles


def get_capacity_balance(config: dict) -> dict:
    """
    Изчислява нетния капацитетен баланс от известните събития.
    Връща обобщение колко капацитет влиза и излиза от пазара.
    """
    events = config.get("capacity_tracker", {}).get("known_events", [])
    offline = sum(e.get("capacity_kt") or 0 for e in events
                  if e.get("status", "").startswith(("ЗАТВОРЕН", "СПРЯН")))
    online = sum(e.get("capacity_kt") or 0 for e in events
                 if e.get("status", "").startswith("РЕСТАРТ"))
    return {
        "offline_kt": offline,
        "online_kt": online,
        "net_kt": online - offline,
        "events": events,
    }


# ── 5. ТЪРГОВСКИ РАЗСЛЕДВАНИЯ ─────────────────

def fetch_trade_investigations(config: dict, days_back: int) -> list[dict]:
    """
    Търговски разследвания в РАННА фаза.

    Инициирането на разследване (ЕС, Бразилия, Индия, Турция)
    движи пазара месеци преди финалното решение. Ранното
    сигнализиране дава време за реакция при договаряне на
    доставки и цени.
    """
    trade = config.get("trade_investigations", {})
    articles = []
    for keyword in trade.get("keywords", []):
        arts = fetch_google_news(keyword, "Търговски разследвания", "Разследвания", days_back)
        articles.extend(arts)
        time.sleep(0.4)

    # Търсене по юрисдикции
    for juris in trade.get("monitored_jurisdictions", []):
        query = f"{juris} titanium dioxide trade investigation 2026"
        arts = fetch_google_news(query, f"Разследване — {juris}", "Разследвания", days_back)
        articles.extend(arts)
        time.sleep(0.3)

    logger.info(f"  Търговски разследвания: {len(articles)} статии")
    return articles
