import tempfile
from pathlib import Path

from legal_bot import db, api
from legal_bot.core.cases import CaseService


def setup_module(module):
    module._old_db = db.DB_PATH
    module._tmp = tempfile.TemporaryDirectory()
    db.DB_PATH = Path(module._tmp.name) / 'calendar.db'
    db.init_db(); db.v193_upgrade(); db.v20_upgrade(); db.v67_upgrade()
    db.register_user(3101, 'calendar-a', '3101', full_name='A')
    db.register_user(4202, 'calendar-b', '4202', full_name='B')
    db.init_case_workspace_tables(); db.init_case_dates_table()
    module.case_a = CaseService().create_empty(3101, 'پرونده الف')
    module.case_b = CaseService().create_empty(4202, 'پرونده ب')


def teardown_module(module):
    db.DB_PATH = module._old_db
    module._tmp.cleanup()


def test_calendar_merges_owned_tasks_and_extracted_dates():
    tid = db.add_case_task(3101, case_a['id'], 'تنظیم لایحه', '2026-11-05')
    assert tid
    db.add_case_important_dates(3101, case_a['id'], [{
        'date_jalali': '1405/08/14', 'date_gregorian': '2026-11-05',
        'description': 'جلسه رسیدگی', 'source_page': 2, 'source_text': 'جلسه رسیدگی در تاریخ مقرر'
    }])
    rows = db.list_user_calendar_items(3101, '2026-11-01', '2026-11-30')
    assert {x['item_type'] for x in rows} == {'task', 'case_date'}
    assert all(x['case_name'] == 'پرونده الف' for x in rows)
    assert db.list_user_calendar_items(4202, '2026-11-01', '2026-11-30') == []


def test_calendar_api_validates_range_and_returns_private_items():
    handler = object.__new__(api.APIHandler)
    captured = {}
    handler.path = '/api/v1/calendar?from=2026-11-01&to=2026-11-30'
    handler._send = lambda status, payload, **kwargs: captured.update(status=status, payload=payload)
    handler._calendar(3101)
    assert captured['status'] == 200
    assert captured['payload']['data']['count'] >= 2
    handler.path = '/api/v1/calendar?from=bad&to=2026-11-30'
    try:
        handler._calendar(3101)
    except ValueError:
        pass
    else:
        raise AssertionError('invalid calendar range must be rejected')


def test_miniapp_calendar_reuses_existing_calendar_and_case_task_routes():
    root = Path(__file__).resolve().parents[1]
    app = (root / 'miniapp' / 'app.js').read_text(encoding='utf-8')
    html = (root / 'miniapp' / 'index.html').read_text(encoding='utf-8')
    assert 'async function openCalendar()' in app
    assert '/api/v1/calendar?' in app
    assert "due_at:$('taskDue').value||null" in app
    assert "data-calendar-task" in app
    assert 'id="homeMiniCalendar"' in html
    assert 'id="calendarMonth"' in html


def test_global_bot_tasks_are_included_in_calendar_and_can_be_completed():
    task_id = db.add_task(3101, 'تماس با موکل', due_at='2026-11-12')
    rows = db.list_user_calendar_items(3101, '2026-11-01', '2026-11-30')
    global_item = next(x for x in rows if x['item_type'] == 'user_task' and x['id'] == task_id)
    assert global_item['case_name'] == 'کارهای من'
    handler = object.__new__(api.APIHandler)
    captured = {}
    handler._send = lambda status, payload, **kwargs: captured.update(status=status, payload=payload)
    handler._update_calendar_task(3101, task_id, {'done': True, 'item_type': 'user_task'})
    assert captured['status'] == 200
    assert db.get_task(3101, task_id)['done'] == 1


def test_calendar_api_creates_global_and_case_linked_tasks_safely():
    handler = object.__new__(api.APIHandler)
    captured = {}
    handler._send = lambda status, payload, **kwargs: captured.update(status=status, payload=payload)
    handler._create_calendar_task(3101, {'title': 'پیگیری مستقل', 'due_at': '2026-11-18'})
    assert captured['status'] == 201
    assert captured['payload']['data']['item_type'] == 'user_task'
    handler._create_calendar_task(3101, {'title': 'ارسال لایحه', 'due_at': '2026-11-19', 'case_id': case_a['id']})
    assert captured['status'] == 201
    assert captured['payload']['data']['item_type'] == 'task'
    try:
        handler._create_calendar_task(3101, {'title': 'تاریخ نامعتبر', 'due_at': '2026-19-99'})
    except ValueError:
        pass
    else:
        raise AssertionError('invalid task date must be rejected')


