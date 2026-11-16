"""Executable additive policy oracle; no translation, eligibility or visibility inference."""
import json,math
from pathlib import Path

def budgets(native_words,density):
    if not isinstance(native_words,int) or native_words<=0 or not math.isfinite(density) or not 0<=density<=.75:raise ValueError('invalid input')
    return (0,0) if density==0 else (max(1,math.floor(native_words*density)),min(native_words,max(1,math.floor(native_words*.75))))

def select(case):
    novel=case['novel_budget'];cap=case['hard_ceiling']
    if not isinstance(novel,int) or not isinstance(cap,int) or novel<0 or cap<0:raise ValueError('invalid budgets')
    if novel==0:return []
    eligible=[c for c in case['candidates'] if c['eligible']]
    if len({c['id'] for c in eligible})!=len(eligible):raise ValueError('duplicate IDs')
    if any(c['start']<0 or c['end']<=c['start'] or c['state'] not in ('seen','unseen') or not isinstance(c.get('cost',1),int) or c.get('cost',1)<1 for c in eligible):raise ValueError('invalid candidate')
    unseen=sorted((c for c in eligible if c['state']=='unseen'),key=lambda c:(c.get('priority',c['start']),c['start'],c['end'],c['id']))
    seen=sorted((c for c in eligible if c['state']=='seen'),key=lambda c:(not c['due'],c['start'],c['end'],c['id']))
    chosen=[];used=0;new_used=0
    def add(c):
        nonlocal used,new_used
        cost=c.get('cost',1)
        if used+cost>cap or (c['state']=='unseen' and new_used+cost>novel) or any(c['start']<x['end'] and x['start']<c['end'] for x in chosen):return False
        chosen.append(c);used+=cost
        if c['state']=='unseen':new_used+=cost
        return True
    for c in unseen:
        if add(c):break
    for c in seen:add(c)
    for c in unseen:add(c)
    return [x['id'] for x in sorted(chosen,key=lambda c:(c['start'],c['end'],c['id']))]

if __name__=='__main__':
    fixture=json.loads(Path(__file__).with_name('fixtures.json').read_text())
    for case in fixture['cases']:
        result=select(case)
        assert result==case['expected'],(case['id'],result,case['expected'])
    for case in fixture['budget_cases']:assert budgets(case['native_words'],case['density'])==(case['novel_budget'],case['hard_ceiling'])
    for message in fixture['day_progression']['messages']:
        b,c=budgets(fixture['day_progression']['native_words'],fixture['day_progression']['density'])
        cases=[dict(x,start=i*2,end=i*2+1,due=x['state']=='seen',eligible=True) for i,x in enumerate(message['candidates'])]
        assert select({'novel_budget':b,'hard_ceiling':c,'candidates':cases})==message['expected']
    for case in fixture['exposure_cases']:
        seen={}
        for event in case['events']:
            if event['kind']=='visible_dwell':
                last,count=seen.get(event['identity'],(-1,0))
                if event['day']>last:seen[event['identity']]=(event['day'],count+1)
        key=case.get('query_identity',case['events'][0]['identity']);v=seen.get(key)
        assert (v[0] if v else None)==case['expected_last_day']
        if 'expected_exposure_days' in case:assert v[1]==case['expected_exposure_days']
    print(f"{len(fixture['cases'])} selection, {len(fixture['budget_cases'])} budget, {len(fixture['day_progression']['messages'])} progression and {len(fixture['exposure_cases'])} exposure cases pass; policy oracle only")
