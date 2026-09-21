"""Local-only, authoritative Dou Dizhu server. One GPU model, isolated rounds."""
import argparse
import json
import os
from pathlib import Path
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import webbrowser
from ddz.game import Game
from ddz.strategy import Policy, evaluate

os.environ['HF_HUB_OFFLINE']='1'
os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
ROOT=Path(__file__).resolve().parent


class Session:
    def __init__(self):
        self.game=Game()
        self.lock=threading.Lock()
        self.touched=time.monotonic()


class Server(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,address,policy):
        super().__init__(address,Handler)
        self.policy=policy
        self.gpu_lock=threading.Lock()
        self.sessions={}
        self.sessions_lock=threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def log_message(self,format,*args):
        # No card prompts or session tokens in terminal logs.
        pass

    def respond(self,status,data):
        payload=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(payload)))
        self.send_header('Cache-Control','no-store')
        self.end_headers()
        self.wfile.write(payload)

    def local_request(self):
        host=self.headers.get('Host','')
        allowed={f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
        return host in allowed and self.headers.get('Origin',f'http://{host}')==f'http://{host}'

    def do_GET(self):
        if not self.local_request():
            return self.respond(403,{'error':'仅接受本机同源请求。'})
        if self.path=='/api/health':
            return self.respond(200,{'ready':True,'model':'Laya multilingual · 322M · FP16'})
        paths={'/':'index.html','/style.css':'style.css','/app.js':'app.js'}
        if self.path not in paths:
            return self.respond(404,{'error':'页面不存在。'})
        path=ROOT/'web'/paths[self.path]
        payload=path.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type',{'html':'text/html; charset=utf-8','css':'text/css; charset=utf-8','js':'text/javascript; charset=utf-8'}[path.suffix[1:]])
        self.send_header('Content-Length',str(len(payload)))
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        if not self.local_request():
            return self.respond(403,{'error':'仅接受本机同源请求。'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=8192:
                raise ValueError('请求大小不正确。')
            body=json.loads(self.rfile.read(length))
            if not isinstance(body,dict):
                raise ValueError('请求格式不正确。')
        except (ValueError,UnicodeDecodeError):
            return self.respond(400,{'error':'请求格式不正确。'})
        if self.path=='/api/new':
            with self.server.sessions_lock:
                now=time.monotonic()
                self.server.sessions={k:s for k,s in self.server.sessions.items() if now-s.touched<7200 or s.lock.locked()}
                if len(self.server.sessions)>=32:
                    return self.respond(503,{'error':'本机牌桌已满，请重启服务或稍后再试。'})
                key=secrets.token_urlsafe(24)
                session=Session()
                self.server.sessions[key]=session
            return self.respond(200,{'id':key,'game':session.game.view()})
        key=body.get('id')
        if not isinstance(key,str):
            return self.respond(400,{'error':'缺少牌局标识。'})
        with self.server.sessions_lock:
            session=self.server.sessions.get(key)
        if session is None:
            return self.respond(404,{'error':'牌局已过期，请重新开桌。'})
        if not session.lock.acquire(blocking=False):
            return self.respond(409,{'error':'该牌局正在处理上一步，请稍后同步。'})
        try:
            session.touched=time.monotonic()
            game=session.game
            if self.path=='/api/state':
                return self.respond(200,{'game':game.view()})
            if type(body.get('version')) is not int or body['version']!=game.version:
                return self.respond(409,{'error':'牌局已更新，请同步后重试。','game':game.view()})
            if self.path=='/api/next':
                game.version+=1
                game.deal()
            elif self.path=='/api/bid':
                game.bid(0,body.get('bid'))
            elif self.path=='/api/play':
                game.play(0,body.get('cards'))
            elif self.path=='/api/hint':
                if game.phase!='play' or game.turn!=0:
                    raise ValueError('请在你的出牌回合使用提示。')
                options,_=evaluate(game.observation(0),samples=4)
                selected=options[0]['move']
                ids=game.ids_for(0,selected.cards if selected else ())
                return self.respond(200,{'game':game.view(),'suggested':ids})
            elif self.path=='/api/step':
                if game.turn==0 or game.phase=='over':
                    raise ValueError('现在不需要 AI 行动。')
                if not self.server.gpu_lock.acquire(blocking=False):
                    return self.respond(429,{'error':'模型正在处理另一桌，请稍后重试。'})
                try:
                    seat=game.turn
                    decision,diagnostics=self.server.policy.choose(game.observation(seat))
                    if game.phase=='bid':
                        game.bid(seat,decision)
                    else:
                        game.play(seat,game.ids_for(seat,decision))
                    game.last_ai=diagnostics
                finally:
                    self.server.gpu_lock.release()
            else:
                return self.respond(404,{'error':'接口不存在。'})
            return self.respond(200,{'game':game.view()})
        except ValueError as error:
            return self.respond(400,{'error':str(error),'game':session.game.view()})
        except Exception as error:
            print(f'AI request failed: {type(error).__name__}: {error}',flush=True)
            return self.respond(500,{'error':'模型决策失败，回合已保留。请重试；详细错误见启动终端。','game':session.game.view()})
        finally:
            session.lock.release()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',type=Path,default=ROOT/'models/laya')
    parser.add_argument('--port',type=int,default=8770)
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--samples',type=int,default=6,help='Hidden-hand samples per AI play (1–32).')
    args=parser.parse_args()
    if not 1<=args.port<=65535 or not 1<=args.samples<=32:
        parser.error('port 需在 1–65535，samples 需在 1–32。')
    model=args.model.expanduser().resolve()
    if not (model/'model.safetensors').is_file():
        parser.error(f'找不到本地模型 {model}。请按 README 下载模型。')
    # Bind first: an occupied port must not load a second GPU model.
    with Server(('127.0.0.1',args.port),None) as server:
        print('正在加载 Laya 并预热 GPU…',flush=True)
        server.policy=Policy(model,args.samples)
        url=f'http://127.0.0.1:{args.port}'
        print(f'已就绪：{url}  （Ctrl+C 停止）',flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print('\n服务已停止，牌局数据已释放。',flush=True)


if __name__=='__main__':
    main()