def test_bot_task_creation_now_requests_optional_due_date():
    source = Path(__file__).resolve().parents[1] / 'legal_bot' / 'handlers.py'
    text = source.read_text(encoding='utf-8')
    assert "context.user_data['awaiting_task_due']=True" in text
    assert "add_task(uid,title,due_at=parsed[3].isoformat())" in text
    assert 'بدون موعد' in text


def test_calendar_task_reminders_are_due_once_and_isolated_by_user():
    from datetime import datetime, timedelta
    try:
        from zoneinfo import ZoneInfo
        today = datetime.now(ZoneInfo('Asia/Tehran')).date()
    except Exception:
        today = datetime.now().date()
    due = (today + timedelta(days=1)).isoformat()
    global_id = db.add_task(3101, 'یادآوری تماس', due_at=due, reminder_days=1)
    case_id = db.add_case_task(3101, case_a['id'], 'یادآوری لایحه', due_at=due, reminder_days=1)
    other_user_id = db.add_task(4202, 'کار محرمانه وکیل دیگر', due_at=due, reminder_days=1)
    due_rows = db.list_due_calendar_task_reminders()
    keys = {(r['user_id'], r['item_type'], r['task_id']) for r in due_rows}
    assert (3101, 'user_task', global_id) in keys
    assert (3101, 'task', case_id) in keys
    assert (4202, 'user_task', other_user_id) in keys
    assert db.mark_calendar_task_reminder_sent(3101, 'user_task', global_id)
    assert not db.mark_calendar_task_reminder_sent(3101, 'user_task', global_id)
    remaining = {(r['user_id'], r['item_type'], r['task_id']) for r in db.list_due_calendar_task_reminders()}
    assert (3101, 'user_task', global_id) not in remaining


def test_calendar_task_reminder_validation_and_storage():
    handler = object.__new__(api.APIHandler)
    captured = {}
    handler._send = lambda status, payload, **kwargs: captured.update(status=status, payload=payload)
    handler._create_calendar_task(3101, {
        'title': 'مهلت با یادآوری', 'due_at': '2026-11-20', 'reminder_days': 3
    })
    task_id = captured['payload']['data']['id']
    assert db.get_task(3101, task_id)['reminder_days'] == 3
    try:
        handler._create_calendar_task(3101, {
            'title': 'یادآوری نامعتبر', 'due_at': '2026-11-20', 'reminder_days': 2
        })
    except ValueError:
        pass
    else:
        raise AssertionError('unsupported reminder offset must be rejected')
    try:
        handler._create_calendar_task(3101, {
            'title': 'یادآوری بدون موعد', 'reminder_days': 1
        })
    except ValueError:
        pass
    else:
        raise AssertionError('reminder without due date must be rejected')


def test_calendar_ui_exposes_reminder_choices_without_parallel_menu():
    root = Path(__file__).resolve().parents[1]
    app = (root / 'miniapp' / 'app.js').read_text(encoding='utf-8')
    assert 'id="calendarTaskReminder"' in app
    assert 'id="taskReminder"' in app
    assert 'reminder_days:' in app
    assert 'یک هفته قبل' in app


def test_calendar_api_accepts_and_persists_optional_exact_time():
    handler = object.__new__(api.APIHandler)
    captured = {}
    handler._send = lambda status, payload, **kwargs: captured.update(status=status, payload=payload)
    handler._create_calendar_task(3101, {
        'title': 'جلسه با موکل', 'due_at': '2026-11-21T14:30'
    })
    assert captured['status'] == 201
    task_id = captured['payload']['data']['id']
    assert db.get_task(3101, task_id)['due_at'] == '2026-11-21T14:30'


def test_calendar_miniapp_has_week_mode_and_optional_time_without_new_menu():
    root = Path(__file__).resolve().parents[1]
    app = (root / 'miniapp' / 'app.js').read_text(encoding='utf-8')
    css = (root / 'miniapp' / 'styles.css').read_text(encoding='utf-8')
    assert 'calendarView="month"' in app
    assert 'calendarWeekView' in app and 'calendarMonthView' in app
    assert 'calendarWeekStart(calendarSelectedDate)' in app
    assert 'id="calendarTaskTime" type="time"' in app
    assert 'due_at:due' in app and 'T${timeValue}' in app
    assert 'calendar-week-grid' in css
