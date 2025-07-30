#  Тайный гость: Миссия "Идеальная консультация"
#  -------------------------------------------------------------
#  v5.0  (июль-2025)
#  – вопрос о платеже перед разделом 3
#  – 4 доп. критерия после раздела 6 (Да/Нет + баллы)
#  – проверка упоминания имени «Михаил» ≥ 1 раза
#  – менеджер может отвечать частями либо сразу
#  – лемматизация (pymorphy2) + Streamlit chat
#  -------------------------------------------------------------
import streamlit as st, re, json
from collections import deque
from typing import List, Dict

try:
    from pymorphy2 import MorphAnalyzer
    morph = MorphAnalyzer()
except ImportError:
    morph = None                      # падать не будем – лемматизация off

def norm(t:str)->str:
    t = re.sub(r"[^\w\s]"," ",t.lower())
    if not morph: return re.sub(r"\s+"," ",t).strip()
    return " ".join(morph.parse(w)[0].normal_form for w in t.split())

def has_all(keys:List[str],txt:str)->bool: return all(k in txt for k in keys)
def has_any(keys:List[str],txt:str)->bool: return any(k in txt for k in keys)

# ------------ анкета 1-6 --------------------------------------
CRITERIA:Dict[str,Dict]=json.loads("""{
"1. ОБСЛУЖИВАНИЕ":{"weight":0.21,"items":{
 "1.1 Приветствие":{"w":0.02,"kw_any":["здрав","добр","приветств"]},
 "1.2 Представился":{"w":0.02,"kw_must":["меня"],"kw_any":["зов","зовут","имя"]},
 "1.3 Как обращаться":{"w":0.03,"kw_must":["как"],"kw_any":["обращ","можн"]},
 "1.5 Вежливость":{"w":0.05},"1.6 Не перебивал":{"w":0.01},
 "1.7 Конфиденциальность":{"w":0.04},"1.8 Деловой стиль":{"w":0.04}}},
"2. ВЫЯВЛЕНИЕ ПОТРЕБНОСТЕЙ":{"weight":0.18,"items":{
 "2.1 Цель визита":{"w":0.02,"kw_any":["цель"]},
 "2.2 ЗП-карта ПСБ":{"w":0.04,"kw_must":["зарплат"],"kw_any":["псб","наш","банк"]},
 "2.3 Сумма/срок/цель":{"w":0.06,"kw_all":["сумм","срок","цель"]},
 "2.4 Доход":{"w":0.03,"kw_any":["доход","заработ"]},
 "2.5 Предупредил о вопросах":{"w":0.03,"kw_any":["задам","нескольк","ряд","вопрос"]}}},
"3. ПРЕЗЕНТАЦИЯ":{"weight":0.20,"items":{
 "3.1 8 требований":{"w":0.08,"kw_all":["гражданств","возраст","регистрац",
  "прожив","работ","общий","стаж","телефон"]},
 "3.2 Расчёт платежа":{"w":0.04,"kw_any":["платеж","платёж","ежемесяч"]},
 "3.3 Комфорт платежа":{"w":0.04,"kw_any":["комфорт","удобн","подход"]},
 "3.4 Акция «Лучше 0»":{"w":0.04,"kw_must":["лучш"],"kw_any":["0","нол","акц"]}}},
"4. СОЗДАНИЕ ЗАЯВКИ":{"weight":0.05,"items":{
 "4.1 Оформить сейчас":{"w":0.02,"kw_any":["оформ","сейчас","давай","предлаг"]},
 "4.2 Документы":{"w":0.03,"kw_all":["паспорт","снилс","доход","трудов"]}}},
"5. КРОСС-ПРОДАЖИ":{"weight":0.10,"items":{
 "5.1 Доп. продукт":{"w":0.10,"kw_any":["интернет банк","дебет","карта","страхов"]}}},
"6. ЗАВЕРШЕНИЕ":{"weight":0.15,"items":{
 "6.1 Остались вопросы":{"w":0.02,"kw_any":["вопрос"]},
 "6.2 Повторная встреча":{"w":0.03,"kw_any":["встреч","пригл","позвон","предлаг"]},
 "6.3 Телефон":{"w":0.03,"kw_any":["телефон","номер","остав"]},
 "6.4 Контакты":{"w":0.03,"kw_any":["контакт","телеф","номер"]},
 "6.5 Материалы":{"w":0.02,"kw_any":["буклет","материал","расчет","расчёт","просчет","просчёт"]},
 "6.6 Прощание":{"w":0.02,"kw_any":["до свидан","ждем","ждём","рады","добр"]}}}
}""")

