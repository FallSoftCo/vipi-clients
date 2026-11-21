"""Isolated subprocess fixture for abrupt upload worker-loss qualification.

Never imported by the application. Only a caller-supplied loopback listening FD,
private test schema/storage and synthetic verifier are used.
"""
import json
import os
import sys
import uvicorn
from conftest import NOW
from test_api import TestVerifier
from vipi.api import create_app
from vipi.config import Settings
from vipi.db import Database
from vipi import media

spec=json.loads(sys.argv[1])
db=Database(spec['database_url'],connect_args={'server_settings':{'search_path':spec['schema']}})
settings=Settings(database_url=spec['database_url'],workos_client_id='client_fixture',
    workos_issuer='https://api.workos.com',service_secret='a'*43,
    media_enabled=True,media_storage_path=spec['storage'],media_max_bytes=512*1024,media_owner_bytes=1024*1024,
    media_global_bytes=spec.get('global_bytes', 1 << 30),
    media_global_blobs=spec.get('global_blobs', 8192))
if spec['crash_after_finalize']:
    original=media.os.replace
    def lost_worker(source,destination,**kwargs):
        original(source,destination,**kwargs)
        if str(destination).endswith('.ciphertext'):
            os._exit(87)
    media.os.replace=lost_worker
app=create_app(settings,database=db,verifier=TestVerifier(),clock=lambda:NOW)
uvicorn.run(app,fd=int(spec['fd']),access_log=False,log_level='warning')
