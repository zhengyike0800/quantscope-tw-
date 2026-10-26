"""QuantScope TW free-tier backend. Python 3.10+, no third-party dependencies."""
import csv, io, json, os, time, urllib.request, urllib.parse, urllib.error
from datetime import datetime, timezone, timedelta
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

HERE=Path(__file__).resolve().parent
API_KEY=os.environ.get('FUGLE_API_KEY','').strip()
PORT=int(os.environ.get('PORT','8765'))
REFRESH=max(10,int(os.environ.get('REFRESH_SECONDS','15')))
TOP=5
WATCH=[x.strip() for x in os.environ.get('WATCH_SYMBOLS','2330,2317,2454,2603,2881').split(',') if x.strip()]
WATCH=list(dict.fromkeys(x for x in WATCH if x.isdigit() and 4<=len(x)<=6))[:5]
CACHE={'when':0,'value':None,'error':None}
ELIGIBLE=set()
whitelist=HERE/'eligible_symbols.csv'
if whitelist.exists():
    with whitelist.open(encoding='utf-8-sig') as f:
        ELIGIBLE={r['symbol'].strip() for r in csv.DictReader(f) if r.get('symbol')}

TZ=timezone(timedelta(hours=8))
def pull(symbol):
    url=f'https://api.fugle.tw/marketdata/v1.0/stock/intraday/quote/{symbol}'
    req=urllib.request.Request(url,headers={'X-API-KEY': API_KEY,'User-Agent':'QuantScope-TW/0.3'})
    with urllib.request.urlopen(req,timeout=9) as resp:
        d=json.load(resp)
    d['tradeValue']=(d.get('total') or {}).get('tradeValue',0)
    d['tradeVolume']=(d.get('total') or {}).get('tradeVolume',0)
    return d

def score(s):
    p=s.get('closePrice'); o=s.get('openPrice'); h=s.get('highPrice'); low=s.get('lowPrice')
    vol=s.get('tradeVolume') or 0; val=s.get('tradeValue') or 0
    if not all(isinstance(x,(float,int)) and x>0 for x in (p,o,h,low)): return None
    cp=(p/o-1)*100
    amplitude=(h-low)/o*100
    vposition=(p-low)/(h-low) if h>low else .5
    turnover=val/100000000
    bull=0; bear=0; positives=[]; negatives=[]
    if cp>=.65: bull+=26;positives.append('現價高於開盤價，盤中走勢偏強')
    elif cp<=-.65: bear+=26;negatives.append('現價低於開盤價，盤中走勢偏弱')
    if vposition>=.8:bull+=27;positives.append('股價接近日內高點，買盤相對強勢')
    elif vposition<=.2:bear+=27;negatives.append('股價接近日內低點，賣壓相對明顯')
    if turnover>=4:
        bull+=18;bear+=18
        positives.append('成交金額較高，流動性相對充足')
        negatives.append('成交金額較高，但也需防範快速反轉')
    elif turnover>=1:bull+=10;bear+=10
    if amplitude>=2:bull+=12;bear+=12
    if cp>1.5:bull+=12
    if cp< -1.5:bear+=12
    mx=max(bull,bear)
    side='觀望' if mx<53 or abs(bull-bear)<15 else ('偏多' if bull>bear else '偏空')
    reasons=positives if side=='偏多' else negatives if side=='偏空' else ['多空訊號不足或互相矛盾，先觀望']
    if not ELIGIBLE:
        eligible=None
    else:
        eligible=str(s.get('symbol')) in ELIGIBLE
    if eligible is False:
        side='不符合資格'
        reasons=['未列入已匯入的當沖資格名單；不列為可操作標的']
    # No tradeable prices when unvalidated. Reference only.
    entry=round(p,2)
    raw_dist=max(p*.004, min((h-low)*.4,p*.025))
    stop=round(p-raw_dist if side=='偏多' else p+raw_dist,2)
    target=round(p+raw_dist*1.6 if side=='偏多' else p-raw_dist*1.6,2)
    return {'symbol':str(s.get('symbol','')),'name':s.get('name',''),'price':p,'open':o,'high':h,'low':low,
    'turnoverBillion':round(turnover,2),'volume':vol,'intradayPercent':round(cp,2),
    'dayChangePercent':s.get('changePercent'),'score':min(100,mx),'side':side,
    'eligibility':eligible,'reasons':reasons[:3], 'entry':entry,'stop':stop,'target':target,
    'lastUpdated':s.get('lastUpdated')}

def run_scan():
    now=time.monotonic()
    if CACHE['value'] is not None and now-CACHE['when']<REFRESH: return CACHE['value']
    if not API_KEY:
        return {'mode':'unconfigured','rows':[],'message':'尚未設定 FUGLE_API_KEY；未連接真實行情。','refreshedAt':datetime.now(TZ).isoformat()}
    try:
        raws=[]; stamps=[]; failures=[]
        for symbol in WATCH:
            try:
                data=pull(symbol)
                raws.append(data)
                stamps.append(f"{symbol}:{data.get('date','?')}")
            except urllib.error.HTTPError as ex:
                failures.append(f'{symbol}: HTTP {ex.code}')
            except Exception:
                failures.append(f'{symbol}: 無法取得')
        if not raws:
            raise RuntimeError('所有自選股的 API 請求都失敗：'+', '.join(failures))
        data=[v for x in raws if (v:=score(x))]
        data.sort(key=lambda x:(x['score'],x['turnoverBillion']),reverse=True)
        result={'mode':'live','rows':data[:TOP],'universe':len(raws),'refreshedAt':datetime.now(TZ).isoformat(),
                'sourceTime':' / '.join(stamps),'eligibleListLoaded':bool(ELIGIBLE),'eligibleCount':len(ELIGIBLE),
                'message':('免費版僅監控指定候選股；未匯入當沖資格，不能視為可當沖。' if not ELIGIBLE else '已匯入當沖名單；仍須券商確認當日交易資格。')+(' 部分請求失敗：'+', '.join(failures) if failures else '')}
        CACHE.update(when=now,value=result,error=None)
        return result
    except urllib.error.HTTPError as ex:
        err=f'行情 API 回應 HTTP {ex.code}。請檢查金鑰、方案與呼叫頻率。'
    except Exception as ex:
        err=f'行情暫時無法取得：{type(ex).__name__}。請確認網路與 API 設定。'
    old=CACHE.get('value')
    if old:
        return {**old,'mode':'stale','message':err+' 目前顯示舊資料，請勿當成即時訊號。'}
    return {'mode':'error','rows':[],'message':err,'refreshedAt':datetime.now(TZ).isoformat()}

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(HERE),**kwargs)
    def do_GET(self):
        path=urllib.parse.urlsplit(self.path).path
        if path=='/api/scan':
            body=json.dumps(run_scan(),ensure_ascii=False).encode('utf-8')
            self.send_response(200);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        elif path in ('/','/index.html'):
            self.path='/index.html';super().do_GET()
        elif path=='/health':
            body=b'OK';self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        else:
            self.send_error(404)
if __name__=='__main__':
    print(f'QuantScope TW v0.3: http://localhost:{PORT} API key: {"configured" if API_KEY else "missing"}')
    ThreadingHTTPServer(('0.0.0.0',PORT),Handler).serve_forever()
