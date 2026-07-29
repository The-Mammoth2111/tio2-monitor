# 🔬 TiO2 Market Intelligence Monitor

Автоматичен седмичен мониторинг на пазара на титанов диоксид (TiO₂).  
Събира новини, генерира AI резюме на **Български** и изпраща email доклад.

---

## 📋 Какво прави

Всеки **понеделник в 10:00 ч. (BG)** автоматично:

1. **Събира новини** от официалните сайтове на 11 компании + суровини + Google News RSS + медии
2. **Генерира AI резюме** на Български чрез Claude API
3. **Записва в Google Sheets** — История (всяка статия) + Архив (един ред/седмица)
4. **Архивира HTML доклад** в Google Drive
5. **Изпраща Email** с пълния стилизиран доклад

---

## 🏭 Следени компании (11)

| Компания | Марка | Борса | Държава |
|---|---|---|---|
| Tronox | — | NYSE: TROX 📈 | 🇺🇸 |
| Chemours | Ti-Pure® | NYSE: CC 📈 | 🇺🇸 |
| Kronos Worldwide | KRONOS® | NYSE: KRO 📈 | 🇺🇸 |
| INEOS Pigments (Ashtabula) | — | Частна 🔒 | 🇺🇸 |
| LB Group (Lomon Billions) | TIOXIDE® | Частна 🔒 | 🇨🇳 |
| Jinan Yuxing Chemical | R818 | Частна 🔒 | 🇨🇳 |
| Henan Billions Chemicals | — | Частна 🔒 | 🇨🇳 |
| Shandong Doguide Group | SR-240 | Частна 🔒 | 🇨🇳 |
| Grupa Azoty Police | TYTANPOL® | WSE: PCE 📈 | 🇵🇱 |
| Precheza | PRETIOX® | Частна 🔒 (Agrofert) | 🇨🇿 |
| Indorama Advanced Oxides (Huelva) | — | Частна 🔒 | 🇪🇸 |

---

## 🧪 Следени суровини

| Суровина | Значение | Индикатор |
|---|---|---|
| 🟡 **Сяра** ⚠️ | **КРИТИЧЕН разходен фактор** — 3-4 т H₂SO₄ на 1 т TiO₂ | Tampa FL contract · Middle East FOB · China CFR |
| 🔴 Сярна киселина (H₂SO₄) | Директна суровина сулфатен метод | ICIS / Chemanalyst |
| ⚫ Илменит / Рутил | Минерална суровина за всички | TZMI / Wood Mac |

**Производители засегнати от цената на сярата (сулфатен метод):**  
Grupa Azoty Police · Precheza · Kronos · LB Group · Shandong Doguide · Jinan Yuxing

---

## 🏦 Макроикономически индикатори

| Централна банка | Регион | Влияние върху TiO₂ |
|---|---|---|
| 🇺🇸 **Federal Reserve** | САЩ | Строителство, автомобили, потребление на бои |
| 🇪🇺 **ECB** | Еврозона | Ключов за Police, Precheza, Indorama, Kronos EU |
| 🇯🇵 **Bank of Japan** | Япония | Азиатско търсене, валутни курсове JPY/USD |
| 🇨🇳 **PBOC (LPR)** | Китай | Критичен за LB Group, Doguide, Yuxing + строителство |

💡 *Лихвените проценти влияят пряко на строителството и автомобилния сектор — двата най-големи потребителя на TiO₂.*

---

## 💱 Валутни курсове — износна конкурентоспособност

| Двойка | Приоритет | Влияние |
|---|---|---|
| 💶 **EUR/USD** | ВИСОК | Определя конкурентоспособността на европейския износ |
| 🇨🇳 **USD/CNY** | ВИСОК | Определя китайския ценови натиск |
| 🇯🇵 **USD/JPY** | СРЕДЕН | Азиатско търсене |

### Логика на влиянието

**📈 Силен долар** (EUR/USD ↓ под 1.05)  
→ Европейските производители (**Police, Precheza, Indorama, Kronos EU**) стават **по-конкурентни при износ** на изток и към САЩ — продуктите им са по-евтини в доларово изражение.

**📉 Слаб долар** (EUR/USD ↑ над 1.15)  
→ Европейският износ **поскъпва и губи конкурентоспособност**; американските (**Tronox, Chemours, INEOS**) и китайските производители печелят предимство.

**🇨🇳 USD/CNY нагоре** (слаб юан)  
→ Китайският износ поевтинява → повече ценови натиск върху Европа и САЩ.

---

## 📁 Структура

```
tio2-monitor/
├── .github/workflows/weekly_monitor.yml   ← GitHub Actions cron
├── src/
│   ├── main.py           ← Главен orchestrator
│   ├── scraper.py        ← Web scraping + RSS + Суровини
│   ├── dedup.py          ← Дедупликация
│   ├── ai_summary.py     ← Claude API
│   ├── sheets.py         ← Google Sheets
│   ├── drive.py          ← Google Drive
│   └── email_report.py   ← HTML Email
├── config/companies.json ← Конфигурация (компании + суровини)
├── requirements.txt
└── .env.example
```

---

## ⚙️ Инсталация и настройка

### 1. Клонирай репото

```bash
git clone https://github.com/The-Mammoth2111/tio2-monitor.git
cd tio2-monitor
pip install -r requirements.txt
```

### 2. Вземи API ключовете

| Credential | Откъде |
|---|---|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) → API Keys |
| `GMAIL_APP_PASSWORD` | Google Акаунт → Сигурност → 2-Step → **App Passwords** |
| `GOOGLE_CREDENTIALS_JSON` | Google Cloud Console → Service Account → JSON key |

### 3. Google Sheets (вече създадени)

| Sheet | ID |
|---|---|
| История на докладите | `1hIS_KRRCTVzA-g-KeBM2dnSWlwPnWMMw3l2YW2tPF60` |
| Архив на Доклади | `1jMDLrPRZgTG_O6CwdoX8EP5ev52bUrbTWeW9MYKAvdM` |

### 4. Добави GitHub Secrets

**Settings → Secrets and variables → Actions → New repository secret**

```
ANTHROPIC_API_KEY
GMAIL_USER
GMAIL_APP_PASSWORD
RECIPIENT_EMAIL
GOOGLE_CREDENTIALS_JSON
SHEETS_HISTORY_ID
SHEETS_ARCHIVE_ID
```

---

## 🔄 Стартиране

**Автоматично:** Всеки понеделник 07:00 UTC (= 10:00 ч. BG)

**Ръчно от GitHub:**
1. Actions таб
2. TiO2 Monitor — Седмичен доклад
3. Run workflow → Run workflow

---

## 📊 Изходни данни

### Google Sheets — История
`Дата | Компания | Тип | Заглавие | Резюме | Извор | URL | AI Важност (1-5) | AI Причина`

### Google Sheets — Архив
Един ред на седмица с AI резюме и линкове към HTML доклада.

---

## 🛠 Технологии

- **Python 3.11** · **GitHub Actions** · **Claude API** · **gspread** · **Google Drive API** · **feedparser** · **BeautifulSoup4** · **Gmail SMTP**

---

## 📜 Лиценз

MIT License
