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

Оценки за важност:
5 = Критично важно (голяма ценова промяна, регулация, фалит, придобиване)
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
