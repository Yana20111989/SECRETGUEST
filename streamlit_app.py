#  streamlit_app.py    •    Mystery Shopper PSB  (web-GUI)
#  Финал v1.2 – с лемматизацией (pymorphy2) и пошаговой логикой
#  ---------------------------------------------------------------
import streamlit as st
import re, json
from collections import deque
from typing import List, Dict

# ---------- NLP-утилита (лемматизация) --------------------------
try:
    from pymorphy2 import MorphAnalyzer
    morph = MorphAnalyzer()
except ImportError:      # при локальном запуске без pymorphy2
    morph = None

def normalize(text: str) -> str:
    """Нижний регистр + леммы (если pymorphy2 доступна)."""
    text = re.sub(r"[^\w\s]", " ", text.lower())
    if not morph:
        return re.sub(r"\s+", " ", text).strip()
    lemmas = [morph.parse(w)[0].normal_form for w in text.split()]
    return " ".join(lemmas)

def has_all(keywords: List[str], answer: str) -> bool:
    ans = normalize(answer)
    return all(k in ans for k in keywords)

def has_any(keywords: List[str], answer: str) -> bool:
    ans = normalize(answer)
    return any(k in ans for k in keywords)

# ---------- Анкета с обновлёнными критериями --------------------
CLIENT_NAME = "Михаил"

CRITERIA: Dict[str, Dict] = json.loads("""{
  "1. ОБСЛУЖИВАНИЕ": {
    "weight": 0.25,
    "items": {
      "1.1 Приветствие первым":              {"w":0.02, "kw":["здравствовать","добрый"]},
      "1.2 Представился":                    {"w":0.02, "kw":["меня","звать"]},
      "1.3 Уточнил, как обращаться":         {"w":0.03, "kw":["как","обращаться"]},
      "1.4 Обращался по имени":              {"w":0.04, "kw":[]},
      "1.5 Вежливость":                      {"w":0.05, "kw":[]},
      "1.6 Не перебивал":                    {"w":0.01, "kw":[]},
      "1.7 Конфиденциальность":              {"w":0.04, "kw":[]},
      "1.8 Деловой стиль речи":              {"w":0.04, "kw":[]}
    }
  },
  "2. ВЫЯВЛЕНИЕ ПОТРЕБНОСТЕЙ": {
    "weight": 0.15,
    "items": {
      "2.1 Цель визита":                     {"w":0.02, "kw":["цель"]},
      "2.2 ЗП-карта ПСБ":                    {"w":0.04, "kw":["зарплат","псб"]},
      "2.3 Сумма-срок-цель кредита":         {"w":0.06, "kw":["сумм","срок","цель"]},
      "2.4 Уровень дохода":                  {"w":0.03, "kw":["доход"]}
    }
  },
  "3. ПРЕЗЕНТАЦИЯ ПРОДУКТА": {
    "weight": 0.20,
    "items": {
      "3.1 8 требований к заёмщику":         {"w":0.08, "kw":["гражданство","возраст","регистрация","проживание","работа","общий","стаж","телефон"]},
      "3.2 Расчёт платежа":                  {"w":0.04, "kw":["платеж","ежемесячный"]},
      "3.3 Комфортность платежа":            {"w":0.04, "kw":["комфорт","удобно","подходит"]},
      "3.4 Акция «Лучше 0»":                 {"w":0.04, "kw":["лучше","0","ноль","акция"]}
    }
  },
  "4. СОЗДАНИЕ ЗАЯВКИ": {
    "weight": 0.05,
    "items": {
      "4.1 Предложил оформить сейчас":       {"w":0.02, "kw":["оформ","сейчас"]},
      "4.2 Перечень документов":             {"w":0.03, "kw":["паспорт","снилс","доход","трудов"]}
    }
  },
  "5. КРОСС-ПРОДАЖИ": {
    "weight": 0.10,
    "items": {
      "5.1 ИБ/карта/страховой продукт":      {"w":0.10, "kw_any":["интернет банк","дебет","карта","страхов"]}
    }
  },
  "6. ЗАВЕРШЕНИЕ": {
    "weight": 0.15,
    "items": {
      "6.1 Остались вопросы":               {"w":0.02, "kw":["вопрос"]},
      "6.2 Повторная встреча":              {"w":0.03, "kw":["встреч"]},
      "6.3 Телефон":                        {"w":0.03, "kw":["телефон"]},
      "6.4 Контакты":                       {"w":0.03, "kw":["контакт"]},
      "6.5 Рекламные материалы":            {"w":0.02, "kw":["буклет","материал"]},
      "6.6 Прощание+приглашение":           {"w":0.02, "kw":["до свидан","ждём","ждем","рады"]}
    }
  }
}""")   # JSON-блок чтобы не занимать много строк кода

