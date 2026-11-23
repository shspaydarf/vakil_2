"""Interactive lease/rent decision tree for an active case.

Issue-spotting only. The workflow records facts supplied by the lawyer and
uses the existing internal legal corpus; it does not determine the legal
outcome or substitute for checking the current primary source.
"""
from __future__ import annotations
import re
from .files import clean_fa
from .legal_packs import _corpus, _norm
from functools import partial
from .text_utils import has_any_normalized_term, find_law_source_hits


_has = partial(has_any_normalized_term, normalizer=_norm)


_source_hits = partial(find_law_source_hits, corpus_loader=_corpus, normalizer=_norm)


def build_lease_tree(text: str):
    text=clean_fa(text or "")
    if len(text.strip()) < 40:
        return {"sufficient":False,"reason":"متن پرونده برای ساخت مسیر بررسی اجاره کافی نیست."}
    t=_norm(text)
    explicit_negative = _has(t,"هیچ رابطه اجاره","بدون رابطه اجاره","فاقد رابطه اجاره","رابطه اجاره‌ای ندارد")
    is_lease=_has(t,"اجاره","موجر","مستاجر","مستأجر","ودیعه","رهن","تخلیه","اجاره نامه","اجاره‌نامه","سرقفلی","حق کسب و پیشه") and not explicit_negative
    if not is_lease:
        return {"sufficient":True,"is_lease":False,"title":"🏠 درخت بررسی اجاره","message":"در متن پرونده نشانه کافی از رابطه اجاره پیدا نشد. قرارداد یا بخش مرتبط را به پرونده اضافه کنید."}
    nodes=[]; questions=[]; missing=[]; flags=[]; branches=[]
    # 1 date / regime
    has_date=bool(re.search(r"\d{1,4}[/-]\d{1,2}[/-]\d{1,4}",text)) or _has(t,"سال قرارداد","تاریخ قرارداد","منعقد شد")
    if has_date:
        result="تاریخ یا قرینه‌ای از زمان قرارداد دیده می‌شود؛ باید با اصل قرارداد تطبیق شود"
    else:
        result="تاریخ قرارداد در متن کافی نیست"; missing.append("تاریخ انعقاد، تمدید و آخرین الحاقیه")
    questions.append("قرارداد دقیقاً چه تاریخی منعقد یا تمدید شده و آیا نسخه‌های قبلی وجود دارد؟")
    nodes.append({"id":"date","label":"۱) تاریخ و سابقه رابطه","result":result})

    # 2 property/use
    if _has(t,"تجاری","مغازه","سرقفلی","حق کسب و پیشه","کسب و پیشه"):
        prop="نشانه ملک/کاربری تجاری وجود دارد"
        questions.append("ملک تجاری است و آیا سرقفلی یا حق کسب و پیشه برای آن ادعا می‌شود؟")
    elif _has(t,"مسکونی","آپارتمان","خانه","منزل"):
        prop="نشانه ملک مسکونی وجود دارد"
        questions.append("کاربری ملک و استفاده واقعی مستأجر دقیقاً چیست؟")
    else:
        prop="نوع ملک از متن قطعی نیست"; missing.append("نوع ملک و کاربری آن")
        questions.append("ملک مسکونی، تجاری یا دارای کاربری دیگری است؟")
    nodes.append({"id":"property","label":"۲) نوع ملک و کاربری","result":prop})

    # 3 contract form
    if _has(t,"رسمی","دفترخانه","سند رسمی"):
        form="نشانه قرارداد/سند رسمی وجود دارد"
    elif _has(t,"عادی","دست نویس","دست‌نویس","کد رهگیری","مبایعه نامه"):
        form="نشانه سند عادی یا ثبت قراردادی وجود دارد"
    else:
        form="نوع سند از متن قطعی نیست"; missing.append("اصل قرارداد و مشخصات رسمی/عادی بودن آن")
    questions.append("اصل قرارداد، امضاها، کد/شناسه و الحاقیه‌ها در دسترس است؟")
    nodes.append({"id":"form","label":"۳) نوع سند اجاره","result":form})

    # 4 term / continuation
    if _has(t,"پایان مدت","منقضی","انقضای مدت","تمام شده","تمام شد"):
        term="نشانه پایان یا انقضای مدت دیده می‌شود"
        branches.append("بررسی مسیر مرتبط با پایان مدت و وضعیت ادامه تصرف")
    elif _has(t,"تمدید","تمدید شد","قرارداد جدید"):
        term="نشانه تمدید/قرارداد جدید وجود دارد"
        branches.append("بررسی آثار تمدید و نسخه/شرایط جدید")
    else:
        term="وضعیت مدت قرارداد روشن نیست"; missing.append("مدت قرارداد و وضعیت تمدید")
    questions.append("مدت قرارداد تمام شده یا تمدید/توافق جدیدی بعد از آن صورت گرفته است؟")
    nodes.append({"id":"term","label":"۴) مدت و تمدید","result":term})

    # 5 dispute type
    dispute=[]
    if _has(t,"تخلیه","دستور تخلیه","تحویل ملک"): dispute.append("تخلیه")
    if _has(t,"اجاره معوق","اجاره بها","اجاره‌بها","اجاره بهاء","عدم پرداخت اجاره"): dispute.append("اجاره‌بهای معوق")
    if _has(t,"ودیعه","رهن","پس گرفتن رهن","استرداد ودیعه"): dispute.append("ودیعه/رهن")
    if _has(t,"خسارت","خرابی ملک","آسیب به ملک"): dispute.append("خسارت")
    if _has(t,"فسخ","فسخ قرارداد"): dispute.append("فسخ")
    if _has(t,"سرقفلی","حق کسب و پیشه"): dispute.append("سرقفلی/حق کسب و پیشه")
    if dispute:
        result="موضوعات دیده‌شده: "+"، ".join(dict.fromkeys(dispute))
    else:
        result="موضوع اختلاف از متن قطعی نیست"; missing.append("خواسته/اختلاف اصلی و علت آن")
    questions.append("خواسته اصلی دقیقاً تخلیه، اجاره‌بها، ودیعه، خسارت، فسخ یا موضوع دیگری است؟")
    nodes.append({"id":"dispute","label":"۵) موضوع اختلاف","result":result})

    # 6 payment/deposit
    if _has(t,"پرداخت شد","پرداخت شده","رسید پرداخت","واریز","حواله"):
        pay="نشانه‌هایی از پرداخت وجود دارد؛ مبالغ و تاریخ‌ها باید با رسیدها تطبیق شوند"
    else:
        pay="سوابق پرداخت کافی در متن دیده نمی‌شود"; missing.append("رسیدهای ودیعه و اجاره و جدول پرداخت‌ها")
    questions.append("مبلغ ودیعه و اجاره‌بهای ماهانه/معوق با چه رسیدها یا گردش حسابی اثبات می‌شود؟")
    nodes.append({"id":"payment","label":"۶) پرداخت و ودیعه","result":pay})

    # 7 special commercial / prior relation
    special=[]
    if _has(t,"سرقفلی","حق کسب و پیشه","کسب و پیشه"): special.append("حق تجاری/سرقفلی")
    if _has(t,"قبل از ۱۳۷۶","قبل از 1376","سال ۱۳۷۵","سال 1375"): special.append("سابقه پیش از ۱۳۷۶")
    if _has(t,"انتقال به غیر","واگذاری به غیر","اجاره به دیگری"): special.append("انتقال/واگذاری به غیر")
    if _has(t,"تغییر کاربری","استفاده غیرمجاز","تغییر شغل"): special.append("تغییر استفاده/شغل")
    if special:
        result="موضوعات ویژه: "+"، ".join(dict.fromkeys(special))
        flags.append("پرونده دارای نشانه‌ای از وضعیت ویژه است؛ مسیر آن باید جداگانه بررسی شود")
    else:
        result="وضعیت ویژه تجاری/انتقالی از متن قطعی نیست"
    questions.append("آیا سابقه استیجاری قدیمی، سرقفلی، انتقال به غیر یا تخلف از کاربری/شغل وجود دارد؟")
    nodes.append({"id":"special","label":"۷) وضعیت‌های ویژه","result":result})

    if "تخلیه" in dispute: branches.append("بررسی مبنای دقیق تخلیه و مرجع/مسیر قابل بررسی")
    if "اجاره‌بهای معوق" in dispute: branches.append("بررسی مطالبه اجاره‌بها و آثار قراردادی عدم پرداخت")
    if "ودیعه/رهن" in dispute: branches.append("بررسی استرداد ودیعه و تعهدات متقابل هنگام تخلیه")
    if "خسارت" in dispute: branches.append("بررسی خسارت، وضعیت تحویل و تفکیک استهلاک عادی از خسارت ادعایی")
    if "فسخ" in dispute: branches.append("بررسی شرط و مبنای ادعای فسخ در قرارداد")
    if "سرقفلی/حق کسب و پیشه" in dispute: branches.append("بررسی مستقل حقوق تجاری و تاریخ ایجاد/انتقال آن")
    if not branches: branches.append("ابتدا موضوع اصلی اختلاف و خواسته دقیق مشخص شود")

    if _has(t,"اختلاف مبلغ","مبلغ متفاوت","ودیعه متفاوت"): flags.append("تعارض در مبالغ ودیعه/اجاره")
    if _has(t,"قرارداد متفاوت","نسخه دیگر","الحاقیه") and _has(t,"تعارض","مغایرت","متفاوت"): flags.append("احتمال تعارض بین نسخه‌ها یا الحاقیه‌ها")
    if _has(t,"کلید تحویل","تحویل کلید","تخلیه واقعی"): flags.append("تاریخ و کیفیت تحویل/تخلیه باید با اسناد تطبیق شود")
    if _has(t,"اظهارنامه","اخطار"): flags.append("سوابق مطالبه/اخطار باید با تاریخ‌ها تطبیق شود")

    sources=_source_hits(["قانون روابط موجر و مستأجر","قانون مدنی","قانون آیین دادرسی مدنی","قانون ثبت اسناد و املاک","قانون ساماندهی بازار زمین، مسکن و اجاره بها"],8)
    return {"sufficient":True,"is_lease":True,"title":"🌳 درخت بررسی اجاره","nodes":nodes,"branches":list(dict.fromkeys(branches)),"questions":list(dict.fromkeys(questions))[:12],"missing":list(dict.fromkeys(missing))[:10],"flags":list(dict.fromkeys(flags))[:8],"sources":sources,"warning":"این درخت برای issue-spotting و نظم‌دهی بررسی پرونده است، نه اعلام نتیجه قطعی. تاریخ قرارداد، نوع ملک، اصل اسناد و آخرین متن منابع باید کنترل شوند."}


