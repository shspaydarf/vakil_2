"""Interactive property/ownership decision tree.

Issue-spotting only. Reuses the central legal corpus and avoids copying
statutory text into the tree. Ownership, registration, possession, co-ownership
and easement issues are deliberately separated from the lease tree.
"""
from __future__ import annotations
from .files import clean_fa
from .legal_packs import _corpus, _norm
from functools import partial
from .text_utils import has_any_normalized_term, find_law_source_hits

_has = partial(has_any_normalized_term, normalizer=_norm)

_source_hits = partial(find_law_source_hits, corpus_loader=_corpus, normalizer=_norm)

def build_property_tree(text:str):
    text=clean_fa(text or "")
    if len(text.strip())<40: return {"sufficient":False,"reason":"متن پرونده برای ساخت مسیر بررسی املاک و مالکیت کافی نیست."}
    t=_norm(text)
    neg=_has(t,"هیچ ملکی","هیچ ادعای مالکیت","ملک مربوط نیست","فاقد موضوع ملکی")
    terms=("ملک","زمین","آپارتمان","مغازه","مالکیت","مالک","سند مالکیت","پلاک ثبتی","خلع ید","تصرف عدوانی","مزاحمت","ممانعت از حق","افراز","مشاع","حق ارتفاق","حق انتفاع","سند رسمی","قولنامه")
    if not _has(t,*terms) or neg:
        return {"sufficient":True,"is_property":False,"title":"🏢 درخت بررسی املاک و مالکیت","message":"نشانه کافی از مسئله ملکی یا مالکیتی در متن پیدا نشد."}
    nodes=[]; questions=[]; missing=[]; flags=[]; paths=[]
    if _has(t,"آپارتمان","واحد مسکونی"): obj="آپارتمان/واحد مسکونی"
    elif _has(t,"مغازه","واحد تجاری","زمین تجاری"): obj="ملک/واحد تجاری"
    elif _has(t,"زمین","باغ","کشاورزی"): obj="زمین/باغ/کشاورزی"
    else: obj="نوع دقیق ملک از متن قطعی نیست"; missing.append("نوع و مشخصات دقیق ملک")
    nodes.append({"id":"object","label":"۱) موضوع ملک","result":obj}); questions.append("ملک دقیقاً چه نوعی است و پلاک/نشانی/مشخصات آن چیست؟")
    if _has(t,"سند رسمی","سند مالکیت","دفتر املاک","مالک رسمی"): own="نشانه سند/مالکیت رسمی وجود دارد"
    elif _has(t,"قولنامه","مبایعه نامه","مبایعه‌نامه","سند عادی"): own="نشانه سند عادی/قولنامه وجود دارد"
    elif _has(t,"ارث","وراث","انحصار وراثت"): own="ادعای مالکیت ناشی از ارث"
    elif _has(t,"ادعای مالکیت","مالکیت خود را ادعا"): own="مالکیت مورد ادعا/اختلاف است"
    else: own="وضعیت مالکیت از متن قطعی نیست"; missing.append("سند و مبنای ادعای مالکیت")
    nodes.append({"id":"ownership","label":"۲) وضعیت مالکیت","result":own}); questions.append("مالک رسمی/مدعی مالکیت چه کسی است و مبنای مالکیت کدام سند یا سبب تملک است؟")
    reg=[]
    for term,label in [("پلاک ثبتی","پلاک ثبتی"),("دفتر املاک","دفتر املاک"),("استعلام ثبتی","استعلام ثبتی"),("حدود اربعه","حدود اربعه"),("تعارض سند","تعارض اسناد")]:
        if _has(t,term): reg.append(label)
    nodes.append({"id":"registration","label":"۳) وضعیت ثبتی","result":"موارد دیده‌شده: "+"، ".join(reg) if reg else "وضعیت ثبتی کافی مشخص نیست"}); questions.append("پلاک ثبتی، سابقه ثبت، استعلام و حدود ملک چه وضعیتی دارد؟")
    if not reg: missing.append("پلاک ثبتی و استعلام/سابقه ثبتی")
    possession=[]
    for term,label in [("متصرف","تصرف"),("خلع ید","خلع ید"),("تصرف عدوانی","تصرف عدوانی"),("مزاحمت","مزاحمت"),("ممانعت از حق","ممانعت از حق"),("مستاجر","تصرف مستأجر")]:
        if _has(t,term): possession.append(label)
    nodes.append({"id":"possession","label":"۴) وضعیت تصرف","result":"موضوعات دیده‌شده: "+"، ".join(dict.fromkeys(possession)) if possession else "وضعیت تصرف روشن نیست"}); questions.append("ملک فعلاً در تصرف چه کسی است و مبنای تصرف او چیست؟")
    if not possession: missing.append("وضعیت فعلی تصرف و سابقه آن")
    disputes=[]
    for term,label in [("خلع ید","خلع ید"),("تصرف عدوانی","تصرف عدوانی"),("مزاحمت","مزاحمت"),("ممانعت از حق","ممانعت از حق"),("افراز","افراز"),("فروش ملک مشاع","فروش ملک مشاع"),("ابطال سند","ابطال سند"),("الزام به تنظیم سند","الزام به تنظیم سند"),("مالکیت","اختلاف/ادعای مالکیت")]:
        if _has(t,term): disputes.append(label)
    nodes.append({"id":"dispute","label":"۵) نوع اختلاف","result":"موضوعات دیده‌شده: "+"، ".join(dict.fromkeys(disputes)) if disputes else "نوع دعوا/اختلاف روشن نیست"}); questions.append("اختلاف اصلی مالکیت، تصرف، سند، افراز، حدود یا حق ارتفاق/انتفاع است؟")
    if not disputes: missing.append("خواسته و نوع اختلاف ملکی")
    if _has(t,"مشاع","شریک","شرکا"):
        paths.append("بررسی وضعیت اشاعه، سهم شرکا و امکان/ضرورت افراز یا فروش ملک مشاع")
        nodes.append({"id":"coownership","label":"۶) ملک مشاع","result":"نشانه مالکیت/تصرف مشاعی وجود دارد"})
        questions.append("تعداد شرکا، میزان سهم هر شریک و وضعیت تصرف یا توافق بین شرکا چیست؟")
    else:
        nodes.append({"id":"coownership","label":"۶) ملک مشاع","result":"نشانه کافی از اشاعه در متن دیده نشد"})
    rights=[]
    for term,label in [("حق ارتفاق","حق ارتفاق"),("حق عبور","حق عبور"),("حق انتفاع","حق انتفاع"),("راه عبور","حق عبور/راه"),("آب","حق مرتبط با آب")]:
        if _has(t,term): rights.append(label)
    nodes.append({"id":"rights","label":"۷) حقوق وابسته","result":"موارد دیده‌شده: "+"، ".join(dict.fromkeys(rights)) if rights else "حق وابسته مشخصی استخراج نشد"}); questions.append("آیا حق ارتفاق، عبور، انتفاع یا حق وابسته دیگری مطرح است؟")
    if rights: paths.append("بررسی منشأ و حدود حق ارتفاق/انتفاع و اسناد اثباتی آن")
    evidence=[]
    for term,label in [("سند مالکیت","سند مالکیت"),("قولنامه","قولنامه/سند عادی"),("مبایعه نامه","مبایعه‌نامه"),("استعلام","استعلام ثبتی"),("نقشه","نقشه/کروکی"),("کارشناسی","کارشناسی"),("شهادت","شهادت"),("تصرف","ادله تصرف")]:
        if _has(t,term): evidence.append(label)
    nodes.append({"id":"evidence","label":"۸) ادله و اسناد","result":"ادله دیده‌شده: "+"، ".join(dict.fromkeys(evidence)) if evidence else "ادله اصلی از متن روشن نیست"}); questions.append("اصل سند مالکیت/معامله، استعلام ثبتی، نقشه و ادله تصرف در پرونده موجود است؟")
    if not evidence: missing.append("اصل سند و ادله مالکیت/تصرف")
    if _has(t,"اجاره","مستاجر","مستأجر"): paths.append("ارتباط با درخت اجاره: تعیین اینکه اختلاف اصلی اجاره‌ای است یا مالکیتی/تصرفی")
    if _has(t,"طلب","مطالبه","محکومیت مالی","توقیف"): paths.append("ارتباط با درخت مطالبات: بررسی اثر مالکیت/ملک بر طلب، وثیقه یا اجرا")
    if _has(t,"قولنامه","مبایعه نامه","مبایعه‌نامه","الزام به تنظیم سند"): paths.append("بررسی زنجیره انتقال، اعتبار اسناد و مسیر تنظیم/ابطال سند در صورت طرح")
    if _has(t,"حدود","مساحت","متراژ","تعارض"): flags.append("اختلاف در حدود/مساحت/اسناد؛ نیازمند تطبیق سند، نقشه و در صورت لزوم کارشناسی")
    if _has(t,"سند عادی","قولنامه") and _has(t,"مالک رسمی"): flags.append("تعارض احتمالی بین سند عادی و وضعیت مالک رسمی؛ بررسی اسناد و مقررات ثبتی ضروری است")
    if _has(t,"تصرف عدوانی") and _has(t,"خلع ید"): flags.append("خلع ید و دعاوی تصرف را نباید صرفاً به دلیل هم‌زمانی واژه‌ها یکی فرض کرد")
    sources=_source_hits(["قانون مدنی","قانون ثبت اسناد و املاک","قانون آیین دادرسی مدنی","قانون اجرای احکام مدنی"],10)
    return {"sufficient":True,"is_property":True,"title":"🌳 درخت بررسی املاک و مالکیت","nodes":nodes,"paths":list(dict.fromkeys(paths))[:12],"questions":list(dict.fromkeys(questions))[:14],"missing":list(dict.fromkeys(missing))[:12],"flags":list(dict.fromkeys(flags))[:10],"sources":sources,"warning":"این درخت برای issue-spotting و نظم‌دهی بررسی مسائل ملکی است، نه اعلام نتیجه قطعی. سند رسمی، سابقه ثبت، نقشه و آخرین وضعیت منابع باید با اصل مدارک و منابع رسمی کنترل شوند."}

