"""Evidence-only exact complete-form joins. Never changes dictionary eligibility."""
def form_role_evidence(unit,form,endpoint,lexical_units,aligned_envelope_utf16):
    scope=unit['scope'];a,b=scope['utf16'];text=endpoint['text'].encode('utf-16-le')[2*a:2*b].decode('utf-16-le')
    assert text==scope['text']
    assert aligned_envelope_utf16[0]<=a<b<=aligned_envelope_utf16[1]
    record={'unit_id':unit['unit_id'],'form_id':form['form_id'],'lexeme_id':form['lexeme_id'],'actual_form_utf16':[a,b],'actual_occurrence_text':text,'aligned_envelope_utf16':aligned_envelope_utf16,'envelope_larger_than_form':[a,b]!=aligned_envelope_utf16,'dictionary_reasons_unchanged':list(form['reasons']),'dictionary_complete':form['complete'],'dictionary_pos':form['pos'],'role_status':'unassessable','role':None,'raw_analysis_refs':[]}
    if not form['complete'] or form['mode'] not in (1,2):record['reason']='incomplete_or_unsupported_form';return record
    matched=[u for u in lexical_units if u.get('utf16')==[a,b]]
    record['raw_analysis_refs']=[u['evidence_id'] for u in matched]
    if len(matched)!=1:record['reason']='not_one_exact_lexical_unit';return record
    u=matched[0]
    if u.get('unknown') or u.get('joined_morphemes') or len(u['chosen_roles'])!=1:record['reason']='unknown_joined_or_ambiguous_reading';return record
    record.update(role_status='assessable',role=u['chosen_roles'][0],reason=None)
    return record

def relation_stratum(source_term,target_term,direct_candidate=None):
    if direct_candidate is not None:
        assert direct_candidate['kind']=='direct_english_gloss_candidate' and direct_candidate['source_entry_resolved'] is False
        return 'new_direct_english_unresolved_candidate'
    if source_term['sense_id']!=target_term['sense_id']:return 'no_shared_retained_link'
    return 'old_explicit_shared_link' if source_term['explicit'] and target_term['explicit'] else 'old_nonexplicit_shared_link'

def mechanism_controls():
    # Alignment envelope contains article+adjective; exact noun form remains a noun.
    e={'text':'the red house'};u={'unit_id':'synthetic-unit','scope':{'utf16':[8,13],'text':'house'}};f={'form_id':'synthetic-form','lexeme_id':1,'complete':True,'mode':1,'pos':'noun','reasons':['retained_guard']};ls=[{'utf16':[0,3],'chosen_roles':['DET'],'evidence_id':'det'},{'utf16':[4,7],'chosen_roles':['ADJ'],'evidence_id':'adj'},{'utf16':[8,13],'chosen_roles':['NOUN'],'evidence_id':'noun'}]
    result=form_role_evidence(u,f,e,ls,[0,13]);assert result['role']=='NOUN' and result['dictionary_reasons_unchanged']==['retained_guard'] and result['envelope_larger_than_form']
    assert form_role_evidence(u,f,e,[dict(ls[-1],chosen_roles=['PROPN'])],[0,13])['role']=='PROPN'
    assert form_role_evidence(u,f,e,[dict(ls[-1],unknown=True)],[0,13])['role_status']=='unassessable'
    assert form_role_evidence(u,f,e,[dict(ls[-1],utf16=[4,13])],[0,13])['role_status']=='unassessable'
    return {'controls':4,'passed':True,'scope':'Exact form vs envelope, guards retained, proper-name role retained, unknown/multiword mismatch abstain; no target-specific tests.'}
if __name__=='__main__':
    import json
    print(json.dumps(mechanism_controls()))