_INTERACTIVE_NODES=[
 {"id":"role","title":"۱) سمت طرف پرونده","question":"در این اختلاف شما کدام سمت را بررسی می‌کنید؟","choices":[("موجر","l"),("مستأجر","t"),("هر دو/نامشخص","u")]},
 {"id":"property","title":"۲) نوع ملک","question":"نوع ملک یا کاربری آن چیست؟","choices":[("مسکونی","r"),("تجاری","c"),("نامشخص/سایر","u")]},
 {"id":"date","title":"۳) وضعیت زمانی قرارداد","question":"وضعیت قرارداد از نظر تاریخ چگونه است؟","choices":[("قرارداد جاری","a"),("مدت تمام شده","e"),("تمدید/قرارداد جدید","n"),("نامشخص","u")]},
 {"id":"dispute","title":"۴) موضوع اصلی اختلاف","question":"موضوع اصلی پرونده چیست؟","choices":[("تخلیه","v"),("اجاره‌بها","r"),("ودیعه/رهن","d"),("خسارت/فسخ","x"),("سرقفلی/حق کسب و پیشه","g"),("نامشخص","u")]},
 {"id":"special","title":"۵) وضعیت ویژه","question":"آیا یکی از این موارد مطرح است؟","choices":[("سرقفلی/حق کسب و پیشه","g"),("انتقال به غیر/تغییر شغل","t"),("سابقه قدیمی","o"),("خیر/نامشخص","u")]},
]

