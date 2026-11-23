"""Interactive claims/debts decision tree.

Local issue-spotting workflow. It reuses the central legal corpus and does not
copy statutes into the tree or assert definitive legal outcomes.
"""
from __future__ import annotations
import re
from .files import clean_fa
from .legal_packs import _corpus, _norm
from functools import partial
from .text_utils import has_any_normalized_term, find_law_source_hits


_has = partial(has_any_normalized_term, normalizer=_norm)


_source_hits = partial(find_law_source_hits, corpus_loader=_corpus, normalizer=_norm)


def build_claims_tree(text: str):
    text=clean_fa(text or "")
    if len(text.strip()) < 40:
        return {"sufficient":False,"reason":"متن پرونده برای ساخت مسیر بررسی مطالبات و دیون کافی نیست."}
    t=_norm(text)
    debt_terms=("طلب","مطالبه","مطالبه وجه","دین","بدهی","محکومیت مالی","محکوم به","طلبکار","بدهکار","اجرت","اجاره بها","خسارت","وجه التزام","استرداد وجه","قرض","چک","سفته","اجراییه","اجرای احکام","اعسار","تقسیط","پرداخت نکرد","عدم پرداخت","مانده","وجه")
    negative=_has(t,"هیچ طلبی","هیچ دینی","بدهی وجود ندارد","طلبی وجود ندارد")
    is_debt=_has(t,*debt_terms) and not negative
    if not is_debt:
        return {"sufficient":True,"is_debt":False,"title":"💰 درخت بررسی مطالبات و دیون","message":"نشانه کافی از مطالبه یا دین در متن پیدا نشد."}
    nodes=[]; questions=[]; missing=[]; flags=[]; paths=[]
    if _has(t,"چک","گواهی عدم پرداخت","صیادی"): origin="چک/سند تجاری"
    elif _has(t,"اجاره","موجر","مستأجر","اجرت المثل"): origin="اجاره/اجرت"
    elif _has(t,"قرارداد","تعهد","وجه التزام"): origin="قرارداد/تعهد"
    elif _has(t,"قرض","وام"): origin="قرض/تأمین مالی"
    elif _has(t,"خسارت","ضرر و زیان"): origin="خسارت/مسئولیت"
    else: origin="منشأ دین از متن قطعی نیست"
    nodes.append({"id":"origin","label":"۱) منشأ دین","result":origin})
    questions.append("منشأ دقیق دین چیست و سند یا رابطه حقوقی ایجادکننده آن کدام است؟")
    if origin.endswith("قطعی نیست"): missing.append("منشأ و مبنای ایجاد دین")

    if _has(t,"وجه نقد","مبلغ","ریال","تومان","تومان"): nature="وجه نقد/طلب مالی"
    elif _has(t,"تحویل","انجام تعهد","انجام کار"): nature="انجام تعهد یا تحویل"
    else: nature="ماهیت دین از متن قطعی نیست"
    nodes.append({"id":"nature","label":"۲) ماهیت دین","result":nature})
    questions.append("دین مالی است یا انجام/تحویل تعهد یا جبران خسارت؟")
    if nature.endswith("قطعی نیست"): missing.append("ماهیت دقیق خواسته")

    has_amount=bool(re.search(r"\d[\d,٬.]*\s*(?:ریال|تومان)?",text))
    nodes.append({"id":"amount","label":"۳) مبلغ و مانده بدهی","result":"مبلغ یا عدد مالی در متن دیده می‌شود؛ باید با اسناد و پرداخت‌ها تطبیق شود" if has_amount else "مبلغ/مانده روشن نیست"})
    questions.append("اصل دین، پرداخت‌های انجام‌شده و مانده واقعی چگونه محاسبه و اثبات می‌شود؟")
    if not has_amount: missing.append("مبلغ اصل دین و مانده پس از پرداخت‌ها")

    has_due=_has(t,"سررسید","موعد پرداخت","تاریخ پرداخت","مهلت پرداخت") or bool(re.search(r"\d{1,4}[/-]\d{1,2}[/-]\d{1,4}",text))
    nodes.append({"id":"due","label":"۴) سررسید و مطالبه","result":"تاریخ/موعدی در متن دیده می‌شود" if has_due else "سررسید یا تاریخ مطالبه روشن نیست"})
    questions.append("سررسید دین چه زمانی است و مطالبه قابل اثبات چه زمانی انجام شده است؟")
    if not has_due: missing.append("سررسید و تاریخ مطالبه")

    payments=[]
    if _has(t,"پرداخت","واریز","رسید بانکی","تسویه"): payments.append("پرداخت/تسویه")
    if _has(t,"پرداخت جزئی","بخشی از مبلغ"): payments.append("پرداخت جزئی")
    if _has(t,"تقسیط","قسط"): payments.append("تقسیط")
    if _has(t,"تهاتر"): payments.append("تهاتر")
    if _has(t,"ابراء","بخشیدن طلب","بخشش طلب"): payments.append("ابراء/بخشش ادعایی")
    nodes.append({"id":"settlement","label":"۵) پرداخت و تسویه","result":"موارد دیده‌شده: "+"، ".join(dict.fromkeys(payments)) if payments else "وضعیت پرداخت/تسویه روشن نیست"})
    questions.append("آیا پرداخت، تسویه، تهاتر، ابراء یا تقسیطی رخ داده است؟ اسناد آن کجاست؟")
    if not payments: missing.append("سوابق پرداخت و تسویه")

    evidence=[]
    for term,label in [("قرارداد","قرارداد"),("چک","چک"),("سفته","سفته"),("سند رسمی","سند رسمی"),("رسید","رسید"),("اقرار","اقرار"),("حکم","رأی/حکم"),("اجراییه","اجراییه")]:
        if _has(t,term): evidence.append(label)
    nodes.append({"id":"evidence","label":"۶) اسناد و ادله","result":"ادله/اسناد دیده‌شده: "+"، ".join(dict.fromkeys(evidence)) if evidence else "سند اصلی دین از متن روشن نیست"})
    questions.append("اصل سند ایجاد دین و ادله پرداخت/مطالبه در پرونده موجود است؟")
    if not evidence: missing.append("سند ایجاد دین و ادله مطالبه/عدم پرداخت")

    guarantees=[]
    for term,label in [("ضامن","ضمان/ضامن"),("رهن","رهن"),("وثیقه","وثیقه"),("چک تضمینی","چک تضمینی"),("سفته","سفته"),("ضمانت نامه","ضمانت‌نامه")]:
        if _has(t,term): guarantees.append(label)
    nodes.append({"id":"guarantee","label":"۷) تضمین‌ها","result":"تضمین‌های دیده‌شده: "+"، ".join(dict.fromkeys(guarantees)) if guarantees else "تضمین مشخصی استخراج نشد"})
    questions.append("آیا برای دین ضامن، رهن، وثیقه، چک، سفته یا ضمانت‌نامه وجود دارد؟")

    delay=[]
    if _has(t,"خسارت تأخیر","خسارت تاخیر","تأخیر تأدیه","تاخیر تادیه"): delay.append("خسارت تأخیر تأدیه مطرح شده")
    if _has(t,"وجه التزام"): delay.append("وجه التزام")
    if delay: flags.append("مبنای خسارت/وجه التزام و تاریخ شروع آن باید با نوع دین و مقررات خاص تطبیق شود")
    nodes.append({"id":"delay","label":"۸) خسارت و تأخیر تأدیه","result":"؛ ".join(delay) if delay else "ادعای مشخصی درباره خسارت تأخیر استخراج نشد"})
    questions.append("آیا خسارت تأخیر تأدیه یا وجه التزام مطالبه می‌شود و مبنای آن چیست؟")

    stage="پیش از دعوا"
    if _has(t,"دادخواست","جلسه دادگاه","در جریان رسیدگی","پرونده قضایی"): stage="در مرحله رسیدگی"
    if _has(t,"رأی قطعی","محکوم‌به","محکوم علیه","محکوم‌علیه"): stage="پس از صدور رأی/محکومیت"
    if _has(t,"اجراییه","اجرای احکام","توقیف اموال"): stage="مرحله اجرا"
    nodes.append({"id":"stage","label":"۹) مرحله پرونده","result":stage})
    questions.append("پرونده در مرحله مطالبه، رسیدگی، پس از رأی یا اجرای حکم قرار دارد؟")
    if stage=="پیش از دعوا": paths.append("بررسی مسیر مناسب مطالبه و در صورت وجود شرایط، اقدامات تأمینی")
    elif stage=="در مرحله رسیدگی": paths.append("بررسی خواسته، ادله، دفاعیات و اقدامات تأمینی در دعوای جاری")
    elif stage=="پس از صدور رأی/محکومیت": paths.append("بررسی اجراییه، وضعیت پرداخت و اقدامات پس از محکومیت")
    else: paths.append("بررسی عملیات اجرا، شناسایی/توقیف اموال و وضعیت پرداخت")

    if _has(t,"اعسار","تقسیط","ناتوانی مالی"): paths.append("بررسی شاخه اعسار/تقسیط و تاریخ‌های مرتبط")
    if _has(t,"توقیف","مال","ملک","حساب بانکی"): paths.append("بررسی اموال قابل شناسایی/توقیف و مستثنیات با توجه به وضعیت پرونده")
    if _has(t,"چک","گواهی عدم پرداخت"): paths.append("هم‌زمانی/ارتباط با درخت چک و بررسی مسیرهای خاص سند تجاری")
    if _has(t,"قرارداد","وجه التزام"): paths.append("استفاده از نتایج درخت قرارداد برای تعیین منشأ و ضمانت اجرای دین")
    if _has(t,"اجاره","اجاره بها"): paths.append("استفاده از نتایج درخت اجاره برای تعیین منشأ مطالبه")

    if _has(t,"تعارض","مغایرت","مبلغ متفاوت","نسخه متفاوت"): flags.append("اختلاف در مبلغ/نسخه/اسناد؛ محاسبه مانده بدون تطبیق اصل اسناد قابل اتکا نیست")
    if _has(t,"اظهارنامه","اخطار","مطالبه رسمی"): flags.append("تاریخ و مفاد مطالبه رسمی برای بررسی مهلت‌ها و آثار آن باید استخراج شود")
    if _has(t,"اعسار"): flags.append("شاخه اعسار نیازمند کنترل دقیق تاریخ ابلاغ اجراییه و اسناد مالی است")

    sources=_source_hits(["قانون مدنی","قانون آیین دادرسی مدنی","قانون اجرای احکام مدنی","قانون نحوه اجرای محکومیت‌های مالی","قانون صدور چک","قانون مسئولیت مدنی"],10)
    return {"sufficient":True,"is_debt":True,"title":"🌳 درخت بررسی مطالبات و دیون","nodes":nodes,"paths":list(dict.fromkeys(paths))[:12],"questions":list(dict.fromkeys(questions))[:14],"missing":list(dict.fromkeys(missing))[:12],"flags":list(dict.fromkeys(flags))[:10],"sources":sources,"warning":"این درخت برای issue-spotting و نظم‌دهی بررسی مطالبات و دیون است، نه اعلام نتیجه قطعی. مبلغ، تاریخ‌ها، اسناد و آخرین وضعیت مقررات باید با اصل مدارک و منابع رسمی کنترل شوند."}

