"""
sheets.py — Запис в Google Sheets чрез gspread + Service Account.

Записва в два Sheet-а:
  1. История — всяка статия като отделен ред
  2. Архив   — един ред на седмичен доклад
"""

import os
import json
import logging
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]

# Колони за "История" Sheet
HISTORY_HEADERS = [
    "Дата", "Компания", "Тип", "Заглавие",
    "Резюме", "Извор", "URL", "AI Важност (1-5)", "AI Причина"
]

# Колони за "Архив" Sheet
ARCHIVE_HEADERS = [
    "Дата на генериране", "Период от", "Период до",
    "Брой статии", "Брой компании", "Регулаторни", "Финансови",
    "AI Резюме", "Ключови тенденции",
    "Линк към HTML доклад", "Линк към Sheets данни"
]


def get_gspread_client() -> gspread.Client:
    """Създава авторизиран gspread клиент от Service Account JSON."""
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")
    if not creds_json:
        raise ValueError("GOOGLE_CREDENTIALS_JSON не е зададен!")
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)


def ensure_headers(worksheet: gspread.Worksheet, headers: list[str]) -> None:
    """Добавя заглавен ред ако Sheet-ът е празен."""
    try:
        first_row = worksheet.row_values(1)
        if not first_row:
            worksheet.append_row(headers, value_input_option="USER_ENTERED")
            logger.info("  Добавен заглавен ред")
    except Exception as e:
        logger.warning(f"  Не може да провери заглавен ред: {e}")


def append_articles(articles: list[dict], sheet_id: str) -> None:
    """
    Добавя всяка статия като нов ред в „История" Sheet-а.
    Пропуска статии без заглавие или URL.
    """
    if not articles:
        logger.info("  Няма статии за запис в История")
        return

    client = get_gspread_client()
    try:
        sh = client.open_by_key(sheet_id)
        try:
            ws = sh.worksheet("История")
        except gspread.WorksheetNotFound:
            ws = sh.get_worksheet(0)  # fallback към първи лист

        ensure_headers(ws, HISTORY_HEADERS)

        rows = []
        for art in articles:
            if not art.get('title') or not art.get('url'):
                continue
            rows.append([
                art.get('date', ''),
                art.get('company', ''),
                art.get('type', ''),
                art.get('title', ''),
                art.get('summary', '')[:500],
                art.get('source', ''),
                art.get('url', ''),
                art.get('ai_importance', ''),
                art.get('ai_reason', ''),
            ])

        if rows:
            ws.append_rows(rows, value_input_option="USER_ENTERED")
            logger.info(f"✅ Записани {len(rows)} статии в История Sheet")
        else:
            logger.info("  Няма валидни статии за запис")

    except Exception as e:
        logger.error(f"❌ Грешка при запис в История Sheet: {e}")
        raise


def append_archive_row(articles: list[dict], summary_data: dict,
                        period_str: str, drive_url: str,
                        sheets_history_url: str, archive_sheet_id: str) -> None:
    """
    Добавя един обобщен ред в „Архив на Доклади" Sheet-а.
    """
    client = get_gspread_client()
    try:
        sh = client.open_by_key(archive_sheet_id)
        try:
            ws = sh.worksheet("Архив")
        except gspread.WorksheetNotFound:
            ws = sh.get_worksheet(0)

        ensure_headers(ws, ARCHIVE_HEADERS)

        # Статистики
        today = datetime.now().strftime("%Y-%m-%d")
        parts = period_str.split("–")
        period_from = parts[0].strip() if len(parts) > 0 else today
        period_to = parts[1].strip() if len(parts) > 1 else today

        companies_set = {a['company'] for a in articles if a.get('company') != 'ОБЩИ'}
        regulatory_count = sum(1 for a in articles if a.get('type') == 'Регулаторни')
        financial_count = sum(1 for a in articles if a.get('type') == 'Финансови')

        trends_text = " | ".join(summary_data.get("key_trends", []))

        row = [
            today,
            period_from,
            period_to,
            len(articles),
            len(companies_set),
            regulatory_count,
            financial_count,
            summary_data.get("executive_summary", "")[:1000],
            trends_text[:500],
            drive_url,
            sheets_history_url,
        ]

        ws.append_row(row, value_input_option="USER_ENTERED")
        logger.info(f"✅ Записан ред в Архив Sheet ({today})")

    except Exception as e:
        logger.error(f"❌ Грешка при запис в Архив Sheet: {e}")
        raise
