#  streamlit_app.py  •  Mystery Shopper PSB  (web GUI, v2.1)
#  ---------------------------------------------------------------
#  – мизансцена и требование приветствия первым
#  – накопление ответов менеджера
#  – подсказка после 5 попыток
#  – лемматизация (pymorphy2)
#  – st.rerun() вместо experimental_rerun
#  – правки: 2.5, перенос "обращение по имени" в 3.5 и 6.7,
#            расширение 6.5 ключами "расчёт / просчёт"
#  ---------------------------------------------------------------
import streamlit as st
import re, json
from collections import deque
from typing import List, Dict

# ---------- NLP (лемматизация) ---------------------------------
try:
    from pymorphy2 import MorphAnalyzer
    morph = MorphAnalyzer()
except ImportError:
    morph = None

def normalize(txt: str) -> str:
    txt = re.sub(r"[^\w\s]", " ", txt.lower())
    if not morph:
        return re.sub(r"\s+", " ", txt).strip()
    return " ".join(morph.parse(w)[0].normal_form for w in txt.split())

def has_all(keys: List[str], text: str) -> bool:
    t = normalize(text)
    return all(k in t for k in keys)

def has_any(keys: List[str], text: str) -> bool:
    t = normalize(text)
    return any(k in t for k in keys)

# ---------- Анкета ---------------------------------------------
CLIENT_NAME = "михаил"

CRITERIA: Dict[str, Dict] = json.loads("""{
  "1. ОБСЛУЖИВАНИЕ": {
    "weight": 0.21,
    "items": {
      "1.1 Приветствие первым":              {"w":0.02, "kw":["здравствовать","добрый"]},
      "1.2 Представился":                    {"w":0.02, "kw":["меня","звать"]},
      "1.3 Уточнил, как обращаться":         {"w":0.03, "kw":["как","обращаться"]},
      "1.5 Вежливость":                      {"w":0.05, "kw":[]},
      "1.6 Не перебивал":                    {"w":0.01, "kw":[]},
      "1.7 Конфиденциальность":              {"w":0.04, "kw":[]},
      "1.8 Деловой стиль речи":              {"w":0.04, "kw":[]}
    }
  },
  "2. ВЫЯВЛЕНИЕ ПОТРЕБНОСТЕЙ": {
    "weight": 0.18,
    "items": {
      "2.1 Цель визита":                     {"w":0.02, "kw":["цель"]},
      "2.2 ЗП-карта ПСБ":                    {"w":0.04, "kw":["зарплат","псб"]},
      "2.3 Сумма-срок-цель кредита":         {"w":0.06, "kw":["сумм","срок","цель"]},
      "2.4 Уровень дохода":                  {"w":0.03, "kw":["доход"]},
      "2.5 Уточнил, что задаст вопросы":     {"w":0.03, "kw_any":["задам","несколько","ряд","вопрос"]}
    }
  },
  "3. ПРЕЗЕНТАЦИЯ ПРОДУКТА": {
    "weight": 0.24,
    "items": {
      "3.1 8 требований к заёмщику":         {"w":0.08, "kw":[
          "гражданство","возраст","регистрация","проживание",
          "работа","общий","стаж","телефон"]},
      "3.2 Расчёт платежа":                  {"w":0.04, "kw":["платеж","ежемесячный"]},
      "3.3 Комфортность платежа":            {"w":0.04, "kw":["комфорт","удобно","подходит"]},
      "3.4 Акция «лучше 0»":                 {"w":0.04, "kw":["лучше","0","ноль","акция"]},
      "3.5 Обратился по имени":              {"w":0.04, "kw_name": true}
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
    "weight": 0.17,
    "items": {
      "6.1 Остались вопросы":                {"w":0.02, "kw":["вопрос"]},
      "6.2 Повторная встреча":               {"w":0.03, "kw":["встреч"]},
      "6.3 Телефон":                         {"w":0.03, "kw":["телефон"]},
      "6.4 Контакты":                        {"w":0.03, "kw":["контакт"]},
      "6.5 Рекламные материалы":             {"w":0.02, "kw_any":["буклет","материал","расчёт","расчет","просчёт","просчет"]},
      "6.6 Прощание+приглашение":            {"w":0.02, "kw_any":["до свидан","ждём","ждем","рады"]},
      "6.7 Обратился по имени":              {"w":0.02, "kw_name": true}
    }
  }
}""")

