"""Local-first Puyo video review player. Optional OpenCV for MP4 playback."""
import json
import math
from datetime import datetime, timezone
import os
import subprocess
import sys
import time
import uuid
import webbrowser
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog, font as tkfont
from PIL import Image, ImageTk, ImageGrab

ROOT=Path(__file__).resolve().parent
DATA=Path.home()/"PuyoReview"
SHOTS=DATA/"screenshots"
DB=DATA/"bookmarks.json"
CROP_DB=DATA/"board_crops.json"
def companion_executable(name, executable=None):
    """Resolve a sibling PyInstaller onedir app from either a nested or flat bundle."""
    launcher=Path(executable or sys.executable).resolve()
    candidates=(launcher.parent.parent/name/(name+'.exe'),
                launcher.parent/name/(name+'.exe'),
                launcher.parent/(name+'.exe'))
    return next((p for p in candidates if p.is_file()),candidates[0])

COLUMNS=(("number","採番",68),("video","動画名",210),("time","秒数",90),("analysis","解析種別",105),("comment","コメント",280),("saved","日時",155))

def filter_value(record,key,index):
    if key=="number":return f"{index+1:04d}"
    if key=="video":return Path(record.get("source","")).name if record.get("source_type")=="mp4" else (record.get("video_title") or "YouTube")
    if key=="time":return format_time(record.get("time_ms",0))
    if key=="analysis":return "連鎖STATS" if record.get("analysis_type","") in ("連鎖効率","連鎖STATS") else record.get("analysis_type","")
    if key=="comment":return (record.get("memo") or "").replace("\n"," ")
    if key=="saved":
        val=record.get("saved_at")
        if not val:return "日時不明（旧記録）"
        try:return datetime.fromisoformat(val).astimezone().strftime("%Y/%m/%d %H:%M")
        except (ValueError,TypeError):return "日時不明"
    return ""

def sorted_filtered_indices(records,filters=None,sort_key="number",descending=False):
    filters=filters or {}
    indices=[i for i,r in enumerate(records) if all(filter_value(r,k,i) in allowed for k,allowed in filters.items())]
    def key(i):
        r=records[i]
        if sort_key=="number":return i
        if sort_key=="time":return int(r.get("time_ms") or 0)
        if sort_key=="saved":return r.get("saved_at") or ""
        return filter_value(r,sort_key,i).casefold()
    return sorted(indices,key=key,reverse=descending)

def crop_key(source_type,source,image_size):
    """Reuse crop for matching source and resolution, not unrelated recordings."""
    return json.dumps([source_type,source,list(image_size)],ensure_ascii=False)

def load_crops(path=CROP_DB):
    if not path.exists():return {}
    data=json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data,dict) else {}

def save_crop(key,crop,rows,path=CROP_DB):
    data=load_crops(path)
    data[key]={"crop":list(crop),"rows":int(rows)}
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    tmp.replace(path)

def format_time(ms):
    s=max(0,int(ms)//1000)
    return f"{s//3600:02d}:{(s//60)%60:02d}:{s%60:02d}"

def parse_time(value):
    parts=value.strip().split(":")
    if not 1<=len(parts)<=3: raise ValueError("時刻は HH:MM:SS または MM:SS 形式")
    nums=[int(v) for v in parts]
    if any(n<0 for n in nums) or any(n>=60 for n in nums[1:]): raise ValueError("時刻が不正です")
    return sum(v*60**i for i,v in enumerate(reversed(nums)))*1000

def load_bookmarks(path=DB):
    if not path.exists(): return []
    data=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data,list): raise ValueError("記録ファイルが不正です")
    return data

def write_bookmarks(rows,path=DB):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")
    tmp.replace(path)