def interactive_lease_start(text):
    base=build_lease_tree(text)
    if not base.get("is_lease"): return {"status":"not_lease","base":base}
    return {"status":"active","base":base,"index":0,"answers":{},"history":[]}

def interactive_lease_step(state,choice):
    if not state or state.get("status")!="active": return {"status":"invalid"}
    idx=int(state.get("index",0))
    if idx>=len(_INTERACTIVE_NODES): return interactive_lease_finalize(state)
    node=_INTERACTIVE_NODES[idx]; valid={c for _,c in node["choices"]}
    if choice not in valid: return {"status":"invalid","state":state}
    state.setdefault("answers",{})[node["id"]]=choice; state.setdefault("history",[]).append(idx); state["index"]=idx+1
    if state["index"]>=len(_INTERACTIVE_NODES): return interactive_lease_finalize(state)
    return {"status":"question","state":state,"node":_INTERACTIVE_NODES[state["index"]]}

def interactive_lease_finalize(state):
    a=state.get("answers",{}); base=state.get("base",{})
    paths=list(base.get("branches",[])); missing=list(base.get("missing",[])); flags=list(base.get("flags",[]))
    if a.get("dispute")=="v": paths.append("بررسی مسیر تخلیه بر اساس علت، تاریخ و نوع سند")
    if a.get("dispute")=="r": paths.append("بررسی مطالبه اجاره‌بهای معوق و شروط قراردادی")
    if a.get("dispute")=="d": paths.append("بررسی استرداد ودیعه و تعهدات متقابل")
    if a.get("dispute")=="g" or a.get("special")=="g": flags.append("حقوق تجاری/سرقفلی باید مستقل و با تاریخ ایجاد حق بررسی شود")
    if a.get("date")=="e": paths.append("بررسی آثار پایان مدت و ادامه تصرف")
    if a.get("special")=="t": missing.append("مدرک/شرط مربوط به انتقال به غیر یا تغییر شغل")
    if a.get("property")=="u": missing.append("نوع و کاربری دقیق ملک")
    return {"status":"complete","answers":a,"base":base,"paths":list(dict.fromkeys(paths))[:10],"missing":list(dict.fromkeys(missing))[:10],"flags":list(dict.fromkeys(flags))[:8]}

