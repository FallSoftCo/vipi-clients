from pathlib import Path
import datetime, hashlib, json, os
helper=Path('/Users/Apple/Development/vipi-native-delivery-20261109-r01/distribution-archive-r01/interactive-keychain-status-r01.py')
out=helper.parents[1]/'keychain-status-final-r02-raw.json'
assert not out.exists()
namespace={}
exec(compile(helper.read_text().split('result=')[0],str(helper),'exec'),namespace)
result={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'uid':os.getuid(),'context':'bounded SSH native Apple user','helper_sha256':hashlib.sha256(helper.read_bytes()).hexdigest(),'operation':'SecKeychainOpen + SecKeychainGetStatus + CFRelease only','keychains':namespace['r'],'unlock_signing_export_or_mutation_attempted':False,'signing_authorized':False}
raw=json.dumps(result,indent=2)+'\n'
with out.open('x') as stream:
 stream.write(raw);stream.flush();os.fsync(stream.fileno())
print(raw,end='',flush=True)
