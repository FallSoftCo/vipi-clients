#!/usr/bin/env python3
"""Pure stdlib unit economics; explicit assumptions, no provider access."""
import argparse,itertools,json,math
from pathlib import Path

def calculate(*,messages_per_day,cloud_fraction,input_tokens,output_tokens,input_per_million,output_per_million,calls_per_cloud_message,paid_days,trial_days,conversion,commission,vat,margin,non_inference,annual_price):
 for v in [messages_per_day,input_tokens,output_tokens,input_per_million,output_per_million,calls_per_cloud_message,paid_days,trial_days,non_inference,annual_price,vat]:
  if not math.isfinite(v) or v<0:raise ValueError('finite nonnegative input required')
 for v in [cloud_fraction,commission,margin]:
  if not math.isfinite(v) or not 0<=v<=1:raise ValueError('fraction outside [0,1]')
 if not 0<conversion<=1 or commission==1 or margin==1:raise ValueError('conversion/commission/margin denominator invalid')
 percall=(input_tokens*input_per_million+output_tokens*output_per_million)/1e6
 permessage=percall*calls_per_cloud_message
 service_days=paid_days+trial_days/conversion
 paid_inference=messages_per_day*cloud_fraction*permessage*paid_days
 trial_inference=messages_per_day*cloud_fraction*permessage*trial_days/conversion
 cost=paid_inference+trial_inference+non_inference
 net=annual_price/(1+vat)*(1-commission)
 capacity=max(0,net*(1-margin)-non_inference)
 denominator=service_days*cloud_fraction*permessage
 return {'per_call_usd':percall,'paid_inference_usd':paid_inference,'trial_inference_allocated_per_payer_usd':trial_inference,'effective_usage_days_per_payer':service_days,'inference_usd':paid_inference+trial_inference,'non_inference_usd':non_inference,'total_variable_cost_usd':cost,'net_store_receipt_usd':net,'contribution_margin':(net-cost)/net if net else None,'target_margin_met':net*(1-margin)>=cost,'minimum_gross_annual_price_usd':cost/(1-margin)*(1+vat)/(1-commission),'max_messages_per_day_at_target_margin':capacity/denominator if denominator else None,'inference_budget_usd_at_target_margin':capacity}

def run(config):
 rows=[];a=config['assumptions'];axes=config['axes']
 keys=list(axes)
 for values in itertools.product(*(axes[k] for k in keys)):
  s=dict(zip(keys,values));rate=config['rates'][s['rate_period']]
  args={**a,**{k:v for k,v in s.items() if k!='rate_period'},**rate}
  rows.append({'scenario':s,'result':calculate(**args)})
 return {'schema':'vipi-cost-results-1','assumptions':a,'rows':rows,'scope':'Assumed token usage and conversion, not measured demand; no translation-quality or unlimited-service guarantee.'}

def selftest():
 a=dict(messages_per_day=50,cloud_fraction=1,input_tokens=200,output_tokens=60,input_per_million=.3,output_per_million=1.2,calls_per_cloud_message=1,paid_days=365,trial_days=30,conversion=1,commission=.15,vat=0,margin=.6,non_inference=1,annual_price=12)
 r=calculate(**a);assert math.isclose(r['per_call_usd'],.000132);assert math.isclose(r['paid_inference_usd'],2.409);assert math.isclose(r['trial_inference_allocated_per_payer_usd'],.198)
 q=calculate(**{**a,'conversion':.25});assert math.isclose(q['trial_inference_allocated_per_payer_usd'],.792)
 q=calculate(**{**a,'cloud_fraction':.2,'calls_per_cloud_message':3});assert math.isclose(q['inference_usd'],r['inference_usd']*.6)
 q=calculate(**{**a,'vat':.2});assert math.isclose(q['net_store_receipt_usd'],8.5)
 q=calculate(**{**a,'annual_price':r['minimum_gross_annual_price_usd']});assert math.isclose(q['contribution_margin'],.6)
 q=calculate(**{**a,'cloud_fraction':0});assert q['inference_usd']==0 and q['max_messages_per_day_at_target_margin'] is None
 for field,value in [('conversion',0),('commission',1),('margin',1),('input_tokens',-1)]:
  try:calculate(**{**a,field:value})
  except ValueError:pass
  else:raise AssertionError(field)
 return {'passed':True,'checks':['known token arithmetic','trial conversion allocation','cloud/amplification scaling','VAT before store fee','price inversion','zero cloud boundary','invalid denominators/nonnegative values']}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('config',type=Path,nargs='?');p.add_argument('--output',type=Path);p.add_argument('--self-test',action='store_true');args=p.parse_args()
 if args.self_test:print(json.dumps(selftest(),indent=2))
 else:
  if not args.config:p.error('config required')
  result=run(json.loads(args.config.read_text()));text=json.dumps(result,indent=2)+'\n'
  if args.output:
   with args.output.open('x') as f:f.write(text)
  else:print(text,end='')