_INTERACTIVE_NODES=[
 {"id":"origin","title":"۱) منشأ دین","question":"منشأ اصلی مطالبه یا دین چیست؟","choices":[("قرارداد/تعهد","c"),("چک/سند تجاری","k"),("قرض/وام","l"),("خسارت/مسئولیت","d"),("سایر/نامشخص","u")]},
 {"id":"status","title":"۲) وضعیت پرداخت","question":"وضعیت پرداخت یا تسویه چگونه است؟","choices":[("هیچ پرداختی نشده","n"),("پرداخت جزئی","p"),("کامل پرداخت/تسویه ادعایی","s"),("تقسیط/پرداخت قسطی","i"),("نامشخص","u")]},
 {"id":"due","title":"۳) سررسید و مطالبه","question":"وضعیت سررسید و مطالبه چگونه است؟","choices":[("سررسید گذشته و مطالبه شده","o"),("سررسید گذشته ولی مطالبه روشن نیست","m"),("سررسید نرسیده/مورد اختلاف","f"),("نامشخص","u")]},
 {"id":"stage","title":"۴) مرحله پرونده","question":"پرونده اکنون در کدام مرحله است؟","choices":[("قبل از طرح دعوا","p"),("در حال رسیدگی","l"),("رأی/محکومیت صادر شده","j"),("اجرای حکم/اجراییه","e"),("نامشخص","u")]},
 {"id":"security","title":"۵) تضمین و اقدام","question":"آیا تضمین یا اقدام اجرایی مهمی وجود دارد؟","choices":[("ضامن/رهن/وثیقه","g"),("چک/سفته/ضمانت‌نامه","s"),("توقیف/شناسایی مال","a"),("اعسار/تقسیط","i"),("خیر/نامشخص","u")]},
]

