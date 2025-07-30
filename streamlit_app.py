#  streamlit_app.py   •   Тайный гость: Миссия "Идеальная консультация"
#  -------------------------------------------------------------------
#  v3.0:  • гибкие ключи (kw_must / kw_any / kw_all)
#         • пропуск уже выполненных подпунктов, если менеджер дал их ранее
#         • подсказка после 3 попыток
#         • лемматизация pymorphy2 + st.rerun()

import streamlit as st
import re, json
from collections import deque
from typing import List, Dict

# ---------- NLP (лемматизация) ---------------------------------
try:
    from pymorphy2 import MorphAnalyzer
    morph = MorphAnalyzer()
except ImportError:
    morph = None                    # работает и без pymorphy2

def normalize(txt: str) -> str:
    txt = re.sub(r"[^\w\s]", " ", txt.lower())
    if not morph:
        return re.sub(r"\s+", " ", txt).strip()
    return " ".join(morph.parse(w)[0].normal_form for w in txt.split())

def has_all(keys: List[str], text: str) -> bool:
    return all(k in text for k in keys)

def has_any(keys: List[str], text: str) -> bool:
    return any(k in text for k in keys)

# ---------- Анкета ---------------------------------------------
CRITERIA: Dict[str, Dict] = json.loads("""{
  "1. ОБСЛУЖИВАНИЕ": {
    "weight": 0.21,
    "items": {
      "1.1 Приветствие первым":  {"w":0.02, "kw_any":["здрав","добр","приветств"]},
      "1.2 Представился":        {"w":0.02, "kw_must":["меня"], "kw_any":["зов","зовут","имя"]},
      "1.3 Как обращаться":      {"w":0.03, "kw_must":["как"], "kw_any":["обращ","можн"]},
      "1.5 Вежливость":          {"w":0.05},
      "1.6 Не перебивал":        {"w":0.01},
      "1.7 Конфиденциальность":  {"w":0.04},
      "1.8 Деловой стиль речи":  {"w":0.04}
    }
  },

  "2. ВЫЯВЛЕНИЕ ПОТРЕБНОСТЕЙ": {
    "weight": 0.18,
    "items": {
      "2.1 Цель визита":         {"w":0.02, "kw_any":["цель"]},
      "2.2 ЗП-карта ПСБ":        {"w":0.04, "kw_must":["зарплат"], "kw_any":["псб","наш","банк"]},
      "2.3 Сумма/срок/цель":     {"w":0.06, "kw_all":["сумм","срок","цель"]},
      "2.4 Доход":               {"w":0.03, "kw_any":["доход","заработ"]},
      "2.5 Предупредил о вопросах":{"w":0.03, "kw_any":["задам","нескольк","ряд","вопрос"]}
    }
  },

  "3. ПРЕЗЕНТАЦИЯ": {
    "weight": 0.20,
    "items": {
      "3.1 8 требований":        {"w":0.08, "kw_all":[
        "гражданств","возраст","регистрац","прожив",
        "работ","общий","стаж","телефон"]},
      "3.2 Расчёт платежа":      {"w":0.04, "kw_any":["платеж","платёж","ежемесяч"]},
      "3.3 Комфорт платежа":     {"w":0.04, "kw_any":["комфорт","удобн","подход"]},
      "3.4 Акция «Лучше 0»":     {"w":0.04, "kw_must":["лучш"], "kw_any":["0","нол","акц"]}
    }
  },

  "4. СОЗДАНИЕ ЗАЯВКИ": {
    "weight": 0.05,
    "items": {
      "4.1 Оформить сейчас":     {"w":0.02, "kw_any":["оформ","сейчас","давай","предлаг"]},
      "4.2 Документы":           {"w":0.03, "kw_all":["паспорт","снилс","доход","трудов"]}
    }
  },

  "5. КРОСС-ПРОДАЖИ": {
    "weight": 0.10,
    "items": {
      "5.1 Доп. продукт":        {"w":0.10, "kw_any":["интернет банк","дебет","карта","страхов"]}
    }
  },

  "6. ЗАВЕРШЕНИЕ": {
    "weight": 0.15,
    "items": {
      "6.1 Остались вопросы":    {"w":0.02, "kw_any":["вопрос"]},
      "6.2 Повторная встреча":   {"w":0.03, "kw_any":["встреч","пригл","позвон","предлаг"]},
      "6.3 Телефон":             {"w":0.03, "kw_any":["телефон","номер","остав"]},
      "6.4 Контакты":            {"w":0.03, "kw_any":["контакт","телеф","номер"]},
      "6.5 Реклама/материалы":   {"w":0.02, "kw_any":["буклет","материал","расчет","расчёт","просчет","просчёт"]},
      "6.6 Прощание":            {"w":0.02, "kw_any":["до свидан","ждем","ждём","рады","добр"]}
    }
  }
}""")

STAGE7_WEIGHT = 0.10
STAGE7_TEXT = ("1. Комфортность зала\n"
               "2. Нет посторонних шумов\n"
               "3. Деловой вид сотрудников\n"
               "4. Платок/галстук и бейдж")

