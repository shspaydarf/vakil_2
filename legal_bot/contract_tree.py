"""Interactive contract/obligations decision tree.

Local, issue-spotting workflow. It uses the central legal corpus instead of
copying law text into the tree and never states a definitive legal outcome.
"""
from __future__ import annotations
import re
from .files import clean_fa
from .legal_packs import _corpus, _norm
from functools import partial
from .text_utils import has_any_normalized_term, find_law_source_hits


_has = partial(has_any_normalized_term, normalizer=_norm)


_source_hits = partial(find_law_source_hits, corpus_loader=_corpus, normalizer=_norm)


def build_contract_tree(text: str):
    text=clean_fa(text or "")
    if len(text.strip()) < 40:
        return {"sufficient":False,"reason":"متن پرونده برای ساخت مسیر بررسی قرارداد و تعهدات کافی نیست."}
    t=_norm(text)
    negative=_has(t,"هیچ قرارداد","بدون قرارداد","فاقد قرارداد","قراردادی وجود ندارد")
    is_contract=_has(t,"قرارداد","عقد","متعهد","متعهدله","تعهد","فسخ","خسارت قراردادی","وجه التزام","عدم انجام تعهد","نقض قرارداد","الزام به انجام") and not negative
    if not is_contract:
        return {"sufficient":True,"is_contract":False,"title":"📑 درخت بررسی قرارداد و تعهدات","message":"نشانه کافی از رابطه قراردادی یا تعهدی پیدا نشد."}
    nodes=[]; questions=[]; missing=[]; flags=[]; branches=[]
    has_date=bool(re.search(r"\d{1,4}[/-]\d{1,2}[/-]\d{1,4}",text)) or _has(t,"تاریخ قرارداد","تاریخ انعقاد","منعقد شد")
    nodes.append({"id":"date","label":"۱) تاریخ و نسخه قرارداد","result":"نشانه تاریخ قرارداد دیده می‌شود" if has_date else "تاریخ قرارداد روشن نیست"})
    questions.append("تاریخ انعقاد، تمدید، الحاقیه‌ها و آخرین نسخه معتبر قرارداد کدام است؟")
    if not has_date: missing.append("تاریخ انعقاد/تمدید و آخرین نسخه قرارداد")

    if _has(t,"بیع","فروش","خرید"): kind="بیع/فروش"
    elif _has(t,"پیمانکاری","مقاوله","پروژه"): kind="پیمانکاری/اجرای کار"
    elif _has(t,"وکالت"): kind="وکالت"
    elif _has(t,"قرض","وام"): kind="قرض/تأمین مالی"
    elif _has(t,"اجاره","موجر","مستاجر","مستأجر"): kind="اجاره (با درخت تخصصی اجاره نیز قابل بررسی)"
    elif _has(t,"ضمان","ضامن"): kind="ضمان"
    else: kind="نوع قرارداد از متن قطعی نیست"
    nodes.append({"id":"kind","label":"۲) نوع قرارداد","result":kind})
    questions.append("نوع دقیق قرارداد و عنوان/ماهیت حقوقی آن چیست و آیا قراردادهای مرتبط هم وجود دارد؟")
    if kind.endswith("نیست"): missing.append("نوع و ماهیت دقیق قرارداد")

    validity=[]
    if _has(t,"اهلیت","صغیر","مجنون","وکالتنامه"): validity.append("اهلیت/نمایندگی")
    if _has(t,"امضا","مهر","اثر انگشت"): validity.append("امضا/انتساب سند")
    if _has(t,"رضایت","اکراه","اجبار","اشتباه"): validity.append("رضایت/اشتباه/اکراه")
    if _has(t,"موضوع قرارداد","مورد معامله","موضوع تعهد","مبلغ"): validity.append("موضوع و عوض/مبلغ")
    if not validity: missing.append("اصل قرارداد و بررسی امضا، اختیار، موضوع و عوض")
    nodes.append({"id":"validity","label":"۳) تشکیل و اعتبار اولیه","result":"موارد قابل بررسی: "+"، ".join(validity) if validity else "اطلاعات کافی برای کنترل اعتبار اولیه نیست"})
    questions.append("اصل قرارداد، اختیار امضاکنندگان، موضوع تعهد و شرایط اصلی آن چگونه اثبات می‌شود؟")

    breach=[]
    if _has(t,"انجام نداد","عدم انجام","انجام نشده","نقض تعهد","تخلف از تعهد"): breach.append("عدم انجام/نقض تعهد")
    if _has(t,"تاخیر","تأخیر","دیرکرد"): breach.append("تأخیر در اجرا")
    if _has(t,"معیوب","نقص","کیفیت نامناسب","عدم انطباق"): breach.append("اجرای ناقص/معیوب")
    if breach: branches.extend(["بررسی مبنای قراردادی و قانونی مسئولیت ناشی از "+x for x in breach])
    else: missing.append("شرح دقیق تعهد انجام‌نشده، موعد و نحوه تخلف")
    nodes.append({"id":"breach","label":"۴) اجرای تعهد و تخلف","result":"موضوعات دیده‌شده: "+"، ".join(dict.fromkeys(breach)) if breach else "تخلف قراردادی از متن قطعی نیست"})
    questions.append("تعهد دقیق چه بوده، موعد آن چه زمانی بوده و تخلف دقیقاً چگونه رخ داده است؟")

    remedies=[]
    if _has(t,"الزام به انجام","الزام به ایفای تعهد","انجام تعهد"): remedies.append("الزام به انجام تعهد")
    if _has(t,"فسخ","حق فسخ"): remedies.append("فسخ")
    if _has(t,"انفساخ"): remedies.append("انفساخ")
    if _has(t,"خسارت","وجه التزام","ضرر و زیان"): remedies.append("خسارت/وجه التزام")
    if _has(t,"ابطال","بطلان"): remedies.append("بررسی بطلان/ابطال")
    nodes.append({"id":"remedies","label":"۵) ضمانت اجرا و خواسته","result":"موارد مطرح‌شده: "+"، ".join(dict.fromkeys(remedies)) if remedies else "خواسته/ضمانت اجرای مورد نظر روشن نیست"})
    questions.append("خواسته دقیق چیست: اجرای تعهد، فسخ/انفساخ، خسارت، وجه التزام، ابطال/بطلان یا ترکیبی از آن‌ها؟")
    if not remedies: missing.append("خواسته و ضمانت اجرای مورد نظر")

    clauses=[]
    for term,label in [("وجه التزام","وجه التزام"),("شرط داوری","داوری"),("شرط فسخ","شرط فسخ"),("شرط تعلیقی","شرط تعلیقی"),("شرط فاسخ","شرط فاسخ"),("تضمین","تضمین"),("ضمانت نامه","ضمانت‌نامه"),("چک تضمینی","چک تضمینی")]:
        if _has(t,term): clauses.append(label)
    nodes.append({"id":"clauses","label":"۶) شروط و تضمین‌ها","result":"موارد حساس: "+"، ".join(dict.fromkeys(clauses)) if clauses else "شرط ویژه مشخصی از متن استخراج نشد"})
    questions.append("آیا وجه التزام، شرط فسخ/فاسخ، داوری، تضمین، چک یا ضمانت‌نامه در قرارداد وجود دارد؟")
    if clauses: flags.append("شروط قراردادی خاص باید عیناً از اصل قرارداد کنترل شوند")

    if _has(t,"پرداخت","واریز","رسید","فاکتور","تحویل"): nodes.append({"id":"performance","label":"۷) اجرای متقابل و پرداخت","result":"نشانه‌ای از پرداخت/تحویل وجود دارد؛ تاریخ و مبلغ باید با اسناد تطبیق شود"})
    else:
        nodes.append({"id":"performance","label":"۷) اجرای متقابل و پرداخت","result":"سوابق اجرای متقابل کافی نیست"}); missing.append("رسید پرداخت/تحویل و سوابق اجرای تعهدات")
    questions.append("چه مقدار از تعهدات دو طرف اجرا شده و چه اسناد یا رسیدهایی آن را ثابت می‌کند؟")

    if _has(t,"اظهارنامه","اخطار","مطالبه رسمی","نامه مطالبه"): flags.append("تاریخ و مفاد مطالبه/اخطار باید با قرارداد و مهلت اجرا تطبیق شود")
    if _has(t,"تعارض","مغایرت","نسخه متفاوت","الحاقیه") : flags.append("تعارض احتمالی بین نسخه‌ها یا الحاقیه‌ها")
    if _has(t,"فورس ماژور","قوه قاهره","حادثه خارج از اختیار"): flags.append("ادعای فورس‌ماژور/حادثه خارج از اختیار نیازمند کنترل شرط و ادله است")

    if not branches: branches.append("ابتدا تعهد اصلی، موعد اجرا و خواسته دقیق مشخص شود")
    sources=_source_hits(["قانون مدنی","قانون تجارت","قانون آیین دادرسی مدنی","قانون ثبت اسناد و املاک"],8)
    return {"sufficient":True,"is_contract":True,"title":"🌳 درخت بررسی قرارداد و تعهدات","nodes":nodes,"branches":list(dict.fromkeys(branches))[:10],"questions":list(dict.fromkeys(questions))[:12],"missing":list(dict.fromkeys(missing))[:10],"flags":list(dict.fromkeys(flags))[:8],"sources":sources,"warning":"این درخت برای issue-spotting و نظم‌دهی بررسی قرارداد است، نه اعلام نتیجه قطعی. متن کامل قرارداد، الحاقیه‌ها و آخرین متن منابع باید کنترل شوند."}

