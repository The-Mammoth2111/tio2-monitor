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
        "Суровини":    ("badge-comm",  "Суровини"),
        "Макро":       ("badge-macro", "Макро"),
        "Валути":      ("badge-fx",    "Валути"),
        "Енергия":     ("badge-energy","Енергия"),
        "Търсене":     ("badge-demand","Търсене"),
        "Логистика":   ("badge-logi",  "Логистика"),
        "Капацитет":   ("badge-cap",   "Капацитет"),
        "Разследвания":("badge-inv",   "Разследване"),
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
                      period_str: str, sheets_url: str,
                      capacity_data: dict | None = None) -> str:
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
            # Пропускаме суровини и макро — те имат свои секции
            if all(a.get('type') in ('Суровини', 'Макро', 'Валути', 'Енергия', 'Търсене', 'Логистика', 'Капацитет', 'Разследвания') for a in arts):
                continue
            companies_html += _render_company_section(company, arts)

    # ── Суровини ──
    comm_articles = [a for a in articles if a.get('type') == 'Суровини']
    commodity_html = ""
    sulfur_articles = [a for a in comm_articles if 'Сяра' in a.get('company', '')]
    if sulfur_articles:
        commodity_html += """
        <div class="sulfur-alert">
          ⚠️ <strong>Сярата е критичен разходен фактор.</strong> Сулфатният метод изисква 3–4 тона сярна киселина на тон TiO₂.
          Засегнати: Police, Precheza, Kronos, LB Group, Doguide, Yuxing.
        </div>"""
    for art in comm_articles[:8]:
        url_c = art.get('url', '#')
        title_c = art.get('title', '')
        company_c = art.get('company', '')
        source_c = art.get('source', '')
        date_c = art.get('date', '')
        icon = "🟡" if "Сяра" in company_c and "киселина" not in company_c else ("🔴" if "киселина" in company_c else "⚫")
        commodity_html += f"""
        <div class="comm-item">
          <div>{icon}</div>
          <div class="comm-text">
            <strong>{title_c}</strong><br>
            <small style="color:#92400e;">{company_c}</small><br>
            <a class="news-link" href="{url_c}" target="_blank">🔗 {source_c}</a>
            <span class="news-date">{date_c}</span>
          </div>
        </div>"""

    # ── Макро индикатори ──
    macro_articles = [a for a in articles if a.get('type') == 'Макро']
    macro_html = ""
    if macro_articles:
        macro_html += '<div class="macro-grid">'
        seen_regions = set()
        for art in macro_articles:
            comp = art.get('company', '')
            region_key = comp.split('—')[0].strip()
            if region_key in seen_regions:
                continue
            seen_regions.add(region_key)
            url_m = art.get('url', '#')
            title_m = art.get('title', '')[:80]
            macro_html += f"""
            <div class="macro-card">
              <div class="macro-region">{region_key}</div>
              <div class="macro-title">{title_m}</div>
              <a class="news-link" href="{url_m}" target="_blank" style="margin-top:6px;">🔗 Виж</a>
            </div>"""
        macro_html += '</div>'
        macro_html += '<p style="font-size:11px;color:#64748b;margin-top:10px;">💡 Лихвените проценти влияят на строителството и автомобилния сектор — основни потребители на TiO₂.</p>'

    # ── Валутни курсове ──
    fx_articles = [a for a in articles if a.get('type') == 'Валути']
    fx_html = ""
    if fx_articles:
        fx_html += '<div class="fx-grid">'
        seen_pairs = set()
        for art in fx_articles:
            comp = art.get('company', '')
            pair_key = comp.split('(')[0].strip()
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)
            name_part = comp.split('(')[1].rstrip(')') if '(' in comp else ''
            url_f = art.get('url', '#')
            title_f = art.get('title', '')[:75]
            fx_html += f"""
            <div class="fx-card">
              <div class="fx-pair">{pair_key}</div>
              <div class="fx-name">{name_part}</div>
              <div class="fx-title">{title_f}</div>
              <a class="news-link" href="{url_f}" target="_blank" style="margin-top:6px;">🔗 Виж</a>
            </div>"""
        fx_html += '</div>'
        fx_html += """
        <div class="fx-logic">
          <strong>💡 Как валутите влияят на TiO₂ пазара:</strong><br><br>
          📈 <strong>Силен долар</strong> (EUR/USD ↓ под 1.05) → европейските производители
          (Police, Precheza, Indorama, Kronos EU) стават <strong>по-конкурентни при износ</strong>
          на изток и към САЩ — продуктите им са по-евтини в доларово изражение.<br><br>
          📉 <strong>Слаб долар</strong> (EUR/USD ↑ над 1.15) → европейският износ
          <strong>поскъпва и губи конкурентоспособност</strong>; американските (Tronox, Chemours, INEOS)
          и китайските производители печелят предимство.<br><br>
          🇨🇳 <strong>USD/CNY нагоре</strong> (слаб юан) → китайският износ поевтинява →
          повече ценови натиск върху европейските и американските производители.
        </div>"""

    # ── Капацитет ──
    cap_articles = [a for a in articles if a.get('type') == 'Капацитет']
    capacity_html = ""
    if capacity_data:
        offline = capacity_data.get("offline_kt", 0)
        online = capacity_data.get("online_kt", 0)
        net = capacity_data.get("net_kt", 0)
        net_cls = "cap-out" if net < 0 else "cap-in"
        capacity_html += f"""
        <div class="cap-summary">
          <div class="cap-box cap-box-out"><div class="cap-num cap-out">-{offline}</div><div class="cap-label">кт извън пазара</div></div>
          <div class="cap-box cap-box-in"><div class="cap-num cap-in">+{online}</div><div class="cap-label">кт рестартират</div></div>
          <div class="cap-box cap-box-net"><div class="cap-num {net_cls}">{net:+}</div><div class="cap-label">нетен баланс (кт)</div></div>
        </div>
        <table class="cap-table">
          <tr><th>Обект</th><th>Капацитет</th><th>Процес</th><th>Статус</th><th>Дата</th></tr>"""
        for e in capacity_data.get("events", []):
            cap = f"{e['capacity_kt']} кт" if e.get("capacity_kt") else "—"
            status = e.get("status", "")
            cls = "cap-out" if status.startswith(("ЗАТВОРЕН", "СПРЯН")) else "cap-in"
            proc = "хлориден" if e.get("process") == "chloride" else "сулфатен"
            capacity_html += f"""
          <tr><td>{e['site']}</td><td>{cap}</td><td>{proc}</td><td class="{cls}">{status}</td><td>{e.get('date','')}</td></tr>"""
        capacity_html += "</table>"
    for art in cap_articles[:5]:
        capacity_html += f"""
        <div class="comm-item"><div>🏗️</div><div class="comm-text">
          <strong>{art.get('title','')}</strong><br>
          <a class="news-link" href="{art.get('url','#')}" target="_blank">🔗 {art.get('source','')}</a>
          <span class="news-date">{art.get('date','')}</span>
        </div></div>"""

    # ── Енергия ──
    energy_articles = [a for a in articles if a.get('type') == 'Енергия']
    energy_html = ""
    if energy_articles:
        energy_html += '<p style="font-size:11.5px;color:#7c2d12;margin-bottom:10px;">⚡ <strong>Хлоридният метод изисква над 1000°C.</strong> Високите енергийни цени в Европа са пряката причина за затварянето на Venator Greatham и Tronox Botlek.</p>'
    for art in energy_articles[:6]:
        energy_html += f"""
        <div class="energy-item"><div>⚡</div><div>
          <strong>{art.get('title','')}</strong><br>
          <small>{art.get('company','')}</small><br>
          <a class="news-link" href="{art.get('url','#')}" target="_blank">🔗 {art.get('source','')}</a>
          <span class="news-date">{art.get('date','')}</span>
        </div></div>"""

    # ── Търсене ──
    demand_articles = [a for a in articles if a.get('type') == 'Търсене']
    demand_html = ""
    if demand_articles:
        demand_html += '<p style="font-size:11.5px;color:#14532d;margin-bottom:10px;">📈 <strong>Опреждащ индикатор.</strong> Отчетите на производителите на бои показват реалното търсене 1-2 тримесечия преди то да се отрази в TiO₂ поръчките.</p>'
    for art in demand_articles[:8]:
        demand_html += f"""
        <div class="demand-item"><div>📈</div><div>
          <strong>{art.get('title','')}</strong><br>
          <small>{art.get('company','')}</small><br>
          <a class="news-link" href="{art.get('url','#')}" target="_blank">🔗 {art.get('source','')}</a>
          <span class="news-date">{art.get('date','')}</span>
        </div></div>"""

    # ── Логистика ──
    logi_articles = [a for a in articles if a.get('type') == 'Логистика']
    logistics_html = ""
    if logi_articles:
        logistics_html += '<p style="font-size:11.5px;color:#312e81;margin-bottom:10px;">🚢 <strong>Скритият конкурентен фактор.</strong> При скок в навлата Шанхай→Ротердам китайското ценово предимство в Европа изчезва без никаква промяна в заводската цена.</p>'
    for art in logi_articles[:6]:
        logistics_html += f"""
        <div class="logi-item"><div>🚢</div><div>
          <strong>{art.get('title','')}</strong><br>
          <small>{art.get('company','')}</small><br>
          <a class="news-link" href="{art.get('url','#')}" target="_blank">🔗 {art.get('source','')}</a>
          <span class="news-date">{art.get('date','')}</span>
        </div></div>"""

    # ── Търговски разследвания ──
    inv_articles = [a for a in articles if a.get('type') == 'Разследвания']
    investigations_html = ""
    if inv_articles:
        investigations_html += '<p style="font-size:11.5px;color:#701a75;margin-bottom:10px;">🔍 <strong>Ранен сигнал.</strong> Инициирането на разследване движи пазара месеци преди финалното решение — дава време за реакция при договаряне.</p>'
    for art in inv_articles[:6]:
        investigations_html += f"""
        <div class="inv-item"><div>🔍</div><div>
          <strong>{art.get('title','')}</strong><br>
          <small>{art.get('company','')}</small><br>
          <a class="news-link" href="{art.get('url','#')}" target="_blank">🔗 {art.get('source','')}</a>
          <span class="news-date">{art.get('date','')}</span>
        </div></div>"""

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
  .badge-comm  {{ background: #fef08a; color: #713f12; }}
  .badge-macro {{ background: #ddd6fe; color: #4c1d95; }}
  .macro-grid {{ display: flex; gap: 8px; flex-wrap: wrap; }}
  .macro-card {{ flex: 1; min-width: 130px; background: #faf5ff; border: 1px solid #ddd6fe; border-left: 3px solid #7c3aed; border-radius: 0 8px 8px 0; padding: 10px 12px; }}
  .macro-region {{ font-size: 11px; font-weight: 700; color: #5b21b6; margin-bottom: 4px; }}
  .macro-title {{ font-size: 11px; color: #6b21a8; line-height: 1.4; }}
  .comm-item {{ display: flex; align-items: flex-start; gap: 8px; margin-bottom: 8px; padding: 10px 12px; background: #fffbeb; border-left: 3px solid #f59e0b; border-radius: 0 6px 6px 0; font-size: 12.5px; }}
  .comm-text {{ color: #78350f; line-height: 1.5; }}
  .sulfur-alert {{ background: #fef2f2; border: 1px solid #fca5a5; border-radius: 8px; padding: 12px 14px; margin-bottom: 10px; font-size: 12px; color: #991b1b; }}
  .badge-fx {{ background: #cffafe; color: #155e75; }}
  .fx-grid {{ display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 10px; }}
  .fx-card {{ flex: 1; min-width: 150px; background: #ecfeff; border: 1px solid #a5f3fc; border-left: 3px solid #0891b2; border-radius: 0 8px 8px 0; padding: 10px 12px; }}
  .fx-pair {{ font-size: 13px; font-weight: 800; color: #0e7490; font-family: monospace; }}
  .fx-name {{ font-size: 10px; color: #155e75; margin-bottom: 6px; }}
  .fx-title {{ font-size: 11px; color: #164e63; line-height: 1.4; }}
  .fx-logic {{ background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 8px; padding: 12px 14px; font-size: 11.5px; color: #075985; line-height: 1.6; margin-top: 10px; }}
  .fx-logic strong {{ color: #0c4a6e; }}
  .badge-energy {{ background: #fed7aa; color: #7c2d12; }}
  .badge-demand {{ background: #bbf7d0; color: #14532d; }}
  .badge-logi   {{ background: #e0e7ff; color: #312e81; }}
  .badge-cap    {{ background: #fecaca; color: #7f1d1d; }}
  .badge-inv    {{ background: #f5d0fe; color: #701a75; }}
  .energy-item {{ display: flex; gap: 8px; margin-bottom: 8px; padding: 10px 12px; background: #fff7ed; border-left: 3px solid #ea580c; border-radius: 0 6px 6px 0; font-size: 12.5px; color: #7c2d12; line-height: 1.5; }}
  .demand-item {{ display: flex; gap: 8px; margin-bottom: 8px; padding: 10px 12px; background: #f0fdf4; border-left: 3px solid #16a34a; border-radius: 0 6px 6px 0; font-size: 12.5px; color: #14532d; line-height: 1.5; }}
  .logi-item {{ display: flex; gap: 8px; margin-bottom: 8px; padding: 10px 12px; background: #eef2ff; border-left: 3px solid #4f46e5; border-radius: 0 6px 6px 0; font-size: 12.5px; color: #312e81; line-height: 1.5; }}
  .inv-item {{ display: flex; gap: 8px; margin-bottom: 8px; padding: 10px 12px; background: #fdf4ff; border-left: 3px solid #a21caf; border-radius: 0 6px 6px 0; font-size: 12.5px; color: #701a75; line-height: 1.5; }}
  .cap-table {{ width: 100%; border-collapse: collapse; font-size: 11.5px; margin-bottom: 10px; }}
  .cap-table th {{ background: #1e293b; color: #cbd5e1; padding: 7px 9px; text-align: left; font-size: 10px; text-transform: uppercase; }}
  .cap-table td {{ padding: 7px 9px; border-bottom: 1px solid #e2e8f0; color: #334155; }}
  .cap-out {{ color: #dc2626; font-weight: 700; }}
  .cap-in  {{ color: #16a34a; font-weight: 700; }}
  .cap-summary {{ display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }}
  .cap-box {{ flex: 1; min-width: 110px; border-radius: 8px; padding: 12px 10px; text-align: center; }}
  .cap-box-out {{ background: #fef2f2; border: 1px solid #fca5a5; }}
  .cap-box-in {{ background: #f0fdf4; border: 1px solid #86efac; }}
  .cap-box-net {{ background: #eff6ff; border: 1px solid #93c5fd; }}
  .cap-num {{ font-size: 20px; font-weight: 800; }}
  .cap-label {{ font-size: 10px; color: #64748b; margin-top: 3px; }}
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

  {"<div class='section'><div class='section-title'>🟡 Цени на суровини</div>" + commodity_html + "</div>" if commodity_html else ""}

  {"<div class='section'><div class='section-title'>🏦 Лихвени проценти — макроикономически контекст</div>" + macro_html + "</div>" if macro_html else ""}

  {"<div class='section'><div class='section-title'>💱 Валутни курсове — износна конкурентоспособност</div>" + fx_html + "</div>" if fx_html else ""}

  {"<div class='section'><div class='section-title'>🏗️ Капацитет — затваряния и рестарти</div>" + capacity_html + "</div>" if capacity_html else ""}

  {"<div class='section'><div class='section-title'>⚡ Енергийни цени</div>" + energy_html + "</div>" if energy_html else ""}

  {"<div class='section'><div class='section-title'>📈 Индикатори на търсенето — бои, строителство, авто</div>" + demand_html + "</div>" if demand_html else ""}

  {"<div class='section'><div class='section-title'>🚢 Логистика и навла</div>" + logistics_html + "</div>" if logistics_html else ""}

  {"<div class='section'><div class='section-title'>🔍 Търговски разследвания — ранни сигнали</div>" + investigations_html + "</div>" if investigations_html else ""}

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