STAGE7_WEIGHT = 0.10
STAGE7_TEXT = """\
1. Я обратил внимание на: комфортность зала (температура, чистота, отсутствие запахов)
2. В клиентской зоне отсутствуют посторонние шумы
3. Сотрудники одеты в деловом стиле и выглядят опрятно
4. Наличие корпоративных атрибутов: платок/галстук и именной бейдж
"""

# ---------- служебные структуры --------------------------------
def build_queue() -> deque:
    q = deque()
    for s, data in CRITERIA.items():
        for c in data["items"]:
            q.append((s, c))
    q.append(("7. ДОПОЛНИТЕЛЬНАЯ ИНФОРМАЦИЯ", "stage7"))
    return q

def init():
    st.session_state.queue       = build_queue()
    st.session_state.scores      = {s: 0.0 for s in CRITERIA}
    st.session_state.accum       = {}   # criterion id ➜ collected text
    st.session_state.attempts    = {}
    st.session_state.stage7_done = False
    st.session_state.finished    = False
    st.session_state.hist        = []

if "queue" not in st.session_state:
    init()

def crit_id(sec, crit): return f"{sec} >> {crit}"

def add(role, txt): st.session_state.hist.append((role, txt))

# ---------- UI: история ---------------------------------------
st.title("Симулятор тайного покупателя ПСБ")

for r, t in st.session_state.hist:
    st.chat_message(r).write(t)

# ---------- первая мизансцена ---------------------------------
if not st.session_state.hist:
    scene = "ТП: Клиент подошёл к окну обслуживания."
    add("assistant", scene)
    st.chat_message("assistant").write(scene)

# ---------- проверка ответа -----------------------------------
def process(ans: str):
    sec, crit = st.session_state.queue[0]
    cid = crit_id(sec, crit)

    # Этап 7
    if crit == "stage7":
        if normalize(ans) in ("да", "все", "всё"):
            st.session_state.stage7_done = True
            st.session_state.queue.popleft()
            add("assistant", "✅  Этап 7 зачтён. Спасибо!")
        else:
            add("assistant", "⚠️  Для зачёта ответьте «Да» или «Все».")
        return

    cfg = CRITERIA[sec]["items"][crit]
    st.session_state.accum[cid] = st.session_state.accum.get(cid, "") + " " + ans
    st.session_state.attempts[cid] = st.session_state.attempts.get(cid, 0) + 1
    text = st.session_state.accum[cid]

    # --- проверка ---
    if cfg.get("kw_name"):
        ok = CLIENT_NAME in normalize(text)
    elif "kw_any" in cfg:
        ok = has_any(cfg["kw_any"], text)
    else:
        ok = has_all(cfg["kw"], text)

    if ok:
        st.session_state.scores[sec] += cfg["w"]
        st.session_state.queue.popleft()
        add("assistant", "✅  Критерий выполнен, двигаемся дальше.")
        st.session_state.accum.pop(cid, None)
        st.session_state.attempts.pop(cid, None)
    else:
        if st.session_state.attempts[cid] >= 5:
            keys = cfg.get("kw_any", cfg.get("kw", ["имя клиента"]))
            hint = " / ".join(keys)
            add("assistant", f"💡 Подсказка: нужно упомянуть: {hint}")
        else:
            add("assistant", "⚠️  Информации пока недостаточно, уточните ответ.")

# ---------- следующая реплика ТП -------------------------------
if st.session_state.queue:
    sec, crit = st.session_state.queue[0]
    prompt = (f"ТП: Дополнительные критерии офиса:\n{STAGE7_TEXT}\nСоответствует ли всё перечисленному?"
              if crit == "stage7"
              else f"ТП (критерий {crit} секции «{sec}»): прошу информацию.")
    st.chat_message("assistant").write(prompt)

    user_ans = st.chat_input("Ответ менеджера…")
    if user_ans:
        add("user", user_ans)
        process(user_ans)
        st.rerun()

# ---------- финал ---------------------------------------------
else:
    if not st.session_state.finished:
        got   = sum(st.session_state.scores.values()) + (STAGE7_WEIGHT if st.session_state.stage7_done else 0)
        total = sum(s["weight"] for s in CRITERIA.values()) + STAGE7_WEIGHT
        pct   = round(got / total * 100, 1)
        verdict = ("ОТЛИЧНО" if pct >= 90 else
                   "ХОРОШО" if pct >= 75 else
                   "УДОВЛЕТВОРИТЕЛЬНО" if pct >= 60 else
                   "НУЖНО ДОРАБОТАТЬ")
        add("assistant", f"Итоговая оценка менеджера: {pct}%  •  Статус: {verdict}")
        st.session_state.finished = True
        st.rerun()
