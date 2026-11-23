import re
import sqlite3, hashlib, uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from .config import DB_PATH, FREE_CASES, AI_CASE_MONTHLY_LIMIT, FREE_WEEKLY_CREDITS


def conn():
    c=sqlite3.connect(DB_PATH, timeout=20)
    c.row_factory=sqlite3.Row
    # SQLite foreign keys are per connection; enforce integrity everywhere.
    c.execute('PRAGMA foreign_keys=ON')
    return c

def init_db():
    with conn() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY, phone_hash TEXT UNIQUE, phone_last4 TEXT,
            lawyer_code_hash TEXT, free_month TEXT NOT NULL, free_used INTEGER NOT NULL DEFAULT 0,
            active_case_id INTEGER,
            subscription_end TEXT, blocked INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS cases(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, file_name TEXT,
            status TEXT NOT NULL, result TEXT, created_at TEXT NOT NULL, archived_at TEXT, archived_from_status TEXT, FOREIGN KEY(user_id) REFERENCES users(user_id))''')
        c.execute('''CREATE TABLE IF NOT EXISTS case_pins(
            user_id INTEGER NOT NULL, case_id INTEGER NOT NULL, created_at TEXT NOT NULL,
            PRIMARY KEY(user_id, case_id),
            FOREIGN KEY(user_id) REFERENCES users(user_id),
            FOREIGN KEY(case_id) REFERENCES cases(id) ON DELETE CASCADE)''')
        c.execute('CREATE INDEX IF NOT EXISTS idx_case_pins_user_created ON case_pins(user_id, created_at DESC)')
        c.execute('''CREATE TABLE IF NOT EXISTS payments(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, status TEXT NOT NULL,
            created_at TEXT NOT NULL, FOREIGN KEY(user_id) REFERENCES users(user_id))''')
        c.execute('''CREATE TABLE IF NOT EXISTS case_documents(
            id INTEGER PRIMARY KEY AUTOINCREMENT, case_id INTEGER NOT NULL, file_name TEXT,
            page_count INTEGER NOT NULL DEFAULT 0, extracted_text TEXT, created_at TEXT NOT NULL,
            FOREIGN KEY(case_id) REFERENCES cases(id))''')
        c.execute('''CREATE TABLE IF NOT EXISTS case_versions(
            id INTEGER PRIMARY KEY AUTOINCREMENT, case_id INTEGER NOT NULL, version_no INTEGER NOT NULL,
            file_name TEXT, page_count INTEGER NOT NULL DEFAULT 0, extracted_text TEXT, created_at TEXT NOT NULL,
            UNIQUE(case_id, version_no), FOREIGN KEY(case_id) REFERENCES cases(id))''')
        c.execute('''CREATE TABLE IF NOT EXISTS case_lawyer_notes(
            case_id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, note_text TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL, FOREIGN KEY(case_id) REFERENCES cases(id), FOREIGN KEY(user_id) REFERENCES users(user_id))''')
        c.execute('''CREATE TABLE IF NOT EXISTS case_additions(
            id INTEGER PRIMARY KEY AUTOINCREMENT, case_id INTEGER NOT NULL, addition_no INTEGER NOT NULL,
            file_count INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
            UNIQUE(case_id, addition_no), FOREIGN KEY(case_id) REFERENCES cases(id))''')
        c.execute('''CREATE TABLE IF NOT EXISTS clients(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, name TEXT NOT NULL,
            phone TEXT, national_id TEXT, note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id))''')
        c.execute('''CREATE TABLE IF NOT EXISTS client_case_links(
            client_id INTEGER NOT NULL, case_id INTEGER NOT NULL, user_id INTEGER NOT NULL, created_at TEXT NOT NULL,
            PRIMARY KEY(client_id, case_id), FOREIGN KEY(client_id) REFERENCES clients(id), FOREIGN KEY(case_id) REFERENCES cases(id), FOREIGN KEY(user_id) REFERENCES users(user_id))''')
        c.execute('CREATE INDEX IF NOT EXISTS idx_clients_user_name ON clients(user_id, name)')
        c.execute("""CREATE TABLE IF NOT EXISTS credit_periods(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            period_start TEXT NOT NULL, period_end TEXT NOT NULL, allowance INTEGER NOT NULL,
            balance INTEGER NOT NULL, created_at TEXT NOT NULL, UNIQUE(user_id, period_start),
            FOREIGN KEY(user_id) REFERENCES users(user_id))""")
        c.execute("""CREATE TABLE IF NOT EXISTS credit_ledger(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, period_id INTEGER NOT NULL,
            reference_id TEXT NOT NULL UNIQUE, operation TEXT NOT NULL, cost INTEGER NOT NULL,
            status TEXT NOT NULL, created_at TEXT NOT NULL, finalized_at TEXT, metadata TEXT,
            FOREIGN KEY(user_id) REFERENCES users(user_id), FOREIGN KEY(period_id) REFERENCES credit_periods(id))""")
        c.execute('CREATE INDEX IF NOT EXISTS idx_credit_periods_user_end ON credit_periods(user_id, period_end)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_credit_ledger_user_created ON credit_ledger(user_id, created_at)')


def create_client(uid, name, phone='', national_id='', note=''):
    name=(name or '').strip(); phone=(phone or '').strip(); national_id=(national_id or '').strip(); note=(note or '').strip()
    if not name: return None
    ts=now_iso()
    with conn() as c:
        cur=c.execute('INSERT INTO clients(user_id,name,phone,national_id,note,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                      (uid,name,phone,national_id,note,ts,ts)); c.commit(); return cur.lastrowid

def list_clients(uid, limit=30):
    with conn() as c:
        rows=c.execute('SELECT * FROM clients WHERE user_id=? ORDER BY name COLLATE NOCASE, id DESC LIMIT ?', (uid,int(limit))).fetchall()
        return [dict(r) for r in rows]

def get_client(uid, client_id):
    with conn() as c:
        r=c.execute('SELECT * FROM clients WHERE id=? AND user_id=?',(int(client_id),uid)).fetchone()
        return dict(r) if r else None

def update_client(uid, client_id, name, phone='', national_id='', note=''):
    name=(name or '').strip()
    if not name: return False
    with conn() as c:
        cur=c.execute('UPDATE clients SET name=?,phone=?,national_id=?,note=?,updated_at=? WHERE id=? AND user_id=?',
                      (name,(phone or '').strip(),(national_id or '').strip(),(note or '').strip(),now_iso(),int(client_id),uid)); c.commit(); return cur.rowcount==1

def delete_client(uid, client_id):
    # Explicitly remove links in the same transaction for compatibility with
    # older databases whose FK did not use ON DELETE CASCADE.
    with conn() as c:
        cid=int(client_id)
        if not c.execute('SELECT 1 FROM clients WHERE id=? AND user_id=?',(cid,uid)).fetchone():
            return False
        c.execute('DELETE FROM client_case_links WHERE client_id=? AND user_id=?',(cid,uid))
        cur=c.execute('DELETE FROM clients WHERE id=? AND user_id=?',(cid,uid))
        c.commit()
        return cur.rowcount==1

def client_cases(uid, client_id):
    with conn() as c:
        rows=c.execute('''SELECT c.* FROM cases c WHERE c.user_id=? AND c.id IN
            (SELECT case_id FROM client_case_links WHERE client_id=? AND user_id=?) ORDER BY c.id DESC''',(uid,int(client_id),uid)).fetchall()
        return [dict(r) for r in rows]

def link_client_case(uid, client_id, case_id):
    if not get_client(uid, client_id) or not get_case(uid, case_id): return False
    with conn() as c:
        c.execute('INSERT OR IGNORE INTO client_case_links(client_id,case_id,user_id,created_at) VALUES(?,?,?,?)',(int(client_id),int(case_id),uid,now_iso())); c.commit(); return True

def unlink_client_case(uid, client_id, case_id):
    with conn() as c:
        cur=c.execute('DELETE FROM client_case_links WHERE client_id=? AND case_id=? AND user_id=?',(int(client_id),int(case_id),uid)); c.commit(); return cur.rowcount==1


def _credit_now():
    return datetime.now(timezone.utc)

def _ensure_credit_period_locked(c, uid, now=None):
    now = now or _credit_now()
    row = c.execute("SELECT * FROM credit_periods WHERE user_id=? ORDER BY id DESC LIMIT 1", (uid,)).fetchone()
    if row:
        end = datetime.fromisoformat(row['period_end'])
        if now < end:
            return dict(row)
    start = now; end = now + timedelta(days=7)
    c.execute("""INSERT INTO credit_periods
        (user_id,period_start,period_end,allowance,balance,created_at) VALUES(?,?,?,?,?,?)""",
        (uid,start.isoformat(),end.isoformat(),FREE_WEEKLY_CREDITS,FREE_WEEKLY_CREDITS,now.isoformat()))
    return dict(c.execute("SELECT * FROM credit_periods WHERE id=last_insert_rowid()").fetchone())

def credit_status(uid):
    u=get_user(uid)
    if not u: return None
    with conn() as c:
        c.execute('BEGIN IMMEDIATE'); row=_ensure_credit_period_locked(c,uid); c.commit()
    end=datetime.fromisoformat(row['period_end'])
    remaining=max(0,int((end-_credit_now()).total_seconds()))
    return {'period_id':row['id'],'period_start':row['period_start'],'period_end':row['period_end'],
            'allowance':int(row['allowance']),'remaining':int(row['balance']),'seconds_until_refresh':remaining}

def reserve_credit(uid, cost, operation, metadata=None):
    cost=int(cost)
    if cost<=0: return False,'هزینه اعتبار نامعتبر است.'
    with conn() as c:
        c.execute('BEGIN IMMEDIATE')
        u=c.execute('SELECT * FROM users WHERE user_id=?',(uid,)).fetchone()
        if not u: return False,'ابتدا /start را بزنید.'
        if int(u['blocked'] or 0): return False,'حساب شما مسدود است.'
        if active_subscription(dict(u)): return False,'subscription'
        row=_ensure_credit_period_locked(c,uid)
        if int(row['balance'])<cost: return False,'insufficient'
        ref=uuid.uuid4().hex; meta_text=None
        if metadata is not None:
            import json; meta_text=json.dumps(metadata,ensure_ascii=False,sort_keys=True)
        c.execute('UPDATE credit_periods SET balance=balance-? WHERE id=?',(cost,row['id']))
        c.execute("""INSERT INTO credit_ledger
            (user_id,period_id,reference_id,operation,cost,status,created_at,metadata)
            VALUES(?,?,?,?,?,?,?,?)""",(uid,row['id'],ref,operation,cost,'reserved',_credit_now().isoformat(),meta_text))
        c.commit(); return True,ref

def commit_credit(uid, reference_id):
    with conn() as c:
        cur=c.execute("UPDATE credit_ledger SET status='committed',finalized_at=? WHERE user_id=? AND reference_id=? AND status='reserved'",(_credit_now().isoformat(),uid,reference_id)); c.commit(); return cur.rowcount==1

def refund_credit(uid, reference_id):
    with conn() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute("SELECT * FROM credit_ledger WHERE user_id=? AND reference_id=? AND status='reserved'",(uid,reference_id)).fetchone()
        if not row: return False
        c.execute('UPDATE credit_periods SET balance=MIN(allowance,balance+?) WHERE id=?',(int(row['cost']),row['period_id']))
        c.execute("UPDATE credit_ledger SET status='refunded',finalized_at=? WHERE id=?",(_credit_now().isoformat(),row['id'])); c.commit(); return True

def month_key(): return datetime.now(timezone.utc).strftime('%Y-%m')
def now_iso(): return datetime.now(timezone.utc).isoformat()
def hash_value(v): return hashlib.sha256(v.encode()).hexdigest()
def get_user(uid):
    with conn() as c:
        r=c.execute('SELECT * FROM users WHERE user_id=?',(uid,)).fetchone(); return dict(r) if r else None

def register_user(uid, phone_hash, phone_last4, lawyer_code=None, full_name=''):
    if get_user(uid): return False,'شما قبلاً ثبت‌نام کرده‌اید.'
    code_hash=hash_value(lawyer_code) if lawyer_code else None
    with conn() as c:
        if c.execute('SELECT 1 FROM users WHERE phone_hash=?',(phone_hash,)).fetchone():
            return False,'این شماره قبلاً برای یک حساب ثبت شده است.'
        if code_hash and c.execute('SELECT 1 FROM users WHERE lawyer_code_hash=?',(code_hash,)).fetchone():
            return False,'این کد وکالت قبلاً ثبت شده است.'
        c.execute('INSERT INTO users(user_id,phone_hash,phone_last4,lawyer_code_hash,full_name,free_month,created_at) VALUES(?,?,?,?,?,?,?)',
                  (uid,phone_hash,phone_last4,code_hash,(full_name or '').strip(),month_key(),now_iso()))
    return True,f'ثبت‌نام با موفقیت انجام شد. {FREE_WEEKLY_CREDITS} اعتبار رایگان هفتگی برای شما فعال است.'

def set_lawyer_code(uid, lawyer_code):
    if not lawyer_code:
        return False, 'کد وکالت نامعتبر است.'
    code_hash=hash_value(lawyer_code.strip())
    with conn() as c:
        r=c.execute('SELECT user_id FROM users WHERE lawyer_code_hash=?',(code_hash,)).fetchone()
        if r and int(r['user_id']) != int(uid):
            return False, 'این کد وکالت قبلاً ثبت شده است.'
        cur=c.execute('UPDATE users SET lawyer_code_hash=? WHERE user_id=?',(code_hash,uid))
        if cur.rowcount != 1:
            return False, 'حساب کاربری پیدا نشد.'
        c.commit()
    return True, 'کد وکالت ثبت شد.'

def has_lawyer_code(uid):
    with conn() as c:
        r=c.execute('SELECT lawyer_code_hash FROM users WHERE user_id=?',(uid,)).fetchone()
        return bool(r and r['lawyer_code_hash'])

def active_subscription(u):
    if not u or not u.get('subscription_end'): return False
    try: return datetime.fromisoformat(u['subscription_end']) > datetime.now(timezone.utc)
    except: return False

def status(uid):
    u=get_user(uid)
    if not u:return None
    with conn() as c:
        m=month_key()
        if u['free_month']!=m:
            c.execute('UPDATE users SET free_month=?,free_used=0 WHERE user_id=?',(m,uid)); u['free_month']=m;u['free_used']=0
    ai_used=u.get('ai_used') or 0
    return {'active':active_subscription(u),
            'free_left':0 if active_subscription(u) else max(0,FREE_CASES-u['free_used']),
            'subscription_end':u['subscription_end'],
            'ai_left':max(0,AI_CASE_MONTHLY_LIMIT-ai_used)}

def reserve(uid):
    with conn() as c:
        c.execute('BEGIN IMMEDIATE')
        u=c.execute('SELECT * FROM users WHERE user_id=?',(uid,)).fetchone()
        if not u:return False,'ابتدا /start را بزنید.'
        u=dict(u)
        if u['blocked']:return False,'حساب شما مسدود است.'
        m=month_key()
        if u['free_month']!=m:
            c.execute('UPDATE users SET free_month=?,free_used=0 WHERE user_id=?',(m,uid));u['free_month']=m;u['free_used']=0
        if active_subscription(u):return True,'subscription'
        if u['free_used']>=FREE_CASES:return False,'سهمیه رایگان این ماه تمام شده است.'
        c.execute('UPDATE users SET free_used=free_used+1 WHERE user_id=?',(uid,))
    return True,'free'

def refund(uid, reservation_kind='free'):
    # Refund only the reservation that was actually consumed. This avoids a
    # race where an admin activates a subscription while a free job is running.
    if reservation_kind == 'free':
        with conn() as c:
            c.execute('UPDATE users SET free_used=MAX(0,free_used-1) WHERE user_id=?',(uid,))

def create_case(uid,name):
    with conn() as c:
        cur=c.execute('INSERT INTO cases(user_id,file_name,status,created_at,updated_at) VALUES(?,?,?,?,?)',(uid,name,'processing',now_iso(),now_iso())); return cur.lastrowid

def add_case_document(cid,file_name,page_count=0,extracted_text=''):
    with conn() as c:
        if not c.execute("SELECT 1 FROM cases WHERE id=? AND status!='archived'",(int(cid),)).fetchone():
            return None
        cur=c.execute('INSERT INTO case_documents(case_id,file_name,page_count,extracted_text,created_at) VALUES(?,?,?,?,?)',
                      (cid,file_name,int(page_count or 0),extracted_text or '',now_iso()))
        return cur.lastrowid

def set_case_document_storage(doc_id, uid, storage_path, file_size=0, sha256='', mime_type='', stored_at=None):
    with conn() as c:
        cur=c.execute("""UPDATE case_documents SET storage_path=?,file_size=?,sha256=?,mime_type=?,stored_at=?
            WHERE id=? AND EXISTS (SELECT 1 FROM cases WHERE cases.id=case_documents.case_id AND cases.user_id=? AND cases.status!='archived')""",
            (str(storage_path),int(file_size or 0),str(sha256 or ''),str(mime_type or ''),stored_at or now_iso(),int(doc_id),int(uid)))
        c.commit(); return cur.rowcount == 1

def set_case_version_storage(version_id, uid, storage_path, file_size=0, sha256='', mime_type='', stored_at=None):
    with conn() as c:
        cur=c.execute("""UPDATE case_versions SET storage_path=?,file_size=?,sha256=?,mime_type=?,stored_at=?
            WHERE id=? AND EXISTS (SELECT 1 FROM cases WHERE cases.id=case_versions.case_id AND cases.user_id=? AND cases.status!='archived')""",
            (str(storage_path),int(file_size or 0),str(sha256 or ''),str(mime_type or ''),stored_at or now_iso(),int(version_id),int(uid)))
        c.commit(); return cur.rowcount == 1

def archive_case(uid,cid):
    with conn() as c:
        row=c.execute("SELECT status FROM cases WHERE id=? AND user_id=?",(int(cid),int(uid))).fetchone()
        if not row or row['status']=='archived' or row['status']=='processing':
            return False
        source=row['status'] if row['status'] in {'completed','failed'} else 'completed'
        cur=c.execute("UPDATE cases SET status='archived',archived_at=?,archived_from_status=? WHERE id=? AND user_id=? AND status!='archived'",(now_iso(),source,int(cid),int(uid)))
        c.execute("UPDATE users SET active_case_id=NULL WHERE user_id=? AND active_case_id=?",(int(uid),int(cid)))
        c.commit(); return cur.rowcount == 1

def restore_case(uid,cid):
    with conn() as c:
        row=c.execute("SELECT archived_from_status FROM cases WHERE id=? AND user_id=? AND status='archived'",(int(cid),int(uid))).fetchone()
        if not row:
            return False
        source=row['archived_from_status'] if row['archived_from_status'] in {'completed','failed'} else 'completed'
        cur=c.execute("UPDATE cases SET status=?,archived_at=NULL,archived_from_status=NULL WHERE id=? AND user_id=? AND status='archived'",(source,int(cid),int(uid)))
        c.commit(); return cur.rowcount == 1

def delete_case(uid,cid):
    """Permanently delete one owned case and every known case-scoped record.

    File cleanup is staged before the DB commit so a filesystem failure cannot
    leave a live DB record pointing at partially deleted case files.
    """
    import shutil, uuid
    from .config import CASE_STORAGE_DIR
    cid=int(cid); uid=int(uid)
    case_dir=Path(CASE_STORAGE_DIR)/str(cid)
    staged_dir=None

    # Verify ownership before touching any filesystem path derived from a
    # callback-provided case id.
    with conn() as c:
        if not c.execute('SELECT 1 FROM cases WHERE id=? AND user_id=?',(cid,uid)).fetchone():
            return False

    # Stage the durable case directory on the same filesystem. If the directory
    # is absent, deletion can proceed; if staging fails, keep the case intact.
    if case_dir.exists() or case_dir.is_symlink():
        if not case_dir.is_dir() and not case_dir.is_symlink():
            return False
        staged_dir=Path(CASE_STORAGE_DIR)/f'.deleting_{cid}_{uuid.uuid4().hex[:12]}'
        try:
            case_dir.rename(staged_dir)
        except OSError:
            return False

    try:
        with conn() as c:
            c.execute('PRAGMA foreign_keys=ON')
            if not c.execute('SELECT 1 FROM cases WHERE id=? AND user_id=?',(cid,uid)).fetchone():
                raise RuntimeError('case disappeared before deletion')

            if _table_exists(c,'case_date_reminders'):
                c.execute('DELETE FROM case_date_reminders WHERE case_date_id IN (SELECT id FROM case_important_dates WHERE case_id=?)',(cid,))

            # Keep this list explicit: these are the case-owned stores currently
            # used by the product, including workspace and durable drafting data.
            for table in (
                'case_important_dates','case_ai_history','case_lawyer_notes',
                'case_versions','case_documents','case_additions',
                'case_events','case_tasks','drafting_workflow_sessions',
                'tasks','client_case_links'
            ):
                if not _table_exists(c,table):
                    continue
                if table in {'tasks','case_events','case_tasks','drafting_workflow_sessions'}:
                    c.execute(f'DELETE FROM {table} WHERE user_id=? AND case_id=?',(uid,cid))
                elif table=='client_case_links':
                    c.execute('DELETE FROM client_case_links WHERE user_id=? AND case_id=?',(uid,cid))
                else:
                    c.execute(f'DELETE FROM {table} WHERE case_id=?',(cid,))

            c.execute('UPDATE users SET active_case_id=NULL WHERE user_id=? AND active_case_id=?',(uid,cid))
            cur=c.execute('DELETE FROM cases WHERE id=? AND user_id=?',(cid,uid))
            if cur.rowcount != 1:
                raise RuntimeError('case deletion affected an unexpected number of rows')
            c.commit()
    except Exception:
        if staged_dir and staged_dir.exists() and not case_dir.exists():
            try:
                staged_dir.rename(case_dir)
            except OSError:
                pass
        return False

    # DB deletion is committed; now permanently remove the staged files.
    if staged_dir and staged_dir.exists():
        try:
            if staged_dir.is_symlink():
                staged_dir.unlink()
            else:
                shutil.rmtree(staged_dir)
        except OSError:
            # The DB record is already gone. Leave a clearly marked orphan for
            # a later storage cleanup job rather than pretending deletion failed.
            return True
    return True

def delete_user(uid):
    """Permanently delete all user-owned application data and case files."""
    import shutil
    from .config import CASE_STORAGE_DIR
    with conn() as c:
        c.execute('PRAGMA foreign_keys=ON')
        if not c.execute('SELECT 1 FROM users WHERE user_id=?',(int(uid),)).fetchone(): return False
        case_ids=[r[0] for r in c.execute('SELECT id FROM cases WHERE user_id=?',(int(uid),)).fetchall()]
        if _table_exists(c,'case_date_reminders'):
            c.execute('DELETE FROM case_date_reminders WHERE case_date_id IN (SELECT id FROM case_important_dates WHERE user_id=?)',(int(uid),))
        listing_ids=[r[0] for r in c.execute('SELECT id FROM service_listings WHERE user_id=?',(int(uid),)).fetchall()] if _table_exists(c,'service_listings') else []
        referral_ids=[r[0] for r in c.execute('SELECT id FROM referral_requests WHERE client_user_id=?',(int(uid),)).fetchall()] if _table_exists(c,'referral_requests') else []
        if _table_exists(c,'referral_matches'):
            if listing_ids:
                marks=','.join('?'*len(listing_ids)); c.execute(f'DELETE FROM referral_matches WHERE listing_id IN ({marks}) OR lawyer_user_id=?',(*listing_ids,int(uid)))
            else: c.execute('DELETE FROM referral_matches WHERE lawyer_user_id=?',(int(uid),))
            if referral_ids:
                marks=','.join('?'*len(referral_ids)); c.execute(f'DELETE FROM referral_matches WHERE referral_id IN ({marks})',tuple(referral_ids))
        if _table_exists(c,'referral_events'):
            if referral_ids:
                marks=','.join('?'*len(referral_ids)); c.execute(f'DELETE FROM referral_events WHERE referral_id IN ({marks}) OR actor_user_id=?',(*referral_ids,int(uid)))
            else: c.execute('DELETE FROM referral_events WHERE actor_user_id=?',(int(uid),))
        if _table_exists(c,'referral_requests'):
            c.execute('UPDATE referral_requests SET assigned_listing_id=NULL WHERE assigned_listing_id IN (SELECT id FROM service_listings WHERE user_id=?)',(int(uid),))
            c.execute('DELETE FROM referral_requests WHERE client_user_id=?',(int(uid),))
        for table in ('case_important_dates','case_ai_history','case_lawyer_notes'):
            if _table_exists(c,table): c.execute(f'DELETE FROM {table} WHERE user_id=?',(int(uid),))
        for table in ('case_versions','case_documents','case_additions'):
            if _table_exists(c,table): c.execute(f'DELETE FROM {table} WHERE case_id IN (SELECT id FROM cases WHERE user_id=?)',(int(uid),))
        for table in ('user_tasks','tasks'):
            if _table_exists(c,table): c.execute(f'DELETE FROM {table} WHERE user_id=?',(int(uid),))
        if _table_exists(c,'client_case_links'): c.execute('DELETE FROM client_case_links WHERE user_id=?',(int(uid),))
        for table in ('clients','feedback','service_listings','payment_requests','payments','subscriptions','ai_question_quota','free_entitlements'):
            if _table_exists(c,table): c.execute(f'DELETE FROM {table} WHERE user_id=?',(int(uid),))
        c.execute('DELETE FROM cases WHERE user_id=?',(int(uid),))
        c.execute('DELETE FROM users WHERE user_id=?',(int(uid),))
        c.commit()
    for cid in case_ids: shutil.rmtree(Path(CASE_STORAGE_DIR)/str(cid), ignore_errors=True)
    return True

def list_archived_cases(uid, limit=50):
    with conn() as c:
        rows=c.execute("SELECT * FROM cases WHERE user_id=? AND status='archived' ORDER BY id DESC LIMIT ?",(int(uid),int(limit))).fetchall()
        return [dict(r) for r in rows]

def count_case_additions(uid,cid):
    with conn() as c:
        r=c.execute('''SELECT COUNT(*) AS n FROM case_additions a JOIN cases c ON c.id=a.case_id
                       WHERE a.case_id=? AND c.user_id=?''',(cid,uid)).fetchone()
        return int(r['n'] or 0)

def start_case_addition(uid,cid):
    with conn() as c:
        c.execute('BEGIN IMMEDIATE')
        r=c.execute("SELECT COALESCE(MAX(a.addition_no),0)+1 AS n FROM case_additions a JOIN cases c ON c.id=a.case_id WHERE a.case_id=? AND c.user_id=? AND c.status!='archived'",(cid,uid)).fetchone()
        n=int(r['n'])
        if not c.execute("SELECT 1 FROM cases WHERE id=? AND user_id=? AND status!='archived'",(int(cid),int(uid))).fetchone():
            c.rollback(); return None, None
        cur=c.execute('INSERT INTO case_additions(case_id,addition_no,file_count,created_at) VALUES(?,?,0,?)',(cid,n,now_iso()))
        c.commit()
        return cur.lastrowid,n

def get_case_addition_file_count(uid,cid,addition_no):
    with conn() as c:
        r=c.execute('''SELECT a.file_count FROM case_additions a JOIN cases c ON c.id=a.case_id
                       WHERE a.case_id=? AND a.addition_no=? AND c.user_id=?''',(cid,addition_no,uid)).fetchone()
        return int(r['file_count'] or 0) if r else 0

def increment_case_addition_files(uid,cid,addition_no,amount=1):
    with conn() as c:
        cur=c.execute('''UPDATE case_additions SET file_count=file_count+?
                         WHERE case_id=? AND addition_no=? AND EXISTS
                         (SELECT 1 FROM cases WHERE cases.id=? AND cases.user_id=? AND cases.status!='archived')''',(int(amount),cid,addition_no,cid,uid))
        c.commit()
        return cur.rowcount == 1

def delete_case_addition(uid,cid,addition_no):
    with conn() as c:
        cur=c.execute('''DELETE FROM case_additions
                       WHERE case_id=? AND addition_no=? AND EXISTS
                       (SELECT 1 FROM cases WHERE cases.id=? AND cases.user_id=?)''',
                      (int(cid), int(addition_no), int(cid), int(uid)))
        c.commit()
        return cur.rowcount == 1

def finish_case(cid,result):
    with conn() as c:c.execute('UPDATE cases SET status=?,result=? WHERE id=?',('completed',result,cid))
def fail_case(cid,msg):
    with conn() as c:c.execute('UPDATE cases SET status=?,result=? WHERE id=?',('failed',msg,cid))
def list_cases(uid,limit=10):
    return list_cases_numbered(uid,limit)
def get_case(uid,cid):
    with conn() as c:
        r=c.execute('SELECT * FROM cases WHERE id=? AND user_id=?',(cid,uid)).fetchone();return dict(r) if r else None



def set_active_case(uid, cid):
    """Persist the user's currently active case; None means no active case."""
    if cid is not None and not get_case(uid, int(cid)):
        return False
    with conn() as c:
        cur=c.execute('UPDATE users SET active_case_id=? WHERE user_id=?',(cid,uid))
        c.commit()
        return cur.rowcount == 1

def get_active_case_id(uid):
    with conn() as c:
        r=c.execute('SELECT active_case_id FROM users WHERE user_id=?',(uid,)).fetchone()
        return int(r['active_case_id']) if r and r['active_case_id'] is not None else None

def clear_active_case(uid):
    return set_active_case(uid, None)

def get_case_documents(uid,cid):
    with conn() as c:
        rows=c.execute("""SELECT d.* FROM case_documents d
            JOIN cases c ON c.id=d.case_id
            WHERE c.id=? AND c.user_id=? ORDER BY d.id ASC""",(cid,uid)).fetchall()
        return [dict(r) for r in rows]

def get_case_original_text(uid,cid):
    """Return only the primary/original case document text.

    Later attachments are intentionally excluded from version comparison so
    "نسخه اصلی" remains stable even after the lawyer adds new evidence.
    """
    with conn() as c:
        r=c.execute("""SELECT d.extracted_text, d.page_count
            FROM case_documents d JOIN cases c ON c.id=d.case_id
            WHERE d.case_id=? AND c.user_id=? ORDER BY d.id ASC LIMIT 1""",
            (int(cid),int(uid))).fetchone()
        return (r['extracted_text'] or '').strip() if r else ''


def get_case_text(uid,cid):
    docs=get_case_documents(uid,cid)
    chunks=[]
    for d in docs:
        text=(d.get('extracted_text') or '').strip()
        if not text:
            continue
        # PDF extraction already stores authoritative page markers such as
        # [صفحه 1]. Do not wrap the whole document in another fake page marker;
        # that would confuse full-text search and page provenance.
        if re.search(r'(?m)^\s*\[صفحه\s+\d+\]', text):
            chunks.append(text)
        else:
            page_count=int(d.get('page_count') or 1)
            if page_count <= 1:
                chunks.append(text)
            else:
                # Legacy records without page markers: preserve the text and
                # avoid inventing page boundaries. Search can still find it.
                chunks.append(text)
    return '\n\n'.join(chunks).strip()

def count_case_versions(uid,cid):
    with conn() as c:
        r=c.execute('''SELECT COUNT(*) AS n FROM case_versions v JOIN cases c ON c.id=v.case_id WHERE v.case_id=? AND c.user_id=?''',(cid,uid)).fetchone()
        return int(r['n'] or 0)

def add_case_version(uid,cid,file_name,page_count=0,extracted_text=''):
    case=get_case(uid,cid)
    if not case or case.get('status')=='archived':
        return None, None
    with conn() as c:
        r=c.execute('SELECT COALESCE(MAX(version_no),0)+1 AS n FROM case_versions WHERE case_id=?',(cid,)).fetchone()
        n=int(r['n'] or 1)
        cur=c.execute('INSERT INTO case_versions(case_id,version_no,file_name,page_count,extracted_text,created_at) VALUES(?,?,?,?,?,?)',
                      (cid,n,file_name,int(page_count or 0),extracted_text or '',now_iso()))
        return cur.lastrowid,n

def get_case_versions(uid,cid):
    with conn() as c:
        rows=c.execute('''SELECT v.* FROM case_versions v JOIN cases c ON c.id=v.case_id
            WHERE v.case_id=? AND c.user_id=? ORDER BY v.version_no ASC''',(cid,uid)).fetchall()
        return [dict(r) for r in rows]

def delete_case_version(uid,cid,version_id):
    """Compensating delete for a version that failed durable registration."""
    with conn() as c:
        cur=c.execute("DELETE FROM case_versions WHERE id=? AND case_id=? AND EXISTS (SELECT 1 FROM cases WHERE cases.id=? AND cases.user_id=?)",
                      (int(version_id),int(cid),int(cid),int(uid)))
        c.commit()
        return cur.rowcount == 1


def get_case_version(uid,cid,version_no):
    with conn() as c:
        r=c.execute('''SELECT v.* FROM case_versions v JOIN cases c ON c.id=v.case_id
            WHERE v.case_id=? AND v.version_no=? AND c.user_id=?''',(cid,version_no,uid)).fetchone()
        return dict(r) if r else None


def get_case_lawyer_note(uid, cid):
    with conn() as c:
        r=c.execute("SELECT n.* FROM case_lawyer_notes n JOIN cases c ON c.id=n.case_id WHERE n.case_id=? AND c.user_id=?",(cid,uid)).fetchone()
        return dict(r) if r else None

def save_case_lawyer_note(uid, cid, note_text):
    case=get_case(uid, cid)
    if not case or case.get('status')=='archived':
        return False
    with conn() as c:
        c.execute("INSERT INTO case_lawyer_notes(case_id,user_id,note_text,updated_at) VALUES(?,?,?,?) ON CONFLICT(case_id) DO UPDATE SET note_text=excluded.note_text,user_id=excluded.user_id,updated_at=excluded.updated_at",
                  (cid,uid,note_text,now_iso()))
        c.commit()
        return True

def clear_case_lawyer_note(uid, cid):
    # Keep archived cases read-only even when this helper is called outside the API.
    case = get_case(uid, cid)
    if not case or case.get('status') == 'archived':
        return False
    with conn() as c:
        cur=c.execute('DELETE FROM case_lawyer_notes WHERE case_id=? AND user_id=?',(cid,uid))
        c.commit()
        return cur.rowcount > 0

def list_cases_numbered(uid,limit=20):
    with conn() as c:
        rows=c.execute("""SELECT c.*,
            (SELECT COUNT(*) FROM cases c2
             WHERE c2.user_id=c.user_id AND c2.id<=c.id) AS case_no
            FROM cases c WHERE c.user_id=? AND COALESCE(c.status,'')!='archived' ORDER BY c.id DESC LIMIT ?""",(uid,limit)).fetchall()
        return [dict(r) for r in rows]

def grant(uid,days=30):
    u=get_user(uid)
    if not u:return False,'کاربر پیدا نشد.',None
    now=datetime.now(timezone.utc)
    try: old=datetime.fromisoformat(u['subscription_end']) if u['subscription_end'] else None
    except: old=None
    base=old if old and old>now else now
    end=base+timedelta(days=days)
    with conn() as c:c.execute('UPDATE users SET subscription_end=? WHERE user_id=?',(end.isoformat(),uid))
    return True,f'اشتراک تا {end.astimezone().strftime("%Y/%m/%d %H:%M")} فعال شد.',end

def revoke(uid):
    with conn() as c:
        cur=c.execute('UPDATE users SET subscription_end=NULL WHERE user_id=?',(uid,));return cur.rowcount>0

def add_payment(uid):
    with conn() as c:
        if c.execute('SELECT 1 FROM payments WHERE user_id=? AND status="pending" LIMIT 1',(uid,)).fetchone():
            return None
        cur=c.execute('INSERT INTO payments(user_id,status,created_at) VALUES(?,?,?)',(uid,'pending',now_iso()))
        return cur.lastrowid

def pending_payment(pid):
    with conn() as c:return c.execute('SELECT * FROM payments WHERE id=? AND status="pending"',(pid,)).fetchone()

def has_pending_payment(uid):
    with conn() as c:
        return c.execute('SELECT 1 FROM payments WHERE user_id=? AND status="pending" LIMIT 1',(uid,)).fetchone() is not None
def approve_payment(pid):
    with conn() as c:
        cur=c.execute('UPDATE payments SET status="approved" WHERE id=? AND status="pending"',(pid,))
        return cur.rowcount>0


def reject_payment(pid):
    with conn() as c:
        cur=c.execute('UPDATE payments SET status="rejected" WHERE id=? AND status="pending"',(pid,))
        return cur.rowcount>0

# V20 additions: small-scale production hardening for ~500 users.
def _ensure_column(c, table, column, definition):
    cols={r[1] for r in c.execute(f'PRAGMA table_info({table})').fetchall()}
    if column not in cols: c.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')

def v193_upgrade():
    """Lawyer-only registration profile fields; safe and repeatable."""
    with conn() as c:
        _ensure_column(c, 'users', 'full_name', "TEXT NOT NULL DEFAULT ''")
        c.commit()

def v20_upgrade():
    with conn() as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.execute('PRAGMA synchronous=NORMAL')
        c.execute('PRAGMA foreign_keys=ON')
        _ensure_column(c,'users','active_case_id','INTEGER')
        _ensure_column(c,'users','ai_month','TEXT')
        _ensure_column(c,'users','ai_used','INTEGER NOT NULL DEFAULT 0')
        _ensure_column(c,'case_documents','extracted_text','TEXT')
        c.execute('''CREATE TABLE IF NOT EXISTS feedback(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,kind TEXT NOT NULL,message TEXT,context TEXT,created_at TEXT NOT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,case_id INTEGER, title TEXT NOT NULL,due_at TEXT,done INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL)''')
        c.execute('CREATE INDEX IF NOT EXISTS idx_cases_user_created ON cases(user_id,created_at DESC)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_docs_case ON case_documents(case_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_versions_case ON case_versions(case_id,version_no)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_case_notes_user ON case_lawyer_notes(user_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_case_additions_case ON case_additions(case_id,addition_no)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_tasks_user_done_due ON tasks(user_id,done,due_at)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_feedback_user_created ON feedback(user_id,created_at DESC)')

def _table_exists(c, name):
    return c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None

def v67_upgrade():
    """V67 schema migration; safe to run repeatedly."""
    with conn() as c:
        _ensure_column(c, 'cases', 'archived_at', 'TEXT')
        _ensure_column(c, 'cases', 'archived_from_status', 'TEXT')
        for col, definition in (
            ('storage_path','TEXT'), ('file_size','INTEGER NOT NULL DEFAULT 0'),
            ('sha256','TEXT'), ('mime_type','TEXT'), ('stored_at','TEXT')):
            _ensure_column(c, 'case_documents', col, definition)
            _ensure_column(c, 'case_versions', col, definition)
        c.execute('CREATE INDEX IF NOT EXISTS idx_cases_user_status ON cases(user_id,status)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_docs_storage_path ON case_documents(storage_path)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_versions_storage_path ON case_versions(storage_path)')
        c.commit()

# --- V128 case workspace: durable case metadata, timeline, and case tasks ---
def init_case_workspace_tables():
    with conn() as c:
        _ensure_column(c, 'cases', 'stage', "TEXT NOT NULL DEFAULT 'new'")
        _ensure_column(c, 'cases', 'priority', "TEXT NOT NULL DEFAULT 'normal'")
        _ensure_column(c, 'cases', 'next_action', "TEXT NOT NULL DEFAULT ''")
        _ensure_column(c, 'cases', 'updated_at', 'TEXT')
        c.execute("UPDATE cases SET updated_at=COALESCE(updated_at,created_at)")
        c.execute("""CREATE TABLE IF NOT EXISTS case_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, case_id INTEGER NOT NULL,
            event_type TEXT NOT NULL, title TEXT NOT NULL, details TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id), FOREIGN KEY(case_id) REFERENCES cases(id) ON DELETE CASCADE)""")
        c.execute('CREATE INDEX IF NOT EXISTS idx_case_events_case ON case_events(case_id,created_at DESC,id DESC)')
        c.execute("""CREATE TABLE IF NOT EXISTS lawyer_recent_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, case_id INTEGER NOT NULL,
            activity_type TEXT NOT NULL, created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id),
            FOREIGN KEY(case_id) REFERENCES cases(id) ON DELETE CASCADE)""")
        c.execute('CREATE INDEX IF NOT EXISTS idx_recent_activity_user_created ON lawyer_recent_activity(user_id,created_at DESC,id DESC)')
        c.execute("""CREATE TABLE IF NOT EXISTS lawyer_saved_documents (
            user_id INTEGER NOT NULL, case_id INTEGER NOT NULL, document_id INTEGER NOT NULL,
            created_at TEXT NOT NULL, PRIMARY KEY(user_id,case_id,document_id),
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            FOREIGN KEY(case_id) REFERENCES cases(id) ON DELETE CASCADE,
            FOREIGN KEY(document_id) REFERENCES case_documents(id) ON DELETE CASCADE)""")
        c.execute('CREATE INDEX IF NOT EXISTS idx_saved_documents_user_created ON lawyer_saved_documents(user_id,created_at DESC)')
        c.execute("""CREATE TABLE IF NOT EXISTS case_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, case_id INTEGER NOT NULL,
            title TEXT NOT NULL, due_at TEXT, done INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, completed_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(user_id), FOREIGN KEY(case_id) REFERENCES cases(id) ON DELETE CASCADE)""")
        _ensure_column(c, 'case_tasks', 'reminder_days', 'INTEGER')
        _ensure_column(c, 'case_tasks', 'reminder_sent_at', 'TEXT')
        c.execute('CREATE INDEX IF NOT EXISTS idx_case_tasks_case ON case_tasks(case_id,done,due_at,id DESC)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_case_tasks_user ON case_tasks(user_id,done,due_at)')
        c.commit()

def _case_touch(c, cid):
    c.execute('UPDATE cases SET updated_at=? WHERE id=?', (now_iso(), int(cid)))

def add_case_event(uid, cid, event_type, title, details=''):
    init_case_workspace_tables()
    with conn() as c:
        if not c.execute("SELECT 1 FROM cases WHERE id=? AND user_id=? AND status!='archived'",(int(cid),int(uid))).fetchone(): return False
        c.execute('INSERT INTO case_events(user_id,case_id,event_type,title,details,created_at) VALUES(?,?,?,?,?,?)',(int(uid),int(cid),str(event_type),str(title)[:200],str(details or '')[:4000],now_iso()))
        _case_touch(c,cid); c.commit(); return True

def list_case_events(uid, cid, limit=50):
    init_case_workspace_tables()
    with conn() as c:
        rows=c.execute('SELECT * FROM case_events WHERE user_id=? AND case_id=? ORDER BY created_at DESC,id DESC LIMIT ?',(int(uid),int(cid),int(limit))).fetchall()
        return [dict(r) for r in rows]

RECENT_ACTIVITY_LABELS = {
    'case_opened': 'پرونده را باز کرد',
    'documents_opened': 'اسناد پرونده را مشاهده کرد',
    'drafts_opened': 'بخش پیش‌نویس‌ها را باز کرد',
    'timeline_opened': 'خط زمانی پرونده را مشاهده کرد',
    'ai_opened': 'بخش دستیار هوشمند را باز کرد',
    'ai_used': 'از دستیار هوشمند پرسید',
    'draft_created': 'پیش‌نویس جدید ساخت',
}


def record_recent_activity(uid, case_id, activity_type):
    # Store only a minimal navigation/action marker; never store case text.
    activity_type = str(activity_type or '')
    if activity_type not in RECENT_ACTIVITY_LABELS:
        return False
    with conn() as c:
        owned = c.execute("SELECT 1 FROM cases WHERE id=? AND user_id=? AND status!='archived'",
                          (int(case_id), int(uid))).fetchone()
        if not owned:
            return False
        c.execute('INSERT INTO lawyer_recent_activity(user_id,case_id,activity_type,created_at) VALUES(?,?,?,?)',
                  (int(uid), int(case_id), activity_type, now_iso()))
        c.execute("DELETE FROM lawyer_recent_activity WHERE user_id=? AND id NOT IN (SELECT id FROM lawyer_recent_activity WHERE user_id=? ORDER BY created_at DESC,id DESC LIMIT 60)",
                  (int(uid), int(uid)))
        c.commit()
        return True


def list_recent_activity(uid, limit=8):
    limit = max(1, min(int(limit), 20))
    with conn() as c:
        rows = c.execute("SELECT a.id,a.case_id,a.activity_type,a.created_at,c.file_name AS case_name,c.status AS case_status FROM lawyer_recent_activity a JOIN cases c ON c.id=a.case_id WHERE a.user_id=? AND c.user_id=? AND c.status!='archived' ORDER BY a.created_at DESC,a.id DESC LIMIT ?",
                         (int(uid), int(uid), limit)).fetchall()
        items=[]
        for row in rows:
            item=dict(row)
            item['title']=RECENT_ACTIVITY_LABELS.get(item['activity_type'],'فعالیت پرونده')
            items.append(item)
        return items


def update_case_workspace(uid, cid, stage=None, priority=None, next_action=None):
    init_case_workspace_tables()
    with conn() as c:
        current=c.execute("SELECT stage,priority,next_action,status FROM cases WHERE id=? AND user_id=?",(int(cid),int(uid))).fetchone()
        if not current or current['status']=='archived': return False
        stage=current['stage'] if stage is None else str(stage).strip()[:80]
        priority=current['priority'] if priority is None else str(priority).strip()[:30]
        next_action=current['next_action'] if next_action is None else str(next_action).strip()[:1000]
        c.execute('UPDATE cases SET stage=?,priority=?,next_action=?,updated_at=? WHERE id=? AND user_id=?',(stage or 'new',priority or 'normal',next_action,now_iso(),int(cid),int(uid)))
        c.execute('INSERT INTO case_events(user_id,case_id,event_type,title,details,created_at) VALUES(?,?,?,?,?,?)',(int(uid),int(cid),'workspace_updated','به‌روزرسانی وضعیت پرونده',f'مرحله: {stage}\nاولویت: {priority}\nاقدام بعدی: {next_action or "—"}',now_iso()))
        c.commit(); return True

def add_case_task(uid, cid, title, due_at=None, reminder_days=None):
    init_case_workspace_tables(); title=str(title or '').strip()[:500]
    if not title: return None
    with conn() as c:
        if not c.execute("SELECT 1 FROM cases WHERE id=? AND user_id=? AND status!='archived'",(int(cid),int(uid))).fetchone(): return None
        reminder_days = int(reminder_days) if reminder_days is not None and due_at else None
        if reminder_days not in (None, 0, 1, 3, 7): raise ValueError('بازه یادآوری معتبر نیست.')
        cur=c.execute('INSERT INTO case_tasks(user_id,case_id,title,due_at,created_at,reminder_days,reminder_sent_at) VALUES(?,?,?,?,?,?,NULL)',(int(uid),int(cid),title,due_at,now_iso(),reminder_days))
        _case_touch(c,cid)
        c.execute('INSERT INTO case_events(user_id,case_id,event_type,title,details,created_at) VALUES(?,?,?,?,?,?)',(int(uid),int(cid),'task_created','کار جدید ایجاد شد',title,now_iso()))
        c.commit(); return cur.lastrowid

def list_case_tasks(uid, cid, include_done=False, limit=50):
    init_case_workspace_tables(); sql='SELECT * FROM case_tasks WHERE user_id=? AND case_id=?'; args=[int(uid),int(cid)]
    if not include_done: sql += ' AND done=0'
    sql += ' ORDER BY done ASC, CASE WHEN due_at IS NULL THEN 1 ELSE 0 END, due_at ASC, id DESC LIMIT ?'; args.append(int(limit))
    with conn() as c: return [dict(r) for r in c.execute(sql,args).fetchall()]

def list_user_calendar_items(uid, start_date=None, end_date=None, limit=500):
    """Return owned case tasks and extracted case dates for one calendar range."""
    init_case_workspace_tables(); init_case_dates_table(); init_case_reminders_table(); init_tasks_table()
    start_date = str(start_date or '1900-01-01')[:10]
    end_date = str(end_date or '2999-12-31')[:10]
    limit = max(1, min(int(limit), 1000))
    with conn() as c:
        tasks = c.execute("""SELECT t.id,t.case_id,t.title,t.due_at,t.done,t.created_at,
                c.file_name AS case_name,'task' AS item_type
            FROM case_tasks t JOIN cases c ON c.id=t.case_id
            WHERE t.user_id=? AND c.user_id=? AND c.status!='archived'
              AND t.due_at IS NOT NULL AND substr(t.due_at,1,10)>=? AND substr(t.due_at,1,10)<=?
            ORDER BY t.due_at ASC,t.id DESC LIMIT ?""",
            (int(uid),int(uid),start_date,end_date,limit)).fetchall()
        dates = c.execute("""SELECT d.id,d.case_id,d.description AS title,d.date_gregorian AS due_at,
                0 AS done,d.created_at,c.file_name AS case_name,'case_date' AS item_type,
                d.date_jalali,d.source_page,d.source_text,
                EXISTS(SELECT 1 FROM case_date_reminders r WHERE r.case_date_id=d.id AND r.user_id=? AND r.enabled=1) AS reminder_enabled
            FROM case_important_dates d JOIN cases c ON c.id=d.case_id
            WHERE d.user_id=? AND c.user_id=? AND c.status!='archived'
              AND d.date_gregorian>=? AND d.date_gregorian<=?
            ORDER BY d.date_gregorian ASC,d.id DESC LIMIT ?""",
            (int(uid),int(uid),int(uid),start_date,end_date,limit)).fetchall()
        global_tasks = c.execute("""SELECT id,NULL AS case_id,title,due_at,done,created_at,
                'کارهای من' AS case_name,'user_task' AS item_type
            FROM user_tasks WHERE user_id=? AND due_at IS NOT NULL
              AND substr(due_at,1,10)>=? AND substr(due_at,1,10)<=?
            ORDER BY due_at ASC,id DESC LIMIT ?""",
            (int(uid),start_date,end_date,limit)).fetchall()
    items=[dict(r) for r in tasks]+[dict(r) for r in dates]+[dict(r) for r in global_tasks]
    items.sort(key=lambda x:(str(x.get('due_at') or '')[:10], 0 if x.get('item_type')=='case_date' else 1, int(x.get('id') or 0)))
    return items[:limit]

def set_case_task_done(uid, task_id, done=True, case_id=None):
    init_case_workspace_tables()
    with conn() as c:
        sql = "SELECT t.case_id,t.title FROM case_tasks t JOIN cases c ON c.id=t.case_id WHERE t.id=? AND t.user_id=? AND c.status!='archived'"
        args = [int(task_id), int(uid)]
        if case_id is not None:
            sql += " AND t.case_id=?"
            args.append(int(case_id))
        row=c.execute(sql, tuple(args)).fetchone()
        if not row: return False
        c.execute('UPDATE case_tasks SET done=?,completed_at=? WHERE id=? AND user_id=?',(1 if done else 0,now_iso() if done else None,int(task_id),int(uid)))
        _case_touch(c,row['case_id'])
        c.execute('INSERT INTO case_events(user_id,case_id,event_type,title,details,created_at) VALUES(?,?,?,?,?,?)',(int(uid),int(row['case_id']),'task_done' if done else 'task_reopened','کار پرونده تغییر وضعیت داد',row['title'],now_iso()))
        c.commit(); return True

def delete_case_task(uid, task_id, case_id=None):
    init_case_workspace_tables()
    with conn() as c:
        sql = "SELECT t.case_id,t.title FROM case_tasks t JOIN cases c ON c.id=t.case_id WHERE t.id=? AND t.user_id=? AND c.status!='archived'"
        args = [int(task_id), int(uid)]
        if case_id is not None:
            sql += " AND t.case_id=?"
            args.append(int(case_id))
        row=c.execute(sql, tuple(args)).fetchone()
        if not row: return False
        c.execute('DELETE FROM case_tasks WHERE id=? AND user_id=?',(int(task_id),int(uid)))
        _case_touch(c,row['case_id'])
        c.execute('INSERT INTO case_events(user_id,case_id,event_type,title,details,created_at) VALUES(?,?,?,?,?,?)',(int(uid),int(row['case_id']),'task_deleted','کار پرونده حذف شد',row['title'],now_iso()))
        c.commit(); return True

def case_workspace(uid, cid):
    init_case_workspace_tables(); case=get_case(uid,cid)
    if not case: return None
    docs=get_case_documents(uid,cid); versions=get_case_versions(uid,cid); tasks=list_case_tasks(uid,cid,False,20)
    dates=[x for x in list_case_important_dates(uid,200) if int(x['case_id'])==int(cid)][:8]
    with conn() as c:
        if _table_exists(c,'clients'):
            rows=c.execute("""SELECT cl.name FROM clients cl JOIN client_case_links l ON l.client_id=cl.id
                              WHERE l.case_id=? AND l.user_id=? ORDER BY cl.name""",(int(cid),int(uid))).fetchall()
        else: rows=[]
        client_names=[r['name'] for r in rows]
    return {'case':case,'document_count':len(docs),'version_count':len(versions),'open_tasks':len(tasks),'important_dates':dates,'clients':client_names}

def ai_month_key(): return month_key()
def reserve_ai(uid, limit):
    if limit<=0:return False,'سهمیه AI متنی فعال نیست.'
    with conn() as c:
        c.execute('BEGIN IMMEDIATE'); u=c.execute('SELECT * FROM users WHERE user_id=?',(uid,)).fetchone()
        if not u:return False,'ابتدا ثبت‌نام کنید.'
        m=ai_month_key()
        if u['ai_month']!=m:
            c.execute('UPDATE users SET ai_month=?,ai_used=0 WHERE user_id=?',(m,uid)); used=0
        else: used=u['ai_used'] or 0
        if used>=limit:return False,'سهمیه AI متنی این ماه تمام شده است.'
        c.execute('UPDATE users SET ai_used=ai_used+1 WHERE user_id=?',(uid,)); return True,'ai'

def refund_ai(uid):
    with conn() as c:
        c.execute('UPDATE users SET ai_used=MAX(0,COALESCE(ai_used,0)-1) WHERE user_id=?',(uid,))

def add_feedback(uid,kind,message='',context=''):
    with conn() as c:
        c.execute('INSERT INTO feedback(user_id,kind,message,context,created_at) VALUES(?,?,?,?,?)',(uid,kind,message[:4000],context[:1000],now_iso()))

def init_case_dates_table():
    with conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS case_important_dates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            case_id INTEGER NOT NULL,
            date_jalali TEXT NOT NULL,
            date_gregorian TEXT NOT NULL,
            description TEXT NOT NULL,
            source_page INTEGER,
            source_text TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(case_id, date_gregorian, description, source_page)
        )""")
        c.execute('CREATE INDEX IF NOT EXISTS idx_case_dates_user_date ON case_important_dates(user_id, date_gregorian)')
        c.commit()

def add_case_important_dates(uid, cid, dates):
    init_case_dates_table()
    inserted=0
    with conn() as c:
        if not c.execute("SELECT 1 FROM cases WHERE id=? AND user_id=? AND status!='archived'",(int(cid),int(uid))).fetchone():
            return 0
        for d in dates or []:
            try:
                cur=c.execute("""INSERT OR IGNORE INTO case_important_dates
                    (user_id,case_id,date_jalali,date_gregorian,description,source_page,source_text,created_at)
                    VALUES(?,?,?,?,?,?,?,?)""", (uid,cid,d['date_jalali'],d['date_gregorian'],d['description'],d.get('source_page'),d.get('source_text','')[:1000],now_iso()))
                inserted += cur.rowcount
            except Exception:
                continue
        c.commit()
    return inserted

def list_case_important_dates(uid, limit=80):
    init_case_dates_table()
    # V67: past dates remain part of case history. Only reminder rows expire.
    with conn() as c:
        rows=c.execute("""SELECT d.*, c.file_name,
                (SELECT COUNT(*) FROM cases c2 WHERE c2.user_id=c.user_id AND c2.id<=c.id) AS case_no
            FROM case_important_dates d JOIN cases c ON c.id=d.case_id
            WHERE d.user_id=? AND c.status!='archived'
            ORDER BY d.date_gregorian ASC, d.id ASC LIMIT ?""",(uid,int(limit))).fetchall()
        return [dict(r) for r in rows]

def count_case_important_dates(uid):
    return len(list_case_important_dates(uid, 500))

def init_case_reminders_table():
    with conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS case_date_reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            case_date_id INTEGER NOT NULL UNIQUE,
            enabled INTEGER NOT NULL DEFAULT 1,
            sent_at TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(case_date_id) REFERENCES case_important_dates(id)
        )""")
        c.execute('CREATE INDEX IF NOT EXISTS idx_case_reminders_due ON case_date_reminders(enabled,sent_at)')
        c.commit()

def set_case_date_reminder(uid, case_date_id, enabled=True):
    init_case_reminders_table()
    with conn() as c:
        row=c.execute("""SELECT d.id FROM case_important_dates d JOIN cases c ON c.id=d.case_id
            WHERE d.id=? AND d.user_id=? AND c.status!='archived'""",(int(case_date_id),uid)).fetchone()
        if not row:
            return False
        c.execute("""INSERT INTO case_date_reminders(user_id,case_date_id,enabled,sent_at,created_at)
            VALUES(?,?,?,NULL,?)
            ON CONFLICT(case_date_id) DO UPDATE SET enabled=excluded.enabled, sent_at=NULL""",
            (uid,int(case_date_id),1 if enabled else 0,now_iso()))
        c.commit()
        return True

def list_due_case_reminders():
    init_case_reminders_table()
    # Reminder policy: an explicitly enabled date gets one reminder on the
    # calendar day before the extracted date. No legal deadline is inferred.
    from datetime import date, timedelta
    target=(date.today()+timedelta(days=1)).isoformat()
    with conn() as c:
        rows=c.execute("""SELECT r.id AS reminder_id,r.user_id,r.case_date_id,
                d.date_jalali,d.date_gregorian,d.description,d.source_text,
                c.file_name,c.id AS case_id
            FROM case_date_reminders r
            JOIN case_important_dates d ON d.id=r.case_date_id
            JOIN cases c ON c.id=d.case_id
            WHERE r.enabled=1 AND r.sent_at IS NULL AND d.date_gregorian=? AND c.status!='archived'""",(target,)).fetchall()
        return [dict(r) for r in rows]

def mark_case_reminder_sent(reminder_id):
    init_case_reminders_table()
    with conn() as c:
        cur=c.execute('UPDATE case_date_reminders SET sent_at=? WHERE id=? AND sent_at IS NULL',(now_iso(),int(reminder_id)))
        c.commit()
        return cur.rowcount == 1


def list_due_calendar_task_reminders():
    """Return one-time reminders for manually-created tasks, isolated by owner."""
    from datetime import datetime
    try:
        from zoneinfo import ZoneInfo
        today=datetime.now(ZoneInfo('Asia/Tehran')).date().isoformat()
    except Exception:
        today=datetime.now().date().isoformat()
    init_case_workspace_tables(); init_tasks_table()
    with conn() as c:
        rows=[]
        rows += [dict(r) for r in c.execute("""SELECT t.id AS task_id,t.user_id,t.title,t.due_at,t.reminder_days,
                c.file_name AS case_name,c.id AS case_id,'task' AS item_type
            FROM case_tasks t JOIN cases c ON c.id=t.case_id
            WHERE t.done=0 AND t.reminder_days IS NOT NULL AND t.reminder_sent_at IS NULL
              AND t.due_at IS NOT NULL AND substr(t.due_at,1,10)>=?
              AND date(substr(t.due_at,1,10), '-' || t.reminder_days || ' days')<=?
              AND c.user_id=t.user_id AND c.status!='archived'""",(today,today)).fetchall()]
        rows += [dict(r) for r in c.execute("""SELECT id AS task_id,user_id,title,due_at,reminder_days,
                'کارهای من' AS case_name,NULL AS case_id,'user_task' AS item_type
            FROM user_tasks WHERE done=0 AND reminder_days IS NOT NULL AND reminder_sent_at IS NULL
              AND due_at IS NOT NULL AND substr(due_at,1,10)>=?
              AND date(substr(due_at,1,10), '-' || reminder_days || ' days')<=?""",(today,today)).fetchall()]
    return rows


def mark_calendar_task_reminder_sent(user_id, item_type, task_id):
    init_case_workspace_tables(); init_tasks_table()
    table='case_tasks' if item_type=='task' else 'user_tasks' if item_type=='user_task' else None
    if not table: return False
    with conn() as c:
        cur=c.execute(f'UPDATE {table} SET reminder_sent_at=? WHERE id=? AND user_id=? AND reminder_sent_at IS NULL',
                       (now_iso(),int(task_id),int(user_id)))
        c.commit(); return cur.rowcount==1




def init_tasks_table():
    with conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS user_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            due_at TEXT,
            done INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        _ensure_column(c, 'user_tasks', 'reminder_days', 'INTEGER')
        _ensure_column(c, 'user_tasks', 'reminder_sent_at', 'TEXT')
        c.commit()

def add_task(uid, title, due_at=None, reminder_days=None):
    init_tasks_table()
    with conn() as c:
        reminder_days = int(reminder_days) if reminder_days is not None and due_at else None
        if reminder_days not in (None, 0, 1, 3, 7): raise ValueError('بازه یادآوری معتبر نیست.')
        cur = c.execute(
            "INSERT INTO user_tasks(user_id,title,due_at,reminder_days,reminder_sent_at) VALUES(?,?,?,?,NULL)",
            (uid, title.strip(), due_at, reminder_days)
        )
        c.commit()
        return cur.lastrowid

def list_tasks(uid, include_done=True):
    init_tasks_table()
    sql = "SELECT * FROM user_tasks WHERE user_id=?"
    args = [uid]
    if not include_done:
        sql += " AND done=0"
    sql += " ORDER BY done ASC, CASE WHEN due_at IS NULL THEN 1 ELSE 0 END, due_at ASC, id DESC"
    with conn() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]

def get_task(uid, task_id):
    init_tasks_table()
    with conn() as c:
        r = c.execute(
            "SELECT * FROM user_tasks WHERE id=? AND user_id=?",
            (task_id, uid)
        ).fetchone()
        return dict(r) if r else None

def set_task_done(uid, task_id, done=True):
    init_tasks_table()
    with conn() as c:
        cur = c.execute(
            "UPDATE user_tasks SET done=? WHERE id=? AND user_id=?",
            (1 if done else 0, task_id, uid)
        )
        c.commit()
        return cur.rowcount > 0

def delete_task(uid, task_id):
    init_tasks_table()
    with conn() as c:
        cur = c.execute(
            "DELETE FROM user_tasks WHERE id=? AND user_id=?",
            (task_id, uid)
        )
        c.commit()
        return cur.rowcount > 0



FREE_CASE_LIMIT = 3
PAID_CASE_LIMIT = 50
SUBSCRIPTION_DAYS = 30

def init_subscription_tables():
    with conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            plan TEXT NOT NULL DEFAULT 'free',
            started_at TEXT,
            expires_at TEXT,
            monthly_limit INTEGER NOT NULL DEFAULT 3,
            used_cases INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS payment_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            plan TEXT NOT NULL DEFAULT 'monthly',
            receipt_file_id TEXT,
            receipt_caption TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            reviewed_by INTEGER,
            reviewed_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            payment_reference TEXT,
            amount_text TEXT,
            receipt_received_at TEXT
        )""")
        # V134 migration: keep old installations compatible without requiring
        # a destructive database reset.
        cols={r[1] for r in c.execute("PRAGMA table_info(payment_requests)").fetchall()}
        for name, typ in (('payment_reference','TEXT'),('amount_text','TEXT'),('receipt_received_at','TEXT')):
            if name not in cols:
                c.execute(f"ALTER TABLE payment_requests ADD COLUMN {name} {typ}")
        c.commit()

def ensure_subscription(uid):
    init_subscription_tables()
    with conn() as c:
        r=c.execute("SELECT * FROM subscriptions WHERE user_id=? ORDER BY id DESC LIMIT 1",(uid,)).fetchone()
        if r:
            return dict(r)
        c.execute("""INSERT INTO subscriptions
            (user_id,plan,monthly_limit,used_cases,active)
            VALUES(?,?,?,?,?)""",(uid,'free',FREE_CASE_LIMIT,0,0))
        c.commit()
        r=c.execute("SELECT * FROM subscriptions WHERE user_id=? ORDER BY id DESC LIMIT 1",(uid,)).fetchone()
        return dict(r)

def get_subscription(uid):
    return ensure_subscription(uid)

def get_payment_request(pid):
    init_subscription_tables()
    with conn() as c:
        r=c.execute("SELECT * FROM payment_requests WHERE id=?",(pid,)).fetchone()
        return dict(r) if r else None

def has_pending_payment_request(uid):
    init_subscription_tables()
    with conn() as c:
        return c.execute(
            "SELECT 1 FROM payment_requests WHERE user_id=? AND status='pending' LIMIT 1",
            (int(uid),)).fetchone() is not None


def create_payment_request(uid, receipt_file_id, caption=None):
    """Create one pending card-to-card receipt review for a user.

    This intentionally keeps the existing manual payment model: no gateway
    or automatic payment confirmation is assumed.
    """
    init_subscription_tables()
    from secrets import token_hex
    ref=f"LB-{token_hex(4).upper()}"
    now=_utc_now_naive().isoformat()
    with conn() as c:
        # One active manual-review receipt per user prevents duplicate pending
        # submissions and double-review ambiguity.
        if c.execute(
            "SELECT 1 FROM payment_requests WHERE user_id=? AND status='pending' LIMIT 1",
            (int(uid),)).fetchone():
            return None
        cur=c.execute("""INSERT INTO payment_requests
            (user_id,plan,receipt_file_id,receipt_caption,status,payment_reference,amount_text,receipt_received_at)
            VALUES(?,?,?,?,?,?,?,?)""",
            (uid,'monthly',receipt_file_id,caption,'pending',ref,None,now))
        c.commit()
        return cur.lastrowid
def pending_payments(limit=50):
    init_subscription_tables()
    with conn() as c:
        rows=c.execute("""SELECT * FROM payment_requests
            WHERE status='pending' ORDER BY id ASC LIMIT ?""",(limit,)).fetchall()
        return [dict(r) for r in rows]

def review_payment(pid, admin_id, approved):
    init_subscription_tables()
    from datetime import datetime, timedelta
    with conn() as c:
        p=c.execute("SELECT * FROM payment_requests WHERE id=?",(pid,)).fetchone()
        if not p or p["status"]!="pending":
            return False
        now=_utc_now_naive()
        if approved:
            # Start from current expiry when an active subscription exists;
            # otherwise from now, avoiding loss on early renewal.
            sub=c.execute("""SELECT * FROM subscriptions WHERE user_id=?
                ORDER BY id DESC LIMIT 1""",(p["user_id"],)).fetchone()
            base=now
            if sub and sub["active"] and sub["expires_at"]:
                try:
                    old=_parse_utc(sub["expires_at"])
                    if old and old>base: base=old
                except Exception:
                    pass
            expiry=base+timedelta(days=SUBSCRIPTION_DAYS)
            if sub:
                c.execute("""UPDATE subscriptions SET plan='monthly',
                    started_at=?,expires_at=?,monthly_limit=?,used_cases=0,active=1
                    WHERE id=?""",
                    (now.isoformat(),expiry.isoformat(),PAID_CASE_LIMIT,sub["id"]))
            else:
                c.execute("""INSERT INTO subscriptions
                    (user_id,plan,started_at,expires_at,monthly_limit,used_cases,active)
                    VALUES(?,?,?,?,?,?,1)""",
                    (p["user_id"],'monthly',now.isoformat(),expiry.isoformat(),PAID_CASE_LIMIT,0))
            c.execute("""UPDATE payment_requests SET status='approved',
                reviewed_by=?,reviewed_at=? WHERE id=?""",
                (admin_id,now.isoformat(),pid))
        else:
            c.execute("""UPDATE payment_requests SET status='rejected',
                reviewed_by=?,reviewed_at=? WHERE id=?""",
                (admin_id,now.isoformat(),pid))
        c.commit()
        return True

def _utc_now_naive():
    # Subscription timestamps are stored as ISO strings. Keep comparisons
    # timezone-safe even when older rows were written without an offset.
    return datetime.now(timezone.utc).replace(tzinfo=None)

def _parse_utc(value):
    if not value:
        return None
    try:
        dt=datetime.fromisoformat(value)
        if dt.tzinfo is None:
            return dt
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None

def subscription_status(uid):
    s=ensure_subscription(uid)
    if s.get("active") and s.get("expires_at"):
        exp=_parse_utc(s["expires_at"])
        if exp is not None and exp <= _utc_now_naive():
            with conn() as c:
                c.execute("UPDATE subscriptions SET active=0,plan='free',monthly_limit=?,used_cases=0 WHERE id=?",
                          (FREE_CASE_LIMIT,s["id"]))
                c.commit()
            s=ensure_subscription(uid)
    return s

def can_use_case(uid):
    s=subscription_status(uid)
    if not s:
        return False
    if s.get('active'):
        return int(s.get('used_cases') or 0) < int(s.get('monthly_limit') or FREE_CASE_LIMIT)
    credit=credit_status(uid)
    from .config import CREDIT_CASE_COST
    return bool(credit) and int(credit.get('remaining') or 0) >= CREDIT_CASE_COST

def reserve_case(uid):
    """LEGACY compatibility wrapper. New application code uses EntitlementService."""
    s=subscription_status(uid)
    if s and s.get('active'):
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute("SELECT * FROM subscriptions WHERE user_id=? ORDER BY id DESC LIMIT 1",(uid,)).fetchone()
            if not row: return False,'ابتدا /start را بزنید.'
            used=int(row['used_cases'] or 0); limit=int(row['monthly_limit'] or FREE_CASE_LIMIT)
            if used>=limit: return False,'سهمیه پرونده اشتراک شما تمام شده است.'
            c.execute('UPDATE subscriptions SET used_cases=used_cases+1 WHERE id=?',(row['id'],)); c.commit()
        return True,'subscription'
    from .config import CREDIT_CASE_COST
    return reserve_credit(uid,CREDIT_CASE_COST,'case_intake')

def refund_case(uid, reservation_token):
    if reservation_token == 'subscription':
        with conn() as c:
            c.execute("UPDATE subscriptions SET used_cases=MAX(0,used_cases-1) WHERE user_id=? AND active=1 AND used_cases>0",(uid,)); c.commit()
        return True
    return refund_credit(uid,reservation_token)

def consume_case(uid):
    """Backward-compatible wrapper; new code should use reserve_case."""
    ok, _ = reserve_case(uid)
    return ok



def admin_stats():
    init_subscription_tables()
    with conn() as c:
        users = 0
        try:
            users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        except Exception:
            pass
        cases = 0
        try:
            cases = c.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
        except Exception:
            pass
        active = c.execute("""SELECT COUNT(*) FROM subscriptions
            WHERE active=1""").fetchone()[0]
        pending = c.execute("""SELECT COUNT(*) FROM payment_requests
            WHERE status='pending'""").fetchone()[0]
        return {"users":users,"cases":cases,"active":active,"pending":pending}

def admin_users(limit=30):
    init_subscription_tables()
    with conn() as c:
        try:
            rows=c.execute("""SELECT user_id,plan,monthly_limit,used_cases,
                active,expires_at FROM subscriptions
                ORDER BY user_id DESC LIMIT ?""",(limit,)).fetchall()
        except Exception:
            rows=[]
        return [dict(r) for r in rows]

def admin_user(uid):
    init_subscription_tables()
    with conn() as c:
        s=c.execute("""SELECT * FROM subscriptions
            WHERE user_id=? ORDER BY id DESC LIMIT 1""",(uid,)).fetchone()
        return dict(s) if s else None

def admin_grant(uid, days=30, limit=50, admin_id=None):
    init_subscription_tables()
    from datetime import datetime, timedelta
    now=_utc_now_naive()
    expiry=now+timedelta(days=days)
    with conn() as c:
        s=c.execute("SELECT * FROM subscriptions WHERE user_id=? ORDER BY id DESC LIMIT 1",(uid,)).fetchone()
        if s:
            c.execute("""UPDATE subscriptions SET plan='monthly',
                started_at=?,expires_at=?,monthly_limit=?,used_cases=0,active=1
                WHERE id=?""",(now.isoformat(),expiry.isoformat(),limit,s["id"]))
        else:
            c.execute("""INSERT INTO subscriptions
                (user_id,plan,started_at,expires_at,monthly_limit,used_cases,active)
                VALUES(?,?,?,?,?,?,1)""",(uid,'monthly',now.isoformat(),expiry.isoformat(),limit,0))
        c.commit()
    return True

def admin_revoke(uid):
    init_subscription_tables()
    with conn() as c:
        cur=c.execute("""UPDATE subscriptions SET active=0,plan='free',
            monthly_limit=?,used_cases=0 WHERE user_id=?""",(FREE_CASE_LIMIT,uid))
        c.commit()
        return cur.rowcount>0

def admin_set_limit(uid, limit):
    init_subscription_tables()
    with conn() as c:
        cur=c.execute("UPDATE subscriptions SET monthly_limit=? WHERE user_id=?",(int(limit),uid))
        c.commit()
        return cur.rowcount>0



FREE_PERIOD_DAYS = 30

def init_free_channel_tables():
    init_subscription_tables()
    with conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS free_channel_config (
            id INTEGER PRIMARY KEY CHECK (id=1),
            promo_channel_id TEXT,
            promo_channel_username TEXT,
            promo_channel_title TEXT,
            promo_until TEXT,
            info_channel_id TEXT,
            info_channel_username TEXT,
            info_channel_title TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS free_entitlements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            period_key TEXT NOT NULL,
            promo_channel_id TEXT,
            verified_at TEXT,
            expires_at TEXT,
            free_limit INTEGER NOT NULL DEFAULT 3,
            used_cases INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            UNIQUE(user_id, period_key)
        )""")
        c.commit()

def current_free_period_key():
    from datetime import datetime
    return datetime.utcnow().strftime("%Y-%m")

def get_free_channel_config():
    init_free_channel_tables()
    with conn() as c:
        r=c.execute("SELECT * FROM free_channel_config WHERE id=1").fetchone()
        return dict(r) if r else None

def set_free_channels(promo_channel_id, promo_username, promo_title,
                      info_channel_id, info_username, info_title, promo_until=None):
    init_free_channel_tables()
    from datetime import datetime
    with conn() as c:
        c.execute("""INSERT INTO free_channel_config
            (id,promo_channel_id,promo_channel_username,promo_channel_title,
             promo_until,info_channel_id,info_channel_username,info_channel_title,updated_at)
            VALUES(1,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
             promo_channel_id=excluded.promo_channel_id,
             promo_channel_username=excluded.promo_channel_username,
             promo_channel_title=excluded.promo_channel_title,
             promo_until=excluded.promo_until,
             info_channel_id=excluded.info_channel_id,
             info_channel_username=excluded.info_channel_username,
             info_channel_title=excluded.info_channel_title,
             updated_at=excluded.updated_at""",
            (promo_channel_id,promo_username,promo_title,promo_until,
             info_channel_id,info_username,info_title,datetime.utcnow().isoformat()))
        c.commit()

def get_free_entitlement(uid, period_key=None):
    init_free_channel_tables()
    period_key=period_key or current_free_period_key()
    with conn() as c:
        r=c.execute("""SELECT * FROM free_entitlements
            WHERE user_id=? AND period_key=?""",(uid,period_key)).fetchone()
        return dict(r) if r else None

def grant_free_entitlement(uid, promo_channel_id=None):
    init_free_channel_tables()
    from datetime import datetime, timedelta
    now=datetime.utcnow()
    key=current_free_period_key()
    exp=now+timedelta(days=FREE_PERIOD_DAYS)
    with conn() as c:
        c.execute("""INSERT INTO free_entitlements
            (user_id,period_key,promo_channel_id,verified_at,expires_at,free_limit,used_cases,active)
            VALUES(?,?,?,?,?,?,0,1)
            ON CONFLICT(user_id,period_key) DO UPDATE SET
              promo_channel_id=excluded.promo_channel_id,
              verified_at=excluded.verified_at,
              expires_at=excluded.expires_at,
              active=1""",
            (uid,key,promo_channel_id,now.isoformat(),exp.isoformat(),FREE_CASE_LIMIT))
        c.commit()
    return get_free_entitlement(uid,key)

def free_quota_status(uid):
    e=get_free_entitlement(uid)
    if not e:
        return None
    from datetime import datetime
    try:
        if e.get("expires_at") and datetime.fromisoformat(e["expires_at"]) <= datetime.utcnow():
            return None
    except Exception:
        pass
    return e

def consume_free_case(uid):
    e=free_quota_status(uid)
    if not e or not e.get("active"):
        return False
    if int(e.get("used_cases") or 0) >= int(e.get("free_limit") or FREE_CASE_LIMIT):
        return False
    with conn() as c:
        c.execute("UPDATE free_entitlements SET used_cases=used_cases+1 WHERE id=?",(e["id"],))
        c.commit()
    return True

def free_cases_available(uid):
    e=free_quota_status(uid)
    if not e:
        return 0
    return max(0,int(e["free_limit"])-int(e["used_cases"] or 0))



# V112 — user role: lawyer | client (separates menus; not a permission system)
def _ensure_user_role_table(c):
    c.execute("""CREATE TABLE IF NOT EXISTS user_role(
        user_id INTEGER PRIMARY KEY,
        role TEXT NOT NULL,
        selected_at TEXT DEFAULT CURRENT_TIMESTAMP)""")

def get_user_role(uid):
    with conn() as c:
        _ensure_user_role_table(c)
        r = c.execute("SELECT role FROM user_role WHERE user_id=?", (uid,)).fetchone()
        return r["role"] if r else None

def set_user_role(uid, role):
    if role not in ("lawyer", "client"):
        raise ValueError("invalid role")
    with conn() as c:
        _ensure_user_role_table(c)
        c.execute(
            """INSERT INTO user_role(user_id, role, selected_at)
               VALUES(?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET
               role=excluded.role, selected_at=excluded.selected_at""",
            (uid, role, now_iso()),
        )
        return True


def set_account_mode(uid, mode):
    if mode not in ("free", "pro"):
        raise ValueError("invalid mode")
    with conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS user_access_mode(
            user_id INTEGER PRIMARY KEY,
            mode TEXT NOT NULL,
            selected_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("""INSERT INTO user_access_mode(user_id,mode)
            VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET
            mode=excluded.mode, selected_at=CURRENT_TIMESTAMP""",(uid,mode))
        c.commit()

def get_account_mode(uid):
    with conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS user_access_mode(
            user_id INTEGER PRIMARY KEY,
            mode TEXT NOT NULL,
            selected_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        r=c.execute("SELECT mode FROM user_access_mode WHERE user_id=?",(uid,)).fetchone()
        return r["mode"] if r else None


# V13 — independent monthly AI question quota
AI_FREE_QUESTIONS = 7
AI_PRO_QUESTIONS = 100

def current_ai_period_key():
    from datetime import datetime
    return datetime.now().strftime("%Y-%m")

def ai_question_limit(uid):
    mode = get_account_mode(uid) if "get_account_mode" in globals() else None
    return AI_PRO_QUESTIONS if mode == "pro" else AI_FREE_QUESTIONS

def get_ai_quota(uid):
    period = current_ai_period_key()
    with conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS ai_question_quota(
            user_id INTEGER NOT NULL,
            period_key TEXT NOT NULL,
            used_questions INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id, period_key)
        )""")
        r = c.execute("""SELECT used_questions FROM ai_question_quota
                         WHERE user_id=? AND period_key=?""",
                      (uid, period)).fetchone()
        used = int(r["used_questions"]) if r else 0
        limit = ai_question_limit(uid)
        return {
            "period": period,
            "used": used,
            "limit": limit,
            "remaining": max(0, limit-used)
        }

def reserve_ai_question(uid):
    """LEGACY compatibility wrapper. New application code uses EntitlementService."""
    u=get_user(uid)
    if not u: return False
    if active_subscription(u):
        period=current_ai_period_key(); limit=ai_question_limit(uid)
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute("""CREATE TABLE IF NOT EXISTS ai_question_quota(
                user_id INTEGER NOT NULL, period_key TEXT NOT NULL, used_questions INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(user_id, period_key))""")
            r=c.execute("SELECT used_questions FROM ai_question_quota WHERE user_id=? AND period_key=?",(uid,period)).fetchone()
            used=int(r['used_questions']) if r else 0
            if used>=limit: return False
            c.execute("""INSERT INTO ai_question_quota(user_id,period_key,used_questions) VALUES(?,?,1)
                ON CONFLICT(user_id,period_key) DO UPDATE SET used_questions=used_questions+1""",(uid,period)); c.commit(); return True
    from .config import CREDIT_AI_QUESTION_COST
    ok,ref=reserve_credit(uid,CREDIT_AI_QUESTION_COST,'ai_question')
    return ref if ok else False

def refund_ai_question(uid, reservation=None):
    u=get_user(uid)
    if reservation and reservation not in ('subscription',True): return refund_credit(uid,reservation)
    if u and active_subscription(u):
        period=current_ai_period_key()
        with conn() as c:
            c.execute("UPDATE ai_question_quota SET used_questions=MAX(0,used_questions-1) WHERE user_id=? AND period_key=? AND used_questions>0",(uid,period)); c.commit()
        return True
    return False

def consume_ai_question(uid):
    r=reserve_ai_question(uid)
    if not r:return False
    if isinstance(r,str): return commit_credit(uid,r)
    return True


def ai_quota_text(uid):
    q = get_ai_quota(uid)
    return f"🤖 سهمیه سؤال AI: {q['remaining']} از {q['limit']} سؤال باقی مانده"

def init_case_ai_history_table():
    with conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS case_ai_history(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            context_mode TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(case_id) REFERENCES cases(id),
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )""")
        c.commit()

def add_case_ai_exchange(uid, cid, question, answer, context_mode=''):
    if not get_case(uid, cid):
        return False
    init_case_ai_history_table()
    with conn() as c:
        c.execute("""INSERT INTO case_ai_history(case_id,user_id,question,answer,context_mode)
                     VALUES(?,?,?,?,?)""", (uid and int(cid), int(uid), str(question or '').strip(), str(answer or '').strip(), str(context_mode or '')[:80]))
        c.commit()
        return True

def get_case_ai_history(uid, cid, limit=3):
    if not get_case(uid, cid):
        return []
    init_case_ai_history_table()
    with conn() as c:
        rows=c.execute("""SELECT id,question,answer,context_mode,created_at
                         FROM case_ai_history WHERE case_id=? AND user_id=?
                         ORDER BY id DESC LIMIT ?""", (int(cid),int(uid),max(1,min(int(limit),80)))).fetchall()
        return [dict(r) for r in rows]

def get_last_case_ai_exchange(uid, cid):
    rows=get_case_ai_history(uid,cid,1)
    return rows[0] if rows else None




# V29 — private lawyer service listings / referral leads
def init_service_listings_table():
    with conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS service_listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            full_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            city TEXT NOT NULL,
            specialty TEXT NOT NULL,
            service_title TEXT NOT NULL,
            fee_type TEXT NOT NULL CHECK(fee_type IN ('fixed','percent')),
            fee_value TEXT NOT NULL,
            description TEXT,
            charitable INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','active','rejected','deleted')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )""")
        c.execute('CREATE INDEX IF NOT EXISTS idx_service_user_status ON service_listings(user_id,status)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_service_status_created ON service_listings(status,created_at DESC)')

def create_service_listing(uid, full_name, phone, city, specialty, service_title, fee_type, fee_value, description='', charitable=False):
    init_service_listings_table()
    with conn() as c:
        cur=c.execute("""INSERT INTO service_listings(
            user_id,full_name,phone,city,specialty,service_title,fee_type,fee_value,description,charitable,status,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,'pending',?,?)""",
        (uid,full_name.strip()[:120],phone.strip()[:40],city.strip()[:100],specialty.strip()[:150],service_title.strip()[:200],fee_type,fee_value.strip()[:100],description.strip()[:2000],1 if charitable else 0,now_iso(),now_iso()))
        return cur.lastrowid

def get_service_listing(lid):
    init_service_listings_table()
    with conn() as c:
        r=c.execute('SELECT * FROM service_listings WHERE id=?',(lid,)).fetchone()
        return dict(r) if r else None

def list_service_listings(uid, limit=50, include_deleted=False):
    init_service_listings_table()
    where='user_id=?'
    args=[uid]
    if not include_deleted: where += " AND status!='deleted'"
    args.append(limit)
    with conn() as c:
        return [dict(r) for r in c.execute(f'SELECT * FROM service_listings WHERE {where} ORDER BY id DESC LIMIT ?',args).fetchall()]

def set_service_status(lid, status):
    if status not in {'pending','active','rejected','deleted'}: return False
    init_service_listings_table()
    with conn() as c:
        cur=c.execute('UPDATE service_listings SET status=?,updated_at=? WHERE id=?',(status,now_iso(),lid))
        return cur.rowcount>0

def delete_service_listing(uid,lid):
    init_service_listings_table()
    with conn() as c:
        cur=c.execute("UPDATE service_listings SET status='deleted',updated_at=? WHERE id=? AND user_id=? AND status!='deleted'",(now_iso(),lid,uid))
        return cur.rowcount>0

def list_pending_service_listings(limit=100):
    init_service_listings_table()
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM service_listings WHERE status='pending' ORDER BY id ASC LIMIT ?",(limit,)).fetchall()]


def update_service_listing(uid,lid,full_name,phone,city,specialty,service_title,fee_type,fee_value,description='',charitable=False):
    init_service_listings_table()
    with conn() as c:
        cur=c.execute("""UPDATE service_listings SET full_name=?,phone=?,city=?,specialty=?,service_title=?,fee_type=?,fee_value=?,description=?,charitable=?,status='pending',updated_at=?
                     WHERE id=? AND user_id=? AND status!='deleted'""",
            (full_name.strip()[:120],phone.strip()[:40],city.strip()[:100],specialty.strip()[:150],service_title.strip()[:200],fee_type,fee_value.strip()[:100],description.strip()[:2000],1 if charitable else 0,now_iso(),lid,uid))
        return cur.rowcount>0

# --- V41 work dashboard + client referral workflow ---
def init_v41_workflow_tables():
    with conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS referral_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_user_id INTEGER NOT NULL,
            topic TEXT NOT NULL,
            city TEXT NOT NULL,
            urgency TEXT NOT NULL DEFAULT 'normal',
            details TEXT NOT NULL,
            consent INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'new',
            assigned_listing_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(client_user_id) REFERENCES users(user_id),
            FOREIGN KEY(assigned_listing_id) REFERENCES service_listings(id)
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS referral_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referral_id INTEGER NOT NULL,
            listing_id INTEGER NOT NULL,
            lawyer_user_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'sent',
            lawyer_note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(referral_id, listing_id),
            FOREIGN KEY(referral_id) REFERENCES referral_requests(id),
            FOREIGN KEY(listing_id) REFERENCES service_listings(id),
            FOREIGN KEY(lawyer_user_id) REFERENCES users(user_id)
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS referral_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referral_id INTEGER NOT NULL,
            actor_user_id INTEGER,
            event_type TEXT NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(referral_id) REFERENCES referral_requests(id)
        )""")
        c.execute('CREATE INDEX IF NOT EXISTS idx_ref_client_status ON referral_requests(client_user_id,status,created_at DESC)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_ref_match_lawyer ON referral_matches(lawyer_user_id,status,created_at DESC)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_ref_event_ref ON referral_events(referral_id,created_at DESC)')
        c.commit()


def create_referral_request(client_user_id, topic, city, urgency, details, consent=True):
    init_v41_workflow_tables()
    now=now_iso()
    with conn() as c:
        cur=c.execute("""INSERT INTO referral_requests
            (client_user_id,topic,city,urgency,details,consent,status,created_at,updated_at)
            VALUES(?,?,?,?,?,?, 'new',?,?)""",
            (client_user_id,topic.strip()[:160],city.strip()[:100],urgency,details.strip()[:4000],1 if consent else 0,now,now))
        rid=cur.lastrowid
        c.execute("INSERT INTO referral_events(referral_id,actor_user_id,event_type,note,created_at) VALUES(?,?,?,?,?)",
                  (rid,client_user_id,'created','درخواست معرفی ایجاد شد',now))
        c.commit()
        return rid


def get_referral_request(rid):
    init_v41_workflow_tables()
    with conn() as c:
        r=c.execute("SELECT * FROM referral_requests WHERE id=?",(rid,)).fetchone()
        return dict(r) if r else None


def list_referrals_for_user(uid, limit=30):
    init_v41_workflow_tables()
    with conn() as c:
        rows=c.execute("SELECT * FROM referral_requests WHERE client_user_id=? ORDER BY id DESC LIMIT ?",(uid,limit)).fetchall()
        return [dict(r) for r in rows]


def list_referral_matches_for_lawyer(uid, limit=30):
    init_v41_workflow_tables()
    with conn() as c:
        rows=c.execute("""SELECT m.*, r.topic,r.city,r.urgency,r.details,r.client_user_id,r.status AS referral_status,
            s.service_title,s.specialty,s.full_name,s.phone
            FROM referral_matches m
            JOIN referral_requests r ON r.id=m.referral_id
            JOIN service_listings s ON s.id=m.listing_id
            WHERE m.lawyer_user_id=? ORDER BY m.id DESC LIMIT ?""",(uid,limit)).fetchall()
        return [dict(r) for r in rows]


def list_open_referrals(limit=50):
    init_v41_workflow_tables()
    with conn() as c:
        rows=c.execute("""SELECT r.*, u.phone_last4
            FROM referral_requests r JOIN users u ON u.user_id=r.client_user_id
            WHERE r.status IN ('new','sent','more_info') ORDER BY r.id ASC LIMIT ?""",(limit,)).fetchall()
        return [dict(r) for r in rows]


def list_matching_services(topic, city, limit=8):
    init_service_listings_table(); init_v41_workflow_tables()
    topic_tokens=[x for x in re.split(r'\s+', topic.strip()) if len(x)>=2]
    city_norm=city.strip()
    with conn() as c:
        rows=c.execute("""SELECT * FROM service_listings
            WHERE status='active' ORDER BY id DESC LIMIT 200""").fetchall()
        data=[]
        for r in rows:
            d=dict(r); score=0
            if city_norm and city_norm in d['city']: score+=4
            hay=(d['specialty']+' '+d['service_title']+' '+(d.get('description') or '')).lower()
            for tok in topic_tokens:
                if tok.lower() in hay: score+=2
            if d.get('charitable'): score+=1
            data.append((score,d))
        data.sort(key=lambda x:(x[0],x[1]['id']),reverse=True)
        return [d for score,d in data[:limit]]


def assign_referral(referral_id, listing_id, admin_id=None):
    init_v41_workflow_tables(); init_service_listings_table()
    now=now_iso()
    with conn() as c:
        r=c.execute("SELECT * FROM referral_requests WHERE id=?",(referral_id,)).fetchone()
        s=c.execute("SELECT * FROM service_listings WHERE id=? AND status='active'",(listing_id,)).fetchone()
        if not r or not s or not r['consent']:
            return False
        existing=c.execute("SELECT id,status FROM referral_matches WHERE referral_id=? AND listing_id=?",(referral_id,listing_id)).fetchone()
        if existing and existing['status'] not in ('declined','closed'):
            return False
        c.execute("""INSERT OR REPLACE INTO referral_matches
            (id,referral_id,listing_id,lawyer_user_id,status,created_at,updated_at)
            VALUES(COALESCE(?,NULL),?,?,?,?,?,?)""",
            (existing['id'] if existing else None,referral_id,listing_id,s['user_id'],'sent',now,now))
        c.execute("UPDATE referral_requests SET status='sent',assigned_listing_id=?,updated_at=? WHERE id=?",(listing_id,now,referral_id))
        c.execute("INSERT INTO referral_events(referral_id,actor_user_id,event_type,note,created_at) VALUES(?,?,?,?,?)",
                  (referral_id,admin_id,'sent_to_lawyer',f"معرفی به خدمت #{listing_id}",now))
        c.commit()
        return True


def update_referral_match(match_id, lawyer_user_id, status, note=''):
    init_v41_workflow_tables()
    allowed={'accepted','declined','more_info','contact','closed'}
    if status not in allowed: return False
    now=now_iso()
    with conn() as c:
        m=c.execute("SELECT * FROM referral_matches WHERE id=? AND lawyer_user_id=?",(match_id,lawyer_user_id)).fetchone()
        if not m: return False
        c.execute("UPDATE referral_matches SET status=?,lawyer_note=?,updated_at=? WHERE id=?",(status,note[:3000],now,match_id))
        parent='contact' if status=='accepted' else ('more_info' if status=='more_info' else ('closed' if status=='closed' else 'sent'))
        c.execute("UPDATE referral_requests SET status=?,updated_at=? WHERE id=?",(parent,now,m['referral_id']))
        c.execute("INSERT INTO referral_events(referral_id,actor_user_id,event_type,note,created_at) VALUES(?,?,?,?,?)",
                  (m['referral_id'],lawyer_user_id,status,note[:1000],now))
        c.commit()
        return True


def add_referral_event(referral_id, actor_user_id, event_type, note=''):
    init_v41_workflow_tables()
    with conn() as c:
        c.execute("INSERT INTO referral_events(referral_id,actor_user_id,event_type,note,created_at) VALUES(?,?,?,?,?)",
                  (referral_id,actor_user_id,event_type,note[:2000],now_iso()))
        c.commit()
        return True


def list_referral_events(referral_id, limit=50):
    init_v41_workflow_tables()
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM referral_events WHERE referral_id=? ORDER BY id DESC LIMIT ?",(referral_id,limit)).fetchall()]


def get_referral_match(mid):
    init_v41_workflow_tables()
    with conn() as c:
        r=c.execute("""SELECT m.*,r.topic,r.city,r.urgency,r.details,r.client_user_id,r.status AS referral_status,
            s.service_title,s.specialty,s.full_name,s.phone
            FROM referral_matches m JOIN referral_requests r ON r.id=m.referral_id
            JOIN service_listings s ON s.id=m.listing_id WHERE m.id=?""",(mid,)).fetchone()
        return dict(r) if r else None

def add_client_referral_info(referral_id, client_user_id, note):
    init_v41_workflow_tables(); now=now_iso()
    with conn() as c:
        r=c.execute("SELECT * FROM referral_requests WHERE id=? AND client_user_id=?",(referral_id,client_user_id)).fetchone()
        if not r: return False
        old=r['details'] or ''
        merged=old + '\n\n[اطلاعات تکمیلی]\n' + note.strip()[:3000]
        c.execute("UPDATE referral_requests SET details=?,status='sent',updated_at=? WHERE id=?",(merged[:7000],now,referral_id))
        c.execute("UPDATE referral_matches SET status='sent',updated_at=? WHERE referral_id=? AND status='more_info'",(now,referral_id))
        c.execute("INSERT INTO referral_events(referral_id,actor_user_id,event_type,note,created_at) VALUES(?,?,?,?,?)",
                  (referral_id,client_user_id,'client_info',note[:1000],now))
        c.commit(); return True


def cleanup_retention(now=None):
    """Delete only data explicitly classified as ephemeral by retention policy."""
    from datetime import datetime, timezone, timedelta
    from .config import (
        AI_HISTORY_RETENTION_DAYS, DONE_TASK_RETENTION_DAYS,
        FEEDBACK_RETENTION_DAYS, REMINDER_RETENTION_DAYS,
        DELETED_LISTING_RETENTION_DAYS, REFERRAL_RETENTION_DAYS,
        QUOTA_RETENTION_MONTHS,
    )
    now_dt=now or datetime.now(timezone.utc)
    stats={}
    def cutoff(days): return (now_dt-timedelta(days=days)).isoformat()
    with conn() as c:
        if _table_exists(c,'case_ai_history'):
            stats['ai_history']=c.execute(
                'DELETE FROM case_ai_history WHERE created_at<?',
                (cutoff(AI_HISTORY_RETENTION_DAYS),)).rowcount
        if _table_exists(c,'feedback'):
            stats['feedback']=c.execute(
                'DELETE FROM feedback WHERE created_at<?',
                (cutoff(FEEDBACK_RETENTION_DAYS),)).rowcount
        if _table_exists(c,'user_tasks'):
            stats['done_tasks']=c.execute(
                'DELETE FROM user_tasks WHERE done=1 AND created_at<?',
                (cutoff(DONE_TASK_RETENTION_DAYS),)).rowcount
        if _table_exists(c,'tasks'):
            stats['tasks_done']=c.execute(
                'DELETE FROM tasks WHERE done=1 AND created_at<?',
                (cutoff(DONE_TASK_RETENTION_DAYS),)).rowcount
        if _table_exists(c,'case_date_reminders'):
            stats['reminders']=c.execute(
                'DELETE FROM case_date_reminders WHERE sent_at IS NOT NULL AND sent_at<?',
                (cutoff(REMINDER_RETENTION_DAYS),)).rowcount
        if _table_exists(c,'service_listings'):
            stats['deleted_listings']=c.execute(
                "DELETE FROM service_listings WHERE status='deleted' AND updated_at<?",
                (cutoff(DELETED_LISTING_RETENTION_DAYS),)).rowcount
        if _table_exists(c,'referral_events'):
            stats['referral_events']=c.execute(
                "DELETE FROM referral_events WHERE created_at<? AND referral_id IN (SELECT id FROM referral_requests WHERE status IN ('closed','declined','cancelled') AND updated_at<?)",
                (cutoff(REFERRAL_RETENTION_DAYS),cutoff(REFERRAL_RETENTION_DAYS))).rowcount
        if _table_exists(c,'referral_matches'):
            stats['referral_matches']=c.execute(
                "DELETE FROM referral_matches WHERE updated_at<? AND referral_id IN (SELECT id FROM referral_requests WHERE status IN ('closed','declined','cancelled') AND updated_at<?)",
                (cutoff(REFERRAL_RETENTION_DAYS),cutoff(REFERRAL_RETENTION_DAYS))).rowcount
        if _table_exists(c,'referral_requests'):
            stats['referral_requests']=c.execute(
                "DELETE FROM referral_requests WHERE status IN ('closed','declined','cancelled') AND updated_at<?",
                (cutoff(REFERRAL_RETENTION_DAYS),)).rowcount
        if _table_exists(c,'free_entitlements'):
            # Expired entitlements older than the configured quota history.
            old_exp=(now_dt-timedelta(days=max(1,QUOTA_RETENTION_MONTHS)*31)).isoformat()
            stats['free_entitlements']=c.execute(
                'DELETE FROM free_entitlements WHERE expires_at IS NOT NULL AND expires_at<?',
                (old_exp,)).rowcount
        if _table_exists(c,'ai_question_quota'):
            # period_key is YYYY-MM; retain the configured number of months.
            first_current=now_dt.replace(day=1)
            month_index=first_current.year*12+first_current.month-1-QUOTA_RETENTION_MONTHS
            y,m=divmod(month_index,12)
            old_period=f'{y:04d}-{m+1:02d}'
            stats['ai_question_quota']=c.execute(
                'DELETE FROM ai_question_quota WHERE period_key<?',(old_period,)).rowcount
        c.commit()
    return stats

def user_work_counts(uid):
    init_v41_workflow_tables(); init_tasks_table(); init_service_listings_table(); init_subscription_tables()
    with conn() as c:
        pending_tasks=c.execute("SELECT COUNT(*) n FROM user_tasks WHERE user_id=? AND done=0",(uid,)).fetchone()['n']
        open_ref=c.execute("SELECT COUNT(*) n FROM referral_requests WHERE client_user_id=? AND status NOT IN ('closed','declined','cancelled')",(uid,)).fetchone()['n']
        lawyer_ref=c.execute("SELECT COUNT(*) n FROM referral_matches WHERE lawyer_user_id=? AND status IN ('sent','more_info')",(uid,)).fetchone()['n']
        service_pending=c.execute("SELECT COUNT(*) n FROM service_listings WHERE user_id=? AND status='pending'",(uid,)).fetchone()['n']
        payments=c.execute("SELECT COUNT(*) n FROM payment_requests WHERE user_id=? AND status='pending'",(uid,)).fetchone()['n']
        cases=c.execute("SELECT COUNT(*) n FROM cases WHERE user_id=? AND status='processing'",(uid,)).fetchone()['n']
        return {'tasks':pending_tasks,'referrals':open_ref,'lawyer_referrals':lawyer_ref,'services_pending':service_pending,'payments':payments,'cases_processing':cases}

# --- V163 durable unified drafting workflow checkpoints ---
def init_drafting_workflow_tables():
    """Create the durable per-user/per-case drafting workflow checkpoint store."""
    with conn() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS drafting_workflow_sessions (
            user_id INTEGER NOT NULL,
            case_id INTEGER NOT NULL,
            workflow_version INTEGER NOT NULL DEFAULT 163,
            status TEXT NOT NULL DEFAULT 'NOT_STARTED',
            state_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(user_id, case_id),
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            FOREIGN KEY(case_id) REFERENCES cases(id) ON DELETE CASCADE
        )''')
        c.execute('CREATE INDEX IF NOT EXISTS idx_drafting_workflow_updated ON drafting_workflow_sessions(user_id, updated_at DESC)')


