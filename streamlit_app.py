#  streamlit_app.py   •  Тайный гость: Миссия "Идеальная консультация"
#  ------------------------------------------------------------------
#  v4.0 – добавлены автоматические ответы тайного покупателя
#         (сумма, срок, цель, доход, зарплатная карта, документы и т.д.)
#         логика проверки критериев не изменилась.
import streamlit as st
import re, json
from collections import deque
from typing import List, Dict, Optional

# --------- NLP (лемматизация) ---------------------------------
try:
    from pymorphy2 import MorphAnalyzer
    morph = MorphAnalyzer()
except ImportError:
    morph = None

def norm(t: str) -> str:
    t = re.sub(r"[^\w\s]", " ", t.lower())
    if not morph:
        return re.sub(r"\s+", " ", t).strip()
    return " ".join(morph.parse(w)[0].normal_form for w in t.split())

def has_all(keys: List[str], txt: str) -> bool: return all(k in txt for k in keys)
def has_any(keys: List[str], txt: str) -> bool: return any(k in txt for k in keys)

# --------- Анкета (ключи) -------------------------------------
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

MAX_ATTEMPTS = 3  # подсказка после 3 ошибок

# --------- профиль клиента ------------------------------------
CLIENT_PROFILE = {
    "name": "Михаил",
    "purpose": "ремонт квартиры",
    "amount": "500 000",
    "term": "3 года",
    "income": "70 000",
    "salary_bank": "другой банк"
}

def auto_answer(msg: str) -> Optional[str]:
    """Возвращает реплику тайного покупателя при необходимости."""
    txt = norm(msg)
    # вопросы про имя
    if "как" in txt and ("обращ" in txt or "можн" in txt):
        return f"Можно просто {CLIENT_PROFILE['name']}."
    # сумма/срок/цель
    if any(k in txt for k in ["сумм", "срок", "цель"]):
        return (f"Мне нужен кредит {CLIENT_PROFILE['amount']} ₽ "
                f"на {CLIENT_PROFILE['term']}, цель – {CLIENT_PROFILE['purpose']}.")
    # доход
    if "доход" in txt or "заработ" in txt:
        return f"Мой ежемесячный доход около {CLIENT_PROFILE['income']} ₽ после налогов."
    # зарплатный проект
    if "зарплат" in txt:
        return "Зарплату получаю в другом банке, в ПСБ пока нет."
    # документы
    if "документ" in txt or "паспорт" in txt:
        return "Паспорт, СНИЛС и справку о доходах могу предоставить, трудовую тоже."
    # комфорт платежа
    if "комфорт" in txt or "удобн" in txt or "подход" in txt:
        return "Да, такой платёж для меня комфортен."
    # остались вопросы
    if "вопрос" in txt and "остал" in txt:
        return "Нет, вопросов не осталось."
    return None

# --------- состояние ------------------------------------------
def build_queue() -> deque:
    q = deque()
    for s, d in CRITERIA.items():
        for c in d["items"]:
            q.append((s, c))
    q.append(("7. ДОП. ИНФОРМАЦИЯ", "stage7"))
    return q

def init():
    st.session_state.q        = build_queue()
    st.session_state.sec_txt  = {s: "" for s in CRITERIA}
    st.session_state.score    = {s: 0.0 for s in CRITERIA}
    st.session_state.tries    = {}
    st.session_state.stage7   = False
    st.session_state.finished = False
    st.session_state.hist     = []

if "q" not in st.session_state:
    init()

def add(role, text): st.session_state.hist.append((role, text))

# --------- проверка критерия ----------------------------------
def crit_ok(cfg, txt):
    ok = True
    if "kw_must" in cfg: ok &= has_all(cfg["kw_must"], txt)
    if "kw_all"  in cfg: ok &= has_all(cfg["kw_all"],  txt)
    if "kw_any"  in cfg: ok &= has_any(cfg["kw_any"],  txt)
    return ok

# --------- UI: история ----------------------------------------
st.title("Тайный гость: Миссия «Идеальная консультация»")
for r, m in st.session_state.hist:
    st.chat_message(r).write(m)

# первая сцена
if not st.session_state.hist:
    add("assistant", "ТП: Клиент подошёл к окну обслуживания.")
    st.chat_message("assistant").write("ТП: Клиент подошёл к окну обслуживания.")

# авто-скан выполненных критериев
while st.session_state.q:
    sec, crit = st.session_state.q[0]
    if crit == "stage7": break
    if crit_ok(CRITERIA[sec]["items"][crit], norm(st.session_state.sec_txt[sec])):
        st.session_state.score[sec] += CRITERIA[sec]["items"][crit]["w"]
        st.session_state.q.popleft()
    else:
        break

# ---------- диалог --------------------------------------------
if st.session_state.q:
    sec, crit = st.session_state.q[0]
    prompt = ("ТП: Доп. критерии офиса:\n" + STAGE7_TEXT +
              "\nСоответствует ли всё перечисленному?" if crit == "stage7"
              else f"ТП (крит. «{crit}» раздела «{sec}»): прошу информацию.")
    st.chat_message("assistant").write(prompt)

    user_msg = st.chat_input("Ответ менеджера…")
    if user_msg:
        add("user", user_msg)
        st.session_state.sec_txt[sec] += " " + user_msg  # копим текст раздела

        # автоматический ответ клиента
        reply = auto_answer(user_msg)
        if reply:
            add("assistant", reply)

        if crit == "stage7":
            if norm(user_msg) in ("да", "все", "всё"):
                st.session_state.stage7 = True
                st.session_state.q.popleft()
                add("assistant", "✅  Этап 7 зачтён, спасибо!")
        else:
            cid = f"{sec} >> {crit}"
            st.session_state.tries[cid] = st.session_state.tries.get(cid, 0) + 1
            if crit_ok(CRITERIA[sec]["items"][crit], norm(st.session_state.sec_txt[sec])):
                st.session_state.score[sec] += CRITERIA[sec]["items"][crit]["w"]
                st.session_state.q.popleft()
                add("assistant", "✅  Критерий выполнен, двигаемся дальше.")
            else:
                if st.session_state.tries[cid] >= MAX_ATTEMPTS:
                    cfg = CRITERIA[sec]["items"][crit]
                    hint = " / ".join(cfg.get("kw_must", []) +
                                      cfg.get("kw_all", []) +
                                      cfg.get("kw_any", []))
                    add("assistant", f"💡 Подсказка: нужно упомянуть: {hint}")
                else:
                    add("assistant", "⚠️  Информации недостаточно, уточните ответ.")

        st.rerun()

# ---------- финал ---------------------------------------------
if not st.session_state.q and not st.session_state.finished:
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
