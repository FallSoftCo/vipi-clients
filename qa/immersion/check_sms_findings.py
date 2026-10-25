#!/usr/bin/env python3
"""Bind explicit diagnostic assessments to actual observed native spans."""
import argparse
from collections import Counter
import json
from pathlib import Path
from conversation_corpus import sha_file,write_json


def check(report,assessment):
    rows={(p['source']+'-'+p['target'],r['id']):r for p in report['results'] for r in p['samples']}
    if assessment['assessment_kind']!='author_assessment' or assessment['training_use'] is not False:
        raise ValueError('Diagnostic origin required')
    seen=set()
    for finding in assessment['findings']:
        identity=(finding['pair'],finding['case'],finding['source'],finding['target'])
        if identity in seen:raise ValueError('Duplicate assessment')
        seen.add(identity);row=rows[(finding['pair'],finding['case'])]
        if not any(s['original']==finding['source'] and s['translated']==finding['target'] for s in row['spans']):
            raise ValueError('Assessed substitution was not displayed by the native strict pipeline')
    return dict(Counter(f['category'] for f in assessment['findings']))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('report','assessment','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();assessment=json.loads(a.assessment.read_text());report=json.loads(a.report.read_text())
    if a.output.exists():raise ValueError('Preserve receipt')
    if sha_file(a.report)!=assessment['report_sha256']:raise ValueError('Wrong observed report')
    categories=check(report,assessment)
    result={'schema':'vipi-sms-diagnostic-findings-check-1','report_sha256':sha_file(a.report),
        'assessment_sha256':sha_file(a.assessment),'confirmed_observed_spans':len(assessment['findings']),
        'categories':categories,'accuracy_estimate':None,'linguistic_acceptance':False,
        'scope':'Mechanical evidence binding of explicit author diagnostic assessments; not an accuracy sample'}
    write_json(a.output,result);print(json.dumps(result))