def interactive_claims_start(text):
    base=build_claims_tree(text)
    if not base.get("is_debt"): return {"status":"not_debt","base":base}
    return {"status":"active","base":base,"index":0,"answers":{},"history":[]}

def interactive_claims_step(state,choice):
    if not state or state.get("status")!="active": return {"status":"invalid"}
    idx=int(state.get("index",0))
    if idx>=len(_INTERACTIVE_NODES): return interactive_claims_finalize(state)
    node=_INTERACTIVE_NODES[idx]; valid={c for _,c in node["choices"]}
    if choice not in valid: return {"status":"invalid","state":state}
    state.setdefault("answers",{})[node["id"]]=choice; state.setdefault("history",[]).append(idx); state["index"]=idx+1
    if state["index"]>=len(_INTERACTIVE_NODES): return interactive_claims_finalize(state)
    return {"status":"question","state":state,"node":_INTERACTIVE_NODES[state["index"]]}

def interactive_claims_finalize(state):
    a=state.get("answers",{}); base=state.get("base",{}); paths=list(base.get("paths",[])); missing=list(base.get("missing",[])); flags=list(base.get("flags",[]))
    if a.get("status")=="p": paths.append("بررسی مانده اصل دین و اسناد پرداخت جزئی")
    if a.get("status")=="s": flags.append("تسویه ادعایی باید با رسید، اقرار یا سند معتبر تطبیق شود")
    if a.get("due") in {"o","m"}: paths.append("بررسی آثار سررسید و تاریخ مطالبه بر خواسته و خسارت احتمالی")
    if a.get("due")=="m": missing.append("تاریخ و دلیل قابل اثبات مطالبه")
    if a.get("stage")=="e": paths.append("بررسی عملیات اجرای حکم و وضعیت اموال/پرداخت")
    if a.get("security")=="i": paths.append("بررسی اعسار/تقسیط و تاریخ‌های مرتبط")
    if a.get("security") in {"g","s"}: flags.append("تضمین انتخاب‌شده باید از اصل سند و حدود تعهد کنترل شود")
    return {"status":"complete","answers":a,"base":base,"paths":list(dict.fromkeys(paths))[:14],"missing":list(dict.fromkeys(missing))[:12],"flags":list(dict.fromkeys(flags))[:10]}