def youtube_timestamp(url,ms):
    from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
    parts=urlsplit(url)
    if parts.scheme not in ("http","https") or not (parts.hostname or "").lower().endswith(("youtube.com","youtu.be")):
        raise ValueError("YouTubeのURLを入力してください")
    q=[(k,v) for k,v in parse_qsl(parts.query) if k!="t"]
    q.append(("t",str(max(0,ms//1000))+"s"))
    return urlunsplit((parts.scheme,parts.netloc,parts.path,urlencode(q),parts.fragment))

class Review(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ぷよぷよ 録画振り返り v7.15")
        self.geometry("1330x850")
        self.minsize(1000,650)
        self.cap=None; self.cv2=None; self.mode=""; self.source=""; self.current_ms=0
        self.duration_ms=0; self.frame=None; self.frame_image=None; self.playing=False
        self.last_tick=time.monotonic(); self.dragging=False; self.records=[]
        self.speed=tk.DoubleVar(value=1.0);self.frame_accumulator=0.0;self.last_frame_tick=time.monotonic()
        self.filters={};self.sort_key="number";self.sort_desc=False;self.visible_indices=[]
        self.pending_session=None; self.pending_analysis=None; self.pending_shot=None
        self.youtube_process=None; self.youtube_status=None; self.youtube_last_status=None; self.youtube_launch_at=0; self.youtube_fallback_done=False
        self.youtube_pause_handled=0;self.youtube_title="";self.youtube_auto_busy=False
        self.youtube_dock=None;self.youtube_detached_hwnd=0;self.youtube_redock_handled=0;self.youtube_dock_pending=0;self.youtube_dock_enabled=True;self.youtube_closed_by_user=False
        self.build()
        try: self.records=load_bookmarks()
        except Exception as e: messagebox.showwarning("記録読み込み",str(e))
        self.update_list()
        self.after(40,self.tick)
        self.protocol("WM_DELETE_WINDOW",self.close)

    def build(self):
        self.source_label=ttk.Label(self,text="MP4またはYouTubeを開いてください。YouTubeは共通表示領域への埋め込みを試み、失敗時は別ウィンドウで再生します。",wraplength=1000)
        self.source_label.pack(anchor="w",padx=10,pady=(6,2))
        mainrow=ttk.Frame(self,padding=(8,0,8,2));mainrow.pack(fill="both",expand=True)
        videoarea=ttk.Frame(mainrow);videoarea.pack(side="left",fill="both",expand=True)
        self.video_host=tk.Frame(videoarea,bg="#202634")
        self.video_host.pack(fill="both",expand=True,padx=(2,5),pady=3)
        self.video=tk.Label(self.video_host,bg="#202634",fg="white",text="動画プレビュー")
        self.video.pack(fill="both",expand=True)
        sidepanel=ttk.Frame(mainrow,width=250);sidepanel.pack(side="right",fill="y",padx=(5,0))
        sidepanel.pack_propagate(False)
        ttk.Label(sidepanel,text="動画・キャプチャ操作",font=('',10,'bold')).pack(anchor="w",pady=(2,6))
        for label,callback in (("MP4を開く",self.open_mp4),("YouTubeを再生",self.open_youtube),
                               ("YouTubeを別ウィンドウに戻す",self.undock_youtube),
                               ("画面をキャプチャ",self.capture_screen),
                               ("停止画面を解析ツールに入力",self.analyze)):
            ttk.Button(sidepanel,text=label,command=callback).pack(fill="x",pady=2)
        ttk.Separator(sidepanel).pack(fill="x",pady=10)
        ttk.Label(sidepanel,text="YouTube時刻（自動取得・手動修正可）").pack(anchor="w")
        self.manual_time=ttk.Entry(sidepanel,width=16);self.manual_time.insert(0,"00:00:00")
        self.manual_time.pack(anchor="w",pady=(3,2))
        ttk.Label(sidepanel,text="再生ウィンドウで一時停止して取り込み",foreground="gray").pack(anchor="w")
        ttk.Separator(sidepanel).pack(fill="x",pady=10)
        ttk.Label(sidepanel,text="分析種別").pack(anchor="w")
        self.analysis=tk.StringVar(value="連鎖STATS")
        ttk.Combobox(sidepanel,textvariable=self.analysis,values=["連鎖STATS","3手全探索"],state="readonly",width=19).pack(fill="x",pady=(3,8))
        ttk.Label(sidepanel,text="自由メモ").pack(anchor="w")
        self.memo=tk.Text(sidepanel,height=6,wrap="word");self.memo.pack(fill="x",pady=(3,8))
        ttk.Button(sidepanel,text="この場面を記録",command=self.save).pack(fill="x")
        ctrl=ttk.Frame(self,padding=(10,2));ctrl.pack(fill="x")
        ttk.Button(ctrl,text="◀ 1フレーム",command=lambda:self.step(-1)).pack(side="left")
        self.play_btn=ttk.Button(ctrl,text="再生",command=self.toggle);self.play_btn.pack(side="left",padx=6)
        ttk.Label(ctrl,text="速度").pack(side="left",padx=(8,2))
        ttk.Combobox(ctrl,textvariable=self.speed,values=(0.25,0.5,0.75,1.0,1.25,1.5,2.0),state="readonly",width=5).pack(side="left")
        ttk.Button(ctrl,text="1フレーム ▶",command=lambda:self.step(1)).pack(side="left")
        self.seek=tk.Scale(ctrl,from_=0,to=100,orient="horizontal",showvalue=False,command=self.seek_changed)
        self.seek.pack(side="left",fill="x",expand=True,padx=8)
        self.seek.bind("<ButtonPress-1>",lambda e:setattr(self,"dragging",True))
        self.seek.bind("<ButtonRelease-1>",self.seek_release)
        self.time_label=ttk.Label(ctrl,text="00:00:00 / 00:00:00");self.time_label.pack(side="left")
        ttk.Separator(self).pack(fill="x",pady=6)
        ttk.Label(self,text="保存した場面（ダブルクリックで動画の位置へ移動 / URLを開く）").pack(anchor="w",padx=10)
        bottom=ttk.Frame(self,padding=(10,0,10,10));bottom.pack(fill="both",expand=False)
        gridframe=ttk.Frame(bottom);gridframe.pack(side="left",fill="both",expand=True)
        # Headings have separate sort and filter controls; the table itself is a Treeview.
        self.listbox=ttk.Treeview(gridframe,columns=[c[0] for c in COLUMNS],show="headings",height=7,selectmode="browse")
        for key,label,width in COLUMNS:
            self.listbox.heading(key,text=label,command=lambda k=key:self.sort_by(k))
            self.listbox.column(key,width=width,minwidth=55,stretch=(key in ("video","comment")),anchor="w")
        self.listbox.pack(side="left",fill="both",expand=True)
        sc=ttk.Scrollbar(gridframe,orient="vertical",command=self.listbox.yview)
        sc.pack(side="right",fill="y");self.listbox.configure(yscrollcommand=sc.set)
        self.listbox.bind("<Double-Button-1>",lambda e:self.open_selected())
        self.listbox.bind("<<TreeviewSelect>>",lambda e:self.update_csv_button())
        self.listbox.bind("<Button-1>",self.heading_click,add="+")
        self.listbox.bind("<ButtonRelease-1>",lambda e:self.after_idle(self.refresh_headings),add="+")
        self.listbox.bind("<Configure>",lambda e:self.after_idle(self.refresh_headings),add="+")
        # Independent, precisely positioned filter controls: no spaces or glyphs
        # in the heading text (which ttk themes align differently).
        self.filter_labels={}
        for key,_,_ in COLUMNS:
            marker=tk.Label(self.listbox,text="⌄",font=("Segoe UI",8),
                            fg="#777777",bg="#f0f0f0",cursor="hand2",
                            borderwidth=0,padx=0,pady=0)
            marker.bind("<Button-1>",lambda e,k=key:self.show_filter(k))
            self.filter_labels[key]=marker
        ttk.Button(bottom,text="フィルター解除",command=self.clear_filters).pack(side="left",anchor="n",padx=5)
        side=ttk.Frame(bottom);side.pack(side="left",fill="y",padx=8)
        self.csv_button=None
        for text,fn in [("記録を開く",self.open_selected),("スクショを表示",self.show_selected_shot),
                        ("メモを編集",self.edit_selected),("分析結果を見る",self.show_selected_analysis),("盤面を再解析",self.reanalyze_selected),("CSVを開く",self.open_selected_csv),("記録を削除",self.delete_selected),
                        ("保存フォルダを開く",self.open_folder)]:
            btn=ttk.Button(side,text=text,command=fn)
            btn.pack(fill="x",pady=2)
            if text=="CSVを開く":self.csv_button=btn

    def open_mp4(self,filename=None):
        filename=filename or filedialog.askopenfilename(filetypes=[("動画","*.mp4 *.mov *.mkv *.avi"),("すべて","*.*")])
        if not filename:return
        try:
            import cv2
            cap=cv2.VideoCapture(filename)
            if not cap.isOpened(): raise RuntimeError("動画を開けませんでした")
            self.stop_capture()
            self.stop_youtube_player()
            self.video.pack(fill="both",expand=True)
            self.cap=cap;self.cv2=cv2;self.mode="mp4";self.source=str(Path(filename).resolve())
            fps=cap.get(cv2.CAP_PROP_FPS) or 30
            self.fps=fps if 1<=fps<=240 else 30
            self.total_frames=int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            self.duration_ms=int(self.total_frames/self.fps*1000)
            self.seek.config(to=max(1,self.duration_ms))
            self.source_label.config(text=self.source)
            self.current_ms=0;self.frame_accumulator=0.0;self.last_frame_tick=time.monotonic();self.read_frame()
        except ImportError:
            messagebox.showerror("ライブラリ不足","MP4再生にはopencv-pythonが必要です。\nrun_review.batを実行してください。")
        except Exception as e:messagebox.showerror("動画エラー",str(e))

    def stop_capture(self):
        self.playing=False
        if self.cap:self.cap.release()
        self.cap=None
        self.play_btn.config(text="再生")

    def open_youtube(self):
        url=simpledialog.askstring("YouTube","YouTubeの動画URLを入力してください",parent=self)
        if not url:return
        try: youtube_timestamp(url,0)
        except ValueError as e: messagebox.showerror("URL",str(e));return
        self.stop_capture()
        self.mode="youtube";self.source=url;self.frame=None;self.last_shot=None;self.youtube_title=""
        self.video.config(image="",text="YouTubeを読み込み中…")
        self.source_label.config(text=url)
        self.launch_youtube_player(url)

    def launch_youtube_player(self,url,start_ms=0):
        """Use a separate native WebView so desktop capture can see the paused video."""
        try:
            from youtube_player import video_id
            video_id(url)
            self.youtube_status=DATA/'youtube_player_status.json'
            self.youtube_status.parent.mkdir(parents=True,exist_ok=True)
            self.youtube_status.unlink(missing_ok=True)
            self.youtube_last_status=None
            self.youtube_pause_handled=0
            self.stop_youtube_player()
            self.youtube_closed_by_user=False
            self.youtube_detached_hwnd=0
            self.youtube_redock_handled=0
            if getattr(sys,'frozen',False):
                exe=companion_executable('YouTubePlayer')
                if not exe.exists():raise FileNotFoundError('YouTubePlayer.exe が見つかりません')
                command=[str(exe)]
            else:
                command=[sys.executable,str(ROOT/'youtube_player.py')]
            self.video_host.update_idletasks()
            host_arg=['--parent-hwnd',str(self.video_host.winfo_id())] if self.youtube_dock_enabled and sys.platform=='win32' else []
            self.youtube_process=subprocess.Popen(command+['--url',url,'--status',str(self.youtube_status),'--start',str(start_ms//1000)]+host_arg,cwd=str(ROOT))
            self.youtube_launch_at=time.monotonic()
            self.youtube_fallback_done=False
            self.youtube_dock_pending=0
            # The WebView2 window attempts to attach itself after it is shown.
            # Parent polls its status for the actual HWND and verified result.
            self.source_label.config(text='YouTubeプレイヤーを起動しました。再生ウィンドウを開いてください。 '+url)
        except (OSError,ValueError,ImportError) as e:
            self.source_label.config(text='内蔵プレイヤーを起動できませんでした。ブラウザを開きます。 '+str(e))
            webbrowser.open(youtube_timestamp(url,start_ms))

    def stop_youtube_player(self):
        if self.youtube_dock:
            try:self.youtube_dock.detach()
            except Exception:pass
            self.youtube_dock=None
        if self.youtube_process and self.youtube_process.poll() is None:
            self.youtube_process.terminate()
        self.youtube_process=None
        self.youtube_detached_hwnd=0

    def undock_youtube(self):
        """Return to the proven standalone player when embedding is incompatible."""
        self.youtube_dock_enabled=False
        if self.youtube_dock:
            self.youtube_detached_hwnd=self.youtube_dock.hwnd or 0
            self.youtube_dock.detach()
            self.youtube_dock=None
        self.video.pack(fill="both",expand=True)
        if self.mode=='youtube':
            self.video.config(image='',text='YouTubeは別ウィンドウで再生中')

    def redock_youtube(self):
        """Move the existing player back into the shared video area."""
        if self.mode != 'youtube' or not self.youtube_process or self.youtube_process.poll() is not None:
            return
        self.youtube_dock_enabled=True
        if self.youtube_dock and self.youtube_dock.hwnd:
            return
        self.youtube_dock_pending=0
        self.try_dock_youtube()

    def try_dock_youtube(self):
        if (not self.youtube_dock_enabled or self.mode!='youtube' or
                not self.youtube_process or self.youtube_process.poll() is not None):
            return
        if self.youtube_dock:
            return
        try:
            from youtube_dock import Dock,available
            if not available():return
            self.video_host.update_idletasks()
            dock=Dock(self.video_host,self.youtube_process.pid)
            attached=(dock.attach_handle(self.youtube_detached_hwnd) if self.youtube_detached_hwnd else dock.attach())
            if attached:
                self.youtube_dock=dock
                self.youtube_detached_hwnd=0
                self.video.pack_forget()
                dock.resize()
                self.source_label.config(text='YouTubeを再生中（MP4と共通の表示領域）。 '+self.source)
                return
        except Exception as exc:
            self.source_label.config(text='YouTubeは別ウィンドウで再生中（埋め込み不可: '+str(exc)+'）')
            return
        self.youtube_dock_pending+=1
        if self.youtube_dock_pending<30:
            self.after(350,self.try_dock_youtube)
        else:
            self.video.config(text='YouTubeは別ウィンドウで再生中')

    def poll_youtube_time(self):
        if self.mode!='youtube' or not self.youtube_status:return
        if (self.youtube_process is not None and self.youtube_process.poll() is not None
                and not self.youtube_fallback_done and time.monotonic()-self.youtube_launch_at>1):
            self.youtube_fallback_done=True
            self.youtube_closed_by_user=True
            self.youtube_dock=None
            self.youtube_detached_hwnd=0
            self.video.pack(fill='both',expand=True)
            self.video.config(image='',text='YouTubeプレイヤーを閉じました')
            self.source_label.config(text='YouTubeプレイヤーを閉じました。再生する場合は「YouTubeを再生」を押してください。')
            # Do not open a browser when the player was closed using ×.
            return
        try:
            data=json.loads(self.youtube_status.read_text(encoding='utf-8'))
            stamp=self.youtube_status.stat().st_mtime_ns
            if stamp==self.youtube_last_status:return
            self.youtube_last_status=stamp
            self.current_ms=max(0,int(data['time_ms']))
            self.manual_time.delete(0,'end')
            self.manual_time.insert(0,format_time(self.current_ms))
            self.time_label.configure(text=format_time(self.current_ms)+' / YouTube')
            title=str(data.get('title') or '').strip()
            if title:self.youtube_title=title
            redock_request=int(data.get('redock_request') or 0)
            if redock_request>self.youtube_redock_handled:
                self.youtube_redock_handled=redock_request
                self.redock_youtube()
            if self.youtube_dock_enabled and data.get('embedded') and data.get('hwnd') and not self.youtube_dock:
                try:
                    from youtube_dock import Dock
                    dock=Dock(self.video_host,self.youtube_process.pid)
                    dock.adopt(int(data['hwnd']),data.get('original_style'))
                    self.youtube_dock=dock
                    self.video.pack_forget()
                    dock.resize()
                    self.source_label.config(text='YouTubeを再生中（共通の動画表示領域）。 '+self.source)
                except Exception as exc:
                    self.source_label.config(text='YouTube表示の調整に失敗: '+str(exc))
            request=int(data.get('pause_request') or 0)
            if request>self.youtube_pause_handled:
                self.youtube_pause_handled=request
                # The explicit player button is the only auto-analysis trigger.
                # Wait briefly for the iframe to finish painting its paused frame.
                self.after(650,self.analyze_from_youtube_pause)
        except (OSError,ValueError,KeyError,TypeError):pass

    def read_frame(self):
        if not self.cap:return
        ok,frame=self.cap.read()
        if not ok:
            self.playing=False;self.play_btn.config(text="再生");return
        self.frame=frame
        self.last_shot=None
        self.current_ms=int(max(0,self.cap.get(self.cv2.CAP_PROP_POS_FRAMES)-1)/self.fps*1000)
        if not self.dragging:self.seek.set(self.current_ms)
        self.time_label.config(text=f"{format_time(self.current_ms)} / {format_time(self.duration_ms)}")
        self.draw_frame()

    def draw_frame(self):
        if self.frame is None:return
        rgb=self.cv2.cvtColor(self.frame,self.cv2.COLOR_BGR2RGB)
        im=Image.fromarray(rgb)
        w=max(200,self.video.winfo_width()-12);h=max(140,self.video.winfo_height()-12)
        im.thumbnail((w,h))
        self.frame_image=ImageTk.PhotoImage(im)
        self.video.config(image=self.frame_image,text="")

    def toggle(self):
        if not self.cap:return
        self.playing=not self.playing
        self.last_tick=time.monotonic()
        self.last_frame_tick=self.last_tick;self.frame_accumulator=0.0
        self.play_btn.config(text="一時停止" if self.playing else "再生")

    def step(self,delta):
        if not self.cap:return
        self.playing=False;self.play_btn.config(text="再生")
        pos=int(self.cap.get(self.cv2.CAP_PROP_POS_FRAMES))
        # current displayed frame is pos-1
        target=max(0,min(self.total_frames-1,pos-1+delta))
        self.cap.set(self.cv2.CAP_PROP_POS_FRAMES,target)
        self.read_frame()

    def seek_changed(self,value):
        pass
    def seek_release(self,event=None):
        self.dragging=False
        if self.cap:
            target=max(0,min(self.total_frames-1,int(float(self.seek.get())/1000*self.fps)))
            self.cap.set(self.cv2.CAP_PROP_POS_FRAMES,target)
            self.read_frame()

    def tick(self):
        now=time.monotonic()
        if self.playing and self.cap:
            # Wall-clock paced playback. Drop decoded frames if decoding/rendering lags.
            # Display at most one frame per UI tick; this avoids systematically slow playback.
            elapsed=min(0.5,max(0.0,now-self.last_frame_tick))
            self.frame_accumulator+=elapsed*self.fps*float(self.speed.get())
            frames=int(self.frame_accumulator)
            if frames:
                self.frame_accumulator-=frames
                if frames>1:
                    pos=int(self.cap.get(self.cv2.CAP_PROP_POS_FRAMES))
                    target=min(self.total_frames-1,pos+frames-1)
                    if frames<=5:
                        for _ in range(frames-1):
                            if not self.cap.grab():break
                    else:
                        self.cap.set(self.cv2.CAP_PROP_POS_FRAMES,target)
                self.read_frame()
        self.last_frame_tick=now
        self.poll_analysis()
        self.poll_youtube_time()
        self.after(15,self.tick)

    def analyze_from_youtube_pause(self):
        if self.mode!='youtube' or self.youtube_auto_busy:return
        self.youtube_auto_busy=True
        try:
            self.analyze(quiet_capture=True)
        finally:
            self.youtube_auto_busy=False

    def screenshot(self,quiet=False):
        if self.mode=="mp4" and self.frame is not None:
            rgb=self.cv2.cvtColor(self.frame,self.cv2.COLOR_BGR2RGB)
            return Image.fromarray(rgb)
        if self.mode=="youtube":
            # No confirmation dialog: the user already chose to capture/analyze.
            # In embedded mode the player is already inside this window.
            docked=self.youtube_dock is not None and self.youtube_dock.hwnd is not None
            if not docked:
                self.withdraw();self.update()
            try:
                from youtube_capture import capture_player
                img=capture_player(hwnd=self.youtube_dock.hwnd if docked else None,embedded=docked)
            finally:
                if not docked:self.deiconify()
            return img
        raise ValueError("動画を開いてください")

    def capture_screen(self):
        try:
            im=self.screenshot()
            SHOTS.mkdir(parents=True,exist_ok=True)
            path=SHOTS/(f"capture_{uuid.uuid4().hex[:12]}.png")
            im.save(path)
            self.last_shot=path
            messagebox.showinfo("キャプチャ","スクリーンショットを保存しました。\n"+str(path))
        except Exception as e:messagebox.showerror("キャプチャ",str(e))

    def get_shot(self,quiet=False):
        # YouTube can advance while the source URL stays the same. Never reuse
        # a previous pause's screenshot for a new analysis request.
        if self.mode != "youtube" and getattr(self,"last_shot",None) is not None and self.last_shot.exists():
            return self.last_shot
        im=self.screenshot(quiet=True) if quiet else self.screenshot()
        SHOTS.mkdir(parents=True,exist_ok=True)
        path=SHOTS/(f"capture_{uuid.uuid4().hex[:12]}.png")
        im.save(path)
        self.last_shot=path
        return path

    def analysis_command(self):
        if getattr(sys,'frozen',False):
            exe=companion_executable('PuyoAnalysis')
            if not exe.is_file():raise FileNotFoundError('PuyoAnalysis.exe が見つかりません')
            return [str(exe)]
        return [sys.executable,str(ROOT/'puyo_tools'/'app.py')]

    def analyze(self,quiet_capture=False):
        try:
            if not self.source:raise ValueError("動画を開いてください")
            shot=self.get_shot(quiet=quiet_capture)
            ms=self.current_ms if quiet_capture and self.mode=='youtube' else self.get_ms()
        except Exception as e:messagebox.showerror("取り込み",str(e));return
        app=ROOT/"puyo_tools"/"app.py"
        if not app.exists() and not getattr(sys,'frozen',False):messagebox.showerror("解析ツール","同梱の解析ツールが見つかりません");return
        sessions=DATA/"sessions"
        sessions.mkdir(parents=True,exist_ok=True)
        token=uuid.uuid4().hex
        output=sessions/(token+"_result.json")
        session=sessions/(token+"_session.json")
        info={"session_version":1,"id":token,"output":str(output),
              "source":self.source,"source_type":self.mode,
              "time_ms":ms,"screenshot":str(shot),"video_title":self.youtube_title if self.mode=='youtube' else Path(self.source).name}
        session.write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding="utf-8")
        self.pending_session=info
        self.pending_analysis=None
        self.pending_shot=shot
        try:
            subprocess.Popen(self.analysis_command()+["--image",str(shot),
                              "--review-session",str(session)],cwd=str(ROOT))
        except OSError as e:
            messagebox.showerror("解析ツール起動",str(e))

    def poll_analysis(self):
        if not self.pending_session or self.pending_analysis:return
        out=Path(self.pending_session["output"])
        if not out.exists():return
        try:
            result=json.loads(out.read_text(encoding="utf-8"))
            if result.get("session_id")!=self.pending_session["id"]:return
            self.pending_analysis=result["analysis"]
            typ=self.pending_analysis.get("type","")
            self.analysis.set("連鎖STATS" if typ in ("連鎖効率","連鎖STATS") else typ if typ in ("3手全探索","盤面のみ") else "連鎖STATS")
            self.source_label.config(text="盤面を受信しました。「この場面を記録」で保存できます。後から再解析もできます。" if typ=="盤面のみ" else "解析結果を受信しました。「この場面を記録」でメモと一緒に保存できます。")
            self.lift()
        except (OSError,ValueError,KeyError):
            return

    def get_ms(self):
        return parse_time(self.manual_time.get()) if self.mode=="youtube" else self.current_ms

    def save(self):
        try:
            if not self.source:raise ValueError("動画を開いてください")
            if self.pending_analysis is not None:
                session=self.pending_session
                ms=session["time_ms"]
                shot=Path(session["screenshot"])
                source=session["source"]
                mode=session["source_type"]
                analysis=self.pending_analysis
                board=analysis.get("board")
                kind=analysis.get("type",self.analysis.get())
                if kind=="盤面のみ":
                    # No analysis was performed; retain the board for later use.
                    board=analysis.get("board")
            else:
                ms=self.get_ms()
                shot=self.get_shot()
                source=self.source
                mode=self.mode
                analysis=None
                board=None
                kind=self.analysis.get()
            rec={"id":uuid.uuid4().hex,"source_type":mode,"source":source,
                 "time_ms":ms,"screenshot":str(shot),"video_title":(session.get('video_title',self.youtube_title) if self.pending_analysis is not None else self.youtube_title) if mode=='youtube' else Path(source).name,"analysis_type":kind,
                 "memo":self.memo.get("1.0","end-1c"),"board":board,"next_pairs":analysis.get("next_pairs") if analysis else None,
                 "analysis_result":(None if analysis and analysis.get("type")=="盤面のみ" else analysis),"csv_path":analysis.get("csv_path") if analysis else None,
                 "saved_at":datetime.now().astimezone().isoformat(timespec="seconds")}
            self.records.append(rec)
            write_bookmarks(self.records)
            self.update_list()
            self.memo.delete("1.0","end")
            self.last_shot=None
            self.pending_session=None
            self.pending_analysis=None
            self.pending_shot=None
            messagebox.showinfo("保存","記録を保存しました。"+("盤面・分析結果も保存しました。" if analysis else "\\n分析結果なしの記録です。"))
        except Exception as e:messagebox.showerror("保存",str(e))

    def update_list(self):
        old=self.listbox.selection()
        self.visible_indices=sorted_filtered_indices(self.records,self.filters,self.sort_key,self.sort_desc)
        self.listbox.delete(*self.listbox.get_children())
        for i in self.visible_indices:
            rec=self.records[i]
            self.listbox.insert("","end",iid=str(i),values=tuple(filter_value(rec,k,i) for k,_,_ in COLUMNS))
        if old and old[0] in self.listbox.get_children():self.listbox.selection_set(old[0])
        self.refresh_headings()
        self.update_csv_button()

    def refresh_headings(self):
        """Pin one subtle chevron to each header's lower-right corner."""
        header_height=22
        # Detect the actual themed Treeview heading height, if available.
        for y in range(1,42):
            if self.listbox.identify_region(4,y)!="heading":
                header_height=y
                break
        right=0
        for key,label,_ in COLUMNS:
            right+=self.listbox.column(key,"width")
            self.listbox.heading(key,text=label,anchor="w")
            marker=self.filter_labels.get(key)
            if marker is None:continue
            if right>self.listbox.winfo_width() or right<12:
                marker.place_forget()
                continue
            marker.configure(fg="#555555" if key in self.filters else "#888888")
            marker.place(x=right-14,y=max(0,header_height-15),width=12,height=13)
            marker.lift()

    def heading_click(self,event):
        # Header clicks sort. The separate, small chevron control filters.
        return None

    def sort_by(self,key):
        if self.sort_key==key:self.sort_desc=not self.sort_desc
        else:self.sort_key=key;self.sort_desc=False
        self.update_list()

    def clear_filters(self):
        self.filters.clear();self.update_list()

    def show_filter(self,key):
        values=sorted({filter_value(r,key,i) for i,r in enumerate(self.records)},key=str.casefold)
        dialog=tk.Toplevel(self);dialog.title(f"{dict((k,l) for k,l,_ in COLUMNS)[key]} のフィルター")
        dialog.geometry("440x420");dialog.transient(self);dialog.grab_set()
        ttk.Label(dialog,text="表示する値を選択してください（複数選択可）").pack(anchor="w",padx=12,pady=8)
        search=tk.StringVar()
        ttk.Entry(dialog,textvariable=search).pack(fill="x",padx=12)
        listbox=tk.Listbox(dialog,selectmode="extended",exportselection=False)
        listbox.pack(fill="both",expand=True,padx=12,pady=8)
        allowed=self.filters.get(key)
        displayed=[]
        def refresh(*_):
            displayed[:]=[v for v in values if search.get().casefold() in v.casefold()]
            listbox.delete(0,"end")
            for i,v in enumerate(displayed):
                listbox.insert("end",v or "（空欄）")
                if allowed is None or v in allowed:listbox.selection_set(i)
        search.trace_add("write",refresh);refresh()
        buttons=ttk.Frame(dialog);buttons.pack(fill="x",padx=12,pady=10)
        def apply():
            chosen={displayed[i] for i in listbox.curselection()}
            # Search narrows the choices, but keeps any selections outside search.
            if search.get() and allowed is not None:chosen|=(allowed-set(displayed))
            if len(chosen)==len(values):self.filters.pop(key,None)
            else:self.filters[key]=chosen
            dialog.destroy();self.update_list()
        ttk.Button(buttons,text="適用",command=apply).pack(side="left")
        ttk.Button(buttons,text="この列の解除",command=lambda:(self.filters.pop(key,None),dialog.destroy(),self.update_list())).pack(side="left",padx=8)
        ttk.Button(buttons,text="キャンセル",command=dialog.destroy).pack(side="right")

    def selected(self):
        sel=self.listbox.selection()
        if not sel:return None,None
        i=int(sel[0]);return i,self.records[i]

    def open_selected(self):
        _,r=self.selected()
        if not r:return
        if r["source_type"]=="youtube":
            self.mode='youtube';self.source=r['source'];self.frame=None
            self.launch_youtube_player(r['source'],r['time_ms'])
        elif Path(r["source"]).exists():
            self.open_mp4(r["source"])
            self.cap.set(self.cv2.CAP_PROP_POS_FRAMES,int(r["time_ms"]/1000*self.fps))
            self.read_frame()
        else:messagebox.showwarning("動画なし","元動画が見つかりません。")

    def show_selected_shot(self):
        _,r=self.selected()
        if r and Path(r["screenshot"]).exists():
            if sys.platform=="win32":os.startfile(r["screenshot"])
            else:webbrowser.open(Path(r["screenshot"]).as_uri())

    def csv_path_of(self,rec):
        if not rec:return None
        return rec.get('csv_path') or (rec.get('analysis_result') or {}).get('csv_path')

    def update_csv_button(self):
        if getattr(self,'csv_button',None) is None:return
        _,rec=self.selected()
        path=self.csv_path_of(rec)
        self.csv_button.configure(state='normal' if path and Path(path).is_file() else 'disabled')

    def open_selected_csv(self):
        _,rec=self.selected()
        if not rec:return
        path=rec.get('csv_path') or (rec.get('analysis_result') or {}).get('csv_path')
        if not path:
            messagebox.showinfo('CSV','この記録にはCSVがありません。');return
        if not Path(path).exists():
            messagebox.showwarning('CSV','CSVファイルが見つかりません。\n'+path);return
        if sys.platform=='win32':os.startfile(path)
        else:webbrowser.open(Path(path).as_uri())

    def reanalyze_selected(self):
        _,rec=self.selected()
        if not rec:return
        analysis=rec.get('analysis_result') or {}
        board=analysis.get('board') or rec.get('board')
        if not board:
            messagebox.showinfo('再解析','この記録には盤面データがありません。')
            return
        app=ROOT/'puyo_tools'/'app.py'
        if not app.exists() and not getattr(sys,'frozen',False):
            messagebox.showerror('再解析','解析アプリが見つかりません。')
            return
        payload={'board':board,'analysis_type':analysis.get('type') or rec.get('analysis_type'),
                 'next_pairs':analysis.get('next_pairs') or rec.get('next_pairs'),
                 'initial_bonus':analysis.get('initial_bonus',False),
                 'include_future_bonus':analysis.get('include_future_bonus',False),
                 'efficiency_bonus_mode':analysis.get('efficiency_bonus_mode', 'earned' if analysis.get('include_future_bonus',False) else 'none')}
        folder=DATA/'sessions';folder.mkdir(parents=True,exist_ok=True)
        path=folder/(uuid.uuid4().hex+'_reopen.json')
        path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
        try:
            subprocess.Popen(self.analysis_command()+['--load-review',str(path)],cwd=str(ROOT))
        except OSError as e:messagebox.showerror('再解析',str(e))

    def show_selected_analysis(self):
        _,rec=self.selected()
        if not rec:return
        a=rec.get('analysis_result')
        if not a:
            messagebox.showinfo('分析結果','この記録には解析結果がありません。');return
        win=tk.Toplevel(self);win.title('振り返り詳細');win.geometry('1060x800')
        outer=ttk.Frame(win);outer.pack(fill='both',expand=True)
        canvas=tk.Canvas(outer,highlightthickness=0)
        scroll=ttk.Scrollbar(outer,orient='vertical',command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True)
        main=ttk.Frame(canvas,padding=14)
        wid=canvas.create_window((0,0),window=main,anchor='nw')
        main.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda e:canvas.itemconfigure(wid,width=e.width))
        heading=ttk.Frame(main);heading.pack(fill='x')
        ttk.Label(heading,text=f'{format_time(rec["time_ms"])}  {a.get("type","")}',font=('',16,'bold')).pack(side='left')
        ttk.Button(heading,text='元動画へ',command=self.open_selected).pack(side='right')
        ttk.Label(main,text='自由メモ：'+(rec.get('memo') or '（なし）'),wraplength=950,justify='left').pack(anchor='w',pady=8)
        ttk.Button(main,text='メモを編集',command=lambda:(win.destroy(),self.edit_selected())).pack(anchor='w')
        path=self.csv_path_of(rec)
        ttk.Label(main,text='CSV保存先',font=('',11,'bold')).pack(anchor='w',pady=(12,3))
        entry=ttk.Entry(main)
        entry.insert(0,path or '未保存（この記録にCSVはありません）')
        entry.configure(state='readonly');entry.pack(fill='x',pady=2)
        row=ttk.Frame(main);row.pack(anchor='w',pady=3)
        state='normal' if path and Path(path).is_file() else 'disabled'
        ttk.Button(row,text='CSVを開く',state=state,command=lambda:self.open_csv_path(path)).pack(side='left',padx=(0,6))
        ttk.Button(row,text='フォルダを開く',state=state,command=lambda:self.open_csv_folder(path)).pack(side='left',padx=6)
        ttk.Button(row,text='パスをコピー',state='normal' if path else 'disabled',command=lambda:(win.clipboard_clear(),win.clipboard_append(path))).pack(side='left',padx=6)
        ttk.Button(row,text='スクショを開く',command=self.show_selected_shot).pack(side='left',padx=6)
        ttk.Button(row,text='詳細JSONを表示',command=lambda:self.show_raw_json(a)).pack(side='left',padx=6)
        ttk.Separator(main).pack(fill='x',pady=12)
        if a.get('type') in ('連鎖効率','連鎖STATS'):
            chain=a.get('chain',{})
            ttk.Label(main,text='連鎖STATSの解析',font=('',14,'bold')).pack(anchor='w')
            lines=[f'連鎖数：{chain.get("chains",0)}  得点：{chain.get("score",0):,}  消去色ぷよ：{chain.get("erased_colors",0)}  消去おじゃま：{chain.get("erased_ojama",0)}',
                   f'連鎖効率：{a.get("efficiency",0):,.2f}  総所要時間：{a.get("seconds",0):.3f}秒  補充時間：{a.get("consumption_seconds",0):.3f}秒  連鎖時間：{chain.get("frames",0)}F']
            ttk.Label(main,text='\n'.join(lines),justify='left').pack(anchor='w',pady=8)
            self.add_board_history(main,a.get('board',[]),chain)
        else:
            ttk.Label(main,text='3手全探索：保存した候補',font=('',14,'bold')).pack(anchor='w')
            ttk.Label(main,text=f'合計得点：{a.get("total_score",0):,}  ちぎり：{a.get("chigiri",0)}  全消し：{a.get("all_clears",0)}  ネクスト：{a.get("next_pairs",[])}',wraplength=950).pack(anchor='w',pady=8)
            board=a.get('board',[])
            if board:
                ttk.Label(main,text='探索開始盤面',font=('',11,'bold')).pack(anchor='w')
                self.render_board(main,board,cell=22)
            for i,turn in enumerate(a.get('turns',[]),1):
                ttk.Separator(main).pack(fill='x',pady=10)
                chain=turn.get('chain',{})
                ttk.Label(main,text=f'{i}手目  置き方：{turn.get("move","")}  得点：{turn.get("score",0):,}  {chain.get("chains",0)}連鎖  全消しボーナス利用：{turn.get("earned_all_clear_bonus",0)}',font=('',11,'bold'),wraplength=950).pack(anchor='w')
                self.add_board_history(main,turn.get('placed_board',[]),chain)
        ttk.Label(main,text='※古い記録では、保存時に連鎖途中盤面が含まれていないため、開始・最終盤面のみ表示します。',wraplength=950,foreground='#777777').pack(anchor='w',pady=12)

    def add_board_history(self,parent,start_board,chain):
        steps=chain.get('steps',[])
        if not start_board and not steps:return
        ttk.Label(parent,text='盤面推移',font=('',11,'bold')).pack(anchor='w',pady=(8,3))
        summary=ttk.Frame(parent);summary.pack(fill='x')
        if steps:
            for step in steps:
                groups=', '.join(f'{c}{n}' for c,n in step.get('groups',[]))
                ttk.Label(summary,text=f'{step.get("index","?")}連鎖目：{step.get("score",0):,}点 / 消去{step.get("erased_colors",0)}個 / おじゃま{step.get("erased_ojama",0)}個 / 落下{step.get("fall",0)} / {step.get("frames",0)}F / 組：{groups}',wraplength=930).pack(anchor='w',pady=2)
        else:
            ttk.Label(summary,text='発火なし').pack(anchor='w')
        sequence=[('開始・設置後',start_board)]
        sequence.extend((f'{st.get("index","?")}連鎖後',st.get('after')) for st in steps if st.get('after'))
        final=chain.get('final_board')
        if final and (len(sequence)==1 or sequence[-1][1]!=final):sequence.append(('最終盤面',final))
        grid=ttk.Frame(parent);grid.pack(fill='x',pady=5)
        for i,(title,board) in enumerate(sequence):
            if not board:continue
            cell=ttk.Frame(grid);cell.grid(row=i//5,column=i%5,sticky='nw',padx=9,pady=7)
            ttk.Label(cell,text=title).pack(anchor='w')
            self.render_board(cell,board,cell=20)

    def open_csv_path(self,path):
        if not path or not Path(path).is_file():return
        if sys.platform=='win32':os.startfile(path)
        else:webbrowser.open(Path(path).as_uri())

    def render_board(self,parent,board,cell=30):
        colors={'.':'#202634','R':'#e94f58','B':'#438be5','G':'#4fc475','Y':'#f6d451','P':'#ba73e6','O':'#999fa9'}
        canvas=tk.Canvas(parent,width=6*cell+2,height=13*cell+2,bg='#202634',highlightthickness=0)
        canvas.pack(anchor='w',pady=8)
        for y,line in enumerate(board[:13]):
            for x,ch in enumerate(line[:6]):
                xx=x*cell;yy=y*cell
                canvas.create_rectangle(xx,yy,xx+cell,yy+cell,fill='#292f3e',outline='#465063')
                if ch!='.':canvas.create_oval(xx+3,yy+3,xx+cell-3,yy+cell-3,fill=colors.get(ch,'#999fa9'),outline='white')
        canvas.create_line(0,cell,6*cell,cell,fill='#ff9b72',width=2)

    def open_csv_folder(self,path):
        folder=Path(path).parent
        if not folder.is_dir():messagebox.showwarning('フォルダ','保存先が見つかりません。');return
        if sys.platform=='win32':os.startfile(str(folder))
        else:webbrowser.open(folder.as_uri())

    def show_raw_json(self,analysis):
        dialog=tk.Toplevel(self);dialog.title('解析データ（JSON）');dialog.geometry('780x620')
        text=tk.Text(dialog,wrap='none',font=('Consolas',10));text.pack(fill='both',expand=True)
        text.insert('1.0',json.dumps(analysis,ensure_ascii=False,indent=2));text.config(state='disabled')

    def edit_selected(self):
        i,r=self.selected()
        if r is None:return
        new=simpledialog.askstring("メモ編集","自由メモ",initialvalue=r.get("memo",""),parent=self)
        if new is not None:
            r["memo"]=new;write_bookmarks(self.records);self.update_list()

    def delete_selected(self):
        i,r=self.selected()
        if r is not None and messagebox.askyesno("削除","この記録を削除しますか？\n画像ファイルは残ります。"):
            self.records.pop(i);write_bookmarks(self.records);self.update_list()

    def open_folder(self):
        DATA.mkdir(exist_ok=True)
        if sys.platform=="win32":os.startfile(DATA)
        else:webbrowser.open(DATA.as_uri())

    def close(self):
        self.stop_capture()
        self.stop_youtube_player()
        self.destroy()

if __name__=="__main__":
    Review().mainloop()