_INTERACTIVE_NODES=[
 {"id":"topic","title":"۱) مسئله اصلی ملک","question":"مسئله اصلی پرونده کدام است؟","choices":[("مالکیت/سند","o"),("تصرف/خلع ید","p"),("تصرف عدوانی/مزاحمت/ممانعت","t"),("مشاع/افراز","s"),("حدود/ارتفاق/انتفاع","r")]},
 {"id":"ownership","title":"۲) مبنای مالکیت","question":"وضعیت سند و مالکیت چگونه است؟","choices":[("سند رسمی","f"),("قولنامه/سند عادی","a"),("ارث/وراثت","i"),("مالکیت مورد اختلاف","d"),("نامشخص","u")]},
 {"id":"possession","title":"۳) وضعیت تصرف","question":"ملک فعلاً در تصرف چه کسی است؟","choices":[("مالک","o"),("شریک","s"),("مستأجر","t"),("شخص ثالث","h"),("نامشخص","u")]},
 {"id":"registration","title":"۴) وضعیت ثبتی","question":"وضعیت ثبتی و مشخصات ملک چقدر روشن است؟","choices":[("پلاک و سند روشن","c"),("پلاک/استعلام ناقص","p"),("تعارض یا ابهام ثبتی","x"),("ملک در جریان ثبت/وضعیت خاص","s"),("نامشخص","u")]},
 {"id":"evidence","title":"۵) ادله و اقدام","question":"مهم‌ترین وضعیت ادله یا اقدام فعلی چیست؟","choices":[("اصل اسناد و مدارک موجود","e"),("نیاز به استعلام/نقشه","m"),("نیاز به کارشناسی","k"),("دعوا/رأی در جریان است","l"),("نامشخص","u")]},
]

