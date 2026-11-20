from pathlib import Path
from html import escape
import datetime,hashlib,json,os,re,shutil
from PIL import Image,ImageOps
from collections import Counter
root=Path('/home/ai/Development/8bar-houdini/output');key='vipi-studio-20261120'
out=root/key;out.mkdir(exist_ok=True,mode=0o755)
lib=Path('/home/ai/Development/vipi-design-references/vipi');build=Path('/mnt/extradrive1/vipi-builds')
sections=[]
source_times={}

def section(slug,title,description,items):
    media=[]
    for label,path in items:
        if not path.is_file():continue
        assert path.suffix.lower() in {'.svg','.jpg','.jpeg','.png','.webp','.mp4','.pdf'},path
        folder=out/slug;folder.mkdir(exist_ok=True,mode=0o755)
        dest=folder/path.name
        if dest.is_file() and dest.read_bytes()==path.read_bytes():pass
        else:
            tmp=dest.with_name('.'+dest.name+'.tmp');shutil.copyfile(path,tmp);tmp.chmod(0o644);os.replace(tmp,dest)
        source_times[dest] = path.stat().st_mtime
        media.append((label,dest))
    if media:sections.append((slug,title,description,media))

logo=lib/'logo-craft-20261120-r01'
section('logo-concepts','Two handcrafted logo concepts','Woven Reply and Reply Seal are original vector studies. Each is shown enlarged and at launcher size.',[
    ('Compare both concepts',logo/'candidates-early-r01.png'),('Woven Reply',logo/'concept-a-rich.png'),('Editable Woven Reply artwork',logo/'concept-a-rich.svg'),('Reply Seal',logo/'concept-b-rich.png'),('Editable Reply Seal artwork',logo/'concept-b-rich.svg')])
theme=lib/'palette-power-20261120-r01'
section('palette','Ultramarine and vermilion','Two color studies on the same Vipi layouts. The ultramarine direction uses apricot for practice words.',[
    ('Compare the two palettes',theme/'comparison.png')]+[(f'{v.title()} · {scene} · {mode}',theme/f'{v}-{kind}-{mode}-study.png') for v in ['ultramarine','vermilion'] for scene,kind in [('Inbox','list'),('Conversation','chat')] for mode in ['light','dark']]+[('Earlier flat V color study',theme/'brand-existing-v.png'),('Flat V source artwork',theme/'brand-existing-v.svg')])
native=lib/'native-ultramarine-android';run=build/'inbox-review-v15-r01/run-122/journey-ui-122'
section('android-theme','Android · ultramarine in the native app','Native emulator captures with controlled conversations. The paragraph samples exercise practice and playback highlights.',[
    ('Inbox, chat and word highlights',native/'native-inbox-and-chat.jpg')]+[(f'{area} · {file.stem.split("-",1)[-1].replace("-"," ")}',file) for area,sub in [('Inbox','inbox-populated'),('First conversation','inbox-empty'),('Chat','chat-theme'),('Word highlights','palette-paragraphs')] for file in sorted((run/sub).glob('*.png'))])
q=build/'ios-chat-polish-review-r02'
section('ios-inbox','iPhone · inbox and notification permission','Native layout review with test conversations at default and largest text sizes, plus the first-reply permission flow.',[
    ('Populated conversation list',q/'inbox-default--native-inbox-populated.png')]+[(f.stem.replace('--',' · ').replace('-',' '),f) for f in sorted(q.glob('*.png')) if f.name!='inbox-default--native-inbox-populated.png' and not f.name.startswith('chat-polish-failure')])
section('earlier-chat','Chat layout and Mandarin immersion','Earlier native Android chat review, including hold to reveal the original and double tap to switch scripts.',[('Chat in light and dark',lib/'chat-day-night.png'),('Chinese script and pinyin gestures',lib/'mandarin-gesture-demo.mp4'),('Friend typing',lib/'android-typing.png'),('New reply while reading history',lib/'android-new-message.png'),('First-send invitation',lib/'android-first-reply.png'),('Return to the keyboard',lib/'android-after-opt-in.png')])
# New reviewed batches can be added without regenerating unrelated cards.
extra=build/'gallery-publication-r01'/'batches.json'
if extra.exists():
    for batch in json.loads(extra.read_text()):section(batch['slug'],batch['title'],batch['description'],[(i['label'],Path(i['path'])) for i in batch['items']])
