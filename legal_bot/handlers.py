"""Telegram handlers for the stable Core V1 integration.

This module intentionally exposes one canonical handler per user flow.  New
features should be added behind a handler/service boundary and registered in
main.py; callbacks must never exist without a registered handler.
"""
import asyncio
import re
import difflib
import logging
import time
from io import BytesIO
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup,
    WebAppInfo, ReplyKeyboardRemove,
)
from telegram.ext import CallbackQueryHandler, ContextTypes
from .core import CaseIntakeService, CaseWorkflowError
from .config import (
    MINIAPP_URL, ADMIN_TELEGRAM_IDS, PHONE_HASH_SECRET, FREE_CASES, ADMIN_CARD_NUMBER,
    ADMIN_CARD_HOLDER, SUBSCRIPTION_PRICE_TEXT, SUPPORT_EMAIL, MAX_FILE_MB,
    AI_ENABLED, AI_EXTERNAL_DATA_CONSENT, AI_TEXT_MAX_CHARS, AI_MONTHLY_TEXT_LIMIT,
    AI_CASE_MONTHLY_LIMIT, DEBUG_EXTRACTION, AI_DEEP_ON_DEMAND, CASE_NAME_MAX_CHARS,
    MAX_CASE_VERSIONS, MAX_CASE_ADDITIONS, MAX_CASE_ADDITION_FILES, MAX_CASE_NOTE_CHARS,
    MAX_CASE_UPLOAD_FILES, FREE_WEEKLY_CREDITS
)
from .db import *
from . import db as _db
from .files import new_path, extract_with_diagnostics, ocr_status
from .storage import store_case_file, validate_supported_file
from .analysis import analyze, local_case_search, search_case_full_text, search_cases_full_text, search_case_documents, format_case_search_results
from .unified_search import search_user_workspace
from .laws import search as law_search, get_source_record, related_sources
from .glossary import lookup, format_entries
from .formatting import analysis_text, case_summary_text, law_text, reply_long
from .legal_relevance import find_relevant_laws
from .text_guard import normalize_output
from .ai import text_assist, structured_analysis, draft_legal_brief, ask_ai_question, summarize_case_for_lawyer, review_case_contradictions, review_contract_risks
from .quiz import list_levels as quiz_list_levels, list_terms as quiz_list_terms, list_courses as quiz_list_courses, list_categories as quiz_categories, list_essay_categories as quiz_essay_categories, get_questions as quiz_get_questions, get_course_questions as quiz_get_course, get_essay_items as quiz_get_essay, format_question as quiz_format_question, format_essay as quiz_format_essay, check_answer as quiz_check_answer, disclaimer as quiz_disclaimer, essay_disclaimer as quiz_essay_disclaimer
from .brief_templates import list_templates, get_template, TEMPLATES
from .contract_playbooks import list_contract_playbooks, build_playbook_checklist
from .contract_report_pdf import build_contract_report_pdf
from .brief_writer import build_brief, review_brief
from .brief_workflow import detect_brief_gaps, brief_case_summary, source_label
from .brief_information import resolve_case_information, format_information_map, apply_information_answer
from .timeline_engine import build_case_chronology, format_chronology
from .issue_engine import build_case_issues, format_case_issues
from .evidence_engine import build_evidence_matrix, format_evidence_matrix
from .authority_engine import build_case_authorities, format_case_authorities
from .strategy_engine import build_case_strategies, format_case_strategies
from .draft_engine import build_case_draft, render_case_draft
from .adversarial_review import build_case_adversarial_review, render_adversarial_review
from .rewrite_engine import build_case_rewrite, render_rewrite
from .consistency_gate import build_case_consistency_gate, render_consistency_gate
from .output_engine import build_case_output, build_case_docx, build_case_pdf, render_output_overview, render_case_text, render_change_report, render_gate_report, render_source_report
from .drafting_workflow import run_drafting_workflow, workflow_label, preflight_v150, next_required_question, workflow_question_text, load_workflow_state, save_workflow_state
from .brief_workspace import (remember_version, current_text, history_lines, get_version, apply_local_edit,
    diff_summary, compare_versions, add_inline_citations, brief_case_understanding, argument_matrix, extract_opposing_claims, opposing_response_matrix, apply_opposing_responses, opposing_response_outline,
    validate_brief, cleanup_brief_text, detailed_diff_summary, brief_consistency_check, format_consistency_report, brief_gap_analysis, format_gap_analysis)
from .calendar_dates import extract_important_dates, parse_jalali, parse_gregorian, jalali_to_gregorian, gregorian_to_jalali
from .next_step import analyze_next_step, format_next_step
from .case_version_compare import compare_case_versions
from .case_guidance import build_case_guidance, format_case_guidance
from .check_tree import (build_check_tree, format_check_tree, interactive_check_start, interactive_check_step, format_interactive_question, format_interactive_result, _INTERACTIVE_NODES)
from .ejare_tree import (build_lease_tree, interactive_lease_start, interactive_lease_step, format_lease_question, format_lease_result, _INTERACTIVE_NODES as _LEASE_INTERACTIVE_NODES)
from .contract_tree import (interactive_contract_start, interactive_contract_step, format_contract_question, format_contract_result, _INTERACTIVE_NODES as _CONTRACT_INTERACTIVE_NODES)
from .claims_tree import (interactive_claims_start, interactive_claims_step, format_claims_question, format_claims_result, _INTERACTIVE_NODES as _CLAIMS_INTERACTIVE_NODES)
from .property_tree import (interactive_property_start, interactive_property_step, format_property_question, format_property_result, _INTERACTIVE_NODES as _PROPERTY_INTERACTIVE_NODES)
from .tax_assistant import build_tax_guide, build_tax_screen_guide
from .shora_assistant import build_shora_guide
from .check_assistant import build_check_guide, search_hint as check_search_hint, HOLDER_TOPICS, DRAWER_TOPICS
from .family_assistant import build_family_guide, search_hint as family_search_hint, CREDITOR_TOPICS, DEBTOR_TOPICS
from .ejare_assistant import build_ejare_guide, search_hint as ejare_search_hint, ROLES as EJARE_ROLES, TENANT_TOPICS, LANDLORD_TOPICS
from .calculator_data import MAHR_ANNUAL_INDEX, MAHR_PROVISIONAL_YEARS
from .calculators import (parse_amount as calc_parse_amount, mahr_value, diyah_percentage, diyah_items,
    HEAD_WOUND_PCTS, COLOR_PCTS, DIYA_FULL_1405_NORMAL, DIYA_FULL_1405_HARAM,
    court_fee, lawyer_fee_financial, lawyer_fee_split, parse_iso_date, add_calendar_days, alcohol_article_702_fine, delay_damage, CALC_SOURCE_NOTES)

logger = logging.getLogger(__name__)

# V138: service/advertising UI is temporarily suspended.
# The underlying service-listing/referral code remains intact for later reactivation.
SERVICE_LISTINGS_UI_ENABLED = False

def after_search_menu():
    """Compact actions after a legal search so users are not dumped only to main menu."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('🔎 جستجوی جدید', callback_data='law'),
         InlineKeyboardButton('🧮 محاسبات', callback_data='calculators')],
        [InlineKeyboardButton('📖 راهنما', callback_data='help'),
         InlineKeyboardButton('🏠 منوی اصلی', callback_data='home')],
    ])


def menu_lawyer():
    """Compact first-level menu: frequent actions stay one tap away.

    V141 UX rule: the main menu is a launchpad, not a catalog. Less-frequent
    features live behind one clearly named secondary menu; free-form text
    remains the preferred input for search and other stateful flows.
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('🔎 جستجوی حقوقی', callback_data='law'),
         InlineKeyboardButton('📂 پرونده‌ها', callback_data='cases')],
        [InlineKeyboardButton('➕ پرونده جدید', callback_data='newcase'),
         InlineKeyboardButton('🧮 محاسبات', callback_data='calculators')],
        [InlineKeyboardButton('🤖 دستیار هوشمند', callback_data='aimenu')],
        [InlineKeyboardButton('🎓 آزمون دانشجویی', callback_data='quiz'),
         InlineKeyboardButton('📅 تاریخ‌های مهم', callback_data='importantdates')],
        [InlineKeyboardButton('📊 وضعیت حساب', callback_data='status'),
         InlineKeyboardButton('💳 اشتراک', callback_data='subscribe')],
        [InlineKeyboardButton('🆘 پشتیبانی', callback_data='support_menu'),
         InlineKeyboardButton('📖 راهنما', callback_data='help')],
    ])


def menu(uid=None):
    """Current product is lawyer-only; legacy role data no longer changes the UI."""
    return menu_lawyer()



def support_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('💬 ارتباط با پشتیبانی', callback_data='support')],
        [InlineKeyboardButton('🐞 گزارش مشکل / خطا', callback_data='feedback')],
        [InlineKeyboardButton('🏠 منوی اصلی', callback_data='home')],
    ])


def legal_search_menu():
    # Compatibility keyboard for older/stale messages. The current main-menu
    # search button goes directly to `law`, where legal sources and glossary
    # terms are searched together. Keep this callback-safe fallback for users
    # who still have an older inline keyboard in an open Telegram chat.
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('🔎 جستجوی یکپارچه در همه منابع حقوقی', callback_data='law')],
        [InlineKeyboardButton('🏠 منوی اصلی', callback_data='home')],
    ])


def main_reply_keyboard():
    """Small persistent keyboard used only to summon the full inline menu.

    The large inline menu is intentionally not attached to every response.
    This keeps conversations clean while leaving a single, always-available
    way for the user to reopen the main menu.
    """
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton('🔎 جستجوی حقوقی'), KeyboardButton('🧮 محاسبات')],
            [KeyboardButton('☰ منوی اصلی')],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder='عبارت حقوقی را بنویسید یا یک میانبر را بزنید'
    )


def access_choice_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('💎 نسخه پرو — ۵۰ پرونده', callback_data='choose_pro')],
        [InlineKeyboardButton('🎁 نسخه رایگان — ۳ پرونده', callback_data='choose_free')],
    ])


def miniapp_keyboard(case_id=None):
    if not MINIAPP_URL:
        return None
    url = MINIAPP_URL
    if case_id is not None:
        url = f"{url}?case={int(case_id)}"
    return ReplyKeyboardMarkup([[KeyboardButton("🚀 میزکار Mini App", web_app=WebAppInfo(url=url))]], resize_keyboard=True)


def case_menu(cid):
    """Compact case hub: group related actions without changing callback contracts.

    Keep every existing action reachable, but order the common workflow first:
    overview -> documents -> analysis -> drafting -> follow-up. Destructive
    actions remain isolated at the bottom and are never adjacent to routine work.
    """
    rows = [
        [InlineKeyboardButton('📊 نمای کلی', callback_data=f'cworkspace:{cid}'),
         InlineKeyboardButton('🕘 خط زمانی', callback_data=f'ctimeline:{cid}')],
        [InlineKeyboardButton('📎 افزودن سند / متن', callback_data=f'cfile:add:{cid}'),
         InlineKeyboardButton('📄 مقایسه نسخه جدید', callback_data=f'cfile:version:{cid}')],
        [InlineKeyboardButton('🧠 تحلیل پرونده', callback_data=f'canalysis:{cid}'),
         InlineKeyboardButton('🧾 خلاصه پرونده', callback_data=f'csummary:{cid}')],
        [InlineKeyboardButton('✍️ نگارش لایحه', callback_data=f'cdrafting:{cid}'),
         InlineKeyboardButton('🤖 پرسش درباره پرونده', callback_data=f'cai:{cid}')],
        [InlineKeyboardButton('📄 متن استخراج‌شده', callback_data=f'casetext:{cid}'),
         InlineKeyboardButton('🔎 جستجو در پرونده', callback_data=f'caseq:{cid}')],
        [InlineKeyboardButton('✅ کارها و اقدام بعدی', callback_data=f'ctasks:{cid}'),
         InlineKeyboardButton('⚙️ وضعیت پرونده', callback_data=f'cstatus:{cid}')],
        [InlineKeyboardButton('➡️ پیشنهاد قدم بعدی', callback_data=f'cnext:{cid}'),
         InlineKeyboardButton('⚖️ مقررات مرتبط', callback_data=f'claws:{cid}')],
        [InlineKeyboardButton('🗒️ یادداشت وکیل', callback_data=f'cnote:{cid}')],
        [InlineKeyboardButton('🗄️ بایگانی', callback_data=f'carchive:{cid}')],
        [InlineKeyboardButton('🗑️ حذف دائمی پرونده', callback_data=f'casedelete:{cid}')],
        [InlineKeyboardButton('📂 همه پرونده‌ها', callback_data='cases'),
         InlineKeyboardButton('🏠 منوی اصلی', callback_data='home')],
    ]
    return InlineKeyboardMarkup(rows)


def _hash_phone(phone):
    import hashlib, hmac
    return hmac.new(PHONE_HASH_SECRET.encode(), phone.encode(), hashlib.sha256).hexdigest()


def _is_registered(uid):
    return get_user(uid) is not None


def _clear_pending_inputs(context, keep=None):
    keys=('awaiting_lawyer_code','awaiting_lawyer_upgrade','registration_name','registration_license','phone','pending_private_action','awaiting_law_query','awaiting_unified_legal_search','awaiting_case_query',
          'awaiting_glossary','awaiting_global_search','awaiting_feedback',
          'awaiting_ai_question','awaiting_aiassist','awaiting_ai_context_choice','awaiting_case_ai_question','awaiting_case_ai_context_choice','awaiting_case_name','awaiting_case_file','case_upload_buffer','awaiting_case_addition','awaiting_case_version_file','awaiting_case_note','ref_topic','ref_city','ref_urgency','ref_details','awaiting_referral_info','awaiting_task_title',
          'service_name','service_phone','service_city','service_specialty','service_title',
          'service_fee_type','service_fee_value','service_description','service_charity','service_license_photo','service_license_photo_waiting',
          'calc_mahr_amount','calc_mahr_year','calc_quick_percent','brief_v150_waiting_answer','brief_v150_question_key','brief_v150_question_label','brief_v150_resolver','brief_v150_facts','brief_v150_answers','brief_v150_deferred','brief_v150_confirmed','calc_quick_percent_rate','calc_quick_percent_amount','calc_quick_rial','calc_quick_rial_reverse','calc_quick_installment','calc_quick_installment_amount','calc_quick_installment_count','calc_quick_datediff','calc_quick_datediff_start','calc_calendar_convert','calc_alcohol_value','tax_activity','tax_task','tax_income','tax_docs','tax_flow','tax_screen_waiting','shora_flow','ejare_flow','family_flow','check_flow','calc_fee_amount','calc_fee_stage','calc_lawyer_amount','calc_deadline_date','calc_delay_amount','calc_delay_src','calc_delay_dst','calc_delay_amount_value','calc_delay_src_value','brief_facts','brief_type','brief_stage','brief_mode','client_quick_add','client_name','client_phone','client_national_id','client_note','client_edit_id','client_search','awaiting_task_title','awaiting_task_due','pending_task_title')
    for key in keys:
        if key != keep:
            context.user_data.pop(key, None)


async def _require_registered(q):
    if not _is_registered(q.from_user.id):
        await q.message.reply_text('ابتدا /start را بزنید.')
        return False
    return True

async def _require_lawyer(q, context, action):
    """Compatibility gate: lawyer-code verification is suspended.

    Private/case features remain available to registered users for now.  The
    helper name is retained so existing callbacks do not need risky rewrites.
    AI remains optional and is never required by the core document/search flow.
    """
    return await _require_registered(q)


async def start(update, context):
    uid = update.effective_user.id
    context.user_data.clear()
    if _is_registered(uid):
        ensure_subscription(uid)
        # Legacy client/lawyer selections no longer affect the product UI.
        # Normalize the stored role to lawyer so old accounts are migrated lazily.
        if get_user_role(uid) != 'lawyer':
            set_user_role(uid, 'lawyer')
        await update.effective_message.reply_text(
            '⚖️ به دستیار حقوقی خوش آمدید.\n\nبرای باز کردن منوی اصلی، دکمه «☰ منوی اصلی» را بزنید.',
            reply_markup=main_reply_keyboard(),
        )
        return
    kb = ReplyKeyboardMarkup([[KeyboardButton('📱 ارسال شماره تماس', request_contact=True)]], resize_keyboard=True, one_time_keyboard=True)
    await update.effective_message.reply_text(
        '⚖️ برای شروع ثبت‌نام وکیل، ابتدا شماره تماس خود را با دکمه زیر ارسال کنید.\n'
        'سپس فقط نام و نام خانوادگی و شماره پروانه وکالت را وارد می‌کنید.', reply_markup=kb)


async def contact(update, context):
    uid = update.effective_user.id
    c = update.effective_message.contact
    if c.user_id and c.user_id != uid:
        await update.effective_message.reply_text('❌ لطفاً شماره تماس حساب خودتان را ارسال کنید.')
        return
    if context.user_data.get('service_phone'):
        context.user_data.pop('service_phone',None)
        context.user_data['service_phone_value']=c.phone_number.strip()
        _clear_pending_inputs(context, keep='service_city')
        context.user_data['service_city']=True
        await update.effective_message.reply_text('📍 شهر محل فعالیت خود را وارد کنید.', reply_markup=ReplyKeyboardRemove())
        return
    _clear_pending_inputs(context)
    phone = c.phone_number.strip()
    context.user_data['phone'] = phone
    context.user_data['registration_name'] = True
    await update.effective_message.reply_text(
        '👤 نام و نام خانوادگی خود را وارد کنید:',
        reply_markup=ReplyKeyboardRemove())
    return


async def _after_registration(update, context):
    uid = update.effective_user.id
    await update.effective_message.reply_text("✅ ثبت‌نام انجام شد.", reply_markup=ReplyKeyboardRemove())
    set_account_mode(uid, "free")
    grant_free_entitlement(uid)
    # The product is now lawyer-only. Keep the legacy role table for database
    # compatibility, but every newly registered account is stored as lawyer.
    set_user_role(uid, 'lawyer')
    await update.effective_message.reply_text(
        f"🎁 نسخه رایگان فعال شد.\n🪙 {FREE_WEEKLY_CREDITS} اعتبار رایگان در هر ۷ روز\n\n⚖️ این نسخه برای استفاده حرفه‌ای وکلا طراحی شده است.",
        reply_markup=main_reply_keyboard(),
    )


def role_choice_keyboard():
    """Legacy compatibility keyboard; new UI no longer exposes role choice."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚖️ ادامه به‌عنوان وکیل", callback_data="role:set:lawyer")],
        [InlineKeyboardButton("🏠 منوی اصلی", callback_data="home")],
    ])


async def role_set_cb(update, context):
    # Compatibility for stale registration keyboards. The only supported role
    # in the current product is lawyer.
    q = update.callback_query
    await q.answer()
    if not await _require_registered(q):
        return
    set_user_role(q.from_user.id, 'lawyer')
    await q.message.reply_text(
        "⚖️ این نسخه فقط برای وکلا فعال است. نقش شما «وکیل» تنظیم شد.",
        reply_markup=menu(q.from_user.id),
    )


async def role_change_cb(update, context):
    # Compatibility route for old keyboards; role switching has been retired.
    q = update.callback_query
    await q.answer()
    if not await _require_registered(q):
        return
    set_user_role(q.from_user.id, 'lawyer')
    await q.message.reply_text(
        "⚖️ تغییر نقش غیرفعال است؛ این نسخه فقط برای وکلاست.",
        reply_markup=menu(q.from_user.id),
    )


async def _brief_run_information_resolver(msg, context, uid, facts=''):
    """V150: resolve missing case information locally before source selection."""
    cid=context.user_data.get('brief_case_id')
    brief_type=context.user_data.get('brief_type','لایحه دفاعیه')
    template_key=context.user_data.get('brief_template_key','')
    facts=(facts or '').strip()
    answers=context.user_data.get('brief_v150_answers') or {}
    resolver=await asyncio.to_thread(resolve_case_information, uid, cid, brief_type, facts, template_key, answers)
    deferred=set(context.user_data.get('brief_v150_deferred') or set())
    if deferred:
        for item in resolver.get('items') or []:
            if item.get('key') in deferred:
                item['status']='missing'; item['value']=''; item['confirmed_by_user']=False
                item.setdefault('notes',[]).append('وکیل فعلاً پاسخ این مورد را نمی‌داند؛ این مورد fact محسوب نمی‌شود.')
        resolver['questions']=[q for q in resolver.get('questions') or [] if q.get('key') not in deferred]
        resolver['required_missing']=sum(1 for x in resolver.get('items') or [] if x.get('importance')=='required' and x.get('status') in {'missing','conflict'})
        resolver['ready_for_review']=resolver['required_missing']==0 and not any(x.get('status')=='conflict' and x.get('importance')=='required' for x in resolver.get('items') or [])
    context.user_data['brief_v150_resolver']=resolver
    context.user_data['brief_v150_facts']=facts
    questions=resolver.get('questions') or []
    rows=[]
    if questions:
        rows.append([InlineKeyboardButton('✍️ پاسخ به مورد اول', callback_data='brief:info:answer')])
        rows.append([InlineKeyboardButton('🤷 نمی‌دانم / فعلاً رد کن', callback_data='brief:info:unknown')])
    rows.append([InlineKeyboardButton('🔄 بررسی دوباره پرونده', callback_data='brief:info:refresh')])
    if resolver.get('ready_for_review'):
        rows.append([InlineKeyboardButton('✅ تأیید اطلاعات و ادامه', callback_data='brief:info:confirm')])
    else:
        rows.append([InlineKeyboardButton('▶️ ادامه با اطلاعات فعلی', callback_data='brief:info:confirm')])
    await reply_long(msg, format_information_map(resolver))
    await msg.reply_text('V150 فقط از اطلاعات محلی پرونده و ورودی شما استفاده کرد؛ هیچ API خارجی در این مرحله فراخوانی نشد.', reply_markup=InlineKeyboardMarkup(rows))


def _brief_v150_context(context):
    base=(context.user_data.get('brief_v150_facts') or '').strip()
    answers=context.user_data.get('brief_v150_answers') or {}
    extra=[]
    for key,value in answers.items():
        if str(value).strip():
            extra.append(f'{key}: {value}')
    return '\n'.join(x for x in [base, *extra] if x).strip()


async def brief_information_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_lawyer(q, context, 'briefs'): return
    action=q.data.split(':')[-1]
    resolver=context.user_data.get('brief_v150_resolver') or {}
    questions=resolver.get('questions') or []
    if action == 'answer':
        if not questions:
            await q.message.reply_text('مورد ضروری دیگری برای پاسخ‌گویی وجود ندارد.')
            return
        question=questions[0]
        context.user_data['brief_v150_question_key']=question.get('key')
        context.user_data['brief_v150_question_label']=question.get('label')
        context.user_data['brief_v150_waiting_answer']=True
        await q.message.reply_text('✍️ '+question.get('question','لطفاً اطلاعات این مورد را وارد کنید.')+'\n\nاگر نمی‌دانید، بنویسید: «نمی‌دانم»')
        return
    if action == 'unknown':
        if not questions:
            return
        key=questions[0].get('key')
        context.user_data.setdefault('brief_v150_deferred', set()).add(key)
        # Unknown is deliberately not stored as a fact. Keep the item missing
        # and record the lawyer's explicit decision to defer it.
        items=[]
        for item in resolver.get('items') or []:
            item=dict(item)
            if item.get('key')==key:
                item['status']='missing'; item['value']=''; item['confirmed_by_user']=False
                item.setdefault('notes',[]).append('وکیل فعلاً اطلاعات این مورد را نمی‌داند؛ این مورد واقعیت تلقی نمی‌شود.')
            items.append(item)
        resolver=dict(resolver); resolver['items']=items; resolver['questions']=questions[1:]
        context.user_data['brief_v150_resolver']=resolver
        await _brief_run_information_resolver(q.message, context, q.from_user.id, _brief_v150_context(context))
        return
    if action == 'refresh':
        await _brief_run_information_resolver(q.message, context, q.from_user.id, _brief_v150_context(context))
        return
    if action == 'confirm':
        facts=_brief_v150_context(context)
        context.user_data['brief_facts_value']=facts
        context.user_data['brief_v150_confirmed']=True
        await q.message.reply_text('✅ نقشه اطلاعاتی تأیید شد. حالا منابع حقوقی موجود بررسی می‌شوند؛ انتخاب منابع همچنان با تأیید شماست.')
        await _brief_prepare_sources(q.message, context, q.from_user.id, facts)
        return


async def _generate_brief_from_state(msg, context, uid, facts=''):
    """Final generation step after the interactive source/gap workflow."""
    brief_type=context.user_data.get('brief_type','لایحه دفاعیه')
    brief_mode=context.user_data.get('brief_mode','new')
    cid=context.user_data.get('brief_case_id')
    case_text=get_case_text(uid,cid) if cid else ''
    if cid:
        try: set_active_case(uid,cid)
        except Exception: pass
    stage_map={'لایحه تجدیدنظرخواهی':'تجدیدنظر','پاسخ به لایحه طرف مقابل':'نامشخص'}
    brief_stage=context.user_data.get('brief_stage',stage_map.get(brief_type,'نامشخص'))
    selected=context.user_data.get('brief_selected_sources',[])
    template_key=context.user_data.get('brief_template_key')
    facts=(facts or '').strip()
    sources=selected
    try:
        if brief_mode == 'edit':
            review=await asyncio.to_thread(review_brief, facts, sources)
            revised=await asyncio.to_thread(build_brief, facts, brief_type, brief_stage, sources, '', 'edit', template_key)
            result=review+'\n\n'+'═'*24+'\n\n✍️ نسخه پیشنهادی بازتنظیم‌شده\n\n'+revised
        else:
            result=await asyncio.to_thread(build_brief, facts, brief_type, brief_stage, sources, case_text, brief_mode, template_key)
            quick_review=await asyncio.to_thread(review_brief, result, sources)
            result += '\n\n'+'═'*24+'\n\n'+quick_review
        if not result: raise RuntimeError('پیش‌نویس خالی بود')
    except Exception:
        logger.exception('brief draft failed for user=%s', uid)
        await msg.reply_text('❌ پیش‌نویس تولید نشد. لطفاً دوباره تلاش کنید.')
        return
    # Keep the clean draft separate from the review block so editing/exporting
    # never accidentally treats the review as part of the legal text.
    if brief_mode == 'edit' and '═'*24 in result:
        clean_result = result.split('═'*24, 1)[1].strip()
    else:
        clean_result = result.split('═'*24, 1)[0].strip() if '═'*24 in result else result.strip()
    clean_result = add_inline_citations(clean_result, sources)
    context.user_data['brief_manual_edits']=False
    context.user_data['brief_lifecycle']='draft'
    remember_version(context.user_data, clean_result, 'پیش‌نویس اولیه' if not context.user_data.get('brief_versions') else 'بازسازی')
    await reply_long(msg, clean_result)
    await msg.reply_text(
        '⚠️ این متن پیش‌نویس داخلی است. استنادات، ارقام، وقایع و انطباق کامل با پرونده باید توسط وکیل بازبینی شود.',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton('✏️ ویرایش سریع', callback_data='brief:editprompt'), InlineKeyboardButton('🔎 بررسی', callback_data='brief:review')],
            [InlineKeyboardButton('📚 منابع', callback_data='brief:sources'), InlineKeyboardButton('📄 Word', callback_data='brief:word'), InlineKeyboardButton('📑 PDF', callback_data='brief:pdf')],
            [InlineKeyboardButton('🧰 میزکار', callback_data='brief:workspace'), InlineKeyboardButton('🔄 بازسازی', callback_data='brief:regenerate')],
            [InlineKeyboardButton('🕘 تاریخچه', callback_data='brief:history')],
            [InlineKeyboardButton('🏠 منوی اصلی',callback_data='home')]
        ])
    )


async def _brief_prepare_sources(msg, context, uid, facts='', add_to_existing=False):
    """Find candidate sources and ask the lawyer to explicitly approve them."""
    brief_type=context.user_data.get('brief_type','لایحه دفاعیه')
    mode=context.user_data.get('brief_mode','new')
    cid=context.user_data.get('brief_case_id')
    case_text=get_case_text(uid,cid) if cid else ''
    query=(facts.strip() + '\n' + case_text[:14000]).strip()
    candidates=await asyncio.to_thread(law_search, query, 8) if query else []
    existing=list(context.user_data.get('brief_selected_sources') or []) if add_to_existing else []
    if existing and candidates:
        keys={str((x.get('citation') or {}).get('id') or x.get('article') or x.get('ruling_number') or x.get('title') or x.get('law') or '') for x in existing}
        candidates=[c for c in candidates if str((c.get('citation') or {}).get('id') or c.get('article') or c.get('ruling_number') or c.get('title') or c.get('law') or '') not in keys]
    context.user_data['brief_facts_value']=facts.strip()
    context.user_data['brief_candidates']=candidates
    context.user_data['brief_selected_indices']=set()
    context.user_data['brief_add_to_existing']=bool(add_to_existing)
    summary=brief_case_summary(query)
    gaps=detect_brief_gaps(facts, brief_type, case_text, context.user_data.get('brief_template_key',''))
    lines=['📝 بررسی اولیه برای تنظیم لایحه','',f'نوع: {brief_type}',f'مرحله: {context.user_data.get("brief_stage","نامشخص")}','', '📌 خلاصه اطلاعات ورودی:', summary]
    if gaps:
        lines += ['', '⚠️ اطلاعاتی که فعلاً در متن پیدا نشد:'] + [f'• {g}' for g in gaps]
        lines.append('این موارد مانع انتخاب منابع نیستند؛ قبل از نسخه نهایی بهتر است تکمیل شوند.')
    lines += ['', '📚 منابع پیشنهادی — هنوز هیچ‌کدام به‌صورت خودکار تأیید نشده‌اند:']
    if not candidates:
        lines.append('• منبع کافی برای عبارت واردشده پیدا نشد. می‌توانید موضوع/خواسته را دقیق‌تر وارد کنید.')
    else:
        for i,src in enumerate(candidates,1):
            lines.append(f'☐ {source_label(src,i)}')
    buttons=[]
    for i,src in enumerate(candidates,1):
        title=str(src.get('law') or src.get('title') or src.get('name') or 'منبع')[:24]
        buttons.append(InlineKeyboardButton(f'☐ {i} {title}',callback_data=f'briefsrc:{i}'))
    rows=[buttons[i:i+2] for i in range(0,len(buttons),2)]
    selected=context.user_data.get('brief_selected_indices') or set()
    count=len(selected)
    rows.append([InlineKeyboardButton(f'✅ تأیید منابع انتخاب‌شده ({count})',callback_data='briefsrc:done')])
    rows.append([InlineKeyboardButton('🔎 جستجوی دوباره',callback_data='brief:research')])
    rows.append([InlineKeyboardButton('↩️ لایحه‌نویسی',callback_data='briefs')])
    await reply_long(msg,'\n'.join(lines))
    await msg.reply_text('برای ورود هر منبع به پیش‌نویس، آن را انتخاب کنید؛ سپس «تأیید منابع» را بزنید.',reply_markup=InlineKeyboardMarkup(rows))


async def brief_source_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_lawyer(q, context, 'briefs'): return
    data=q.data.split(':',1)[1]
    candidates=context.user_data.get('brief_candidates') or []
    selected=context.user_data.setdefault('brief_selected_indices',set())
    if data == 'done':
        if not selected:
            await q.answer('حداقل یک منبع را انتخاب کنید یا از جستجوی دوباره استفاده کنید.', show_alert=True)
            return
        chosen=[candidates[i] for i in sorted(selected) if 0 <= i < len(candidates)]
        if context.user_data.get('brief_add_to_existing'):
            prior=list(context.user_data.get('brief_selected_sources') or [])
            keys={str((x.get('citation') or {}).get('id') or x.get('article') or x.get('ruling_number') or x.get('title') or x.get('law') or '') for x in prior}
            chosen=prior + [x for x in chosen if str((x.get('citation') or {}).get('id') or x.get('article') or x.get('ruling_number') or x.get('title') or x.get('law') or '') not in keys]
        context.user_data['brief_selected_sources']=chosen
        context.user_data['brief_add_to_existing']=False
        facts=context.user_data.get('brief_facts_value','')
        gaps=detect_brief_gaps(facts,context.user_data.get('brief_type',''),get_case_text(q.from_user.id,context.user_data.get('brief_case_id')) if context.user_data.get('brief_case_id') else '',context.user_data.get('brief_template_key',''))
        if gaps:
            context.user_data['brief_gap_followup']=True
            await q.message.reply_text('📋 منابع تأیید شد. برای تکمیل پیش‌نویس، فقط این موارد را در یک پیام وارد کنید:\n\n'+'\n'.join(f'• {g}' for g in gaps))
            return
        await _generate_brief_from_state(q.message,context,q.from_user.id,facts)
        return
    try: idx=int(data)-1
    except Exception: return
    if not (0 <= idx < len(candidates)): return
    if idx in selected: selected.remove(idx)
    else: selected.add(idx)
    marks=[]
    buttons=[]
    for i,src in enumerate(candidates,1):
        mark='☑' if i-1 in selected else '☐'
        marks.append(f'{mark} {source_label(src,i)}')
        title=str(src.get('law') or src.get('title') or src.get('name') or 'منبع')[:24]
        buttons.append(InlineKeyboardButton(f'{mark} {i} {title}',callback_data=f'briefsrc:{i}'))
    rows=[buttons[i:i+2] for i in range(0,len(buttons),2)]
    count=len(selected)
    rows.append([InlineKeyboardButton(f'✅ تأیید منابع انتخاب‌شده ({count})',callback_data='briefsrc:done')])
    rows.append([InlineKeyboardButton('🔎 جستجوی دوباره',callback_data='brief:research')])
    await q.message.edit_text('📚 انتخاب منابع\n\n'+'\n'.join(marks)+'\n\nمنابع انتخاب‌شده فقط پس از تأیید وارد پیش‌نویس می‌شوند.',reply_markup=InlineKeyboardMarkup(rows))



async def brief_workspace_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_lawyer(q, context, 'briefs'): return
    if not current_text(context.user_data):
        await q.message.reply_text('هنوز پیش‌نویس فعالی ندارید.', reply_markup=brief_menu()); return
    await q.message.reply_text(
        '🧰 میزکار لایحه\n\n'
        'دستور خود را مستقیم بنویسید؛ نسخه‌ها خودکار ذخیره می‌شوند.\n\n'
        'مثال‌ها:\n'
        '• دفاعیات: متن جدید...\n'
        '• شرح ماوقع: متن جدید...\n'
        '• بخش خواسته را حذف کن\n'
        '• متن را کوتاه کن\n\n'
        'تغییر حقوقی جدید بدون متن صریح شما از طرف موتور ساخته نمی‌شود.',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton('✏️ ویرایش', callback_data='brief:editprompt'), InlineKeyboardButton('🔎 بررسی', callback_data='brief:review')],
            [InlineKeyboardButton('🧠 درک پرونده', callback_data='brief:understanding'), InlineKeyboardButton('⚔️ نقشه استدلال', callback_data='brief:arguments')],
            [InlineKeyboardButton('🧩 تحلیل خلأ', callback_data='brief:gaps'), InlineKeyboardButton('⚠️ تناقضات', callback_data='brief:consistency')],
            [InlineKeyboardButton('⚔️ پاسخ به لایحه طرف مقابل', callback_data='brief:opposing')],
            [InlineKeyboardButton('🧩 ویرایش بخش', callback_data='brief:sections'), InlineKeyboardButton('📚 منابع', callback_data='brief:sources')],
            [InlineKeyboardButton('🕘 تاریخچه', callback_data='brief:history'), InlineKeyboardButton('📊 مقایسه', callback_data='brief:compare')],
            [InlineKeyboardButton('🧹 پاکسازی', callback_data='brief:cleanup'), InlineKeyboardButton('🧪 کنترل نهایی', callback_data='brief:finalcheck')],
            [InlineKeyboardButton('📄 Word', callback_data='brief:word'), InlineKeyboardButton('📑 PDF', callback_data='brief:pdf')],
        ])
    )

async def brief_sections_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_lawyer(q, context, 'briefs'): return
    text=current_text(context.user_data)
    if not text:
        await q.message.reply_text('پیش‌نویس فعالی ندارید.'); return
    import re as _re
    heads=[]
    for m in _re.finditer(r'(?m)^\s*(\d+)\)\s*(.+)$', text):
        title=m.group(2).strip()
        if len(title)>60: title=title[:60]
        heads.append((m.group(1), title))
    rows=[[InlineKeyboardButton(f'✏️ {n}) {t}', callback_data=f'briefsec:{n}')] for n,t in heads[:12]]
    rows.append([InlineKeyboardButton('↩️ میزکار', callback_data='brief:workspace')])
    await q.message.reply_text('🧩 بخش موردنظر برای ویرایش را انتخاب کنید.\n\nبعد از انتخاب، متن جدید همان بخش را ارسال کنید.', reply_markup=InlineKeyboardMarkup(rows))

async def brief_section_edit_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_lawyer(q, context, 'briefs'): return
    try: num=int(q.data.split(':')[1])
    except Exception: return
    context.user_data['brief_section_edit_number']=num
    await q.message.reply_text(f'✏️ متن جدید بخش {num} را کامل ارسال کنید.\n\nفقط همان بخش جایگزین می‌شود و سایر بخش‌ها دست‌نخورده می‌مانند.')

def _replace_numbered_section(text: str, number: int, replacement: str) -> str:
    import re as _re
    # Accept Latin, Persian and Arabic-Indic section numbers so editing remains
    # stable even when a copied draft uses a different numeral system.
    digits = '۰۱۲۳۴۵۶۷۸۹'
    arabic = '٠١٢٣٤٥٦٧٨٩'
    ascii_n = str(int(number))
    fa_n = ''.join(digits[int(ch)] for ch in ascii_n)
    ar_n = ''.join(arabic[int(ch)] for ch in ascii_n)
    num_pat = f'(?:{_re.escape(ascii_n)}|{_re.escape(fa_n)}|{_re.escape(ar_n)})'
    pat=_re.compile(rf'(?ms)^\s*{num_pat}\)\s*[^\n]*\n.*?(?=^\s*\d+\)\s|^\s*─{{8,}}|\Z)')
    m=pat.search(text)
    if not m: return text
    heading=text[m.start():text.find('\n',m.start())]
    return text[:m.start()] + heading + '\n' + replacement.strip() + '\n\n' + text[m.end():]

async def brief_compare_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_lawyer(q, context, 'briefs'): return
    versions=context.user_data.get('brief_versions') or []
    if len(versions)<2:
        await q.message.reply_text('برای مقایسه حداقل دو نسخه لازم است.')
        return
    try:
        parts=q.data.split(':')
        requested=int(parts[1]) if q.data.startswith('briefcompare:') and len(parts) == 2 else None
    except Exception:
        requested=None
    active=current_text(context.user_data)
    if requested is not None and get_version(context.user_data, requested) is None:
        await q.message.reply_text('نسخه انتخاب‌شده دیگر در تاریخچه موجود نیست.')
        return
    if requested is not None and get_version(context.user_data, requested) and get_version(context.user_data, requested).get('text','') == active:
        await q.message.reply_text('این نسخه همان نسخه فعال است و تفاوت متنی با خودش ندارد.')
        return
    base=requested if requested is not None else versions[-2].get('version')
    diff=compare_versions(context.user_data, int(base))
    await reply_long(q.message, f'📊 مقایسه V{base} با نسخه فعال\n\n{diff}')


async def brief_understanding_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_lawyer(q, context, 'briefs'): return
    text=(context.user_data.get('brief_facts_value') or '')
    cid=context.user_data.get('brief_case_id')
    if cid: text=(get_case_text(q.from_user.id,cid) or '') + '\n' + text
    if not text.strip(): text=current_text(context.user_data)
    u=await asyncio.to_thread(brief_case_understanding,text)
    lines=['🧠 درک اولیه پرونده','', 'این صفحه فقط اطلاعات صریح متن را استخراج می‌کند و نتیجه حقوقی قطعی نمی‌دهد.']
    for title,key in [('👥 طرفین/سمت‌ها','parties'),('🎯 ادعاها و خواسته‌ها','claims'),('📎 ادله و مستندات','evidence'),('📅 تاریخ‌ها و مهلت‌ها','dates'),('📚 ارجاعات قانونی','refs')]:
        lines += ['',title]
        vals=u.get(key) or []
        lines += [f'• {x}' for x in vals[:5]] if vals else ['• در متن استخراج‌شده پیدا نشد.']
    lines += ['', '⚠️ موارد نیازمند تکمیل'] + ([f'• {x}' for x in u['missing']] if u['missing'] else ['• مورد آشکارِ ناقص پیدا نشد.'])
    await reply_long(q.message,'\n'.join(lines))

async def brief_argument_map_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_lawyer(q, context, 'briefs'): return
    text=current_text(context.user_data) or context.user_data.get('brief_facts_value','')
    rows=await asyncio.to_thread(argument_matrix,text,context.user_data.get('brief_selected_sources',[]))
    if not rows:
        await q.message.reply_text('هنوز ادعای صریحی برای ساخت نقشه استدلال پیدا نشد.')
        return
    lines=['⚔️ ماتریس استدلال لایحه','',
           'زنجیره هر ادعا: واقعیت → دلیل → قاعده → اعمال قاعده → خواسته.']
    for r in rows:
        lines += [f"{r['id']}) ادعا: {r['claim']}",
                  f"   📌 واقعیت: {r['fact'] or 'ثبت نشده'}",
                  f"   📎 دلیل: {' | '.join(r['evidence'][:2]) if r['evidence'] else 'ثبت نشده'}",
                  f"   ⚖️ قاعده: {r['rule'] or 'ثبت نشده'}",
                  f"   🔗 اعمال قاعده: {r['application'] or 'نیازمند توضیح کاربر'}",
                  f"   🎯 خواسته: {r['request'] or 'ثبت نشده'}",
                  f"   📚 منبع: {' '.join(r['citations']) if r['citations'] else 'ثبت نشده'}",
                  f"   وضعیت: {r['status']}"]
        if r.get('gaps'):
            lines.append('   ⚠️ خلأ: ' + '، '.join(r['gaps']))
        lines.append('')
    await reply_long(q.message,'\n'.join(lines))
    await q.message.reply_text(
        'این ماتریس فقط ارتباط‌های قابل استخراج از متن را نشان می‌دهد. خانه «اعمال قاعده» عمداً خودکار پر نمی‌شود؛ این بخش نیازمند استدلال و بازبینی حقوقی است.',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🔎 بررسی',callback_data='brief:review'),InlineKeyboardButton('🧪 کنترل نهایی',callback_data='brief:finalcheck')],[InlineKeyboardButton('🧰 میزکار',callback_data='brief:workspace')]])
    )

async def brief_opposing_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_lawyer(q, context, 'briefs'): return
    context.user_data['brief_opposing_text_input']=True
    await q.message.reply_text(
        '⚔️ پاسخ به لایحه طرف مقابل\n\n'
        'متن کامل لایحه طرف مقابل را ارسال کنید.\n'
        'سیستم ادعاهای صریح آن را استخراج می‌کند و برای هر ادعا، محل پاسخ، دلیل و مستند را مشخص می‌کند.\n\n'
        '⚠️ پاسخ حقوقی از طرف سیستم حدس زده نمی‌شود؛ موارد استخراج‌شده برای تأیید و تکمیل شما نمایش داده می‌شوند.'
    )

async def brief_opposing_result_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_lawyer(q, context, 'briefs'): return
    text=context.user_data.get('brief_opposing_text','')
    rows=opposing_response_matrix(text, context.user_data.get('brief_facts_value',''), context.user_data.get('brief_selected_sources',[]))
    if not rows:
        await q.message.reply_text('ادعای صریح قابل استخراجی پیدا نشد؛ متن لایحه طرف مقابل را بررسی و در صورت نیاز دستی وارد کنید.')
        return
    lines=['⚔️ جدول پاسخ به لایحه طرف مقابل','']
    for r in rows:
        lines += [f"{r['id']}) ادعای طرف مقابل: {r['claim']}",
                  f"   ↩️ پاسخ ما: {'هنوز ثبت نشده'}",
                  f"   📎 دلیل موجود: {' | '.join(r['evidence']) if r['evidence'] else 'ثبت نشده'}",
                  f"   📚 مستند: {' '.join(r['citations']) if r['citations'] else 'ثبت نشده'}",
                  f"   وضعیت: {r['status']}", '']
    await reply_long(q.message,'\n'.join(lines))
    await q.message.reply_text(
        'برای تکمیل پاسخ، می‌توانید هر بند را به‌صورت «پاسخ ۱: ...» ارسال کنید.\n'
        'این جدول هنوز پیش‌نویس لایحه نیست و قبل از ورود به متن نهایی نیاز به بازبینی دارد.',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton('✏️ ثبت پاسخ‌ها',callback_data='brief:opposing_edit'), InlineKeyboardButton('📝 ساخت اسکلت پاسخ',callback_data='brief:opposing_outline')],
            [InlineKeyboardButton('🧩 نقشه استدلال',callback_data='brief:arguments'), InlineKeyboardButton('📚 منابع',callback_data='brief:sources')],
            [InlineKeyboardButton('🧪 کنترل نهایی',callback_data='brief:finalcheck'), InlineKeyboardButton('🧰 میزکار',callback_data='brief:workspace')]
        ]))

async def brief_opposing_edit_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_lawyer(q, context, 'briefs'): return
    context.user_data['brief_opposing_response_input']=True
    await q.message.reply_text('✏️ پاسخ‌ها را به این شکل ارسال کنید:\n\nپاسخ ۱: متن پاسخ شما\nپاسخ ۲: متن پاسخ شما\n\nفقط پاسخ‌هایی که صریحاً وارد کنید در جدول ثبت می‌شوند.')

async def brief_opposing_outline_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_lawyer(q, context, 'briefs'): return
    rows=opposing_response_matrix(context.user_data.get('brief_opposing_text',''), context.user_data.get('brief_facts_value',''), context.user_data.get('brief_selected_sources',[]))
    rows=apply_opposing_responses(rows, context.user_data.get('brief_opposing_responses',''))
    if not rows:
        await q.message.reply_text('ابتدا متن لایحه طرف مقابل را وارد کنید.')
        return
    await reply_long(q.message, opposing_response_outline(rows))
    await q.message.reply_text('اگر می‌خواهید این اسکلت به انتهای پیش‌نویس فعلی اضافه شود، از دکمه زیر استفاده کنید؛ متن موجود جایگزین نمی‌شود.', reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton('➕ افزودن به لایحه فعلی', callback_data='brief:opposing_apply')],
        [InlineKeyboardButton('🧰 میزکار', callback_data='brief:workspace')]
    ]))

async def brief_opposing_apply_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_lawyer(q, context, 'briefs'): return
    rows=opposing_response_matrix(context.user_data.get('brief_opposing_text',''), context.user_data.get('brief_facts_value',''), context.user_data.get('brief_selected_sources',[]))
    rows=apply_opposing_responses(rows, context.user_data.get('brief_opposing_responses',''))
    if not rows:
        await q.message.reply_text('ابتدا متن لایحه طرف مقابل را وارد و ادعاها را استخراج کنید.')
        return
    old=current_text(context.user_data)
    outline=opposing_response_outline(rows)
    new=(old.rstrip()+'\n\n'+outline).strip() if old else outline
    new=add_inline_citations(new, context.user_data.get('brief_selected_sources',[]))
    context.user_data['brief_manual_edits']=True
    context.user_data['brief_lifecycle']='review'
    remember_version(context.user_data,new,'افزودن پاسخ به لایحه طرف مقابل')
    await reply_long(q.message,new)
    await q.message.reply_text('✅ اسکلت پاسخ به انتهای پیش‌نویس اضافه شد. متن قبلی جایگزین نشد؛ پیش از خروجی، بررسی و تکمیل کنید.', reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton('🔎 بررسی', callback_data='brief:review'), InlineKeyboardButton('🧩 تحلیل خلأ', callback_data='brief:gaps')],
        [InlineKeyboardButton('⚠️ تناقضات', callback_data='brief:consistency'), InlineKeyboardButton('🧰 میزکار', callback_data='brief:workspace')]
    ]))

async def brief_gap_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_lawyer(q, context, 'briefs'): return
    text=current_text(context.user_data)
    if not text:
        await q.message.reply_text('پیش‌نویسی برای تحلیل خلأ وجود ندارد.')
        return
    case_text=get_case_text(q.from_user.id,context.user_data.get('brief_case_id')) if context.user_data.get('brief_case_id') else ''
    report=await asyncio.to_thread(brief_gap_analysis, text, case_text, context.user_data.get('brief_selected_sources',[]), context.user_data.get('brief_type',''), context.user_data.get('brief_template_key',''), context.user_data.get('brief_opposing_text',''))
    context.user_data['brief_gap_report']=report
    await q.message.reply_text(format_gap_analysis(report), reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton('🧩 نقشه استدلال',callback_data='brief:arguments'), InlineKeyboardButton('⚠️ تناقضات',callback_data='brief:consistency')],
        [InlineKeyboardButton('✏️ اصلاح',callback_data='brief:editprompt'), InlineKeyboardButton('🧪 کنترل نهایی',callback_data='brief:finalcheck')],
        [InlineKeyboardButton('🧰 میزکار',callback_data='brief:workspace')]
    ]))

async def brief_finalcheck_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_lawyer(q, context, 'briefs'): return
    text=current_text(context.user_data)
    if not text: await q.message.reply_text('پیش‌نویسی برای کنترل نهایی وجود ندارد.'); return
    sources=context.user_data.get('brief_selected_sources',[])
    result=validate_brief(text,sources)
    case_text=get_case_text(q.from_user.id,context.user_data.get('brief_case_id')) if context.user_data.get('brief_case_id') else ''
    gap_report=await asyncio.to_thread(brief_gap_analysis, text, case_text, sources, context.user_data.get('brief_type',''), context.user_data.get('brief_template_key',''), context.user_data.get('brief_opposing_text',''))
    context.user_data['brief_gap_report']=gap_report
    checks=[('موضوع',result['has_topic']),('خواسته/تقاضا',result['has_request']),('مرجع',result['has_authority']),('ادله',result['has_evidence'])]
    lines=['🧪 کنترل نهایی لایحه','']+[('✅ ' if ok else '⚠️ ')+label for label,ok in checks]
    lines += [f"📚 تعداد Citation: {result['citation_count']}"]
    if result['invalid_citations']: lines.append('⚠️ Citation نامعتبر: '+', '.join(f'C{x}' for x in result['invalid_citations']))
    if result['unused_sources']: lines.append('ℹ️ منابع انتخاب‌شده بدون Citation مستقیم: '+', '.join(f'C{x}' for x in result['unused_sources']))
    if result['placeholder']: lines.append('⚠️ جای‌خالی یا placeholder در متن باقی مانده است.')
    if result['overconfident']: lines.append('⚠️ عبارت نتیجه‌محور/قطعی نیازمند بازبینی است.')
    if gap_report['items']: lines.append(f"🧩 خلأهای مهم: {gap_report['count']} مورد ({gap_report['high']} پرریسک)")
    if gap_report.get('consistency',{}).get('findings'):
        lines.append(f"⚠️ تناقضات قابل بررسی: {gap_report['consistency']['count']} مورد")
    if context.user_data.get('brief_manual_edits'):
        lines.append('✏️ این نسخه شامل ویرایش دستی است؛ بازسازی کامل می‌تواند تغییرات دستی را جایگزین کند.')
    if not any([result['placeholder'],result['invalid_citations'],result['overconfident']]) and all(x[1] for x in checks) and not gap_report['high']:
        context.user_data['brief_lifecycle']='ready'
        lines += ['', '🟢 وضعیت: آماده خروجی پس از بازبینی وکیل.']
    else:
        context.user_data['brief_lifecycle']='review'
        lines += ['', '🟠 وضعیت: نیازمند بازبینی/تکمیل.']
    await q.message.reply_text('\n'.join(lines),reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton('✏️ اصلاح',callback_data='brief:editprompt'),InlineKeyboardButton('🧩 تحلیل خلأ',callback_data='brief:gaps'),InlineKeyboardButton('🔎 بررسی',callback_data='brief:review')],
        [InlineKeyboardButton('📄 Word + منابع',callback_data='brief:word'),InlineKeyboardButton('📑 PDF',callback_data='brief:pdf')]
    ]))

async def brief_consistency_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_lawyer(q, context, 'briefs'): return
    text=current_text(context.user_data)
    if not text:
        await q.message.reply_text('پیش‌نویسی برای کنترل تناقضات وجود ندارد.')
        return
    case_text=get_case_text(q.from_user.id,context.user_data.get('brief_case_id')) if context.user_data.get('brief_case_id') else ''
    report=await asyncio.to_thread(brief_consistency_check, text, case_text)
    context.user_data['brief_consistency_report']=report
    await q.message.reply_text(format_consistency_report(report), reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton('🔎 بررسی کامل',callback_data='brief:review'), InlineKeyboardButton('✏️ اصلاح',callback_data='brief:editprompt')],
        [InlineKeyboardButton('🧪 کنترل نهایی',callback_data='brief:finalcheck'), InlineKeyboardButton('🧰 میزکار',callback_data='brief:workspace')]
    ]))


async def brief_cleanup_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_lawyer(q, context, 'briefs'): return
    text=current_text(context.user_data)
    if not text: await q.message.reply_text('پیش‌نویسی برای پاکسازی وجود ندارد.'); return
    new=cleanup_brief_text(text); new=add_inline_citations(new,context.user_data.get('brief_selected_sources',[]))
    if new==text:
        await q.message.reply_text('پاکسازی تغییری در متن ایجاد نکرد.')
        return
    context.user_data['brief_manual_edits']=True
    context.user_data['brief_lifecycle']='review'
    remember_version(context.user_data,new,'پاکسازی نگارشی/نمایشی')
    await reply_long(q.message,new)
    await q.message.reply_text('✅ فقط پاکسازی نمایشی/نگارشی انجام شد؛ محتوای حقوقی بازنویسی نشد.',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🧪 کنترل نهایی',callback_data='brief:finalcheck'),InlineKeyboardButton('🧰 میزکار',callback_data='brief:workspace')]]))

async def brief_regenerate_confirm_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_lawyer(q, context, 'briefs'): return
    await q.message.reply_text('⚠️ این لایحه ویرایش دستی دارد. بازسازی کامل می‌تواند تغییرات دستی را جایگزین کند.',reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton('🔄 بازسازی کامل',callback_data='briefregen:force')],[InlineKeyboardButton('↩️ انصراف',callback_data='brief:workspace')]
    ]))

async def brief_review_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_lawyer(q, context, 'briefs'): return
    text=current_text(context.user_data)
    if not text:
        await q.message.reply_text('پیش‌نویس فعالی برای بررسی نیست.'); return
    review=await asyncio.to_thread(review_brief, text, context.user_data.get('brief_selected_sources',[]))
    case_text = get_case_text(q.from_user.id,context.user_data.get('brief_case_id')) if context.user_data.get('brief_case_id') else ''
    consistency = await asyncio.to_thread(brief_consistency_check, text, case_text)
    context.user_data['brief_consistency_report'] = consistency
    gaps=detect_brief_gaps(context.user_data.get('brief_facts_value',''), context.user_data.get('brief_type',''), case_text, context.user_data.get('brief_template_key',''))
    extra=[]
    if gaps: extra += ['📋 کمبودهای اطلاعاتی:', *[f'• {x}' for x in gaps]]
    consistency_text = format_consistency_report(consistency)
    await q.message.reply_text('🔎 بررسی لایحه\n\n'+review+('\n\n'+'\n'.join(extra) if extra else '')+'\n\n'+consistency_text, reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton('✏️ اصلاح', callback_data='brief:editprompt'), InlineKeyboardButton('🧩 تحلیل خلأ', callback_data='brief:gaps'), InlineKeyboardButton('⚠️ تناقضات', callback_data='brief:consistency')],
        [InlineKeyboardButton('📚 منابع', callback_data='brief:sources')],
        [InlineKeyboardButton('📄 Word', callback_data='brief:word'), InlineKeyboardButton('📑 PDF', callback_data='brief:pdf'), InlineKeyboardButton('🕘 تاریخچه', callback_data='brief:history')]
    ]))

async def brief_sources_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_lawyer(q, context, 'briefs'): return
    selected=context.user_data.get('brief_selected_sources') or []
    if not selected:
        await q.message.reply_text('هنوز منبع تأییدشده‌ای برای این لایحه انتخاب نشده است.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🔎 جستجوی منابع', callback_data='brief:research')]])); return
    lines=['📚 منابع تأییدشده لایحه','']
    rows=[]
    for i,s in enumerate(selected,1):
        lines.append(f'{i}. {source_label(s,i)}')
        title=str(s.get('law') or s.get('title') or s.get('name') or 'منبع')[:24]
        rows.append([InlineKeyboardButton(f'❌ حذف {i} — {title}', callback_data=f'briefsrcdel:{i}')])
    rows += [[InlineKeyboardButton('➕ افزودن/جستجوی منبع', callback_data='brief:research')],
             [InlineKeyboardButton('✏️ ویرایش لایحه', callback_data='brief:editprompt'), InlineKeyboardButton('🔎 بررسی', callback_data='brief:review')]]
    await q.message.reply_text('\n'.join(lines), reply_markup=InlineKeyboardMarkup(rows))

async def brief_source_delete_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_lawyer(q, context, 'briefs'): return
    try: idx=int(q.data.split(':')[1])-1
    except Exception: return
    selected=context.user_data.get('brief_selected_sources') or []
    if not (0 <= idx < len(selected)):
        await q.message.reply_text('منبع پیدا نشد.'); return
    removed=selected.pop(idx)
    context.user_data['brief_selected_sources']=selected
    title=str(removed.get('law') or removed.get('title') or removed.get('name') or 'منبع')
    # Re-map citation markers immediately so the active draft never points to
    # a deleted/reordered source. The legal text itself is not regenerated.
    old_text=current_text(context.user_data)
    if old_text:
        remapped=add_inline_citations(old_text, selected)
        if remapped != old_text:
            remember_version(context.user_data, remapped, 'اصلاح استناد پس از حذف منبع')
    if not selected:
        await q.message.reply_text('آخرین منبع حذف شد. برای تولید نسخه مستند، حداقل یک منبع باید انتخاب شود.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('➕ افزودن منبع', callback_data='brief:research')]])); return
    lines=[f'{i}. {source_label(s,i)}' for i,s in enumerate(selected,1)]
    rows=[[InlineKeyboardButton(f'❌ حذف {i} — {str(s.get("law") or s.get("title") or s.get("name") or "منبع")[:24]}', callback_data=f'briefsrcdel:{i}')] for i,s in enumerate(selected,1)]
    rows += [[InlineKeyboardButton('➕ افزودن/جستجوی منبع', callback_data='brief:research')],[InlineKeyboardButton('🔎 بررسی', callback_data='brief:review')]]
    await q.message.reply_text('حذف شد: '+title+'\n\n📚 منابع باقی‌مانده\n'+'\n'.join(lines), reply_markup=InlineKeyboardMarkup(rows))

async def brief_history_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_lawyer(q, context, 'briefs'): return
    versions=context.user_data.get('brief_versions') or []
    if not versions:
        await q.message.reply_text('تاریخچه‌ای وجود ندارد.'); return
    rows=[]
    for v in reversed(versions[-8:]):
        rows.append([InlineKeyboardButton(f"V{v['version']} — {v.get('label','نسخه')}", callback_data=f"briefver:{v['version']}")])
    await q.message.reply_text('🕘 تاریخچه نسخه‌های لایحه:', reply_markup=InlineKeyboardMarkup(rows))

async def brief_version_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_lawyer(q, context, 'briefs'): return
    try: n=int(q.data.split(':')[1])
    except Exception: return
    v=get_version(context.user_data,n)
    if not v:
        await q.message.reply_text('نسخه پیدا نشد.'); return
    await reply_long(q.message, f"V{n} — {v.get('label','نسخه')}\n\n{v.get('text','')}")
    await q.message.reply_text('می‌توانید این نسخه را فعال کنید.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('✅ فعال‌کردن این نسخه', callback_data=f'briefveruse:{n}')],[InlineKeyboardButton('📊 مقایسه با نسخه فعال', callback_data=f'briefcompare:{n}')],[InlineKeyboardButton('↩️ بازگشت به تاریخچه', callback_data='brief:history')]]))

async def brief_word_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_lawyer(q, context, 'briefs'): return
    text=current_text(context.user_data)
    if not text:
        await q.message.reply_text('پیش‌نویسی برای خروجی وجود ندارد.'); return
    try:
        from docx import Document
        from docx.shared import Pt
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from pathlib import Path
        import tempfile, os
        doc=Document(); sec=doc.sections[0]
        sec.top_margin=Pt(60); sec.bottom_margin=Pt(60); sec.left_margin=Pt(54); sec.right_margin=Pt(54)
        if doc.paragraphs:
            doc.paragraphs[0].add_run('')
        header=sec.header.paragraphs[0]; header.alignment=WD_ALIGN_PARAGRAPH.RIGHT; header.text='LegalBot — پیش‌نویس لایحه'
        footer=sec.footer.paragraphs[0]; footer.alignment=WD_ALIGN_PARAGRAPH.CENTER; footer.text='پیش‌نویس داخلی — بررسی و تطبیق با پرونده و مقررات الزامی است.'
        for block in text.split('\n\n'):
            p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.RIGHT
            r=p.add_run(block.strip()); r.font.name='B Nazanin'; r.font.size=Pt(12)
        sources=context.user_data.get('brief_selected_sources') or []
        if sources:
            h=doc.add_paragraph(); h.alignment=WD_ALIGN_PARAGRAPH.RIGHT
            rr=h.add_run('منابع تأییدشده لایحه'); rr.bold=True; rr.font.name='B Nazanin'; rr.font.size=Pt(13)
            for i,src in enumerate(sources,1):
                label=source_label(src,i)
                p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.RIGHT
                r=p.add_run(f'[C{i}] {label}'); r.font.name='B Nazanin'; r.font.size=Pt(11)
        path=Path(tempfile.gettempdir())/f"legalbot_brief_{q.from_user.id}.docx"
        doc.save(path)
        with open(path,'rb') as fh:
            await q.message.reply_document(document=fh, filename='LegalBot_Brief.docx', caption='📄 خروجی Word — پیش‌نویس قابل ویرایش')
        try: os.unlink(path)
        except Exception: pass
    except Exception:
        logger.exception('brief word export failed')
        await q.message.reply_text('❌ ساخت فایل Word انجام نشد.')


async def brief_pdf_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_lawyer(q, context, 'briefs'): return
    text=current_text(context.user_data)
    if not text:
        await q.message.reply_text('پیش‌نویسی برای خروجی وجود ندارد.'); return
    try:
        from docx import Document
        from docx.shared import Pt
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from pathlib import Path
        import tempfile, subprocess, os
        root=Path(tempfile.mkdtemp(prefix='legalbot_pdf_'))
        doc=Document(); sec=doc.sections[0]
        sec.top_margin=Pt(60); sec.bottom_margin=Pt(60); sec.left_margin=Pt(54); sec.right_margin=Pt(54)
        header=sec.header.paragraphs[0]; header.alignment=WD_ALIGN_PARAGRAPH.RIGHT; header.text='LegalBot — پیش‌نویس لایحه'
        footer=sec.footer.paragraphs[0]; footer.alignment=WD_ALIGN_PARAGRAPH.CENTER; footer.text='پیش‌نویس داخلی — بررسی و تطبیق با پرونده و مقررات الزامی است.'
        for block in text.split('\n\n'):
            p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.RIGHT
            r=p.add_run(block.strip()); r.font.name='Noto Sans'; r.font.size=Pt(12)
        sources=context.user_data.get('brief_selected_sources') or []
        if sources:
            h=doc.add_paragraph(); h.alignment=WD_ALIGN_PARAGRAPH.RIGHT
            rr=h.add_run('منابع تأییدشده لایحه'); rr.bold=True; rr.font.name='Noto Sans'; rr.font.size=Pt(13)
            for i,src in enumerate(sources,1):
                p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.RIGHT
                r=p.add_run(f'[C{i}] {source_label(src,i)}'); r.font.name='Noto Sans'; r.font.size=Pt(11)
        docx=root/'LegalBot_Brief.docx'; doc.save(docx)
        subprocess.run(['libreoffice','--headless','--convert-to','pdf','--outdir',str(root),str(docx)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        pdf=root/'LegalBot_Brief.pdf'
        if not pdf.exists(): raise RuntimeError('PDF conversion failed')
        await q.message.reply_document(document=open(pdf,'rb'), filename='LegalBot_Brief.pdf', caption='📄 خروجی PDF — پیش‌نویس قابل بازبینی')
    except Exception:
        logger.exception('brief pdf export failed')
        await q.message.reply_text('❌ ساخت PDF در این محیط در دسترس نبود؛ خروجی Word را امتحان کنید.')

async def brief_version_use_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_lawyer(q, context, 'briefs'): return
    try: n=int(q.data.split(':')[1])
    except Exception: return
    v=get_version(context.user_data,n)
    if not v:
        await q.message.reply_text('نسخه پیدا نشد.'); return
    remember_version(context.user_data, v.get('text',''), f'بازگشت از V{n}')
    await reply_long(q.message, current_text(context.user_data))
    await q.message.reply_text(f'✅ نسخه V{n} به‌عنوان نسخه فعال انتخاب شد.', reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton('🔎 بررسی', callback_data='brief:review'), InlineKeyboardButton('📄 Word', callback_data='brief:word'), InlineKeyboardButton('📑 PDF', callback_data='brief:pdf')]
    ]))

async def brief_editprompt_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_lawyer(q, context, 'briefs'): return
    if not current_text(context.user_data):
        await q.message.reply_text('ابتدا یک لایحه تولید کنید.'); return
    context.user_data['brief_edit_prompt']=True
    await q.message.reply_text('✏️ تغییر موردنظر را بنویسید. مثال:\n«دفاعیات: ...»\nیا «بخش خواسته را حذف کن»\nیا «متن را کوتاه کن»')

async def brief_regenerate_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_lawyer(q, context, 'briefs'): return
    facts=context.user_data.get('brief_facts_value','')
    if not current_text(context.user_data):
        await q.message.reply_text('هنوز پیش‌نویسی برای بازسازی ندارید.')
        return
    if context.user_data.get('brief_manual_edits') and q.data == 'brief:regenerate':
        await brief_regenerate_confirm_cb(update, context)
        return
    context.user_data['brief_manual_edits']=False
    gaps=detect_brief_gaps(
        facts,
        context.user_data.get('brief_type',''),
        get_case_text(q.from_user.id,context.user_data.get('brief_case_id')) if context.user_data.get('brief_case_id') else '',
        context.user_data.get('brief_template_key','')
    )
    if gaps:
        context.user_data['brief_gap_followup']=True
        await q.message.reply_text('📋 برای بازسازی دقیق‌تر، این موارد هنوز ناقص‌اند:\n\n'+'\n'.join(f'• {g}' for g in gaps))
        return
    await _generate_brief_from_state(q.message, context, q.from_user.id, facts)


async def brief_force_regenerate_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_lawyer(q, context, 'briefs'): return
    if q.data != 'briefregen:force': return
    context.user_data['brief_manual_edits']=False
    facts=context.user_data.get('brief_facts_value','')
    await _generate_brief_from_state(q.message, context, q.from_user.id, facts)


async def brief_research_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_lawyer(q, context, 'briefs'): return
    await q.message.reply_text(
        '🔎 موضوع یا منبعی را که می‌خواهید بیشتر بررسی شود بنویسید.\n\n'
        'مثلاً: «رأی وحدت رویه مرتبط با تخلیه» یا «ماده ۲۱۹ قانون مدنی»'
    )
    context.user_data['brief_source_query']=True
    context.user_data['brief_add_to_existing']=bool(context.user_data.get('brief_selected_sources'))

async def text(update, context):
    uid = update.effective_user.id
    msg = update.effective_message
    value = (msg.text or '').strip()
    if not value:
        return
    # The main menu is now summoned on demand.  Do this before all stateful
    # text routing so the menu button can never be consumed as user input.
    if value in {'🔎 جستجوی حقوقی', 'جستجوی حقوقی'}:
        if not _is_registered(uid):
            await msg.reply_text('ابتدا /start را بزنید.')
            return
        _clear_pending_inputs(context, keep='awaiting_unified_legal_search')
        context.user_data['awaiting_unified_legal_search'] = True
        await msg.reply_text('🔎 عبارت حقوقی را بنویسید؛ مثلاً «ماده ۱۰ قانون مدنی» یا «رأی وحدت رویه ۸۱۰».')
        return
    if value in {'🧮 محاسبات', 'محاسبات'}:
        if not _is_registered(uid):
            await msg.reply_text('ابتدا /start را بزنید.')
            return
        _clear_pending_inputs(context)
        await msg.reply_text('🧮 محاسبات حقوقی', reply_markup=calculator_menu())
        return
    if value in {'☰ منوی اصلی', 'منوی اصلی'}:
        _clear_pending_inputs(context)
        await msg.reply_text('⚖️ منوی اصلی:', reply_markup=menu(update.effective_user.id if update.effective_user else None))
        return
    if context.user_data.get('calc_calendar_convert') is True:
        parsed = parse_jalali(value) or parse_gregorian(value)
        if not parsed:
            await msg.reply_text('❌ تاریخ قابل تشخیص نیست. نمونه: ۱۴۰۵/۰۶/۲۹ یا 2026/09/20')
            return
        y,m,d,g = parsed
        jy,jm,jd = gregorian_to_jalali(g)
        source = 'شمسی' if parse_jalali(value) else 'میلادی'
        context.user_data.pop('calc_calendar_convert',None)
        await msg.reply_text(
            f'🔄 نتیجه تبدیل تاریخ\n\n'
            f'ورودی ({source}): {value}\n'
            f'📅 شمسی ایران: {_fa_num_text(f"{jy:04d}/{jm:02d}/{jd:02d}")}\n'
            f'🌍 میلادی: {_fa_num_text(g.strftime("%Y/%m/%d"))}', reply_markup=calendar_menu())
        return
    if context.user_data.get('calc_quick_percent') is True:
        amount=calc_parse_amount(value)
        if amount is None or amount <= 0:
            await msg.reply_text('❌ مبلغ معتبر وارد کنید.'); return
        context.user_data.pop('calc_quick_percent',None)
        context.user_data['calc_quick_percent_amount']=amount
        await msg.reply_text('🔢 درصد را وارد کنید؛ مثلاً ۲۵:')
        context.user_data['calc_quick_percent_rate']=True
        return
    if context.user_data.get('calc_quick_percent_rate') is True:
        pct=calc_parse_amount(value)
        if pct is None or pct < 0:
            await msg.reply_text('❌ درصد معتبر وارد کنید.'); return
        amount=context.user_data.pop('calc_quick_percent_amount'); context.user_data.pop('calc_quick_percent_rate',None)
        result=amount*float(pct)/100
        await msg.reply_text(f'🔢 نتیجه درصد\n\nمبلغ: {_fa_num_text(f"{amount:,.0f}")} تومان\nدرصد: {_fa_num_text(f"{pct:g}")}٪\n💰 حاصل: {_fa_num_text(f"{result:,.0f}")} تومان', reply_markup=_calculator_back_keyboard())
        return
    if context.user_data.get('calc_quick_rial') is True:
        amount=calc_parse_amount(value)
        if amount is None or amount < 0:
            await msg.reply_text('❌ مبلغ معتبر وارد کنید.'); return
        context.user_data.pop('calc_quick_rial',None)
        await msg.reply_text(f'💱 نتیجه تبدیل\n\n{_fa_num_text(f"{amount:,.0f}")} تومان\n= {_fa_num_text(f"{amount*10:,.0f}")} ریال', reply_markup=_calculator_back_keyboard())
        return
    if context.user_data.get('calc_quick_rial_reverse') is True:
        amount=calc_parse_amount(value)
        if amount is None or amount < 0:
            await msg.reply_text('❌ مبلغ معتبر وارد کنید.'); return
        context.user_data.pop('calc_quick_rial_reverse',None)
        await msg.reply_text(f'💱 نتیجه تبدیل\n\n{_fa_num_text(f"{amount:,.0f}")} ریال\n= {_fa_num_text(f"{amount/10:,.1f}")} تومان', reply_markup=_calculator_back_keyboard())
        return
    if context.user_data.get('calc_quick_installment') is True:
        amount=calc_parse_amount(value)
        if amount is None or amount <= 0:
            await msg.reply_text('❌ مبلغ معتبر وارد کنید.'); return
        context.user_data.pop('calc_quick_installment',None); context.user_data['calc_quick_installment_amount']=amount
        await msg.reply_text('➗ تعداد اقساط را وارد کنید؛ مثلاً ۱۲:'); context.user_data['calc_quick_installment_count']=True
        return
    if context.user_data.get('calc_quick_installment_count') is True:
        n=calc_parse_amount(value)
        if n is None or n <= 0 or int(n)!=n:
            await msg.reply_text('❌ تعداد اقساط باید یک عدد صحیح مثبت باشد.'); return
        amount=context.user_data.pop('calc_quick_installment_amount'); context.user_data.pop('calc_quick_installment_count',None)
        base=amount//int(n); rem=int(amount)%int(n)
        await msg.reply_text(f'➗ نتیجه قسط‌بندی\n\nکل مبلغ: {_fa_num_text(f"{amount:,.0f}")} تومان\nتعداد: {_fa_num_text(str(int(n)))} قسط\nهر قسط پایه: {_fa_num_text(f"{base:,.0f}")} تومان\nباقی‌مانده تقسیم: {_fa_num_text(str(rem))} تومان\n\n⚠️ این تقسیم مساوی ساده است و سود/کارمزد/ضمانت را لحاظ نمی‌کند.', reply_markup=_calculator_back_keyboard())
        return
    if context.user_data.get('calc_quick_datediff'):
        stage=context.user_data.get('calc_quick_datediff')
        parsed=parse_jalali(value) or parse_gregorian(value)
        if not parsed:
            await msg.reply_text('❌ تاریخ قابل تشخیص نیست.'); return
        g=parsed[3]
        if stage==1:
            context.user_data['calc_quick_datediff_start']=g.isoformat(); context.user_data['calc_quick_datediff']=2
            await msg.reply_text('📆 تاریخ دوم را وارد کنید:'); return
        start=date.fromisoformat(context.user_data.pop('calc_quick_datediff_start')); context.user_data.pop('calc_quick_datediff',None)
        delta=(g-start).days
        absdelta=abs(delta)
        await msg.reply_text(f'📆 فاصله دو تاریخ\n\nتاریخ اول: {_fa_num_text(_fmt_jalali(start))} / {_fa_num_text(_fmt_gregorian(start))}\nتاریخ دوم: {_fa_num_text(_fmt_jalali(g))} / {_fa_num_text(_fmt_gregorian(g))}\n\n⏱ فاصله: {_fa_num_text(str(absdelta))} روز تقویمی\n' + ('↗️ تاریخ دوم بعد از تاریخ اول است.' if delta>0 else '↙️ تاریخ دوم قبل از تاریخ اول است.' if delta<0 else '🟰 دو تاریخ یکسان‌اند.'), reply_markup=calendar_menu())
        return
    if context.user_data.get('calc_mahr_amount') is True:
        amount=calc_parse_amount(value)
        if amount is None or amount <= 0:
            await msg.reply_text('❌ لطفاً مبلغ معتبر را به تومان وارد کنید.')
            return
        context.user_data['calc_mahr_amount']=amount
        await msg.reply_text('📅 سال وقوع عقد را انتخاب کنید:',reply_markup=mahr_year_keyboard())
        return
    if context.user_data.get('calc_fee_amount') is True:
        amount=calc_parse_amount(value)
        if amount is None or amount <= 0:
            await msg.reply_text('❌ لطفاً مبلغ معتبر را به ریال وارد کنید.')
            return
        context.user_data['calc_fee_amount']=amount
        await msg.reply_text('مرحله را انتخاب کنید:',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('بدوی',callback_data='calc:feestage:first')],[InlineKeyboardButton('تجدیدنظر/واخواهی',callback_data='calc:feestage:appeal')],[InlineKeyboardButton('فرجام/اعاده/اعتراض ثالث',callback_data='calc:feestage:supreme')]]))
        return
    if context.user_data.get('calc_lawyer_amount') is True:
        amount=calc_parse_amount(value)
        if amount is None or amount <= 0:
            await msg.reply_text('❌ لطفاً مبلغ معتبر را به ریال وارد کنید.')
            return
        context.user_data['calc_lawyer_amount']=amount
        await msg.reply_text(_lawyer_fee_message(amount), reply_markup=calculator_menu())
        context.user_data.pop('calc_lawyer_amount',None)
        return
    if context.user_data.get('calc_deadline_date') is True:
        parsed = parse_jalali(value) or parse_gregorian(value)
        if not parsed:
            await msg.reply_text('❌ تاریخ قابل تشخیص نیست. نمونه: ۱۴۰۵/۰۶/۱۲ یا 2026-09-03')
            return
        d=parsed[3]; result=add_calendar_days(d,20)
        context.user_data.pop('calc_deadline_date',None)
        await msg.reply_text(f'📅 نتیجه مهلت تقویمی ۲۰ روزه\n\nتاریخ مبنا: {_fa_num_text(_fmt_jalali(d))} / {_fa_num_text(_fmt_gregorian(d))}\nپایان محاسبه تقویمی: {_fa_num_text(_fmt_jalali(result))} / {_fa_num_text(_fmt_gregorian(result))}\n\n⚠️ این فقط جمع ۲۰ روز تقویمی است و تعطیلات، قواعد خاص ابلاغ و نحوه احتساب مهلت را خودکار اعمال نمی‌کند.',reply_markup=calendar_menu())
        return
    if context.user_data.get('calc_delay_amount') is True:
        amount=calc_parse_amount(value)
        if amount is None or amount<=0:
            await msg.reply_text('❌ مبلغ معتبر وارد کنید.'); return
        context.user_data.pop('calc_delay_amount',None); context.user_data['calc_delay_amount_value']=amount; context.user_data['calc_delay_src']=True
        await msg.reply_text('شاخص مبدأ را وارد کنید (مثلاً 100):'); return
    if context.user_data.get('calc_delay_src') is True:
        idx=calc_parse_amount(value)
        if idx is None or idx<=0:
            await msg.reply_text('❌ شاخص معتبر وارد کنید.'); return
        context.user_data.pop('calc_delay_src',None); context.user_data['calc_delay_src_value']=idx; context.user_data['calc_delay_dst']=True
        await msg.reply_text('شاخص مقصد را وارد کنید:'); return
    if context.user_data.get('calc_delay_dst') is True:
        idx=calc_parse_amount(value)
        if idx is None or idx<=0:
            await msg.reply_text('❌ شاخص معتبر وارد کنید.'); return
        amount=context.user_data.pop('calc_delay_amount_value'); src=context.user_data.pop('calc_delay_src_value'); context.user_data.pop('calc_delay_dst',None)
        try:
            dd=delay_damage(amount,src,idx); corrected,damage=dd['corrected'],dd['damage']
        except Exception:
            corrected=round(amount*idx/src); damage=corrected-amount
        await msg.reply_text(f'💰 نتیجه شاخص‌محور\n\nاصل دین: {_fa_num(f"{amount:,.0f}")} تومان\nشاخص مبدأ: {_fa_num(f"{src:,.0f}")}\nشاخص مقصد: {_fa_num(f"{idx:,.0f}")}\nمبلغ تعدیل‌شده: {_fa_num(f"{corrected:,.0f}")} تومان\nمابه‌التفاوت (برآورد خسارت شاخصی): {_fa_num(f"{damage:,.0f}")} تومان\n\n📐 فرمول: اصل × (مقصد ÷ مبدأ)\n⚠️ تعدیل شاخصی است نه رأی قطعی. ماده ۵۲۲ و شاخص رسمی را جداگانه بررسی کنید.', reply_markup=calculator_menu()); return
    if context.user_data.get('registration_name') is True:
        name = re.sub(r'\s+', ' ', value).strip()
        if len(name) < 3 or len(name) > 100 or len(name.split()) < 2:
            await msg.reply_text('❌ نام و نام خانوادگی معتبر وارد کنید؛ مثلاً «علی رضایی».')
            return
        context.user_data['registration_name_value'] = name
        context.user_data.pop('registration_name', None)
        context.user_data['registration_license'] = True
        await msg.reply_text(
            '⚖️ شماره پروانه وکالت خود را وارد کنید.\n'
            'مثلاً: ۱۲۳۴۵ / 12345')
        return

    if context.user_data.get('registration_license') is True:
        license_no = re.sub(r'\s+', ' ', value).strip()
        if len(license_no) < 3 or len(license_no) > 60:
            await msg.reply_text('❌ شماره پروانه وکالت معتبر نیست. دوباره وارد کنید.')
            return
        phone = context.user_data.get('phone')
        name = context.user_data.get('registration_name_value', '')
        if not phone or not name:
            _clear_pending_inputs(context)
            await msg.reply_text('❌ اطلاعات ثبت‌نام ناقص شد. لطفاً /start را دوباره بزنید.')
            return
        ok, message = register_user(uid, _hash_phone(phone), phone[-4:], license_no, name)
        if not ok:
            if 'کد وکالت' in message:
                await msg.reply_text('❌ این شماره پروانه وکالت قبلاً ثبت شده است. اگر قبلاً حساب ساخته‌اید، /start را بزنید.')
            elif 'شماره قبلاً برای یک حساب' in message:
                await msg.reply_text('❌ این شماره تماس قبلاً برای یک حساب ثبت شده است. اگر قبلاً حساب ساخته‌اید، /start را بزنید.')
            else:
                await msg.reply_text('❌ ' + message)
            return
        _clear_pending_inputs(context)
        ensure_subscription(uid)
        await _after_registration(update, context)
        return

    if context.user_data.get('awaiting_lawyer_upgrade'):
        if not _is_registered(uid):
            await msg.reply_text('ابتدا /start را بزنید.')
            return
        if len(value) > 200:
            await msg.reply_text('❌ کد وکالت نامعتبر است.')
            return
        ok, message = set_lawyer_code(uid, value)
        context.user_data.pop('awaiting_lawyer_upgrade', None)
        pending = context.user_data.pop('pending_private_action', None)
        if not ok:
            await msg.reply_text('❌ ' + message)
            return
        await msg.reply_text('✅ اطلاعات ثبت شد.')
        if pending == 'newcase':
            await new_case_cb(update, context, command=True)
        elif pending == 'cases':
            # Text updates have no callback query; render the same cases flow directly.
            rows = list_cases(uid,20)
            if not rows:
                await msg.reply_text('📁 هنوز پرونده‌ای ثبت نشده است.')
            else:
                active_case_id=get_active_case_id(uid)
                kb=[[InlineKeyboardButton((('🟢 ' if active_case_id == c['id'] else '📁 ') + (c['file_name'] or 'بدون نام'))[:55], callback_data=f'caseview:{c["id"]}')] for c in rows]
                kb.append([InlineKeyboardButton('➕ پرونده جدید', callback_data='newcase'), InlineKeyboardButton('🏠 منوی اصلی', callback_data='home')])
                await msg.reply_text('📁 پرونده‌های من:', reply_markup=InlineKeyboardMarkup(kb))
        elif pending in {'aiassist','briefs','globalsearch'}:
            await msg.reply_text('✅ دسترسی فعال شد. حالا از منوی اصلی بخش موردنظر را انتخاب کنید.')
        else:
            await msg.reply_text('از منوی اصلی، بخش موردنظر را انتخاب کنید.')
        return

    if context.user_data.get('awaiting_lawyer_code'):
        # Legacy registration state retained for backward compatibility.
        phone = context.user_data.get('phone')
        if not phone:
            await msg.reply_text('ابتدا شماره تماس را ارسال کنید.')
            return
        if len(value) > 200:
            await msg.reply_text('❌ کد وکالت نامعتبر است.')
            return
        ok, message = register_user(uid, _hash_phone(phone), phone[-4:], value)
        context.user_data.pop('awaiting_lawyer_code', None)
        context.user_data.pop('phone', None)
        if not ok:
            await msg.reply_text('❌ ' + message)
            return
        ensure_subscription(uid)
        await _after_registration(update, context)
        return
    if not _is_registered(uid):
        await msg.reply_text('ابتدا /start را بزنید.')
        return


    if context.user_data.get('client_search') is True:
        context.user_data.pop('client_search',None)
        term=value.replace('%','').replace('_',' ')
        rows=list_clients(uid,100)
        rows=[c for c in rows if term.casefold() in (c.get('name') or '').casefold() or term in (c.get('phone') or '')]
        if not rows:
            await msg.reply_text('🔎 موصلی با این مشخصات پیدا نشد.', reply_markup=client_menu()); return
        kb=[[InlineKeyboardButton(f'👤 {c["name"]}'[:55], callback_data=f'clientview:{c["id"]}')] for c in rows[:30]]
        kb.append([InlineKeyboardButton('↩️ مدیریت موکل‌ها', callback_data='clients')])
        await msg.reply_text('🔎 نتایج جستجو:', reply_markup=InlineKeyboardMarkup(kb)); return

    if context.user_data.get('client_quick_add') is True:
        context.user_data.pop('client_quick_add', None)
        raw=value.strip()
        compact=raw.replace(' ','').replace('-','')
        phone_match=re.search(r'(?:\+98|0098|98|0)?9\d{9}', compact)
        phone=phone_match.group(0) if phone_match else ''
        if phone.startswith('+98'): phone='0'+phone[3:]
        elif phone.startswith('0098'): phone='0'+phone[4:]
        elif phone.startswith('98') and len(phone)==12: phone='0'+phone[2:]
        name=raw
        if phone_match:
            name=raw.replace(phone_match.group(0),'').replace('-', ' ').strip(' ،,؛;')
        if not name or len(name)>120:
            await msg.reply_text('❌ نام موکل معتبر نیست. دوباره فقط نام و نام خانوادگی را بفرستید.')
            return
        cid=create_client(uid,name,phone,'','')
        await msg.reply_text(
            '✅ موکل ثبت شد.\n'
            f'👤 {name}' + (f'\n📞 {phone}' if phone else '') +
            '\n\nبرای اطلاعات بیشتر بعداً می‌توانید ویرایش کنید.',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('👤 مشاهده موکل',callback_data=f'clientview:{cid}')],
                [InlineKeyboardButton('➕ افزودن سریع دیگری',callback_data='clientaddquick'),InlineKeyboardButton('↩️ مدیریت موکل‌ها',callback_data='clients')]
            ])
        )
        return

    if context.user_data.get('client_name') is True:
        edit_id=context.user_data.get('client_edit_id')
        if not value or len(value)>120:
            await msg.reply_text('❌ نام موکل باید معتبر و حداکثر ۱۲۰ نویسه باشد.'); return
        context.user_data['client_name_value']=value
        context.user_data.pop('client_name',None); context.user_data['client_phone']=True
        old=(context.user_data.get('client_edit_data') or {}).get('phone','')
        await msg.reply_text(f'📞 شماره تماس موکل را وارد کنید یا «رد» بزنید.\nشماره فعلی: {old or "ثبت نشده"}')
        return
    if context.user_data.get('client_phone') is True:
        v='' if value in {'رد','ندارم','ندارد','-'} else value
        context.user_data['client_phone_value']=v; context.user_data.pop('client_phone',None); context.user_data['client_national_id']=True
        old=(context.user_data.get('client_edit_data') or {}).get('national_id','')
        await msg.reply_text(f'🪪 کد ملی را وارد کنید یا «رد» بزنید.\nکد فعلی: {old or "ثبت نشده"}')
        return
    if context.user_data.get('client_national_id') is True:
        v='' if value in {'رد','ندارم','ندارد','-'} else value
        context.user_data['client_national_id_value']=v; context.user_data.pop('client_national_id',None); context.user_data['client_note']=True
        old=(context.user_data.get('client_edit_data') or {}).get('note','')
        await msg.reply_text(f'📝 یادداشت کوتاه درباره موکل را وارد کنید یا «رد» بزنید.\nیادداشت فعلی: {old or "ثبت نشده"}')
        return
    if context.user_data.get('client_note') is True:
        v='' if value in {'رد','ندارم','ندارد','-'} else value[:1000]
        edit_id=context.user_data.get('client_edit_id')
        if edit_id:
            old=context.user_data.get('client_edit_data') or {}
            ok=update_client(uid,edit_id,context.user_data.get('client_name_value'),context.user_data.get('client_phone_value',''),context.user_data.get('client_national_id_value',''),v)
            await msg.reply_text('✅ اطلاعات موکل ویرایش شد.' if ok else '❌ ویرایش انجام نشد.', reply_markup=client_menu())
        else:
            cid=create_client(uid,context.user_data.get('client_name_value'),context.user_data.get('client_phone_value',''),context.user_data.get('client_national_id_value',''),v)
            await msg.reply_text('✅ موکل ثبت شد.' if cid else '❌ ثبت موکل انجام نشد.', reply_markup=client_menu())
        for k in ('client_note','client_edit_id','client_edit_data','client_name_value','client_phone_value','client_national_id_value'): context.user_data.pop(k,None)
        return

    if context.user_data.get('service_edit_step'):
        step=context.user_data['service_edit_step']
        if step=='name':
            context.user_data['service_name_value']=value; context.user_data['service_edit_step']='city'; await msg.reply_text('📍 شهر محل فعالیت را وارد کنید:'); return
        if step=='city':
            context.user_data['service_city_value']=value; context.user_data['service_edit_step']='specialty'; await msg.reply_text('⚖️ تخصص یا حوزه اصلی فعالیت را وارد کنید:'); return
        if step=='specialty':
            context.user_data['service_specialty_value']=value; context.user_data['service_edit_step']='title'; await msg.reply_text('💼 عنوان یک خدمت مشخص را وارد کنید:'); return
        if step=='title':
            context.user_data['service_title_value']=value; context.user_data['service_edit_step']='fee'; await msg.reply_text('💰 نوع دستمزد را انتخاب کنید:',reply_markup=service_fee_keyboard()); return
        if step=='description':
            context.user_data['service_description_value']='' if value=='ندارد' else value; context.user_data['service_edit_step']='charity'; await msg.reply_text('❤️ این خدمت حمایتی است؟',reply_markup=service_charity_keyboard()); return
    if context.user_data.get('service_name'):
        context.user_data.pop('service_name',None); context.user_data['service_name_value']=value
        _clear_pending_inputs(context, keep='service_phone')
        context.user_data['service_phone']=True
        await msg.reply_text('📞 شماره تماس برای معرفی به موکل را وارد کنید.\nمی‌توانید شماره همراه، شماره دیگر یا تلفن ثابت دفتر را بنویسید.')
        return
    if context.user_data.get('service_phone'):
        # Service contact is intentionally free-form: a lawyer may enter a
        # mobile number, another phone, an office landline, or an extension.
        context.user_data.pop('service_phone',None); context.user_data['service_phone_value']=value
        _clear_pending_inputs(context, keep='service_city')
        context.user_data['service_city']=True
        await msg.reply_text('📍 شهر محل فعالیت خود را وارد کنید:', reply_markup=ReplyKeyboardRemove())
        return
    if context.user_data.get('service_license_photo_waiting'):
        await msg.reply_text('📷 لطفاً عکس پروانه وکالت را به‌صورت عکس ارسال کنید.')
        return
    if context.user_data.get('service_city'):
        context.user_data.pop('service_city',None); context.user_data['service_city_value']=value
        _clear_pending_inputs(context, keep='service_specialty')
        context.user_data['service_specialty']=True
        await msg.reply_text('⚖️ تخصص یا حوزه اصلی فعالیت خود را وارد کنید:')
        return
    if context.user_data.get('service_specialty'):
        context.user_data.pop('service_specialty',None); context.user_data['service_specialty_value']=value
        _clear_pending_inputs(context, keep='service_title')
        context.user_data['service_title']=True
        await msg.reply_text('💼 یک خدمت مشخصی که ارائه می‌دهید را وارد کنید:')
        return
    if context.user_data.get('service_title'):
        context.user_data.pop('service_title',None); context.user_data['service_title_value']=value
        _clear_pending_inputs(context, keep='service_fee_type')
        context.user_data['service_fee_type']='choose'
        await msg.reply_text('💰 دستمزد این خدمت را چگونه دریافت می‌کنید؟',reply_markup=service_fee_keyboard())
        return
    if context.user_data.get('service_fee_value_waiting') and context.user_data.get('service_fee_type') in {'fixed','percent'}:
        # Fee value is intentionally free-form. Lawyers may enter amounts,
        # ranges, units, negotiated terms, or other pricing text. The bot
        # only stores/displays it; it does not impose a numeric format here.
        context.user_data['service_fee_value']=value.strip()
        context.user_data.pop('service_fee_value_waiting',None)
        if context.user_data.get('service_edit_step')=='fee':
            context.user_data['service_edit_step']='description'
        else:
            _clear_pending_inputs(context, keep='service_description')
            context.user_data['service_description']=True
        await msg.reply_text('📝 توضیح کوتاه درباره این خدمت یا شرایط پذیرش آن (اختیاری) را وارد کنید. اگر توضیحی ندارید، «ندارد» بنویسید.')
        return
    if context.user_data.get('service_description'):
        context.user_data.pop('service_description',None); context.user_data['service_description_value']='' if value=='ندارد' else value
        await msg.reply_text('❤️ آیا مایلید این خدمت به‌عنوان خدمت حمایتی برای افراد کم‌توان مالی نیز در نظر گرفته شود؟',reply_markup=service_charity_keyboard())
        return
    if context.user_data.get('awaiting_case_note'):
        cid=int(context.user_data.pop('awaiting_case_note'))
        if not get_case(uid,cid):
            await msg.reply_text('❌ پرونده پیدا نشد.')
            return
        if len(value) > MAX_CASE_NOTE_CHARS:
            await msg.reply_text(f'❌ یادداشت بیش از حد مجاز است. حداکثر {MAX_CASE_NOTE_CHARS:,} نویسه (حدود ۱۰ صفحه متن) مجاز است.')
            context.user_data['awaiting_case_note']=cid
            return
        if not value:
            await msg.reply_text('❌ یادداشت نمی‌تواند خالی باشد.')
            context.user_data['awaiting_case_note']=cid
            return
        if not save_case_lawyer_note(uid,cid,value):
            await msg.reply_text('🗄️ این پرونده بایگانی شده یا دیگر در دسترس نیست؛ یادداشت ذخیره نشد.')
            return
        set_active_case(uid,cid)
        await msg.reply_text('✅ یادداشت وکیل برای این پرونده ذخیره شد.', reply_markup=case_menu(cid))
        return

    if context.user_data.get('awaiting_case_addition'):
        cid=int(context.user_data['awaiting_case_addition'])
        await _process_case_addition_text(update, context, value, cid)
        return

    if context.user_data.get('awaiting_case_version_file'):
        await msg.reply_text('📎 منتظر فایل نسخه جدید همین پرونده هستم؛ لطفاً فایل یا عکس را ارسال کنید.')
        return
    if context.user_data.get('awaiting_case_name'):
        if not value or len(value) > CASE_NAME_MAX_CHARS:
            await msg.reply_text(f'❌ نام پرونده باید بین ۱ تا {CASE_NAME_MAX_CHARS} نویسه باشد.')
            return
        context.user_data.pop('awaiting_case_name', None)
        _clear_pending_inputs(context, keep='awaiting_case_file')
        context.user_data['pending_case_name'] = value
        context.user_data['awaiting_case_file'] = True
        context.user_data['case_upload_buffer'] = []
        await msg.reply_text(
            f'📁 نام پرونده ثبت شد: «{value}»\n\n'
            f'📎 فایل یا عکس‌های مربوط به پرونده را بفرستید.\n'
            f'• پی‌دی‌اف، ورد یا عکس تا {MAX_FILE_MB} مگابایت\n'
            f'• اگر چند فایل دارید، همه را پشت‌سرهم ارسال کنید.\n'
            f'• ترجیحاً فایل متنی یا عکس واضح از متن بفرستید.\n'
            f'• وقتی ارسال فایل‌ها تمام شد، دکمه «ثبت پرونده» را بزنید.',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('✅ ثبت پرونده با فایل‌های دریافتی', callback_data='caseupload:finish')],
                [InlineKeyboardButton('❌ انصراف', callback_data='home')],
            ]),
        )
        return
    if context.user_data.get('awaiting_case_file'):
        await msg.reply_text('📎 هنوز منتظر فایل یا عکس همین پرونده هستم. لطفاً فایل را ارسال کنید.')
        return

    if context.user_data.get('awaiting_unified_legal_search'):
        context.user_data.pop('awaiting_unified_legal_search', None)
        law_results = await asyncio.to_thread(law_search, value, 8)
        glossary_results = await asyncio.to_thread(lookup, value, 8)

        parts = []
        if law_results:
            parts.append(law_text(law_results))
        if glossary_results:
            parts.append(format_entries(glossary_results))

        if parts:
            await reply_long(msg, '🔎 نتایج جستجو\n\n' + '\n\n────────────\n\n'.join(parts))
        else:
            await reply_long(msg, '❌ در منابع حقوقی موجود، نتیجه‌ای برای عبارت شما پیدا نشد.')

        await msg.reply_text('مرحله بعد:', reply_markup=after_search_menu())
        return

    if context.user_data.get('awaiting_law_query'):
        context.user_data.pop('awaiting_law_query', None)
        results = await asyncio.to_thread(law_search, value, 8)
        await reply_long(msg, law_text(results))
        if results:
            for r in results[:8]:
                cid=(r.get('citation') or {}).get('id')
                if cid:
                    label=r.get('title') or r.get('law') or 'منبع'
                    locator=r.get('article') or r.get('ruling_number') or r.get('consultation_number')
                    if locator: label += f' — {locator}'
                    await msg.reply_text(f'📖 {label}', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('مشاهده منبع و منابع مرتبط', callback_data=f'source:{cid}')]]))
        await msg.reply_text('مرحله بعد:', reply_markup=after_search_menu())
        return
    if context.user_data.get('awaiting_case_query'):
        cid = context.user_data.pop('awaiting_case_query')
        case = get_case(uid, cid)
        if not case:
            await msg.reply_text('❌ پرونده پیدا نشد.')
            return
        # Search every stored document independently so each hit retains its
        # original filename, document id and extracted page marker.
        case_documents = get_case_documents(uid, cid)
        results = await asyncio.to_thread(search_case_documents, case_documents, value, 40, 12)
        await reply_long(msg, format_case_search_results(results, value))
        await msg.reply_text('📁 ادامه پرونده:', reply_markup=case_menu(cid))
        return
    if context.user_data.get('awaiting_glossary'):
        context.user_data.pop('awaiting_glossary', None)
        result = await asyncio.to_thread(lookup, value)
        await reply_long(msg, format_entries(result) if result else '❌ مدخلی پیدا نشد.')
        await msg.reply_text('⚖️ منوی اصلی:', reply_markup=menu(update.effective_user.id if update.effective_user else None))
        return
    if context.user_data.get('awaiting_global_search'):
        context.user_data.pop('awaiting_global_search', None)
        data = await asyncio.to_thread(search_user_workspace, uid, value, scopes=("cases", "documents", "notes", "tasks"), limit=20)
        items = data.get("items") or []
        if not items:
            await msg.reply_text('🔎 موردی پیدا نشد.')
        else:
            lines = []
            for item in items:
                case_label = f' · پرونده: {item.get("case_name")}' if item.get("case_name") else ''
                locator = f' · صفحه {item.get("page")}' if item.get("page") else ''
                lines.append(f'🔎 {item.get("source")}: {item.get("title")}{case_label}{locator}\n{item.get("snippet", "")}')
            await reply_long(msg, '\n\n'.join(lines))
        await msg.reply_text('⚖️ منوی اصلی:', reply_markup=menu(update.effective_user.id if update.effective_user else None))
        return
    if context.user_data.get('awaiting_case_next_action'):
        cid=int(context.user_data.pop('awaiting_case_next_action'))
        if update_case_workspace(uid,cid,next_action=value):
            await msg.reply_text('✅ اقدام بعدی پرونده ثبت شد.',reply_markup=case_menu(cid))
        else: await msg.reply_text('❌ پرونده پیدا نشد.')
        return
    if context.user_data.get('awaiting_case_task_title'):
        cid=int(context.user_data.pop('awaiting_case_task_title'))
        tid=add_case_task(uid,cid,value)
        if not tid:
            await msg.reply_text('❌ ثبت کار پرونده انجام نشد.', reply_markup=case_menu(cid))
            return
        await msg.reply_text(f'✅ کار پرونده #{tid} ثبت شد.', reply_markup=case_menu(cid))
        return
    if context.user_data.get('awaiting_task_due'):
        if value.strip().lower() in {'بدون موعد','رد','skip','بدون تاریخ'}:
            title=context.user_data.pop('pending_task_title','')
            context.user_data.pop('awaiting_task_due',None)
            tid=add_task(uid,title)
            await msg.reply_text(f'✅ کار #{tid} ثبت شد و بدون موعد در «کارهای من» قرار گرفت.')
            return
        parsed=parse_jalali(value) or parse_gregorian(value)
        if not parsed:
            await msg.reply_text('❌ تاریخ قابل تشخیص نیست. تاریخ شمسی مثل ۱۴۰۵/۰۸/۱۴ یا میلادی مثل ۲۰۲۶/۱۱/۰۵ بفرستید؛ برای رد کردن بنویسید «بدون موعد».')
            return
        title=context.user_data.pop('pending_task_title','')
        context.user_data.pop('awaiting_task_due',None)
        tid=add_task(uid,title,due_at=parsed[3].isoformat())
        await msg.reply_text(f'✅ کار #{tid} با موعد {_fa_num_text(parsed[3].isoformat())} ثبت شد و در تقویم هم نمایش داده می‌شود.')
        return
    if context.user_data.get('awaiting_task_title'):
        context.user_data.pop('awaiting_task_title',None)
        context.user_data['pending_task_title']=value.strip()[:500]
        context.user_data['awaiting_task_due']=True
        await msg.reply_text('📅 موعد این کار را وارد کنید.\n\nشمسی: ۱۴۰۵/۰۸/۱۴\nمیلادی: ۲۰۲۶/۱۱/۰۵\n\nاگر موعد ندارد، بنویسید «بدون موعد».')
        return
    if context.user_data.get('awaiting_referral_info'):
        rid=context.user_data.pop('awaiting_referral_info')
        if add_client_referral_info(int(rid), uid, value):
            await msg.reply_text('✅ اطلاعات تکمیلی ثبت شد و برای ادامه معرفی ارسال می‌شود.')
        else:
            await msg.reply_text('❌ این درخواست معرفی دیگر قابل به‌روزرسانی نیست.')
        return
    if context.user_data.get('ref_topic'):
        context.user_data.pop('ref_topic',None); context.user_data['ref_topic_value']=value
        context.user_data['ref_city']=True
        await msg.reply_text('📍 شهر یا محل موردنظر برای دریافت وکیل را وارد کنید:')
        return
    if context.user_data.get('ref_city'):
        context.user_data.pop('ref_city',None); context.user_data['ref_city_value']=value
        context.user_data['ref_urgency']=True
        await msg.reply_text('⏱ فوریت درخواست را انتخاب کنید:', reply_markup=referral_urgency_keyboard())
        return
    if context.user_data.get('ref_details'):
        context.user_data.pop('ref_details',None)
        rid=create_referral_request(uid, context.user_data.pop('ref_topic_value',''), context.user_data.pop('ref_city_value',''), context.user_data.pop('ref_urgency_value','normal'), value, True)
        context.user_data.clear()
        await msg.reply_text(f'✅ درخواست معرفی شما با شماره #{rid} ثبت شد.\n\nاطلاعات لازم برای بررسی و معرفی وکیل در اختیار ادمین قرار گرفت. نتیجه از طریق همین ربات اطلاع داده می‌شود.')
        await _send_referral_to_admins(msg.get_bot(), rid)
        return
    if context.user_data.get('awaiting_feedback'):
        feedback_kind = context.user_data.pop('awaiting_feedback', 'user_report')
        add_feedback(uid, feedback_kind if feedback_kind in {'support','user_report'} else 'user_report', value)
        await msg.reply_text('✅ گزارش شما ثبت شد. ممنون.')
        return
    # V163: durable interactive V150 answers survive bot/process restarts.
    workflow_answer_keys=[k for k,v in context.user_data.items() if str(k).startswith('draft_workflow_waiting_answer:') and v]
    workflow_cid = None
    if workflow_answer_keys:
        try: workflow_cid=int(workflow_answer_keys[0].split(':',1)[1])
        except Exception: workflow_cid=None
    else:
        # After a restart there is no context.user_data checkpoint. Recover the
        # pending question from the durable session of the user's active case.
        try:
            active_cid=get_active_case_id(uid)
            durable=get_drafting_workflow_session(uid, int(active_cid)) if active_cid else None
            if durable and str(durable.get('status')) == 'WAITING_FOR_INPUT':
                workflow_cid=int(active_cid)
                workflow_answer_keys=[f'draft_workflow_waiting_answer:{workflow_cid}']
        except Exception:
            workflow_cid=None
    if workflow_cid is not None:
        cid=workflow_cid
        state=load_workflow_state(uid, cid)
        qkey=context.user_data.pop(f'draft_workflow_question:{cid}',None) or state.get('waiting_question_key')
        for k in workflow_answer_keys:
            context.user_data.pop(k,None)
        answers=dict(state.get('answers') or {})
        deferred=set(state.get('deferred') or [])
        unknown = value in {'نمی‌دانم','نمیدانم','نمی دانم','unknown'}
        if not unknown and qkey:
            answers[str(qkey)]=value
        elif unknown and qkey:
            deferred.add(str(qkey))
        state['answers']=answers
        state['deferred']=sorted(deferred)
        state.pop('waiting_question_key',None)
        preflight=await asyncio.to_thread(preflight_v150, uid, cid, 'لایحه دفاعیه', answers, deferred)
        state['preflight']=preflight
        if preflight.get('workflow_ready'):
            state=save_workflow_state(uid, cid, state, 'READY_TO_RUN')
            await msg.reply_text('✅ اطلاعات ضروری تکمیل شد. در حال ادامه لایحه‌نویسی...')
            result=await asyncio.to_thread(run_drafting_workflow, uid, cid, brief_type='لایحه دفاعیه', answers=answers, deferred=set(state.get('deferred') or []))
            state.update({'status':result.get('status'),'preflight':result.get('preflight'),'gate':result.get('gate'),'output':result.get('output')})
            save_workflow_state(uid, cid, state, result.get('status') or 'NEEDS_LAWYER_REVIEW')
            context.user_data[f'draft_workflow:{cid}']=state
            if result.get('output'):
                await reply_long(msg, render_output_overview(result['output']))
            await msg.reply_text(workflow_label(result), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('📄 مشاهده پیش‌نویس', callback_data=f'couttext160:{cid}')],[InlineKeyboardButton('📤 دریافت Word / PDF', callback_data=f'coutput160:{cid}')],[InlineKeyboardButton('🔍 موارد نیازمند بررسی', callback_data=f'coutgate160:{cid}')],[InlineKeyboardButton('⬅️ لایحه‌نویسی', callback_data=f'cdrafting:{cid}')]]))
        else:
            question=next_required_question(preflight, set(state.get('deferred') or []))
            if question:
                state['waiting_question_key']=question.get('key')
                save_workflow_state(uid, cid, state, 'WAITING_FOR_INPUT')
                context.user_data[f'draft_workflow:{cid}']=state
                context.user_data[f'draft_workflow_question:{cid}']=question.get('key')
                context.user_data[f'draft_workflow_waiting_answer:{cid}']=True
                await msg.reply_text('✏️ '+str(question.get('question') or question.get('label'))+'\n\nاگر فعلاً پاسخ را نمی‌دانید، بنویسید «نمی‌دانم».', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('⏭️ فعلاً رد کن', callback_data=f'cskip162:{cid}')],[InlineKeyboardButton('⬅️ لایحه‌نویسی', callback_data=f'cdrafting:{cid}')]]))
        return
    if context.user_data.get('brief_v150_waiting_answer'):
        context.user_data.pop('brief_v150_waiting_answer', None)
        key=context.user_data.pop('brief_v150_question_key', None)
        label=context.user_data.pop('brief_v150_question_label', None)
        resolver=context.user_data.get('brief_v150_resolver') or {}
        if value in {'نمی‌دانم','نمیدانم','نمی دانم','unknown'}:
            # Explicitly deferred; never converted into a fact.
            answer=''
            confirmed=False
        else:
            answer=value
            confirmed=True
        resolver=apply_information_answer(resolver, key, answer, confirmed=confirmed)
        if not confirmed:
            for item in resolver.get('items') or []:
                if item.get('key')==key:
                    item.setdefault('notes',[]).append('وکیل اعلام کرد فعلاً پاسخ را نمی‌داند؛ مقدار خالی است و fact محسوب نمی‌شود.')
            resolver['questions']=[q for q in resolver.get('questions',[]) if q.get('key')!=key]
        context.user_data['brief_v150_resolver']=resolver
        answers=context.user_data.setdefault('brief_v150_answers',{})
        if answer:
            answers[str(key)]=answer
        await _brief_run_information_resolver(msg, context, uid, _brief_v150_context(context))
        return
    if context.user_data.get('brief_source_query'):
        context.user_data.pop('brief_source_query', None)
        base=context.user_data.get('brief_facts_value','')
        query=(base+'\n'+value).strip()
        add_mode=bool(context.user_data.pop('brief_add_to_existing', False))
        await _brief_prepare_sources(msg, context, uid, query, add_to_existing=add_mode)
        return
    if context.user_data.get('brief_opposing_response_input'):
        context.user_data.pop('brief_opposing_response_input', None)
        context.user_data['brief_opposing_responses'] = value
        rows = opposing_response_matrix(context.user_data.get('brief_opposing_text',''), context.user_data.get('brief_facts_value',''), context.user_data.get('brief_selected_sources',[]))
        rows = apply_opposing_responses(rows, value)
        lines=['⚔️ جدول پاسخ به لایحه طرف مقابل','']
        for r in rows:
            lines += [f"{r['id']}) ادعا: {r['claim']}", f"   ↩️ پاسخ: {r['response'] or 'ثبت نشده'}", f"   وضعیت: {r['status']}", '']
        await reply_long(msg,'\n'.join(lines))
        await msg.reply_text('پاسخ‌های صریح ثبت شدند؛ برای ساخت اسکلت لایحه می‌توانید ادامه دهید.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('📝 ساخت اسکلت پاسخ',callback_data='brief:opposing_outline'),InlineKeyboardButton('🧰 میزکار',callback_data='brief:workspace')]]))
        return

    if context.user_data.get('brief_opposing_text_input'):
        context.user_data.pop('brief_opposing_text_input', None)
        context.user_data['brief_opposing_text'] = value
        rows = opposing_response_matrix(value, context.user_data.get('brief_facts_value',''), context.user_data.get('brief_selected_sources',[]))
        lines=['⚔️ ادعاهای استخراج‌شده از لایحه طرف مقابل','']
        if rows:
            for r in rows:
                lines.append(f"{r['id']}) {r['claim']}")
        else:
            lines.append('⚠️ ادعای صریحی پیدا نشد.')
        await reply_long(msg,'\n'.join(lines))
        await msg.reply_text('اگر استخراج مورد تأیید است، جدول پاسخ را باز کنید.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('⚔️ ساخت جدول پاسخ',callback_data='brief:opposing_result'),InlineKeyboardButton('🧰 میزکار',callback_data='brief:workspace')]]))
        return

    if context.user_data.get('brief_section_edit_number'):
        try: num=int(context.user_data.pop('brief_section_edit_number'))
        except Exception: num=0
        old=current_text(context.user_data)
        new=_replace_numbered_section(old, num, value) if num else old
        if new != old:
            new=add_inline_citations(new, context.user_data.get('brief_selected_sources',[]))
            context.user_data['brief_manual_edits']=True
            context.user_data['brief_lifecycle']='review'
            remember_version(context.user_data,new,f'ویرایش بخش {num}')
            await reply_long(msg,new)
            await msg.reply_text('✅ همان بخش اصلاح شد.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🔎 بررسی',callback_data='brief:review'),InlineKeyboardButton('🧰 میزکار',callback_data='brief:workspace')],[InlineKeyboardButton('📄 Word',callback_data='brief:word')]]))
        else:
            await msg.reply_text('❌ بخش موردنظر پیدا نشد یا تغییری ایجاد نشد.')
        return
    if context.user_data.get('brief_edit_prompt'):
        context.user_data.pop('brief_edit_prompt', None)
        old=current_text(context.user_data)
        new,note=apply_local_edit(old, value)
        if new != old:
            new=add_inline_citations(new, context.user_data.get('brief_selected_sources',[]))
            context.user_data['brief_manual_edits']=True
            context.user_data['brief_lifecycle']='review'
            remember_version(context.user_data, new, 'ویرایش کاربر')
            # Keep the regeneration input aligned with the current manual draft
            # only for future review; regeneration still rebuilds from source facts.
            await reply_long(msg, new)
            await msg.reply_text('✅ '+note, reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('🔎 بررسی', callback_data='brief:review'), InlineKeyboardButton('📄 Word', callback_data='brief:word'), InlineKeyboardButton('📑 PDF', callback_data='brief:pdf')],
                [InlineKeyboardButton('🕘 تاریخچه', callback_data='brief:history')]
            ]))
        else:
            await msg.reply_text('ℹ️ '+note, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('✏️ تلاش دوباره', callback_data='brief:editprompt')]]))
        return
    if context.user_data.get('brief_facts'):
        context.user_data.pop('brief_facts', None)
        await _brief_prepare_sources(msg, context, uid, value)
        return
    if context.user_data.get('brief_gap_followup'):
        context.user_data.pop('brief_gap_followup', None)
        prior=context.user_data.get('brief_facts_value','')
        merged=(prior+'\n'+value).strip()
        context.user_data['brief_facts_value']=merged
        await _generate_brief_from_state(msg, context, uid, merged)
        return
    if context.user_data.get('awaiting_case_ai_question'):
        cid=int(context.user_data.pop('awaiting_case_ai_question'))
        if not get_case(uid,cid):
            await msg.reply_text('❌ پرونده پیدا نشد.'); return
        context.user_data['case_ai_question']=value
        context.user_data['case_ai_context_choice']=cid
        context.user_data['awaiting_case_ai_context_choice']=True
        await msg.reply_text('📎 برای پاسخ به این سؤال، کدام زمینه را همراه آن به AI بفرستیم؟', reply_markup=_case_ai_context_keyboard(cid))
        return
    if context.user_data.get('awaiting_ai_question'):
        context.user_data.pop('awaiting_ai_question', None)
        context.user_data.pop('awaiting_ai_context_choice', None)
        context.user_data.pop('ai_question', None)
        # General legal Q&A sends only the user's question. No case documents,
        # files, images, or prior conversations are attached implicitly.
        await dispatch_ai_question(update, context, value)
        return
    await msg.reply_text('از دکمه‌های منوی اصلی استفاده کنید.')




SERVICE_INTRO = """🤝 ثبت خدمات برای معرفی به موکلان

می‌توانید خدمات و تخصص خود را به‌صورت رایگان ثبت کنید.

📌 ثبت خدمت رایگان است و پس از بررسی، وضعیت آن در بخش خدمات شما نمایش داده می‌شود.

❤️ اگر مایل باشید خدمتی را برای افراد کم‌توان مالی رایگان یا با هزینه کمتر ارائه دهید، می‌توانید آن را به‌عنوان خدمت حمایتی ثبت کنید."""


def service_fee_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('💰 مبلغ ثابت', callback_data='servicefee:fixed'),
         InlineKeyboardButton('📊 درصد', callback_data='servicefee:percent')],
    ])


def service_charity_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('❤️ بله، خدمت حمایتی است', callback_data='servicecharity:yes')],
        [InlineKeyboardButton('خیر', callback_data='servicecharity:no')],
    ])


def service_admin_keyboard(lid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('✅ تأیید', callback_data=f'serviceadmin:approve:{lid}'),
         InlineKeyboardButton('❌ رد', callback_data=f'serviceadmin:reject:{lid}')],
    ])


def _service_fee_text(row):
    return f"{row['fee_value']} تومان" if row['fee_type']=='fixed' else f"{row['fee_value']}٪"


def _service_admin_text(row):
    charity='❤️ خدمت حمایتی' if row.get('charitable') else 'خدمت عادی'
    return (f"📥 خدمت جدید #{row['id']}\n\n"
            f"👤 نام: {row['full_name']}\n"
            f"📞 تماس: {row['phone']}\n"
            f"📍 شهر: {row['city']}\n"
            f"⚖️ تخصص: {row['specialty']}\n"
            f"💼 خدمت: {row['service_title']}\n"
            f"💰 دستمزد: {_service_fee_text(row)}\n"
            f"{charity}\n"
            f"📝 توضیحات: {row.get('description') or '—'}\n\n"
            f"👤 Telegram ID: {row['user_id']}\n"
            f"وضعیت: {row['status']}")


def _validate_service_fields(full_name, phone, city, specialty, title, fee_type, fee_value, description=''):
    vals = {
        'نام و نام خانوادگی': full_name, 'شماره تماس': phone, 'شهر': city,
        'تخصص': specialty, 'عنوان خدمت': title,
    }
    for label, value in vals.items():
        if not str(value or '').strip():
            return False, f'❌ {label} نمی‌تواند خالی باشد.'
    if fee_type not in {'fixed', 'percent'}:
        return False, '❌ نوع دستمزد نامعتبر است.'
    # Pricing is intentionally free-form. Do not reject a lawyer's entry
    # based on numeric format or a percentage ceiling; the listing is a
    # public description of the lawyer's requested fee.
    if not str(fee_value or '').strip():
        return False, '❌ مبلغ/درصد دستمزد نمی‌تواند خالی باشد.'
    if len(str(description or '')) > 2000:
        return False, '❌ توضیحات بیش از حد طولانی است.'
    return True, ''


async def _send_service_for_review(bot, row, license_file_id=None):
    """Send listing + optional license photo to every configured admin DM.

    Photo failures are no longer swallowed: we log the exact Telegram error and
    try a second send without reply threading before giving up.
    """
    if not row:
        return False
    if not ADMIN_TELEGRAM_IDS:
        logger.error('No ADMIN_TELEGRAM_IDS configured; service #%s cannot be sent to admins', row.get('id'))
        return False
    text = _service_admin_text(row)
    sent = False
    for aid in ADMIN_TELEGRAM_IDS:
        try:
            m = await bot.send_message(chat_id=aid, text=text, reply_markup=service_admin_keyboard(row['id']))
            sent = True
        except Exception as exc:
            logger.exception('Failed to send service #%s to admin %s: %s', row.get('id'), aid, exc)
            continue
        if license_file_id:
            caption = f'📷 پروانه وکالت — آگهی #{row["id"]} (صرفاً جهت بایگانی)'
            try:
                await bot.send_photo(chat_id=aid, photo=license_file_id, caption=caption, reply_to_message_id=m.message_id)
            except Exception as exc:
                logger.exception('Failed to send license photo for service #%s to admin %s (threaded): %s', row.get('id'), aid, exc)
                try:
                    await bot.send_photo(chat_id=aid, photo=license_file_id, caption=caption)
                except Exception as exc2:
                    logger.exception('Failed to send license photo for service #%s to admin %s (plain): %s', row.get('id'), aid, exc2)
    return sent


def payment_admin_keyboard(pid):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton('✅ تأیید و فعال‌سازی', callback_data=f'payok:{pid}'),
        InlineKeyboardButton('❌ رد رسید', callback_data=f'payno:{pid}'),
    ]])


def _payment_admin_text(row):
    caption = (row.get('receipt_caption') or '').strip()
    return (f'💳 رسید پرداخت اشتراک #{row["id"]}\n\n'
            f'👤 Telegram ID: {row["user_id"]}\n'
            f'📦 پلن: اشتراک ماهانه\n'
            f'🔖 کد پیگیری: {row.get("payment_reference") or "—"}\n'
            f'📅 وضعیت: {row["status"]}'
            + (f'\n📝 توضیح کاربر: {caption}' if caption else ''))


async def _send_payment_receipt_to_admins(bot, pid, user_id, file_id, caption=None):
    """Send a subscription receipt photo to every configured admin DM."""
    row = get_payment_request(pid) or {'id': pid, 'user_id': user_id, 'status': 'pending', 'receipt_caption': caption or ''}
    if not ADMIN_TELEGRAM_IDS:
        logger.error('No ADMIN_TELEGRAM_IDS configured; payment receipt #%s cannot be sent to admins', pid)
        return False
    text = _payment_admin_text(row)
    sent = False
    for aid in ADMIN_TELEGRAM_IDS:
        try:
            await bot.send_photo(chat_id=aid, photo=file_id, caption=text, reply_markup=payment_admin_keyboard(pid))
            sent = True
        except Exception as exc:
            logger.exception('Failed to send payment receipt #%s to admin %s: %s', pid, aid, exc)
            # The file_id is valid in normal Telegram photo updates. If the
            # photo send is rejected, still deliver the review item as text so
            # the admin can see the pending payment and the bot does not fail silently.
            try:
                await bot.send_message(chat_id=aid, text=text + '\n\n⚠️ ارسال خود عکس ناموفق بود؛ خطای Telegram در لاگ ثبت شد.', reply_markup=payment_admin_keyboard(pid))
                sent = True
            except Exception as exc2:
                logger.exception('Failed to send payment review text #%s to admin %s: %s', pid, aid, exc2)
    return sent


async def payment_admin_cb(update, context):
    q = update.callback_query
    if q.from_user.id not in ADMIN_TELEGRAM_IDS:
        await q.answer('دسترسی ندارید.', show_alert=True)
        return
    await q.answer()
    parts = q.data.split(':')
    if len(parts) != 2:
        return
    action, raw_pid = parts
    try:
        pid = int(raw_pid)
    except ValueError:
        return
    approved = action == 'payok'
    row = get_payment_request(pid)
    if not row:
        await q.message.reply_text('❌ رسید پیدا نشد.')
        return
    if row.get('status') != 'pending':
        await q.message.reply_text('ℹ️ این رسید قبلاً بررسی شده است.')
        return
    if not review_payment(pid, q.from_user.id, approved):
        await q.message.reply_text('❌ بررسی رسید انجام نشد.')
        return
    try:
        await q.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    if approved:
        label = '✅ پرداخت شما تأیید شد و اشتراک یک‌ماهه فعال شد.'
    else:
        label = '❌ رسید پرداخت شما تأیید نشد. در صورت نیاز، رسید صحیح را دوباره ارسال کنید.'
    try:
        await q.message.get_bot().send_message(chat_id=row['user_id'], text=label)
    except Exception:
        pass
    await q.message.reply_text('✅ رسید تأیید و اشتراک فعال شد.' if approved else '❌ رسید رد شد.')


async def service_add_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_registered(q): return
    _clear_pending_inputs(context, keep='service_name')
    context.user_data['service_name']=True
    await q.message.reply_text(SERVICE_INTRO + '\n\n📝 نام و نام خانوادگی خود را وارد کنید:')


async def myservices_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_registered(q): return
    _clear_pending_inputs(context)
    rows=list_service_listings(uid)
    if not rows:
        await q.message.reply_text('📋 هنوز خدمتی ثبت نکرده‌اید.'); return
    await q.message.reply_text('📋 خدمات ثبت‌شده شما:')
    for row in rows:
        status={'pending':'🟡 در انتظار بررسی','active':'🟢 فعال','rejected':'🔴 رد شده','deleted':'⚪ حذف شده'}.get(row['status'],row['status'])
        txt=(f"#{row['id']} — {row['service_title']}\n"
             f"📍 {row['city']} | 💰 {_service_fee_text(row)}\n"
             f"{status}")
        kb=InlineKeyboardMarkup([[InlineKeyboardButton('👁 مشاهده',callback_data=f'serviceview:{row["id"]}'), InlineKeyboardButton('✏️ ویرایش',callback_data=f'serviceedit:{row["id"]}'), InlineKeyboardButton('🗑 حذف',callback_data=f'servicedelete:{row["id"]}')]])
        await q.message.reply_text(txt,reply_markup=kb)
    await q.message.reply_text('⚖️ منوی اصلی:',reply_markup=menu(q.from_user.id if q and getattr(q, 'from_user', None) else None))



async def service_edit_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_registered(q): return
    try: lid=int(q.data.split(':')[1])
    except: return
    row=get_service_listing(lid)
    if not row or row['user_id']!=uid or row['status']=='deleted':
        await q.message.reply_text('❌ خدمت پیدا نشد.'); return
    _clear_pending_inputs(context, keep='service_edit_id')
    context.user_data['service_edit_id']=lid
    context.user_data['service_name_value']=row['full_name']
    context.user_data['service_phone_value']=row['phone']
    context.user_data['service_city_value']=row['city']
    context.user_data['service_specialty_value']=row['specialty']
    context.user_data['service_title_value']=row['service_title']
    context.user_data['service_fee_type_value']=row['fee_type']
    context.user_data['service_fee_value_value']=row['fee_value']
    context.user_data['service_description_value']=row.get('description') or ''
    context.user_data['service_charity']=bool(row.get('charitable'))
    context.user_data['service_edit_step']='name'
    await q.message.reply_text(f'✏️ ویرایش خدمت #{lid}\n\nنام و نام خانوادگی جدید را وارد کنید:')

async def service_view_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_registered(q): return
    _clear_pending_inputs(context)
    try: lid=int(q.data.split(':')[1])
    except: return
    row=get_service_listing(lid)
    if not row or row['user_id']!=uid or row['status']=='deleted':
        await q.message.reply_text('❌ خدمت پیدا نشد.'); return
    status={'pending':'🟡 در انتظار بررسی','active':'🟢 فعال','rejected':'🔴 رد شده'}.get(row['status'],row['status'])
    txt=(f"📋 خدمت #{row['id']}\n\n👤 {row['full_name']}\n📞 {row['phone']}\n📍 {row['city']}\n⚖️ {row['specialty']}\n💼 {row['service_title']}\n💰 {_service_fee_text(row)}\n"
         f"{'❤️ خدمت حمایتی' if row['charitable'] else ''}\n📝 {row['description'] or '—'}\n\n{status}")
    await q.message.reply_text(txt,reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('✏️ ویرایش',callback_data=f'serviceedit:{lid}'), InlineKeyboardButton('🗑 حذف این خدمت',callback_data=f'servicedelete:{lid}')]]))


async def service_delete_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_registered(q): return
    try: lid=int(q.data.split(':')[1])
    except: return
    if not delete_service_listing(uid,lid):
        await q.message.reply_text('❌ خدمت پیدا نشد یا قبلاً حذف شده.'); return
    await q.message.reply_text('✅ خدمت شما حذف شد.')


async def service_fee_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_registered(q): return
    if context.user_data.get('service_fee_type') not in {'fixed','percent'}:
        context.user_data['service_fee_type']=q.data.split(':')[1]
        context.user_data['service_fee_value_waiting']=True
        unit='تومان' if q.data.endswith('fixed') else 'درصد'
        context.user_data['service_fee_unit']=unit
        await q.message.reply_text(f'💰 مبلغ/درصد دستمزد موردنظر را وارد کنید ({unit}):')


async def service_charity_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_registered(q): return
    context.user_data['service_charity'] = q.data.endswith(':yes')
    if not context.user_data.get('service_license_photo'):
        context.user_data['service_license_photo'] = None
        context.user_data['service_license_photo_waiting'] = True
        await q.message.reply_text('📷 حالا لطفاً یک عکس واضح از پروانه وکالت خود ارسال کنید. این تصویر فقط برای بایگانی ادمین ارسال می‌شود و در آگهی عمومی نمایش داده نمی‌شود.')
        return
    if context.user_data.get('service_edit_step')=='charity':
        lid=context.user_data.get('service_edit_id')
        fee_type=context.user_data.get('service_fee_type','fixed')
        fee_value=context.user_data.get('service_fee_value','')
        okv, err=_validate_service_fields(context.user_data.get('service_name_value',''),context.user_data.get('service_phone_value',''),context.user_data.get('service_city_value',''),context.user_data.get('service_specialty_value',''),context.user_data.get('service_title_value',''),fee_type,fee_value,context.user_data.get('service_description_value',''))
        if not okv:
            await q.message.reply_text(err); return
        ok=update_service_listing(uid,lid,context.user_data['service_name_value'],context.user_data['service_phone_value'],context.user_data['service_city_value'],context.user_data['service_specialty_value'],context.user_data['service_title_value'],fee_type,fee_value,context.user_data.get('service_description_value',''),context.user_data.get('service_charity',False))
        row=get_service_listing(lid) if ok else None
        sent=await _send_service_for_review(q.message.get_bot(),row,context.user_data.get('service_license_photo')) if row else False
        for key in list(context.user_data):
            if key.startswith('service_'): context.user_data.pop(key,None)
        msg='✅ تغییرات ثبت شد و برای بررسی مجدد ارسال شد.' if ok and sent else ('✅ تغییرات ثبت شد، اما ارسال به کانال بررسی انجام نشد.' if ok else '❌ ویرایش انجام نشد.')
        await q.message.reply_text(msg)
        return
    context.user_data['service_description']=context.user_data.get('service_description','')
    await _finish_service_listing(q, context)


async def _finish_service_edit_after_license(update, context):
    q = update.effective_message
    uid = update.effective_user.id
    lid = context.user_data.get('service_edit_id')
    fee_type = context.user_data.get('service_fee_type','fixed')
    fee_value = context.user_data.get('service_fee_value','')
    okv, err = _validate_service_fields(
        context.user_data.get('service_name_value',''), context.user_data.get('service_phone_value',''),
        context.user_data.get('service_city_value',''), context.user_data.get('service_specialty_value',''),
        context.user_data.get('service_title_value',''), fee_type, fee_value,
        context.user_data.get('service_description_value',''))
    if not okv:
        await q.reply_text(err); return
    ok = update_service_listing(uid, lid, context.user_data['service_name_value'], context.user_data['service_phone_value'],
                                context.user_data['service_city_value'], context.user_data['service_specialty_value'],
                                context.user_data['service_title_value'], fee_type, fee_value,
                                context.user_data.get('service_description_value',''), context.user_data.get('service_charity',False))
    row = get_service_listing(lid) if ok else None
    sent = await _send_service_for_review(q.get_bot(), row, context.user_data.get('service_license_photo')) if row else False
    for key in list(context.user_data):
        if key.startswith('service_'): context.user_data.pop(key,None)
    msg = '✅ تغییرات ثبت شد و آگهی و تصویر پروانه برای ادمین ارسال شد.' if ok and sent else ('✅ تغییرات ثبت شد، اما ارسال برای ادمین انجام نشد.' if ok else '❌ ویرایش انجام نشد.')
    await q.reply_text(msg)


async def _finish_service_listing_from_photo(update, context):
    # The photo completes the new-listing flow. Reuse the existing validation/storage path.
    class _Q:
        def __init__(self, message, user): self.message=message; self.from_user=user
    await _finish_service_listing(_Q(update.effective_message, update.effective_user), context)


async def _finish_service_listing(q, context):
    uid=q.from_user.id
    fee_type=context.user_data.get('service_fee_type')
    fee_value=context.user_data.get('service_fee_value','')
    ok, err=_validate_service_fields(
        context.user_data.get('service_name_value',''), context.user_data.get('service_phone_value',''),
        context.user_data.get('service_city_value',''), context.user_data.get('service_specialty_value',''),
        context.user_data.get('service_title_value',''), fee_type, fee_value,
        context.user_data.get('service_description_value',''))
    if not ok:
        await q.message.reply_text(err); return
    lid=create_service_listing(uid,context.user_data['service_name_value'],context.user_data['service_phone_value'],context.user_data['service_city_value'],context.user_data['service_specialty_value'],context.user_data['service_title_value'],fee_type,fee_value,context.user_data.get('service_description_value',''),context.user_data.get('service_charity',False))
    row=get_service_listing(lid)
    sent=await _send_service_for_review(q.message.get_bot(), row, context.user_data.get('service_license_photo'))
    for key in list(context.user_data):
        if key.startswith('service_'): context.user_data.pop(key,None)
    if sent:
        msg='✅ خدمت شما ثبت شد و برای بررسی ارسال شد.'
    else:
        msg='✅ خدمت شما ثبت شد و در انتظار بررسی است. وضعیت خدمت را از بخش «خدمات من و وضعیت معرفی» پیگیری کنید.'
    await q.message.reply_text(msg)


async def service_admin_cb(update, context):
    q=update.callback_query
    if q.from_user.id not in ADMIN_TELEGRAM_IDS:
        await q.answer('دسترسی ندارید.',show_alert=True); return
    await q.answer()
    parts=q.data.split(':')
    try: lid=int(parts[2])
    except: return
    action=parts[1]
    row=get_service_listing(lid)
    if not row:
        await q.message.reply_text('❌ خدمت پیدا نشد.'); return
    new_status='active' if action=='approve' else 'rejected'
    set_service_status(lid,new_status)
    await q.message.edit_reply_markup(reply_markup=None)
    label='✅ خدمت تأیید و فعال شد.' if new_status=='active' else '❌ خدمت رد شد.'
    await q.message.reply_text(label)
    try:
        await q.message.get_bot().send_message(chat_id=row['user_id'],text=label)
    except Exception: pass


# --- Source-grounded legal brief assistant ---
def brief_menu():
    rows=[]
    # If a case is already active, make the shortest path the most prominent.
    # The callback remains the same so old deployments do not need migration.
    rows.append([InlineKeyboardButton('📁 لایحه از پرونده فعال',callback_data='brief:case')])
    rows.append([InlineKeyboardButton('🧠 تکمیل هوشمند اطلاعات پرونده',callback_data='brief:info')])
    rows += [
        [InlineKeyboardButton('🆕 لایحه جدید',callback_data='brief:new')],
        [InlineKeyboardButton('📂 انتخاب یک پرونده',callback_data='brief:case')],
        [InlineKeyboardButton('✏️ بررسی/تقویت لایحه موجود',callback_data='brief:edit')],
        [InlineKeyboardButton('📦 قالب‌های آماده موضوعات پرتکرار',callback_data='brief:templates')],
        [InlineKeyboardButton('↩️ منوی اصلی',callback_data='home')],
    ]
    return InlineKeyboardMarkup(rows)

def brief_type_keyboard():
    rows=[]
    for i,x in enumerate(BRIEF_TYPES):
        rows.append([InlineKeyboardButton(x,callback_data=f'brieftype:{i}')])
    rows.append([InlineKeyboardButton('↩️ لایحه‌نویسی',callback_data='briefs')])
    return InlineKeyboardMarkup(rows)

BRIEF_TYPES=['لایحه دفاعیه','پاسخ به لایحه طرف مقابل','اعتراض/درخواست','لایحه تجدیدنظرخواهی','لایحه مطالبه/خواسته','لایحه اعسار/تقسیط','سایر']
BRIEF_STAGES=['دادگاه بدوی','تجدیدنظر','فرجام','دادسرا/کیفری','اجرای احکام','دیوان عدالت اداری','سایر']

def brief_stage_keyboard():
    # Kept for callback compatibility with older conversations.
    rows=[[InlineKeyboardButton(x,callback_data=f'briefstage:{i}')] for i,x in enumerate(BRIEF_STAGES)]
    rows.append([InlineKeyboardButton('↩️ لایحه‌نویسی',callback_data='briefs')])
    return InlineKeyboardMarkup(rows)


def brief_templates_keyboard():
    rows = []
    for key, title in list_templates():
        rows.append([InlineKeyboardButton(title, callback_data=f'brieftpl:{key}')])
    rows.append([InlineKeyboardButton('↩️ لایحه‌نویسی', callback_data='briefs')])
    return InlineKeyboardMarkup(rows)


async def brief_templates_cb(update, context):
    q = update.callback_query
    await q.answer()
    if not await _require_lawyer(q, context, 'briefs'):
        return
    _clear_pending_inputs(context)
    await q.message.reply_text(
        "📦 قالب‌های آماده\n\n"
        "یک موضوع پرتکرار را انتخاب کنید. متن اسکلت با جای خالی می‌آید؛ "
        "باید با مشخصات پرونده پر و توسط وکیل بازبینی شود.",
        reply_markup=brief_templates_keyboard(),
    )


async def brief_template_pick_cb(update, context):
    q = update.callback_query
    await q.answer()
    if not await _require_lawyer(q, context, 'briefs'):
        return
    key = q.data.split(':', 1)[1]
    try:
        text = get_template(key)
    except Exception:
        await q.message.reply_text('❌ قالب پیدا نشد.', reply_markup=brief_templates_keyboard())
        return
    await reply_long(q.message, text)
    await q.message.reply_text(
        "می‌توانید همین متن را ویرایش کنید یا از «بررسی/تقویت لایحه موجود» برای کنترل ساختاری بفرستید.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton('▶️ شروع تنظیم با این قالب', callback_data=f'brieftpluse:{key}')],
            [InlineKeyboardButton('📦 قالب دیگر', callback_data='brief:templates')],
            [InlineKeyboardButton('✏️ بررسی لایحه موجود', callback_data='brief:edit')],
            [InlineKeyboardButton('📝 منوی لایحه', callback_data='briefs')],
        ]),
    )



async def brief_template_use_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_lawyer(q, context, 'briefs'): return
    key=q.data.split(':',1)[1]
    meta=TEMPLATES.get(key)
    if not meta:
        await q.message.reply_text('❌ قالب پیدا نشد.',reply_markup=brief_templates_keyboard()); return
    context.user_data['brief_template_key']=key
    context.user_data['brief_type']=meta.get('brief_type') or 'لایحه دفاعیه'
    await q.message.reply_text(
        f"📦 قالب «{meta.get('title','قالب منتخب')}» انتخاب شد.\n\n"
        "این قالب اسکلت اختصاصی این نوع لایحه را تعیین می‌کند؛ اطلاعات پرونده و منابع انتخاب‌شده در همان ساختار تطبیق داده می‌شوند.\n\n"
        "از کدام مسیر ادامه دهیم؟",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton('📁 استفاده از پرونده فعال',callback_data='brief:case')],
            [InlineKeyboardButton('🆕 وارد کردن اطلاعات جدید',callback_data='brief:new')],
            [InlineKeyboardButton('↩️ قالب‌ها',callback_data='brief:templates')],
        ]))


def quiz_categories_keyboard():
    """Legacy flat list — prefer term keyboard."""
    rows = []
    for c in quiz_categories()[:20]:
        rows.append([InlineKeyboardButton(
            f"{c['title']} ({c['count']})",
            callback_data=f"quiz:cat:{c['id']}",
        )])
    rows.append([InlineKeyboardButton("🏠 منوی اصلی", callback_data="home")])
    return InlineKeyboardMarkup(rows)


def quiz_terms_keyboard():
    """Levels list (سال اول کارشناسی ... دکتری)."""
    rows = []
    for t in quiz_list_levels():
        rows.append([InlineKeyboardButton(t["title"], callback_data=f"quiz:term:{t['id']}")])
    rows.append([InlineKeyboardButton("↩️ نوع تمرین", callback_data="quiz")])
    return InlineKeyboardMarkup(rows)


def quiz_courses_keyboard(level_id):
    rows = []
    for c in quiz_list_courses(level_id):
        rows.append([InlineKeyboardButton(
            f"{c['title']} ({c['count']} سوال)",
            callback_data=f"quiz:cat:{c['id']}",
        )])
    rows.append([InlineKeyboardButton("↩️ انتخاب سال", callback_data="quiz:mode:mcq")])
    return InlineKeyboardMarkup(rows)



def quiz_options_keyboard(qid_token):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("۱", callback_data=f"quiz:ans:{qid_token}:0"),
            InlineKeyboardButton("۲", callback_data=f"quiz:ans:{qid_token}:1"),
            InlineKeyboardButton("۳", callback_data=f"quiz:ans:{qid_token}:2"),
            InlineKeyboardButton("۴", callback_data=f"quiz:ans:{qid_token}:3"),
        ],
        [InlineKeyboardButton("📚 دسته دیگر", callback_data="quiz"),
         InlineKeyboardButton("🏠 منو", callback_data="home")],
    ])


async def quiz_cb(update, context):
    q = update.callback_query
    await q.answer()
    if not await _require_registered(q):
        return
    _clear_pending_inputs(context)
    context.user_data.pop("quiz_session", None)
    context.user_data.pop("essay_session", None)
    await q.message.reply_text(
        "🎓 آزمون و تمرین دانشجویی\n\n"
        + quiz_disclaimer()
        + "\n\nنوع تمرین را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 تست چهارگزینه‌ای", callback_data="quiz:mode:mcq")],
            [InlineKeyboardButton("✍️ سوالات تشریحی", callback_data="quiz:mode:essay")],
            [InlineKeyboardButton("🏠 منوی اصلی", callback_data="home")],
        ]),
    )


async def quiz_mode_cb(update, context):
    q = update.callback_query
    await q.answer()
    if not await _require_registered(q):
        return
    mode = q.data.split(":")[-1]
    if mode == "mcq":
        await q.message.reply_text(
            "📝 مقطع و سال را انتخاب کنید:\n"
            "(دروس عمومی دانشگاه پوشش داده نشده‌اند)\n\n"
            + quiz_disclaimer(),
            reply_markup=quiz_terms_keyboard(),
        )
    else:
        await q.message.reply_text(
            "✍️ دسته تشریحی را انتخاب کنید:\n\n" + quiz_essay_disclaimer(),
            reply_markup=quiz_essay_categories_keyboard(),
        )


def quiz_essay_categories_keyboard():
    rows = []
    for c in quiz_essay_categories():
        rows.append([InlineKeyboardButton(
            f"{c['title']} ({c['count']})",
            callback_data=f"quiz:essaycat:{c['id']}",
        )])
    rows.append([InlineKeyboardButton("↩️ بازگشت", callback_data="quiz")])
    return InlineKeyboardMarkup(rows)


async def quiz_essay_cat_cb(update, context):
    q = update.callback_query
    await q.answer()
    if not await _require_registered(q):
        return
    cat = q.data.split(":")[-1]
    items = quiz_get_essay(cat, limit=5, shuffle=True)
    if not items:
        await q.message.reply_text("سوالی نیست.", reply_markup=quiz_essay_categories_keyboard())
        return
    context.user_data["essay_session"] = {
        "cat": cat, "items": items, "index": 0, "total": len(items),
    }
    await _essay_send_current(q.message, context)


async def _essay_send_current(msg, context):
    sess = context.user_data.get("essay_session") or {}
    items = sess.get("items") or []
    idx = int(sess.get("index") or 0)
    if idx >= len(items):
        context.user_data.pop("essay_session", None)
        await msg.reply_text(
            "🏁 پایان این سری تشریحی\n\n" + quiz_essay_disclaimer(),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✍️ دسته دیگر", callback_data="quiz:mode:essay")],
                [InlineKeyboardButton("🎓 منوی آزمون", callback_data="quiz")],
            ]),
        )
        return
    item = items[idx]
    context.user_data["essay_current"] = item
    text = quiz_format_essay(item, idx + 1, len(items))
    token = f"{sess.get('cat')}_{idx}"
    await msg.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💡 نمایش پاسخ نمونه", callback_data=f"quiz:essayshow:{token}")],
            [InlineKeyboardButton("⏭️ سوال بعد", callback_data=f"quiz:essaynext:{token}")],
            [InlineKeyboardButton("↩️ دسته‌ها", callback_data="quiz:mode:essay")],
        ]),
    )


async def quiz_essay_show_cb(update, context):
    q = update.callback_query
    await q.answer()
    parts = q.data.split(":")
    token = parts[2] if len(parts) >= 3 else ""
    sess = context.user_data.get("essay_session") or {}
    idx = int(sess.get("index") or 0)
    expected = f"{sess.get('cat')}_{idx}" if sess else ""
    if not sess or token != expected:
        await q.message.reply_text("این دکمه مربوط به سؤال قبلی است. لطفاً سؤال فعلی را استفاده کنید.")
        return
    item = context.user_data.get("essay_current") or {}
    sample = item.get("sample") or "پاسخ نمونه موجود نیست."
    await q.message.reply_text(
        "💡 پاسخ نمونه:\n\n" + sample + "\n\n⚠️ راهنمای مطالعه است، نه کلید رسمی.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⏭️ سوال بعد", callback_data=f"quiz:essaynext:{expected}")],
            [InlineKeyboardButton("↩️ دسته‌ها", callback_data="quiz:mode:essay")],
        ]),
    )


async def quiz_essay_next_cb(update, context):
    q = update.callback_query
    await q.answer()
    parts = q.data.split(":")
    token = parts[2] if len(parts) >= 3 else ""
    sess = context.user_data.get("essay_session") or {}
    idx = int(sess.get("index") or 0)
    expected = f"{sess.get('cat')}_{idx}" if sess else ""
    if not sess:
        await q.message.reply_text("نشست فعال نیست.", reply_markup=quiz_categories_keyboard())
        return
    if token != expected:
        await q.message.reply_text("این دکمه مربوط به سؤال قبلی است. لطفاً سؤال فعلی را استفاده کنید.")
        return
    sess["index"] = idx + 1
    context.user_data["essay_session"] = sess
    await _essay_send_current(q.message, context)



async def quiz_term_cb(update, context):
    q = update.callback_query
    await q.answer()
    if not await _require_registered(q):
        return
    term = q.data.split(":")[-1]
    courses = quiz_list_courses(term)
    if not courses:
        await q.message.reply_text("برای این ترم درسی ثبت نشده.", reply_markup=quiz_terms_keyboard())
        return
    await q.message.reply_text(
        "📚 دروس پرکاربرد این سال:\n"
        "هر درس حداقل حدود ۱۰ سوال تمرین دارد.",
        reply_markup=quiz_courses_keyboard(term),
    )


async def quiz_cat_cb(update, context):
    q = update.callback_query
    await q.answer()
    if not await _require_registered(q):
        return
    cat = q.data.split(":")[-1]
    questions = quiz_get_questions(cat, limit=10, shuffle=True)
    if not questions:
        await q.message.reply_text("در این دسته سوالی نیست.", reply_markup=quiz_categories_keyboard())
        return
    context.user_data["quiz_session"] = {
        "cat": cat,
        "questions": questions,
        "index": 0,
        "correct": 0,
        "total": len(questions),
    }
    await _quiz_send_current(q.message, context)


async def _quiz_send_current(msg, context):
    sess = context.user_data.get("quiz_session") or {}
    qs = sess.get("questions") or []
    idx = int(sess.get("index") or 0)
    if idx >= len(qs):
        total = int(sess.get("total") or 0)
        correct = int(sess.get("correct") or 0)
        context.user_data.pop("quiz_session", None)
        await msg.reply_text(
            f"🏁 پایان این سری\n\nپاسخ درست: {correct} از {total}\n\n"
            + quiz_disclaimer(),
            reply_markup=quiz_categories_keyboard(),
        )
        return
    question = qs[idx]
    token = f"{sess.get('cat')}_{idx}"
    context.user_data["quiz_current"] = question
    text = quiz_format_question(question, idx + 1, len(qs))
    await msg.reply_text(text, reply_markup=quiz_options_keyboard(token))


async def quiz_ans_cb(update, context):
    q = update.callback_query
    await q.answer()
    if not await _require_registered(q):
        return
    parts = q.data.split(":")
    # quiz:ans:token:choice
    if len(parts) < 4:
        return
    token = parts[2]
    try:
        choice = int(parts[-1])
    except Exception:
        return
    sess = context.user_data.get("quiz_session")
    question = context.user_data.get("quiz_current")
    expected_token = f"{sess.get('cat')}_{int(sess.get('index') or 0)}" if sess else None
    # Reject stale buttons from an older question/message. Telegram can deliver
    # a callback from an old inline keyboard after the current question changed.
    if not expected_token or token != expected_token:
        await q.message.reply_text("این گزینه مربوط به سؤال قبلی است. لطفاً گزینه‌های سؤال فعلی را انتخاب کنید.")
        return
    if not sess or not question:
        await q.message.reply_text("نشست آزمون فعال نیست.", reply_markup=quiz_categories_keyboard())
        return
    ok, feedback = quiz_check_answer(question, choice)
    if ok:
        sess["correct"] = int(sess.get("correct") or 0) + 1
    sess["index"] = int(sess.get("index") or 0) + 1
    context.user_data["quiz_session"] = sess
    await q.message.reply_text(feedback)
    await _quiz_send_current(q.message, context)


async def briefs_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_lawyer(q, context, 'briefs'): return
    _clear_pending_inputs(context)
    active=get_active_case_id(q.from_user.id)
    hint='\n\n🟢 یک پرونده فعال دارید؛ «لایحه از پرونده فعال» کوتاه‌ترین مسیر است.' if active else ''
    await q.message.reply_text(
        '📝 تنظیم و بررسی لایحه\n\n'
        'پیش‌نویس از متن پرونده/حقایق شما ساخته می‌شود (استخراجی، نه هوش مصنوعی).\n'
        'استناد و خواسته نهایی را قبل از تقدیم حتماً بازبینی کنید.\n'
        'اگر پرونده فعال دارید، کوتاه‌ترین مسیر «لایحه از پرونده فعال» است.'+hint,
        reply_markup=brief_menu())

async def brief_information_start_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_lawyer(q, context, 'briefs'): return
    cid=context.user_data.get('brief_case_id') or get_active_case_id(q.from_user.id)
    if cid and get_case(q.from_user.id,cid):
        context.user_data['brief_case_id']=cid
        context.user_data.setdefault('brief_type','لایحه دفاعیه')
        context.user_data.setdefault('brief_v150_answers',{})
        await _brief_run_information_resolver(q.message, context, q.from_user.id, context.user_data.get('brief_facts_value',''))
    else:
        context.user_data['brief_mode']='new'
        context.user_data.setdefault('brief_type','لایحه دفاعیه')
        context.user_data.setdefault('brief_v150_answers',{})
        context.user_data['brief_facts']=True
        await q.message.reply_text('✍️ برای تکمیل هوشمند، شرح کوتاه ماجرا، خواسته و هر مدرکی که می‌دانید را بنویسید. بات ابتدا همان اطلاعات را به‌صورت محلی بررسی می‌کند.')


async def brief_mode_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_lawyer(q, context, 'briefs'): return
    mode=q.data.split(':')[1]
    context.user_data['brief_mode']=mode
    if mode=='case':
        active=get_active_case_id(q.from_user.id)
        if active and get_case(q.from_user.id, active):
            context.user_data['brief_case_id']=active
            await q.message.reply_text('📁 پرونده فعال انتخاب شد.\n\n📝 نوع لایحه را انتخاب کنید:',reply_markup=brief_type_keyboard())
            return
        cases=list_cases(q.from_user.id,20)
        if not cases:
            await q.message.reply_text('📁 پرونده‌ای برای انتخاب وجود ندارد. ابتدا پرونده جدید ثبت کنید.',reply_markup=brief_menu()); return
        rows=[[InlineKeyboardButton(f'#{c["case_no"]} {c["file_name"] or "پرونده"}'[:55],callback_data=f'briefcase:{c["id"]}')] for c in cases]
        rows.append([InlineKeyboardButton('↩️ لایحه‌نویسی',callback_data='briefs')])
        await q.message.reply_text('📁 پرونده را انتخاب کنید:',reply_markup=InlineKeyboardMarkup(rows)); return
    await q.message.reply_text('📝 نوع لایحه را انتخاب کنید:',reply_markup=brief_type_keyboard())

async def brief_type_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_lawyer(q, context, 'briefs'): return
    try: idx=int(q.data.split(':')[1]); context.user_data['brief_type']=BRIEF_TYPES[idx]
    except Exception: return
    context.user_data['brief_v150_answers']={}
    context.user_data['brief_v150_deferred']=set()
    context.user_data['brief_v150_confirmed']=False
    mode=context.user_data.get('brief_mode','new')
    if mode=='case':
        # V150 resolves the case locally before source selection.
        await _brief_run_information_resolver(q.message, context, q.from_user.id, '')
        return
    context.user_data['brief_facts']=True
    if mode == 'edit':
        await q.message.reply_text('✏️ متن لایحه موجود را کامل ارسال کنید.\n\nبررسی اولیه و نسخه پیشنهادی جداگانه ارائه می‌شود؛ متن اصلی شما دست‌کاری نمی‌شود.')
    else:
        await q.message.reply_text('✍️ فقط شرح ماجرا، خواسته یا نکته‌ای را که می‌خواهید در لایحه بیاید بنویسید. اطلاعات تکمیلیِ قابل استخراج دوباره از شما پرسیده نمی‌شود.')

async def brief_stage_cb(update, context):
    # Backward-compatible handler; stage is now optional and no longer a required step.
    q=update.callback_query; await q.answer()
    if not await _require_lawyer(q, context, 'briefs'): return
    try: idx=int(q.data.split(':')[1]); context.user_data['brief_stage']=BRIEF_STAGES[idx]
    except Exception: return
    context.user_data['brief_facts']=True
    await q.message.reply_text('✍️ اطلاعات تکمیلی لایحه را ارسال کنید:')

async def brief_case_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_lawyer(q, context, 'briefs'): return
    uid=q.from_user.id
    try: cid=int(q.data.split(':')[1])
    except Exception: return
    case=get_case(uid,cid)
    if not case:
        await q.message.reply_text('❌ پرونده پیدا نشد.',reply_markup=brief_menu()); return
    set_active_case(uid,cid)
    context.user_data['brief_case_id']=cid
    context.user_data['brief_mode']='case'
    await q.message.reply_text('📁 پرونده انتخاب شد.\n\n📝 نوع لایحه را انتخاب کنید:',reply_markup=brief_type_keyboard())

# Override the facts entry for case mode: prepend the stored case text automatically.

# --- Lightweight legal calculator prototype ---
# Prototype uses a small, explicit annual-index table. The calculation engine is
# deterministic and does not call AI. The table is deliberately isolated so it
# can later be replaced/updated from verified official index releases.
MAHR_FIXED_AMOUNT = 10_000_000

# نرخ رسمی دیه کامل سال ۱۴۰۵ (تومان)
DIYA_1405_NORMAL = 2_100_000_000
DIYA_1405_HARAM = 2_800_000_000
def _fa_num(n):
    return str(n).translate(str.maketrans('0123456789,.','۰۱۲۳۴۵۶۷۸۹٫٬'))

def _parse_amount(value):
    trans=str.maketrans('۰۱۲۳۴۵۶۷۸۹٬،٫','0123456789,,.')
    s=value.translate(trans).replace(',','').replace('٬','').replace('،','').replace('٫','.')
    s=re.sub(r'[^0-9.]','',s)
    if not s: return None
    try: return float(s)
    except ValueError: return None


def tax_activity_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('🛍️ فروش کالا / آنلاین‌شاپ', callback_data='tax:act:shop')],
        [InlineKeyboardButton('🔧 خدمات / فریلنسری', callback_data='tax:act:service')],
        [InlineKeyboardButton('🏠 اجاره ملک', callback_data='tax:act:rent')],
        [InlineKeyboardButton('🤝 پورسانتی / کارمزدی', callback_data='tax:act:commission')],
        [InlineKeyboardButton('🏡 کسب‌وکار خانگی', callback_data='tax:act:home')],
        [InlineKeyboardButton('❓ سایر / مطمئن نیستم', callback_data='tax:act:other')],
    ])


def tax_task_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('🆕 ثبت‌نام و شروع کار', callback_data='tax:task:register')],
        [InlineKeyboardButton('📝 تکمیل اظهارنامه / فرم', callback_data='tax:task:return')],
        [InlineKeyboardButton('📄 بررسی برگه یا ابلاغیه', callback_data='tax:task:notice')],
        [InlineKeyboardButton('💰 کاهش قانونی مالیات', callback_data='tax:task:reduce')],
        [InlineKeyboardButton('❓ نمی‌دانم از کجا شروع کنم', callback_data='tax:task:unknown')],
    ])


def tax_income_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('زیر ۱۰۰ میلیون', callback_data='tax:income:low'), InlineKeyboardButton('۱۰۰ تا ۵۰۰ میلیون', callback_data='tax:income:mid')],
        [InlineKeyboardButton('۵۰۰ میلیون تا ۱ میلیارد', callback_data='tax:income:high')],
        [InlineKeyboardButton('بیش از ۱ میلیارد', callback_data='tax:income:large'), InlineKeyboardButton('نمی‌دانم', callback_data='tax:income:unknown')],
    ])


def tax_docs_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('✅ بله، مدارک دارم', callback_data='tax:docs:yes'), InlineKeyboardButton('❌ نه / ناقص است', callback_data='tax:docs:no')],
        [InlineKeyboardButton('🤷 نمی‌دانم چه مدرکی لازم است', callback_data='tax:docs:unknown')],
    ])


async def taxhelp_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_registered(q): return
    _clear_pending_inputs(context)
    context.user_data['tax_flow']={}
    await q.message.reply_text(
        '🧾 کمک مالیاتی\n\n'
        'با چند سؤال ساده، یک راهنمای شخصی برای کار مالیاتی‌ات می‌سازیم.\n'
        'این بخش فرم رسمی را پر یا ارسال نمی‌کند؛ فقط می‌گوید چه چیزهایی را بررسی و کجا چه اطلاعاتی را آماده کنی.\n\n'
        'اول بگو بیشتر چه نوع درآمدی داری:',
        reply_markup=tax_activity_keyboard())


async def tax_screen_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_registered(q): return
    context.user_data['tax_screen_waiting']=True
    await q.message.reply_text('📸 عکس همان صفحه مالیاتی را بفرست.\n\nترجیحاً تصویر واضح و کامل باشد؛ LegalBot فقط برای توضیح و راهنمایی آن را بررسی می‌کند و فرم رسمی را پر یا ارسال نمی‌کند.')


async def tax_activity_cb(update, context):
    q=update.callback_query; await q.answer()
    flow=context.user_data.setdefault('tax_flow',{})
    flow['activity']=q.data.split(':')[2]
    await q.message.reply_text('🎯 الان بیشتر برای کدام کار مالیاتی کمک می‌خواهی؟', reply_markup=tax_task_keyboard())


async def tax_task_cb(update, context):
    q=update.callback_query; await q.answer()
    flow=context.user_data.setdefault('tax_flow',{})
    flow['task']=q.data.split(':')[2]
    await q.message.reply_text('💰 حدود درآمد سالانه‌ات در چه بازه‌ای است؟\n\nاگر دقیق نمی‌دانی، «نمی‌دانم» را بزن.', reply_markup=tax_income_keyboard())


async def tax_income_cb(update, context):
    q=update.callback_query; await q.answer()
    flow=context.user_data.setdefault('tax_flow',{})
    flow['income']=q.data.split(':')[2]
    await q.message.reply_text('📎 برای درآمد و هزینه‌ها مدارک یا رسید داری؟', reply_markup=tax_docs_keyboard())


async def tax_docs_cb(update, context):
    q=update.callback_query; await q.answer()
    flow=context.user_data.setdefault('tax_flow',{})
    flow['docs']=q.data.split(':')[2]
    result=build_tax_guide(flow)
    # V72: keep tax_flow so screenshot guide can use prior answers
    await reply_long(q.message, result)
    await q.message.reply_text('اگر الان صفحه‌ای از سامانه جلوی توست، 📸 عکس همان صفحه را بفرست؛ بدون نیاز به AI، متن و بخش‌های قابل تشخیص صفحه را محلی بررسی می‌کنیم.', reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton('📸 بررسی عکس صفحه مالیاتی', callback_data='taxscreen')],
        [InlineKeyboardButton('🧾 شروع دوباره کمک مالیاتی', callback_data='taxhelp')],
        [InlineKeyboardButton('🏠 منوی اصلی', callback_data='home')]
    ]))


def shora_topic_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 چک / سفته / طلب مالی", callback_data="shora:topic:check")],
        [InlineKeyboardButton("🏠 اجاره و تخلیه", callback_data="shora:topic:rent")],
        [InlineKeyboardButton("🔧 خسارت جزئی", callback_data="shora:topic:damage")],
        [InlineKeyboardButton("🏢 اختلاف همسایگی", callback_data="shora:topic:neighbor")],
        [InlineKeyboardButton("❓ سایر / مطمئن نیستم", callback_data="shora:topic:other")],
    ])


def shora_amount_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("زیر ۵۰ میلیون", callback_data="shora:amount:low"),
         InlineKeyboardButton("۵۰ تا ۱۰۰ میلیون", callback_data="shora:amount:mid")],
        [InlineKeyboardButton("بیش از ۱۰۰ میلیون", callback_data="shora:amount:high"),
         InlineKeyboardButton("نمی‌دانم", callback_data="shora:amount:unknown")],
    ])


def shora_docs_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ مدرک مکتوب دارم", callback_data="shora:docs:yes")],
        [InlineKeyboardButton("📄 مدرک ناقص دارم", callback_data="shora:docs:partial")],
        [InlineKeyboardButton("❌ مدرک مکتوب ندارم", callback_data="shora:docs:no")],
    ])


async def shora_cb(update, context):
    q = update.callback_query
    await q.answer()
    if not await _require_registered(q):
        return
    _clear_pending_inputs(context)
    context.user_data["shora_flow"] = {}
    await q.message.reply_text(
        "⚖️ راهنمای شورای حل اختلاف و دادگاه صلح\n\n"
        "با چند سؤال کوتاه، یک چک‌لیست و مسیر پیشنهادی برای موضوع‌ات می‌سازیم.\n"
        "این بخش پرونده ثبت نمی‌کند و جایگزین مشاوره تخصصی نیست.\n\n"
        "موضوع اصلی اختلاف چیست؟",
        reply_markup=shora_topic_keyboard(),
    )


async def shora_topic_cb(update, context):
    q = update.callback_query
    await q.answer()
    flow = context.user_data.setdefault("shora_flow", {})
    flow["topic"] = q.data.split(":")[2]
    await q.message.reply_text(
        "💰 حدود مبلغ یا ارزش خواسته‌ات تقریباً چقدر است؟",
        reply_markup=shora_amount_keyboard(),
    )


async def shora_amount_cb(update, context):
    q = update.callback_query
    await q.answer()
    flow = context.user_data.setdefault("shora_flow", {})
    flow["amount"] = q.data.split(":")[2]
    await q.message.reply_text(
        "📎 برای این موضوع مدرک مکتوب (قرارداد، چک، رسید و...) داری؟",
        reply_markup=shora_docs_keyboard(),
    )


async def shora_docs_cb(update, context):
    q = update.callback_query
    await q.answer()
    flow = context.user_data.setdefault("shora_flow", {})
    flow["docs"] = q.data.split(":")[2]
    result = build_shora_guide(flow)
    context.user_data.pop("shora_flow", None)
    await reply_long(q.message, result)
    await q.message.reply_text(
        "اگر می‌خواهی موضوع دیگری را بررسی کنی یا به منو برگردی:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⚖️ موضوع جدید شورای حل اختلاف", callback_data="shora")],
            [InlineKeyboardButton("🧾 کمک مالیاتی", callback_data="taxhelp")],
            [InlineKeyboardButton("🏠 منوی اصلی", callback_data="home")],
        ]),
    )



def quick_calculator_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('🔢 درصد از مبلغ', callback_data='calc:quick:percent')],
        [InlineKeyboardButton('💱 تومان ↔ ریال', callback_data='calc:quick:rial')],
        [InlineKeyboardButton('➗ قسط‌بندی مبلغ', callback_data='calc:quick:installment')],
        [InlineKeyboardButton('📆 فاصله دو تاریخ', callback_data='calc:quick:datediff')],
        [InlineKeyboardButton('↩️ محاسبات حقوقی', callback_data='calculators')],
    ])


def calendar_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('🗓 تاریخ امروز ایران', callback_data='calc:calendar:today')],
        [InlineKeyboardButton('🔄 تبدیل تاریخ شمسی ↔ میلادی', callback_data='calc:calendar:convert')],
        [InlineKeyboardButton('⏳ محاسبه فاصله دو تاریخ', callback_data='calc:quick:datediff')],
        [InlineKeyboardButton('📅 مهلت ۲۰ روزه', callback_data='calc:deadline')],
        [InlineKeyboardButton('📌 تاریخ‌های مهم پرونده‌ها', callback_data='importantdates')],
        [InlineKeyboardButton('↩️ محاسبات حقوقی', callback_data='calculators')],
    ])


def _fmt_gregorian(d):
    return f'{d.year:04d}/{d.month:02d}/{d.day:02d}'


def _fmt_jalali(d):
    y,m,day=gregorian_to_jalali(d)
    return f'{y:04d}/{m:02d}/{day:02d}'


def _fa_num_text(s):
    return str(s).translate(str.maketrans('0123456789','۰۱۲۳۴۵۶۷۸۹'))


def _iran_now_from_telegram(update):
    msg = update.effective_message
    stamp = getattr(msg, 'date', None)
    if stamp is None:
        stamp = datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(ZoneInfo('Asia/Tehran'))


def _calendar_today_text(update):
    now = _iran_now_from_telegram(update)
    gd = now.date()
    jy,jm,jd = gregorian_to_jalali(gd)
    weekday = ['دوشنبه','سه‌شنبه','چهارشنبه','پنجشنبه','جمعه','شنبه','یکشنبه'][gd.weekday()]
    return (f'🗓 تقویم امروز ایران\n\n'
            f'📅 شمسی: {_fa_num_text(f"{jy:04d}/{jm:02d}/{jd:02d}")}\n'
            f'🌍 میلادی: {_fa_num_text(gd.strftime("%Y/%m/%d"))}\n'
            f'🕐 ساعت ایران: {_fa_num_text(now.strftime("%H:%M"))}\n'
            f'📍 منطقه زمانی: ایران (Asia/Tehran)\n'
            f'📨 زمان مبنا: تاریخ/زمان ثبت پیام در تلگرام\n'
            f'🗓 روز هفته: {weekday}')


def _calculator_back_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton('🧮 محاسبات سریع', callback_data='calc:quick')],
                                 [InlineKeyboardButton('📅 تقویم و تاریخ', callback_data='calc:calendar'),
                                  InlineKeyboardButton('↩️ محاسبات حقوقی', callback_data='calculators')]])

def calculator_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('💍 مهریه به نرخ روز', callback_data='calc:mahr'),
         InlineKeyboardButton('🩸 دیه', callback_data='calc:diya')],
        [InlineKeyboardButton('⚖️ هزینه دادرسی', callback_data='calc:fee'),
         InlineKeyboardButton('👔 حق‌الوکاله', callback_data='calc:lawyerfee')],
        [InlineKeyboardButton('⚡ محاسبات سریع', callback_data='calc:quick'),
         InlineKeyboardButton('📅 تقویم و تاریخ', callback_data='calc:calendar')],
        [InlineKeyboardButton('⏳ مهلت ۲۰ روزه', callback_data='calc:deadline'),
         InlineKeyboardButton('💸 جریمه‌ها', callback_data='calc:fines')],
        [InlineKeyboardButton('💍 مهریه و اعسار', callback_data='family'),
         InlineKeyboardButton('🧾 ابزار چک', callback_data='check')],
        [InlineKeyboardButton('ℹ️ مبنا و وضعیت داده‌ها', callback_data='calc:about')],
        [InlineKeyboardButton('↩️ منوی اصلی', callback_data='home')],
    ])


def mahr_year_keyboard():
    # Only expose years for which the bundled calculation table has an explicit
    # annual index. Do not offer estimated/midpoint values as if they were exact.
    years = sorted(MAHR_ANNUAL_INDEX.keys())
    rows=[]
    for i in range(0,len(years),5):
        rows.append([InlineKeyboardButton(_fa_num(y), callback_data=f'calc:mahryear:{y}') for y in years[i:i+5]])
    rows.append([InlineKeyboardButton('↩️ محاسبات حقوقی',callback_data='calculators')])
    return InlineKeyboardMarkup(rows)


def ejare_role_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 من مستأجرم", callback_data="ejare:role:tenant")],
        [InlineKeyboardButton("🏢 من موجرم", callback_data="ejare:role:landlord")],
        [InlineKeyboardButton("🏠 منوی اصلی", callback_data="home")],
    ])


def ejare_topic_keyboard(role: str):
    topics = TENANT_TOPICS if role == "tenant" else LANDLORD_TOPICS
    rows = [[InlineKeyboardButton(label, callback_data=f"ejare:topic:{role}:{key}")]
            for key, label in topics.items()]
    rows.append([InlineKeyboardButton("↩️ تغییر نقش", callback_data="ejare"),
                 InlineKeyboardButton("🏠 منوی اصلی", callback_data="home")])
    return InlineKeyboardMarkup(rows)


def ejare_result_keyboard(role: str, topic: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔎 جستجوی مرتبط", callback_data=f"ejare:search:{role}:{topic}")],
        [InlineKeyboardButton("🏠 موضوع دیگر اجاره", callback_data="ejare"),
         InlineKeyboardButton("🧮 محاسبات", callback_data="calculators")],
        [InlineKeyboardButton("⚖️ منوی اصلی", callback_data="home")],
    ])


async def ejare_cb(update, context):
    q = update.callback_query
    await q.answer()
    if not await _require_registered(q):
        return
    _clear_pending_inputs(context)
    context.user_data["ejare_flow"] = {}
    await q.message.reply_text(
        "🏠 مسیر اجاره و تخلیه\n\n"
        "نقش خود را انتخاب کنید. با چند دکمه یک راهنمای عملی کوتاه می‌گیرید.\n"
        "این بخش دادخواست ثبت نمی‌کند و نتیجه پرونده را پیش‌بینی نمی‌کند.",
        reply_markup=ejare_role_keyboard(),
    )


async def ejare_role_cb(update, context):
    q = update.callback_query
    await q.answer()
    if not await _require_registered(q):
        return
    role = q.data.split(":")[-1]
    if role not in ("tenant", "landlord"):
        return
    flow = context.user_data.setdefault("ejare_flow", {})
    flow["role"] = role
    label = "مستأجر" if role == "tenant" else "موجر"
    await q.message.reply_text(
        f"نقش: {label}\nموضوع را انتخاب کنید:",
        reply_markup=ejare_topic_keyboard(role),
    )


async def ejare_topic_cb(update, context):
    q = update.callback_query
    await q.answer()
    if not await _require_registered(q):
        return
    parts = q.data.split(":")
    if len(parts) < 4:
        return
    role, topic = parts[2], parts[3]
    text = build_ejare_guide(role, topic)
    context.user_data.pop("ejare_flow", None)
    await q.message.reply_text(text, reply_markup=ejare_result_keyboard(role, topic))


async def ejare_search_cb(update, context):
    """Seed unified legal search with a suggested query for this branch."""
    q = update.callback_query
    await q.answer()
    if not await _require_registered(q):
        return
    parts = q.data.split(":")
    if len(parts) < 4:
        return
    role, topic = parts[2], parts[3]
    hint = ejare_search_hint(role, topic)
    _clear_pending_inputs(context, keep="awaiting_unified_legal_search")
    context.user_data["awaiting_unified_legal_search"] = True
    await q.message.reply_text(
        f"🔎 عبارت پیشنهادی برای جستجو:\n«{hint}»\n\n"
        "می‌توانید همین را بفرستید یا عبارت خودتان را بنویسید."
    )




def family_role_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 طلبکار مهریه (زوجه)", callback_data="family:role:creditor")],
        [InlineKeyboardButton("👤 بدهکار مهریه (زوج)", callback_data="family:role:debtor")],
        [InlineKeyboardButton("🏠 منوی اصلی", callback_data="home")],
    ])


def family_topic_keyboard(role: str):
    topics = CREDITOR_TOPICS if role == "creditor" else DEBTOR_TOPICS
    rows = [[InlineKeyboardButton(label, callback_data=f"family:topic:{role}:{key}")]
            for key, label in topics.items()]
    rows.append([InlineKeyboardButton("↩️ تغییر نقش", callback_data="family"),
                 InlineKeyboardButton("🏠 منوی اصلی", callback_data="home")])
    return InlineKeyboardMarkup(rows)


def family_result_keyboard(role: str, topic: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔎 جستجوی مرتبط", callback_data=f"family:search:{role}:{topic}")],
        [InlineKeyboardButton("🧮 ماشین‌حساب مهریه", callback_data="calc:mahr")],
        [InlineKeyboardButton("💍 موضوع دیگر", callback_data="family"),
         InlineKeyboardButton("⚖️ منوی اصلی", callback_data="home")],
    ])


async def family_cb(update, context):
    q = update.callback_query
    await q.answer()
    if not await _require_registered(q):
        return
    _clear_pending_inputs(context)
    context.user_data["family_flow"] = {}
    await q.message.reply_text(
        "💍 مسیر مهریه و اعسار\n\n"
        "نقش خود را انتخاب کنید. راهنما عملی و محافظه‌کارانه است؛\n"
        "جایگزین بررسی عقدنامه و مشاوره موردی نیست.",
        reply_markup=family_role_keyboard(),
    )


async def family_role_cb(update, context):
    q = update.callback_query
    await q.answer()
    if not await _require_registered(q):
        return
    role = q.data.split(":")[-1]
    if role not in ("creditor", "debtor"):
        return
    context.user_data.setdefault("family_flow", {})["role"] = role
    label = "طلبکار مهریه" if role == "creditor" else "بدهکار مهریه"
    await q.message.reply_text(
        f"نقش: {label}\nموضوع را انتخاب کنید:",
        reply_markup=family_topic_keyboard(role),
    )


async def family_topic_cb(update, context):
    q = update.callback_query
    await q.answer()
    if not await _require_registered(q):
        return
    parts = q.data.split(":")
    if len(parts) < 4:
        return
    role, topic = parts[2], parts[3]
    text = build_family_guide(role, topic)
    context.user_data.pop("family_flow", None)
    await q.message.reply_text(text, reply_markup=family_result_keyboard(role, topic))


async def family_search_cb(update, context):
    q = update.callback_query
    await q.answer()
    if not await _require_registered(q):
        return
    parts = q.data.split(":")
    if len(parts) < 4:
        return
    role, topic = parts[2], parts[3]
    hint = family_search_hint(role, topic)
    _clear_pending_inputs(context, keep="awaiting_unified_legal_search")
    context.user_data["awaiting_unified_legal_search"] = True
    await q.message.reply_text(
        f"🔎 عبارت پیشنهادی:\n«{hint}»\n\nهمین را بفرستید یا عبارت خودتان را بنویسید."
    )




def check_role_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 دارنده چک / طلبکار", callback_data="check:role:holder")],
        [InlineKeyboardButton("👤 صادرکننده / ظهرنویس", callback_data="check:role:drawer")],
        [InlineKeyboardButton("🏠 منوی اصلی", callback_data="home")],
    ])


def check_topic_keyboard(role: str):
    topics = HOLDER_TOPICS if role == "holder" else DRAWER_TOPICS
    rows = [[InlineKeyboardButton(label, callback_data=f"check:topic:{role}:{key}")]
            for key, label in topics.items()]
    rows.append([InlineKeyboardButton("↩️ تغییر نقش", callback_data="check"),
                 InlineKeyboardButton("🏠 منوی اصلی", callback_data="home")])
    return InlineKeyboardMarkup(rows)


def check_result_keyboard(role: str, topic: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔎 جستجوی مرتبط", callback_data=f"check:search:{role}:{topic}")],
        [InlineKeyboardButton("🧮 خسارت تأخیر", callback_data="calc:delay")],
        [InlineKeyboardButton("🧾 موضوع دیگر چک", callback_data="check"),
         InlineKeyboardButton("⚖️ منوی اصلی", callback_data="home")],
    ])


async def check_cb(update, context):
    q = update.callback_query
    await q.answer()
    if not await _require_registered(q):
        return
    _clear_pending_inputs(context)
    context.user_data["check_flow"] = {}
    await q.message.reply_text(
        "🧾 مسیر چک\n\n"
        "نقش خود را انتخاب کنید. راهنما عمومی است و نوع چک (مثلاً صیادی) در مسیر اثر دارد.",
        reply_markup=check_role_keyboard(),
    )


async def check_role_cb(update, context):
    q = update.callback_query
    await q.answer()
    if not await _require_registered(q):
        return
    role = q.data.split(":")[-1]
    if role not in ("holder", "drawer"):
        return
    context.user_data.setdefault("check_flow", {})["role"] = role
    label = "دارنده / طلبکار" if role == "holder" else "صادرکننده / ظهرنویس"
    await q.message.reply_text(
        f"نقش: {label}\nموضوع را انتخاب کنید:",
        reply_markup=check_topic_keyboard(role),
    )


async def check_topic_cb(update, context):
    q = update.callback_query
    await q.answer()
    if not await _require_registered(q):
        return
    parts = q.data.split(":")
    if len(parts) < 4:
        return
    role, topic = parts[2], parts[3]
    text = build_check_guide(role, topic)
    context.user_data.pop("check_flow", None)
    await q.message.reply_text(text, reply_markup=check_result_keyboard(role, topic))


async def check_search_cb(update, context):
    q = update.callback_query
    await q.answer()
    if not await _require_registered(q):
        return
    parts = q.data.split(":")
    if len(parts) < 4:
        return
    role, topic = parts[2], parts[3]
    hint = check_search_hint(role, topic)
    _clear_pending_inputs(context, keep="awaiting_unified_legal_search")
    context.user_data["awaiting_unified_legal_search"] = True
    await q.message.reply_text(
        f"🔎 عبارت پیشنهادی:\n«{hint}»\n\nهمین را بفرستید یا عبارت خودتان را بنویسید."
    )



async def fines_cb(update, context):
    q=update.callback_query; await q.answer(); _clear_pending_inputs(context)
    await q.message.reply_text(
        '💸 جزای نقدی و جریمه‌های قانونی\n\n'
        'برای شروع، مواردی را نمایش می‌دهیم که مبنای عددی آن‌ها روشن و قابل محاسبه است.\n\n'
        '⚠️ جریمه‌های ثابت یا مبالغی که با مصوبه/تورم/بودجه تغییر می‌کنند فقط پس از احراز منبع رسمی وارد می‌شوند.',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton('🍷 حمل/نگهداری/خرید/فروش مشروبات — ماده ۷۰۲',callback_data='calc:fine:alcohol')],
            [InlineKeyboardButton('↩️ محاسبات حقوقی',callback_data='calculators')]
        ])
    )

async def alcohol_fine_cb(update, context):
    q=update.callback_query; await q.answer(); _clear_pending_inputs(context)
    context.user_data['calc_alcohol_value']=True
    await q.message.reply_text('💰 ارزش عرفی مشروبات مکشوفه را به تومان وارد کنید:\nمثال: ۱۰۰۰۰۰۰')


async def quick_calc_cb(update, context):
    q=update.callback_query; await q.answer(); _clear_pending_inputs(context)
    await q.message.reply_text('⚡ محاسبات سریع\n\nچند ابزار عمومی و بدون نیاز به AI برای محاسبه فوری:', reply_markup=quick_calculator_menu())

async def quick_percent_cb(update, context):
    q=update.callback_query; await q.answer(); _clear_pending_inputs(context)
    context.user_data['calc_quick_percent']=True
    await q.message.reply_text('🔢 درصد از مبلغ\n\nاول مبلغ را به تومان وارد کنید؛ سپس درصد را می‌پرسیم.\nمثال: ۲۵۰۰۰۰۰۰۰')

async def quick_rial_cb(update, context):
    q=update.callback_query; await q.answer(); _clear_pending_inputs(context)
    context.user_data['calc_quick_rial']=True
    await q.message.reply_text('💱 تبدیل تومان ↔ ریال\n\nمبلغ را وارد کنید.\nمثال: ۱۰۰۰۰۰۰\n\nابتدا فرض می‌کنیم ورودی «تومان» است و معادل ریالی را می‌دهیم.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('ریال → تومان', callback_data='calc:quick:rial_reverse')],[InlineKeyboardButton('↩️ محاسبات سریع',callback_data='calc:quick')]]))

async def quick_rial_reverse_cb(update, context):
    q=update.callback_query; await q.answer(); _clear_pending_inputs(context)
    context.user_data['calc_quick_rial_reverse']=True
    await q.message.reply_text('💱 تبدیل ریال به تومان\n\nمبلغ ریالی را وارد کنید:')

async def quick_installment_cb(update, context):
    q=update.callback_query; await q.answer(); _clear_pending_inputs(context)
    context.user_data['calc_quick_installment']=True
    await q.message.reply_text('➗ قسط‌بندی مبلغ\n\nکل مبلغ را به تومان وارد کنید:')

async def quick_datediff_cb(update, context):
    q=update.callback_query; await q.answer(); _clear_pending_inputs(context)
    context.user_data['calc_quick_datediff']=1
    await q.message.reply_text('📆 فاصله دو تاریخ\n\nتاریخ اول را وارد کنید. شمسی مثل ۱۴۰۵/۰۶/۲۹ یا میلادی مثل ۲۰۲۶/۰۹/۲۰ قابل قبول است:')

async def calendar_cb(update, context):
    q=update.callback_query; await q.answer(); _clear_pending_inputs(context)
    await q.message.reply_text('📅 تقویم و تاریخ\n\nتاریخ شمسی ایران و تاریخ میلادی را کنار هم ببینید و در صورت نیاز تبدیل کنید.', reply_markup=calendar_menu())

async def calendar_today_cb(update, context):
    q=update.callback_query; await q.answer(); _clear_pending_inputs(context)
    await q.message.reply_text(_calendar_today_text(update), reply_markup=calendar_menu())

async def calendar_convert_cb(update, context):
    q=update.callback_query; await q.answer(); _clear_pending_inputs(context)
    context.user_data['calc_calendar_convert']=True
    await q.message.reply_text('🔄 تبدیل تاریخ\n\nیک تاریخ شمسی یا میلادی بفرستید.\nشمسی: ۱۴۰۵/۰۶/۲۹\nمیلادی: ۲۰۲۶/۰۹/۲۰')

async def calculator_about_cb(update, context):
    q=update.callback_query; await q.answer()
    await q.message.reply_text(
        "ℹ️ منبع و اعتبار اعداد محاسبه‌گرها\n\n"
        "💍 مهریه:\n"
        "• فرمول: مبلغ × (شاخص سال محاسبه ÷ شاخص سال عقد)\n"
        "• تا ۱۴۰۲: سری ذخیره‌شده در بات\n"
        "• ۱۴۰۳ و ۱۴۰۴: تقریبی/علی‌الحساب — قبل از استناد با جدول بانک مرکزی تطبیق دهید\n\n"
        "💰 خسارت تأخیر تأدیه:\n"
        "• فرمول: اصل × (شاخص مقصد ÷ شاخص مبدأ)؛ خسارت = مبلغ تعدیلی − اصل\n"
        "• شاخص را خودتان از منبع رسمی وارد می‌کنید (بات از نت شاخص زنده نمی‌گیرد)\n\n"
        "🩸 دیه ۱۴۰۵:\n"
        "• غیرحرام ۲٫۱ میلیارد تومان | حرام ۲٫۸ میلیارد تومان (ابلاغ قوه قضاییه)\n"
        "• ارش عمداً عددسازی نمی‌شود\n\n"
        "⚖️ هزینه دادرسی: فرمول پیکربندی‌شده (بدوی ۲٫۵٪/۳٫۵٪؛ تجدیدنظر ۴٫۵٪؛ فرجام ۵٫۵٪) — مبالغ ریال\n\n"
        "👔 حق‌الوکاله: پلکان آیین‌نامه تعرفه؛ توافق طرفین می‌تواند متفاوت باشد\n\n"
        "📅 مهلت: فقط جمع روز تقویمی؛ تعطیل و ابلاغ جداست\n\n"
        "⚠️ همه نتایج راهنما هستند و جایگزین تعرفه/کارشناسی رسمی شعبه نیستند.",
        reply_markup=calculator_menu())

async def calculators_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_registered(q): return
    _clear_pending_inputs(context)
    await q.message.reply_text('🧮 محاسبات حقوقی\n\nمحاسبه‌گرها محلی و فرمول‌محورند و نتیجه همراه با مبنای محاسبه نمایش داده می‌شود.',reply_markup=calculator_menu())

async def mahr_cb(update, context):
    q=update.callback_query; await q.answer(); _clear_pending_inputs(context)
    context.user_data['calc_mahr_amount']=True
    await q.message.reply_text('💍 محاسبه مهریه به نرخ روز\n\nمبلغ مهریه را به تومان وارد کنید؛ مثال: ۵۰۰ میلیون یا 500000000')

async def mahr_amount_cb(update, context):
    q=update.callback_query; await q.answer();
    context.user_data['calc_mahr_amount']=True
    await q.message.reply_text('💰 مبلغ مهریه را به تومان وارد کنید:')

async def mahr_year_cb(update, context):
    q=update.callback_query; await q.answer()
    try: year=int(q.data.split(':')[2])
    except Exception: return
    amount=context.user_data.get('calc_mahr_amount')
    if not isinstance(amount,(int,float)):
        await q.message.reply_text('❌ ابتدا مبلغ مهریه را وارد کنید.')
        return
    index=MAHR_ANNUAL_INDEX.get(year)
    target_year=max(MAHR_ANNUAL_INDEX)
    target_index=MAHR_ANNUAL_INDEX[target_year]
    if not index:
        await q.message.reply_text('❌ برای این سال شاخص صریح و قابل اتکای موجود در بسته فعلی نداریم؛ عدد تخمینی تولید نمی‌کنیم.')
        return
    result=mahr_value(amount,index,target_index)
    increase_pct=(target_index/index-1)*100
    context.user_data.pop('calc_mahr_amount',None)
    await q.message.reply_text(
        '💍 نتیجه محاسبه مهریه\n\n'
        f'مبلغ مهریه: {_fa_num(f"{amount:,.0f}")} تومان\n'
        f'سال عقد: {_fa_num(year)}\n'
        f'سال مرجع داده: {_fa_num(target_year)}\n'
        f'شاخص سال عقد: {_fa_num(f"{index:g}")}\n'
        f'شاخص سال مرجع: {_fa_num(f"{target_index:g}")}\n'
        f'📈 افزایش شاخص: {_fa_num(f"{increase_pct:,.1f}")}٪\n'
        f'💰 مبلغ محاسبه‌شده: {_fa_num(f"{result:,.0f}")} تومان\n\n'
        '📚 مبنا: تبصره ماده ۱۰۸۲ قانون مدنی و شاخص سالانه بانک مرکزی.\n'
        'فرمول: مبلغ × (شاخص سال محاسبه ÷ شاخص سال عقد)\n'
        + ('\n⚠️ شاخص ۱۴۰۳ یا ۱۴۰۴ علی‌الحساب/تقریبی است؛ ملاک نهایی جدول رسمی بانک مرکزی است.'
           if (year in MAHR_PROVISIONAL_YEARS or target_year in MAHR_PROVISIONAL_YEARS)
           else '\n✅ شاخص سال‌های انتخاب‌شده در جدول بسته موجود است.'),
        reply_markup=calculator_menu())

async def diya_cb(update, context):
    q=update.callback_query; await q.answer(); _clear_pending_inputs(context)
    rows=[
        [InlineKeyboardButton('دیه کامل — ماه غیرحرام', callback_data='calc:diya:p:100:n')],
        [InlineKeyboardButton('دیه کامل — ماه حرام (فقط در موارد قانونیِ تغلیظ)', callback_data='calc:diya:p:100:h')],
        [InlineKeyboardButton('جراحات سر و صورت',callback_data='calc:diya:head')],
        [InlineKeyboardButton('تغییر رنگ پوست',callback_data='calc:diya:color')],
        [InlineKeyboardButton('⚠️ ارش — بدون عدد ثابت',callback_data='calc:diya:ersh')],
        [InlineKeyboardButton('↩️ محاسبات حقوقی',callback_data='calculators')]
    ]
    await q.message.reply_text('🩸 محاسبه دیه — سال ۱۴۰۵\n\nدیه کامل ماه غیرحرام: ۲٬۱۰۰٬۰۰۰٬۰۰۰ تومان\nدیه کامل ماه حرام: ۲٬۸۰۰٬۰۰۰٬۰۰۰ تومان\n\n⚠️ تغلیظ ماه حرام را به‌صورت ضریب عمومی برای هر نوع آسیب اعمال نمی‌کنیم؛ مورد باید از نظر قانونی احراز شود.',reply_markup=InlineKeyboardMarkup(rows))

async def diya_percent_cb(update, context):
    q=update.callback_query; await q.answer(); await q.message.reply_text('از منوی دیه، درصد یا نوع آسیب را انتخاب کنید.',reply_markup=calculator_menu())

async def diya_result_cb(update, context):
    q=update.callback_query; await q.answer()
    parts=q.data.split(':')
    if len(parts)<5: return
    try: pct=float(parts[3]); kind=parts[4]
    except Exception: return
    base=DIYA_FULL_1405_HARAM if kind=='h' else DIYA_FULL_1405_NORMAL
    amount=diyah_percentage(base,pct)
    await q.message.reply_text('🩸 نتیجه دیه ۱۴۰۵\n\n'+f'درصد: {_fa_num(f"{pct:g}")}٪\n'+f'مبنای دیه کامل: {_fa_num(f"{base:,.0f}")} تومان\n'+f'💰 مبلغ: {_fa_num(f"{amount:,.0f}")} تومان\n\n⚠️ این عدد فقط حاصل اعمال درصد ثابت انتخاب‌شده بر دیه کامل سال ۱۴۰۵ است؛ برای نوع صدمه، عضو، جراحت، تعدد صدمات و شرایط تغلیظ باید مقررات مربوط جداگانه بررسی شود.',reply_markup=calculator_menu())

async def diya_head_cb(update, context):
    q=update.callback_query; await q.answer()
    rows=[[InlineKeyboardButton(f'{name} — {_fa_num(f"{pct:g}")}٪',callback_data=f'calc:diya:p:{pct}:n')] for name,pct in HEAD_WOUND_PCTS.items()]
    rows.append([InlineKeyboardButton('↩️ دیه',callback_data='calc:diya')])
    await q.message.reply_text('🩸 جراحات سر و صورت — سال ۱۴۰۵\n\nنوع جراحت را انتخاب کنید:',reply_markup=InlineKeyboardMarkup(rows))

async def diya_color_cb(update, context):
    q=update.callback_query; await q.answer()
    rows=[[InlineKeyboardButton(f'{name} — {_fa_num(f"{pct:g}")}٪',callback_data=f'calc:diya:p:{pct}:n')] for name,pct in COLOR_PCTS.items()]
    rows.append([InlineKeyboardButton('↩️ دیه',callback_data='calc:diya')])
    await q.message.reply_text('🩸 تغییر رنگ — درصدهای ثابت اعلام‌شده در قانون\n\nنوع را انتخاب کنید:',reply_markup=InlineKeyboardMarkup(rows))

async def diya_ersh_cb(update, context):
    q=update.callback_query; await q.answer()
    await q.message.reply_text('⚠️ ارش مبلغ ثابت از پیش تعیین‌شده ندارد و میزان آن با توجه به نوع و کیفیت آسیب و معیارهای قانونی توسط مرجع صالح تعیین می‌شود؛ بنابراین عدد حدسی تولید نمی‌کنیم.',reply_markup=calculator_menu())

async def delay_cb(update, context):
    q=update.callback_query; await q.answer(); _clear_pending_inputs(context)
    await q.message.reply_text('💰 خسارت تأخیر تأدیه\n\nبرای جلوگیری از عددسازی، این بخش فعلاً شاخص‌محور است.\n\nاصل دین را به تومان وارد کنید:')
    context.user_data['calc_delay_amount']=True

async def fee_cb(update, context):
    q=update.callback_query; await q.answer(); _clear_pending_inputs(context)
    context.user_data['calc_fee_amount']=True
    await q.message.reply_text('⚖️ هزینه دادرسی\n\nبهای خواسته را به ریال وارد کنید:')

async def fee_stage_cb(update, context):
    q=update.callback_query; await q.answer()
    context.user_data['calc_fee_stage']=q.data.split(':')[-1]
    amount=context.user_data.get('calc_fee_amount')
    try: result=court_fee(int(amount),'first' if context.user_data['calc_fee_stage']=='first' else context.user_data['calc_fee_stage'])
    except Exception:
        await q.message.reply_text('❌ ورودی نامعتبر است.'); return
    context.user_data.pop('calc_fee_amount',None); context.user_data.pop('calc_fee_stage',None)
    await q.message.reply_text(f'⚖️ نتیجه هزینه دادرسی\n\nبهای خواسته: {_fa_num(f"{amount:,.0f}")} ریال\n💰 هزینه تقریبی: {_fa_num(f"{result:,.0f}")} ریال\n\n⚠️ تعرفه‌های خدمات قضایی ممکن است با قانون بودجه/بخشنامه به‌روزرسانی شوند؛ قبل از پرداخت، مبلغ سامانه خدمات قضایی را ملاک نهایی قرار دهید.',reply_markup=calculator_menu())

async def lawyer_fee_cb(update, context):
    q=update.callback_query; await q.answer(); _clear_pending_inputs(context); context.user_data['calc_lawyer_amount']=True
    await q.message.reply_text('👨‍⚖️ حق‌الوکاله تعرفه‌ای\n\nبهای خواسته دعوای مالی را به ریال وارد کنید:')

def _lawyer_fee_message(amount):
    total=lawyer_fee_financial(int(amount))
    first,appeal=lawyer_fee_split(total)
    return (f'👨‍⚖️ نتیجه حق‌الوکاله تعرفه‌ای\n\n'
            f'بهای خواسته: {_fa_num(f"{int(amount):,.0f}")} ریال\n'
            f'💰 کل تعرفه: {_fa_num(f"{total:,.0f}")} ریال\n'
            f'مرحله نخستین (۶۰٪): {_fa_num(f"{first:,.0f}")} ریال\n'
            f'تجدیدنظر (۴۰٪): {_fa_num(f"{appeal:,.0f}")} ریال\n\n'
            '⚠️ این محاسبه برای دعوای مالی بر مبنای جدول تعرفه تنظیم‌شده در نسخه فعلی است؛ پرونده‌های کیفری، خانوادگی، غیرمالی و موارد خاص قواعد جدا دارند.')

async def lawyer_fee_result_cb(update, context):
    q=update.callback_query; await q.answer()
    amount=context.user_data.get('calc_lawyer_amount')
    try: text_result=_lawyer_fee_message(amount)
    except Exception: await q.message.reply_text('❌ مبلغ معتبر نیست.'); return
    context.user_data.pop('calc_lawyer_amount',None)
    await q.message.reply_text(text_result,reply_markup=calculator_menu())

async def deadline_cb(update, context):
    q=update.callback_query; await q.answer(); _clear_pending_inputs(context); context.user_data['calc_deadline_date']=True
    await q.message.reply_text('📅 محاسبه مهلت ۲۰ روزه\n\nتاریخ ابلاغ را شمسی یا میلادی وارد کنید؛ مثال شمسی: ۱۴۰۵/۰۶/۱۲ یا میلادی: 2026-09-03\n\nمبدأ و نتیجه هر دو به شمسی و میلادی نمایش داده می‌شوند. تعطیلات و قواعد خاص مهلت هنوز خودکار اعمال نمی‌شوند.')

async def delay_amount_text(value, context, msg):
    amount=calc_parse_amount(value)
    if amount is None or amount<=0:
        await msg.reply_text('❌ مبلغ معتبر وارد کنید.'); return True
    context.user_data.pop('calc_delay_amount',None); context.user_data['calc_delay_amount_value']=amount
    await msg.reply_text('شاخص سال/مبدأ را وارد کنید (مثلاً 100):'); context.user_data['calc_delay_src']=True; return True

async def status_cb(update, context):
    q = update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_registered(q): return
    _clear_pending_inputs(context)
    from .core.entitlements import EntitlementService
    ent_status = EntitlementService().status(uid)
    if ent_status and ent_status.get('source') == 'subscription':
        s = ent_status.get('subscription') or {}
        caseq = ent_status.get('case') or {}
        aiq = ent_status.get('ai_question') or {}
        plan = f'💎 پرو تا {str(s.get("expires_at") or "")[:10]}\n📁 باقی‌مانده پرونده: {caseq.get("remaining", 0)}'
        quota = f'🤖 سهمیه AI فعلی: {aiq.get("remaining", 0)} از {aiq.get("limit", 0)}'
    else:
        credit = (ent_status or {}).get('credits') or credit_status(uid)
        sec=credit['seconds_until_refresh']; days,rem=divmod(sec,86400); hours,rem=divmod(rem,3600); minutes,_=divmod(rem,60)
        wait=(f'{days} روز و {hours} ساعت' if days else (f'{hours} ساعت و {minutes} دقیقه' if hours else f'{minutes} دقیقه'))
        plan = f'🎁 رایگان\n🪙 اعتبار: {credit["remaining"]} از {credit["allowance"]}\n🔄 شارژ بعدی: {wait} دیگر'
        quota = '📌 جستجو، پرونده و سؤال AI از همین اعتبار هفتگی مصرف می‌شوند.'
    await q.message.reply_text(f'📊 وضعیت حساب\n\n{plan}\n{quota}', reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton('💳 اشتراک', callback_data='subscribe')],
        [InlineKeyboardButton('🗑️ حذف کامل حساب و اطلاعات', callback_data='accountdelete')],
        [InlineKeyboardButton('🏠 منوی اصلی', callback_data='home')],
    ]))


async def cases_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    _clear_pending_inputs(context)

    cases=list_cases(uid,20)
    counts=user_work_counts(uid)
    tasks=list_tasks(uid, include_done=False)[:8]
    refs=list_referrals_for_user(uid,8)
    lawyer_refs=list_referral_matches_for_lawyer(uid,8)

    lines=['📂 پرونده‌ها و کارهای من','']
    if cases:
        lines.append(f'📁 پرونده‌های من: {len(cases)}')
    else:
        lines.append('📁 هنوز پرونده‌ای ثبت نشده است.')

    total=counts['tasks']+counts['referrals']+counts['lawyer_referrals']+counts['payments']+counts['cases_processing']
    lines.append(f'🔴 موارد نیازمند اقدام: {total}')
    if counts['cases_processing']: lines.append(f'⏳ {counts["cases_processing"]} پرونده در حال پردازش')
    if counts['payments']: lines.append(f'💳 {counts["payments"]} پرداخت در انتظار بررسی')
    if counts['referrals']: lines.append(f'🤝 {counts["referrals"]} درخواست معرفی فعال شما')
    if counts['lawyer_referrals']: lines.append(f'📨 {counts["lawyer_referrals"]} معرفی جدید برای خدمات شما')

    if tasks:
        lines += ['', '📝 کارهای ثبت‌شده']
        for t in tasks: lines.append(f'⬜ #{t["id"]} {t["title"]}' + (f' — موعد: {_fa_num_text(str(t["due_at"])[:10])}' if t.get('due_at') else ' — بدون موعد'))
    if refs:
        lines += ['', '🤝 معرفی‌های من']
        for r in refs[:5]: lines.append(f'• #{r["id"]} {r["topic"]} — {_referral_status_fa(r["status"])}')
    if lawyer_refs:
        lines += ['', '📨 معرفی‌های دریافتی']
        for r in lawyer_refs[:5]: lines.append(f'• #{r["id"]} {r["topic"]} — {_match_status_fa(r["status"])}')
    if not cases and not tasks and not refs and not lawyer_refs and total==0:
        lines += ['', '✨ فعلاً موردی برای پیگیری ندارید.']

    kb=[]
    active_case_id=get_active_case_id(uid)
    for c in cases:
        prefix='🟢 ' if active_case_id == c['id'] else '📁 '
        label=(c['file_name'] or 'بدون نام')[:52]
        kb.append([InlineKeyboardButton(f'{prefix}{label}', callback_data=f'caseview:{c["id"]}')])
    task_rows=[]
    for t in tasks[:5]:
        task_rows.append([InlineKeyboardButton(f'✅ انجام شد #{t["id"]}',callback_data=f'taskact:done:{t["id"]}'), InlineKeyboardButton('🗑 حذف',callback_data=f'taskact:delete:{t["id"]}')])
    kb += task_rows
    kb += [
        [InlineKeyboardButton('🗄️ کمد پرونده‌ها',callback_data='archivedcases')],
        [InlineKeyboardButton('➕ پرونده جدید',callback_data='newcase'), InlineKeyboardButton('➕ کار جدید',callback_data='tasknew')],
        [InlineKeyboardButton('🤝 درخواست معرفی',callback_data='referral_new'), InlineKeyboardButton('📨 معرفی‌های من',callback_data='referrals')],
        [InlineKeyboardButton('🏠 منوی اصلی',callback_data='home')],
    ]
    if MINIAPP_URL:
        await q.message.reply_text('🚀 برای کار یکپارچه روی پرونده‌ها می‌توانید میزکار Mini App را باز کنید.', reply_markup=miniapp_keyboard())
    await q.message.reply_text('\n'.join(lines), reply_markup=InlineKeyboardMarkup(kb))


async def archived_cases_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    _clear_pending_inputs(context)
    rows=list_archived_cases(uid,50)
    if not rows:
        await q.message.reply_text('🗄️ کمد پرونده‌ها خالی است.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('↩️ پرونده‌ها',callback_data='cases')]]))
        return
    kb=[]
    for c in rows:
        kb.append([InlineKeyboardButton(f'🗄️ {(c.get("file_name") or "بدون نام")[:50]}', callback_data=f'archivedview:{c["id"]}')])
    kb.append([InlineKeyboardButton('↩️ پرونده‌ها',callback_data='cases')])
    await q.message.reply_text('🗄️ پرونده‌های داخل کمد:', reply_markup=InlineKeyboardMarkup(kb))

async def archived_view_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    cid=int(q.data.split(':')[1]); c=get_case(uid,cid)
    if not c or c.get('status')!='archived':
        await q.message.reply_text('❌ پرونده پیدا نشد.')
        return
    await q.message.reply_text(f'🗄️ پرونده «{c.get("file_name") or "بدون نام"}»\n\nاین پرونده آرشیو شده و اطلاعات آن حفظ شده است.', reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton('↩️ بازگردانی پرونده',callback_data=f'archiverestore:{cid}')],
        [InlineKeyboardButton('🗑️ حذف دائمی پرونده',callback_data=f'casedelete:{cid}')],
        [InlineKeyboardButton('🗄️ کمد',callback_data='archivedcases')],
    ]))

async def archived_restore_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    cid=int(q.data.split(':')[1])
    if not restore_case(uid,cid):
        await q.message.reply_text('❌ بازگردانی پرونده انجام نشد.')
        return
    await q.message.reply_text('📂 پرونده از کمد خارج و دوباره فعال شد.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('📁 مشاهده پرونده',callback_data=f'caseview:{cid}')]]))

async def account_delete_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_registered(q): return
    _clear_pending_inputs(context)
    await q.message.reply_text(
        '⚠️ حذف کامل حساب\n\nتمام پرونده‌ها، اسناد ذخیره‌شده، متن‌های OCR، نسخه‌ها، یادداشت‌ها، تاریخ‌ها، سابقه AI، موکل‌ها، کارها و اطلاعات اشتراک/پرداخت حساب حذف می‌شوند.\n\nاین عملیات از داخل برنامه قابل بازگشت نیست. نسخه‌های پشتیبان نیز طبق چرخه نگهداری خودکار در موعد مقرر منقضی می‌شوند.',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton('❌ بله، حذف کامل حساب',callback_data='accountdelconfirm')],
            [InlineKeyboardButton('↩️ انصراف',callback_data='status')],
        ])
    )

async def account_delete_confirm_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_registered(q): return
    _clear_pending_inputs(context)
    if not delete_user(uid):
        await q.message.reply_text('❌ حذف حساب انجام نشد.')
        return
    context.user_data.clear()
    await q.message.reply_text('🗑️ حساب و اطلاعات آن از سیستم اصلی حذف شد. برای استفاده دوباره باید از ابتدا ثبت‌نام کنید.')

async def case_cmd(update, context):
    await new_case_cb(update, context, command=True)


async def new_case_cb(update, context, command=False):
    uid=update.effective_user.id
    if not command:
        q=update.callback_query; await q.answer();
        if not await _require_lawyer(q, context, 'newcase'): return
        msg=q.message
    else:
        msg=update.effective_message
        if not _is_registered(uid):
            await msg.reply_text('ابتدا /start را بزنید.'); return
    if not _is_registered(uid):
        await msg.reply_text('ابتدا /start را بزنید.'); return
    if not can_use_case(uid):
        credit=credit_status(uid)
        await msg.reply_text(_free_credit_exhausted_message(credit, insufficient=True), reply_markup=_free_credit_exhausted_reply_markup()); return
    _clear_pending_inputs(context, keep='awaiting_case_name')
    context.user_data['awaiting_case_name'] = True
    await msg.reply_text('📁 نام این پرونده را وارد کنید.\n\nمثلاً: «قرارداد اجاره مغازه» یا «پرونده اختلاف ملکی»')


async def _process_case_addition_file(update, context, tg_file, suffix, display_name, cid):
    uid=update.effective_user.id
    case=get_case(uid, cid)
    if not case or case.get('status')=='archived':
        context.user_data.pop('awaiting_case_addition', None)
        context.user_data.pop('case_addition_no', None)
        await update.effective_message.reply_text('🗄️ این پرونده بایگانی شده و امکان افزودن سند یا متن جدید به آن وجود ندارد.')
        return
    addition_no = context.user_data.get('case_addition_no')
    if not addition_no:
        if count_case_additions(uid, cid) >= MAX_CASE_ADDITIONS:
            context.user_data.pop('awaiting_case_addition', None)
            await update.effective_message.reply_text(f'❌ سقف افزودن‌های این پرونده ({MAX_CASE_ADDITIONS} نوبت) پر شده است.', reply_markup=case_menu(cid))
            return
        _, addition_no = start_case_addition(uid, cid)
        context.user_data['case_addition_no'] = addition_no
    count = get_case_addition_file_count(uid, cid, addition_no)
    if count >= MAX_CASE_ADDITION_FILES:
        await update.effective_message.reply_text(
            f'❌ در این نوبت حداکثر {MAX_CASE_ADDITION_FILES} فایل/عکس می‌توانید اضافه کنید.\n'
            'برای پایان این نوبت، دکمه «✅ پایان افزودن» را بزنید.'
        )
        return
    path = new_path(suffix)
    try:
        await tg_file.download_to_drive(custom_path=str(path))
        text_value, diag = await asyncio.to_thread(extract_with_diagnostics, path)
        if not text_value.strip():
            await update.effective_message.reply_text('❌ از این فایل متن قابل استفاده استخراج نشد؛ فایل به پرونده اضافه نشد.')
            return
        doc_id = add_case_document(cid, display_name, diag.get('pages', 1), text_value)
        try:
            stored = store_case_file(cid, path, display_name, 'documents')
            set_case_document_storage(doc_id, uid, stored['storage_path'], stored['file_size'], stored['sha256'], stored['mime_type'])
        except Exception as storage_error:
            logger.exception('durable added-file storage failed: %s', storage_error)
        increment_case_addition_files(uid, cid, addition_no)
        set_active_case(uid, cid)
        new_count = count + 1
        await update.effective_message.reply_text(
            f'✅ فایل به پرونده «{get_case(uid,cid).get("file_name") or "بدون نام"}» اضافه شد.\n'
            f'این نوبت: {new_count} از {MAX_CASE_ADDITION_FILES} فایل\n'
            f'نوبت‌های استفاده‌شده: {count_case_additions(uid,cid)} از {MAX_CASE_ADDITIONS}',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('✅ پایان افزودن', callback_data=f'cadddone:{cid}')]])
        )
    except Exception as e:
        logger.exception('case addition failed for user=%s', uid)
        await update.effective_message.reply_text('❌ افزودن فایل به پرونده انجام نشد. لطفاً دوباره تلاش کنید.')
    finally:
        try: path.unlink(missing_ok=True)
        except Exception: pass


async def _process_case_addition_text(update, context, text_value, cid):
    uid=update.effective_user.id
    case=get_case(uid, cid)
    if not case or case.get('status')=='archived':
        context.user_data.pop('awaiting_case_addition', None)
        context.user_data.pop('case_addition_no', None)
        await update.effective_message.reply_text('🗄️ این پرونده بایگانی شده و امکان افزودن سند یا متن جدید به آن وجود ندارد.')
        return
    text_value=(text_value or '').strip()
    if not text_value:
        await update.effective_message.reply_text('❌ متن خالی قابل افزودن نیست.')
        return
    if len(text_value) > MAX_TEXT_CHARS:
        await update.effective_message.reply_text(f'❌ متن بیش از حد مجاز است. حداکثر {MAX_TEXT_CHARS:,} نویسه مجاز است.')
        return
    addition_no=context.user_data.get('case_addition_no')
    if not addition_no:
        if count_case_additions(uid,cid) >= MAX_CASE_ADDITIONS:
            context.user_data.pop('awaiting_case_addition', None)
            await update.effective_message.reply_text(f'❌ سقف افزودن‌های این پرونده ({MAX_CASE_ADDITIONS} نوبت) پر شده است.', reply_markup=case_menu(cid))
            return
        _, addition_no=start_case_addition(uid,cid)
        context.user_data['case_addition_no']=addition_no
    count=get_case_addition_file_count(uid,cid,addition_no)
    if count >= MAX_CASE_ADDITION_FILES:
        await update.effective_message.reply_text(f'❌ در این نوبت حداکثر {MAX_CASE_ADDITION_FILES} فایل/متن می‌توانید اضافه کنید.\nبرای پایان این نوبت، دکمه «✅ پایان افزودن» را بزنید.')
        return
    doc_id=add_case_document(cid, 'متن اضافه‌شده', 1, text_value)
    if not doc_id or not increment_case_addition_files(uid,cid,addition_no):
        await update.effective_message.reply_text('🗄️ این پرونده دیگر فعال نیست؛ متن جدید ثبت نشد.', reply_markup=case_menu(cid))
        return
    set_active_case(uid,cid)
    new_count=count+1
    await update.effective_message.reply_text(
        f'✅ متن به پرونده اضافه شد.\nاین نوبت: {new_count} از {MAX_CASE_ADDITION_FILES} مورد',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('✅ پایان افزودن', callback_data=f'cadddone:{cid}')]])
    )



async def caseupload_finish_cb(update, context):
    """Finalize multi-file case creation from buffered photos/files."""
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    if not await _require_registered(q):
        return
    buf = context.user_data.get("case_upload_buffer") or []
    if not context.user_data.get("awaiting_case_file"):
        await q.message.reply_text("نشست بارگذاری پرونده فعال نیست. از «➕ پرونده جدید» شروع کنید.")
        return
    if not buf:
        await q.message.reply_text(
            "هنوز فایلی دریافت نشده. حداقل یک عکس یا فایل بفرستید.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ ثبت پرونده با فایل‌های دریافتی", callback_data="caseupload:finish")],
            ]),
        )
        return
    # Process first file as primary case document; rest as additions merged into text
    first = buf[0]
    # _process_document expects tg file-like with download_to_drive
    await _process_document_multi(update, context, buf)
    context.user_data.pop("case_upload_buffer", None)


async def _process_document_multi(update, context, buf):
    """Create one case from multiple buffered uploads (photos/files)."""
    uid = update.effective_user.id if update.effective_user else update.callback_query.from_user.id
    msg = update.effective_message if update.effective_message else update.callback_query.message
    case_name = (context.user_data.get("pending_case_name") or "").strip()
    if not case_name:
        await msg.reply_text("❌ نام پرونده مشخص نیست. ابتدا «➕ پرونده جدید» را بزنید.")
        return
    from .core.entitlements import EntitlementService
    entitlement = EntitlementService()
    ok, reservation_kind = entitlement.reserve(uid, "case")
    if not ok:
        credit=credit_status(uid)
        await msg.reply_text(_free_credit_exhausted_message(credit, insufficient=True), reply_markup=_free_credit_exhausted_reply_markup())
        return
    context.user_data.pop("awaiting_case_file", None)
    context.user_data.pop("pending_case_name", None)
    paths = []
    cid = None
    try:
        texts = []
        total_pages = 0
        diags = []
        for idx, item in enumerate(buf[:MAX_CASE_UPLOAD_FILES]):
            tg = item["tg"]
            suffix = item.get("suffix") or ".jpg"
            display_name = item.get("name") or f"file_{idx+1}{suffix}"
            path = new_path(suffix)
            paths.append(path)
            await tg.download_to_drive(custom_path=str(path))
            if not validate_supported_file(path, suffix):
                continue
            text_value, diag = await asyncio.to_thread(extract_with_diagnostics, path)
            if text_value and text_value.strip():
                texts.append(f"[فایل {idx+1}: {display_name}]\n{text_value.strip()}")
                total_pages += int(diag.get("pages") or 1)
                diags.append(diag)
                successful_files.append((path, display_name, suffix))
            try:
                # keep path for storage of first successful only below
                pass
            except Exception:
                pass
        if not texts:
            entitlement.refund(uid, reservation_kind)
            await msg.reply_text("❌ از فایل‌های ارسالی متن قابل استفاده استخراج نشد.")
            return
        combined = "\n\n".join(texts)
        cid = create_case(uid, case_name)
        set_active_case(uid, cid)
        # store combined text as primary document; store first file binary if available
        doc_id = add_case_document(cid, f"combined_{len(texts)}_files", total_pages or len(texts), combined)
        first_success = successful_files[0] if successful_files else None
        if first_success and first_success[0].exists():
            try:
                first_path, first_name, _ = first_success
                stored = store_case_file(cid, first_path, first_name or "file1", "documents")
                set_case_document_storage(doc_id, uid, stored["storage_path"], stored["file_size"], stored["sha256"], stored["mime_type"])
            except Exception as storage_error:
                logger.exception("multi upload storage: %s", storage_error)
        try:
            important_dates = await asyncio.to_thread(extract_important_dates, combined, 40)
            add_case_important_dates(uid, cid, important_dates)
        except Exception as date_error:
            logger.warning("important date extraction skipped: %s", date_error)
        import json
        finish_case(cid, json.dumps({"extraction": {"files": len(texts), "pages": total_pages, "items": diags}}, ensure_ascii=False))
        if not entitlement.commit(uid, reservation_kind):
            raise RuntimeError("ثبت نهایی سهمیه پرونده انجام نشد.")
        await msg.reply_text(
            f"✅ پرونده «{case_name}» با {len(texts)} فایل ثبت شد.\n\n"
            "برای گرفتن خلاصه یا تحلیل پرونده، به «📂 پرونده‌ها» مراجعه کنید."
        )
    except Exception as e:
        if cid:
            fail_case(cid, f"{type(e).__name__}: {e}")
        entitlement.refund(uid, reservation_kind)
        logger.exception("multi case upload failed user=%s", uid)
        await msg.reply_text("❌ پردازش فایل‌ها متوقف شد. سهمیه در صورت رزرو برگشت داده شد.")
    finally:
        for path in paths:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass



async def _process_document(update, context, tg_file, suffix, display_name):
    """Telegram adapter for the canonical case-intake workflow."""
    uid = update.effective_user.id
    case_name = (context.user_data.get("pending_case_name") or "").strip()
    if not case_name:
        await update.effective_message.reply_text("❌ نام پرونده مشخص نیست. ابتدا «➕ پرونده جدید» را بزنید.")
        return

    path = new_path(suffix)
    context.user_data.pop("awaiting_case_file", None)
    context.user_data.pop("pending_case_name", None)
    try:
        await tg_file.download_to_drive(custom_path=str(path))
        await asyncio.to_thread(
            CaseIntakeService().ingest_one,
            uid, case_name, path, display_name, suffix,
        )
        await update.effective_message.reply_text(
            f'✅ پرونده «{case_name}» ثبت شد.\n\n'
            'برای گرفتن خلاصه یا تحلیل پرونده، به «📂 پرونده‌ها و کارهای من» مراجعه کنید.'
        )
    except CaseWorkflowError as exc:
        credit = credit_status(uid)
        text = str(exc)
        if "سهمیه" in text or "credit" in text.lower():
            await update.effective_message.reply_text(
                _free_credit_exhausted_message(credit, insufficient=True),
                reply_markup=_free_credit_exhausted_reply_markup(),
            )
        else:
            await update.effective_message.reply_text(f"❌ پردازش پرونده انجام نشد.\n{text}")
    except Exception:
        logger.exception("case intake adapter failed user=%s", uid)
        await update.effective_message.reply_text("❌ پردازش پرونده با خطای غیرمنتظره متوقف شد.")
    finally:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass

def _compact_diff(old_text, new_text, max_blocks=12):
    old_lines=[re.sub(r'\s+',' ',x).strip() for x in old_text.splitlines() if x.strip()]
    new_lines=[re.sub(r'\s+',' ',x).strip() for x in new_text.splitlines() if x.strip()]
    sm=difflib.SequenceMatcher(a=old_lines,b=new_lines,autojunk=False)
    blocks=[]
    for tag,i1,i2,j1,j2 in sm.get_opcodes():
        if tag=='equal': continue
        removed='\n'.join(old_lines[i1:i2])
        added='\n'.join(new_lines[j1:j2])
        blocks.append((tag,removed,added))
        if len(blocks)>=max_blocks: break
    return blocks, len(old_lines), len(new_lines)

def format_case_version_diff(base_text, new_text, version_no):
    blocks, old_n, new_n=_compact_diff(base_text,new_text)
    if not blocks:
        return f'🔎 مقایسه نسخه {version_no} با متن اصلی پرونده\n\nتفاوت متنی قابل تشخیصی بین دو نسخه پیدا نشد.'
    out=[f'🔎 تفاوت‌های نسخه {version_no} با پرونده اصلی','',
         f'📄 خطوط متن اصلی: {old_n} | خطوط نسخه جدید: {new_n}','',
         'موارد زیر تفاوت‌های متنی قابل تشخیص هستند؛ این گزارش به‌تنهایی درباره اهمیت یا اثر حقوقی هر تغییر داوری نمی‌کند.','']
    for i,(tag,removed,added) in enumerate(blocks,1):
        label={'replace':'✏️ تغییر','delete':'➖ حذف از نسخه جدید','insert':'➕ اضافه‌شده در نسخه جدید'}.get(tag,'✏️ تغییر')
        out.append(f'{label} — مورد {i}')
        if removed:
            txt=removed
            if len(txt)>500: txt=txt[:500].rsplit(' ',1)[0]+'…'
            out.append('نسخه اصلی: «'+txt+'»')
        if added:
            txt=added
            if len(txt)>500: txt=txt[:500].rsplit(' ',1)[0]+'…'
            out.append('نسخه جدید: «'+txt+'»')
        out.append('')
    if len(blocks)<sum(1 for _ in difflib.SequenceMatcher(a=[x.strip() for x in base_text.splitlines() if x.strip()],b=[x.strip() for x in new_text.splitlines() if x.strip()],autojunk=False).get_opcodes() if _[0]!='equal'):
        out.append('ℹ️ برای کوتاه ماندن پیام، فقط بخشی از تغییرات متنی نمایش داده شد.')
    return normalize_output('\n'.join(out))

async def _process_case_version(update, context, tg_file, suffix, display_name, cid):
    uid=update.effective_user.id
    if not get_case(uid,cid):
        context.user_data.pop('awaiting_case_version_file',None)
        await update.effective_message.reply_text('❌ پرونده پیدا نشد.')
        return
    if count_case_versions(uid,cid) >= MAX_CASE_VERSIONS:
        context.user_data.pop('awaiting_case_version_file',None)
        await update.effective_message.reply_text(f'❌ حداکثر {MAX_CASE_VERSIONS} نسخه جدید برای این پرونده قابل ثبت است.', reply_markup=case_menu(cid))
        return
    path=new_path(suffix)
    stored_path=None
    version_id=None
    try:
        await tg_file.download_to_drive(custom_path=str(path))
        if not validate_supported_file(path, suffix):
            await update.effective_message.reply_text('❌ محتوای فایل با پسوند اعلام‌شده سازگار نیست. نسخه ثبت نشد.', reply_markup=case_menu(cid))
            return
        new_text,diag=await asyncio.to_thread(extract_with_diagnostics,path)
        if not new_text.strip():
            await update.effective_message.reply_text('❌ از نسخه جدید متن قابل استفاده استخراج نشد. نسخه ثبت نشد.', reply_markup=case_menu(cid))
            return
        # The comparison baseline is the first/original case document only.
        # Later attachments are evidence additions and must not silently become
        # part of the "original" version.
        base_text=get_case_original_text(uid,cid)
        if not base_text:
            await update.effective_message.reply_text('❌ متن اصلی پرونده برای مقایسه موجود نیست. نسخه جدید ثبت نشد.', reply_markup=case_menu(cid))
            return

        # Durable file storage happens before the DB version row. If either
        # persistence step fails, compensate so no dangling DB/file artifact
        # remains.
        stored=store_case_file(cid, path, display_name, 'versions')
        stored_path=stored.get('absolute_path')
        version_id,version_no=add_case_version(uid,cid,display_name,diag.get('pages',1),new_text)
        if not version_id:
            raise RuntimeError('ثبت نسخه در پایگاه‌داده انجام نشد.')
        if not set_case_version_storage(version_id, uid, stored['storage_path'], stored['file_size'], stored['sha256'], stored['mime_type']):
            raise RuntimeError('ثبت مسیر فایل نسخه در پایگاه‌داده انجام نشد.')

        set_active_case(uid,cid)
        context.user_data.pop('awaiting_case_version_file',None)
        await update.effective_message.reply_text(f'✅ نسخه جدید {version_no} برای پرونده ثبت شد.')

        try:
            comparison=await asyncio.to_thread(compare_case_versions,base_text,new_text)
            await reply_long(update.effective_message,comparison['report'])
        except Exception as compare_error:
            logger.exception('case version comparison failed: %s', compare_error)
            await update.effective_message.reply_text(
                '⚠️ نسخه جدید با موفقیت ذخیره شد، اما گزارش مقایسه ساختاری در این نوبت تولید نشد. '
                'خود نسخه محفوظ است و می‌توانید دوباره آن را بررسی کنید.'
            )
        await update.effective_message.reply_text('📁 ادامه پرونده:',reply_markup=case_menu(cid))
    except Exception as e:
        if version_id:
            try:
                delete_case_version(uid,cid,version_id)
            except Exception:
                logger.exception('case version DB compensation failed: %s', version_id)
        if stored_path:
            try:
                from pathlib import Path
                Path(stored_path).unlink(missing_ok=True)
            except Exception:
                logger.exception('case version file compensation failed: %s', stored_path)
        logger.exception('case version failed for user=%s case=%s', uid, cid)
        await update.effective_message.reply_text('❌ ثبت یا مقایسه نسخه جدید انجام نشد. نسخه ناقص ثبت نشد؛ لطفاً دوباره تلاش کنید.', reply_markup=case_menu(cid))
    finally:
        try: path.unlink(missing_ok=True)
        except Exception: pass


async def document(update, context):
    uid=update.effective_user.id
    if not _is_registered(uid): await update.effective_message.reply_text('ابتدا /start را بزنید.'); return
    if context.user_data.get('awaiting_case_addition'):
        cid=int(context.user_data['awaiting_case_addition'])
        if get_case(uid,cid):
            doc=update.effective_message.document
            name=doc.file_name or 'document'
            suffix='.'+name.rsplit('.',1)[1].lower() if '.' in name else ''
            if suffix not in {'.pdf','.docx','.txt'}:
                await update.effective_message.reply_text('❌ این فرمت پشتیبانی نمی‌شود. PDF/DOCX/TXT ارسال کنید.')
                return
            if doc.file_size and doc.file_size > MAX_FILE_MB*1024*1024:
                await update.effective_message.reply_text(f'❌ حجم فایل بیشتر از {MAX_FILE_MB}MB است.'); return
            tg=await doc.get_file()
            await _process_case_addition_file(update,context,tg,suffix,name,cid)
            return
        context.user_data.pop('awaiting_case_addition',None)

    if context.user_data.get('awaiting_case_version_file'):
        cid=int(context.user_data['awaiting_case_version_file'])
        if not get_case(uid,cid):
            context.user_data.pop('awaiting_case_version_file',None)
            await update.effective_message.reply_text('❌ پرونده پیدا نشد.')
            return
        if count_case_versions(uid,cid) >= MAX_CASE_VERSIONS:
            context.user_data.pop('awaiting_case_version_file',None)
            await update.effective_message.reply_text(f'❌ حداکثر {MAX_CASE_VERSIONS} نسخه جدید برای این پرونده قابل ثبت است.', reply_markup=case_menu(cid))
            return
        name=update.effective_message.document.file_name or 'version'
        suffix='.'+name.rsplit('.',1)[1].lower() if '.' in name else ''
        if suffix not in {'.pdf','.docx','.txt','.jpg','.jpeg','.png'}:
            await update.effective_message.reply_text('❌ این فرمت پشتیبانی نمی‌شود. PDF/DOCX/TXT یا JPG/JPEG/PNG ارسال کنید.')
            return
        if update.effective_message.document.file_size and update.effective_message.document.file_size > MAX_FILE_MB*1024*1024:
            await update.effective_message.reply_text(f'❌ حجم فایل بیشتر از {MAX_FILE_MB}MB است.'); return
        tg=await update.effective_message.document.get_file()
        await _process_case_version(update,context,tg,suffix,name,cid)
        return
    if not context.user_data.get('awaiting_case_file'):
        await update.effective_message.reply_text('ابتدا «➕ پرونده جدید» را بزنید.'); return
    doc=update.effective_message.document
    name=doc.file_name or 'document'
    suffix='.'+name.rsplit('.',1)[1].lower() if '.' in name else ''
    if suffix not in {'.pdf','.docx','.txt','.jpg','.jpeg','.png','.webp'}:
        await update.effective_message.reply_text('❌ این فرمت پشتیبانی نمی‌شود. PDF/DOCX/TXT/عکس ارسال کنید.')
        return
    if doc.file_size and doc.file_size > MAX_FILE_MB*1024*1024:
        await update.effective_message.reply_text(f'❌ حجم فایل بیشتر از {MAX_FILE_MB}MB است.'); return
    buf = context.user_data.setdefault('case_upload_buffer', [])
    if len(buf) >= MAX_CASE_UPLOAD_FILES:
        await update.effective_message.reply_text(
            f'❌ حداکثر {MAX_CASE_UPLOAD_FILES} فایل. دکمه ثبت را بزنید.',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('✅ ثبت پرونده با فایل‌های دریافتی', callback_data='caseupload:finish')],
            ]),
        )
        return
    tg=await doc.get_file()
    buf.append({'tg': tg, 'suffix': suffix, 'name': name})
    await update.effective_message.reply_text(
        f'📄 فایل دریافت شد ({len(buf)}/{MAX_CASE_UPLOAD_FILES}).\n'
        'فایل بعدی را بفرستید یا ثبت را بزنید.',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton('✅ ثبت پرونده با فایل‌های دریافتی', callback_data='caseupload:finish')],
        ]),
    )


async def photo(update, context):
    uid=update.effective_user.id
    if not _is_registered(uid):
        await update.effective_message.reply_text('ابتدا /start را بزنید.')
        return
    photo = update.effective_message.photo[-1]
    # During service registration, this is the lawyer's license photo. It is
    # archived for admins only and is never published in the public listing.
    if context.user_data.get('service_license_photo_waiting'):
        context.user_data['service_license_photo'] = photo.file_id
        context.user_data.pop('service_license_photo_waiting', None)
        if context.user_data.get('service_edit_step') == 'charity':
            await _finish_service_edit_after_license(update, context)
        else:
            await _finish_service_listing_from_photo(update, context)
        return
    # A photo while a case-addition session is pending belongs to that case.
    if context.user_data.get('awaiting_case_addition'):
        cid=int(context.user_data['awaiting_case_addition'])
        if get_case(uid,cid):
            tg=await photo.get_file()
            await _process_case_addition_file(update,context,tg,'.jpg','image.jpg',cid)
            return
        context.user_data.pop('awaiting_case_addition',None)

    # A photo while a version upload is pending belongs to that case.
    if context.user_data.get('awaiting_case_version_file'):
        cid=int(context.user_data['awaiting_case_version_file'])
        if count_case_versions(uid,cid) >= MAX_CASE_VERSIONS:
            context.user_data.pop('awaiting_case_version_file',None)
            await update.effective_message.reply_text(f'❌ حداکثر {MAX_CASE_VERSIONS} نسخه جدید برای این پرونده قابل ثبت است.', reply_markup=case_menu(cid))
            return
        tg=await photo.get_file()
        await _process_case_version(update,context,tg,'.jpg','image.jpg',cid)
        return
    # A photo while a case upload is pending belongs to the case pipeline.
    if context.user_data.get('awaiting_case_file'):
        buf = context.user_data.setdefault('case_upload_buffer', [])
        if len(buf) >= MAX_CASE_UPLOAD_FILES:
            await update.effective_message.reply_text(
                f'❌ حداکثر {MAX_CASE_UPLOAD_FILES} فایل برای یک پرونده. دکمه ثبت را بزنید.',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('✅ ثبت پرونده با فایل‌های دریافتی', callback_data='caseupload:finish')],
                ]),
            )
            return
        tg = await photo.get_file()
        buf.append({'tg': tg, 'suffix': '.jpg', 'name': f'image_{len(buf)+1}.jpg'})
        await update.effective_message.reply_text(
            f'📷 عکس دریافت شد ({len(buf)}/{MAX_CASE_UPLOAD_FILES}).\n'
            'عکس بعدی را بفرستید یا ثبت را بزنید.',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('✅ ثبت پرونده با فایل‌های دریافتی', callback_data='caseupload:finish')],
            ]),
        )
        return
    if context.user_data.get('tax_screen_waiting'):
        context.user_data.pop('tax_screen_waiting', None)
        answers = context.user_data.pop('tax_flow', None) or {}
        tg=await photo.get_file()
        path=new_path('.jpg')
        try:
            await tg.download_to_drive(str(path))
            ocr_text, diag = await asyncio.to_thread(extract_with_diagnostics, path)
            guide=build_tax_screen_guide(ocr_text, answers)
            await reply_long(update.effective_message, guide)
        except Exception:
            logger.exception('tax screenshot guide failed for user=%s', uid)
            await update.effective_message.reply_text('❌ بررسی تصویر انجام نشد. لطفاً عکس واضح‌تری بفرستید.')
        finally:
            try: path.unlink(missing_ok=True)
            except Exception: pass
        return
    # Otherwise treat the photo as a subscription receipt and send it directly
    # to admins for manual approval. This restores the old, simple payment flow.
    caption = (update.effective_message.caption or '').strip()
    if has_pending_payment_request(uid):
        await update.effective_message.reply_text('⏳ یک رسید پرداخت شما هنوز در انتظار بررسی ادمین است. لطفاً تا اعلام نتیجه، رسید دیگری ارسال نکنید.')
        return
    pid = create_payment_request(uid, photo.file_id, caption)
    if not pid:
        await update.effective_message.reply_text('⏳ یک رسید پرداخت شما هنوز در انتظار بررسی ادمین است.')
        return
    sent = await _send_payment_receipt_to_admins(update.effective_message.get_bot(), pid, uid, photo.file_id, caption)
    if sent:
        row = get_payment_request(pid) or {}
        ref = row.get('payment_reference') or str(pid)
        await update.effective_message.reply_text(f'✅ رسید شما برای ادمین ارسال شد.\n🔖 کد پیگیری: {ref}\nپس از بررسی، نتیجه به شما اعلام می‌شود.')
    else:
        await update.effective_message.reply_text('❌ ارسال رسید به ادمین انجام نشد. لطفاً کمی بعد دوباره تلاش کنید.')


def relevant_laws_text(results):
    s=['📚 منابع حقوقی مرتبط با این پرونده','',
       'از متن اصلی پرونده، فقط بخش‌هایی با ارتباط قوی‌تر انتخاب شده‌اند؛ حداکثر ۱۰ بخش و ۳ منبع برای هر بخش.','',
       '📌 ارتباط احتمالی: این بخش از متن پرونده با موضوعات و عبارات موجود در این ماده هم‌پوشانی متنی دارد.','']
    for i,group in enumerate(results[:10],1):
        page=f' — صفحه {group["page"]}' if group.get('page') else ''
        passage=str(group.get('passage','')).strip()
        # Keep the source passage compact so a large relevance report does not
        # consume several Telegram messages. It remains source-faithful.
        if len(passage) > 320:
            passage=passage[:320].rsplit(' ',1)[0].rstrip(' ،؛,') + '…'
        s += [f'🔹 {i}) بخش مرتبط از پرونده{page}:', f'«{passage}»','']
        for src in group.get('sources',[])[:3]:
            kind=src.get('kind'); icon={'law':'⚖️','ruling':'🏛️','consultation':'💬','sample':'📄','circular':'📢'}.get(kind,'📚')
            explanation=str(src.get('explanation','')).strip()
            if len(explanation) > 180:
                explanation=explanation[:180].rsplit(' ',1)[0].rstrip(' ،؛,') + '…'
            s += [f'{icon} {src.get("display_label","")}', f'📖 توضیح کوتاه: {explanation}', '']
        s += ['────────────','']
    s += ['⚠️ توجه: این موارد پیشنهادهای خودکار بر اساس متن پرونده و بانک حقوقی LegalBot هستند و به معنی قطعی بودن قابلیت استناد یا نتیجه پرونده نیستند.',
          'برای استناد نهایی، متن کامل منبع، قانون خاص مرتبط و آخرین اصلاحات باید بررسی شود.']
    return normalize_output('\n'.join(s))


def client_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('➕ افزودن موکل', callback_data='clientadd'), InlineKeyboardButton('👥 فهرست موکل‌ها', callback_data='clientlist')],
        [InlineKeyboardButton('🔎 جستجوی موکل', callback_data='clientsearch')],
        [InlineKeyboardButton('📌 موکل + پرونده فعال', callback_data='clientlinkactive')],
        [InlineKeyboardButton('🏠 منوی اصلی', callback_data='home')],
    ])

async def clients_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'clients'): return
    _clear_pending_inputs(context)
    rows=list_clients(uid,30)
    await q.message.reply_text(f'👤 موکل‌های من\n\nتعداد ثبت‌شده: {len(rows)}\n\nاین بخش برای نگهداری حداقلی اطلاعات موکل و اتصال او به پرونده‌هاست؛ نه یک CRM کامل.', reply_markup=client_menu())

async def client_list_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'clients'): return
    _clear_pending_inputs(context)
    rows=list_clients(uid,30)
    if not rows:
        await q.message.reply_text('👥 هنوز موکلی ثبت نشده است.', reply_markup=client_menu()); return
    kb=[]
    for c in rows:
        kb.append([InlineKeyboardButton(f'👤 {c["name"]}'[:55], callback_data=f'clientview:{c["id"]}')])
    kb.append([InlineKeyboardButton('➕ افزودن موکل', callback_data='clientadd'), InlineKeyboardButton('🔎 جستجو', callback_data='clientsearch')])
    kb.append([InlineKeyboardButton('↩️ مدیریت موکل‌ها', callback_data='clients')])
    await q.message.reply_text('👥 فهرست موکل‌ها:', reply_markup=InlineKeyboardMarkup(kb))

async def client_quick_add_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'clients'): return
    _clear_pending_inputs(context, keep='client_quick_add')
    context.user_data['client_quick_add']=True
    await q.message.reply_text(
        '👤 افزودن سریع موکل\n\n'
        'نام و نام خانوادگی را بنویسید؛ اگر خواستید شماره تماس را هم در همان پیام وارد کنید.\n'
        'مثال: علی رضایی - 09121234567'
    )

async def client_add_cb(update, context):
    # Backward-compatible callback: use the new one-message quick-add flow.
    return await client_quick_add_cb(update, context)

async def client_view_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'clients'): return
    _clear_pending_inputs(context)
    cid=int(q.data.split(':')[1]); c=get_client(uid,cid)
    if not c: await q.message.reply_text('❌ موکل پیدا نشد.'); return
    cases=client_cases(uid,cid)
    lines=[f'👤 {c["name"]}']
    if c.get('phone'): lines.append(f'📞 {c["phone"]}')
    if c.get('national_id'): lines.append(f'🪪 کد ملی: {c["national_id"]}')
    if c.get('note'): lines += ['', '📝 یادداشت:', c['note']]
    lines += ['', f'📂 پرونده‌های مرتبط: {len(cases)}']
    for case in cases[:8]: lines.append(f'• {case.get("file_name") or "بدون نام"}')
    kb=[[InlineKeyboardButton('✏️ ویرایش', callback_data=f'clientedit:{cid}'), InlineKeyboardButton('🗑 حذف', callback_data=f'clientdelete:{cid}')],
        [InlineKeyboardButton('📂 اتصال به پرونده', callback_data=f'clientlink:{cid}')],
        [InlineKeyboardButton('👥 فهرست موکل‌ها', callback_data='clientlist'), InlineKeyboardButton('↩️ مدیریت موکل‌ها', callback_data='clients')]]
    await q.message.reply_text('\n'.join(lines), reply_markup=InlineKeyboardMarkup(kb))

async def client_link_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'clients'): return
    _clear_pending_inputs(context)
    cid=int(q.data.split(':')[1]); c=get_client(uid,cid)
    if not c: await q.message.reply_text('❌ موکل پیدا نشد.'); return
    linked={x['id'] for x in client_cases(uid,cid)}
    cases=list_cases(uid,30)
    choices=[x for x in cases if x['id'] not in linked]
    if not choices:
        await q.message.reply_text('📂 پرونده دیگری برای اتصال وجود ندارد.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('↩️ موکل',callback_data=f'clientview:{cid}')]])); return
    kb=[[InlineKeyboardButton(f'📁 {(x.get("file_name") or "بدون نام")[:48]}', callback_data=f'clientlinkdo:{cid}:{x["id"]}')] for x in choices]
    kb.append([InlineKeyboardButton('↩️ موکل',callback_data=f'clientview:{cid}')])
    await q.message.reply_text(f'📂 یک پرونده را برای اتصال به «{c["name"]}» انتخاب کنید:', reply_markup=InlineKeyboardMarkup(kb))

async def client_link_do_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'clients'): return
    _,cid,caseid=q.data.split(':')
    ok=link_client_case(uid,int(cid),int(caseid))
    await q.message.reply_text('✅ پرونده به موکل متصل شد.' if ok else '❌ اتصال انجام نشد.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('👤 مشاهده موکل',callback_data=f'clientview:{cid}')]]))

async def client_link_active_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'clients'): return
    cid=get_active_case_id(uid)
    if not cid or not get_case(uid,cid):
        await q.message.reply_text('📌 فعلاً پرونده فعالی ندارید. ابتدا یک پرونده را انتخاب کنید.', reply_markup=client_menu())
        return
    rows=list_clients(uid,50)
    if not rows:
        await q.message.reply_text('👥 هنوز موکلی ثبت نشده است. ابتدا یک موکل اضافه کنید.', reply_markup=client_menu())
        return
    kb=[[InlineKeyboardButton(f'👤 {c["name"]}'[:55], callback_data=f'clientlinkactive_do:{c["id"]}:{cid}')] for c in rows]
    kb.append([InlineKeyboardButton('↩️ مدیریت موکل‌ها',callback_data='clients')])
    await q.message.reply_text('📌 پرونده فعال را به کدام موکل وصل کنم؟', reply_markup=InlineKeyboardMarkup(kb))

async def client_link_active_do_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'clients'): return
    _,client_id,case_id=q.data.split(':')
    ok=link_client_case(uid,int(client_id),int(case_id))
    await q.message.reply_text('✅ پرونده فعال به موکل متصل شد.' if ok else '❌ اتصال انجام نشد.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('👤 مشاهده موکل',callback_data=f'clientview:{client_id}')],[InlineKeyboardButton('↩️ مدیریت موکل‌ها',callback_data='clients')]]))

async def client_delete_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'clients'): return
    cid=int(q.data.split(':')[1]); c=get_client(uid,cid)
    if not c: await q.message.reply_text('❌ موکل پیدا نشد.'); return
    kb=InlineKeyboardMarkup([[InlineKeyboardButton('⚠️ بله، حذف شود', callback_data=f'clientdelconfirm:{cid}'), InlineKeyboardButton('لغو', callback_data=f'clientview:{cid}')]])
    await q.message.reply_text(f'آیا موکل «{c["name"]}» حذف شود؟\n\n⚠️ پرونده‌های مرتبط حذف نمی‌شوند.', reply_markup=kb)

async def client_delete_confirm_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'clients'): return
    cid=int(q.data.split(':')[1]); ok=delete_client(uid,cid)
    await q.message.reply_text('✅ موکل حذف شد.' if ok else '❌ موکل پیدا نشد.', reply_markup=client_menu())

async def client_edit_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'clients'): return
    cid=int(q.data.split(':')[1]); c=get_client(uid,cid)
    if not c: await q.message.reply_text('❌ موکل پیدا نشد.'); return
    _clear_pending_inputs(context, keep='client_name'); context.user_data.update({'client_name':True,'client_edit_id':cid,'client_edit_data':c})
    await q.message.reply_text(f'✏️ نام موکل را وارد کنید.\nنام فعلی: {c["name"]}')

async def client_search_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'clients'): return
    _clear_pending_inputs(context, keep='client_search'); context.user_data['client_search']=True
    await q.message.reply_text('🔎 بخشی از نام یا شماره تماس موکل را وارد کنید:')

async def case_view_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    _clear_pending_inputs(context)
    cid=int(q.data.split(':')[1])
    c=get_case(uid,cid)
    if not c:
        await q.message.reply_text('❌ پرونده پیدا نشد.')
        return
    if c.get('status')=='archived':
        await q.message.reply_text(
            f'🗄️ پرونده «{c.get("file_name") or "بدون نام"}»\n\nاین پرونده بایگانی شده و برای جلوگیری از تغییر ناخواسته، فعلاً قابل ویرایش نیست.',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('↩️ بازگردانی پرونده',callback_data=f'archiverestore:{cid}')],
                [InlineKeyboardButton('🗑️ حذف دائمی پرونده',callback_data=f'casedelete:{cid}')],
                [InlineKeyboardButton('🗄️ کمد پرونده‌ها',callback_data='archivedcases')],
            ])
        )
        return
    set_active_case(uid, cid)
    status_label = {'processing':'در حال ثبت','completed':'ثبت شده','failed':'خطا در ثبت'}.get(c.get('status'), c.get('status','نامشخص'))
    if MINIAPP_URL:
        await q.message.reply_text('🚀 این پرونده را می‌توانید یک‌جا در میزکار Mini App ادامه دهید.', reply_markup=miniapp_keyboard(cid))
    await q.message.reply_text(
        f'📁 پرونده «{c.get("file_name") or "بدون نام"}»\n'
        f'وضعیت: {status_label}\n\n'
        'این پرونده اکنون پرونده فعال شماست.\n'
        'عملیات موردنظر را از دکمه‌های زیر انتخاب کنید:',
        reply_markup=case_menu(cid)
    )


async def case_workspace_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    _clear_pending_inputs(context)
    cid=int(q.data.split(':')[1]); ws=case_workspace(uid,cid)
    if not ws:
        await q.message.reply_text('❌ پرونده پیدا نشد.'); return
    c=ws['case']; status_label={'processing':'در حال پردازش','completed':'فعال/ثبت‌شده','failed':'خطادار','archived':'آرشیوشده'}.get(c.get('status'),c.get('status','—'))
    priority={'urgent':'🔴 فوری','high':'🟠 بالا','normal':'🟢 عادی','low':'⚪ پایین'}.get(c.get('priority'),'🟢 عادی')
    lines=[f'📊 نمای کلی پرونده «{c.get("file_name") or "بدون نام"}»','',f'وضعیت: {status_label}',f'مرحله: {c.get("stage") or "جدید"}',f'اولویت: {priority}',f'👤 موکل: {"، ".join(ws["clients"]) if ws["clients"] else "ثبت نشده"}',f'📄 اسناد: {ws["document_count"]}',f'🗂 نسخه‌ها: {ws["version_count"]}',f'📝 کارهای باز: {ws["open_tasks"]}']
    lines += ['',f'➡️ اقدام بعدی: {c.get("next_action") or "هنوز تعیین نشده"}']
    if ws['important_dates']:
        lines += ['', '📅 تاریخ‌های مهم نزدیک/ثبت‌شده:']
        lines += [f'• {d["date_jalali"]} — {d["description"]}' for d in ws['important_dates'][:5]]
    lines += ['', f'🕒 آخرین به‌روزرسانی: {(c.get("updated_at") or c.get("created_at") or "—")[:19]}']
    await q.message.reply_text('\n'.join(lines), reply_markup=case_menu(cid))

async def case_issues_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    _clear_pending_inputs(context)
    try: cid=int(q.data.split(':')[1])
    except Exception: return
    if not get_case(uid,cid):
        await q.message.reply_text('❌ پرونده پیدا نشد.', reply_markup=case_menu(cid)); return
    set_active_case(uid,cid)
    try:
        result=await asyncio.to_thread(build_case_issues, uid, cid)
        await reply_long(q.message, format_case_issues(result))
    except Exception:
        logger.exception('case issues failed for user=%s case=%s',uid,cid)
        await q.message.reply_text('❌ استخراج مسائل حقوقی پرونده انجام نشد. لطفاً دوباره تلاش کنید.')
    await q.message.reply_text('📁 ادامه پرونده:',reply_markup=case_menu(cid))


async def case_evidence_cb(update, context):
    """V153: show claim-to-evidence matrix with source-level provenance."""
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    _clear_pending_inputs(context)
    try: cid=int(q.data.split(':')[1])
    except Exception: return
    if not get_case(uid,cid):
        await q.message.reply_text('❌ پرونده پیدا نشد.', reply_markup=case_menu(cid)); return
    set_active_case(uid,cid)
    try:
        result=await asyncio.to_thread(build_evidence_matrix, uid, cid)
        await reply_long(q.message, format_evidence_matrix(result))
    except Exception:
        logger.exception('case evidence failed for user=%s case=%s',uid,cid)
        await q.message.reply_text('❌ ساخت ماتریس ادعا و مدرک انجام نشد. لطفاً دوباره تلاش کنید.')
    await q.message.reply_text('📁 ادامه پرونده:',reply_markup=case_menu(cid))


async def case_authority_cb(update, context):
    """V154: show issue/claim to legal-authority mapping with provenance."""
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    _clear_pending_inputs(context)
    try: cid=int(q.data.split(':')[1])
    except Exception: return
    if not get_case(uid,cid):
        await q.message.reply_text('❌ پرونده پیدا نشد.', reply_markup=case_menu(cid)); return
    set_active_case(uid,cid)
    try:
        result=await asyncio.to_thread(build_case_authorities, uid, cid)
        await reply_long(q.message, format_case_authorities(result))
    except Exception:
        logger.exception('case authority failed for user=%s case=%s',uid,cid)
        await q.message.reply_text('❌ نقشه مستندات قانونی پرونده ساخته نشد. لطفاً دوباره تلاش کنید.')
    await q.message.reply_text('📁 ادامه پرونده:',reply_markup=case_menu(cid))

async def case_strategy_cb(update, context):
    """V155: show a conservative, traceable defense-strategy frame."""
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    _clear_pending_inputs(context)
    try: cid=int(q.data.split(':')[1])
    except Exception: return
    if not get_case(uid,cid):
        await q.message.reply_text('❌ پرونده پیدا نشد.', reply_markup=case_menu(cid)); return
    set_active_case(uid,cid)
    try:
        result=await asyncio.to_thread(build_case_strategies, uid, cid)
        await reply_long(q.message, format_case_strategies(result))
    except Exception:
        logger.exception('case strategy failed for user=%s case=%s',uid,cid)
        await q.message.reply_text('❌ نقشه استراتژی دفاعی پرونده ساخته نشد. لطفاً دوباره تلاش کنید.')
    await q.message.reply_text('📁 ادامه پرونده:',reply_markup=case_menu(cid))

async def case_analysis_menu_cb(update, context):
    """Unified case analyzer: specialized trees are internal modules, not user-facing tools."""
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    _clear_pending_inputs(context)
    try: cid=int(q.data.split(':')[1])
    except Exception: return
    if not get_case(uid,cid):
        await q.message.reply_text('❌ پرونده پیدا نشد.', reply_markup=case_menu(cid)); return
    set_active_case(uid,cid)
    text_value=get_case_text(uid,cid)
    if not text_value:
        await q.message.reply_text('❌ متن قابل استفاده‌ای برای تحلیل پرونده موجود نیست.', reply_markup=case_menu(cid)); return
    try:
        result=await asyncio.to_thread(build_case_guidance,text_value)
        await reply_long(q.message, format_case_guidance(result))
    except Exception:
        logger.exception('unified case analyzer failed for user=%s case=%s',uid,cid)
        await q.message.reply_text('❌ تحلیل یکپارچه پرونده انجام نشد. لطفاً دوباره تلاش کنید.')
    await q.message.reply_text('📁 ادامه پرونده:',reply_markup=case_menu(cid))


async def case_drafting_menu_cb(update, context):
    """Compact user-facing drafting workspace; V149-V160 stay internal."""
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    _clear_pending_inputs(context)
    try: cid=int(q.data.split(':')[1])
    except Exception: return
    c=get_case(uid,cid)
    if not c:
        await q.message.reply_text('❌ پرونده پیدا نشد.', reply_markup=case_menu(cid)); return
    if c.get('status')=='archived':
        await q.message.reply_text('🗄️ این پرونده بایگانی شده و لایحه‌نویسی آن قابل ویرایش نیست.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('↩️ بازگردانی پرونده',callback_data=f'archiverestore:{cid}')],[InlineKeyboardButton('🗄️ کمد پرونده‌ها',callback_data='archivedcases')]])); return
    set_active_case(uid,cid)
    context.user_data['draft_workflow_case_id']=cid
    state=load_workflow_state(uid,cid)
    label='▶️ شروع لایحه' if state.get('status') in {'NOT_STARTED','DONE','CANCELLED'} else '▶️ ادامه لایحه'
    rows=[[InlineKeyboardButton(label, callback_data=f'cstart161:{cid}')]]
    if state.get('status') in {'READY_FOR_REVIEW','NEEDS_LAWYER_REVIEW'}:
        rows.append([InlineKeyboardButton('📄 مشاهده پیش‌نویس', callback_data=f'coutput160:{cid}')])
    if state.get('status') in {'NEEDS_INFORMATION','WAITING_FOR_INPUT'}:
        rows.append([InlineKeyboardButton('⚠️ مشاهده اطلاعات ناقص', callback_data=f'cinfo161:{cid}')])
    rows += [
        [InlineKeyboardButton('📊 وضعیت لایحه', callback_data=f'cstatus161:{cid}')],
        [InlineKeyboardButton('⬅️ بازگشت به پرونده', callback_data=f'caseview:{cid}')],
    ]
    await q.message.reply_text(
        '📝 لایحه‌نویسی\n\n'
        'این بخش مراحل تحلیل، تنظیم، بازبینی و کنترل لایحه را به‌صورت یکپارچه انجام می‌دهد.\n'
        'لازم نیست مراحل داخلی را جداگانه اجرا کنید.',
        reply_markup=InlineKeyboardMarkup(rows))


async def case_workflow_answer_162_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    try: cid=int(q.data.split(':')[1])
    except Exception: return
    if not get_case(uid,cid):
        await q.message.reply_text('❌ پرونده پیدا نشد.')
        return
    state=load_workflow_state(uid,cid)
    preflight=state.get('preflight') or {}
    question=next_required_question(preflight, set(state.get('deferred') or []))
    if not question and state.get('waiting_question_key'):
        question={'key':state.get('waiting_question_key'),'question':'لطفاً اطلاعات این مورد را وارد کنید.'}
    if not question:
        await q.message.reply_text('✅ اطلاعات ضروری تکمیل است. از گزینه ادامه استفاده کنید.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('▶️ ادامه', callback_data=f'cstart161:{cid}')]]))
        return
    state['waiting_question_key']=question.get('key')
    save_workflow_state(uid,cid,state,'WAITING_FOR_INPUT')
    context.user_data[f'draft_workflow:{cid}']=state
    context.user_data[f'draft_workflow_waiting_answer:{cid}']=True
    context.user_data[f'draft_workflow_question:{cid}']=question.get('key')
    await q.message.reply_text('✏️ '+str(question.get('question') or question.get('label') or 'لطفاً اطلاعات این مورد را وارد کنید.')+'\n\nاگر فعلاً پاسخ را نمی‌دانید، بنویسید «نمی‌دانم».')


async def case_workflow_skip_162_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    try: cid=int(q.data.split(':')[1])
    except Exception: return
    if not get_case(uid,cid):
        await q.message.reply_text('❌ پرونده پیدا نشد.')
        return
    state=load_workflow_state(uid,cid)
    key=context.user_data.get(f'draft_workflow_question:{cid}') or state.get('waiting_question_key')
    deferred=set(state.get('deferred') or [])
    if key:
        deferred.add(key)
    state['deferred']=list(deferred); state['waiting_question_key']=None
    state['answers']=dict(state.get('answers') or {})
    state['preflight']=state.get('preflight') or {}
    save_workflow_state(uid,cid,state,'NEEDS_INFORMATION')
    context.user_data[f'draft_workflow:{cid}']=state
    context.user_data.pop(f'draft_workflow_waiting_answer:{cid}',None)
    context.user_data.pop(f'draft_workflow_question:{cid}',None)
    await q.message.reply_text('ℹ️ این مورد به‌عنوان واقعیت ثبت نمی‌شود. اگر برای ادامه قابل اغماض باشد، سیستم با هشدار ادامه می‌دهد.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('▶️ ادامه با اطلاعات فعلی', callback_data=f'ccontinue161:{cid}')],[InlineKeyboardButton('✏️ پاسخ به مورد بعدی', callback_data=f'canswer162:{cid}')],[InlineKeyboardButton('⬅️ لایحه‌نویسی', callback_data=f'cdrafting:{cid}')]]))


async def case_start_workflow_161_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    try: cid=int(q.data.split(':')[1])
    except Exception: return
    if not get_case(uid,cid):
        await q.message.reply_text('❌ پرونده پیدا نشد.')
        return
    set_active_case(uid,cid)
    key=f'draft_workflow:{cid}'
    await q.message.reply_text('📝 در حال بررسی پرونده...\n\n🔎 اطلاعات لازم بررسی می‌شود؛ اگر مورد ضروری ناقص باشد فقط همان مورد را از شما می‌پرسیم.')
    try:
        state=load_workflow_state(uid,cid)
        answers=dict(state.get('answers') or {})
        allow_incomplete=bool(context.user_data.pop(f'draft_workflow_allow_incomplete:{cid}', False))
        # If the user explicitly chose "continue with current info", keep that decision
        # for this run only; it is never persisted as a fact.
        result=await asyncio.to_thread(run_drafting_workflow, uid, cid, brief_type='لایحه دفاعیه', answers=answers, deferred=set(state.get('deferred') or []), allow_incomplete=allow_incomplete)
        state.update({
            'status': result.get('status'), 'case_id': cid,
            'preflight': result.get('preflight'), 'gate': result.get('gate'),
            'output': result.get('output'), 'answers': answers,
            'waiting_question_key': None,
        })
        if result.get('status') == 'NEEDS_INFORMATION':
            question=next_required_question(result.get('preflight') or {})
            if question:
                state['waiting_question_key']=question.get('key')
                save_workflow_state(uid,cid,state,'WAITING_FOR_INPUT')
                context.user_data[key]=state
                context.user_data[f'draft_workflow_question:{cid}']=question.get('key')
                context.user_data[f'draft_workflow_waiting_answer:{cid}']=False
                rows=[[InlineKeyboardButton('✏️ پاسخ به این مورد', callback_data=f'canswer162:{cid}')],
                      [InlineKeyboardButton('⏭️ فعلاً رد کن', callback_data=f'cskip162:{cid}')],
                      [InlineKeyboardButton('⬅️ لایحه‌نویسی', callback_data=f'cdrafting:{cid}')]]
                await q.message.reply_text(workflow_question_text(result.get('preflight') or {}), reply_markup=InlineKeyboardMarkup(rows))
            else:
                save_workflow_state(uid,cid,state,'NEEDS_INFORMATION')
            return
        if result.get('status') == 'CASE_NOT_FOUND':
            save_workflow_state(uid,cid,state,'CASE_NOT_FOUND')
            await q.message.reply_text('❌ پرونده پیدا نشد.')
            return
        save_workflow_state(uid,cid,state,result.get('status') or 'NEEDS_LAWYER_REVIEW')
        context.user_data[key]=state
        out=result.get('output') or {}
        await reply_long(q.message, render_output_overview(out))
        rows=[[InlineKeyboardButton('📄 مشاهده پیش‌نویس', callback_data=f'couttext160:{cid}')],
              [InlineKeyboardButton('📤 دریافت فایل Word / PDF', callback_data=f'coutput160:{cid}')],
              [InlineKeyboardButton('🔍 موارد نیازمند بررسی', callback_data=f'coutgate160:{cid}')],
              [InlineKeyboardButton('📊 وضعیت لایحه', callback_data=f'cstatus161:{cid}')],
              [InlineKeyboardButton('⬅️ بازگشت به لایحه‌نویسی', callback_data=f'cdrafting:{cid}')]]
        await q.message.reply_text(workflow_label(result), reply_markup=InlineKeyboardMarkup(rows))
    except Exception:
        logger.exception('unified drafting workflow failed for user=%s case=%s',uid,cid)
        state=load_workflow_state(uid,cid)
        state['last_error']='workflow_execution_failed'
        save_workflow_state(uid,cid,state,'ERROR')
        await q.message.reply_text('❌ اجرای لایحه‌نویسی انجام نشد. لطفاً دوباره تلاش کنید.')


async def case_continue_workflow_161_cb(update, context):
    q=update.callback_query; uid=q.from_user.id
    try: cid=int(q.data.split(':')[1])
    except Exception: return
    set_active_case(uid,cid)
    context.user_data[f'draft_workflow_allow_incomplete:{cid}']=True
    await case_start_workflow_161_cb(update, context)


async def case_workflow_info_161_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    try: cid=int(q.data.split(':')[1])
    except Exception: return
    state=load_workflow_state(uid,cid)
    items=(state.get('preflight') or {}).get('workflow_required_missing') or []
    lines=['⚠️ اطلاعات موردنیاز','']
    for item in items[:10]:
        lines.append('• '+str(item.get('label') or item.get('key') or 'مورد نامشخص'))
    await q.message.reply_text('\n'.join(lines) if len(lines)>2 else '✅ مورد ضروری ناقصی ثبت نشده است.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('▶️ ادامه', callback_data=f'cstart161:{cid}')],[InlineKeyboardButton('⬅️ لایحه‌نویسی', callback_data=f'cdrafting:{cid}')]]))


async def case_workflow_status_161_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    try: cid=int(q.data.split(':')[1])
    except Exception: return
    state=load_workflow_state(uid,cid)
    status=state.get('status') or 'NOT_STARTED'
    labels={'NOT_STARTED':'شروع نشده','WAITING_FOR_INPUT':'منتظر پاسخ شما','NEEDS_INFORMATION':'نیازمند تکمیل اطلاعات','READY_TO_RUN':'آماده اجرا','READY_FOR_REVIEW':'آماده بازبینی','NEEDS_LAWYER_REVIEW':'نیازمند بررسی وکیل','DONE':'تکمیل شده','ERROR':'متوقف‌شده؛ قابل ادامه'}
    await q.message.reply_text(f'📊 وضعیت لایحه\n\nوضعیت: {labels.get(status,status)}', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('▶️ ادامه', callback_data=f'cstart161:{cid}')],[InlineKeyboardButton('⬅️ لایحه‌نویسی', callback_data=f'cdrafting:{cid}')]]))


async def case_draft_cb(update, context):
    """V156: build a structured, source-traceable draft from V149-V155."""
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    _clear_pending_inputs(context)
    try: cid=int(q.data.split(':')[1])
    except Exception: return
    if not get_case(uid,cid):
        await q.message.reply_text('❌ پرونده پیدا نشد.', reply_markup=case_menu(cid)); return
    set_active_case(uid,cid)
    _invalidate_v160_cache(context, cid)
    try:
        result=await asyncio.to_thread(build_case_draft, uid, cid, brief_type='لایحه دفاعیه')
        await reply_long(q.message, render_case_draft(result))
    except Exception:
        logger.exception('case draft V156 failed for user=%s case=%s',uid,cid)
        await q.message.reply_text('❌ پیش‌نویس ساختاری پرونده ساخته نشد. لطفاً دوباره تلاش کنید.')
    await q.message.reply_text('📁 ادامه پرونده:', reply_markup=case_menu(cid))

async def case_adversarial_review_cb(update, context):
    """V157: adversarial review of the structured V156 draft."""
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    _clear_pending_inputs(context)
    try: cid=int(q.data.split(':')[1])
    except Exception: return
    if not get_case(uid,cid):
        await q.message.reply_text('❌ پرونده پیدا نشد.', reply_markup=case_menu(cid)); return
    set_active_case(uid,cid)
    _invalidate_v160_cache(context, cid)
    try:
        result=await asyncio.to_thread(build_case_adversarial_review, uid, cid, brief_type='لایحه دفاعیه')
        await reply_long(q.message, render_adversarial_review(result))
    except Exception:
        logger.exception('case adversarial review V157 failed for user=%s case=%s',uid,cid)
        await q.message.reply_text('❌ بازبینی خصمانه انجام نشد. لطفاً دوباره تلاش کنید.')
    await q.message.reply_text('📁 ادامه پرونده:', reply_markup=case_menu(cid))

async def case_rewrite_158_cb(update, context):
    """V158: apply only deterministic, finding-scoped rewrites to the V156 draft."""
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    _clear_pending_inputs(context)
    try: cid=int(q.data.split(':')[1])
    except Exception: return
    if not get_case(uid,cid):
        await q.message.reply_text('❌ پرونده پیدا نشد.'); return
    set_active_case(uid,cid)
    _invalidate_v160_cache(context, cid)
    try:
        result=await asyncio.to_thread(build_case_rewrite, uid, cid, brief_type='لایحه دفاعیه')
        await reply_long(q.message, render_rewrite(result))
    except Exception:
        logger.exception('case V158 rewrite failed for user=%s case=%s',uid,cid)
        await q.message.reply_text('❌ بازنویسی کنترل‌شده V158 انجام نشد. لطفاً دوباره تلاش کنید.')
    await q.message.reply_text('📁 ادامه پرونده:', reply_markup=case_menu(cid))

async def case_consistency_gate_159_cb(update, context):
    """V159: read-only citation and consistency gate over V158 output."""
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    _clear_pending_inputs(context)
    try: cid=int(q.data.split(':')[1])
    except Exception: return
    if not get_case(uid,cid):
        await q.message.reply_text('❌ پرونده پیدا نشد.'); return
    set_active_case(uid,cid)
    _invalidate_v160_cache(context, cid)
    try:
        result=await asyncio.to_thread(build_case_consistency_gate, uid, cid, brief_type='لایحه دفاعیه')
        await reply_long(q.message, render_consistency_gate(result))
    except Exception:
        logger.exception('case V159 consistency gate failed for user=%s case=%s',uid,cid)
        await q.message.reply_text('❌ کنترل سازگاری V159 انجام نشد. لطفاً دوباره تلاش کنید.')
    await q.message.reply_text('📁 ادامه پرونده:', reply_markup=case_menu(cid))


async def _build_v160_for_case(uid: int, cid: int, context=None, *, force_refresh: bool = False):
    """Build V160 once per active user/case window so all output buttons share one gate snapshot."""
    cache_key = f"v160_gate:{int(cid)}"
    if context is not None and not force_refresh:
        cached = context.user_data.get(cache_key)
        if cached and (time.time() - float(cached.get("cached_at", 0))) < 300:
            return build_case_output(cached.get("gate") or {})
    gate = await asyncio.to_thread(build_case_consistency_gate, uid, cid, brief_type='لایحه دفاعیه')
    if context is not None:
        # Keep only the current case snapshot; output reports must remain mutually consistent.
        for key in list(context.user_data.keys()):
            if str(key).startswith("v160_gate:") and key != cache_key:
                context.user_data.pop(key, None)
        context.user_data[cache_key] = {"cached_at": time.time(), "gate": gate}
    return build_case_output(gate)


def _invalidate_v160_cache(context, cid: int) -> None:
    if context is not None:
        context.user_data.pop(f"v160_gate:{int(cid)}", None)


async def case_output_160_cb(update, context):
    """V160: read-only presentation/export menu over the V159-gated artifact."""
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    _clear_pending_inputs(context)
    try: cid=int(q.data.split(':')[1])
    except Exception: return
    if not get_case(uid,cid):
        await q.message.reply_text('❌ پرونده پیدا نشد.'); return
    set_active_case(uid,cid)
    try:
        result=await _build_v160_for_case(uid,cid,context)
        await reply_long(q.message, render_output_overview(result))
        await q.message.reply_text(
            '📤 خروجی V160',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('📝 دریافت Word قابل ویرایش', callback_data=f'coutdocx160:{cid}')],
                [InlineKeyboardButton('📄 دریافت PDF متنی', callback_data=f'coutpdf160:{cid}')],
                [InlineKeyboardButton('🔍 گزارش تغییرات V158', callback_data=f'coutchg160:{cid}')],
                [InlineKeyboardButton('🧪 گزارش Gate V159', callback_data=f'coutgate160:{cid}')],
                [InlineKeyboardButton('📚 Trace و منابع', callback_data=f'coutsrc160:{cid}')],
                [InlineKeyboardButton('⬅️ بازگشت به drafting', callback_data=f'cdrafting:{cid}')],
            ]))
    except Exception:
        logger.exception('case V160 output failed for user=%s case=%s',uid,cid)
        await q.message.reply_text('❌ ساخت خروجی V160 انجام نشد. لطفاً دوباره تلاش کنید.')


async def case_output_docx_160_cb(update, context):
    """Send an editable Word document generated from the same gated draft."""
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    _clear_pending_inputs(context)
    try: cid=int(q.data.split(':')[1])
    except Exception: return
    if not get_case(uid,cid):
        await q.message.reply_text('❌ پرونده پیدا نشد.')
        return
    try:
        result=await _build_v160_for_case(uid,cid,context)
        docx_bytes=await asyncio.to_thread(build_case_docx, result)
        bio=BytesIO(docx_bytes)
        bio.name=f'legal_brief_{cid}.docx'
        await q.message.reply_document(
            document=bio, filename=bio.name,
            caption='📝 فایل Word قابل ویرایش — پیش‌نویس است و پیش از استفاده باید توسط وکیل بررسی شود.'
        )
    except Exception:
        logger.exception('V160 Word output failed for user=%s case=%s',uid,cid)
        await q.message.reply_text('❌ ساخت یا ارسال فایل Word انجام نشد. لطفاً دوباره تلاش کنید.')


async def case_output_pdf_160_cb(update, context):
    """V166.2: send the gated user-facing draft as a Persian PDF document."""
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    _clear_pending_inputs(context)
    try: cid=int(q.data.split(':')[1])
    except Exception: return
    if not get_case(uid,cid):
        await q.message.reply_text('❌ پرونده پیدا نشد.')
        return
    try:
        result=await _build_v160_for_case(uid,cid,context)
        pdf_bytes=await asyncio.to_thread(build_case_pdf, result)
        bio=BytesIO(pdf_bytes)
        bio.name=f'legal_brief_{cid}.pdf'
        await q.message.reply_document(
            document=bio,
            filename=bio.name,
            caption='📄 پیش‌نویس لایحه آماده شد\n⚖️ این فایل همچنان نیازمند بررسی و تأیید وکیل است.'
        )
    except Exception:
        logger.exception('V166.2 PDF output failed for user=%s case=%s',uid,cid)
        await q.message.reply_text('❌ ساخت یا ارسال PDF لایحه انجام نشد. لطفاً دوباره تلاش کنید.')


async def case_output_text_160_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    _clear_pending_inputs(context)
    try: cid=int(q.data.split(':')[1])
    except Exception: return
    if not get_case(uid,cid): await q.message.reply_text('❌ پرونده پیدا نشد.'); return
    try:
        result=await _build_v160_for_case(uid,cid,context)
        await reply_long(q.message, render_case_text(result))
    except Exception:
        logger.exception('V160 text output failed for user=%s case=%s',uid,cid)
        await q.message.reply_text('❌ نمایش متن V160 انجام نشد.')


async def case_output_changes_160_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    _clear_pending_inputs(context)
    try: cid=int(q.data.split(':')[1])
    except Exception: return
    if not get_case(uid,cid): await q.message.reply_text('❌ پرونده پیدا نشد.'); return
    try:
        result=await _build_v160_for_case(uid,cid,context)
        await reply_long(q.message, render_change_report(result))
    except Exception:
        logger.exception('V160 change report failed for user=%s case=%s',uid,cid)
        await q.message.reply_text('❌ گزارش تغییرات ساخته نشد.')


async def case_output_gate_160_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    _clear_pending_inputs(context)
    try: cid=int(q.data.split(':')[1])
    except Exception: return
    if not get_case(uid,cid): await q.message.reply_text('❌ پرونده پیدا نشد.'); return
    try:
        result=await _build_v160_for_case(uid,cid,context)
        await reply_long(q.message, render_gate_report(result))
    except Exception:
        logger.exception('V160 gate report failed for user=%s case=%s',uid,cid)
        await q.message.reply_text('❌ گزارش Gate ساخته نشد.')


async def case_output_source_160_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    _clear_pending_inputs(context)
    try: cid=int(q.data.split(':')[1])
    except Exception: return
    if not get_case(uid,cid): await q.message.reply_text('❌ پرونده پیدا نشد.'); return
    try:
        result=await _build_v160_for_case(uid,cid,context)
        await reply_long(q.message, render_source_report(result))
    except Exception:
        logger.exception('V160 source report failed for user=%s case=%s',uid,cid)
        await q.message.reply_text('❌ گزارش Trace ساخته نشد.')




async def case_check_tree_cb(update, context):
    """Run the local cheque decision tree on the active case text."""
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    _clear_pending_inputs(context)
    try: cid=int(q.data.split(':')[1])
    except Exception: return
    if not get_case(uid,cid):
        await q.message.reply_text('❌ پرونده پیدا نشد.')
        return
    set_active_case(uid,cid)
    text_value=get_case_text(uid,cid)
    if not text_value:
        await q.message.reply_text('❌ متن قابل استفاده‌ای برای درخت بررسی چک در این پرونده موجود نیست.', reply_markup=case_menu(cid)); return
    try:
        result=await asyncio.to_thread(interactive_check_start,text_value)
        context.user_data['check_tree_state'] = result
        context.user_data['check_tree_case_id'] = cid
        if result.get('status') == 'active':
            node=result['state']['index'] if 'state' in result else result.get('index',0)
            node_obj=_INTERACTIVE_NODES[node]
            kb=[[InlineKeyboardButton(label, callback_data=f'ccstep:{cid}:{code}')] for label,code in node_obj['choices']]
            kb.append([InlineKeyboardButton('❌ بستن درخت', callback_data=f'ccclose:{cid}')])
            await q.message.reply_text(format_interactive_question(node_obj, node+1, len(_INTERACTIVE_NODES)), reply_markup=InlineKeyboardMarkup(kb))
        else:
            await reply_long(q.message, format_interactive_result(result))
    except Exception:
        logger.exception('case cheque tree failed for user=%s case=%s',uid,cid)
        await q.message.reply_text('❌ ساخت درخت بررسی چک انجام نشد. لطفاً دوباره تلاش کنید.')
    return

async def case_check_tree_step_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    try:
        _,cid_s,choice=q.data.split(':',2); cid=int(cid_s)
    except Exception: return
    if not get_case(uid,cid): return
    if context.user_data.get('check_tree_case_id') != cid:
        await q.message.reply_text('⚠️ این درخت دیگر فعال نیست؛ دوباره «درخت بررسی چک» را از پرونده باز کنید.')
        return
    state=context.user_data.get('check_tree_state')
    try:
        result=interactive_check_step(state, choice)
        if result.get('status') == 'question':
            context.user_data['check_tree_state']=result['state']
            node=result['node']; step=result['state']['index']
            kb=[[InlineKeyboardButton(label, callback_data=f'ccstep:{cid}:{code}')] for label,code in node['choices']]
            if step > 0:
                kb.append([InlineKeyboardButton('↩️ شروع دوباره', callback_data=f'ccrestart:{cid}')])
            kb.append([InlineKeyboardButton('❌ بستن درخت', callback_data=f'ccclose:{cid}')])
            await q.message.edit_text(format_interactive_question(node, step+1, len(_INTERACTIVE_NODES)), reply_markup=InlineKeyboardMarkup(kb))
        elif result.get('status') == 'complete':
            context.user_data.pop('check_tree_state',None); context.user_data.pop('check_tree_case_id',None)
            await q.message.edit_text(format_interactive_result(result), reply_markup=case_menu(cid))
        else:
            await q.message.reply_text('❌ پاسخ این مرحله معتبر نیست.')
    except Exception:
        logger.exception('interactive cheque tree failed for user=%s case=%s',uid,cid)
        await q.message.reply_text('❌ ادامه درخت انجام نشد؛ دوباره درخت را باز کنید.')

async def case_check_tree_restart_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    try: cid=int(q.data.split(':')[1])
    except Exception: return
    text_value=get_case_text(uid,cid)
    if not text_value: return
    result=interactive_check_start(text_value)
    context.user_data['check_tree_state']=result; context.user_data['check_tree_case_id']=cid
    node=_INTERACTIVE_NODES[0]
    kb=[[InlineKeyboardButton(label, callback_data=f'ccstep:{cid}:{code}')] for label,code in node['choices']]
    kb.append([InlineKeyboardButton('❌ بستن درخت', callback_data=f'ccclose:{cid}')])
    await q.message.edit_text(format_interactive_question(node,1,len(_INTERACTIVE_NODES)), reply_markup=InlineKeyboardMarkup(kb))

async def case_check_tree_close_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    try: cid=int(q.data.split(':')[1])
    except Exception: return
    context.user_data.pop('check_tree_state',None); context.user_data.pop('check_tree_case_id',None)
    await q.message.edit_text('🌳 درخت بررسی چک بسته شد.', reply_markup=case_menu(cid))

async def case_lease_tree_cb(update, context):
    """Run the local interactive lease decision tree on the active case."""
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    _clear_pending_inputs(context)
    try: cid=int(q.data.split(':')[1])
    except Exception: return
    if not get_case(uid,cid):
        await q.message.reply_text('❌ پرونده پیدا نشد.'); return
    set_active_case(uid,cid); text_value=get_case_text(uid,cid)
    if not text_value:
        await q.message.reply_text('❌ متن قابل استفاده‌ای برای درخت بررسی اجاره در این پرونده موجود نیست.', reply_markup=case_menu(cid)); return
    try:
        result=await asyncio.to_thread(interactive_lease_start,text_value)
        context.user_data['lease_tree_state']=result; context.user_data['lease_tree_case_id']=cid
        if result.get('status')=='active':
            node_obj=_LEASE_INTERACTIVE_NODES[result['state']['index']]
            kb=[[InlineKeyboardButton(label, callback_data=f'clstep:{cid}:{code}')] for label,code in node_obj['choices']]
            kb.append([InlineKeyboardButton('❌ بستن درخت', callback_data=f'clclose:{cid}')])
            await q.message.reply_text(format_lease_question(node_obj,1,len(_LEASE_INTERACTIVE_NODES)), reply_markup=InlineKeyboardMarkup(kb))
        else:
            await reply_long(q.message, format_lease_result(result))
    except Exception:
        logger.exception('case lease tree failed for user=%s case=%s',uid,cid)
        await q.message.reply_text('❌ ساخت درخت بررسی اجاره انجام نشد. لطفاً دوباره تلاش کنید.')

async def case_lease_tree_step_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    try: _,cid_s,choice=q.data.split(':',2); cid=int(cid_s)
    except Exception: return
    if not get_case(uid,cid): return
    if context.user_data.get('lease_tree_case_id')!=cid:
        await q.message.reply_text('⚠️ این درخت دیگر فعال نیست؛ دوباره «درخت بررسی اجاره» را باز کنید.'); return
    state=context.user_data.get('lease_tree_state')
    try:
        result=interactive_lease_step(state,choice)
        if result.get('status')=='question':
            context.user_data['lease_tree_state']=result['state']; node=result['node']; step=result['state']['index']
            kb=[[InlineKeyboardButton(label, callback_data=f'clstep:{cid}:{code}')] for label,code in node['choices']]
            if step>0: kb.append([InlineKeyboardButton('↩️ شروع دوباره', callback_data=f'clrestart:{cid}')])
            kb.append([InlineKeyboardButton('❌ بستن درخت', callback_data=f'clclose:{cid}')])
            await q.message.edit_text(format_lease_question(node,step+1,len(_LEASE_INTERACTIVE_NODES)), reply_markup=InlineKeyboardMarkup(kb))
        elif result.get('status')=='complete':
            context.user_data.pop('lease_tree_state',None); context.user_data.pop('lease_tree_case_id',None)
            await q.message.edit_text(format_lease_result(result), reply_markup=case_menu(cid))
        else: await q.message.reply_text('❌ پاسخ این مرحله معتبر نیست.')
    except Exception:
        logger.exception('interactive lease tree failed for user=%s case=%s',uid,cid)
        await q.message.reply_text('❌ ادامه درخت اجاره انجام نشد؛ دوباره درخت را باز کنید.')

async def case_lease_tree_restart_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    try: cid=int(q.data.split(':')[1])
    except Exception: return
    text_value=get_case_text(uid,cid)
    if not text_value: return
    result=interactive_lease_start(text_value)
    context.user_data['lease_tree_state']=result; context.user_data['lease_tree_case_id']=cid
    node=_LEASE_INTERACTIVE_NODES[0]
    kb=[[InlineKeyboardButton(label, callback_data=f'clstep:{cid}:{code}')] for label,code in node['choices']]
    kb.append([InlineKeyboardButton('❌ بستن درخت', callback_data=f'clclose:{cid}')])
    await q.message.edit_text(format_lease_question(node,1,len(_LEASE_INTERACTIVE_NODES)), reply_markup=InlineKeyboardMarkup(kb))

async def case_lease_tree_close_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    try: cid=int(q.data.split(':')[1])
    except Exception: return
    context.user_data.pop('lease_tree_state',None); context.user_data.pop('lease_tree_case_id',None)
    await q.message.edit_text('🌳 درخت بررسی اجاره بسته شد.', reply_markup=case_menu(cid))

async def case_contract_tree_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    _clear_pending_inputs(context)
    try: cid=int(q.data.split(':')[1])
    except Exception: return
    if not get_case(uid,cid): await q.message.reply_text('❌ پرونده پیدا نشد.'); return
    set_active_case(uid,cid); text_value=get_case_text(uid,cid)
    if not text_value:
        await q.message.reply_text('❌ متن قابل استفاده‌ای برای درخت قرارداد و تعهدات در این پرونده موجود نیست.', reply_markup=case_menu(cid)); return
    try:
        result=await asyncio.to_thread(interactive_contract_start,text_value)
        context.user_data['contract_tree_state']=result; context.user_data['contract_tree_case_id']=cid
        if result.get('status')=='active':
            node=_CONTRACT_INTERACTIVE_NODES[result['state']['index']]
            kb=[[InlineKeyboardButton(label, callback_data=f'cctstep:{cid}:{code}')] for label,code in node['choices']]
            kb.append([InlineKeyboardButton('❌ بستن درخت', callback_data=f'cctclose:{cid}')])
            await q.message.reply_text(format_contract_question(node,1,len(_CONTRACT_INTERACTIVE_NODES)), reply_markup=InlineKeyboardMarkup(kb))
        else: await reply_long(q.message, format_contract_result(result))
    except Exception:
        logger.exception('contract tree failed for user=%s case=%s',uid,cid)
        await q.message.reply_text('❌ ساخت درخت قرارداد و تعهدات انجام نشد. لطفاً دوباره تلاش کنید.')

async def case_contract_tree_step_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    try: _,cid_s,choice=q.data.split(':',2); cid=int(cid_s)
    except Exception: return
    if not get_case(uid,cid): return
    if context.user_data.get('contract_tree_case_id')!=cid:
        await q.message.reply_text('⚠️ این درخت دیگر فعال نیست؛ دوباره «درخت قرارداد و تعهدات» را باز کنید.'); return
    state=context.user_data.get('contract_tree_state')
    try:
        result=interactive_contract_step(state,choice)
        if result.get('status')=='question':
            context.user_data['contract_tree_state']=result['state']; node=result['node']; step=result['state']['index']
            kb=[[InlineKeyboardButton(label, callback_data=f'cctstep:{cid}:{code}')] for label,code in node['choices']]
            if step>0: kb.append([InlineKeyboardButton('↩️ شروع دوباره', callback_data=f'cctrestart:{cid}')])
            kb.append([InlineKeyboardButton('❌ بستن درخت', callback_data=f'cctclose:{cid}')])
            await q.message.edit_text(format_contract_question(node,step+1,len(_CONTRACT_INTERACTIVE_NODES)), reply_markup=InlineKeyboardMarkup(kb))
        elif result.get('status')=='complete':
            context.user_data.pop('contract_tree_state',None); context.user_data.pop('contract_tree_case_id',None)
            await q.message.edit_text(format_contract_result(result), reply_markup=case_menu(cid))
        else: await q.message.reply_text('❌ پاسخ این مرحله معتبر نیست.')
    except Exception:
        logger.exception('interactive contract tree failed for user=%s case=%s',uid,cid)
        await q.message.reply_text('❌ ادامه درخت قرارداد انجام نشد؛ دوباره درخت را باز کنید.')

async def case_contract_tree_restart_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    try: cid=int(q.data.split(':')[1])
    except Exception: return
    text_value=get_case_text(uid,cid)
    if not text_value: return
    result=interactive_contract_start(text_value)
    context.user_data['contract_tree_state']=result; context.user_data['contract_tree_case_id']=cid
    node=_CONTRACT_INTERACTIVE_NODES[0]
    kb=[[InlineKeyboardButton(label, callback_data=f'cctstep:{cid}:{code}')] for label,code in node['choices']]
    kb.append([InlineKeyboardButton('❌ بستن درخت', callback_data=f'cctclose:{cid}')])
    await q.message.edit_text(format_contract_question(node,1,len(_CONTRACT_INTERACTIVE_NODES)), reply_markup=InlineKeyboardMarkup(kb))

async def case_contract_tree_close_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    try: cid=int(q.data.split(':')[1])
    except Exception: return
    context.user_data.pop('contract_tree_state',None); context.user_data.pop('contract_tree_case_id',None)
    await q.message.edit_text('🌳 درخت قرارداد و تعهدات بسته شد.', reply_markup=case_menu(cid))

async def case_claims_tree_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    _clear_pending_inputs(context)
    try: cid=int(q.data.split(':')[1])
    except Exception: return
    if not get_case(uid,cid): await q.message.reply_text('❌ پرونده پیدا نشد.'); return
    set_active_case(uid,cid); text_value=get_case_text(uid,cid)
    if not text_value:
        await q.message.reply_text('❌ متن قابل استفاده‌ای برای درخت مطالبات و دیون در این پرونده موجود نیست.', reply_markup=case_menu(cid)); return
    try:
        result=await asyncio.to_thread(interactive_claims_start,text_value)
        context.user_data['claims_tree_state']=result; context.user_data['claims_tree_case_id']=cid
        if result.get('status')=='active':
            node=_CLAIMS_INTERACTIVE_NODES[result['index']]
            kb=[[InlineKeyboardButton(label, callback_data=f'cclstep:{cid}:{code}')] for label,code in node['choices']]
            kb.append([InlineKeyboardButton('❌ بستن درخت', callback_data=f'cclclose:{cid}')])
            await q.message.reply_text(format_claims_question(node,1,len(_CLAIMS_INTERACTIVE_NODES)), reply_markup=InlineKeyboardMarkup(kb))
        else: await reply_long(q.message, format_claims_result(result))
    except Exception:
        logger.exception('claims tree failed for user=%s case=%s',uid,cid)
        await q.message.reply_text('❌ ساخت درخت مطالبات و دیون انجام نشد. لطفاً دوباره تلاش کنید.')

async def case_claims_tree_step_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    try: _,cid_s,choice=q.data.split(':',2); cid=int(cid_s)
    except Exception: return
    if not get_case(uid,cid): return
    if context.user_data.get('claims_tree_case_id')!=cid:
        await q.message.reply_text('⚠️ این درخت دیگر فعال نیست؛ دوباره «درخت مطالبات و دیون» را باز کنید.'); return
    try:
        result=interactive_claims_step(context.user_data.get('claims_tree_state'),choice)
        if result.get('status')=='question':
            context.user_data['claims_tree_state']=result['state']; node=result['node']; step=result['state']['index']
            kb=[[InlineKeyboardButton(label, callback_data=f'cclstep:{cid}:{code}')] for label,code in node['choices']]
            if step>0: kb.append([InlineKeyboardButton('↩️ شروع دوباره', callback_data=f'cclrestart:{cid}')])
            kb.append([InlineKeyboardButton('❌ بستن درخت', callback_data=f'cclclose:{cid}')])
            await q.message.edit_text(format_claims_question(node,step+1,len(_CLAIMS_INTERACTIVE_NODES)), reply_markup=InlineKeyboardMarkup(kb))
        elif result.get('status')=='complete':
            context.user_data.pop('claims_tree_state',None); context.user_data.pop('claims_tree_case_id',None)
            await q.message.edit_text(format_claims_result(result), reply_markup=case_menu(cid))
        else: await q.message.reply_text('❌ پاسخ این مرحله معتبر نیست.')
    except Exception:
        logger.exception('interactive claims tree failed for user=%s case=%s',uid,cid)
        await q.message.reply_text('❌ ادامه درخت مطالبات انجام نشد؛ دوباره درخت را باز کنید.')

async def case_claims_tree_restart_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    try: cid=int(q.data.split(':')[1])
    except Exception: return
    text_value=get_case_text(uid,cid)
    if not text_value: return
    result=interactive_claims_start(text_value); context.user_data['claims_tree_state']=result; context.user_data['claims_tree_case_id']=cid
    node=_CLAIMS_INTERACTIVE_NODES[0]
    kb=[[InlineKeyboardButton(label, callback_data=f'cclstep:{cid}:{code}')] for label,code in node['choices']]
    kb.append([InlineKeyboardButton('❌ بستن درخت', callback_data=f'cclclose:{cid}')])
    await q.message.edit_text(format_claims_question(node,1,len(_CLAIMS_INTERACTIVE_NODES)), reply_markup=InlineKeyboardMarkup(kb))

async def case_claims_tree_close_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    try: cid=int(q.data.split(':')[1])
    except Exception: return
    context.user_data.pop('claims_tree_state',None); context.user_data.pop('claims_tree_case_id',None)
    await q.message.edit_text('🌳 درخت مطالبات و دیون بسته شد.', reply_markup=case_menu(cid))

async def case_property_tree_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    _clear_pending_inputs(context)
    try: cid=int(q.data.split(':')[1])
    except Exception: return
    if not get_case(uid,cid): await q.message.reply_text('❌ پرونده پیدا نشد.'); return
    set_active_case(uid,cid); text_value=get_case_text(uid,cid)
    if not text_value:
        await q.message.reply_text('❌ متن قابل استفاده‌ای برای درخت املاک و مالکیت در این پرونده موجود نیست.', reply_markup=case_menu(cid)); return
    try:
        result=await asyncio.to_thread(interactive_property_start,text_value)
        context.user_data['property_tree_state']=result; context.user_data['property_tree_case_id']=cid
        if result.get('status')=='active':
            node=_PROPERTY_INTERACTIVE_NODES[result['index']]
            kb=[[InlineKeyboardButton(label, callback_data=f'cptstep:{cid}:{code}')] for label,code in node['choices']]
            kb.append([InlineKeyboardButton('❌ بستن درخت', callback_data=f'cptclose:{cid}')])
            await q.message.reply_text(format_property_question(node,1,len(_PROPERTY_INTERACTIVE_NODES)), reply_markup=InlineKeyboardMarkup(kb))
        else: await reply_long(q.message, format_property_result(result))
    except Exception:
        logger.exception('property tree failed for user=%s case=%s',uid,cid)
        await q.message.reply_text('❌ ساخت درخت املاک و مالکیت انجام نشد. لطفاً دوباره تلاش کنید.')

async def case_property_tree_step_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    try: _,cid_s,choice=q.data.split(':',2); cid=int(cid_s)
    except Exception: return
    if not get_case(uid,cid): return
    if context.user_data.get('property_tree_case_id')!=cid:
        await q.message.reply_text('⚠️ این درخت دیگر فعال نیست؛ دوباره «درخت املاک و مالکیت» را باز کنید.'); return
    try:
        result=interactive_property_step(context.user_data.get('property_tree_state'),choice)
        if result.get('status')=='question':
            context.user_data['property_tree_state']=result['state']; node=result['node']; step=result['state']['index']
            kb=[[InlineKeyboardButton(label, callback_data=f'cptstep:{cid}:{code}')] for label,code in node['choices']]
            if step>0: kb.append([InlineKeyboardButton('↩️ شروع دوباره', callback_data=f'cptrestart:{cid}')])
            kb.append([InlineKeyboardButton('❌ بستن درخت', callback_data=f'cptclose:{cid}')])
            await q.message.edit_text(format_property_question(node,step+1,len(_PROPERTY_INTERACTIVE_NODES)), reply_markup=InlineKeyboardMarkup(kb))
        elif result.get('status')=='complete':
            context.user_data.pop('property_tree_state',None); context.user_data.pop('property_tree_case_id',None)
            await q.message.edit_text(format_property_result(result), reply_markup=case_menu(cid))
        else: await q.message.reply_text('❌ پاسخ این مرحله معتبر نیست.')
    except Exception:
        logger.exception('interactive property tree failed for user=%s case=%s',uid,cid)
        await q.message.reply_text('❌ ادامه درخت املاک انجام نشد؛ دوباره درخت را باز کنید.')

async def case_property_tree_restart_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    try: cid=int(q.data.split(':')[1])
    except Exception: return
    text_value=get_case_text(uid,cid)
    if not text_value: return
    result=interactive_property_start(text_value); context.user_data['property_tree_state']=result; context.user_data['property_tree_case_id']=cid
    node=_PROPERTY_INTERACTIVE_NODES[0]
    kb=[[InlineKeyboardButton(label, callback_data=f'cptstep:{cid}:{code}')] for label,code in node['choices']]
    kb.append([InlineKeyboardButton('❌ بستن درخت', callback_data=f'cptclose:{cid}')])
    await q.message.edit_text(format_property_question(node,1,len(_PROPERTY_INTERACTIVE_NODES)), reply_markup=InlineKeyboardMarkup(kb))

async def case_property_tree_close_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    try: cid=int(q.data.split(':')[1])
    except Exception: return
    context.user_data.pop('property_tree_state',None); context.user_data.pop('property_tree_case_id',None)
    await q.message.edit_text('🌳 درخت املاک و مالکیت بسته شد.', reply_markup=case_menu(cid))

async def case_timeline_cb(update, context):
    """V151: show the source-linked legal chronology, not Telegram audit events."""
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    _clear_pending_inputs(context); cid=int(q.data.split(':')[1])
    if not get_case(uid,cid):
        await q.message.reply_text('❌ پرونده پیدا نشد.'); return
    try:
        chronology=await asyncio.to_thread(build_case_chronology, uid, cid, True)
        text=format_chronology(chronology, 18)
    except Exception:
        logger.exception('V151 chronology failed for user=%s case=%s', uid, cid)
        await q.message.reply_text('❌ ساخت خط زمانی پرونده انجام نشد.'); return
    await q.message.reply_text(text, reply_markup=case_menu(cid))

async def case_tasks_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    _clear_pending_inputs(context); cid=int(q.data.split(':')[1])
    if not get_case(uid,cid):
        await q.message.reply_text('❌ پرونده پیدا نشد.'); return
    tasks=list_case_tasks(uid,cid,False,20)
    lines=['📝 کارهای پرونده','']
    if tasks:
        for t in tasks: lines.append(f'⬜ #{t["id"]} {t["title"]}' + (f' — موعد: {_fa_num_text(str(t["due_at"])[:10])}' if t.get('due_at') else ' — بدون موعد'))
    else: lines.append('✨ کار باز برای این پرونده ندارید.')
    rows=[]
    for t in tasks[:8]: rows.append([InlineKeyboardButton(f'✅ انجام شد #{t["id"]}',callback_data=f'ctask:done:{t["id"]}'),InlineKeyboardButton('🗑 حذف',callback_data=f'ctask:delete:{t["id"]}')])
    rows += [[InlineKeyboardButton('➕ کار جدید برای این پرونده',callback_data=f'ctasknew:{cid}')],[InlineKeyboardButton('📊 نمای کلی',callback_data=f'cworkspace:{cid}'),InlineKeyboardButton('↩️ پرونده',callback_data=f'caseview:{cid}')]]
    await q.message.reply_text('\n'.join(lines),reply_markup=InlineKeyboardMarkup(rows))

async def case_task_new_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id; cid=int(q.data.split(':')[1])
    if not await _require_lawyer(q, context, 'cases'): return
    if not get_case(uid,cid): await q.message.reply_text('❌ پرونده پیدا نشد.'); return
    _clear_pending_inputs(context,keep='awaiting_case_task_title'); context.user_data['awaiting_case_task_title']=cid
    await q.message.reply_text('📝 عنوان کار این پرونده را وارد کنید:')

async def case_task_action_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id; parts=q.data.split(':')
    if not await _require_lawyer(q, context, 'cases'): return
    try: action,tid=parts[1],int(parts[2])
    except Exception: return
    with _db.conn() as c:
        row=c.execute('SELECT case_id FROM case_tasks WHERE id=? AND user_id=?',(tid,uid)).fetchone()
    cid=int(row['case_id']) if row else None
    ok=set_case_task_done(uid,tid,True) if action=='done' else delete_case_task(uid,tid) if action=='delete' else False
    await q.message.reply_text('✅ انجام شد.' if ok else '❌ کار پیدا نشد.')
    if ok and cid: await case_tasks_cb(update,context)

async def case_status_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id; cid=int(q.data.split(':')[1])
    if not await _require_lawyer(q, context, 'cases'): return
    _clear_pending_inputs(context); c=get_case(uid,cid)
    if not c: await q.message.reply_text('❌ پرونده پیدا نشد.'); return
    stage_rows=[[InlineKeyboardButton('جدید',callback_data=f'cstage:new:{cid}'),InlineKeyboardButton('در حال بررسی',callback_data=f'cstage:review:{cid}')],[InlineKeyboardButton('در اقدام',callback_data=f'cstage:action:{cid}'),InlineKeyboardButton('مختومه',callback_data=f'cstage:closed:{cid}')]]
    priority_rows=[[InlineKeyboardButton('🟢 عادی',callback_data=f'cprio:normal:{cid}'),InlineKeyboardButton('🟠 بالا',callback_data=f'cprio:high:{cid}')],[InlineKeyboardButton('🔴 فوری',callback_data=f'cprio:urgent:{cid}'),InlineKeyboardButton('⚪ پایین',callback_data=f'cprio:low:{cid}')]]
    await q.message.reply_text(f'⚙️ وضعیت پرونده\n\nمرحله فعلی: {c.get("stage") or "new"}\nاولویت فعلی: {c.get("priority") or "normal"}\nاقدام بعدی: {c.get("next_action") or "تعیین نشده"}\n\nمرحله را انتخاب کنید:',reply_markup=InlineKeyboardMarkup(stage_rows+[[InlineKeyboardButton('— اولویت —',callback_data=f'noop:{cid}')]]+priority_rows+[[InlineKeyboardButton('✏️ تعیین اقدام بعدی',callback_data=f'cnextaction:{cid}')],[InlineKeyboardButton('↩️ پرونده',callback_data=f'caseview:{cid}')]]))

async def case_stage_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id; _,stage,cid=q.data.split(':')
    if not await _require_lawyer(q, context, 'cases'): return
    labels={'new':'new','review':'review','action':'action','closed':'closed'}
    if stage in labels and update_case_workspace(uid,int(cid),stage=labels[stage]):
        await q.message.reply_text('✅ مرحله پرونده به‌روزرسانی شد.',reply_markup=case_menu(int(cid)))

async def case_priority_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id; _,priority,cid=q.data.split(':')
    if not await _require_lawyer(q, context, 'cases'): return
    if update_case_workspace(uid,int(cid),priority=priority): await q.message.reply_text('✅ اولویت پرونده به‌روزرسانی شد.',reply_markup=case_menu(int(cid)))

async def case_next_action_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id; cid=int(q.data.split(':')[1])
    if not await _require_lawyer(q, context, 'cases'): return
    _clear_pending_inputs(context,keep='awaiting_case_next_action'); context.user_data['awaiting_case_next_action']=cid
    await q.message.reply_text('➡️ اقدام بعدی پرونده را در یک جمله وارد کنید:')

async def case_next_step_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    _clear_pending_inputs(context)
    cid=int(q.data.split(':')[1])
    if not get_case(uid,cid):
        await q.message.reply_text('❌ پرونده پیدا نشد.')
        return
    set_active_case(uid, cid)
    text_value=get_case_text(uid,cid)
    if not text_value:
        await q.message.reply_text('❌ متن قابل استفاده‌ای برای تشخیص قدم بعدی در این پرونده موجود نیست.', reply_markup=case_menu(cid))
        return
    try:
        result=await asyncio.to_thread(analyze_next_step, text_value)
        await reply_long(q.message, format_next_step(result))
    except Exception as e:
        logger.exception('case next-step failed')
        logger.exception('next-step analysis failed for user=%s case=%s', uid, cid)
        await q.message.reply_text('❌ تشخیص قدم بعدی پرونده انجام نشد. لطفاً دوباره تلاش کنید.')
    await q.message.reply_text('📁 ادامه پرونده:', reply_markup=case_menu(cid))


async def case_intelligence_cb(update, context):
    """Backward-compatible alias for the unified case analyzer."""
    q=update.callback_query
    if q:
        q.data = q.data.replace('cintel:', 'canalysis:', 1)
    return await case_analysis_menu_cb(update, context)


async def case_summary_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    _clear_pending_inputs(context)
    cid=int(q.data.split(':')[1])
    if not get_case(uid,cid):
        await q.message.reply_text('❌ پرونده پیدا نشد.')
        return
    set_active_case(uid, cid)
    text_value=get_case_text(uid,cid)
    if not text_value:
        await q.message.reply_text('❌ متن قابل استفاده‌ای برای خلاصه‌سازی در این پرونده موجود نیست.', reply_markup=case_menu(cid))
        return
    try:
        result=await asyncio.to_thread(analyze, text_value)
        if not result:
            raise RuntimeError('خلاصه‌ای تولید نشد.')
        await reply_long(q.message, case_summary_text(result))
    except Exception as e:
        logger.exception('case summary failed for user=%s case=%s', uid, cid)
        await q.message.reply_text('❌ خلاصه پرونده تولید نشد. لطفاً دوباره تلاش کنید.')
    await q.message.reply_text('📁 ادامه پرونده:', reply_markup=case_menu(cid))


async def case_summary_detailed_cb(update, context):
    """Backward-compatible alias for the canonical faithful case summary.

    The old detailed entry point duplicated the same analyzer and re-rendered
    summary snippets already present in ``analysis_text``. Keep old callback
    data working, but expose only one summary button in the case menu.
    """
    return await case_summary_cb(update, context)

async def case_relevant_laws_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    _clear_pending_inputs(context)
    cid=int(q.data.split(':')[1])
    if not get_case(uid,cid):
        await q.message.reply_text('❌ پرونده پیدا نشد.')
        return
    set_active_case(uid, cid)
    text_value=get_case_text(uid,cid)
    if not text_value:
        await q.message.reply_text('❌ متن قابل استفاده‌ای برای پیدا کردن مواد مرتبط در این پرونده موجود نیست.', reply_markup=case_menu(cid))
        return
    try:
        relevant=await asyncio.to_thread(find_relevant_laws, text_value, 10)
        if relevant:
            await reply_long(q.message, relevant_laws_text(relevant))
        else:
            await q.message.reply_text('❌ ماده یا منبع مرتبطی بر اساس متن این پرونده پیدا نشد.')
    except Exception as e:
        logger.exception('relevant laws failed for user=%s case=%s', uid, cid)
        await q.message.reply_text('❌ جستجوی مواد مرتبط انجام نشد. لطفاً دوباره تلاش کنید.')
    await q.message.reply_text('📁 ادامه پرونده:', reply_markup=case_menu(cid))


async def case_delete_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    _clear_pending_inputs(context)
    cid=int(q.data.split(':')[1])
    case = get_case(uid,cid)
    if not case:
        await q.message.reply_text('❌ پرونده پیدا نشد.')
        return
    case_name=(case.get('file_name') or 'بدون نام').strip()[:120]
    await q.message.reply_text(
        f'⚠️ حذف دائمی پرونده\n\nپرونده: «{case_name}»\n\nبا تأیید شما، فایل‌های ذخیره‌شده، متن استخراج‌شده، نسخه‌ها، یادداشت‌ها، تاریخ‌ها، کارها، رویدادهای Workspace، وضعیت لایحه‌نویسی و سابقه پرسش‌های AI این پرونده حذف می‌شوند.\n\nاین عملیات از داخل برنامه قابل بازگشت نیست.',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton('🗑️ تأیید حذف دائمی', callback_data=f'casedelconfirm:{cid}')],
            [InlineKeyboardButton('↩️ انصراف', callback_data=f'caseview:{cid}')],
        ])
    )

async def case_delete_confirm_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    _clear_pending_inputs(context)
    cid=int(q.data.split(':')[1])
    if not delete_case(uid,cid):
        await q.message.reply_text('❌ حذف پرونده انجام نشد یا پرونده پیدا نشد.')
        return
    await q.message.reply_text('🗑️ پرونده و داده‌های وابسته آن از سیستم اصلی حذف شد.', reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton('📂 پرونده‌ها و کارهای من', callback_data='cases')],
        [InlineKeyboardButton('🏠 منوی اصلی', callback_data='home')],
    ]))

async def case_archive_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    _clear_pending_inputs(context)
    cid=int(q.data.split(':')[1])
    c=get_case(uid,cid)
    if not c:
        await q.message.reply_text('❌ پرونده پیدا نشد.')
        return
    if c.get('status')=='processing':
        await q.message.reply_text('⏳ این پرونده هنوز در حال پردازش است. بعد از پایان پردازش می‌توانید آن را بایگانی کنید.', reply_markup=case_menu(cid))
        return
    if c.get('status')=='archived':
        await q.message.reply_text('🗄️ این پرونده از قبل بایگانی شده است.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🗄️ کمد پرونده‌ها',callback_data='archivedcases')]]))
        return
    if not archive_case(uid, cid):
        await q.message.reply_text('❌ انتقال پرونده به کمد انجام نشد.')
        return
    await q.message.reply_text('🗄️ پرونده بایگانی شد؛ اطلاعات و فایل‌های آن محفوظ مانده‌اند.', reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton('📂 پرونده‌ها و کارهای من', callback_data='cases')],
        [InlineKeyboardButton('🏠 منوی اصلی', callback_data='home')],
    ]))


async def case_note_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    cid=int(q.data.split(':')[1])
    c=get_case(uid,cid)
    if not c:
        await q.message.reply_text('❌ پرونده پیدا نشد.')
        return
    if c.get('status')=='archived':
        await q.message.reply_text('🗄️ این پرونده بایگانی شده و یادداشت آن قابل ویرایش نیست.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('↩️ بازگردانی پرونده',callback_data=f'archiverestore:{cid}')],[InlineKeyboardButton('🗄️ کمد پرونده‌ها',callback_data='archivedcases')]]))
        return
    set_active_case(uid,cid)
    note=get_case_lawyer_note(uid,cid)
    buttons=[[InlineKeyboardButton('📝 ثبت/ویرایش یادداشت', callback_data=f'cnoteedit:{cid}')]]
    if note and (note.get('note_text') or '').strip():
        await reply_long(q.message, '🗒️ یادداشت وکیل برای این پرونده\n\n'+note['note_text'])
        buttons.append([InlineKeyboardButton('🗑️ پاک کردن یادداشت', callback_data=f'cnoteclr:{cid}')])
    else:
        await q.message.reply_text('🗒️ برای این پرونده هنوز یادداشتی ثبت نشده است.')
    buttons.append([InlineKeyboardButton('📁 بازگشت به پرونده', callback_data=f'caseview:{cid}')])
    await q.message.reply_text('حداکثر حجم یادداشت: حدود ۱۰ صفحه متن.', reply_markup=InlineKeyboardMarkup(buttons))

async def case_note_edit_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    cid=int(q.data.split(':')[1])
    c=get_case(uid,cid)
    if not c:
        await q.message.reply_text('❌ پرونده پیدا نشد.')
        return
    if c.get('status')=='archived':
        await q.message.reply_text('🗄️ این پرونده بایگانی شده و یادداشت آن قابل ویرایش نیست.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('↩️ بازگردانی پرونده',callback_data=f'archiverestore:{cid}')],[InlineKeyboardButton('🗄️ کمد پرونده‌ها',callback_data='archivedcases')]]))
        return
    _clear_pending_inputs(context, keep='awaiting_case_note')
    context.user_data['awaiting_case_note']=cid
    await q.message.reply_text(f'📝 متن یادداشت وکیل را ارسال کنید.\n\nحداکثر {MAX_CASE_NOTE_CHARS:,} نویسه (حدود ۱۰ صفحه متن) مجاز است.\n\nیادداشت قبلی در صورت وجود، با متن جدید جایگزین می‌شود.')

async def case_note_clear_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    cid=int(q.data.split(':')[1])
    c=get_case(uid,cid)
    if not c:
        await q.message.reply_text('❌ پرونده پیدا نشد.')
        return
    if c.get('status')=='archived':
        await q.message.reply_text('🗄️ این پرونده بایگانی شده و یادداشت آن قابل ویرایش نیست.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('↩️ بازگردانی پرونده',callback_data=f'archiverestore:{cid}')],[InlineKeyboardButton('🗄️ کمد پرونده‌ها',callback_data='archivedcases')]]))
        return
    clear_case_lawyer_note(uid,cid)
    await q.message.reply_text('🗑️ یادداشت این پرونده پاک شد.', reply_markup=case_menu(cid))

async def case_file_action_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    parts=q.data.split(':')
    cid=int(parts[2])
    c=get_case(uid,cid)
    if not c:
        await q.message.reply_text('❌ پرونده پیدا نشد.')
        return
    if c.get('status')=='archived':
        await q.message.reply_text('🗄️ این پرونده بایگانی شده و امکان افزودن/مقایسه نسخه یا ثبت یادداشت در آن وجود ندارد.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('↩️ بازگردانی پرونده',callback_data=f'archiverestore:{cid}')],[InlineKeyboardButton('🗄️ کمد پرونده‌ها',callback_data='archivedcases')]]))
        return
    set_active_case(uid, cid)
    labels={'add':'📎 افزودن عکس و متن به پرونده','version':'📄 افزودن و مقایسه نسخه جدید پرونده با نسخه اصلی','note':'🗒️ یادداشت وکیل برای این پرونده'}
    if parts[1]=='add':
        count=count_case_additions(uid,cid)
        if count >= MAX_CASE_ADDITIONS:
            await q.message.reply_text(f'❌ سقف افزودن‌های این پرونده ({MAX_CASE_ADDITIONS} نوبت) پر شده است.', reply_markup=case_menu(cid))
            return
        _clear_pending_inputs(context, keep='awaiting_case_addition')
        context.user_data['awaiting_case_addition']=cid
        context.user_data.pop('case_addition_no',None)
        await q.message.reply_text(
            f'📎 افزودن عکس و متن به پرونده «{get_case(uid,cid).get("file_name") or "بدون نام"}»\n\n'
            f'یک نوبت افزودن می‌تواند حداکثر {MAX_CASE_ADDITION_FILES} فایل/عکس/متن داشته باشد.\n'
            f'نوبت‌های استفاده‌شده: {count} از {MAX_CASE_ADDITIONS}\n\n'
            'PDF/DOCX/TXT یا عکس بفرستید؛ متن را هم می‌توانید مستقیم ارسال کنید.\n'
            'پس از پایان، دکمه «✅ پایان افزودن» را بزنید.',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('✅ پایان افزودن', callback_data=f'cadddone:{cid}')]])
        )
        return
    if parts[1]=='version':
        count=count_case_versions(uid,cid)
        if count >= MAX_CASE_VERSIONS:
            await q.message.reply_text(f'❌ سقف نسخه‌های جدید این پرونده ({MAX_CASE_VERSIONS} نسخه) پر شده است.', reply_markup=case_menu(cid))
            return
        context.user_data['awaiting_case_version_file']=cid
        await q.message.reply_text(
            f'📄 افزودن و مقایسه نسخه جدید پرونده با نسخه اصلی\n\nنسخه اول/اصلی پرونده مبنای مقایسه است؛ فایل‌ها و مدارک بعدی جزو مبنای اصلی مقایسه نیستند. فایل نسخه جدید را ارسال کنید.\n\nعلاوه بر تفاوت متنی، مبلغ، تاریخ/مهلت، طرفین، خواسته/ادعا، تعهدات، مراجع قانونی، بندهای حساس و برخی وضعیت‌های پرداخت/رأی هم به‌صورت ساختاری استخراج و مقایسه می‌شوند.\n\nنسخه‌های جدید ثبت‌شده: {count} از {MAX_CASE_VERSIONS}',
            reply_markup=case_menu(cid)
        )
        return
    await q.message.reply_text(f'{labels.get(parts[1], "این قابلیت")}\n\n🚧 این بخش فعلاً در حال توسعه است و هنوز فعال نشده است.', reply_markup=case_menu(cid))


async def case_add_done_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    cid=int(q.data.split(':')[1])
    if not get_case(uid,cid):
        context.user_data.pop('awaiting_case_addition',None)
        context.user_data.pop('case_addition_no',None)
        await q.message.reply_text('❌ پرونده پیدا نشد.')
        return
    _clear_pending_inputs(context)
    set_active_case(uid,cid)
    await q.message.reply_text('✅ افزودن به پرونده پایان یافت. فایل‌های ثبت‌شده محفوظ هستند.', reply_markup=case_menu(cid))


async def case_text_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    _clear_pending_inputs(context)
    cid=int(q.data.split(':')[1])
    if not get_case(uid,cid):
        await q.message.reply_text('❌ پرونده پیدا نشد.'); return
    set_active_case(uid,cid)
    text_value=get_case_text(uid,cid)
    if not text_value: await q.message.reply_text('❌ متن استخراج‌شده‌ای موجود نیست.'); return
    await reply_long(q.message,'📄 متن استخراج‌شده:\n\n'+text_value)
    await q.message.reply_text('📁 ادامه پرونده:',reply_markup=case_menu(cid))


async def caseq_cb(update, context):
    q=update.callback_query; await q.answer(); cid=int(q.data.split(':')[1]); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    _clear_pending_inputs(context)
    if not get_case(uid,cid): await q.message.reply_text('❌ پرونده پیدا نشد.'); return
    set_active_case(uid,cid)
    context.user_data['awaiting_case_query']=cid
    await q.message.reply_text('🔎 عبارت موردنظر برای جستجو در این پرونده را ارسال کنید.')


async def case_ai_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    _clear_pending_inputs(context)
    cid=int(q.data.split(':')[1])
    set_active_case(uid, cid)
    context.user_data['ai_selected_case_id'] = cid
    context.user_data['ai_selected_feature'] = 'question'
    case=get_case(uid,cid)
    if not case: await q.message.reply_text('❌ پرونده پیدا نشد.'); return
    if not (AI_ENABLED and AI_EXTERNAL_DATA_CONSENT):
        await q.message.reply_text('🤖 دستیار AI پرونده فقط با فعال بودن AI و رضایت پردازش خارجی در دسترس است.', reply_markup=case_menu(cid))
        return
    if not get_case_text(uid,cid):
        await q.message.reply_text('❌ متن قابل استفاده‌ای در این پرونده موجود نیست.', reply_markup=case_menu(cid)); return
    set_active_case(uid,cid)
    context.user_data['awaiting_case_ai_question']=cid
    await q.message.reply_text(
        f'🤖 پرسش از هوش مصنوعی — پرونده «{str(case.get("file_name") or f"پرونده #{cid}")[:100]}»\n\n'
        'سؤال یا درخواست خود را درباره همین پرونده بفرستید.\n'
        'بعد از دریافت سؤال، مشخص می‌کنید چه مقدار از اطلاعات پرونده و سوابق سؤال‌وجواب برای AI ارسال شود.')


def _case_ai_context_keyboard(cid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('📌 خلاصه پرونده + پرامپت استاندارد', callback_data=f'caictx:summary:{cid}')],
        [InlineKeyboardButton('🔎 بخش مرتبط متن پرونده + پرامپت', callback_data=f'caictx:relevant:{cid}')],
        [InlineKeyboardButton('🧠 خلاصه + متن مرتبط + سؤال‌وجواب قبلی', callback_data=f'caictx:history:{cid}')],
        [InlineKeyboardButton('🚫 فقط سؤال من', callback_data=f'caictx:none:{cid}')],
        [InlineKeyboardButton('❌ لغو', callback_data=f'caseview:{cid}')],
    ])

async def case_ai_context_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    if not context.user_data.get('awaiting_case_ai_context_choice'): return
    parts=q.data.split(':')
    try: cid=int(parts[2])
    except Exception: return
    if not get_case(uid,cid):
        context.user_data.pop('awaiting_case_ai_context_choice',None)
        await q.message.reply_text('❌ پرونده پیدا نشد.'); return
    question=context.user_data.pop('case_ai_question','').strip()
    context.user_data.pop('awaiting_case_ai_context_choice',None)
    if not question:
        await q.message.reply_text('❌ سؤال پیدا نشد. دوباره از دکمه AI همین پرونده شروع کنید.', reply_markup=case_menu(cid)); return
    mode=parts[1]
    full_text=get_case_text(uid,cid)
    case_title=str(get_case(uid,cid).get('file_name') or f'پرونده #{cid}')
    standard_prompt=(
        'نقش: دستیار حقوقی فارسی برای کمک اولیه به وکیل.\n'
        'فقط بر اساس اطلاعات ارائه‌شده پاسخ بده؛ اگر اطلاعات یا منبع کافی نیست صریحاً بگو.\n'
        'ماده قانون، رأی، تاریخ، عدد یا واقعیت را حدس نزن. بین واقعیت پرونده، متن مستندات و تحلیل خودت تفکیک قائل شو.\n'
        'اگر برای پاسخ قطعی نیاز به بررسی منبع رسمی است، آن را صریحاً اعلام کن. پاسخ جایگزین بررسی تخصصی و منابع رسمی نیست.'
    )
    case_summary=''
    relevant=''
    history=''
    if mode in ('summary','history'):
        try:
            local=await asyncio.to_thread(analyze, full_text)
            bullets=[str(x.get('text','')).strip() for x in (local.get('summary') or []) if isinstance(x,dict) and x.get('text')]
            claims=[str(x.get('claim','')).strip() for x in (local.get('claims') or []) if isinstance(x,dict) and x.get('claim')]
            dates=[f'{x.get("value")} — {x.get("event","")}'.strip(' —') for x in (local.get('dates') or []) if isinstance(x,dict) and x.get('value')]
            parts=[str(x.get('name','')).strip() for x in (local.get('parties') or []) if isinstance(x,dict) and x.get('name')]
            lines=[]
            if local.get('document_type'): lines.append('نوع سند: '+str(local.get('document_type')))
            if parts: lines.append('طرفین/اشخاص: '+'، '.join(parts[:8]))
            if bullets: lines.append('خلاصه: '+' | '.join(bullets[:10]))
            if claims: lines.append('خواسته‌ها/ادعاها: '+' | '.join(claims[:8]))
            if dates: lines.append('تاریخ‌ها: '+' | '.join(dates[:8]))
            case_summary='\n'.join(lines)[:12000]
        except Exception:
            case_summary=''
    if mode in ('relevant','history'):
        hits=await asyncio.to_thread(local_case_search, full_text, question, 8)
        relevant='\n'.join(f'[صفحه {h.get("page")}] {h.get("text","")}' for h in hits)[:10000]
        if not relevant: relevant='برای سؤال فعلی، بخش متنی مرتبطی با جستجوی محلی پیدا نشد.'
    if mode=='history':
        last=get_last_case_ai_exchange(uid,cid)
        if last:
            history=('سؤال قبلی: '+str(last.get('question',''))[:4000]+'\n'+
                     'بخشی از پاسخ قبلی: '+str(last.get('answer',''))[:6000])
        else:
            history='سؤال‌وجواب قبلی برای این پرونده ثبت نشده است.'
    context_parts=[]
    if standard_prompt: context_parts.append(('پرامپت استاندارد',standard_prompt))
    if case_summary: context_parts.append(('خلاصه پرونده',case_summary))
    if relevant: context_parts.append(('بخش مرتبط از متن پرونده',relevant))
    if history: context_parts.append(('بخشی از سؤال‌وجواب قبلی',history))
    result=await dispatch_ai_question(update, context, question, case_summary='\n\n'.join(f'{k}:\n{v}' for k,v in context_parts), standard_prompt='', case_title=case_title, case_id=cid, context_mode=mode)
    return result


async def home_cb(update, context):
    q=update.callback_query; await q.answer(); _clear_pending_inputs(context); await q.message.reply_text('⚖️ منوی اصلی:',reply_markup=menu(q.from_user.id if q and getattr(q, 'from_user', None) else None))


async def ai_menu_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_lawyer(q, context, 'cases'): return
    _clear_pending_inputs(context)
    kb=InlineKeyboardMarkup([
        [InlineKeyboardButton('💬 پرسش حقوقی', callback_data='aifuture:question')],
        [InlineKeyboardButton('📄 تحلیل پرونده', callback_data='aifuture:documents')],
        [InlineKeyboardButton('🔎 بررسی ایرادها و تناقض‌ها', callback_data='aifuture:review')],
        [InlineKeyboardButton('✍️ نگارش و بازبینی متن حقوقی', callback_data='aifuture:drafting')],
        [InlineKeyboardButton('🏠 منوی اصلی', callback_data='home')],
    ])
    await q.message.reply_text(
        '🤖 دستیار هوشمند حقوقی\n\n'
        '«تحلیل پرونده» و «بررسی ایرادها و تناقض‌ها» فعال‌اند. هر دو ابتدا از متن استخراج‌شده به‌صورت محلی استفاده می‌کنند؛ در صورت فعال بودن مجوز ارسال داده و سهمیه، امکان بررسی تکمیلی با هوش مصنوعی هم وجود دارد.\n\n'
        '«پرسش حقوقی عمومی» فقط سؤال شما را ارسال می‌کند و به پرونده‌ها یا فایل‌ها دسترسی ضمنی ندارد. برای سؤال درباره پرونده ثبت‌شده، گزینه اول را انتخاب کنید تا زمینه ارسالی را خودتان تعیین کنید. نگارش و بازبینی متن از گردش‌کار پرونده استفاده می‌کند.',
        reply_markup=kb)


async def ai_future_placeholder_cb(update, context):
    q=update.callback_query
    await q.answer()
    if not await _require_lawyer(q, context, 'cases'):
        return
    _clear_pending_inputs(context)
    labels = {
        'question': 'پرسش حقوقی',
        'legal': 'پرسش حقوقی عمومی',
        'documents': 'تحلیل پرونده',
        'drafting': 'نگارش و بازبینی متن حقوقی',
        'review': 'بررسی ایرادها و تناقض‌ها',
    }
    feature = (q.data or '').partition(':')[2]
    label = labels.get(feature)
    if not label:
        await q.message.reply_text('این گزینه شناخته‌شده نیست.', reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton('↩️ بازگشت به دستیار هوشمند', callback_data='aimenu')],
            [InlineKeyboardButton('🏠 منوی اصلی', callback_data='home')],
        ]))
        return
    # These tools need a case context. Always ask the user to choose a case
    # explicitly instead of relying on a stale active-case selection.
    if feature in {'documents', 'drafting', 'review'}:
        rows = list_cases(q.from_user.id, 20)
        if not rows:
            await q.message.reply_text(
                '📂 هنوز پرونده‌ای ثبت نکرده‌اید. ابتدا یک پرونده بسازید تا این ابزار به آن متصل شود.',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('➕ پرونده جدید', callback_data='newcase')],
                    [InlineKeyboardButton('↩️ بازگشت به دستیار هوشمند', callback_data='aimenu')],
                ]))
            return
        active_case_id = get_active_case_id(q.from_user.id)
        kb = []
        for c in rows:
            cid = int(c['id'])
            prefix = '🟢 ' if active_case_id == cid else '📁 '
            case_label = (c.get('file_name') or f'پرونده #{cid}')[:48]
            kb.append([InlineKeyboardButton(
                f'{prefix}{case_label}', callback_data=f'aicasepick:{feature}:{cid}')])
        kb.append([InlineKeyboardButton('↩️ بازگشت به دستیار هوشمند', callback_data='aimenu')])
        kb.append([InlineKeyboardButton('🏠 منوی اصلی', callback_data='home')])
        await q.message.reply_text(
            f'📂 برای «{label}» ابتدا پرونده موردنظر را از کمد پرونده‌ها انتخاب کنید:',
            reply_markup=InlineKeyboardMarkup(kb))
        return

    # Keep the top-level menu compact while preserving both public Q&A and
    # case-context questions as explicit user choices.
    if feature == 'question':
        await q.message.reply_text(
            '💬 پرسش حقوقی\n\nمی‌خواهید یک سؤال عمومی بپرسید یا دربارهٔ پرونده‌ای ثبت‌شده سؤال کنید؟',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('⚖️ سؤال حقوقی عمومی', callback_data='aifuture:legal')],
                [InlineKeyboardButton('📁 سؤال دربارهٔ پرونده', callback_data='aicases')],
                [InlineKeyboardButton('↩️ بازگشت به دستیار هوشمند', callback_data='aimenu')],
            ]))
        return

    # Public legal Q&A requires no case context; ask only for the question.
    if feature == 'legal':
        if not (AI_ENABLED and AI_EXTERNAL_DATA_CONSENT):
            await q.message.reply_text(
                '🤖 پرسش حقوقی عمومی فعلاً در دسترس نیست؛ پردازش خارجی هوش مصنوعی یا رضایت ارسال داده فعال نیست. هیچ متنی ارسال نشد.',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('↩️ بازگشت به دستیار هوشمند', callback_data='aimenu')],
                    [InlineKeyboardButton('🏠 منوی اصلی', callback_data='home')],
                ]))
            return
        context.user_data['awaiting_ai_question'] = True
        await q.message.reply_text(
            '⚖️ پرسش حقوقی عمومی\n\nسؤال حقوقی خود را در یک پیام بنویسید. فقط متن همین سؤال برای پاسخ‌گویی ارسال می‌شود؛ پرونده‌ها و فایل‌های شما به‌صورت خودکار ضمیمه نمی‌شوند.\n\nاگر پاسخ به کشور/حوزه قضایی یا تاریخ خاصی وابسته است، آن را در سؤال مشخص کنید. پاسخ برای بررسی اولیه است و استنادهای مهم باید با منبع رسمی کنترل شوند.',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('❌ لغو', callback_data='aimenu')],
            ]))
        return
    await q.message.reply_text(
        f'🚧 «{label}» هنوز فعال نشده است.',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton('↩️ بازگشت به دستیار هوشمند', callback_data='aimenu')],
            [InlineKeyboardButton('🏠 منوی اصلی', callback_data='home')],
        ]))


async def ai_case_feature_select_cb(update, context):
    """Bind a future case-dependent AI tool to an explicitly selected case."""
    q = update.callback_query
    await q.answer()
    if not await _require_lawyer(q, context, 'cases'):
        return
    _clear_pending_inputs(context)
    try:
        _, feature, raw_cid = (q.data or '').split(':', 2)
        cid = int(raw_cid)
    except (ValueError, TypeError):
        await q.message.reply_text('❌ انتخاب پرونده معتبر نیست.', reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton('↩️ بازگشت به دستیار هوشمند', callback_data='aimenu')],
        ]))
        return
    labels = {
        'documents': 'تحلیل و خلاصه‌سازی پرونده',
        'drafting': 'نگارش و بازبینی متن حقوقی',
        'review': 'بررسی ایرادها و تناقض‌ها',
    }
    if feature not in labels:
        await q.message.reply_text('❌ این ابزار برای اتصال به پرونده شناخته‌شده نیست.')
        return
    case = get_case(q.from_user.id, cid)
    if not case or case.get('status') == 'archived':
        await q.message.reply_text('❌ پرونده پیدا نشد یا بایگانی شده است. لطفاً از کمد پرونده‌ها پرونده دیگری انتخاب کنید.',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('📂 انتخاب پرونده', callback_data=f'aifuture:{feature}')],
                [InlineKeyboardButton('↩️ بازگشت به دستیار هوشمند', callback_data='aimenu')],
            ]))
        return
    if not set_active_case(q.from_user.id, cid):
        await q.message.reply_text('❌ اتصال به پرونده انجام نشد. لطفاً دوباره تلاش کنید.')
        return
    context.user_data['ai_selected_case_id'] = cid
    context.user_data['ai_selected_feature'] = feature
    case_title = str(case.get('file_name') or f'پرونده #{cid}')[:100]

    if feature == 'drafting':
        # Reuse the existing durable drafting/review workflow; do not create a
        # parallel AI drafting engine or spend an API call just to open the menu.
        context.user_data['draft_workflow_case_id'] = cid
        state = load_workflow_state(q.from_user.id, cid)
        workflow_status = str(state.get('status') or 'NOT_STARTED')
        start_label = '▶️ شروع لایحه' if workflow_status in {'NOT_STARTED', 'DONE', 'CANCELLED'} else '▶️ ادامه لایحه'
        rows = [[InlineKeyboardButton(start_label, callback_data=f'cstart161:{cid}')]]
        if workflow_status in {'READY_FOR_REVIEW', 'NEEDS_LAWYER_REVIEW'}:
            rows.append([InlineKeyboardButton('📄 مشاهده و بازبینی پیش‌نویس', callback_data=f'coutput160:{cid}')])
        if workflow_status in {'NEEDS_INFORMATION', 'WAITING_FOR_INPUT'}:
            rows.append([InlineKeyboardButton('⚠️ مشاهده اطلاعات ناقص', callback_data=f'cinfo161:{cid}')])
        rows.extend([
            [InlineKeyboardButton('📊 وضعیت لایحه', callback_data=f'cstatus161:{cid}')],
            [InlineKeyboardButton('📁 باز کردن پرونده', callback_data=f'caseview:{cid}')],
            [InlineKeyboardButton('↩️ بازگشت به دستیار هوشمند', callback_data='aimenu')],
        ])
        await q.message.reply_text(
            f'✍️ نگارش و بازبینی متن حقوقی\nپرونده: «{case_title}»\n\n'
            'از فرایند یکپارچه موجود برای تهیه پیش‌نویس، کنترل موارد ناقص و بازبینی خروجی استفاده کنید. '
            'پیش‌نویس خروجی اولیه است و پیش از استفاده باید توسط وکیل بررسی شود.\n\n'
            'برای نمایش این منو هیچ درخواست خارجی یا مصرف سهمیه هوش مصنوعی انجام نمی‌شود.',
            reply_markup=InlineKeyboardMarkup(rows))
        return

    if feature == 'review':
        # Conservative local scan first; external AI is an optional, consent-gated
        # enhancement. The original file/image/PDF is never sent to the model.
        extracted_text = get_case_text(q.from_user.id, cid)
        if not extracted_text.strip():
            await q.message.reply_text(
                '❌ متن قابل استفاده‌ای در اسناد این پرونده پیدا نشد. ابتدا استخراج متن یا OCR محلی اسناد را بررسی کنید.\n'
                'فایل اصلی یا تصویر برای بررسی خارجی ارسال نمی‌شود.',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('📁 باز کردن همین پرونده', callback_data=f'caseview:{cid}')],
                    [InlineKeyboardButton('↩️ بازگشت به دستیار هوشمند', callback_data='aimenu')],
                ]))
            return
        status_msg = await q.message.reply_text('⏳ در حال بررسی محلی متن پرونده برای یافتن موارد قابل تطبیق…')
        try:
            local_findings = brief_consistency_check('', case_text=extracted_text)
            local_report = format_consistency_report(local_findings)
        except Exception:
            logger.exception('local contradiction review failed for user=%s case=%s', q.from_user.id, cid)
            await status_msg.edit_text('❌ بررسی محلی انجام نشد. اطلاعات پرونده تغییری نکرده است؛ لطفاً دوباره تلاش کنید.')
            return

        if not (AI_ENABLED and AI_EXTERNAL_DATA_CONSENT):
            await status_msg.edit_text('ℹ️ بررسی محلی آماده شد؛ هوش مصنوعی خارجی فعال نیست یا اجازه ارسال داده داده نشده است. هیچ متنی به سرویس خارجی ارسال نشد.')
            await reply_long(q.message, '🔎 بررسی ایرادها و تناقض‌ها\n\n' + local_report)
        else:
            from .core.ai_entitlement import AIEntitlementService
            entitlement = AIEntitlementService()
            ok, reservation = entitlement.reserve_question(q.from_user.id)
            if not ok or not reservation:
                await status_msg.edit_text('ℹ️ سهمیه هوش مصنوعی در دسترس نیست؛ نتیجه محلی آماده شد و هیچ درخواست خارجی ارسال نشد.')
                await reply_long(q.message, '🔎 بررسی محلی ایرادها و تناقض‌ها\n\n' + local_report)
            else:
                try:
                    ai_report = await asyncio.to_thread(review_case_contradictions, extracted_text, local_report)
                    entitlement.commit(q.from_user.id, reservation)
                    await status_msg.edit_text(f'✅ بررسی تکمیلی انجام شد: «{case_title}»')
                    await reply_long(q.message, ai_report)
                except Exception:
                    entitlement.refund(q.from_user.id, reservation)
                    logger.exception('AI contradiction review failed for user=%s case=%s', q.from_user.id, cid)
                    await status_msg.edit_text('⚠️ بررسی تکمیلی هوش مصنوعی دریافت نشد و سهمیه مصرف نشد؛ نتیجه محلی در ادامه آمده است.')
                    await reply_long(q.message, '🔎 بررسی محلی ایرادها و تناقض‌ها\n\n' + local_report)
        await q.message.reply_text('📁 ادامه پرونده:', reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton('🧾 بررسی تخصصی قراردادهای این پرونده', callback_data=f'aicontract:{cid}')],
            [InlineKeyboardButton('📁 باز کردن همین پرونده', callback_data=f'caseview:{cid}')],
            [InlineKeyboardButton('↩️ بازگشت به دستیار هوشمند', callback_data='aimenu')],
            [InlineKeyboardButton('🏠 منوی اصلی', callback_data='home')],
        ]))
        return

    if feature == 'documents':
        # Local extraction/analysis is the baseline; external AI is an explicit,
        # consent-gated enhancement and receives extracted text only.
        extracted_text = get_case_text(q.from_user.id, cid)
        if not extracted_text.strip():
            await q.message.reply_text(
                '❌ متن قابل استفاده‌ای در اسناد این پرونده پیدا نشد. ابتدا استخراج متن یا OCR محلی اسناد را بررسی کنید.\n'
                'فایل اصلی یا تصویر برای خلاصه‌سازی به سرویس خارجی ارسال نمی‌شود.',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('📁 باز کردن همین پرونده', callback_data=f'caseview:{cid}')],
                    [InlineKeyboardButton('↩️ بازگشت به دستیار هوشمند', callback_data='aimenu')],
                ]))
            return
        status_msg = await q.message.reply_text('⏳ در حال بررسی متن استخراج‌شده پرونده…')
        try:
            local_result = await asyncio.to_thread(analyze, extracted_text)
            if not local_result:
                raise RuntimeError('تحلیل محلی خروجی نداشت')
            local_report = case_summary_text(local_result)
        except Exception:
            logger.exception('local AI-submenu case summary failed for user=%s case=%s', q.from_user.id, cid)
            await status_msg.edit_text('❌ تحلیل محلی پرونده انجام نشد. اطلاعات پرونده تغییری نکرده است؛ لطفاً دوباره تلاش کنید.')
            return

        if not (AI_ENABLED and AI_EXTERNAL_DATA_CONSENT):
            await status_msg.edit_text('ℹ️ خلاصه محلی آماده شد. هوش مصنوعی خارجی فعال نیست یا اجازه ارسال داده به سرویس خارجی داده نشده؛ بنابراین هیچ متنی به سرویس خارجی ارسال نشد.')
            await reply_long(q.message, local_report)
        else:
            from .core.ai_entitlement import AIEntitlementService
            entitlement = AIEntitlementService()
            ok, reservation = entitlement.reserve_question(q.from_user.id)
            if not ok or not reservation:
                await status_msg.edit_text('ℹ️ سهمیه هوش مصنوعی در دسترس نیست؛ گزارش محلی آماده شد و هیچ درخواست خارجی ارسال نشد.')
                await reply_long(q.message, local_report)
            else:
                try:
                    ai_report = await asyncio.to_thread(summarize_case_for_lawyer, extracted_text, local_report)
                    entitlement.commit(q.from_user.id, reservation)
                    await status_msg.edit_text(f'✅ خلاصه‌سازی تکمیل شد: «{case_title}»')
                    await reply_long(q.message, ai_report)
                except Exception:
                    entitlement.refund(q.from_user.id, reservation)
                    logger.exception('AI case summary failed for user=%s case=%s', q.from_user.id, cid)
                    await status_msg.edit_text('⚠️ خلاصه هوش مصنوعی دریافت نشد و سهمیه مصرف نشد؛ گزارش محلی پرونده در ادامه آمده است.')
                    await reply_long(q.message, local_report)
        await q.message.reply_text('📁 ادامه پرونده:', reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton('📁 باز کردن همین پرونده', callback_data=f'caseview:{cid}')],
            [InlineKeyboardButton('↩️ بازگشت به دستیار هوشمند', callback_data='aimenu')],
            [InlineKeyboardButton('🏠 منوی اصلی', callback_data='home')],
        ]))
        return

    await q.message.reply_text(
        f'🔗 پرونده «{case_title}» به ابزار «{labels[feature]}» متصل شد.',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton('📁 باز کردن همین پرونده', callback_data=f'caseview:{cid}')],
            [InlineKeyboardButton('↩️ بازگشت به دستیار هوشمند', callback_data='aimenu')],
            [InlineKeyboardButton('🏠 منوی اصلی', callback_data='home')],
        ]))


async def ai_contract_review_cb(update, context):
    """Select a built-in playbook, then run the consent-gated review."""
    q = update.callback_query
    await q.answer()
    if not await _require_lawyer(q, context, 'cases'):
        return
    parts = (q.data or '').split(':')
    try:
        cid = int(parts[1])
    except (ValueError, IndexError):
        await q.message.reply_text('❌ شناسه پرونده معتبر نیست.')
        return
    case = get_case(q.from_user.id, cid)
    if not case or case.get('status') == 'archived':
        await q.message.reply_text('❌ پرونده پیدا نشد یا بایگانی شده است.')
        return

    # First click opens the built-in playbook picker; no AI call or quota use.
    if len(parts) == 2:
        buttons = [
            [InlineKeyboardButton(item['title'], callback_data=f"aicontract:{cid}:{item['id']}")]
            for item in list_contract_playbooks()
        ]
        buttons.append([InlineKeyboardButton('↩️ بازگشت به پرونده', callback_data=f'caseview:{cid}')])
        await q.message.reply_text(
            '📚 الگوی بررسی قرارداد را انتخاب کنید. معیارهای الگو فقط برای هدایت بررسی اولیه استفاده می‌شوند:',
            reply_markup=InlineKeyboardMarkup(buttons))
        return

    playbook_id = parts[2]
    checklist = build_playbook_checklist(playbook_id)
    if checklist is None:
        await q.message.reply_text('❌ الگوی انتخاب‌شده معتبر نیست؛ لطفاً دوباره انتخاب کنید.')
        return
    extracted_text = get_case_text(q.from_user.id, cid)
    if not extracted_text.strip():
        await q.message.reply_text('❌ متن استخراج‌شده‌ای برای بررسی وجود ندارد. ابتدا استخراج متن یا OCR محلی را تکمیل کنید.')
        return
    if not (AI_ENABLED and AI_EXTERNAL_DATA_CONSENT):
        await q.message.reply_text('⚠️ بررسی تخصصی قرارداد به پردازش خارجی نیاز دارد؛ تنظیمات هوش مصنوعی یا رضایت ارسال داده فعال نیست. هیچ متنی ارسال نشد.')
        return
    from .core.ai_entitlement import AIEntitlementService
    entitlement = AIEntitlementService()
    ok, reservation = entitlement.reserve_question(q.from_user.id)
    if not ok or not reservation:
        await q.message.reply_text('⚠️ سهمیه هوش مصنوعی در دسترس نیست؛ هیچ درخواستی ارسال نشد.')
        return
    status_msg = await q.message.reply_text(f"⏳ در حال بررسی قرارداد با الگوی «{checklist['title']}»…")
    try:
        report = await asyncio.to_thread(review_contract_risks, extracted_text, checklist['title'], checklist)
        entitlement.commit(q.from_user.id, reservation)
        await status_msg.edit_text('✅ بررسی اولیه قرارداد آماده شد. یافته‌ها نیازمند بازبینی هستند.')
        await reply_long(q.message, report)
        try:
            pdf_buffer = await asyncio.to_thread(build_contract_report_pdf, report, checklist['title'])
            pdf_buffer.name = f"MACHINA_contract_review_{playbook_id}.pdf"
            await q.message.reply_document(
                document=pdf_buffer,
                filename=pdf_buffer.name,
                caption='📄 نسخه PDF گزارش بررسی اولیه قرارداد؛ نیازمند بازبینی وکیل.'
            )
        except Exception:
            logger.exception('Contract report PDF export failed for user=%s case=%s', q.from_user.id, cid)
            await q.message.reply_text('⚠️ گزارش متنی آماده است، اما ساخت یا ارسال PDF ناموفق بود.')
    except Exception:
        entitlement.refund(q.from_user.id, reservation)
        logger.exception('AI contract review failed for user=%s case=%s playbook=%s', q.from_user.id, cid, playbook_id)
        await status_msg.edit_text('❌ بررسی قرارداد انجام نشد؛ سهمیه بازگردانده شد و اطلاعات پرونده تغییری نکرد.')
    await q.message.reply_text('📁 ادامه پرونده:', reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton('📁 باز کردن همین پرونده', callback_data=f'caseview:{cid}')],
        [InlineKeyboardButton('↩️ بازگشت به دستیار هوشمند', callback_data='aimenu')],
    ]))


async def ai_cases_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_lawyer(q, context, 'cases'): return
    _clear_pending_inputs(context)
    rows=list_cases(uid, 20)
    if not rows:
        await q.message.reply_text(
            '📂 هنوز پرونده‌ای ثبت نکرده‌اید. ابتدا یک پرونده بسازید تا بتوانید درباره آن از دستیار هوشمند سؤال بپرسید.',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('➕ پرونده جدید', callback_data='newcase')],
                [InlineKeyboardButton('↩️ بازگشت به دستیار هوشمند', callback_data='aimenu')],
            ]))
        return
    active_case_id=get_active_case_id(uid)
    kb=[]
    for c in rows:
        prefix='🟢 ' if active_case_id == c['id'] else '📁 '
        label=(c.get('file_name') or 'بدون نام')[:48]
        kb.append([InlineKeyboardButton(f'{prefix}{label}', callback_data=f'cai:{c["id"]}')])
    kb.append([InlineKeyboardButton('↩️ بازگشت به دستیار هوشمند', callback_data='aimenu')])
    kb.append([InlineKeyboardButton('🏠 منوی اصلی', callback_data='home')])
    await q.message.reply_text('📂 پرونده موردنظر را برای پرسش از دستیار هوشمند انتخاب کنید:', reply_markup=InlineKeyboardMarkup(kb))


async def subscribe_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_registered(q): return
    _clear_pending_inputs(context)
    text='💳 اشتراک ماهانه\n\n' + SUBSCRIPTION_PRICE_TEXT
    if ADMIN_CARD_NUMBER: text += f'\n\nشماره کارت: {ADMIN_CARD_NUMBER}'
    if ADMIN_CARD_HOLDER: text += f'\nبه نام: {ADMIN_CARD_HOLDER}'
    text += '\n\nپس از پرداخت، رسید را برای پشتیبانی/ادمین ارسال کنید.'
    await q.message.reply_text(text)


async def support_menu_cb(update, context):
    q=update.callback_query
    await q.answer()
    if not await _require_registered(q):
        return
    _clear_pending_inputs(context)
    await q.message.reply_text('🆘 پشتیبانی و گزارش مشکل', reply_markup=support_menu())


async def tools_menu_cb(update, context):
    # Compatibility route for old keyboards. The old client-oriented tools
    # submenu was retired; lawyer-useful tools now live under calculations.
    q=update.callback_query; await q.answer()
    if not await _require_registered(q): return
    _clear_pending_inputs(context)
    await q.message.reply_text('🧮 محاسبات حقوقی', reply_markup=calculator_menu())


async def topics_menu_cb(update, context):
    # Compatibility route for the former client-oriented topic menu.
    q=update.callback_query; await q.answer()
    if not await _require_registered(q): return
    _clear_pending_inputs(context)
    await q.message.reply_text('🧮 محاسبات حقوقی', reply_markup=calculator_menu())


async def account_menu_cb(update, context):
    # Compatibility route for old/stale keyboards. The account submenu was
    # intentionally removed; old callbacks now return to the current menu.
    await home_cb(update, context)


async def legal_search_menu_cb(update, context):
    # Compatibility route for old keyboards: do not reintroduce a second
    # search submenu. The unified search flow already includes glossary
    # lookup, so old `legal_search_menu` callbacks go straight to `law_cb`.
    await law_cb(update, context)


async def support_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_registered(q): return
    _clear_pending_inputs(context, keep='awaiting_feedback')
    context.user_data['awaiting_feedback']='support'
    await q.message.reply_text(
        '🆘 پشتیبانی\n\n'
        'پیام، سؤال یا مشکل خود را همین‌جا ارسال کنید تا برای ادمین/پشتیبانی ارسال شود.'
    )


async def help_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_registered(q): return
    _clear_pending_inputs(context)
    await q.message.reply_text(
        '📖 راهنمای ساده LegalBot 140\n\n'
        'اگر اولین بار است از بات استفاده می‌کنید، نگران نباشید؛ بیشتر کارها با چند دکمه انجام می‌شود و هر جا لازم باشد خود بات از شما می‌خواهد متن یا فایل بفرستید.\n\n'
        '🏠 از کجا شروع کنم؟\n'
        'اگر پرونده‌ای دارید، «➕ پرونده جدید» را بزنید، یک نام برای پرونده انتخاب کنید و فایل‌ها یا عکس‌های مربوط را بفرستید. بعداً هر وقت لازم باشد همان پرونده را باز کنید و امکاناتش را استفاده کنید.\n\n'
        '📂 پرونده‌ها و کارهای من\n'
        'اینجا پرونده‌های شما را می‌بینید. با انتخاب هر پرونده، امکانات مخصوص همان پرونده باز می‌شود. پرونده‌ای که انتخاب کرده‌اید به‌عنوان «پرونده فعال» شناخته می‌شود تا لازم نباشد هر بار دوباره آن را معرفی کنید.\n\n'
        '📎 افزودن عکس و متن به پرونده\n'
        'اگر بعداً مدرک، عکس، PDF، Word یا متن جدیدی پیدا کردید، لازم نیست پرونده را از اول بسازید؛ همین گزینه را بزنید و موارد جدید را بفرستید.\n\n'
        '📝 خلاصه پرونده\n'
        'از متن ذخیره‌شده پرونده یک جمع‌بندی اولیه می‌سازد. اگر بعداً مدرک جدید اضافه کنید، آن اطلاعات هم در پردازش‌های بعدی قابل استفاده است.\n\n'
        '⚖️ مواد و مقررات مرتبط\n'
        'بات بر اساس متن پرونده، مواد و منابع مرتبط موجود در منابع داخلی خود را پیشنهاد می‌کند. این پیشنهاد جای بررسی متن رسمی قانون را نمی‌گیرد.\n\n'
        '🤖 پرسش از هوش مصنوعی\n'
        'اگر AI فعال باشد، می‌توانید درباره همان پرونده سؤال بپرسید. قبل از ارسال اطلاعات به سرویس خارجی، تنظیمات مربوط به AI و اجازه پردازش خارجی باید فعال باشد. پاسخ AI راهنمای اولیه است و نباید بدون بررسی منبع رسمی مبنای تصمیم حقوقی قرار گیرد.\n\n'
        '📄 افزودن و مقایسه نسخه جدید پرونده با نسخه اصلی\n'
        'اگر نسخه جدیدی از قرارداد یا سند پرونده دارید، آن را به همان پرونده اضافه کنید تا علاوه بر تفاوت‌های متنی، برخی تفاوت‌های ساختاری مثل مبلغ، تاریخ/مهلت، طرفین، خواسته/ادعا، تعهدات، مراجع قانونی و بندهای حساس هم استخراج و نمایش داده شود. این استخراج محلی است و به‌تنهایی اثر حقوقی تغییر را تعیین نمی‌کند.\n\n'
        '🗒️ یادداشت برای پرونده\n'
        'برای هر پرونده می‌توانید یادداشت جداگانه داشته باشید و بعداً آن را ویرایش یا پاک کنید.\n\n'
        '📅 تاریخ‌های مهم پرونده‌ها\n'
        'تاریخ‌هایی که از متن پرونده با زمینه حقوقی قابل استخراج باشند در یک فهرست جمع می‌شوند. این فهرست یادآور اطلاعات متن است؛ به معنی تشخیص قطعی مهلت قانونی نیست.\n\n'
        '🔎 جستجو در پرونده‌ها\n'
        'اگر یادتان نیست یک عبارت یا موضوع در کدام پرونده بوده، عبارت موردنظر را وارد کنید تا در متن پرونده‌های ذخیره‌شده جستجو شود.\n\n'
        '🔎 جستجوی قوانین و منابع حقوقی\n'
        'نام قانون، شماره ماده، واژه حقوقی، رأی وحدت رویه یا عبارت موردنظر را وارد کنید.\n\n'
        '🧮 محاسبات حقوقی\n'
        'چند ابزار محاسباتی اولیه در دسترس است. عدد نمایش‌داده‌شده را نتیجه قطعی پرونده در نظر نگیرید؛ بعضی محاسبات به قانون، تاریخ و داده رسمی به‌روز وابسته‌اند. اگر داده رسمی کافی نباشد، بات عمداً از نمایش عدد حدسی خودداری می‌کند.\n\n'
        '📝 لایحه‌نویسی\n'
        'اگر پرونده فعال داشته باشید، بات می‌تواند برای همان پرونده پیش‌نویس لایحه بسازد و اطلاعاتی را که از پرونده دارد دوباره از شما نپرسد. همچنین می‌توانید یک لایحه جدید بنویسید یا متن موجود را برای بررسی و تقویت اولیه بدهید.\n\n'
        '👥 مدیریت موکل‌ها\n'
        'در نسخه وکلا می‌توانید موکل‌ها را ثبت، ویرایش و به پرونده‌های مربوط متصل کنید.\n\n'
        '💳 اشتراک و 📊 وضعیت حساب\n'
        'از این قسمت‌ها می‌توانید وضعیت حساب، سهمیه‌ها و امکانات اشتراک را ببینید.\n\n'
        '🆘 پشتیبانی و گزارش مشکل\n'
        'اگر چیزی درست کار نکرد، از گزارش مشکل استفاده کنید و خیلی ساده بنویسید چه کاری انجام دادید و چه اتفاقی افتاد.\n\n'
        '💡 یک نکته مهم\n'
        'لازم نیست اطلاعاتی را که قبلاً داخل پرونده ثبت کرده‌اید دوباره تایپ کنید. اول پرونده را انتخاب کنید؛ معمولاً بات از همان اطلاعات ذخیره‌شده استفاده می‌کند.\n\n'
        '⚠️ این بات ابزار کمک و بررسی اولیه است. خلاصه، پیشنهاد قانونی، محاسبه و متن لایحه باید قبل از استفاده واقعی با اسناد پرونده و منابع رسمی کنترل شوند.' )

def source_detail_keyboard(record):
    citation=(record or {}).get('citation') or {}
    cid=citation.get('id')
    if not cid:
        return None
    rel=related_sources(record, 6)
    rows=[]
    for r in rel[:6]:
        rc=(r.get('citation') or {}).get('id')
        if not rc:
            continue
        kind=r.get('kind','law')
        icon={'law':'⚖️','ruling':'🏛️','consultation':'💬','sample':'📄','circular':'📢'}.get(kind,'📚')
        label=r.get('title') or r.get('law') or 'منبع مرتبط'
        locator=r.get('article') or r.get('ruling_number') or r.get('consultation_number')
        if locator:
            label += f' — {locator}'
        rows.append([InlineKeyboardButton(f'{icon} {label}'[:60], callback_data=f'source:{rc}')])
    rows.append([InlineKeyboardButton('↩️ بازگشت به جستجو', callback_data='law')])
    return InlineKeyboardMarkup(rows)

async def source_detail_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_registered(q): return
    cid=q.data.split(':',1)[1]
    record=get_source_record(cid)
    if not record:
        await q.message.reply_text('❌ این منبع دیگر در بانک حقوقی فعال پیدا نشد.')
        return
    citation=record.get('citation') or {}
    kind=record.get('kind','law')
    icon={'law':'⚖️','ruling':'🏛️','consultation':'💬','sample':'📄','circular':'📢'}.get(kind,'📚')
    title=record.get('title') or record.get('law') or 'منبع حقوقی'
    locator=record.get('article') or record.get('ruling_number') or record.get('consultation_number')
    lines=[f'{icon} {title}', '']
    if locator: lines.append(f'📌 شناسه/ماده: {locator}')
    if record.get('date'): lines.append(f'📅 تاریخ: {record["date"]}')
    lines += [f'🧾 شناسه استناد: {citation.get("id","—")}', f'🛡 وضعیت منبع: {citation.get("verification_label") or "نامشخص"}']
    authorities='، '.join(citation.get('primary_sources') or [])
    if authorities: lines.append('🏛 مرجع منبع: '+authorities)
    if citation.get('last_verified'): lines.append('📅 آخرین تطبیق ثبت‌شده: '+str(citation['last_verified']))
    urls=citation.get('source_urls') or []
    if urls: lines.append('🔗 منبع ثبت‌شده: '+str(urls[0]))
    if citation.get('source_file'): lines.append('📄 فایل/نسخه: '+str(citation['source_file']))
    lines += ['', 'این کارت برای ردیابی منبع و پژوهش است؛ «مرتبط» بودن موارد زیر به معنی نتیجه قطعی حقوقی نیست.']
    text=record.get('clean_text') or record.get('text') or ''
    if kind=='consultation' and record.get('question'):
        lines += ['', '❓ سؤال:', str(record.get('question'))[:900]]
    lines += ['', '📖 متن:', str(text)[:2600]]
    rel=related_sources(record,6)
    if rel:
        lines += ['', '🔗 منابع مرتبط پیشنهادی بر اساس هم‌پوشانی واژگان/عنوان:']
        for i,r in enumerate(rel,1):
            rtitle=r.get('title') or r.get('law') or 'منبع'
            rloc=r.get('article') or r.get('ruling_number') or r.get('consultation_number')
            lines.append(f'{i}. {rtitle}' + (f' — {rloc}' if rloc else ''))
    await reply_long(q.message, normalize_output('\n'.join(lines)))
    kb=source_detail_keyboard(record)
    if kb: await q.message.reply_text('منبع مرتبط را باز کنید:', reply_markup=kb)

async def law_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_registered(q): return
    _clear_pending_inputs(context, keep='awaiting_unified_legal_search')
    context.user_data['awaiting_unified_legal_search'] = True
    await q.message.reply_text(
        '🔎 جستجوی حقوقی یکپارچه\n\n'
        'فقط عبارت موردنظر را همین‌جا بنویسید؛ جستجو هم‌زمان در منابع حقوقی و واژه‌نامه حقوقی انجام می‌شود و لازم نیست از منوهای بعدی عبور کنید.\n\n'
        'مثال‌ها:\n'
        '• ماده ۱۰ قانون مدنی\n'
        '• رأی وحدت رویه ۸۱۰\n'
        '• کمیسیون ماده ۱۰۰\n'
        '• نظریه مشورتی قرارداد\n\n'
        'هر زمان خواستید می‌توانید جستجوی بعدی را هم مستقیم بفرستید.'
    )


async def glossary_cb(update, context):
    # Compatibility route for old/stale glossary buttons. Glossary lookup is
    # now part of the unified legal-search flow rather than a separate menu.
    await law_cb(update, context)


async def _glossary_text(update, context, value):
    entries=lookup(value)
    return format_entries(entries) if entries else '❌ مدخلی پیدا نشد.'


async def feedback_cb(update, context):
    q=update.callback_query; await q.answer();
    if not await _require_registered(q): return
    _clear_pending_inputs(context, keep='awaiting_feedback'); context.user_data['awaiting_feedback']=True
    await q.message.reply_text('🐛 متن مشکل یا پیشنهاد خود را ارسال کنید.')


async def feedback_kind_cb(update, context):
    q=update.callback_query; await q.answer();
    if not await _require_registered(q): return
    _clear_pending_inputs(context, keep='awaiting_feedback'); context.user_data['awaiting_feedback']=True
    await q.message.reply_text('متن گزارش را ارسال کنید.')


def _important_date_text(rows):
    if not rows:
        return ('📅 تاریخ‌های مهم پرونده‌ها\n\n'
                'فعلاً تاریخ مهمی که از متن پرونده‌ها قابل استخراج باشد پیدا نشد.\n\n'
                'با پردازش هر پرونده، تاریخ‌های صریح و دارای زمینه حقوقی در این فهرست ثبت می‌شوند.')
    lines=['📅 تاریخ‌های مهم پرونده‌ها','', 'تاریخ‌ها از متن پرونده‌های شما استخراج شده‌اند و قبل از نمایش از نظر قالب تاریخ بررسی می‌شوند.']
    current_case=None
    for r in rows:
        case_label=f'پرونده #{r["case_no"]} — {r.get("file_name") or "بدون نام"}'
        if case_label != current_case:
            lines += ['', f'📁 {case_label}']
            current_case=case_label
        date_fa=str(r['date_jalali']).translate(str.maketrans('0123456789','۰۱۲۳۴۵۶۷۸۹'))
        page=f' — صفحه {r["source_page"]}' if r.get('source_page') else ''
        lines.append(f'📅 {date_fa} — {r["description"]}{page}')
        if r.get('source_text'):
            lines.append(f'   ↳ {r["source_text"][:220]}')
    lines += ['', 'ℹ️ تاریخ‌هایی که بیش از یک ماه از آنها گذشته باشد از این فهرست حذف می‌شوند؛ متن اصلی پرونده دست‌نخورده باقی می‌ماند.',
              '⚠️ ثبت این تاریخ‌ها به معنی تشخیص قطعی مهلت یا موعد قانونی نیست و فقط بازتاب اطلاعات استخراج‌شده از متن پرونده است.']
    return '\n'.join(lines)


async def important_dates_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_registered(q): return
    _clear_pending_inputs(context)
    rows=list_case_important_dates(uid, 80)
    await reply_long(q.message, _important_date_text(rows))
    kb=[]
    for r in rows[:12]:
        kb.append([InlineKeyboardButton(f'🔔 یادآوری {r["date_jalali"]} — {r["description"]}', callback_data=f'remind:{r["id"]}')])
    kb += [[InlineKeyboardButton('🔔 یادآوری‌های فعال',callback_data='reminders')], [InlineKeyboardButton('🏠 منوی اصلی',callback_data='home')]]
    await q.message.reply_text(
        'اگر یک تاریخ برایتان واقعاً مهم است، می‌توانید یادآوری آن را فعال کنید.\n\n'
        '⚠️ یادآوری فقط یک اعلان کمکی است و به معنی تشخیص قطعی مهلت قانونی نیست.',
        reply_markup=InlineKeyboardMarkup(kb))


async def reminder_toggle_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_registered(q): return
    try: did=int(q.data.split(':',1)[1])
    except Exception: return
    ok=set_case_date_reminder(uid,did,True)
    await q.message.reply_text(
        '🔔 یادآوری فعال شد. یک روز قبل از تاریخ ثبت‌شده به شما پیام می‌دهیم.'
        if ok else '❌ این تاریخ پیدا نشد یا متعلق به حساب شما نیست.')


async def reminders_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_registered(q): return
    _clear_pending_inputs(context)
    init_case_reminders_table()
    with _db.conn() as c:
        active=c.execute("""SELECT d.*,c.file_name FROM case_date_reminders r
            JOIN case_important_dates d ON d.id=r.case_date_id
            JOIN cases c ON c.id=d.case_id
            WHERE r.user_id=? AND r.enabled=1 AND d.date_gregorian>=date('now') AND c.status!='archived'
            ORDER BY d.date_gregorian ASC""",(uid,)).fetchall()
        active=[dict(x) for x in active]
    if not active:
        text='🔔 یادآوری‌های پرونده\n\nفعلاً یادآوری فعالی ندارید. از «📅 تاریخ‌های مهم پرونده‌ها» یک تاریخ را انتخاب کنید.'
    else:
        lines=['🔔 یادآوری‌های فعال پرونده','']
        for r in active[:20]:
            lines.append(f'• {r["date_jalali"]} — {r["description"]} — پرونده: {r["file_name"] or "بدون نام"}')
        lines += ['', 'یادآوری یک روز قبل ارسال می‌شود.']
        text='\n'.join(lines)
    await q.message.reply_text(text,reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton('📅 تاریخ‌های مهم پرونده‌ها',callback_data='importantdates')],
        [InlineKeyboardButton('🏠 منوی اصلی',callback_data='home')]]))


async def tasks_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_registered(q): return
    _clear_pending_inputs(context)
    counts=user_work_counts(uid)
    tasks=list_tasks(uid, include_done=False)[:8]
    refs=list_referrals_for_user(uid,8)
    lawyer_refs=list_referral_matches_for_lawyer(uid,8)
    lines=['📋 کارهای من','']
    total=counts['tasks']+counts['referrals']+counts['lawyer_referrals']+counts['payments']+counts['cases_processing']
    lines.append(f'🔴 موارد نیازمند اقدام: {total}')
    if counts['cases_processing']: lines.append(f'📁 {counts["cases_processing"]} پرونده در حال پردازش')
    if counts['payments']: lines.append(f'💳 {counts["payments"]} پرداخت در انتظار بررسی')
    if counts['referrals']: lines.append(f'🤝 {counts["referrals"]} درخواست معرفی فعال شما')
    if counts['lawyer_referrals']: lines.append(f'📨 {counts["lawyer_referrals"]} معرفی جدید برای خدمات شما')
    lines.append('')
    if tasks:
        lines.append('📝 کارهای ثبت‌شده')
        for t in tasks: lines.append(f'⬜ #{t["id"]} {t["title"]}' + (f' — موعد: {_fa_num_text(str(t["due_at"])[:10])}' if t.get('due_at') else ' — بدون موعد'))
    if refs:
        lines.append('')
        lines.append('🤝 معرفی‌های من')
        for r in refs[:5]: lines.append(f'• #{r["id"]} {r["topic"]} — {_referral_status_fa(r["status"])}')
    if lawyer_refs:
        lines.append('')
        lines.append('📨 معرفی‌های دریافتی')
        for r in lawyer_refs[:5]: lines.append(f'• #{r["id"]} {r["topic"]} — {_match_status_fa(r["status"])}')
    if not tasks and not refs and not lawyer_refs and total==0:
        lines.append('✨ فعلاً موردی برای پیگیری ندارید.')
    task_rows=[]
    for t in tasks[:5]:
        task_rows.append([InlineKeyboardButton(f'✅ انجام شد #{t["id"]}',callback_data=f'taskact:done:{t["id"]}'), InlineKeyboardButton('🗑 حذف',callback_data=f'taskact:delete:{t["id"]}')])
    kb=InlineKeyboardMarkup(task_rows+[
        [InlineKeyboardButton('➕ کار جدید',callback_data='tasknew'), InlineKeyboardButton('🤝 درخواست معرفی',callback_data='referral_new')],
        [InlineKeyboardButton('📨 معرفی‌های من',callback_data='referrals')],
        [InlineKeyboardButton('🏠 منوی اصلی',callback_data='home')]])
    await q.message.reply_text('\n'.join(lines),reply_markup=kb)


async def task_new_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_registered(q): return
    _clear_pending_inputs(context,keep='awaiting_task_title'); context.user_data['awaiting_task_title']=True
    await q.message.reply_text('📝 عنوان کاری که می‌خواهید پیگیری کنید را وارد کنید:')

async def task_action_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_registered(q): return
    parts=q.data.split(':')
    try: tid=int(parts[2])
    except: return
    action=parts[1]
    if action=='done': ok=set_task_done(uid,tid,True)
    elif action=='undo': ok=set_task_done(uid,tid,False)
    elif action=='delete': ok=delete_task(uid,tid)
    else: ok=False
    await q.message.reply_text('✅ انجام شد.' if ok else '❌ کار پیدا نشد.')
    if ok: await tasks_cb(update,context)

def referral_urgency_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton('🟢 عادی',callback_data='refurg:normal'), InlineKeyboardButton('🟠 نسبتاً فوری',callback_data='refurg:soon')],[InlineKeyboardButton('🔴 فوری',callback_data='refurg:urgent')]])

def _referral_status_fa(s):
    return {'new':'جدید','sent':'ارسال‌شده برای وکیل','more_info':'منتظر اطلاعات بیشتر','contact':'در حال ارتباط','closed':'بسته‌شده','declined':'ردشده','cancelled':'لغوشده'}.get(s,s)

def _match_status_fa(s):
    return {'sent':'منتظر پاسخ شما','accepted':'پذیرفته‌شده','declined':'ردشده','more_info':'اطلاعات بیشتر خواسته شده','contact':'ارتباط فعال','closed':'بسته‌شده'}.get(s,s)

def _referral_admin_text(r):
    return (f'🤝 درخواست معرفی #{r["id"]}\n\nموضوع: {r["topic"]}\nشهر: {r["city"]}\nفوریت: {r["urgency"]}\n\nشرح متقاضی:\n{r["details"][:3500]}\n\n⚠️ اطلاعات تماس متقاضی تا مرحله پذیرش اولیه برای وکیل ارسال نمی‌شود.')

async def _send_referral_to_admins(bot, rid):
    r=get_referral_request(rid)
    if not r: return False
    services=list_matching_services(r['topic'],r['city'],8)
    rows=[]
    for s in services:
        rows.append([InlineKeyboardButton(f'📨 ارسال به {s["service_title"][:30]} | {s["city"][:15]}',callback_data=f'refadmin:send:{rid}:{s["id"]}')])
    rows.append([InlineKeyboardButton('❌ فعلاً بدون معرفی',callback_data=f'refadmin:close:{rid}')])
    kb=InlineKeyboardMarkup(rows)
    ok=False
    for aid in ADMIN_TELEGRAM_IDS:
        try:
            await bot.send_message(chat_id=aid,text=_referral_admin_text(r),reply_markup=kb); ok=True
        except Exception as exc: logger.exception('Failed to send referral #%s to admin %s: %s',rid,aid,exc)
    return ok

async def referral_new_cb(update, context):
    q=update.callback_query; await q.answer();
    if not await _require_registered(q): return
    _clear_pending_inputs(context,keep='ref_topic'); context.user_data['ref_topic']=True
    await q.message.reply_text('🤝 درخواست معرفی وکیل\n\nموضوع پرونده یا مشکل خود را کوتاه و روشن وارد کنید:')

async def referral_urgency_cb(update, context):
    q=update.callback_query; await q.answer();
    if not await _require_registered(q): return
    if not context.user_data.get('ref_urgency'): return
    val=q.data.split(':',1)[1]
    context.user_data.pop('ref_urgency',None); context.user_data['ref_urgency_value']=val; context.user_data['ref_details']=True
    await q.message.reply_text('📝 شرح مختصر موضوع، اتفاقات مهم، خواسته شما و هر اطلاعاتی که برای انتخاب وکیل لازم است را بنویسید.\n\nاطلاعات تماس و مدارک حساس را فعلاً داخل این متن ننویسید.')

async def referrals_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_registered(q): return
    _clear_pending_inputs(context)
    client=list_referrals_for_user(uid,10); lawyer=list_referral_matches_for_lawyer(uid,10)
    if not client and not lawyer:
        await q.message.reply_text('🤝 هنوز معرفی‌ای برای شما ثبت نشده است.',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('➕ درخواست معرفی وکیل',callback_data='referral_new')],[InlineKeyboardButton('🏠 منوی اصلی',callback_data='home')]])); return
    for r in client:
        kb=InlineKeyboardMarkup([[InlineKeyboardButton('ℹ️ مشاهده وضعیت',callback_data=f'refview:{r["id"]}')]])
        await q.message.reply_text(f'🤝 درخواست #{r["id"]}\nموضوع: {r["topic"]}\nشهر: {r["city"]}\nوضعیت: {_referral_status_fa(r["status"])}',reply_markup=kb)
    for m in lawyer:
        kb=InlineKeyboardMarkup([[InlineKeyboardButton('👁 بررسی معرفی',callback_data=f'refmatch:{m["id"]}')]])
        await q.message.reply_text(f'📨 معرفی #{m["referral_id"]}\nموضوع: {m["topic"]}\nشهر: {m["city"]}\nوضعیت: {_match_status_fa(m["status"])}',reply_markup=kb)

async def referral_view_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_registered(q): return
    try: rid=int(q.data.split(':')[1])
    except: return
    r=get_referral_request(rid)
    if not r or r['client_user_id']!=uid: await q.message.reply_text('❌ درخواست پیدا نشد.'); return
    text=f'🤝 درخواست #{rid}\n\nموضوع: {r["topic"]}\nشهر: {r["city"]}\nفوریت: {r["urgency"]}\nوضعیت: {_referral_status_fa(r["status"])}'
    await q.message.reply_text(text,reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🏠 منوی اصلی',callback_data='home')]]))

async def referral_match_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_registered(q): return
    try: mid=int(q.data.split(':')[1])
    except: return
    m=get_referral_match(mid)
    if not m or m['lawyer_user_id']!=uid: await q.message.reply_text('❌ معرفی پیدا نشد.'); return
    if m['status'] not in ('sent','more_info'):
        await q.message.reply_text(f'📨 وضعیت: {_match_status_fa(m["status"])}'); return
    text=(f'📨 معرفی #{m["referral_id"]}\n\nموضوع: {m["topic"]}\nشهر: {m["city"]}\nفوریت: {m["urgency"]}\n\nشرح متقاضی:\n{m["details"][:3000]}\n\n⚠️ در این مرحله اطلاعات تماس متقاضی نمایش داده نمی‌شود.')
    kb=InlineKeyboardMarkup([[InlineKeyboardButton('✅ پذیرش اولیه',callback_data=f'refmatch:accept:{mid}'),InlineKeyboardButton('❌ رد',callback_data=f'refmatch:decline:{mid}')],[InlineKeyboardButton('❓ اطلاعات بیشتر',callback_data=f'refmatch:more:{mid}')]])
    await q.message.reply_text(text,reply_markup=kb)

async def referral_match_action_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_registered(q): return
    parts=q.data.split(':'); action=parts[1]
    try: mid=int(parts[2])
    except: return
    m=get_referral_match(mid)
    if not m or m['lawyer_user_id']!=uid: await q.message.reply_text('❌ معرفی پیدا نشد.'); return
    if action=='more':
        update_referral_match(mid,uid,'more_info','وکیل اطلاعات تکمیلی خواست')
        await q.message.edit_reply_markup(reply_markup=None)
        try:
            await q.message.get_bot().send_message(chat_id=m['client_user_id'],text=f'❓ وکیل برای معرفی #{m["referral_id"]} اطلاعات بیشتری لازم دارد. لطفاً موارد تکمیلی را از طریق دکمه زیر ارسال کنید.',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('📝 ارسال اطلاعات تکمیلی',callback_data=f'refinfo:{m["referral_id"]}')]]))
        except Exception: pass
        return
    status='accepted' if action=='accept' else 'declined'
    update_referral_match(mid,uid,status,'')
    await q.message.edit_reply_markup(reply_markup=None)
    if status=='accepted':
        await q.message.reply_text('✅ پذیرش اولیه ثبت شد. اطلاعات تماس طرفین برای ایجاد ارتباط ارسال می‌شود.')
        try:
            await q.message.get_bot().send_message(chat_id=m['client_user_id'],text=f'✅ یک وکیل برای درخواست #{m["referral_id"]} پذیرش اولیه انجام داد.\n\nوکیل: {m["full_name"]}\nخدمت: {m["service_title"]}\n📞 تماس وکیل: {m["phone"]}\n\n📞 شماره ثبت‌شده شما نیز در اختیار وکیل قرار می‌گیرد تا ارتباط پرونده را پیگیری کند.')
            await q.message.get_bot().send_message(chat_id=m['client_user_id'],text='اگر تمایل به ادامه ندارید، می‌توانید از پشتیبانی درخواست لغو ارتباط کنید.')
            await q.message.get_bot().send_message(chat_id=uid,text=f'📞 اطلاعات تماس متقاضی درخواست #{m["referral_id"]}:\nبرای حفظ حریم خصوصی، اطلاعات تماس فقط پس از پذیرش اولیه نمایش داده می‌شود.\nشناسه کاربر تلگرام: {m["client_user_id"]}')
        except Exception as exc: logger.exception('Referral contact notification failed: %s',exc)
    else:
        try: await q.message.get_bot().send_message(chat_id=m['client_user_id'],text=f'❌ وکیل انتخاب‌شده درخواست #{m["referral_id"]} را نپذیرفت. درخواست برای بررسی گزینه دیگری در اختیار پشتیبانی است.')
        except Exception: pass

async def referral_info_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_registered(q): return
    try: rid=int(q.data.split(':')[1])
    except: return
    r=get_referral_request(rid)
    if not r or r['client_user_id']!=uid or r['status'] not in ('more_info','sent'):
        await q.message.reply_text('❌ این درخواست در حال حاضر قابل تکمیل نیست.'); return
    _clear_pending_inputs(context,keep='awaiting_referral_info'); context.user_data['awaiting_referral_info']=rid
    await q.message.reply_text('📝 اطلاعات تکمیلی را ارسال کنید:')

async def referral_admin_cb(update, context):
    q=update.callback_query
    if q.from_user.id not in ADMIN_TELEGRAM_IDS: await q.answer('دسترسی ندارید.',show_alert=True); return
    await q.answer(); parts=q.data.split(':'); action=parts[1]
    try: rid=int(parts[2])
    except: return
    r=get_referral_request(rid)
    if not r: await q.message.reply_text('❌ درخواست پیدا نشد.'); return
    if action=='close':
        add_referral_event(rid,q.from_user.id,'closed','بسته‌شدن توسط ادمین')
        await q.message.edit_reply_markup(reply_markup=None)
        try: await q.message.get_bot().send_message(chat_id=r['client_user_id'],text=f'ℹ️ درخواست معرفی #{rid} فعلاً بسته شد. در صورت نیاز می‌توانید درخواست جدید ثبت کنید.')
        except Exception: pass
        return
    try: lid=int(parts[3])
    except: return
    if not assign_referral(rid,lid,q.from_user.id):
        await q.message.reply_text('❌ ارسال این معرفی ممکن نیست؛ احتمالاً قبلاً ارسال شده یا خدمت دیگر فعال نیست.'); return
    s=get_service_listing(lid)
    await q.message.reply_text(f'✅ معرفی #{rid} به خدمت #{lid} ارسال شد.')
    await q.message.edit_reply_markup(reply_markup=None)
    ms=list_referral_matches_for_lawyer(s['user_id'],10)
    mid=next((x['id'] for x in ms if x['referral_id']==rid),None)
    if not mid:
        return
    try:
        await q.message.get_bot().send_message(chat_id=s['user_id'],text=(f'📨 معرفی جدید #{rid}\n\nموضوع: {r["topic"]}\nشهر: {r["city"]}\nفوریت: {r["urgency"]}\n\nشرح متقاضی:\n{r["details"][:3000]}\n\n⚠️ اطلاعات تماس متقاضی فعلاً نمایش داده نمی‌شود. پس از پذیرش اولیه امکان ایجاد ارتباط فراهم می‌شود.'),reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('👁 بررسی معرفی',callback_data=f'refmatch:{mid}')]]))
    except Exception as exc:
        logger.exception('Failed to notify lawyer for referral #%s: %s',rid,exc)

async def globalsearch_cb(update, context):
    q=update.callback_query; await q.answer();
    if not await _require_lawyer(q, context, 'globalsearch'): return
    _clear_pending_inputs(context, keep='awaiting_global_search'); context.user_data['awaiting_global_search']=True
    await q.message.reply_text('🔎 عبارت موردنظر برای جستجو در پرونده‌های خود را ارسال کنید.')


def _credit_wait_text(credit):
    sec=max(0,int(credit.get("seconds_until_refresh") or 0))
    days,rem=divmod(sec,86400)
    hours,rem=divmod(rem,3600)
    minutes,_=divmod(rem,60)
    if days:
        return f"{days} روز و {hours} ساعت"
    if hours:
        return f"{hours} ساعت و {minutes} دقیقه"
    return f"{max(1,minutes)} دقیقه"


def _free_credit_exhausted_reply_markup():
    return InlineKeyboardMarkup([[InlineKeyboardButton("💳 خرید اشتراک", callback_data="subscribe")]])


def _free_credit_exhausted_message(credit, insufficient=False):
    allowance=int(credit.get("allowance") or 0)
    remaining=int(credit.get("remaining") or 0)
    if insufficient and remaining > 0:
        text=f"⚠️ اعتبار رایگان فعلی برای انجام این عملیات کافی نیست.\n\n🪙 اعتبار باقی‌مانده: {remaining} از {allowance}"
    else:
        text="⚠️ اعتبار رایگان هفتگی شما تمام شده است."
    text += f"\n\n🔄 شارژ رایگان بعدی: {_credit_wait_text(credit)} دیگر\n🎁 سهمیه دوره بعد: {allowance} اعتبار"
    text += "\n\n💳 اگر نمی‌خواهید تا شارژ بعدی صبر کنید، می‌توانید همین حالا اشتراک تهیه کنید."
    if ADMIN_CARD_NUMBER:
        text += f"\n\n💰 مبلغ اشتراک: {SUBSCRIPTION_PRICE_TEXT}\nشماره کارت: {ADMIN_CARD_NUMBER}"
        if ADMIN_CARD_HOLDER:
            text += f"\nبه نام: {ADMIN_CARD_HOLDER}"
        text += "\nپس از پرداخت، رسید را همین‌جا ارسال کنید."
    else:
        text += "\n\nبرای مشاهده مبلغ و روش پرداخت، روی «💳 خرید اشتراک» بزنید."
    return text


async def dispatch_ai_question(update, context, question, case_summary='', standard_prompt='', case_title='', case_id=None, context_mode=''):
    uid=update.effective_user.id
    if not (AI_ENABLED and AI_EXTERNAL_DATA_CONSENT):
        await update.effective_message.reply_text('🤖 AI خارجی در تنظیمات فعال نیست؛ بنابراین هیچ متن حقوقی به سرویس خارجی ارسال نمی‌شود.')
        return False
    from .core.ai_entitlement import AIEntitlementService
    ai_entitlement = AIEntitlementService()
    ok, reservation = ai_entitlement.reserve_question(uid)
    if not ok:
        reservation = False
    if not reservation:
        credit = credit_status(uid)
        if credit:
            await update.effective_message.reply_text(
                _free_credit_exhausted_message(credit, insufficient=True),
                reply_markup=_free_credit_exhausted_reply_markup(),
            )
        else:
            await update.effective_message.reply_text('🤖 سهمیه سؤال AI شما در این دوره تمام شده است.')
        return False
    try:
        result=await asyncio.to_thread(ask_ai_question, question, case_summary, standard_prompt, preference_uid=uid)
        from .text_guard import prepare_ai_answer
        result = prepare_ai_answer(result)
        if not result: raise RuntimeError('پاسخ خالی یا فاقد متن قابل نمایش بود')
        await reply_long(update.effective_message,result)
        if case_id:
            add_case_ai_exchange(uid, int(case_id), question, str(result), context_mode)
        if reservation and reservation != "subscription":
            ai_entitlement.commit(uid, reservation)
        elif reservation == "subscription":
            ai_entitlement.commit(uid, reservation)
        if case_title:
            await update.effective_message.reply_text(f'📁 زمینه پرونده «{case_title[:100]}» همراه سؤال ارسال شد.')
        return True
    except Exception as e:
        ai_entitlement.refund(uid, reservation)
        logger.exception('AI question failed for user=%s', uid)
        await update.effective_message.reply_text('❌ پاسخ AI دریافت نشد و سهمیه مصرف نشد. لطفاً دوباره تلاش کنید.')
        return False


async def show_ai_quota(update, context):
    uid=update.effective_user.id
    from .core.entitlements import EntitlementService
    status = EntitlementService().status(uid)
    if not status:
        await update.effective_message.reply_text('🤖 اطلاعات سهمیه شما در دسترس نیست.')
        return
    if status.get('source') == 'subscription':
        q = status.get('ai_question') or {}
        await update.effective_message.reply_text(f'🤖 سهمیه AI اشتراک: {q.get("remaining", 0)} از {q.get("limit", 0)}')
        return
    c = status.get('credits') or {}
    await update.effective_message.reply_text(
        f'🪙 اعتبار رایگان: {c.get("remaining", 0)} از {c.get("allowance", 0)}\n'
        f'🔄 شارژ بعدی: {c.get("period_end", "")[:19].replace("T", " ")} UTC'
    )


async def myid(update, context):
    await _admin_reply(update, f'🆔 شناسه شما: {update.effective_user.id}')


async def _admin_reply(update, text):
    uid=update.effective_user.id
    if uid not in ADMIN_TELEGRAM_IDS:
        await update.effective_message.reply_text('⛔ دسترسی ندارید.'); return
    await update.effective_message.reply_text(text)


async def admin_grant(update, context):
    uid=update.effective_user.id
    if uid not in ADMIN_TELEGRAM_IDS: await update.effective_message.reply_text('⛔ دسترسی ندارید.'); return
    try: target=int(context.args[0]); days=int(context.args[1]) if len(context.args)>1 else 30
    except Exception: await update.effective_message.reply_text('استفاده: /grant USER_ID [DAYS]'); return
    _db.admin_grant(target,days=days,limit=50,admin_id=uid)
    await update.effective_message.reply_text('✅ اشتراک فعال شد.')


async def admin_revoke(update, context):
    uid=update.effective_user.id
    if uid not in ADMIN_TELEGRAM_IDS: await update.effective_message.reply_text('⛔ دسترسی ندارید.'); return
    try: target=int(context.args[0])
    except Exception: await update.effective_message.reply_text('استفاده: /revoke USER_ID'); return
    await update.effective_message.reply_text('✅' if _db.admin_revoke(target) else '❌ کاربر پیدا نشد.')


async def admin_user(update, context):
    uid=update.effective_user.id
    if uid not in ADMIN_TELEGRAM_IDS: await update.effective_message.reply_text('⛔ دسترسی ندارید.'); return
    try: target=int(context.args[0])
    except Exception: await update.effective_message.reply_text('استفاده: /user USER_ID'); return
    s=subscription_status(target); await update.effective_message.reply_text(str(s))


async def payment_cb(update, context):
    q=update.callback_query; await q.answer()
    if not await _require_registered(q): return
    await q.message.reply_text('💳 پس از پرداخت، تصویر رسید را همین‌جا ارسال کنید. رسید مستقیماً برای ادمین ارسال و پس از بررسی اشتراک فعال می‌شود.')


async def ocrstatus(update, context):
    """Report local OCR readiness without invoking unrelated AI handlers."""
    s = await asyncio.to_thread(ocr_status)
    await update.effective_message.reply_text('🔧 وضعیت OCR:\n' + str(s))


async def unhandled_callback(update, context):
    """Final safety net for stale/unknown callback_data."""
    q=update.callback_query
    if not q:
        return
    try:
        await q.answer('این گزینه دیگر فعال نیست.', show_alert=False)
    except Exception:
        pass
    if q.message:
        await q.message.reply_text('⚠️ این گزینه مربوط به نسخه قدیمی یا مسیری است که فعلاً فعال نیست. از منوی اصلی استفاده کنید.')


def register_v12_choice_handlers(application):
    application.add_handler(CallbackQueryHandler(access_choice_cb, pattern=r'^choose_(pro|free)$'))


async def access_choice_cb(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if not await _require_registered(q): return
    _clear_pending_inputs(context)
    mode='pro' if q.data=='choose_pro' else 'free'
    if mode=='pro':
        # Selecting a plan must never grant paid entitlements by itself.
        await q.message.reply_text('💎 نسخه پرو پس از تأیید اشتراک فعال می‌شود. فعلاً از بخش «💳 اشتراک» اقدام کنید.')
        return
    set_account_mode(uid,'free')
    grant_free_entitlement(uid)
    await q.message.reply_text('🎁 حالت رایگان انتخاب شد.\n\n')


async def show_access_choice(update, context):
    await update.effective_message.reply_text('روش استفاده را انتخاب کنید:',reply_markup=access_choice_keyboard())


def needs_access_choice(uid): return get_account_mode(uid) is None


async def v12_start_gate(update, context):
    if needs_access_choice(update.effective_user.id):
        await show_access_choice(update,context); return True
    return False


async def ai_question_message_router(update, context):
    if not context.user_data.get('awaiting_ai_question'): return False
    context.user_data.pop('awaiting_ai_question',None); await dispatch_ai_question(update,context,update.effective_message.text or ''); return True

def mark_ai_answer_success(uid): return consume_ai_question(uid)
def finalize_ai_answer(uid, answer_text): return bool(answer_text and consume_ai_question(uid))

# Alias kept for compatibility with older imports; the canonical handler is case_text_cb.
casetext_cb = case_text_cb
