#!/usr/bin/env python3
"""First project-authored development batch; no linguistic approval asserted.

These examples seed a growing catalog, never an independent acceptance corpus.
Pairs share explicit meanings. Only the focus is a replacement candidate; words
outside it (including pronouns/possessors) remain the user's original text.
"""
import argparse
import json
from pathlib import Path
from build_wiktextract import canonical
from mapping_catalog import validate

AUTHOR='Codex session 01a16e0d-ac69-7dd0-872a-8cf087160515'
FORMS={
 'coffee':{'en':('coffee',''),'es':('café',''),'fr':('café',''),'de':('Kaffee',''),
   'it':('caffè',''),'pt':('café',''),'ar':('قهوة','qahwa'),'zh':('咖啡','kāfēi'),
   'ja':('コーヒー','kōhī'),'ko':('커피','keopi')},
 'water':{'en':('water',''),'es':('agua',''),'fr':('eau',''),'de':('Wasser',''),
   'it':('acqua',''),'pt':('água',''),'ar':('ماء',"mā'"),'zh':('水','shuǐ'),
   'ja':('水','mizu'),'ko':('물','mul')},
 'bread':{'en':('bread',''),'es':('pan',''),'fr':('pain',''),'de':('Brot',''),
   'it':('pane',''),'pt':('pão',''),'ar':('خبز','khubz'),'zh':('面包','miànbāo'),
   'ja':('パン','pan'),'ko':('빵','ppang')},
 'tea':{'en':('tea',''),'es':('té',''),'fr':('thé',''),'de':('Tee',''),
   'it':('tè',''),'pt':('chá',''),'ar':('شاي','shāy'),'zh':('茶','chá'),
   'ja':('お茶','ocha'),'ko':('차','cha')},
}
MEANINGS={'coffee':'coffee as a beverage, not the plant or a cafe establishment',
          'water':'water requested for drinking, not a verb or a body of water',
          'bread':'bread as food, not money or a verb',
          'tea':'tea as a beverage, not the meal or the plant'}


def context(language, concept, form):
    templates={'en':'I want {}.','es':'Quiero {}.','fr':'Je veux du {}.',
       'de':'Ich will {}.','it':'Voglio del {}.','pt':'Quero {}.',
       'ar':'أريد {}.','zh':'我想要{}。','ja':'{}が欲しいです。','ko':'{}를 원해요.'}
    if language=='fr' and concept=='water': return 'Je veux de l’eau.'
    if language=='it' and concept=='water': return 'Voglio dell’acqua.'
    if language=='ko' and concept in ('water','bread'): return form+'을 원해요.'
    # These indefinite Arabic objects retain the written accusative ending;
    # the lexical focus excludes it, just as Korean case particles stay outside.
    if language=='ar' and concept in ('bread','tea'): return 'أريد '+form+'ًا.'
    return templates[language].format(form)


def mapping(identity,source,target,left,right,original,translation,meaning,reading=''):
    if original.count(left)!=1 or translation.count(right)!=1: raise ValueError('Unique authored focus required')
    a=original.index(left); b=translation.index(right)
    value={'schema':'vipi-contextual-mapping-1','logical_id':'vipi-authored-r1:'+identity+':'+source+'-'+target,
        'source_language':source,'target_language':target,'source':left,'target':right,'reading':reading,
        'source_context':original,'target_context':translation,
        'source_span':[a,a+len(left)],'target_span':[b,b+len(right)],'meaning':meaning,
        'usage':{'scope':'lexical_focus_only','context_generalization':'requires_evaluation',
                 'preserve_outside_focus':['pronouns','possessors','names','numbers','negation']},
        'provenance':{'author':AUTHOR,'license':'FallSoft.Co project-authored; unpublished',
                      'kind':'generated_development_seed','independent_acceptance_data':False}}
    if source=='en' and identity.startswith('book'):
        value['usage']['context_generalization']='finite-authored-variants; requires evaluation'
        value['usage']['context_pattern']=[{'literal':'Can '},{'slot':['you','they','we']},
            {'literal':' bring '},{'slot':['my','your','their','our']},{'literal':' '},
            {'focus':left},{'literal':'?'}]
    validate(value); return value


def records():
    for concept,forms in FORMS.items():
        for source,(left,_) in forms.items():
            for target,(right,reading) in forms.items():
                if source==target: continue
                yield mapping(concept,source,target,left,right,context(source,concept,left),context(target,concept,right),MEANINGS[concept],reading)
    for identifier,english,spanish,left,right in [
        ('book_my','Can you bring my book?','¿Puedes traer mi libro?','book','libro'),
        ('book_your','Can you bring your book?','¿Puedes traer tu libro?','book','libro'),
        ('books_their','Can they bring their books?','¿Pueden traer sus libros?','books','libros'),
        ('route_you','Can you buy bread on the way home?','¿Puedes comprar pan de camino a casa?','on the way home','de camino a casa'),
        ('route_me','I bought bread on the way home.','Compré pan de camino a casa.','on the way home','de camino a casa')]:
        meaning='books as physical reading material; ownership outside focus' if identifier.startswith('book') else 'while travelling toward home; actor determined outside focus'
        yield mapping(identifier,'en','es',left,right,english,spanish,meaning)
        yield mapping(identifier,'es','en',right,left,spanish,english,meaning)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True); args=parser.parse_args()
    values=list(records())
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as output:
        for value in values: output.write(canonical(value)+'\n')
    print(json.dumps({'records':len(values),'pairs':len({(x['source_language'],x['target_language']) for x in values}),
                      'linguistic_acceptance':False,'author':AUTHOR}))
