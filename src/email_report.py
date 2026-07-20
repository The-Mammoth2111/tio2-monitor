"""
email_report.py — Генерира стилизиран HTML email доклад и го изпраща чрез Gmail SMTP.
"""

import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# HTML ГЕНЕРАТОР
# ─────────────────────────────────────────────

def _importance_color(score) -> tuple[str, str]:
    """Връща (bg_color, text_color) според важността."""
    try:
        s = int(score)
    except (ValueError, TypeError):
        s = 3
    if s == 5:
        return "#fce7f3", "#9d174d"
    if s == 4:
        return "#dbeafe", "#1e40af"
    if s == 3:
        return "#fef3c7", "#92400e"
    return "#f1f5f9", "#475569"


def _type_badge(article_type: str) -> str:
    colors = {
        "Финансови":   ("badge-fin",   "Финансови"),
        "Регулаторни": ("badge-reg",   "Регулаторни"),
        "Цени":        ("badge-price", "Цени"),
        "Продукти":    ("badge-prod",  "Продукти"),
        "Новини":      ("badge-news",  "Новини"),
    }
    cls, label = colors.get(article_type, ("badge-news", article_type))
    return f'<span class="badge {cls}">{label}</span>'


def _articles_by_company(articles: list[dict]) -> dict:
    """Групира статии по компания."""
    grouped = defaultdict(list)
    for art in articles:
        company = art.get('company', 'ОБЩИ')
        grouped[company].append(art)
    return dict(grouped)


def _render_company_section(company: str, articles: list[dict]) -> str:
    """Рендира HTML секция за една компания."""
    items_html = ""
    for art in sorted(articles, key=lambda x: x.get('ai_importance', 3), reverse=True):
        importance = art.get('ai_importance', 3)
        bg, color = _importance_color(importance)
        url = art.get('url', '#')
        title = art.get('title', '')
        summary = art.get('summary', '')[:200]
        source = art.get('source', '')
        date = art.get('date', '')
        badge = _type_badge(art.get('type', 'Новини'))

        link_html = (
            f'<a class="news-link" href="{url}" target="_blank">🔗 {source}</a>'
            if url and url != '#' else ''
        )

        items_html += f"""
        <div class="news-item">
          <div class="news-dot" style="color:{color};">→</div>
          <div class="news-text">
            <strong>{title}</strong> {badge}
            {"<br><small>" + summary + "</small>" if summary else ""}
            <br>{link_html}
            {"<span class='news-date'>" + date + "</span>" if date else ""}
          </div>
        </div>"""

    flag = "🇨🇳" if any(art.get('company', '') in [
        'LB Group (Lomon Billions)', 'Jinan Yuxing Chemical',
        'Henan Billions Chemicals', 'Shandong Doguide Group'
    ] for art in articles) else "🏭"

    return f"""
    <div class="company-card">
      <div class="company-header">
        <div class="company-name">{flag} {company}</div>
        <span class="badge badge-count">{len(articles)} статии</span>
      </div>
      {items_html}
    </div>"""