def get_drafting_workflow_session(uid, cid):
    """Return the durable workflow session for an owned case, or None."""
    import json
    with conn() as c:
        row = c.execute(
            'SELECT * FROM drafting_workflow_sessions WHERE user_id=? AND case_id=?',
            (int(uid), int(cid))
        ).fetchone()
    if not row:
        return None
    try:
        state = json.loads(row['state_json'] or '{}')
        if not isinstance(state, dict):
            state = {}
    except Exception:
        state = {}
    return {
        'user_id': int(row['user_id']),
        'case_id': int(row['case_id']),
        'workflow_version': int(row['workflow_version']),
        'status': row['status'],
        'state': state,
        'created_at': row['created_at'],
        'updated_at': row['updated_at'],
    }


def save_drafting_workflow_session(uid, cid, state=None, status=None, workflow_version=163):
    """Upsert one durable drafting checkpoint atomically."""
    import json
    ts = now_iso()
    state = dict(state or {})
    if status is None:
        status = str(state.get('status') or 'NOT_STARTED')
    state['status'] = status
    state['updated_at'] = ts
    payload = json.dumps(state, ensure_ascii=False, separators=(',', ':'), default=str)
    with conn() as c:
        existing = c.execute(
            'SELECT created_at FROM drafting_workflow_sessions WHERE user_id=? AND case_id=?',
            (int(uid), int(cid))
        ).fetchone()
        created = existing['created_at'] if existing else ts
        c.execute('''INSERT INTO drafting_workflow_sessions
            (user_id, case_id, workflow_version, status, state_json, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(user_id, case_id) DO UPDATE SET
                workflow_version=excluded.workflow_version,
                status=excluded.status,
                state_json=excluded.state_json,
                updated_at=excluded.updated_at''',
            (int(uid), int(cid), int(workflow_version), str(status), payload, created, ts)
        )
        c.commit()
    return get_drafting_workflow_session(uid, cid)


