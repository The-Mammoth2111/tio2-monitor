# 🔬 TiO2 Market Intelligence Monitor

Автоматичен седмичен мониторинг на пазара на титанов диоксид (TiO₂).  
Събира новини, генерира AI резюме на **Български** и изпраща email доклад.

---

## 📋 Какво прави

Всеки **понеделник в 10:00 ч. (BG)** автоматично:

1. **Събира новини** от официалните сайтове на 7 компании + Google News RSS + медии
2. **Генерира AI резюме** на Български чрез Claude API
3. **Записва в Google Sheets** — История (всяка статия) + Архив (един ред/седмица)
4. **Архивира HTML доклад** в Google Drive
5. **Изпраща Email** с пълния стилизиран доклад

---

## 🏭 Следени компании

| Компания | Борса | Държава |
|---|---|---|
| Tronox | NYSE: TROX | 🇺🇸 |
| Chemours | NYSE: CC | 🇺🇸 |
| Kronos Worldwide | NYSE: KRO | 🇺🇸 |
| LB Group (Lomon Billions) | Shenzhen | 🇨🇳 |
| Jinan Yuxing Chemical | — | 🇨🇳 |
| Henan Billions Chemicals | — | 🇨🇳 |
| Shandong Doguide Group | — | 🇨🇳 |

---

## 📁 Структура

```
tio2-monitor/
├── .github/workflows/weekly_monitor.yml   ← GitHub Actions cron
├── src/
│   ├── main.py           ← Главен orchestrator
│   ├── scraper.py        ← Web scraping + RSS
│   ├── dedup.py          ← Дедупликация
│   ├── ai_summary.py     ← Claude API
│   ├── sheets.py         ← Google Sheets
│   ├── drive.py          ← Google Drive
│   └── email_report.py   ← HTML Email
├── config/companies.json ← Конфигурация
├── requirements.txt
└── .env.example
```

---

## ⚙️ Инсталация и настройка

### 1. Клонирай репото

```bash
git clone https://github.com/YOUR_USERNAME/tio2-monitor.git
cd tio2-monitor
pip install -r requirements.txt
```

### 2. Вземи API ключовете

| Credential | Откъде |
|---|---|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) → API Keys |
| `GMAIL_APP_PASSWORD` | Google Акаунт → Сигурност → 2-Step → **App Passwords** |
| `GOOGLE_CREDENTIALS_JSON` | Google Cloud Console → Service Account → JSON key |

### 3. Настрой Google Service Account

1. Отиди на [console.cloud.google.com](https://console.cloud.google.com)
2. Създай нов проект (или използвай съществуващ)
3. Включи: **Google Sheets API** + **Google Drive API**
4. Създай **Service Account** → Download JSON
5. **Сподели** двата Google Sheet-а с email-а на Service Account:
   - `TiO2 Monitor — История` → Share → добави service account email → Editor
   - `TiO2 Monitor — Архив` → Share → добави service account email → Editor

### 4. Google Sheets (вече създадени)

| Sheet | ID |
|---|---|
| История на докладите | `1hIS_KRRCTVzA-g-KeBM2dnSWlwPnWMMw3l2YW2tPF60` |
| Архив на Доклади | `1jMDLrPRZgTG_O6CwdoX8EP5ev52bUrbTWeW9MYKAvdM` |

### 5. Добави GitHub Secrets

В GitHub репото: **Settings → Secrets and variables → Actions → New repository secret**

```
ANTHROPIC_API_KEY
GMAIL_USER
GMAIL_APP_PASSWORD
RECIPIENT_EMAIL
GOOGLE_CREDENTIALS_JSON
SHEETS_HISTORY_ID
SHEETS_ARCHIVE_ID
```

### 6. Тествай локално

```bash
cp .env.example .env
# Попълни стойностите в .env

# Зареди .env и стартирай
export $(cat .env | xargs)
python src/main.py
```

---

## 🔄 Ръчно стартиране от GitHub

1. GitHub → **Actions** таб
2. Избери **TiO2 Monitor — Седмичен доклад**
3. Клик **Run workflow** → **Run workflow**

Можеш да зададеш и различен брой дни назад (напр. `14` за двуседмичен доклад).

---

## 📊 Изходни данни

### Google Sheets — История
| Колона | Описание |
|---|---|
| Дата | Дата на статията |
| Компания | Tronox, Chemours, и т.н. |
| Тип | Новини / Финансови / Регулаторни / Цени |
| Заглавие | Заглавие на статията |
| Резюме | Кратко резюме (до 500 символа) |
| Извор | Медия / RSS |
| URL | Линк към оригиналната статия |
| AI Важност (1-5) | Оценка от Claude |
| AI Причина | Обяснение на оценката |

### Google Sheets — Архив
Един ред на седмица с AI резюме и линкове към HTML доклада.

---

## 🛠 Технологии

- **Python 3.11** — основен език
- **GitHub Actions** — безплатен cron scheduler
- **Claude API (claude-sonnet-4-6)** — AI резюме на Български
- **gspread** — Google Sheets интеграция
- **Google Drive API** — архивиране на HTML доклади
- **feedparser** — RSS парсиране
- **BeautifulSoup4** — HTML scraping
- **Gmail SMTP** — изпращане на email

---

## 📜 Лиценз

MIT License — използвай свободно.