STAGE7_WEIGHT = 0.10
STAGE7_TEXT = """\
1. Я обратил внимание на: комфортность зала (температура, чистота, отсутствие запахов)
2. В клиентской зоне отсутствуют посторонние шумы
3. Сотрудники одеты в деловом стиле и выглядят опрятно
4. Наличие корпоративных атрибутов: платок/галстук и именной бейдж
"""

# ---------- 4. Начальная и сервисная логика -------------------

def build_queue() -> deque:
    q = deque()
    for sec, data in CRITERIA.items():
        for crit in data["items"]:
            q.append((sec, crit))
    q.append(("7. ДОПОЛНИТЕЛЬНАЯ ИНФОРМАЦИЯ", "stage7"))
    return q

def init_state():
    st.session_state.queue = build_queue()
    st.session_state.scores = {sec: 0.0 for sec in CRITERIA}
    st.session_state.stage7_done = False
    st.session_state.finished = False
    st.session_state.history = []             # (speaker, text)

if "queue" not in st.session_state:
    init_state()

def add_history(who, msg):
    st.session_state.history.append((who, msg))

# ---------- 5. UI (чат-интерфейс) -----------------------------

st.title("Симулятор тайного покупателя ПСБ")

for who, msg in st.session_state.history:
    st.chat_message(who).write(msg)

# Стартовый реплик тайного покупателя
if not st.session_state.history:
    greeting = "ТП: Здравствуйте! Хочу узнать об условиях кредита на ремонт квартиры."
    add_history("assistant", greeting)
    st.chat_message("assistant").write(greeting)

# ---------- 6. Обработка действий менеджера -------------------

def process_answer(ans: str):
    queue = st.session_state.queue
    sec, crit = queue[0]           # текущий критерий

    # --- special Stage 7 ---
    if crit == "stage7":
        if normalize(ans) in ("да", "все", "всё"):
            st.session_state.stage7_done = True
            queue.popleft()
            add_history("assistant", "✅  Этап 7 зачтён. Спасибо!")
        else:
            add_history("assistant", "⚠️  Для зачёта напишите «Да» или «Все».")
        return

    # --- обычная проверка ---
    cfg = CRITERIA[sec]["items"][crit]
    ok = False
    if crit.startswith("1.4"):
        ok = CLIENT_NAME.lower() in normalize(ans)
    elif "kw_any" in cfg:
        ok = has_any(cfg["kw_any"], ans)
    else:
        ok = has_all(cfg["kw"], ans)

    if ok:
        st.session_state.scores[sec] += cfg["w"]
        queue.popleft()
        add_history("assistant", "✅  Готово, переходим далее.")
    else:
        add_history("assistant", "⚠️  Информации недостаточно, дополните, пожалуйста.")

# ---------- 7. Вывод текущего вопроса или финального результата

if st.session_state.queue:
    current_sec, current_crit = st.session_state.queue[0]
    if current_crit == "stage7":
        prompt = f"ТП: Дополнительные критерии офиса:\n{STAGE7_TEXT}\nСоответствует ли всё перечисленному?"
    else:
        prompt = f"ТП (критерий {current_crit} секции «{current_sec}»): пожалуйста, предоставьте информацию."

    st.chat_message("assistant").write(prompt)
    answer = st.chat_input("Введите ответ менеджера …")
    if answer:
        add_history("user", answer)
        process_answer(answer)
        st.experimental_rerun()

else:
    # ---------- симуляция окончена ----------
    if not st.session_state.finished:
        total_score = sum(st.session_state.scores.values()) + (STAGE7_WEIGHT if st.session_state.stage7_done else 0)
        total_weight = sum(sec["weight"] for sec in CRITERIA.values()) + STAGE7_WEIGHT
        final_pct = round(total_score / total_weight * 100, 1)

        verdict = ("ОТЛИЧНО" if final_pct >= 90 else
                   "ХОРОШО" if final_pct >= 75 else
                   "УДОВЛЕТВОРИТЕЛЬНО" if final_pct >= 60 else
                   "НУЖНО ДОРАБОТАТЬ")

        result_msg = f"Итоговая оценка менеджера: {final_pct}%  •  Статус: {verdict}"
        add_history("assistant", result_msg)
        st.session_state.finished = True
        st.experimental_rerun()