# ------------ 4 доп. критерия офиса (после раздела-6) ----------
EXTRA = {
 "7.1 Комфорт зала":        "Комфортность помещения (температура, чистота, нет запахов)",
 "7.2 Тишина":              "Отсутствие посторонних шумов",
 "7.3 Внешний вид":         "Деловой внешний вид сотрудников",
 "7.4 Атрибуты":            "Наличие платка/галстука и бейджа"
}
EXTRA_WEIGHT = 0.10        # 0.025 за каждый

MAX_ATTEMPTS = 3

# --------- профиль клиента ------------------------------------
PROFILE = {"name":"Михаил","purpose":"ремонт квартиры",
           "amount":"500 000","term":"3 года","income":"70 000"}

def auto_reply(q:str)->str|None:
    qn = norm(q)
    if "как" in qn and ("обращ" in qn or "можн" in qn):
        return f"Можно просто {PROFILE['name']}."
    if any(k in qn for k in ["сумм","срок","цель"]):
        return f"{PROFILE['amount']} ₽ на {PROFILE['term']}, цель – {PROFILE['purpose']}."
    if "доход" in qn or "заработ" in qn:
        return f"Около {PROFILE['income']} ₽ в месяц."
    if "зарплат" in qn:
        return "Зарплату получаю в другом банке."
    if "комфорт" in qn or "удобн" in qn or "подход" in qn:
        return "Да, платёж для меня комфортен."
    if "документ" in qn or "паспорт" in qn:
        return "Паспорт, СНИЛС и справку о доходах предоставлю."
    if "вопрос" in qn and "остал" in qn:
        return "Нет, больше вопросов нет."
    return None

# --------- состояние сессии -----------------------------------
def init():
    if "queue" in st.session_state: return
    q = deque()
    for s,d in CRITERIA.items():           # блоки 1-6
        for c in d["items"]: q.append((s,c))
    q.append(("PAYMENT_QUESTION","pay"))   # вопрос о платеже
    for c in EXTRA: q.append(("7. ДОП.","extra:"+c))
    st.session_state.queue = q
    st.session_state.sec_text = {s:"" for s in CRITERIA}
    st.session_state.score = {s:0.0 for s in CRITERIA}|{"7. ДОП.":0.0}
    st.session_state.tries = {}
    st.session_state.chat=[]
    st.session_state.extra_index=0
    st.session_state.finished=False
    st.session_state.name_used=False

init()

def add(role,msg): st.session_state.chat.append((role,msg))

# --------- проверка критерия ----------------------------------
def ok(cfg,txt):
    return  (("kw_must" not in cfg or has_all(cfg["kw_must"],txt))
         and ("kw_all"  not in cfg or has_all(cfg["kw_all"], txt))
         and ("kw_any"  not in cfg or has_any(cfg["kw_any"], txt)))

# --------- вывод истории --------------------------------------
st.title("Тайный гость: Миссия «Идеальная консультация»")
for r,m in st.session_state.chat: st.chat_message(r).write(m)
if not st.session_state.chat:
    add("assistant","ТП: Клиент подошёл к окну обслуживания.")
    st.chat_message("assistant").write(st.session_state.chat[-1][1])

