"""
drive.py — Качва HTML доклад в Google Drive чрез Service Account.
Връща публичния view URL на файла.
"""

import os
import json
import logging
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive",
]


def get_drive_service():
    """Създава авторизиран Drive API service."""
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")
    if not creds_json:
        raise ValueError("GOOGLE_CREDENTIALS_JSON не е зададен!")
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return build("drive", "v3", credentials=creds)


def upload_html_report(html_content: str, filename: str,
                        parent_folder_id: str | None = None) -> str:
    """
    Качва HTML съдържание в Google Drive.

    Args:
        html_content: Пълното HTML съдържание на доклада
        filename: Желаното име на файла (напр. "TiO2 Доклад — 14-20 Юли 2026.html")
        parent_folder_id: (опц.) ID на папка в Drive. Ако None — качва в root.

    Returns:
        View URL на файла в Google Drive
    """
    service = get_drive_service()

    file_metadata = {"name": filename, "mimeType": "text/html"}
    if parent_folder_id:
        file_metadata["parents"] = [parent_folder_id]

    media = MediaInMemoryUpload(
        html_content.encode("utf-8"),
        mimetype="text/html",
        resumable=False,
    )

    try:
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, webViewLink, name",
        ).execute()

        file_id = file.get("id")
        view_url = file.get("webViewLink", f"https://drive.google.com/file/d/{file_id}/view")

        # Даваме достъп за четене на всеки с линк (опционално)
        # Разкоментирай ако искаш да споделяш доклади с колеги:
        # service.permissions().create(
        #     fileId=file_id,
        #     body={"type": "anyone", "role": "reader"},
        # ).execute()

        logger.info(f"✅ HTML доклад качен в Drive: {filename}")
        logger.info(f"   URL: {view_url}")
        return view_url

    except Exception as e:
        logger.error(f"❌ Грешка при качване в Drive: {e}")
        raise
