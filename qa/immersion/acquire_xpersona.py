#!/usr/bin/env python3
"""Acquire pinned conversation research text and licenses, never app mappings."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

REVISION='1da049a1bbf3b01548f98cc23ba75ef871416e50'
LANGUAGES={'En':'en','Fr':'fr','It':'it','Jp':'ja','Ko':'ko','Zh':'zh'}
API='https://api.github.com/repos/'


def request(url):return urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Vipi-corpus-research'}),timeout=60)


def metadata(url):
    with request(url) as response:return json.load(response)


def blob(data):return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()


def acquire(output):
    output.mkdir(parents=True,exist_ok=True)
    receipt=output/'acquisition.json'
    if receipt.exists():raise ValueError('Preserve completed acquisition receipt')
    tree=metadata(API+'HLTCHKUST/Xpersona/git/trees/'+REVISION+'?recursive=1')
    if tree.get('truncated'):raise ValueError('Truncated repository tree')
    entries={row['path']:row for row in tree['tree'] if row['type']=='blob'}
    names=['LICENSE','README.md','dataset/README.md']
    for code in LANGUAGES:
        names.extend(['dataset/'+code+'_persona_'+suffix+'.json' for suffix in
            (['train','valid','test'] if code=='En' else ['train_corrected','split_valid_human_annotated','split_test_human_annotated'])])
    total=sum(entries[name]['size'] for name in names)
    if total>190_000_000:raise ValueError('Pinned acquisition exceeds declared disk allowance')
    files=[]
    for name in names:
        item=entries[name];path=output/name;path.parent.mkdir(parents=True,exist_ok=True)
        url='https://raw.githubusercontent.com/HLTCHKUST/Xpersona/'+REVISION+'/'+name
        if not path.exists():
            temporary=path.with_suffix(path.suffix+'.partial')
            try:
                with request(url) as response,temporary.open('wb') as stream:
                    received=0
                    while chunk:=response.read(65536):
                        received+=len(chunk)
                        if received>item['size']:raise ValueError('Unexpected upstream file size')
                        stream.write(chunk)
                data=temporary.read_bytes()
                if len(data)!=item['size'] or blob(data)!=item['sha']:raise ValueError('Upstream blob mismatch')
                temporary.rename(path)
            finally:temporary.unlink(missing_ok=True)
        data=path.read_bytes()
        if len(data)!=item['size'] or blob(data)!=item['sha']:raise ValueError('Changed cached source: '+name)
        files.append({'path':name,'url':url,'bytes':len(data),'git_blob':item['sha'],'sha256':hashlib.sha256(data).hexdigest()})
    base_revision=metadata(API+'facebookresearch/ParlAI/commits/main')['sha']
    base_path='parlai/tasks/personachat/LICENSE_DOCUMENTATION'
    license_url='https://raw.githubusercontent.com/facebookresearch/ParlAI/'+base_revision+'/'+base_path
    with request(license_url) as response:license_bytes=response.read(65537)
    if len(license_bytes)>65536 or not license_bytes.startswith(b'Attribution 4.0 International'):raise ValueError('Unexpected base dataset license')
    (output/'PERSONACHAT-LICENSE-CC-BY-4.0.txt').write_bytes(license_bytes)
    result={'schema':'vipi-xpersona-acquisition-1','repository':'https://github.com/HLTCHKUST/Xpersona','revision':REVISION,
        'languages':list(LANGUAGES.values()),'bytes':total,'files':files,
        'license_evidence':{'repository_license':'MIT, CAiRE 2020; retained repository license',
            'underlying_personachat_license':'CC BY 4.0; retain original authors and attribution',
            'base_license_url':license_url,'base_license_sha256':hashlib.sha256(license_bytes).hexdigest()},
        'paper':'https://aclanthology.org/2021.nlp4convai-1.10/',
        'limits':['Crowdsourced personas; not organic private friend conversations.',
            'Non-English training text is machine translated with iterative human correction.',
            'Human validation/test annotators could adapt content; row positions are not exact translation gold.',
            'Official test data reserved; acquisition is not linguistic assessment or app-pack incorporation.'],
        'release_ready':False}
    with receipt.open('x') as stream:json.dump(result,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print(json.dumps({'revision':REVISION,'files':len(files),'bytes':total,'receipt_sha256':hashlib.sha256(receipt.read_bytes()).hexdigest()}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    acquire(p.parse_args().output)
