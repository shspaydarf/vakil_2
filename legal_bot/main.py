"""Production entrypoint for LegalBot V165.

Single source of truth for Telegram dispatcher registration.  Every callback
used by the current core menu is registered here, including casetext:ID.
"""
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from .config import BOT_TOKEN, PHONE_HASH_SECRET, PHONE_HASH_SECRET_MIN_LEN
from .ai_usage import init_ai_usage_tables
from .db import init_db, v193_upgrade, v20_upgrade, v67_upgrade, init_subscription_tables, init_free_channel_tables, init_service_listings_table, init_v41_workflow_tables, init_case_dates_table, init_case_reminders_table, init_case_workspace_tables, init_drafting_workflow_tables, list_due_case_reminders, mark_case_reminder_sent, list_due_calendar_task_reminders, mark_calendar_task_reminder_sent, cleanup_retention
from .storage import cleanup_temp_files
from .handlers import (
    start, contact, text, status_cb, cases_cb, case_cmd, subscribe_cb,
    support_menu_cb, legal_search_menu_cb, source_detail_cb, tools_menu_cb, topics_menu_cb, account_menu_cb, support_cb, help_cb, law_cb, glossary_cb, document, photo, payment_cb,
    admin_grant, admin_revoke, admin_user, myid, ocrstatus, new_case_cb,
    home_cb, ai_menu_cb, ai_cases_cb, ai_future_placeholder_cb, ai_case_feature_select_cb, ai_contract_review_cb, case_view_cb, case_summary_cb, case_summary_detailed_cb, case_next_step_cb, case_relevant_laws_cb, case_archive_cb, case_delete_cb, case_delete_confirm_cb, archived_cases_cb, archived_view_cb, archived_restore_cb, account_delete_cb, account_delete_confirm_cb, case_note_cb, case_note_edit_cb, case_note_clear_cb, case_file_action_cb, case_add_done_cb, case_text_cb, caseq_cb, case_ai_cb, case_ai_context_cb, case_workspace_cb, case_intelligence_cb, case_check_tree_cb, case_check_tree_step_cb, case_check_tree_restart_cb, case_check_tree_close_cb, case_lease_tree_cb, case_lease_tree_step_cb, case_lease_tree_restart_cb, case_lease_tree_close_cb, case_contract_tree_cb, case_contract_tree_step_cb, case_contract_tree_restart_cb, case_contract_tree_close_cb, case_claims_tree_cb, case_claims_tree_step_cb, case_claims_tree_restart_cb, case_claims_tree_close_cb, case_property_tree_cb, case_property_tree_step_cb, case_property_tree_restart_cb, case_property_tree_close_cb, case_analysis_menu_cb, case_drafting_menu_cb, case_start_workflow_161_cb, case_continue_workflow_161_cb, case_workflow_info_161_cb, case_workflow_status_161_cb, case_workflow_answer_162_cb, case_workflow_skip_162_cb, case_timeline_cb, case_authority_cb, case_strategy_cb, case_draft_cb, case_adversarial_review_cb, case_rewrite_158_cb, case_consistency_gate_159_cb, case_output_160_cb, case_output_docx_160_cb, case_output_pdf_160_cb, case_output_text_160_cb, case_output_changes_160_cb, case_output_gate_160_cb, case_output_source_160_cb, case_tasks_cb, case_task_new_cb, case_task_action_cb, case_status_cb, case_stage_cb, case_priority_cb, case_next_action_cb,
    feedback_cb, feedback_kind_cb, tasks_cb, globalsearch_cb,
    access_choice_cb, unhandled_callback, service_add_cb, myservices_cb, service_view_cb,
    service_delete_cb, service_edit_cb, service_fee_cb, service_charity_cb, service_admin_cb, payment_admin_cb, task_new_cb, task_action_cb, referral_new_cb, referral_urgency_cb, referrals_cb, referral_view_cb, referral_match_cb, referral_match_action_cb, referral_info_cb, referral_admin_cb,
    important_dates_cb, reminder_toggle_cb, reminders_cb, calculators_cb, quick_calc_cb, quick_percent_cb, quick_rial_cb, quick_rial_reverse_cb, quick_installment_cb, quick_datediff_cb, calendar_cb, calendar_today_cb, calendar_convert_cb, calculator_about_cb, fines_cb, alcohol_fine_cb, mahr_cb, mahr_amount_cb, mahr_year_cb, diya_cb, diya_percent_cb, diya_result_cb, diya_head_cb, diya_color_cb, diya_ersh_cb, delay_cb, fee_cb, fee_stage_cb, lawyer_fee_cb, lawyer_fee_result_cb, deadline_cb, taxhelp_cb, tax_screen_cb, tax_activity_cb, tax_task_cb, tax_income_cb, tax_docs_cb, shora_cb, shora_topic_cb, shora_amount_cb, shora_docs_cb, ejare_cb, ejare_role_cb, ejare_topic_cb, ejare_search_cb, family_cb, family_role_cb, family_topic_cb, family_search_cb, check_cb, check_role_cb, check_topic_cb, check_search_cb, role_set_cb, role_change_cb, caseupload_finish_cb, briefs_cb, brief_information_start_cb, brief_information_cb, brief_mode_cb, brief_type_cb, brief_stage_cb, brief_case_cb, brief_templates_cb, brief_template_pick_cb, brief_source_cb, brief_source_delete_cb, brief_research_cb, brief_regenerate_cb, brief_template_use_cb, brief_editprompt_cb, brief_workspace_cb, brief_sections_cb, brief_section_edit_cb, brief_compare_cb, brief_review_cb, brief_sources_cb, brief_history_cb, brief_version_cb, brief_word_cb, brief_pdf_cb, brief_version_use_cb, brief_understanding_cb, brief_argument_map_cb, brief_opposing_cb, brief_opposing_result_cb, brief_opposing_edit_cb, brief_opposing_outline_cb, brief_finalcheck_cb, brief_gap_cb, brief_consistency_cb, brief_cleanup_cb, brief_force_regenerate_cb, quiz_cb, quiz_mode_cb, quiz_term_cb, quiz_cat_cb, quiz_ans_cb, quiz_essay_cat_cb, quiz_essay_show_cb, quiz_essay_next_cb, clients_cb, client_list_cb, client_add_cb, client_quick_add_cb, client_search_cb, client_view_cb, client_edit_cb, client_delete_cb, client_delete_confirm_cb, client_link_cb, client_link_do_cb, client_link_active_cb, client_link_active_do_cb,
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
logger=logging.getLogger('legal_bot')


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception('Unhandled Telegram update error', exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text('❌ خطای غیرمنتظره‌ای رخ داد. لطفاً دوباره تلاش کنید.')
        except Exception:
            pass


async def _maintenance_worker(app):
    """V67: reminders plus retention cleanup and off-tree backups."""
    import asyncio
    from datetime import datetime, timezone
    from .config import BACKUP_INTERVAL_HOURS
    from .backup import create_backup, rotate_backups
    last_backup = 0.0
    while True:
        try:
            due=list_due_case_reminders()
            for r in due:
                text=(f'🔔 یادآوری پرونده\n\n📁 پرونده: {r["file_name"] or "بدون نام"}\n📅 تاریخ: {r["date_jalali"]}\n📌 موضوع: {r["description"]}\n\nاین یادآوری بر اساس تاریخ استخراج‌شده از متن پرونده است؛ به معنی تشخیص قطعی مهلت قانونی نیست.')
                try:
                    await app.bot.send_message(chat_id=r['user_id'], text=text)
                    mark_case_reminder_sent(r['reminder_id'])
                except Exception:
                    logger.exception('case reminder send failed: reminder=%s', r['reminder_id'])
            for r in list_due_calendar_task_reminders():
                due_date=str(r.get('due_at') or '')[:10]
                try:
                    from datetime import date
                    from .calendar_dates import gregorian_to_jalali
                    jy,jm,jd=gregorian_to_jalali(date.fromisoformat(due_date))
                    due_label=f'{jy:04d}/{jm:02d}/{jd:02d}'
                except Exception:
                    due_label=due_date
                lead=int(r.get('reminder_days') or 0)
                lead_label='در روز موعد' if lead==0 else f'{lead} روز مانده به موعد'
                msg=(f'🔔 یادآوری کار\n\n📌 {r["title"]}\n📅 موعد شمسی: {due_label}\n⏰ زمان یادآوری: {lead_label}\n📁 {r.get("case_name") or "کار عمومی"}\n\nاین یادآوری بر اساس تاریخی است که خودتان برای کار ثبت کرده‌اید؛ محاسبه یا تأیید مهلت قانونی نیست.')
                try:
                    await app.bot.send_message(chat_id=r['user_id'], text=msg)
                    mark_calendar_task_reminder_sent(r['user_id'], r['item_type'], r['task_id'])
                except Exception:
                    logger.exception('calendar task reminder send failed: user=%s type=%s task=%s', r['user_id'], r['item_type'], r['task_id'])
            cleanup_temp_files()
            cleanup_retention()
            now = datetime.now(timezone.utc).timestamp()
            if now - last_backup >= BACKUP_INTERVAL_HOURS * 3600:
                await asyncio.to_thread(create_backup)
                await asyncio.to_thread(rotate_backups)
                last_backup = now
        except Exception:
            logger.exception('V67 maintenance worker failed')
        await asyncio.sleep(900)


def build_application():
    if not BOT_TOKEN:
        raise RuntimeError('BOT_TOKEN در Secrets تنظیم نشده است.')
    if len(PHONE_HASH_SECRET) < PHONE_HASH_SECRET_MIN_LEN:
        raise RuntimeError(f'PHONE_HASH_SECRET باید حداقل {PHONE_HASH_SECRET_MIN_LEN} نویسه و فقط از Secrets تنظیم شود.')
    init_db(); init_ai_usage_tables(); v193_upgrade(); v20_upgrade(); v67_upgrade(); init_subscription_tables(); init_free_channel_tables(); init_service_listings_table(); init_v41_workflow_tables(); init_case_dates_table(); init_case_reminders_table(); init_case_workspace_tables(); init_drafting_workflow_tables()
    app=Application.builder().token(BOT_TOKEN).build()
    app.create_task(_maintenance_worker(app), name='v67-maintenance-worker')
    app.add_error_handler(error_handler)

    # Commands
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('case', case_cmd))
    app.add_handler(CommandHandler('grant', admin_grant))
    app.add_handler(CommandHandler('revoke', admin_revoke))
    app.add_handler(CommandHandler('user', admin_user))
    app.add_handler(CommandHandler('myid', myid))
    app.add_handler(CommandHandler('ocrstatus', ocrstatus))

    # Media / registration
    app.add_handler(MessageHandler(filters.CONTACT, contact))
    app.add_handler(MessageHandler(filters.Document.ALL, document))
    app.add_handler(MessageHandler(filters.PHOTO, photo))

    # Core callback map — deliberately explicit and non-overlapping.
    callbacks = [
        (access_choice_cb, r'^choose_(pro|free)$'),
        (payment_admin_cb, r'^pay(ok|no):'),
        (payment_cb, r'^pay$'),
        (status_cb, r'^status$'),
        (cases_cb, r'^cases$'),
        (clients_cb, r'^clients$'),
        (client_list_cb, r'^clientlist$'),
        (client_add_cb, r'^clientadd$'),
        (client_quick_add_cb, r'^clientaddquick$'),
        (client_search_cb, r'^clientsearch$'),
        (client_view_cb, r'^clientview:\d+$'),
        (client_edit_cb, r'^clientedit:\d+$'),
        (client_delete_cb, r'^clientdelete:\d+$'),
        (client_delete_confirm_cb, r'^clientdelconfirm:\d+$'),
        (client_link_cb, r'^clientlink:\d+$'),
        (client_link_do_cb, r'^clientlinkdo:\d+:\d+$'),
        (client_link_active_cb, r'^clientlinkactive$'),
        (client_link_active_do_cb, r'^clientlinkactive_do:\d+:\d+$'),
        (case_view_cb, r'^caseview:\d+$'),
        (case_summary_detailed_cb, r'^csummaryd:\d+$'),
        (case_workspace_cb, r'^cworkspace:\d+$'),
        (case_intelligence_cb, r'^cintel:\d+$'),
        (case_check_tree_cb, r'^cchecktree:\d+$'),
        (case_check_tree_step_cb, r'^ccstep:\d+:[a-z]$'),
        (case_check_tree_restart_cb, r'^ccrestart:\d+$'),
        (case_check_tree_close_cb, r'^ccclose:\d+$'),
        (case_lease_tree_cb, r'^cleasetree:\d+$'),
        (case_lease_tree_step_cb, r'^clstep:\d+:[a-z]$'),
        (case_lease_tree_restart_cb, r'^clrestart:\d+$'),
        (case_lease_tree_close_cb, r'^clclose:\d+$'),
        (case_contract_tree_cb, r'^ccontracttree:\d+$'),
        (case_contract_tree_step_cb, r'^cctstep:\d+:[a-z]+$'),
        (case_contract_tree_restart_cb, r'^cctrestart:\d+$'),
        (case_contract_tree_close_cb, r'^cctclose:\d+$'),
        (case_claims_tree_cb, r'^cclaimstree:\d+$'),
        (case_claims_tree_step_cb, r'^cclstep:\d+:[a-z]+$'),
        (case_claims_tree_restart_cb, r'^cclrestart:\d+$'),
        (case_claims_tree_close_cb, r'^cclclose:\d+$'),
        (case_property_tree_cb, r'^cpropertytree:\d+$'),
        (case_property_tree_step_cb, r'^cptstep:\d+:[a-z]+$'),
        (case_property_tree_restart_cb, r'^cptrestart:\d+$'),
        (case_property_tree_close_cb, r'^cptclose:\d+$'),
        (case_analysis_menu_cb, r'^canalysis:\d+$'),
        (case_drafting_menu_cb, r'^cdrafting:\d+$'),
        (case_start_workflow_161_cb, r'^cstart161:\d+$'),
        (case_continue_workflow_161_cb, r'^ccontinue161:\d+$'),
        (case_workflow_info_161_cb, r'^cinfo161:\d+$'),
        (case_workflow_status_161_cb, r'^cstatus161:\d+$'),
        (case_workflow_answer_162_cb, r'^canswer162:\d+$'),
        (case_workflow_skip_162_cb, r'^cskip162:\d+$'),
        (case_timeline_cb, r'^ctimeline:\d+$'),
        (case_issues_cb, r'^cissues:\d+$'),
        (case_evidence_cb, r'^cevidence:\d+$'),
        (case_authority_cb, r'^cauthority:\d+$'),
        (case_strategy_cb, r'^cstrategy:\d+$'),
        (case_draft_cb, r'^cdraft:\d+$'),
        (case_adversarial_review_cb, r'^creview157:\d+$'),
        (case_rewrite_158_cb, r'^crewrite158:\d+$'),
        (case_consistency_gate_159_cb, r'^cgate159:\d+$'),
        (case_output_160_cb, r'^coutput160:\d+$'),
        (case_output_docx_160_cb, r'^coutdocx160:\d+$'),
        (case_output_pdf_160_cb, r'^coutpdf160:\d+$'),
        (case_output_text_160_cb, r'^couttext160:\d+$'),
        (case_output_changes_160_cb, r'^coutchg160:\d+$'),
        (case_output_gate_160_cb, r'^coutgate160:\d+$'),
        (case_output_source_160_cb, r'^coutsrc160:\d+$'),
        (case_tasks_cb, r'^ctasks:\d+$'),
        (case_task_new_cb, r'^ctasknew:\d+$'),
        (case_task_action_cb, r'^ctask:(done|delete):\d+$'),
        (case_status_cb, r'^cstatus:\d+$'),
        (case_stage_cb, r'^cstage:(new|review|action|closed):\d+$'),
        (case_priority_cb, r'^cprio:(normal|high|urgent|low):\d+$'),
        (case_next_action_cb, r'^cnextaction:\d+$'),
        (case_summary_cb, r'^csummary:\d+$'),
        (case_next_step_cb, r'^cnext:\d+$'),
        (case_relevant_laws_cb, r'^claws:\d+$'),
        (case_archive_cb, r'^carchive:\d+$'),
        (case_delete_cb, r'^casedelete:\d+$'),
        (case_delete_confirm_cb, r'^casedelconfirm:\d+$'),
        (archived_cases_cb, r'^archivedcases$'),
        (archived_view_cb, r'^archivedview:\d+$'),
        (archived_restore_cb, r'^archiverestore:\d+$'),
        (account_delete_cb, r'^accountdelete$'),
        (account_delete_confirm_cb, r'^accountdelconfirm$'),
        (case_note_cb, r'^cnote:\d+$'),
        (case_note_edit_cb, r'^cnoteedit:\d+$'),
        (case_note_clear_cb, r'^cnoteclr:\d+$'),
        (case_file_action_cb, r'^(?:cfile|cplaceholder):(add|version):\d+$'),
        (case_add_done_cb, r'^cadddone:\d+$'),
        (case_text_cb, r'^casetext:\d+$'),
        (caseq_cb, r'^caseq:\d+$'),
        (case_ai_cb, r'^cai:\d+$'),
        (case_ai_context_cb, r'^caictx:(summary|relevant|history|none):\d+$'),
        (subscribe_cb, r'^subscribe$'),
        (support_menu_cb, r'^support_menu$'),
        (support_cb, r'^support$'),
        (help_cb, r'^help$'),
        (legal_search_menu_cb, r'^legal_search_menu$'),
        (source_detail_cb, r'^source:CIT-[A-F0-9]{12}$'),
        (tools_menu_cb, r'^tools_menu$'),
        (topics_menu_cb, r'^topics_menu$'),
        (account_menu_cb, r'^account_menu$'),
        (law_cb, r'^law$'),
        (glossary_cb, r'^glossary$'),
        (new_case_cb, r'^newcase$'),
        (home_cb, r'^home$'),
        (ai_menu_cb, r'^aimenu$'),
        (ai_cases_cb, r'^aicases$'),
        (ai_future_placeholder_cb, r'^aifuture:(question|legal|documents|drafting|review)$'),
        (ai_case_feature_select_cb, r'^aicasepick:(documents|drafting|review):\d+$'),
        (ai_contract_review_cb, r'^aicontract:\d+(?::[a-z_]+)?$'),
        (feedback_cb, r'^feedback$'),
        (feedback_kind_cb, r'^fb:'),
        (tasks_cb, r'^tasks$'),
        (important_dates_cb, r'^importantdates$'),
        (reminder_toggle_cb, r'^remind:\d+$'),
        (reminders_cb, r'^reminders$'),
        (task_new_cb, r'^tasknew$'),
        (task_action_cb, r'^taskact:(done|undo|delete):\d+$'),
        (referral_new_cb, r'^referral_new$'),
        (referral_urgency_cb, r'^refurg:(normal|soon|urgent)$'),
        (referrals_cb, r'^referrals$'),
        (referral_view_cb, r'^refview:\d+$'),
        (referral_match_cb, r'^refmatch:\d+$'),
        (referral_match_action_cb, r'^refmatch:(accept|decline|more):\d+$'),
        (referral_info_cb, r'^refinfo:\d+$'),
        (referral_admin_cb, r'^refadmin:(send|close):\d+(?::\d+)?$'),
        (globalsearch_cb, r'^globalsearch$'),
        (service_add_cb, r'^service_add$'),
        (myservices_cb, r'^myservices$'),
        (service_view_cb, r'^serviceview:\d+$'),
        (service_delete_cb, r'^servicedelete:\d+$'),
        (service_edit_cb, r'^serviceedit:\d+$'),
        (service_fee_cb, r'^servicefee:(fixed|percent)$'),
        (service_charity_cb, r'^servicecharity:(yes|no)$'),
        (service_admin_cb, r'^serviceadmin:(approve|reject):\d+$'),
        (calculators_cb, r'^calculators$'),
        (quick_calc_cb, r'^calc:quick$'),
        (quick_percent_cb, r'^calc:quick:percent$'),
        (quick_rial_cb, r'^calc:quick:rial$'),
        (quick_rial_reverse_cb, r'^calc:quick:rial_reverse$'),
        (quick_installment_cb, r'^calc:quick:installment$'),
        (quick_datediff_cb, r'^calc:quick:datediff$'),
        (calendar_cb, r'^calc:calendar$'),
        (calendar_today_cb, r'^calc:calendar:today$'),
        (calendar_convert_cb, r'^calc:calendar:convert$'),
        (calculator_about_cb, r'^calc:about$'),
        (fines_cb, r'^calc:fines$'),
        (alcohol_fine_cb, r'^calc:fine:alcohol$'),
        (mahr_cb, r'^calc:mahr$'),
                (mahr_year_cb, r'^calc:mahryear:\d+$'),
        (diya_cb, r'^calc:diya$'),
        (diya_percent_cb, r'^calc:diya:percent$'),
        (diya_result_cb, r'^calc:diya:p:\d+(?:\.\d+)?:[nh]$'),
        (diya_head_cb, r'^calc:diya:head$'),
        (diya_color_cb, r'^calc:diya:color$'),
        (diya_ersh_cb, r'^calc:diya:ersh$'),
        (delay_cb, r'^calc:delay$'),
        (fee_cb, r'^calc:fee$'),
        (fee_stage_cb, r'^calc:feestage:(first|appeal|supreme)$'),
        (lawyer_fee_cb, r'^calc:lawyerfee$'),
        (lawyer_fee_result_cb, r'^calc:lawyerfee:result$'),
        (deadline_cb, r'^calc:deadline$'),
        (taxhelp_cb, r'^taxhelp$'),
        (tax_screen_cb, r'^taxscreen$'),
        (tax_activity_cb, r'^tax:act:(shop|service|rent|commission|home|other)$'),
        (tax_task_cb, r'^tax:task:(register|return|notice|reduce|unknown)$'),
        (tax_income_cb, r'^tax:income:(low|mid|high|large|unknown)$'),
        (tax_docs_cb, r'^tax:docs:(yes|no|unknown)$'),
        (shora_cb, r'^shora$'),
        (shora_topic_cb, r'^shora:topic:(check|rent|damage|neighbor|other)$'),
        (shora_amount_cb, r'^shora:amount:(low|mid|high|unknown)$'),
        (shora_docs_cb, r'^shora:docs:(yes|partial|no)$'),
        (role_set_cb, r'^role:set:(lawyer|client)$'),
        (role_change_cb, r'^role:change$'),
        (caseupload_finish_cb, r'^caseupload:finish$'),
        (ejare_cb, r'^ejare$'),
        (ejare_role_cb, r'^ejare:role:(tenant|landlord)$'),
        (ejare_topic_cb, r'^ejare:topic:(tenant|landlord):[a-z_]+$'),
        (ejare_search_cb, r'^ejare:search:(tenant|landlord):[a-z_]+$'),
        (family_cb, r'^family$'),
        (family_role_cb, r'^family:role:(creditor|debtor)$'),
        (family_topic_cb, r'^family:topic:(creditor|debtor):[a-z_]+$'),
        (family_search_cb, r'^family:search:(creditor|debtor):[a-z_]+$'),
        (check_cb, r'^check$'),
        (check_role_cb, r'^check:role:(holder|drawer)$'),
        (check_topic_cb, r'^check:topic:(holder|drawer):[a-z_]+$'),
        (check_search_cb, r'^check:search:(holder|drawer):[a-z_]+$'),
        (briefs_cb, r'^briefs$'),
        (brief_information_start_cb, r'^brief:info$'),
        (brief_information_cb, r'^brief:info:(answer|unknown|refresh|confirm)$'),
        (brief_mode_cb, r'^brief:(new|case|edit)$'),
        (brief_templates_cb, r'^brief:templates$'),
        (brief_source_cb, r'^briefsrc:(?:\d+|done)$'),
        (brief_source_delete_cb, r'^briefsrcdel:\d+$'),
        (brief_template_use_cb, r'^brieftpluse:[a-z_]+$'),
        (brief_research_cb, r'^brief:research$'),
        (brief_regenerate_cb, r'^brief:regenerate$'),
        (brief_editprompt_cb, r'^brief:editprompt$'),
        (brief_workspace_cb, r'^brief:workspace$'),
        (brief_sections_cb, r'^brief:sections$'),
        (brief_section_edit_cb, r'^briefsec:\d+$'),
        (brief_compare_cb, r'^brief:compare$'),
        (brief_compare_cb, r'^briefcompare:\d+$'),
        (brief_review_cb, r'^brief:review$'),
        (brief_sources_cb, r'^brief:sources$'),
        (brief_history_cb, r'^brief:history$'),
        (brief_version_cb, r'^briefver:\d+$'),
        (brief_word_cb, r'^brief:word$'),
        (brief_pdf_cb, r'^brief:pdf$'),
        (brief_version_use_cb, r'^briefveruse:\d+$'),
        (brief_understanding_cb, r'^brief:understanding$'),
        (brief_argument_map_cb, r'^brief:arguments$'),
        (brief_opposing_cb, r'^brief:opposing$'),
        (brief_opposing_result_cb, r'^brief:opposing_result$'),
        (brief_opposing_edit_cb, r'^brief:opposing_edit$'),
        (brief_opposing_outline_cb, r'^brief:opposing_outline$'),
        (brief_opposing_apply_cb, r'^brief:opposing_apply$'),
        (brief_finalcheck_cb, r'^brief:finalcheck$'),
        (brief_gap_cb, r'^brief:gaps$'),
        (brief_consistency_cb, r'^brief:consistency$'),
        (brief_cleanup_cb, r'^brief:cleanup$'),
        (brief_force_regenerate_cb, r'^briefregen:force$'),
        (brief_template_pick_cb, r'^brieftpl:[a-z_]+$'),
        (quiz_cb, r'^quiz$'),
        (quiz_mode_cb, r'^quiz:mode:(mcq|essay)$'),
        (quiz_term_cb, r'^quiz:term:[a-z0-9_]+$'),
        (quiz_cat_cb, r'^quiz:cat:[a-z0-9_]+$'),
        (quiz_ans_cb, r'^quiz:ans:[^:]+:[0-3]$'),
        (quiz_essay_cat_cb, r'^quiz:essaycat:[a-z_]+$'),
        (quiz_essay_show_cb, r'^quiz:essayshow:[^:]+:[0-9]+$'),
        (quiz_essay_next_cb, r'^quiz:essaynext:[^:]+:[0-9]+$'),
        (brief_type_cb, r'^brieftype:\d+$'),
        (brief_stage_cb, r'^briefstage:\d+$'),
        (brief_case_cb, r'^briefcase:\d+$'),
    ]
    for fn, pattern in callbacks:
        app.add_handler(CallbackQueryHandler(fn, pattern=pattern))

    # Final safety net: stale buttons from older messages must not leave the
    # Telegram client spinning forever. Specific handlers above win first.
    app.add_handler(CallbackQueryHandler(unhandled_callback))

    # Plain text is last: all stateful text routing lives in handlers.text.
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text))
    return app


def main():
    app=build_application()
    logger.info('LegalBot V165 starting')
    app.run_polling(drop_pending_updates=False, allowed_updates=['message','callback_query'])


if __name__=='__main__':
    main()
