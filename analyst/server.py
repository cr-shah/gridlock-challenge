"""Local same-origin server; never serves credentials or repository metadata."""
import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from threading import BoundedSemaphore
from dotenv import load_dotenv
from analyst.core import ROOT, answer, configuration, AnalystError

load_dotenv(ROOT/'.env')
GATE=BoundedSemaphore(3)
NATION_GATE=BoundedSemaphore(8)
def allowed_asset(name):
    path=ROOT/name
    allowed=(path.parent==ROOT and path.suffix in {'.html','.css','.js'}) or (path.parent==ROOT/'data/published' and path.suffix=='.json')
    return allowed and path.is_file() and path.resolve().is_relative_to(ROOT.resolve())

class Handler(BaseHTTPRequestHandler):
    def respond(self,status,value):
        body=json.dumps(value).encode()
        self.send_response(status); self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
    def do_GET(self):
        path=urlsplit(self.path).path
        if path=='/api/analyst/status':return self.respond(200,configuration())
        if path.startswith('/api/nation/'):
            if not NATION_GATE.acquire(blocking=False):
                return self.respond(429,{'error':'Explorer is busy. Retry shortly.'})
            try:
                from nation.api import dispatch
                return self.respond(200,dispatch(self.path))
            except KeyError:
                return self.respond(404,{'error':'Record or endpoint not found.'})
            except (ValueError,TypeError) as exc:
                return self.respond(400,{'error':str(exc)})
            except Exception:
                return self.respond(503,{'error':'National catalog unavailable. Existing regional tools remain available.'})
            finally:
                NATION_GATE.release()
        name=path.lstrip('/') or ('index.html' if 'view=radar' in urlsplit(self.path).query else 'nationwide.html')
        if not allowed_asset(name):return self.respond(404,{'error':'Not found'})
        body=(ROOT/name).read_bytes()
        self.send_response(200);self.send_header('Content-Type',mimetypes.guess_type(name)[0] or 'application/octet-stream');self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(body)
    def do_POST(self):
        if self.path!='/api/analyst':return self.respond(404,{'error':'Not found'})
        origin=self.headers.get('Origin')
        if origin and origin not in {f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'}:
            return self.respond(403,{'error':'Same-origin requests only.'})
        if self.headers.get('Content-Type','').split(';')[0]!='application/json':return self.respond(415,{'error':'JSON required.'})
        try:length=int(self.headers.get('Content-Length','0'))
        except ValueError:return self.respond(400,{'error':'Invalid request size.'})
        if not 0<length<=16000:return self.respond(413,{'error':'Request too large or empty.'})
        if not GATE.acquire(blocking=False):return self.respond(429,{'error':'Analyst is busy. Retry shortly.'})
        try:
            payload=json.loads(self.rfile.read(length))
            if not isinstance(payload,dict):raise ValueError('Invalid request.')
            self.respond(200,answer(payload))
        except (ValueError,TypeError):self.respond(400,{'error':'Invalid question or selection. Select an opportunity for a briefing.'})
        except AnalystError as exc:self.respond(503,{'error':str(exc)})
        except Exception:self.respond(500,{'error':'Analyst could not complete the request. No result was generated.'})
        finally:GATE.release()
    def log_message(self,*args):pass

if __name__=='__main__':
    port=int(os.getenv('ANALYST_PORT','8002'))
    print(f'GridLock with AI Analyst: http://127.0.0.1:{port}')
    ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()