meta=root/'catalog-extras'/(key+'.json')
prior={c['id']:c for c in (json.loads(meta.read_text()) if meta.exists() else [])}
cards=[]; review=[]
def atomic(path,data):
    tmp=path.with_name('.'+path.name+'.tmp')
    if path.is_file() and path.read_bytes()==data:return
    tmp.write_bytes(data);tmp.chmod(0o644);os.replace(tmp,path)
def stamp(ts):
    return datetime.datetime.fromtimestamp(ts,datetime.timezone.utc).isoformat()
for slug,title,desc,items in sections:
    card_id='vipi-studio-'+slug
    label,poster=items[0]; img=Image.open(poster);w,h=img.size
    path=lambda f:str(f.relative_to(root))
    downloads=[dict(label=n,path=path(f)) for n,f in items]
    for d, (_, f) in zip(downloads, items): d['bytes']=f.stat().st_size
    digest=hashlib.sha256(''.join(hashlib.sha256(f.read_bytes()).hexdigest() for _,f in items).encode()).hexdigest()
    prev=prior.get(card_id,{})
    updated=stamp(max(source_times[f] for _,f in items))
    card=dict(id=card_id,brand='Vipi',collection='vipi',group='Vipi · native design review',title='Vipi · '+title,updatedAt=updated,ready=True,finalReady=False,customerReady=False,privateQaOnly=True,marketingApproved=False,staticPoster=True,seconds=0,poster=path(poster),width=w,height=h,aspect='portrait' if h>w else 'wide' if w>h else 'square',craft='Vipi design',font='Native interface and original artwork',theme=desc,playbackLabel='Design review',interactivePreview=key+'/review.html#'+slug,note=desc,downloads=downloads,vipiContentHash=digest)
    cards.append(card)
    thumb=poster.parent/'gallery-preview.webp'
    # Static poster is displayed at moderate size. All originals stay available.
    ImageOps.contain(img.convert('RGB'),(960,800)).save(thumb,'WEBP',quality=85);thumb.chmod(0o644)
    links=''.join('<li><a href="'+escape(str(f.relative_to(out)),quote=True)+'">'+escape(n)+'</a></li>' for n,f in items)
    review.append((updated,slug, '<article id="'+slug+'"><a href="'+escape(str(poster.relative_to(out)))+'"><img alt="'+escape(title)+'" src="'+escape(str(thumb.relative_to(out)))+'"></a><h2>'+escape(title)+'</h2><p>'+escape(desc)+'</p><ul>'+links+'</ul></article>'))
ordered=sorted(review,key=lambda v:v[0],reverse=True)
intro='<!doctype html><html lang="en"><meta name="viewport" content="width=device-width, initial-scale=1"><meta charset="utf-8"><title>Vipi design gallery</title><style>:root{color-scheme:light dark;font:16px/1.5 system-ui,sans-serif}body{margin:0 auto;max-width:1080px;padding:24px}h1{font-size:2.2rem}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(315px,100%),1fr));gap:28px}article{min-width:0}article img{width:100%;height:245px;object-fit:contain;background:light-dark(#efede8,#171a28);border-radius:12px}h2{line-height:1.2;font-size:1.35rem}a{color:light-dark(#293fbc,#bac6ff)}ul{padding-left:20px}li{margin:.25rem 0}</style><header><a href="/8bar/">NextComp Gallery</a><h1>Vipi design gallery</h1><p>Native builds, design studies and editable logo artwork. <a href="https://mobbin.com/collections/c5a5bb7e-8d36-41e2-92e3-12605fc17cc6/mobile/screens">Private Mobbin references</a></p></header><main>'
atomic(out/'index.html',(intro+''.join(x[2] for x in ordered)+'</main></html>').encode())
atomic(out/'review.html',(out/'index.html').read_bytes())
atomic(meta,(json.dumps(cards,indent=2,ensure_ascii=False)+'\n').encode())
print(len(cards),'cards,',sum(len(c['downloads']) for c in cards),'original downloads.')
