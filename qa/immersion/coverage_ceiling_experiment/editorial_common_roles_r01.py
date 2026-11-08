"""One occurrence-eligibility stage shared by old and editorial candidates.

Research only. These are explicit local role clues, not a complete English parser.
Role approval never asserts the chosen lexical sense is correct in this context.
"""
from evaluate_reviewed_words import WORD, PROTECTED
from evaluate_source_concepts import DETERMINERS, PREPOSITIONS, OBJECT_VERBS

COPULA=set('am is are was were be been being seem seems seemed feel feels felt look looks looked sound sounds sounded become becomes became'.split())
PRONOUN=set('i you he she it we they'.split())
DEGREE=set('very really quite so too more most less least pretty extremely rather especially fairly'.split())
AUX=set('do does did can could should would will may might must shall'.split())
NEG_AUX={"don't","doesn't","didn't","can't","couldn't","shouldn't","wouldn't","won't","cannot"}
VERB_ADV=set('really always often sometimes usually never also still just probably certainly actually'.split())

def context(text,tokens,index,capitalized_homographs=()):
 t=tokens[index];initial=not text[:t.start()].strip() or text[:t.start()].rstrip()[-1:] in '.!?'
 common=None
 if any(m.start()<t.end() and t.start()<m.end() for m in PROTECTED.finditer(text)):common='protected_literal'
 elif any(x in text for x in ('"','“','”','`')):common='quoted_or_code_message'
 elif t.group().isupper() and len(t.group())>1:common='uppercase_identifier'
 elif t.group()[0].isupper() and not initial:common='mid_sentence_capital'
 elif t.group()[0].isupper() and t.group().casefold() in capitalized_homographs:common='attested_capitalized_homograph'
 left=index
 while left and not text[tokens[left-1].end():tokens[left].start()].strip():left-=1
 right=index+1
 while right<len(tokens) and not text[tokens[right-1].end():tokens[right].start()].strip():right+=1
 words=lambda ts:[t.group().casefold().replace('’',"'") for t in ts]
 return {'before':words(tokens[left:index]),'after':words(tokens[index+1:right]),'initial':initial,'common_rejection':common,'word':t.group().casefold().replace('’',"'")}

def eligible(ctx,pos,source_roles,form_kind='canonical'):
 if ctx['common_rejection']:return False,ctx['common_rejection']
 before,after=ctx['before'],ctx['after'];prev=before[-1] if before else None;next_word=after[0] if after else None
 if pos=='noun':
  # A short attested adjective chain may sit inside a noun phrase.
  prefix=before[:]
  for _ in range(3):
   if prefix and 'adj' in source_roles.get(prefix[-1],set()):prefix.pop()
   else:break
  anchor=prefix[-1] if prefix else None
  allowed=anchor in DETERMINERS|PREPOSITIONS|OBJECT_VERBS
  allowed|=bool(ctx['initial'] and next_word in COPULA)
  allowed|=not before and not after
  return bool(allowed),'noun_role_unresolved' if not allowed else 'noun_role'
 if pos=='adj':
  if ctx['word'] in DEGREE and 'adj' in source_roles.get(next_word,set()):return False,'degree_adverb_role'
  allowed=prev in COPULA|DEGREE
  allowed|=bool('noun' in source_roles.get(next_word,set()) and (ctx['initial'] or prev in DETERMINERS|DEGREE))
  allowed|=not before and not after
  return bool(allowed),'adjective_role_unresolved' if not allowed else 'adjective_role'
 if pos=='verb':
  prefix=before[:]
  for _ in range(2):
   if prefix and prefix[-1] in VERB_ADV|NEG_AUX|{'not','do','does','did'}:prefix.pop()
   else:break
  subject=prefix[-1] if prefix and prefix[-1] in PRONOUN else None
  preceding=prefix[-2] if subject and len(prefix)>1 else None
  allowed=prev=='to' or prev in AUX|NEG_AUX or bool(subject and preceding not in COPULA)
  # Inflected finite forms are never inferred from a bare-verb rule.
  return bool(allowed),'verb_role_unresolved' if not allowed else 'verb_role'
 if pos=='adv':return True,'existing_adverb_role'
 return False,'unqualified_content_pos'
