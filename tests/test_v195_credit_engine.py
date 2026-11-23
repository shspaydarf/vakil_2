import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from legal_bot import config, db

def run():
    with tempfile.TemporaryDirectory() as td:
        old=db.DB_PATH; db.DB_PATH=Path(td)/'test.db'
        try:
            db.init_db(); db.v193_upgrade(); uid=991001
            ok,msg=db.register_user(uid,'phone-hash-v195','1234','law-v195','وکیل آزمایشی'); assert ok,msg
            st=db.credit_status(uid); assert st['allowance']==config.FREE_WEEKLY_CREDITS; assert st['remaining']==config.FREE_WEEKLY_CREDITS
            ok,ref=db.reserve_credit(uid,config.CREDIT_AI_QUESTION_COST,'ai_question'); assert ok and ref
            assert db.credit_status(uid)['remaining']==config.FREE_WEEKLY_CREDITS-config.CREDIT_AI_QUESTION_COST
            assert db.commit_credit(uid,ref)
            ok,ref=db.reserve_case(uid); assert ok and ref
            before=db.credit_status(uid)['remaining']; assert db.refund_case(uid,ref); assert db.credit_status(uid)['remaining']==before+config.CREDIT_CASE_COST
            ai_ref=db.reserve_ai_question(uid); assert isinstance(ai_ref,str) and ai_ref
            ai_before=db.credit_status(uid)['remaining']; assert db.commit_credit(uid,ai_ref); assert db.credit_status(uid)['remaining']==ai_before
            ok,reason=db.reserve_credit(uid,config.FREE_WEEKLY_CREDITS+1,'case_intake'); assert not ok and reason=='insufficient'
            with db.conn() as c:
                end=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(); c.execute('UPDATE credit_periods SET period_end=? WHERE user_id=?',(end,uid)); c.commit()
            fresh=db.credit_status(uid); assert fresh['remaining']==config.FREE_WEEKLY_CREDITS; assert fresh['period_start']!=st['period_start']
            print('V195 credit engine smoke test: PASS')
        finally: db.DB_PATH=old
if __name__=='__main__': run()