MAX_ATTEMPTS = 3      # после 3-й ошибки показываем подсказку

# ---------- состояние сессии ----------------------------------
def build_queue() -> deque:
    q = deque()
    for s, data in CRITERIA.items():
        for c in data["items"]:
            q.append((s, c))
    q.append(("7. ДОП. ИНФОРМАЦИЯ", "stage7"))
    return q

def init_state():
    st.session_state.q          = build_queue()
    st.session_state.section_txt= {s: "" for s in CRITERIA}
    st.session_state.score      = {s: 0.0 for s in CRITERIA}
    st.session_state.tries      = {}
    st.session_state.stage7     = False
    st.session_state.finished   = False
    st.session_state.chat       = []

if "q" not in st.session_state:
    init_state()

def add(role, msg): st.session_state.chat.append((role, msg))

# ---------- вспомогательная проверка --------------------------
def criterion_ok(cfg, text_norm):
    ok = True
    if "kw_must" in cfg: ok &= has_all(cfg["kw_must"], text_norm)
    if "kw_all"  in cfg: ok &= has_all(cfg["kw_all"],  text_norm)
    if "kw_any"  in cfg: ok &= has_any(cfg["kw_any"],  text_norm)
    return ok

# ---------- UI: история ---------------------------------------
st.title("Тайный гость: Миссия «Идеальная консультация»")
for r, m in st.session_state.chat:
    st.chat_message(r).write(m)

# ---------- мизансцена ----------------------------------------
if not st.session_state.chat:
    add("assistant", "ТП: Клиент подошёл к окну обслуживания.")
    st.chat_message("assistant").write("ТП: Клиент подошёл к окну обслуживания.")

# ---------- авто-проскок ранее выполненных критериев ----------
while st.session_state.q:
    sec, crit = st.session_state.q[0]
    if crit == "stage7": break
    cfg = CRITERIA[sec]["items"][crit]
    text_norm = normalize(st.session_state.section_txt[sec])
    if criterion_ok(cfg, text_norm):
        st.session_state.score[sec] += cfg.get("w", 0)
        st.session_state.q.popleft()
    else:
        break   # первый невыполненный подпункт найден

# ---------- вывод вопроса / обработка ответа ------------------
if st.session_state.q:
    sec, crit = st.session_state.q[0]

    # ---- stage-7 ----------
    if crit == "stage7":
        prompt = ("ТП: Дополнительные критерии офиса:\n"
                  f"{STAGE7_TEXT}\n"
                  "Соответствует ли всё перечисленному?")
    else:
        prompt = f"ТП (критерий «{crit}» раздела «{sec}»): прошу информацию."

    st.chat_message("assistant").write(prompt)
    reply = st.chat_input("Ответ менеджера…")

    if reply:
        add("user", reply)

        # копим текст раздела
        if sec in st.session_state.section_txt:
            st.session_state.section_txt[sec] += " " + reply

        if crit == "stage7":
            if normalize(reply) in ("да", "все", "всё"):
                st.session_state.stage7 = True
                st.session_state.q.popleft()
                add("assistant", "✅  Этап 7 зачтён, спасибо!")
            else:
                add("assistant", "⚠️  Для зачёта ответьте «Да» или «Все».")
        else:
            cid = f"{sec} >> {crit}"
            st.session_state.tries[cid] = st.session_state.tries.get(cid, 0) + 1
            text_norm = normalize(st.session_state.section_txt[sec])

            if criterion_ok(cfg, text_norm):
                st.session_state.score[sec] += cfg["w"]
                st.session_state.q.popleft()
                add("assistant", "✅  Критерий выполнен, двигаемся далее.")
            else:
                if st.session_state.tries[cid] >= MAX_ATTEMPTS:
                    must  = cfg.get("kw_must", [])
                    all_  = cfg.get("kw_all", [])
                    any_  = cfg.get("kw_any", [])
                    hint = " / ".join(must + all_ + any_)
                    add("assistant", f"💡 Подсказка: нужно упомянуть: {hint}")
                else:
                    add("assistant", "⚠️  Информации недостаточно, уточните ответ.")

        st.rerun()

# ---------- итог ----------------------------------------------
if not st.session_state.q and not st.session_state.finished:
    gained = sum(st.session_state.score.values()) + (STAGE7_WEIGHT if st.session_state.stage7 else 0)
    total  = sum(sec["weight"] for sec in CRITERIA.values()) + STAGE7_WEIGHT
    pct    = round(gained / total * 100, 1)
    verdict = ("ОТЛИЧНО" if pct >= 90 else
               "ХОРОШО"  if pct >= 75 else
               "УДОВЛЕТВОРИТЕЛЬНО" if pct >= 60 else
               "НУЖНО ДОРАБОТАТЬ")
    add("assistant", f"Итоговая оценка менеджера: {pct}%  •  Статус: {verdict}")
    st.session_state.finished = True
    st.rerun()
