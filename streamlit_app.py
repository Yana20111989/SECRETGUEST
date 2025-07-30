#  streamlit_app.py  •  Mystery Shopper PSB  (web-GUI, v2.3)
#  ------------------------------------------------------------------
#  • лемматизация pymorphy2
#  • гибкие корни (укороченные) — принимаются любые формы слова
#  • подсказка выводится после 3-й неудачной попытки
#  • критерий «обращение по имени» удалён окончательно
#  ------------------------------------------------------------------
import streamlit as st
import re, json
from collections import deque
from typing import List, Dict

# ---------------- NLP  (лемматизация) --------------------------
try:
    from pymorphy2 import MorphAnalyzer
    morph = MorphAnalyzer()
except ImportError:
    morph = None                     # симулятор работает и без pymorphy2

def normalize(text: str) -> str:
    text = re.sub(r"[^\w\s]", " ", text.lower())
    if not morph:
        return re.sub(r"\s+", " ", text).strip()
    return " ".join(morph.parse(w)[0].normal_form for w in text.split())

def has_all(keys: List[str], text: str) -> bool:
    t = normalize(text)
    return all(k in t for k in keys)

def has_any(keys: List[str], text: str) -> bool:
    t = normalize(text)
    return any(k in t for k in keys)

# ---------------- Анкета (укороченные корни) -------------------
CRITERIA: Dict[str, Dict] = json.loads("""{
  "1. ОБСЛУЖИВАНИЕ": {
    "weight": 0.21,
    "items": {
      "1.1 Приветствие первым":      {"w":0.02, "kw_any":["здрав","добр"]},
      "1.2 Представился":            {"w":0.02, "kw_all":["меня","звать"]},
      "1.3 Как обращаться":          {"w":0.03, "kw_all":["как","обращ"]},
      "1.5 Вежливость":              {"w":0.05},
      "1.6 Не перебивал":            {"w":0.01},
      "1.7 Конфиденциальность":      {"w":0.04},
      "1.8 Деловой стиль речи":      {"w":0.04}
    }
  },
  "2. ВЫЯВЛЕНИЕ ПОТРЕБНОСТЕЙ": {
    "weight": 0.18,
    "items": {
      "2.1 Цель визита":             {"w":0.02, "kw_any":["цель"]},
      "2.2 ЗП-карта ПСБ":            {"w":0.04, "kw_all":["зарплат","псб"]},
      "2.3 Сумма-срок-цель":         {"w":0.06, "kw_all":["сумм","срок","цель"]},
      "2.4 Доход":                   {"w":0.03, "kw_any":["доход"]},
      "2.5 Предупредил о вопросах":  {"w":0.03, "kw_any":["задам","нескольк","ряд","вопрос"]}
    }
  },
  "3. ПРЕЗЕНТАЦИЯ": {
    "weight": 0.20,
    "items": {
      "3.1 8 требований":           {"w":0.08, "kw_all":[
          "гражданств","возраст","регистрац","прожив",
          "работ","общ","стаж","телефон"]},
      "3.2 Расчёт платежа":          {"w":0.04, "kw_any":["платеж","ежемесяч"]},
      "3.3 Комфорт платежа":         {"w":0.04, "kw_any":["комфорт","удобн","подход"]},
      "3.4 Акция «Лучше 0»":         {"w":0.04, "kw_all":["лучш"], "kw_any2":["0","нол","акц"]}
    }
  },
  "4. СОЗДАНИЕ ЗАЯВКИ": {
    "weight": 0.05,
    "items": {
      "4.1 Оформить сейчас":         {"w":0.02, "kw_all":["оформ","сейчас"]},
      "4.2 Документы":               {"w":0.03, "kw_all":["паспорт","снилс","доход","трудов"]}
    }
  },
  "5. КРОСС-ПРОДАЖИ": {
    "weight": 0.10,
    "items": {
      "5.1 Доп. продукт":            {"w":0.10, "kw_any":["интернет","дебет","карта","страхов"]}
    }
  },
  "6. ЗАВЕРШЕНИЕ": {
    "weight": 0.15,
    "items": {
      "6.1 Остались вопросы":        {"w":0.02, "kw_any":["вопрос"]},
      "6.2 Повторная встреча":       {"w":0.03, "kw_any":["встреч"]},
      "6.3 Телефон":                 {"w":0.03, "kw_any":["телефон"]},
      "6.4 Контакты":                {"w":0.03, "kw_any":["контакт"]},
      "6.5 Рекламные материалы":     {"w":0.02, "kw_any":["буклет","материал","расчет","просчет","расчёт","просчёт"]},
      "6.6 Прощание":                {"w":0.02, "kw_any":["до свидан","ждем","ждём","рады"]}
    }
  }
}""")