def interactive_property_start(text):
    base=build_property_tree(text)
    if not base.get("is_property"): return {"status":"not_property","base":base}
    return {"status":"active","base":base,"index":0,"answers":{},"history":[]}

def interactive_property_step(state,choice):
    if not state or state.get("status")!="active": return {"status":"invalid"}
    idx=int(state.get("index",0));
    if idx>=len(_INTERACTIVE_NODES): return interactive_property_finalize(state)
    node=_INTERACTIVE_NODES[idx]; valid={c for _,c in node["choices"]}
    if choice not in valid: return {"status":"invalid","state":state}
    state.setdefault("answers",{})[node["id"]]=choice; state.setdefault("history",[]).append(idx); state["index"]=idx+1
    if state["index"]>=len(_INTERACTIVE_NODES): return interactive_property_finalize(state)
    return {"status":"question","state":state,"node":_INTERACTIVE_NODES[state["index"]]}

def interactive_property_finalize(state):
    a=state.get("answers",{}); base=state.get("base",{}); paths=list(base.get("paths",[])); missing=list(base.get("missing",[])); flags=list(base.get("flags",[]))
    topic=a.get("topic")
    if topic=="o": paths.append("تمرکز بر وضعیت مالکیت، سند، زنجیره انتقال و مقررات ثبتی")
    if topic=="p": paths.append("تفکیک خلع ید از دعاوی تصرف و بررسی مبنای تصرف فعلی")
    if topic=="t": paths.append("تفکیک تصرف عدوانی، مزاحمت و ممانعت از حق بر اساس موضوع و ادله تصرف")
    if topic=="s": paths.append("بررسی سهم شرکا، افراز و در صورت لزوم فروش ملک مشاع")
    if topic=="r": paths.append("بررسی منشأ و حدود حق ارتفاق/انتفاع و ادله آن")
    if a.get("ownership") in {"a","d"}: flags.append("اسناد عادی/ادعای مالکیت باید با وضعیت مالک رسمی و سابقه ثبت تطبیق شود")
    if a.get("possession") in {"t","h"}: paths.append("بررسی مبنای تصرف و تاریخ/کیفیت تصرف، بدون فرض قطعی بودن عنوان دعوا")
    if a.get("registration") in {"p","x","u"}: missing.append("استعلام و وضعیت ثبتی دقیق ملک")
    if a.get("evidence")=="m": missing.append("استعلام ثبتی و نقشه/مدارک حدود")
    if a.get("evidence")=="k": missing.append("نظریه/قرار کارشناسی و مستندات فنی")
    return {"status":"complete","answers":a,"base":base,"paths":list(dict.fromkeys(paths))[:12],"missing":list(dict.fromkeys(missing))[:12],"flags":list(dict.fromkeys(flags))[:10]}

