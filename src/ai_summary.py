"""
ai_summary.py — Генерира AI резюме и оценки на важност чрез Claude API.
Резюмето е на Български.
"""

import os
import json
import logging
import anthropic

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 2000


def _build_articles_text(articles: list[dict]) -> str:
    """Форматира статиите като текст за подаване към Claude."""
    lines = []
    for i, art in enumerate(articles, 1):
        lines.append(
            f"{i}. [{art['company']}] [{art['type']}] {art['title']}\n"
            f"   Дата: {art['date']} | Извор: {art['source']}\n"
            f"   {art['summary'][:250] if art['summary'] else '(без резюме)'}\n"
        )
    return "\n".join(lines)


def generate_summary(articles: list[dict], period_str: str) -> dict:
    """
    Изпраща статиите към Claude API и получава:
      - executive_summary: резюме на Български (5-8 изречения)
      - key_trends: списък с 3-5 ключови тенденции
      - articles_with_importance: оригиналните статии + AI оценка (1-5)
    """
    if not articles:
        return {
            "executive_summary": "Не са намерени новини за тази седмица.",
            "key_trends": [],
            "articles_with_importance": [],
        }

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    articles_text = _build_articles_text(articles)

    prompt = f"""Ти си TiO2 (титанов диоксид) пазарен анализатор. Получаваш списък с новини от седмицата {period_str}.

Производителите, които следим: Tronox, Chemours, Kronos Worldwide, LB Group (Lomon Billions), Jinan Yuxing, Henan Billions, Shandong Doguide.

НОВИНИ:
{articles_text}

ЗАДАЧА: Върни JSON обект (само JSON, без markdown блокове) с точно тази структура:
{{
  "executive_summary": "Резюме на БЪЛГАРСКИ от 5-8 изречения. Обхваща: ценови тенденции, регулаторни промени, финансови резултати, стратегически ходове на компаниите.",
  "key_trends": [
    "Тенденция 1 на Български",
    "Тенденция 2 на Български",
    "Тенденция 3 на Български"
  ],
  "article_scores": [
    {{"index": 1, "importance": 5, "reason": "кратко обяснение на Български"}},
    {{"index": 2, "importance": 3, "reason": "кратко обяснение на Български"}}
  ]
}}

ВАЖНО: Ако има новини за цени на СЯРА или СЯРНА КИСЕЛИНА — коментирай задължително как влияят на производителите със сулфатен метод (Police, Precheza, Kronos, LB Group, Doguide, Yuxing). Сулфатният процес изисква 3-4 тона сярна киселина на тон TiO₂.

Ако има новини за ЛИХВЕНИ ПРОЦЕНТИ (Fed, ECB, BOJ, PBOC) — коментирай как влияят на строителството и автомобилния сектор, които са основни потребители на TiO₂.

Ако има новини за ВАЛУТНИ КУРСОВЕ — приложи следната логика:
- СИЛЕН долар (EUR/USD пада под 1.05) → европейските производители (Police, Precheza, Indorama, Kronos EU) стават по-конкурентни при износ на изток и към САЩ, защото продуктите им са по-евтини в доларово изражение.
- СЛАБ долар (EUR/USD над 1.15) → европейският износ поскъпва и губи конкурентоспособност; американските (Tronox, Chemours, INEOS) и китайските производители печелят предимство.
- USD/CNY нагоре (слаб юан) → китайският износ поевтинява → повече ценови натиск върху Европа и САЩ.

Ако има новини за ЕНЕРГИЯ (TTF газ, електроенергия, Brent) — хлоридният метод изисква >1000°C. Високите енергийни цени в Европа са причина за затварянето на Venator Greatham и Tronox Botlek. Коментирай кога европейските производители влизат в зоната на загубата.

Ако има новини за ПРОИЗВОДИТЕЛИ НА БОИ (PPG, Sherwin-Williams, AkzoNobel, Jotun, Nippon Paint) или строителство/автомобили — това е сигнал за ТЪРСЕНЕТО 1-2 тримесечия напред. Коментирай какво означава за TiO₂ поръчките.

Ако има новини за ЛОГИСТИКА (навла Шанхай-Ротердам, Baltic Dry Index, Червено море, Ормузки проток) — при скок в навлата китайското ценово предимство в Европа изчезва без промяна в заводската цена. Това е ключов конкурентен фактор.

Ако има новини за КАПАЦИТЕТ (затваряния, рестарти, разширения) — това е НАЙ-СИЛНИЯТ ценови сигнал в индустрията. Над 1.1 млн. т (11% от световния пазар) излязоха 2025-2026. Всяко ново затваряне или рестарт променя баланса месеци напред. Дай приоритет 5 на такива новини.

Ако има новини за ТЪРГОВСКИ РАЗСЛЕДВАНИЯ — разграничи ФАЗАТА: инициирано разследване (ранен сигнал, движи пазара месеци преди решението) vs предварителни мита vs финални мита vs преглед. Инициирането е най-ценната информация, защото дава време за реакция.

Оценки за важност:
5 = Критично важно (голяма ценова промяна, регулация, фалит, придобиване, скок в цената на сярата)
4 = Важно (финансови резултати, значителна новина)
3 = Умерено важно (пазарни тенденции, продуктови новини)
2 = Ниска важност (общи новини за индустрията)
1 = Малка важност (PR, корпоративни съобщения)"""

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip()
        # Премахваме markdown блокове ако има
        raw = raw.replace("```json", "").replace("```", "").strip()
        result = json.loads(raw)

        # Добавяме AI оценките към статиите
        score_map = {s['index']: s for s in result.get('article_scores', [])}
        articles_enriched = []
        for i, art in enumerate(articles, 1):
            art_copy = art.copy()
            if i in score_map:
                art_copy['ai_importance'] = score_map[i].get('importance', '')
                art_copy['ai_reason'] = score_map[i].get('reason', '')
            else:
                art_copy['ai_importance'] = 3
                art_copy['ai_reason'] = ''
            articles_enriched.append(art_copy)

        logger.info(f"✅ AI резюме генерирано успешно ({len(articles_enriched)} статии оценени)")
        return {
            "executive_summary": result.get("executive_summary", ""),
            "key_trends": result.get("key_trends", []),
            "articles_with_importance": articles_enriched,
        }

    except json.JSONDecodeError as e:
        logger.error(f"❌ Грешка при парсиране на AI отговор: {e}")
        return _fallback_summary(articles, period_str)
    except Exception as e:
        logger.error(f"❌ Claude API грешка: {e}")
        return _fallback_summary(articles, period_str)


def _fallback_summary(articles: list[dict], period_str: str) -> dict:
    """Fallback при грешка с API — без AI резюме."""
    for art in articles:
        art['ai_importance'] = 3
        art['ai_reason'] = ''
    return {
        "executive_summary": f"Автоматичното AI резюме не беше генерирано за периода {period_str}. Намерени са {len(articles)} статии.",
        "key_trends": [],
        "articles_with_importance": articles,
    }
