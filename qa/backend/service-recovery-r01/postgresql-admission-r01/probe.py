import asyncio,json,pathlib,sys
from datetime import datetime,UTC,timedelta
from uuid import uuid4
from sqlalchemy import text
from sqlalchemy.engine import URL
import httpx
sys.path.insert(0,str(pathlib.Path('/home/ai/Development/vipi-production-20261107/backend')))
from vipi.db import Database,User,Device,Entitlement,BotPool,UsageBucket,Reservation,AccountDeletion
from vipi.recovery_admission import RecoveryHoldError,mark_restore
from vipi.recovery import BoundRecoveryEvidence,reconcile_marked_offline
from vipi.api import create_app
from vipi.config import Settings

ROOT=pathlib.Path('/home/ai/Development/.vipi-recovery-pg-20261111-r01')
URL_VALUE=URL.create('postgresql+asyncpg',username='ai',database='postgres',query={'host':str(ROOT/'socket')})
NOW=datetime(2026,11,11,tzinfo=UTC)
async def main():
 result={'driver':'asyncpg','socket_only':True,'checks':[],'reopen_authorized':False}
 normal=Database(URL_VALUE);offline=Database(URL_VALUE,offline_recovery=True)
 async def denied(label):
  try:await normal.check_admission()
  except RecoveryHoldError:result['checks'].append(label)
  else:raise AssertionError(label)
 try:
  await normal.create_for_test()
  # Repeated real checkout/rollback must leave ordinary SQL/transactions usable.
  for _ in range(3):await normal.check_admission()
  settings=Settings(database_url=URL_VALUE.render_as_string(hide_password=False),workos_client_id='client_fixture',workos_issuer='https://api.workos.com',service_secret='x'*43)
  class Verifier:
   async def verify(self,*a):raise AssertionError('no auth required by readiness')
  app=create_app(settings,database=normal,verifier=Verifier(),store_providers={})
  async with app.router.lifespan_context(app):
   async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://isolated.test') as client:
    response=await client.get('/health/ready');assert response.status_code==200,response.text
  result['checks'].append('unmarked actual API lifespan/listener/readiness and repeated asyncpg checkout')
  async with offline.engine.begin() as c:await c.execute(text('CREATE TABLE public.vipi_restore_hold (garbage integer)'))
  await denied('malformed empty marker denies real asyncpg checkout')
  async with offline.engine.begin() as c:await c.execute(text('DROP TABLE public.vipi_restore_hold'))
  rid=str(uuid4());await mark_restore(offline,snapshot_sha256='a'*64,snapshot_at=NOW-timedelta(days=2),restore_id=rid)
  async with offline.engine.begin() as c:await c.execute(text('DELETE FROM public.vipi_restore_hold'))
  await denied('well-shaped empty marker denies real asyncpg checkout')
  await mark_restore(offline,snapshot_sha256='a'*64,snapshot_at=NOW-timedelta(days=2),restore_id=rid)
  async with offline.sessions.begin() as s:
   for uid in ['alice','bob','eve']:s.add(User(id=uid,subject='user_'+uid,username=uid,display_name=uid,created_at=NOW))
   await s.flush()
   for uid in ['alice','bob','eve']:s.add(Device(id=uid+'-phone',user_id=uid,credential_hash='a'*64,active=True,created_at=NOW))
   s.add(Entitlement(id='grant',user_id='bob',product='bot',store='apple',transaction_id='tx',expires_at=NOW+timedelta(days=30),verified_at=NOW))
   s.add(BotPool(period='2026-11',budget_nano_usd=1000,reserved_nano_usd=200,spent_nano_usd=400))
   s.add(UsageBucket(user_id='bob',period='2026-11',budget_nano_usd=900,reserved_nano_usd=200,spent_nano_usd=300))
   s.add(Reservation(id='consumed',user_id='bob',period='2026-11',reserved_nano_usd=200,state='uncertain',created_at=NOW))
   s.add(AccountDeletion(account_id='bob',subject_hash='d'*64,receipt_hash='e'*64,created_at=NOW,finished_at=NOW,next_attempt_at=NOW,attempts=0))
  def supplied(conflict=False):
   e=dict(schema_version=1,snapshot_sha256='a'*64,snapshot_at=NOW-timedelta(days=2),cutoff_at=NOW,claimed_complete=True,deletions=[dict(account_id='alice',subject_hash='b'*64,receipt_hash='c'*64,created_at=NOW-timedelta(days=1),finished_at=NOW)],restrictions=[dict(account_id='bob',suspended=True,observed_at=NOW)])
   if conflict:e['deletions'].append(dict(account_id='bob',subject_hash='f'*64,receipt_hash='e'*64,created_at=NOW,finished_at=NOW))
   return BoundRecoveryEvidence.model_validate(dict(reconciliation=e,coverage=[dict(domain=d,snapshot_sha256='a'*64,start_at=e['snapshot_at'],cutoff_at=NOW,artifact_sha256=str(i)*64,claimed_complete=True) for i,d in enumerate(['deletions','restrictions','billing','spend','requests'],1)]))
  try:await reconcile_marked_offline(offline,supplied(True),now=NOW)
  except ValueError as e:assert str(e)=='conflicting deletion receipt identity'
  else:raise AssertionError('conflict accepted')
  async with offline.sessions() as s:
   assert await s.get(User,'alice') is not None;assert (await s.get(Device,'alice-phone')).active
  await denied('failed reconciliation rolls back data and retains durable hold')
  result['report']=await reconcile_marked_offline(offline,supplied(),now=NOW)
  async with offline.sessions() as s:
   assert await s.get(User,'alice') is None;assert (await s.get(User,'bob')).suspended
   assert not (await s.get(Device,'bob-phone')).active
   assert (await s.get(Entitlement,'grant')).verified_at is None
   assert (await s.get(Reservation,'consumed')).state=='uncertain'
   assert (await s.get(BotPool,'2026-11')).reserved_nano_usd==200
  await denied('valid supplied restrictive evidence applies without reopening or erasing uncertain spend')
  app=create_app(settings,database=normal,verifier=Verifier(),store_providers={})
  try:
   async with app.router.lifespan_context(app):raise AssertionError('held API started')
  except RecoveryHoldError:result['checks'].append('held actual API lifespan refuses before listener')
  result['passed']=True
 finally:
  await normal.close();await offline.close()
 (ROOT/'probe-result.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result))
asyncio.run(main())
