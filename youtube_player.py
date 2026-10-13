"""Official YouTube iframe player in a native WebView window.

Uses YouTube IFrame Player API, not downloading or extracting video streams.
Time and pause state are written to a local JSON file through pywebview's JS bridge.
"""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
from urllib.parse import urlparse, parse_qs


def video_id(url):
    parsed=urlparse(url)
    host=(parsed.hostname or '').lower()
    if parsed.scheme not in ('https','http'):
        raise ValueError('YouTubeのURLではありません')
    if host in ('youtu.be','www.youtu.be'):
        vid=parsed.path.strip('/').split('/')[0]
    elif host in ('youtube.com','www.youtube.com','m.youtube.com','music.youtube.com','youtube-nocookie.com','www.youtube-nocookie.com'):
        parts=parsed.path.strip('/').split('/')
        if parts[0] in ('shorts','live','embed') and len(parts)>1:vid=parts[1]
        elif parts[0]=='watch':vid=parse_qs(parsed.query).get('v',[''])[0]
        else:vid=''
    else:vid=''
    if len(vid)!=11 or not all(c.isascii() and (c.isalnum() or c in '_-') for c in vid):
        raise ValueError('対応しているYouTube動画URLを入力してください')
    return vid


def player_html(vid, start_seconds=0):
    # Embed only the official player; no direct stream access.
    return '''<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><style>
html,body{margin:0;background:#151923;color:#eee;font-family:sans-serif;height:100%;}
main{height:100%;display:flex;flex-direction:column;min-width:0}#player{flex:1 1 auto;min-height:0;min-width:0;position:relative;overflow:hidden}#player iframe{position:absolute;inset:0;width:100%!important;height:100%!important;border:0}
footer{padding:8px 14px;font-size:13px}button{padding:5px 12px;margin-left:10px}body.embedded footer{display:none}
</style></head><body><main><div id="player"></div><footer>
YouTube公式プレイヤー | 「一時停止・盤面入力」で停止画面を自動的に解析ツールへ渡します。
<button onclick="requestRedock()">YouTubeを埋め込む</button><button onclick="pauseAndAnalyze()">一時停止・盤面入力</button></footer></main>
<script src="https://www.youtube.com/iframe_api"></script><script>
let player=null; let pauseRequest=0; let redockRequest=0;
function requestRedock(){redockRequest++;report();}
function pauseAndAnalyze(){if(!player)return;player.pauseVideo();pauseRequest++;report();}
function onYouTubeIframeAPIReady(){
 player=new YT.Player('player',{width:'100%',height:'100%',videoId:VIDEO_ID,playerVars:{start:START,playsinline:1,rel:0},
 events:{onReady:()=>report(),onStateChange:()=>report()}});
}
function report(){
 if(!player||!player.getCurrentTime||!window.pywebview||!window.pywebview.api)return;
 try{Promise.resolve(window.pywebview.api.update(Math.round(player.getCurrentTime()*1000),player.getPlayerState(),pauseRequest,(player.getVideoData()||{}).title||"",redockRequest))
 .then(embedded=>document.body.classList.toggle('embedded',embedded===true)).catch(()=>{});}catch(e){}
}
setInterval(report,500);
window.addEventListener('resize',()=>{if(player&&player.getIframe){const f=player.getIframe();if(f){f.style.width='100%';f.style.height='100%';}}});
</script></body></html>'''.replace('VIDEO_ID',json.dumps(vid)).replace('START',str(max(0,int(start_seconds))))


class Bridge:
    def __init__(self,path):
        self.path=Path(path)
        self.embedded=False
        self.original_style=None
        self.player_hwnd=0
        self.parent_hwnd=0
        self.redock_request=0
    def update(self,ms,state,pause_request=0,title="",redock_request=0):
        # Query the actual Win32 parent so the button reappears if undocked.
        if self.player_hwnd and self.parent_hwnd:
            try:
                import ctypes
                from ctypes import wintypes
                user32=ctypes.windll.user32
                user32.GetParent.argtypes=[wintypes.HWND]
                user32.GetParent.restype=wintypes.HWND
                self.embedded=(user32.GetParent(self.player_hwnd)==self.parent_hwnd)
            except (AttributeError,OSError):
                pass
        try:
            ms=max(0,int(ms));state=int(state)
            self.path.parent.mkdir(parents=True,exist_ok=True)
            tmp=self.path.with_suffix('.tmp')
            tmp.write_text(json.dumps({'time_ms':ms,'state':state,'pause_request':int(pause_request),'title':str(title)[:300], 'embedded':self.embedded, 'hwnd':self.player_hwnd, 'original_style':self.original_style, 'redock_request':int(redock_request)}),encoding='utf-8')
            tmp.replace(self.path)
        except (OSError,ValueError,TypeError):pass
        return bool(self.embedded)


def check_frozen_clr_runtime():
    """Check that the bundled pythonnet bridge works before starting WebView2."""
    import os
    import sys
    if getattr(sys, "frozen", False):
        from pathlib import Path
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        py_dll = base / f"python{sys.version_info.major}{sys.version_info.minor}.dll"
        if py_dll.is_file():
            os.environ.setdefault("PYTHONNET_PYDLL", str(py_dll))
    import clr
    from System import String
    if String("test").Length != 4:
        raise RuntimeError("pythonnet CLR smoke test failed")


def main():
    import sys
    if "--self-test-runtime" in sys.argv:
        check_frozen_clr_runtime()
        return
    parser=argparse.ArgumentParser()
    parser.add_argument('--url',required=True)
    parser.add_argument('--status',required=True)
    parser.add_argument('--start',type=int,default=0)
    parser.add_argument('--parent-hwnd',type=int,default=0)
    args=parser.parse_args()
    vid=video_id(args.url)
    check_frozen_clr_runtime()
    import webview
    html=player_html(vid,args.start)
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body=html.encode('utf-8')
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        bridge=Bridge(args.status)
        window=webview.create_window('YouTube | ぷよぷよ振り返り',f'http://127.0.0.1:{server.server_port}/',js_api=bridge,width=1060,height=750,min_size=(640,480))
        def on_shown():
            if args.parent_hwnd:
                try:
                    from webview_host import attach_to_host
                    bridge.player_hwnd,bridge.embedded=attach_to_host(args.parent_hwnd)
                    from webview_host import original_style_for
                    bridge.original_style=original_style_for(bridge.player_hwnd)
                    bridge.parent_hwnd=args.parent_hwnd
                except Exception:
                    bridge.embedded=False
            bridge.update(0,-1,0,'')
        window.events.shown += on_shown
        # Windows WebView2 backend; if unavailable, the app will report a
        # player-launch failure rather than silently switching browsers.
        webview.start(gui='edgechromium',debug=False)
    finally:server.shutdown();server.server_close()

if __name__=='__main__':main()