def clear_drafting_workflow_session(uid, cid):
    with conn() as c:
        cur = c.execute(
            'DELETE FROM drafting_workflow_sessions WHERE user_id=? AND case_id=?',
            (int(uid), int(cid))
        )
        return cur.rowcount > 0


# --- V164 durable supervised case workflow agent ---
def init_case_workflow_agent_tables():
    """Durable, owner-scoped checkpoints for the supervised case workflow agent."""
    with conn() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS case_workflow_agent_sessions (
            user_id INTEGER NOT NULL,
            case_id INTEGER NOT NULL,
            workflow_version INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'PENDING_APPROVAL',
            state_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(user_id, case_id),
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            FOREIGN KEY(case_id) REFERENCES cases(id) ON DELETE CASCADE
        )''')
        c.execute('CREATE INDEX IF NOT EXISTS idx_case_workflow_agent_updated ON case_workflow_agent_sessions(user_id, updated_at DESC)')

def get_case_workflow_agent_session(uid, cid):
    import json
    with conn() as c:
        row = c.execute('SELECT * FROM case_workflow_agent_sessions WHERE user_id=? AND case_id=?', (int(uid), int(cid))).fetchone()
    if not row:
        return None
    try:
        state = json.loads(row['state_json'] or '{}')
        if not isinstance(state, dict): state = {}
    except Exception:
        state = {}
    return {'user_id': int(row['user_id']), 'case_id': int(row['case_id']),
            'workflow_version': int(row['workflow_version']), 'status': row['status'],
            'state': state, 'created_at': row['created_at'], 'updated_at': row['updated_at']}

def save_case_workflow_agent_session(uid, cid, state=None, workflow_version=1):
    import json
    ts = now_iso(); state = dict(state or {}); status = str(state.get('status') or 'PENDING_APPROVAL')
    state['status'] = status; state['updated_at'] = ts
    payload = json.dumps(state, ensure_ascii=False, separators=(',', ':'), default=str)
    with conn() as c:
        row = c.execute('SELECT created_at FROM case_workflow_agent_sessions WHERE user_id=? AND case_id=?', (int(uid), int(cid))).fetchone()
        created = row['created_at'] if row else ts
        c.execute('''INSERT INTO case_workflow_agent_sessions
            (user_id, case_id, workflow_version, status, state_json, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(user_id, case_id) DO UPDATE SET
                workflow_version=excluded.workflow_version, status=excluded.status,
                state_json=excluded.state_json, updated_at=excluded.updated_at''',
            (int(uid), int(cid), int(workflow_version), status, payload, created, ts))
        c.commit()
    return get_case_workflow_agent_session(uid, cid)

def save_case_workflow_agent_session_if_unchanged(uid, cid, state=None, workflow_version=1, expected_updated_at=None):
    """Compare-and-swap a workflow checkpoint to prevent concurrent lost updates.

    ``expected_updated_at=None`` means the caller expects no session to exist.
    An existing timestamp means the row must still have exactly that version.
    Returns the refreshed session on success, or None when another request won.
    """
    import json
    uid, cid = int(uid), int(cid)
    ts = now_iso()
    state = dict(state or {})
    status = str(state.get('status') or 'PENDING_APPROVAL')
    state['status'] = status
    state['updated_at'] = ts
    payload = json.dumps(state, ensure_ascii=False, separators=(',', ':'), default=str)
    with conn() as c:
        c.execute('BEGIN IMMEDIATE')
        row = c.execute(
            'SELECT created_at, updated_at FROM case_workflow_agent_sessions WHERE user_id=? AND case_id=?',
            (uid, cid),
        ).fetchone()
        if expected_updated_at is None:
            if row is not None:
                c.rollback()
                return None
            c.execute("""INSERT INTO case_workflow_agent_sessions
                (user_id, case_id, workflow_version, status, state_json, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?)""",
                (uid, cid, int(workflow_version), status, payload, ts, ts))
        else:
            if row is None or row['updated_at'] != expected_updated_at:
                c.rollback()
                return None
            cur = c.execute("""UPDATE case_workflow_agent_sessions
                SET workflow_version=?, status=?, state_json=?, updated_at=?
                WHERE user_id=? AND case_id=? AND updated_at=?""",
                (int(workflow_version), status, payload, ts, uid, cid, expected_updated_at))
            if cur.rowcount != 1:
                c.rollback()
                return None
        c.commit()
    return get_case_workflow_agent_session(uid, cid)


def clear_case_workflow_agent_session(uid, cid):
    with conn() as c:
        cur = c.execute('DELETE FROM case_workflow_agent_sessions WHERE user_id=? AND case_id=?', (int(uid), int(cid)))
        c.commit()
        return cur.rowcount > 0


def set_document_saved(uid, case_id, document_id, saved):
    """Save/unsave a document only after verifying case and document ownership."""
    uid, case_id, document_id = int(uid), int(case_id), int(document_id)
    with conn() as c:
        owned = c.execute("""SELECT 1 FROM case_documents d JOIN cases c ON c.id=d.case_id
            WHERE d.id=? AND d.case_id=? AND c.user_id=? AND c.status!='archived'""",
            (document_id, case_id, uid)).fetchone()
        if not owned:
            return False
        if saved:
            c.execute('INSERT OR IGNORE INTO lawyer_saved_documents(user_id,case_id,document_id,created_at) VALUES(?,?,?,?)',
                      (uid, case_id, document_id, now_iso()))
        else:
            c.execute('DELETE FROM lawyer_saved_documents WHERE user_id=? AND case_id=? AND document_id=?',
                      (uid, case_id, document_id))
        c.commit()
        return True


def list_saved_documents(uid, limit=30):
    """Return saved document metadata for this lawyer, never extracted text."""
    limit = max(1, min(int(limit), 60))
    with conn() as c:
        rows = c.execute("""SELECT s.case_id,s.document_id,s.created_at,d.file_name,d.page_count,
            c.file_name AS case_name FROM lawyer_saved_documents s
            JOIN cases c ON c.id=s.case_id AND c.user_id=s.user_id
            JOIN case_documents d ON d.id=s.document_id AND d.case_id=s.case_id
            WHERE s.user_id=? AND c.status!='archived'
            ORDER BY s.created_at DESC LIMIT ?""", (int(uid), limit)).fetchall()
        return [dict(r) for r in rows]


def list_saved_document_ids(uid, case_id):
    with conn() as c:
        rows = c.execute('SELECT document_id FROM lawyer_saved_documents WHERE user_id=? AND case_id=?',
                         (int(uid), int(case_id))).fetchall()
        return [int(r[0]) for r in rows]


def list_pinned_case_ids(uid):
    """Return only this lawyer's pinned case IDs."""
    with conn() as c:
        rows=c.execute("SELECT case_id FROM case_pins WHERE user_id=? ORDER BY created_at DESC", (int(uid),)).fetchall()
        return [int(r[0]) for r in rows]

def set_case_pinned(uid, case_id, pinned):
    """Pin/unpin a case after verifying ownership."""
    uid=int(uid); case_id=int(case_id)
    with conn() as c:
        if not c.execute("SELECT 1 FROM cases WHERE id=? AND user_id=?", (case_id, uid)).fetchone():
            return False
        if pinned:
            c.execute("INSERT OR IGNORE INTO case_pins(user_id,case_id,created_at) VALUES(?,?,?)",
                      (uid, case_id, datetime.now(timezone.utc).isoformat()))
        else:
            c.execute("DELETE FROM case_pins WHERE user_id=? AND case_id=?", (uid, case_id))
        c.commit()
        return True