def format_lease_question(node,step,total):
    lines=["🌳 درخت بررسی اجاره",f"مرحله {step} از {total}","",node["title"],node["question"],""]
    for label,_ in node["choices"]: lines.append("• "+label)
    lines += ["","🔒 موتور: درخت تصمیم داخلی و بدون AI"]
    return "\n".join(lines)

def format_lease_result(result):
    if result.get("status")=="not_lease": return "🌳 درخت بررسی اجاره\n\nℹ️ "+result.get("base",{}).get("message","نشانه کافی از اجاره پیدا نشد.")
    base=result.get("base",{}); lines=["🌳 نتیجه درخت بررسی اجاره","","🔒 موتور: داخلی و بدون AI"]
    lines.append("\n🧭 یافته‌های پرونده:")
    for n in base.get("nodes",[]): lines.append(f"• {n['label']}: {n['result']}")
    if result.get("paths"): lines += ["","🛣️ مسیرهای قابل بررسی:"]+["• "+x for x in result["paths"]]
    if result.get("missing"): lines += ["","📂 اطلاعات/مدارک ناقص:"]+["• "+x for x in result["missing"]]
    if result.get("flags"): lines += ["","🚩 نقاط حساس:"]+["• "+x for x in result["flags"]]
    if base.get("sources"): lines += ["","📚 منابع داخلی قابل بررسی:"]+["• "+x["title"] for x in base["sources"]]
    lines += ["","⚠️ "+base.get("warning","")]
    return "\n".join(lines)