# --------- авто-скан блоков 1-6 --------------------------------
while st.session_state.queue and st.session_state.queue[0][0] in CRITERIA:
    sec,crit=st.session_state.queue[0]
    if ok(CRITERIA[sec]["items"][crit], norm(st.session_state.sec_text[sec])):
        st.session_state.score[sec]+=CRITERIA[sec]["items"][crit]["w"]
        st.session_state.queue.popleft()
    else: break

# --------- формирование текущего запроса ----------------------
if st.session_state.queue:
    sec, crit = st.session_state.queue[0]

    # ----- вопрос о платеже перед разделом-3 -------
    if sec=="PAYMENT_QUESTION":
        prompt = "ТП: Скажите, пожалуйста, сколько я буду платить ежемесячно?"
    elif sec=="7. ДОП.":
        key=list(EXTRA.keys())[st.session_state.extra_index]
        prompt=f"ТП: {EXTRA[key]}. Всё соответствует моим требованиям? Ответьте «Да» или «Нет»."
    else:
        prompt=f"ТП (крит. «{crit}» раздела «{sec}»): прошу информацию."
    st.chat_message("assistant").write(prompt)

    user=st.chat_input("Ответ менеджера…")
    if user:
        add("user",user)
        st.session_state.name_used |= ("михаил" in norm(user))
        if sec in CRITERIA:
            st.session_state.sec_text[sec]+= " "+user

        # авто-ответ
        ar=auto_reply(user)
        if ar: add("assistant",ar)

        # ---- обработка PAY_QUESTION (0 вес) -----------
        if sec=="PAYMENT_QUESTION":
            if has_any(["платеж","платёж","ежемесяч"], norm(user)):
                st.session_state.queue.popleft()                  # переходим к 3-му разделу
            else:
                add("assistant","⚠️  Нужен сам размер ежемесячного платежа.")
            st.rerun()

        # ---- обработка EXTRA --------------------------
        elif sec=="7. ДОП.":
            if norm(user) in ("да","все","всё"):
                st.session_state.score["7. ДОП."] += EXTRA_WEIGHT/4
            st.session_state.queue.popleft()
            st.session_state.extra_index+=1
            st.rerun()

        # ---- обработка обычного критерия --------------
        else:
            cid=f"{sec}_{crit}"
            st.session_state.tries[cid]=st.session_state.tries.get(cid,0)+1
            if ok(CRITERIA[sec]["items"][crit], norm(st.session_state.sec_text[sec])):
                st.session_state.score[sec]+=CRITERIA[sec]["items"][crit]["w"]
                st.session_state.queue.popleft()
                add("assistant","✅  Критерий выполнен, идём дальше.")
            else:
                if st.session_state.tries[cid]>=MAX_ATTEMPTS:
                    cfg=CRITERIA[sec]["items"][crit]
                    hint=" / ".join(cfg.get("kw_must",[])+cfg.get("kw_all",[])+cfg.get("kw_any",[]))
                    add("assistant",f"💡 Подсказка: нужно упомянуть: {hint}")
                else:
                    add("assistant","⚠️  Информации недостаточно, уточните.")
            st.rerun()

# --------- финал ----------------------------------------------
if not st.session_state.finished and not st.session_state.queue:
    total_weight = sum(CRITERIA[s]["weight"] for s in CRITERIA)+EXTRA_WEIGHT
    gained = sum(st.session_state.score.values())
    # проверка имени
    if not st.session_state.name_used:
        note="Имя клиента ни разу не использовано – автоматически снижена оценка."
        gained=max(gained-0.05,0)   # –5 %
    else:
        note=""
    pct=round(gained/total_weight*100,1)
    verdict=("ОТЛИЧНО" if pct>=90 else "ХОРОШО" if pct>=75
             else "УДОВЛЕТВОРИТЕЛЬНО" if pct>=60 else "НУЖНО ДОРАБОТАТЬ")
    add("assistant",f"Итоговая оценка: {pct}%  •  Статус: {verdict}")
    if note: add("assistant",f"⚠️  {note}")
    st.session_state.finished=True
    st.rerun()