def format_property_question(node,step,total):
    return "\n".join(["🌳 درخت بررسی املاک و مالکیت",f"مرحله {step} از {total}","",node["title"],node["question"],""]+["• "+label for label,_ in node["choices"]]+["","🔒 موتور: درخت تصمیم داخلی و بدون AI"])

def format_property_result(result):
    if result.get("status")=="not_property": return "🌳 درخت بررسی املاک و مالکیت\n\nℹ️ "+result.get("base",{}).get("message","نشانه کافی از مسئله ملکی پیدا نشد.")
    base=result.get("base",{}); lines=["🌳 نتیجه درخت بررسی املاک و مالکیت","","🔒 موتور: داخلی و بدون AI","","🧭 یافته‌های پرونده:"]
    lines += [f"• {n['label']}: {n['result']}" for n in base.get("nodes",[])]
    if result.get("paths"): lines += ["","🛣️ مسیرهای قابل بررسی:"]+["• "+x for x in result["paths"]]
    if result.get("missing"): lines += ["","📂 اطلاعات/مدارک ناقص:"]+["• "+x for x in result["missing"]]
    if result.get("flags"): lines += ["","🚩 نقاط حساس:"]+["• "+x for x in result["flags"]]
    if base.get("sources"): lines += ["","📚 منابع داخلی قابل بررسی:"]+["• "+x["title"] for x in base["sources"]]
    lines += ["","⚠️ "+base.get("warning","")]
    return "\n".join(lines)