_INTERACTIVE_NODES=[
 {"id":"kind","title":"۱) نوع قرارداد","question":"نوع اصلی قرارداد یا تعهد چیست؟","choices":[("بیع/فروش","b"),("پیمانکاری/خدمات","p"),("اجاره","r"),("وکالت/ضمان/قرض یا سایر","o"),("نامشخص","u")]},
 {"id":"status","title":"۲) وضعیت اجرای تعهد","question":"تعهد اصلی در چه وضعیتی است؟","choices":[("کامل انجام شده","d"),("انجام نشده","n"),("با تأخیر انجام شده","l"),("ناقص/معیوب انجام شده","i"),("نامشخص","u")]},
 {"id":"remedy","title":"۳) خواسته/ضمانت اجرا","question":"خواسته یا ضمانت اجرای مورد نظر کدام است؟","choices":[("الزام به انجام تعهد","e"),("فسخ/انفساخ","f"),("خسارت/وجه التزام","c"),("بطلان/ابطال","v"),("نامشخص","u")]},
 {"id":"clause","title":"۴) شروط خاص","question":"آیا شرط یا تضمین ویژه‌ای در قرارداد وجود دارد؟","choices":[("وجه التزام","p"),("شرط فسخ/فاسخ","f"),("داوری","a"),("تضمین/چک/ضمانت‌نامه","g"),("خیر/نامشخص","u")]},
 {"id":"evidence","title":"۵) ادله و اسناد اجرا","question":"وضعیت اسناد اجرای تعهد و مطالبه چگونه است؟","choices":[("اسناد کامل‌تر موجود است","c"),("بخشی از اسناد موجود است","p"),("اسناد کافی نیست","m"),("نامشخص","u")]},
]