def build_html_email(articles: list[dict], summary_data: dict,
                      period_str: str, sheets_url: str) -> str:
    """
    Изгражда пълния HTML email от динамичните данни.
    Връща HTML string готов за изпращане.
    """
    now_str = datetime.now().strftime("%d %b %Y, %H:%M UTC")

    # Статистики
    companies_set = {a['company'] for a in articles if a.get('company') not in ('ОБЩИ', '')}
    reg_count = sum(1 for a in articles if a.get('type') == 'Регулаторни')
    fin_count = sum(1 for a in articles if a.get('type') == 'Финансови')

    # AI резюме
    executive_summary = summary_data.get("executive_summary", "")
    key_trends = summary_data.get("key_trends", [])
    trends_html = "".join(f"<li>{t}</li>" for t in key_trends) if key_trends else ""

    # Компании секции (без ОБЩИ)
    grouped = _articles_by_company(articles)
    company_order = [
        "Tronox", "Chemours", "Kronos Worldwide",
        "LB Group (Lomon Billions)", "Jinan Yuxing Chemical",
        "Henan Billions Chemicals", "Shandong Doguide Group",
    ]
    companies_html = ""
    for company in company_order:
        if company in grouped and grouped[company]:
            companies_html += _render_company_section(company, grouped[company])
    # Добавяме останали компании (ако има)
    for company, arts in grouped.items():
        if company not in company_order and company != "ОБЩИ" and arts:
            companies_html += _render_company_section(company, arts)

    # Регулаторни (от ОБЩИ или с тип Регулаторни)
    reg_articles = [a for a in articles if a.get('type') == 'Регулаторни']
    reg_html = ""
    for art in reg_articles[:5]:
        url = art.get('url', '#')
        title = art.get('title', '')
        date = art.get('date', '')
        source = art.get('source', '')
        reg_html += f"""
        <div class="reg-item">
          <div>⚠️</div>
          <div class="reg-text">
            <strong>{title}</strong><br>
            <a class="news-link" href="{url}" target="_blank">🔗 {source}</a>
            <span class="news-date">{date}</span>
          </div>
        </div>"""

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: Arial, sans-serif; background: #f0f4f8; margin: 0; padding: 20px; color: #1a202c; }}
  .wrapper {{ max-width: 680px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.12); }}
  .header {{ background: linear-gradient(135deg, #0f2444 0%, #1e4a8a 100%); color: white; padding: 32px 28px; text-align: center; }}
  .header h1 {{ margin: 0 0 6px; font-size: 22px; }}
  .header p {{ margin: 0; font-size: 13px; opacity: 0.75; }}
  .period {{ margin-top: 10px; display: inline-block; background: rgba(255,255,255,0.15); border-radius: 20px; padding: 4px 14px; font-size: 12px; }}
  .meta {{ background: #ebf4ff; padding: 10px 24px; display: flex; justify-content: space-around; flex-wrap: wrap; gap: 8px; border-bottom: 1px solid #dbeafe; }}
  .meta span {{ font-size: 11px; color: #2563eb; font-weight: 600; }}
  .section {{ padding: 20px 28px; border-bottom: 1px solid #f1f5f9; }}
  .section-title {{ font-size: 14px; font-weight: 700; color: #0f2444; margin: 0 0 14px; }}
  .ai-box {{ background: #f0fdf4; border-left: 4px solid #16a34a; padding: 16px 18px; border-radius: 0 8px 8px 0; font-size: 13px; color: #14532d; line-height: 1.75; }}
  .trends-list {{ margin: 10px 0 0 0; padding-left: 20px; }}
  .trends-list li {{ margin-bottom: 5px; font-size: 12px; color: #166534; }}
  .company-card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 14px 16px; margin-bottom: 12px; }}
  .company-header {{ display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }}
  .company-name {{ font-size: 13px; font-weight: 700; color: #0f172a; flex: 1; }}
  .badge {{ font-size: 10px; padding: 2px 8px; border-radius: 12px; font-weight: 600; }}
  .badge-fin   {{ background: #d1fae5; color: #065f46; }}
  .badge-news  {{ background: #dbeafe; color: #1e40af; }}
  .badge-price {{ background: #fef3c7; color: #92400e; }}
  .badge-reg   {{ background: #fce7f3; color: #9d174d; }}
  .badge-prod  {{ background: #ede9fe; color: #5b21b6; }}
  .badge-count {{ background: #e0f2fe; color: #0369a1; }}
  .news-item {{ display: flex; align-items: flex-start; gap: 8px; margin-bottom: 9px; padding-bottom: 9px; border-bottom: 1px solid #e9edf2; font-size: 12.5px; }}
  .news-item:last-child {{ margin-bottom: 0; padding-bottom: 0; border-bottom: none; }}
  .news-dot {{ font-size: 16px; line-height: 1.3; flex-shrink: 0; }}
  .news-text {{ color: #334155; line-height: 1.55; flex: 1; }}
  .news-link {{ display: inline-block; margin-top: 4px; font-size: 11px; color: #2563eb; text-decoration: none; background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 4px; padding: 2px 7px; margin-right: 4px; }}
  .news-date {{ font-size: 10px; color: #94a3b8; margin-left: 4px; }}
  .stats {{ display: flex; gap: 10px; flex-wrap: wrap; }}
  .stat {{ flex: 1; min-width: 100px; background: #f1f5f9; border-radius: 8px; padding: 14px 10px; text-align: center; border: 1px solid #e2e8f0; }}
  .stat-num {{ font-size: 24px; font-weight: 800; color: #2563eb; }}
  .stat-label {{ font-size: 10px; color: #64748b; margin-top: 3px; text-transform: uppercase; letter-spacing: 0.5px; }}
  .reg-item {{ display: flex; align-items: flex-start; gap: 8px; margin-bottom: 10px; padding: 10px 12px; background: #fff7ed; border-left: 3px solid #f97316; border-radius: 0 6px 6px 0; font-size: 12.5px; }}
  .reg-text {{ color: #431407; line-height: 1.5; }}
  .cta-section {{ text-align: center; padding: 24px 28px; background: #f8fafc; }}
  .btn-sheets {{ display: inline-block; background: #16a34a; color: white; padding: 12px 26px; border-radius: 8px; text-decoration: none; font-size: 14px; font-weight: 700; }}
  .footer {{ background: #1e293b; color: #94a3b8; padding: 16px 28px; font-size: 11px; text-align: center; line-height: 1.8; }}
  .footer a {{ color: #60a5fa; text-decoration: none; }}
</style>
</head>
<body>
<div class="wrapper">
  <div class="header">
    <h1>🔬 TiO₂ Market Intelligence Monitor</h1>
    <p>Автоматичен седмичен доклад — генериран от Claude AI</p>
    <div class="period">📅 Период: {period_str}</div>
  </div>
  <div class="meta">
    <span>🏭 {len(companies_set)} Компании</span>
    <span>📰 {len(articles)} Статии</span>
    <span>⚖️ {reg_count} Регулаторни</span>
    <span>💰 {fin_count} Финансови</span>
    <span>⏱ {now_str}</span>
  </div>

  <div class="section">
    <div class="section-title">🤖 AI Резюме (Claude)</div>
    <div class="ai-box">
      {executive_summary}
      {"<ul class='trends-list'>" + trends_html + "</ul>" if trends_html else ""}
    </div>
  </div>

  <div class="section">
    <div class="section-title">📊 Статистика</div>
    <div class="stats">
      <div class="stat"><div class="stat-num">{len(articles)}</div><div class="stat-label">Статии</div></div>
      <div class="stat"><div class="stat-num">{len(companies_set)}</div><div class="stat-label">Компании</div></div>
      <div class="stat"><div class="stat-num">{reg_count}</div><div class="stat-label">Регулаторни</div></div>
      <div class="stat"><div class="stat-num">{fin_count}</div><div class="stat-label">Финансови</div></div>
    </div>
  </div>

  <div class="section">
    <div class="section-title">🏭 По компании</div>
    {companies_html if companies_html else '<p style="color:#94a3b8;font-size:13px;">Няма новини по компании за тази седмица.</p>'}
  </div>

  {"<div class='section'><div class='section-title'>⚖️ Регулаторни промени</div>" + reg_html + "</div>" if reg_html else ""}

  <div class="cta-section">
    <p style="font-size:13px; color:#475569; margin-bottom:14px;">Пълната история на всички данни:</p>
    <a href="{sheets_url}" class="btn-sheets" target="_blank">📊 Отвори Google Sheets история</a>
    <p style="font-size:11px; color:#94a3b8; margin-top:14px;">Следващ доклад: следващия понеделник</p>
  </div>

  <div class="footer">
    TiO₂ Market Intelligence Monitor · Claude AI<br>
    Tronox · Kronos · Chemours · LB Group · Jinan Yuxing · Henan Billions · Shandong Doguide
  </div>
</div>
</body>
</html>"""


# ─────────────────────────────────────────────
# ИЗПРАЩАНЕ НА EMAIL
# ─────────────────────────────────────────────

def send_email(html_content: str, subject: str, recipient: str) -> None:
    """
    Изпраща HTML email чрез Gmail SMTP.
    Нужни environment variables:
      GMAIL_USER         — от кой адрес се изпраща
      GMAIL_APP_PASSWORD — App Password от Google Акаунт
    """
    sender = os.environ.get("GMAIL_USER", "")
    password = os.environ.get("GMAIL_APP_PASSWORD", "")

    if not sender or not password:
        raise ValueError("GMAIL_USER или GMAIL_APP_PASSWORD не са зададени!")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient

    # Plain text fallback
    plain_text = f"TiO2 Monitor — {subject}\n\nОтвори HTML версията в email клиента си."
    msg.attach(MIMEText(plain_text, "plain", "utf-8"))
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, password)
            server.sendmail(sender, recipient, msg.as_string())
        logger.info(f"✅ Email изпратен до {recipient}")
    except Exception as e:
        logger.error(f"❌ Грешка при изпращане на email: {e}")
        raise