STAGE7_WEIGHT = 0.10
STAGE7_TEXT = """\
1. Комфортность зала (температура, чистота, отсутствие запахов)
2. Нет посторонних шумов
3. Деловой внешний вид сотрудников
4. Платок/галстук и бейдж на сотрудниках
"""

# ------------ параметры подсказки ------------------------------
MAX_ATTEMPTS = 3   # после 3-й неудачной попытки даём подсказку

# ------------ состояние сессии --------------------------------
def build_queue() -> deque:
    q = deque()
    for s, data in CRITERIA.items():
        for c in data["items"]:
            q.append((s, c))
    q.append(("7. ДОП. ИНФОРМАЦИЯ", "stage7"))
    return q

def session_init():
    st.session_state.q        = build_queue()
    st.session_state.score    = {s: 0.0 for s in CRITERIA}
    st.session_state.accum    = {}
    st.session_state.tries    = {}
    st.session_state.stage7   = False
    st.session_state.finished = False
    st.session_state.chat     = []

if "q" not in st.session_state:
    session_init()

def add(role: str, text: str):
    st.session_state.chat.append((role, text))

# ------------ UI: вывод истории --------------------------------
st.title("Симулятор тайного покупателя ПСБ")

for r, m in st.session_state.chat:
    st.chat_message(r).write(m)

# ------------ первая реплика -----------------------------------
if not st.session_state.chat:
    add("assistant", "ТП: Клиент подошёл к окну обслуживания.")
    st.chat_message("assistant").write("ТП: Клиент подошёл к окну обслуживания.")

# ------------ обработка ответа менеджера -----------------------
def process(ans: str):
    sec, crit = st.session_state.q[0]

    # ---------- Stage-7 ----------
    if crit == "stage7":
        if normalize(ans) in ("да", "все", "всё"):
            st.session_state.stage7 = True
            st.session_state.q.popleft()
            add("assistant", "✅  Этап 7 зачтён, благодарю!")
        else:
            add("assistant", "⚠️  Для зачёта ответьте «Да» или «Все».")
        return

    cfg = CRITERIA[sec]["items"][crit]
    cid = f"{sec} >> {crit}"

    # накапливаем текст
    st.session_state.accum[cid] = st.session_state.accum.get(cid, "") + " " + ans
    st.session_state.tries[cid] = st.session_state.tries.get(cid, 0) + 1
    collected = st.session_state.accum[cid]

    # --- проверка на исполнение ---
    ok = True
    if "kw_all" in cfg:          ok &= has_all(cfg["kw_all"], collected)
    if "kw_any" in cfg:          ok &= has_any(cfg["kw_any"], collected)
    if "kw_any2" in cfg:         ok &= has_any(cfg["kw_any2"], collected)

    if ok:
        st.session_state.score[sec] += cfg.get("w", 0)
        st.session_state.q.popleft()
        add("assistant", "✅  Критерий выполнен, переходим дальше.")
        st.session_state.accum.pop(cid, None)
        st.session_state.tries.pop(cid, None)
    else:
        if st.session_state.tries[cid] >= MAX_ATTEMPTS:
            hint = " / ".join(cfg.get("kw_any", cfg.get("kw_all", [])))
            if "kw_any2" in cfg:
                hint += " + (" + " / ".join(cfg["kw_any2"]) + ")"
            add("assistant", f"💡 Подсказка: нужно упомянуть: {hint}")
        else:
            add("assistant", "⚠️  Информации недостаточно, уточните ответ.")

# ------------ вывод очередного запроса -------------------------
if st.session_state.q:
    sec, crit = st.session_state.q[0]
    prompt = (f"ТП: Доп. критерии офиса:\n{STAGE7_TEXT}\nСоответствует ли всё перечисленному?"
              if crit == "stage7"
              else f"ТП (критерий {crit} секции «{sec}»): прошу информацию.")
    st.chat_message("assistant").write(prompt)

    user = st.chat_input("Ответ менеджера…")
    if user:
        add("user", user)
        process(user)
        st.rerun()
else:
    # ---------- финальный экран ----------
    if not st.session_state.finished:
        gained = sum(st.session_state.score.values()) + (STAGE7_WEIGHT if st.session_state.stage7 else 0)
        total  = sum(s["weight"] for s in CRITERIA.values()) + STAGE7_WEIGHT
        pct    = round(gained / total * 100, 1)
        verdict = ("ОТЛИЧНО" if pct >= 90 else
                   "ХОРОШО"  if pct >= 75 else
                   "УДОВЛЕТВОРИТЕЛЬНО" if pct >= 60 else
                   "НУЖНО ДОРАБОТАТЬ")
        add("assistant", f"Итоговая оценка менеджера: {pct}%  •  Статус: {verdict}")
        st.session_state.finished = True
        st.rerun()
