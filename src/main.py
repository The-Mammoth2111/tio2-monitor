"""
main.py — Главен orchestrator на TiO2 Monitor.

Изпълнява целия pipeline:
  1. Scrape → 2. Dedup → 3. AI Summary →
  4. Sheets (История) → 5. Drive (HTML архив) →
  6. Sheets (Архив ред) → 7. Email

Пробен режим (DRY_RUN=1):
  Минава стъпки 1–3 и генерира HTML доклада, но НЕ пише в Sheets/Drive
  и НЕ изпраща имейл. Докладът се записва в report.html (в GitHub Actions
  се качва като артефакт). Не изисква никакви secrets — без
  ANTHROPIC_API_KEY резюмето е резервно (без AI).
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta

# Добавяме src/ в path
sys.path.insert(0, os.path.dirname(__file__))

from scraper import scrape_all, get_capacity_balance, load_config
from dedup import deduplicate
from ai_summary import generate_summary
from email_report import build_html_email, report_stats

ROOT = os.path.join(os.path.dirname(__file__), "..")
LOG_PATH = os.path.join(ROOT, "tio2_monitor.log")
REPORT_PATH = os.path.join(ROOT, "report.html")

# ─── Logging (конзола + файл, който workflow-ът качва при грешка) ───
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


# Какво е всяка настройка и къде се взима — показва се, ако липсва.
ENV_HELP = {
    "ANTHROPIC_API_KEY": "API ключ от console.anthropic.com → API Keys (за AI резюмето)",
    "GMAIL_USER": "Gmail адресът, от който се изпраща докладът",
    "GMAIL_APP_PASSWORD": "App Password: myaccount.google.com → Security → App passwords (изисква 2-стъпкова проверка)",
    "RECIPIENT_EMAIL": "Получатели, разделени със запетая (напр. a@petrex.bg, b@petrex.bg)",
    "GOOGLE_CREDENTIALS_JSON": "Целият JSON на Google service account (Cloud Console → IAM → Service Accounts → Keys)",
    "SHEETS_HISTORY_ID": "ID на Sheet-а „История“ (частта от URL-а между /d/ и /edit)",
    "SHEETS_ARCHIVE_ID": "ID на Sheet-а „Архив“ (частта от URL-а между /d/ и /edit)",
}


def is_dry_run() -> bool:
    return os.environ.get("DRY_RUN", "").strip().lower() in ("1", "true", "yes", "да")


def check_env_vars(dry_run: bool) -> None:
    """Проверява настройките и обяснява ясно какво липсва."""
    missing = [v for v in ENV_HELP if not os.environ.get(v, "").strip()]
    if dry_run:
        if missing:
            logger.info("🧪 ПРОБЕН РЕЖИМ — не са нужни secrets. Липсващи (игнорират се): "
                        + ", ".join(missing))
        if "ANTHROPIC_API_KEY" in missing:
            logger.warning("⚠️  Без ANTHROPIC_API_KEY резюмето ще е резервно (без AI анализ).")
        return
    if missing:
        logger.error("❌ Липсват настройки (GitHub → Settings → Secrets and variables → Actions):")
        for v in missing:
            logger.error(f"   • {v}: {ENV_HELP[v]}")
        logger.error("   Съвет: пусни workflow-а ръчно с dry_run = true, за да тестваш без secrets.")
        sys.exit(1)
    # Ранна проверка на JSON-а — иначе грешката излиза чак на стъпка 4
    try:
        json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
    except json.JSONDecodeError as e:
        logger.error(f"❌ GOOGLE_CREDENTIALS_JSON не е валиден JSON ({e}). "
                     "Копирай целия файл, включително { и }.")
        sys.exit(1)
    logger.info("✅ Всички настройки са налични")


def build_period(days_back: int = 7) -> dict:
    """
    Връща периода в няколко формата:
      label     = "14 Jul – 20 Jul 2026"  (за имейла)
      file      = "14-20 Jul 2026"        (за името в Drive)
      start/end = "2026-07-14" / "2026-07-20" (за Архива)
    """
    end = datetime.now()
    start = end - timedelta(days=days_back)
    return {
        "label": f"{start.strftime('%d %b')} – {end.strftime('%d %b %Y')}",
        "file": f"{start.strftime('%d')}-{end.strftime('%d %b %Y')}",
        "start": start.strftime("%Y-%m-%d"),
        "end": end.strftime("%Y-%m-%d"),
    }


def main() -> None:
    dry_run = is_dry_run()
    logger.info("=" * 60)
    logger.info("🔬 TiO2 MONITOR СТАРТИРА" + ("  [ПРОБЕН РЕЖИМ]" if dry_run else ""))
    logger.info("=" * 60)

    # 0. Проверка на настройките
    check_env_vars(dry_run)

    DAYS_BACK = int(os.environ.get("DAYS_BACK", "7") or 7)
    period = build_period(DAYS_BACK)
    logger.info(f"📅 Период: {period['label']}")

    config = load_config()
    history_id = os.environ.get("SHEETS_HISTORY_ID", "")
    archive_id = os.environ.get("SHEETS_ARCHIVE_ID", "")
    history_url = f"https://docs.google.com/spreadsheets/d/{history_id}/edit" if history_id else ""

    # ── СТЪПКА 1: Scraping ──────────────────
    logger.info("\n📡 СТЪПКА 1: Събиране на новини...")
    try:
        raw_articles = scrape_all(days_back=DAYS_BACK)
        logger.info(f"   Намерени: {len(raw_articles)} статии")
    except Exception as e:
        logger.exception(f"❌ Scraping грешка: {e}")
        raw_articles = []
    if not raw_articles:
        logger.warning("⚠️  Не са намерени новини. Докладът ще е празен.")

    # ── СТЪПКА 2: Дедупликация ──────────────
    logger.info("\n🧹 СТЪПКА 2: Дедупликация...")
    articles = deduplicate(raw_articles)
    logger.info(f"   Оставащи: {len(articles)} статии")

    # ── СТЪПКА 3: AI Резюме ─────────────────
    logger.info("\n🤖 СТЪПКА 3: AI резюме (Claude)...")
    summary_data = generate_summary(articles, period["label"])
    enriched_articles = summary_data.get("articles_with_importance", articles)
    stats = report_stats(enriched_articles, config)
    logger.info(f"   Компании: {stats['companies']} · Регулаторни: {stats['regulatory']} · "
                f"Финансови: {stats['financial']}")

    # ── СТЪПКА 4: HTML доклад ───────────────
    logger.info("\n📄 СТЪПКА 4: Генериране на HTML доклад...")
    capacity_data = get_capacity_balance(config)
    html_content = build_html_email(
        articles=enriched_articles,
        summary_data=summary_data,
        period_str=period["label"],
        sheets_url=history_url,
        capacity_data=capacity_data,
        alloc_data=config.get("acid_allocation"),
        oprate_data=config.get("operating_rates"),
        margin_data=config.get("margin_tracker"),
        export_data=config.get("export_restrictions"),
        outage_data=config.get("unplanned_outages"),
        markets_data=config.get("addressable_markets"),
        config=config,
    )
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(html_content)
    logger.info(f"   Записан: report.html ({len(html_content.encode()):,} байта)")

    if dry_run:
        logger.info("\n🧪 ПРОБЕН РЕЖИМ: пропускам Sheets, Drive и имейла.")
        logger.info("   Докладът е в report.html (в GitHub: Actions → това пускане → Artifacts).")
        logger.info("✅ TiO2 MONITOR ЗАВЪРШИ (пробно)")
        return

    # Модулите с Google/Gmail се зареждат само в истинско пускане
    from sheets import append_articles, append_archive_row
    from drive import upload_html_report
    from email_report import send_email

    errors = []

    # ── СТЪПКА 5: Sheets — История ──────────
    logger.info("\n📊 СТЪПКА 5: Запис в Google Sheets (История)...")
    try:
        append_articles(enriched_articles, history_id)
    except Exception as e:
        logger.error(f"❌ Sheets История грешка: {e}")
        errors.append("Sheets История")

    # ── СТЪПКА 6: Drive ─────────────────────
    logger.info("\n📁 СТЪПКА 6: Качване в Google Drive...")
    drive_url = ""
    try:
        drive_url = upload_html_report(html_content, f"TiO2 Доклад — {period['file']}.html")
    except Exception as e:
        logger.error(f"❌ Drive грешка: {e}")
        errors.append("Drive")

    # ── СТЪПКА 7: Sheets — Архив ────────────
    logger.info("\n📊 СТЪПКА 7: Запис в Google Sheets (Архив)...")
    try:
        append_archive_row(
            summary_data=summary_data,
            stats=stats,
            period=period,
            drive_url=drive_url,
            sheets_history_url=history_url,
            archive_sheet_id=archive_id,
        )
    except Exception as e:
        logger.error(f"❌ Sheets Архив грешка: {e}")
        errors.append("Sheets Архив")

    # ── СТЪПКА 8: Имейл ─────────────────────
    logger.info("\n📧 СТЪПКА 8: Изпращане на имейл...")
    recipients = os.environ["RECIPIENT_EMAIL"]
    subject = f"🔬 TiO₂ Monitor — Седмичен доклад | {period['label']}"
    try:
        send_email(html_content, subject, recipients)
    except Exception as e:
        logger.error(f"❌ Email грешка: {e}")
        errors.append("Имейл")

    # ── ФИНАЛ ───────────────────────────────
    logger.info("\n" + "=" * 60)
    logger.info(f"   Статии: {len(enriched_articles)} · Drive: {drive_url or 'N/A'}")
    if errors:
        logger.error(f"❌ ЗАВЪРШИ С ГРЕШКИ в: {', '.join(errors)}")
        logger.info("=" * 60)
        sys.exit(1)  # пускането в GitHub излиза червено, за да се види
    logger.info("✅ TiO2 MONITOR ЗАВЪРШИ УСПЕШНО")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