def format_claims_question(node,step,total):
    lines=["🌳 درخت بررسی مطالبات و دیون",f"مرحله {step} از {total}","",node["title"],node["question"],"",*(["• "+x for x,_ in node["choices"]]),"","🔒 موتور: درخت تصمیم داخلی و بدون AI"]
    return "\n".join(lines)

def format_claims_result(result):
    if result.get("status")=="not_debt": return "🌳 درخت بررسی مطالبات و دیون\n\nℹ️ "+result.get("base",{}).get("message","نشانه کافی از مطالبه یا دین پیدا نشد.")
    base=result.get("base",{}); lines=["🌳 نتیجه درخت بررسی مطالبات و دیون","","🔒 موتور: داخلی و بدون AI","","🧭 یافته‌های پرونده:"]
    lines += [f"• {n['label']}: {n['result']}" for n in base.get("nodes",[])]
    if result.get("paths"): lines += ["","🛣️ مسیرهای قابل بررسی:"]+["• "+x for x in result["paths"]]
    if result.get("missing"): lines += ["","📂 اطلاعات/مدارک ناقص:"]+["• "+x for x in result["missing"]]
    if result.get("flags"): lines += ["","🚩 نقاط حساس:"]+["• "+x for x in result["flags"]]
    if base.get("sources"): lines += ["","📚 منابع داخلی قابل بررسی:"]+["• "+x["title"] for x in base["sources"]]
    lines += ["","⚠️ "+base.get("warning","")]
    return "\n".join(lines)
