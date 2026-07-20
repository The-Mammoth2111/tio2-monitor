"""
main.py — Главен orchestrator на TiO2 Monitor.

Изпълнява целия pipeline:
  1. Scrape → 2. Dedup → 3. AI Summary →
  4. Sheets (История) → 5. Drive (HTML архив) →
  6. Sheets (Архив ред) → 7. Email
"""

import os
import sys
import logging
from datetime import datetime, timedelta

# Добавяме src/ в path
sys.path.insert(0, os.path.dirname(__file__))

from scraper import scrape_all
from dedup import deduplicate
from ai_summary import generate_summary
from sheets import append_articles, append_archive_row
from drive import upload_html_report
from email_report import build_html_email, send_email

# ─── Logging ────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


def check_env_vars() -> None:
    """Проверява задължителните environment variables."""
    required = [
        "ANTHROPIC_API_KEY",
        "GMAIL_USER",
        "GMAIL_APP_PASSWORD",
        "RECIPIENT_EMAIL",
        "GOOGLE_CREDENTIALS_JSON",
        "SHEETS_HISTORY_ID",
        "SHEETS_ARCHIVE_ID",
    ]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        logger.error(f"❌ Липсващи environment variables: {', '.join(missing)}")
        sys.exit(1)
    logger.info("✅ Всички environment variables са налични")


def build_period_str(days_back: int = 7) -> tuple[str, str]:
    """
    Връща (period_str, filename_period):
      period_str     = "14 Jul – 20 Jul 2026"  (за email)
      filename_period= "14-20-Jul-2026"          (за Drive filename)
    """
    end = datetime.now()
    start = end - timedelta(days=days_back)
    period_str = f"{start.strftime('%d %b')} – {end.strftime('%d %b %Y')}"
    file_period = f"{start.strftime('%d')}-{end.strftime('%d %b %Y')}"
    return period_str, file_period


def main() -> None:
    logger.info("=" * 60)
    logger.info("🔬 TiO2 MONITOR СТАРТИРА")
    logger.info("=" * 60)

    # 0. Проверка на env vars
    check_env_vars()

    # Период
    DAYS_BACK = int(os.environ.get("DAYS_BACK", "7"))
    period_str, file_period = build_period_str(DAYS_BACK)
    logger.info(f"📅 Период: {period_str}")

    # URLs за Sheets
    history_id = os.environ["SHEETS_HISTORY_ID"]
    archive_id = os.environ["SHEETS_ARCHIVE_ID"]
    history_url = f"https://docs.google.com/spreadsheets/d/{history_id}/edit"

    # ── СТЪПКА 1: Scraping ──────────────────
    logger.info("\n📡 СТЪПКА 1: Събиране на новини...")
    try:
        raw_articles = scrape_all(days_back=DAYS_BACK)
        logger.info(f"   Намерени: {len(raw_articles)} статии")
    except Exception as e:
        logger.error(f"❌ Scraping грешка: {e}")
        raw_articles = []

    if not raw_articles:
        logger.warning("⚠️  Не са намерени новини. Докладът ще е празен.")

    # ── СТЪПКА 2: Дедупликация ──────────────
    logger.info("\n🧹 СТЪПКА 2: Дедупликация...")
    articles = deduplicate(raw_articles)
    logger.info(f"   Оставащи: {len(articles)} статии")

    # ── СТЪПКА 3: AI Резюме ─────────────────
    logger.info("\n🤖 СТЪПКА 3: AI резюме (Claude)...")
    try:
        summary_data = generate_summary(articles, period_str)
        logger.info(f"   Резюме генерирано ({len(summary_data.get('key_trends', []))} тенденции)")
    except Exception as e:
        logger.error(f"❌ AI Summary грешка: {e}")
        summary_data = {
            "executive_summary": "AI резюмето не беше генерирано поради грешка.",
            "key_trends": [],
            "articles_with_importance": articles,
        }

    enriched_articles = summary_data.get("articles_with_importance", articles)

    # ── СТЪПКА 4: Google Sheets — История ───
    logger.info("\n📊 СТЪПКА 4: Запис в Google Sheets (История)...")
    try:
        append_articles(enriched_articles, history_id)
    except Exception as e:
        logger.error(f"❌ Sheets История грешка: {e}")

    # ── СТЪПКА 5: HTML Email + Drive ────────
    logger.info("\n📄 СТЪПКА 5: Генериране на HTML доклад...")
    html_content = build_html_email(
        articles=enriched_articles,
        summary_data=summary_data,
        period_str=period_str,
        sheets_url=history_url,
    )

    logger.info("\n📁 СТЪПКА 5б: Качване в Google Drive...")
    drive_url = ""
    try:
        filename = f"TiO2 Доклад — {file_period}.html"
        drive_url = upload_html_report(html_content, filename)
    except Exception as e:
        logger.error(f"❌ Drive грешка: {e}")

    # ── СТЪПКА 6: Sheets — Архив ────────────
    logger.info("\n📊 СТЪПКА 6: Запис в Google Sheets (Архив)...")
    try:
        append_archive_row(
            articles=enriched_articles,
            summary_data=summary_data,
            period_str=period_str,
            drive_url=drive_url,
            sheets_history_url=history_url,
            archive_sheet_id=archive_id,
        )
    except Exception as e:
        logger.error(f"❌ Sheets Архив грешка: {e}")

    # ── СТЪПКА 7: Изпращане на Email ────────
    logger.info("\n📧 СТЪПКА 7: Изпращане на Email...")
    recipient = os.environ["RECIPIENT_EMAIL"]
    subject = f"🔬 TiO₂ Monitor — Седмичен доклад | {period_str}"
    try:
        send_email(html_content, subject, recipient)
    except Exception as e:
        logger.error(f"❌ Email грешка: {e}")

    # ── ФИНАЛ ───────────────────────────────
    logger.info("\n" + "=" * 60)
    logger.info("✅ TiO2 MONITOR ЗАВЪРШИ УСПЕШНО")
    logger.info(f"   Статии: {len(enriched_articles)}")
    logger.info(f"   Email до: {recipient}")
    logger.info(f"   Drive: {drive_url or 'N/A'}")
    logger.info(f"   Sheets: {history_url}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
