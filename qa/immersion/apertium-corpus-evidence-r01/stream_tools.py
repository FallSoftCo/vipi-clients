"""Exact parser functions retained from frozen32pair comparison; no inference."""
import re

def split_escaped(s,delimiter):
 parts=[];last=0;escape=False
 for i,ch in enumerate(s):
  if escape:escape=False;continue
  if ch=='\\':escape=True;continue
  if ch==delimiter:parts.append(s[last:i]);last=i+1
 parts.append(s[last:]);return parts

def unescape(s):return re.sub(r'\\(.)',r'\1',s)

def lexical_units(stream):
 units=[];begin=None;escape=False
 for i,ch in enumerate(stream):
  if escape:escape=False;continue
  if ch=='\\':escape=True;continue
  if ch=='^':assert begin is None;begin=i+1
  elif ch=='$' and begin is not None:
   fields=split_escaped(stream[begin:i],'/');assert len(fields)>=2;units.append({'surface':unescape(fields[0]),'readings':fields[1:],'raw':stream[begin-1:i+1]});begin=None
 assert begin is None;return units

def map_units(stream,text):
 cursor=0;lost=False;units=lexical_units(stream)
 for u in units:
  surface=u['surface'];start=text.find(surface,cursor)
  if lost or start<0:
   u['mapping']='unmatched_or_after_mapping_loss';u['codepoints']=None
   if text[cursor:].strip():lost=True
   continue
  if text[cursor:start].strip():
   u['mapping']='nonblank_gap_mapping_loss';u['codepoints']=None;lost=True;continue
  end=start+len(surface);u.update(mapping='exact_surface',codepoints=[start,end],utf16=[len(text[:z].encode('utf-16-le'))//2 for z in (start,end)]);cursor=end
 return units

def reading_role(reading,mapping):
 if reading.startswith('*'):return 'UNKNOWN'
 if len(split_escaped(reading,'+'))!=1:return 'UNASSESSABLE_JOINED_MORPHEMES'
 tags=re.findall(r'<([^>]+)>',reading)
 return mapping.get(tags[0],'UNMAPPED_TAG') if tags else 'UNMAPPED_TAG'