def interactive_contract_start(text):
    base=build_contract_tree(text)
    if not base.get("is_contract"): return {"status":"not_contract","base":base}
    return {"status":"active","base":base,"index":0,"answers":{},"history":[]}

def interactive_contract_step(state,choice):
    if not state or state.get("status")!="active": return {"status":"invalid"}
    idx=int(state.get("index",0))
    if idx>=len(_INTERACTIVE_NODES): return interactive_contract_finalize(state)
    node=_INTERACTIVE_NODES[idx]; valid={c for _,c in node["choices"]}
    if choice not in valid: return {"status":"invalid","state":state}
    state.setdefault("answers",{})[node["id"]]=choice; state.setdefault("history",[]).append(idx); state["index"]=idx+1
    if state["index"]>=len(_INTERACTIVE_NODES): return interactive_contract_finalize(state)
    return {"status":"question","state":state,"node":_INTERACTIVE_NODES[state["index"]]}

def interactive_contract_finalize(state):
    a=state.get("answers",{}); base=state.get("base",{}); paths=list(base.get("branches",[])); missing=list(base.get("missing",[])); flags=list(base.get("flags",[]))
    if a.get("status")=="n": paths.append("بررسی مبنای الزام/ضمانت اجرای عدم انجام تعهد")
    if a.get("status")=="l": paths.append("بررسی آثار تأخیر و شروط مربوط به موعد")
    if a.get("status")=="i": paths.append("بررسی اجرای ناقص، کیفیت تعهد و امکان مطالبه آثار آن")
    if a.get("remedy")=="c": paths.append("بررسی شرط وجه التزام و ادله خسارت، بدون فرض تحقق قطعی شرایط")
    if a.get("remedy")=="f": paths.append("بررسی مبنای قراردادی/قانونی فسخ یا انفساخ")
    if a.get("clause") in {"p","f","a","g"}: flags.append("شرط خاص انتخاب‌شده باید عیناً از متن قرارداد و الحاقیه‌ها بررسی شود")
    if a.get("evidence")=="m": missing.append("اصل قرارداد، الحاقیه‌ها و ادله اجرای/مطالبه تعهد")
    return {"status":"complete","answers":a,"base":base,"paths":list(dict.fromkeys(paths))[:10],"missing":list(dict.fromkeys(missing))[:10],"flags":list(dict.fromkeys(flags))[:8]}

def format_contract_question(node,step,total):
    lines=["🌳 درخت بررسی قرارداد و تعهدات",f"مرحله {step} از {total}","",node["title"],node["question"],""]
    lines += ["• "+label for label,_ in node["choices"]]
    lines += ["","🔒 موتور: درخت تصمیم داخلی و بدون AI"]
    return "\n".join(lines)

def format_contract_result(result):
    if result.get("status")=="not_contract": return "🌳 درخت بررسی قرارداد و تعهدات\n\nℹ️ "+result.get("base",{}).get("message","نشانه کافی از قرارداد پیدا نشد.")
    base=result.get("base",{}); lines=["🌳 نتیجه درخت بررسی قرارداد و تعهدات","","🔒 موتور: داخلی و بدون AI","","🧭 یافته‌های پرونده:"]
    lines += [f"• {n['label']}: {n['result']}" for n in base.get("nodes",[])]
    if result.get("paths"): lines += ["","🛣️ مسیرهای قابل بررسی:"]+["• "+x for x in result["paths"]]
    if result.get("missing"): lines += ["","📂 اطلاعات/مدارک ناقص:"]+["• "+x for x in result["missing"]]
    if result.get("flags"): lines += ["","🚩 نقاط حساس:"]+["• "+x for x in result["flags"]]
    if base.get("sources"): lines += ["","📚 منابع داخلی قابل بررسی:"]+["• "+x["title"] for x in base["sources"]]
    lines += ["","⚠️ "+base.get("warning","")]
    return "\n".join(lines)
