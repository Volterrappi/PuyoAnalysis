"""Puyo desktop app (Tkinter, standard library only)."""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from threading import Thread,Event
from queue import Queue, Empty
from collections import defaultdict
import csv
import json
import os
import sys
from pathlib import Path
from PIL import Image, ImageTk, ImageGrab
import record_store
from tenpai_probe import probe as tenpai_probe
from tenpai_evaluation import evaluate
from tenpai_search import search as search_tenpai,add_color
from tenpai_view import ResponseList
from crop_suggest import suggest as suggest_crop
from common.analysis import candidate_stats, group_by_score, detail_row, matches_filters, response_priority
from common.result_columns import result_fields, visible_result_fields, export_row
from common.engine import *
from common.ghost_fall import ghost_frames, advance_row14, validate_row14
from common.image_board import recognize_board, recognize_esports_next
from common.reference import nuisance, nuisance_label, nuisance_parts, four_clear_rows, double_rows, multi_rows, TA_PACES, four_clear_at_height, group_equal_metrics

PALETTE = {'.':'#202634','R':'#e94f58','B':'#438be5','G':'#4fc475','Y':'#f6d451','P':'#ba73e6','O':'#999fa9'}
NAMES = {'.':'消去','R':'赤','B':'青','G':'緑','Y':'黄','P':'紫','O':'おじゃま'}
PAGE_SIZE = 250

def new_placement_cells(previous, placed):
    """Cells occupied by the latest pair, visible on the 13-row board."""
    return {(r,c) for r in range(H) for c in range(W)
            if previous[r][c] == '.' and placed[r][c] != '.'}


def draw_board(parent, board, cell=20, highlight=()):
    canvas=tk.Canvas(parent,width=W*cell+2,height=H*cell+2,bg='#202634',highlightthickness=0)
    for r,line in enumerate(board):
        for c,ch in enumerate(line):
            x=c*cell;y=r*cell
            canvas.create_rectangle(x,y,x+cell,y+cell,fill='#292f3e',outline='#465063')
            if ch!='.':canvas.create_oval(x+2,y+2,x+cell-2,y+cell-2,fill=PALETTE[ch],outline='#ffffff')
    for r,c in highlight:
        x=c*cell;y=r*cell
        canvas.create_rectangle(x+1,y+1,x+cell-1,y+cell-1,outline='#c1d0d8',width=1,tags='added-puyo')
    canvas.create_line(0,cell,W*cell,cell,fill='#ff9b72',width=2)
    canvas.pack()
    return canvas


def format_board_text(board, pairs):
    """13 board rows followed by axis->child NEXT pairs; human editable text."""
    if len(board)!=H or any(len(row)!=W for row in board):
        raise ValueError('盤面のサイズが正しくありません')
    values=str(pairs).upper().replace(',', ' ').split()
    if len(values)!=3 or any(len(v)!=2 or not set(v)<=set(COLORS) for v in values):
        raise ValueError('ネクストは RB GY RR のように3組指定してください')
    return '\n'.join(board)+'\nNEXT: '+' '.join(values)+'\n'


def parse_board_text(text, fallback_pairs=None):
    """Read v25 text format and legacy board-only 13-line text."""
    lines=[line.strip() for line in text.splitlines() if line.strip()]
    next_lines=[line for line in lines if line.upper().startswith('NEXT:')]
    if len(next_lines)>1:
        raise ValueError('NEXT行は1行だけ指定してください')
    board_lines=[line for line in lines if not line.upper().startswith('NEXT:')]
    board=parse_board('\n'.join(board_lines))
    raw=next_lines[0].split(':',1)[1] if next_lines else fallback_pairs
    if raw is None:
        return board,None
    values=str(raw).upper().replace(',', ' ').split()
    if len(values)!=3 or any(len(v)!=2 or not set(v)<=set(COLORS) for v in values):
        raise ValueError('ネクストは RB GY RR のように3組指定してください')
    return board,' '.join(values)


class ChainAnimation(ttk.Frame):
    """Show a timed preview of each clear/drop; expand the static history on click.

    Visual timing is a simplified rendering of the calculated per-step frames.
    Tk's after callbacks are cancelled when the widget is destroyed.
    """
    def __init__(self, parent, chain, *, cell=18, on_copy=None, title='連鎖アニメーション', initial_bonus=0,
                 static_parent=None,caption_width=280):
        super().__init__(parent)
        self.chain=chain
        self.cell=cell
        self.on_copy=on_copy
        self.initial_bonus=initial_bonus if chain.steps else 0
        self.ojama_renderer=getattr(self.winfo_toplevel(),'ojama_display',None)
        self._job=None
        self._phase=0
        self._playing=True
        self._frames=self._build_frames(chain,self.initial_bonus)
        self.caption_holder=ttk.Frame(self,width=caption_width)
        self.caption_holder.pack(anchor='w')
        self._frame=tk.Label(self.caption_holder, text=title, font=('',9,'bold'),wraplength=caption_width,justify='left')
        self._frame.pack(anchor='w')
        # Reserve enough height for every animation caption, not just frame 0.
        heights=[]
        for _,caption,_,_ in self._frames:
            self._frame.configure(text=caption);heights.append(self._frame.winfo_reqheight())
        self.caption_height=max(heights,default=1)
        self.caption_holder.configure(height=self.caption_height)
        self.caption_holder.pack_propagate(False)
        self.canvas=tk.Canvas(self, width=W*cell+2,height=H*cell+2,bg='#202634',highlightthickness=0, cursor='hand2')
        self.ojama_holder=ttk.Frame(self)
        self.ojama_holder.pack(anchor='w',pady=(3,2))
        self.canvas.pack(anchor='w')
        self._displayed_score=None
        self.canvas.bind('<Button-1>',self.show_menu)
        self.canvas.bind('<Button-3>',self.show_menu)
        self._frame.bind('<Button-1>',self.show_menu)
        self._frame.bind('<Button-3>',self.show_menu)
        self._frame.configure(cursor='hand2')
        self.static=ttk.LabelFrame(static_parent,text=title+'・静止盤面') if static_parent is not None else ttk.Frame(self)

        self._draw_frame(0)
        self._job=self.after(self._frames[0][2],self._tick)
        self.bind('<Destroy>',self._destroyed)

    @staticmethod
    def _build_frames(chain,initial_bonus=0):
        frames=[]
        total=0
        score=initial_bonus if chain.steps else 0
        for step in chain.steps:
            total+=step.frames
            # Roughly reproduce one clear, vanish, fall per step using known states.
            score+=step.score
            header=f'{step.index}連鎖目 / {step.frames}F / {step.score:,}点（累計{total}F・{score:,}点）'
            erased=tuple(''.join('.' if (r,c) in set(step.erased)|set(step.erased_ojama) else ch
                        for c,ch in enumerate(row)) for r,row in enumerate(step.before))
            duration=max(140,round(step.frames*1000/60))
            # Double playback speed relative to v23 while keeping every visual phase.
            phase_ms=max(70,round(max(140,duration//3)/2))
            step_attack=step.score+(initial_bonus if step.index==1 else 0)
            frames.extend([(step.before,header,phase_ms,step_attack),
                           (erased,header,phase_ms,step_attack),
                           (step.after,header,phase_ms,step_attack)])
        if not frames:
            frames=[(chain.final,'連鎖なし',400,0)]
        return frames

    def show_nuisance(self,parent,score):
        ttk.Label(parent,text='この連鎖分',foreground='#7b838c',font=('',8)).pack(side='left',padx=(0,3))
        if self.ojama_renderer:
            self.ojama_renderer(parent,score,compact=True,subdued=True).pack(side='left')
        else:
            ttk.Label(parent,text=f'{nuisance(score):,}個',foreground='#7b838c',font=('',9)).pack(side='left')

    def _draw_frame(self,index):
        board,caption,_,score=self._frames[index]
        self._frame.configure(text=caption)
        if score!=self._displayed_score:
            for widget in self.ojama_holder.winfo_children():widget.destroy()
            self.show_nuisance(self.ojama_holder,score)
            self._displayed_score=score
        cv=self.canvas;cv.delete('all');cell=self.cell
        for r,row in enumerate(board):
            for c,ch in enumerate(row):
                x=c*cell;y=r*cell
                cv.create_rectangle(x,y,x+cell,y+cell,fill='#292f3e',outline='#465063')
                if ch!='.':cv.create_oval(x+2,y+2,x+cell-2,y+cell-2,fill=PALETTE[ch],outline='white')
        cv.create_line(0,cell,W*cell,cell,fill='#ff9b72',width=2)

    def _tick(self):
        self._job=None
        if not self.winfo_exists():return
        if self._playing and self._frames:
            self._phase=(self._phase+1)%len(self._frames)
            self._draw_frame(self._phase)
        delay=self._frames[self._phase][2] if self._playing else 200
        self._job=self.after(delay,self._tick)

    def show_menu(self, event):
        """The same cursor-position pop-up interaction as timeline board copy."""
        menu=tk.Menu(self,tearoff=0)
        menu.add_command(label='静止盤面を閉じる' if self.static.winfo_manager() else '静止盤面を展開',
                         command=self.toggle_static)
        menu.add_command(label='一時停止' if self._playing else '再生',command=self.toggle_play)
        try:
            menu.tk_popup(event.x_root,event.y_root)
        finally:
            menu.grab_release()
        return 'break'

    def toggle_play(self):
        self._playing=not self._playing

    def static_board_menu(self,event,board):
        if self.on_copy is None:
            return 'break'
        menu=tk.Menu(self,tearoff=0)
        menu.add_command(label='入力にコピー',
                         command=lambda b=tuple(board):self.on_copy(b))
        try:
            menu.tk_popup(event.x_root,event.y_root)
        finally:
            menu.grab_release()
        return 'break'

    def toggle_static(self):
        if self.static.winfo_manager():
            self.static.pack_forget()
            self._playing=True
            return
        self._playing=False
        if not self.static.winfo_children():
            boards=[]
            cumulative_frames=0
            cumulative_score=self.initial_bonus
            for i,step in enumerate(self.chain.steps):
                # The snapshot preceding a clear belongs to that chain step.
                cumulative_frames+=step.frames
                cumulative_score+=step.score
                step_attack=step.score+(self.initial_bonus if i==0 else 0)
                boards.append((f'{step.index}連鎖目（{step.frames}F / {step.score:,}点）',step.before,step_attack))
            if self.chain.steps:
                boards.append((f'{len(self.chain.steps)}連鎖後（{cumulative_frames}F / {cumulative_score:,}点）',
                               self.chain.final,step_attack))
            for i,(name,board,score) in enumerate(boards):
                frame=ttk.Frame(self.static);frame.grid(row=i//5,column=i%5,padx=3,pady=3,sticky='n')
                lbl=ttk.Label(frame,text=name,wraplength=155,cursor='hand2' if self.on_copy else '')
                lbl.pack()
                ojama=ttk.Frame(frame);ojama.pack(anchor='w',pady=(3,2))
                self.show_nuisance(ojama,score)
                canvas=draw_board(frame,board,14)
                if self.on_copy:
                    canvas.configure(cursor='hand2')
                    for widget in (lbl,canvas):
                        widget.bind('<Button-1>',lambda event,b=tuple(board):self.static_board_menu(event,b))
                        widget.bind('<Button-3>',lambda event,b=tuple(board):self.static_board_menu(event,b))
        self.static.pack(anchor='w',pady=4)

    def _destroyed(self,event):
        if event.widget is self and self._job is not None:
            try:self.after_cancel(self._job)
            except tk.TclError:pass
            self._job=None
    def destroy(self):
        # Destroy detached history before Tk destroys the animation's widgets;
        # doing it from <Destroy> can double-delete Tcl callback commands.
        try:
            if self.static.master is not self and self.static.winfo_exists():self.static.destroy()
        except tk.TclError:pass
        super().destroy()

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('PuyoAnalysis v1.0.2 — 連鎖STATS・3手全探索・テンパイ探索')
        self.geometry('1330x850');self.minsize(1020,690)
        self.ojama_icons = {}
        self.reference_icons = {}
        for name, filename in (('王冠','crown.png'),('月','moon.png'),('星','star.png'),
                               ('赤玉','red.png'),('大玉','large.png'),('小玉','small.png')):
            path = Path(__file__).resolve().parent / 'assets' / filename
            if path.exists():
                with Image.open(path) as source:
                    icon = source.convert('RGBA').resize((24, 24), Image.Resampling.NEAREST)
                self.ojama_icons[name] = ImageTk.PhotoImage(icon)
                quiet=icon.resize((18,18),Image.Resampling.LANCZOS)
                quiet.putalpha(quiet.getchannel('A').point(lambda value:round(value*0.55)))
                self.reference_icons[name]=ImageTk.PhotoImage(quiet)
        self.queue=Queue();self.results=[];self.stats=[];self.order=[];self.groups=[];self.filtered=[]
        self.tenpai_evaluations=[]
        self.input_tenpai_queue=Queue();self.input_tenpai_result=None
        self.input_tenpai_running=False
        self.input_tenpai_cancel=Event();self.input_tenpai_notice_timer=None;self.input_tenpai_notice=None
        self.input_tenpai_progress=None
        self.current=EMPTY;self.cells=[list(row) for row in EMPTY]
        self.paint=tk.StringVar(value='R');self.pairs_var=tk.StringVar(value='.. .. ..');self.view=tk.StringVar(value='summary')
        self.page=0;self.visible=[];self.selected_index=None
        self.score_bonus=tk.BooleanVar(value=False);self.eff_mode=tk.StringVar(value="used")
        self.applied_score_bonus=False;self.applied_eff_mode="used";self.applied_initial_bonus=False
        self.filters=[];self.custom_sort=None
        self.undo_stack=[];self._drag_snapshot=None;self.search_board=None
        self.search_context=None;self.pending_search_context=None;self.search_running=False
        self.chain_context=None
        self.review_session=None;self.review_mode=None
        self.imported_image=None;self.latest_record_result=None
        self.build();self.after(100,self.poll)

    def build(self):
        ttk.Label(self,text='13段目は最上行（隠し段） | 左クリック: 選択色を置く / 右クリック: 消す | 配置到達判定は簡易モデル・子ぷよ14段目は候補に含む（14段目・時間の試作は詳細設定からON）',foreground='#a34c00').pack(anchor='w',padx=10,pady=5)
        outer=ttk.Panedwindow(self,orient='horizontal');outer.pack(fill='both',expand=True,padx=8,pady=6)
        left_shell=ttk.Frame(outer);right=ttk.Frame(outer);outer.add(left_shell,weight=0);outer.add(right,weight=1)
        self.left_canvas=tk.Canvas(left_shell,width=260,highlightthickness=0)
        left_scroll=ttk.Scrollbar(left_shell,orient='vertical',command=self.left_canvas.yview)
        self.left_canvas.configure(yscrollcommand=left_scroll.set)
        left_scroll.pack(side='right',fill='y');self.left_canvas.pack(side='left',fill='both',expand=True)
        left=ttk.Frame(self.left_canvas);self.left_content=left
        left_item=self.left_canvas.create_window((0,0),window=left,anchor='nw')
        self.left_canvas.bind('<Configure>',lambda e:self.left_canvas.itemconfigure(left_item,width=e.width))
        left.bind('<Configure>',lambda e:(self.left_canvas.configure(scrollregion=self.left_canvas.bbox('all')),self.bind_left_scroll(left)))
        self.left_canvas.bind('<MouseWheel>',self.left_mousewheel)
        ttk.Label(left,text='① 盤面を入力',font=('',11,'bold')).pack(anchor='w')
        ttk.Label(left,text='色を選び、盤面・NEXTをクリック').pack(anchor='w')
        palette=ttk.Frame(left);palette.pack(anchor='w',pady=5)
        for i,ch in enumerate('.RBGYPO'):
            b=tk.Radiobutton(palette,text=NAMES[ch],variable=self.paint,value=ch,indicatoron=False,
                             bg=PALETTE[ch],fg=('white' if ch in '.RBGPO' else 'black'),
                             selectcolor=PALETTE[ch],width=6,relief='raised')
            b.grid(row=i//4,column=i%4,padx=1,pady=2)
        self.row14='......'
        self.row14_enabled=tk.BooleanVar(value=False)
        self.mawashi_frames=tk.StringVar(value='20')
        self.edit_cell=28
        hidden_line=ttk.Frame(left);self.hidden_line=hidden_line
        self.hidden_editor=tk.Canvas(hidden_line,width=168,height=14,bg='#eef0f2',highlightthickness=0)
        self.hidden_editor.pack(side='left')
        ttk.Label(hidden_line,text='14段',foreground='#8b9198',font=('',8)).pack(side='left')
        self.hidden_editor.bind('<Button-1>',lambda e:self.edit_row14(e,self.paint.get()))
        self.hidden_editor.bind('<Button-3>',lambda e:self.edit_row14(e,'.'))
        editor_row=ttk.Frame(left);editor_row.pack(anchor='w',pady=4)
        self.editor=tk.Canvas(editor_row,width=W*self.edit_cell,height=H*self.edit_cell,bg='#202634',highlightthickness=0)
        self.editor.pack(side='left')
        pair_area=ttk.Frame(editor_row);pair_area.pack(side='left',anchor='n',padx=(9,0))
        ttk.Label(pair_area,text='ネクスト3組',font=('',9,'bold')).pack(anchor='w')
        ttk.Label(pair_area,text='子上・軸下',font=('',8)).pack(anchor='w')
        # One vertical 2-cell field per pair: child on top, axis on bottom.
        # The stored pair string remains axis->child (e.g. RB).
        self.pair_canvases=[]
        self.pair_cell=28
        for index,title in enumerate(('現在手','ネクスト','ダブネク')):
            ttk.Label(pair_area,text=title).pack(anchor='w',pady=(8,0))
            canvas=tk.Canvas(pair_area,width=self.pair_cell,height=2*self.pair_cell,
                             bg='#202634',highlightthickness=0)
            canvas.pack(anchor='w',pady=(2,0))
            canvas.bind('<Button-1>',lambda event,i=index:self.click_pair(event,i,self.paint.get()))
            canvas.bind('<B1-Motion>',lambda event,i=index:self.click_pair(event,i,self.paint.get()))
            canvas.bind('<Button-3>',lambda event,i=index:self.click_pair(event,i,'.'))
            canvas.bind('<B3-Motion>',lambda event,i=index:self.click_pair(event,i,'.'))
            self.pair_canvases.append(canvas)
        self.pairs_var.trace_add('write',lambda *_:(self.redraw_pairs(),self.update_analysis_status()))
        self.redraw_pairs()
        self.editor.bind('<Button-1>',lambda e:self.edit_click(e,self.paint.get()))
        self.editor.bind('<B1-Motion>',lambda e:self.edit_click(e,self.paint.get()))
        self.editor.bind('<Button-3>',lambda e:self.edit_click(e,'.'))
        self.editor.bind('<B3-Motion>',lambda e:self.edit_click(e,'.'))
        self.editor.bind('<ButtonPress-1>',lambda e:self.start_paint(e,self.paint.get()))
        self.editor.bind('<ButtonPress-3>',lambda e:self.start_paint(e,'.'))
        self.editor.bind('<ButtonRelease-1>',self.end_paint)
        self.editor.bind('<ButtonRelease-3>',self.end_paint)
        self.bind_all('<Control-z>',self.undo_board)
        self.redraw_editor()
        ttk.Button(left,text='1操作戻す（Ctrl+Z）',command=self.undo_board).pack(fill='x',pady=2)
        ttk.Button(left,text='3手全探索前の盤面に戻す',command=self.restore_search_board).pack(fill='x',pady=2)
        ttk.Button(left,text='空盤面に戻す',command=self.clear).pack(fill='x',pady=2)
        ttk.Button(left,text='テキストで入力 / 貼り付け',command=self.text_import).pack(fill='x',pady=2)
        ttk.Button(left,text='画像から盤面を読み取る',command=self.image_import).pack(fill='x',pady=2)
        ttk.Button(left,text='クリップボードの画像を読み取る',command=self.image_import_clipboard).pack(fill='x',pady=2)
        self.review_save_btn=ttk.Button(left,text='振り返り記録に保存',command=self.save_review, state='disabled')
        ttk.Separator(left).pack(fill='x',pady=7)
        ttk.Label(left,text='③ 結果を保存',font=('',11,'bold')).pack(anchor='w')
        ttk.Button(left,text='盤面・解析結果を保存',command=self.save_standalone).pack(fill='x',pady=3)
        ttk.Label(left,text='3手探索は全候補CSVも一緒に保存',foreground='#66717c').pack(anchor='w')
        ttk.Button(left,text='保存した記録を開く・整理',command=self.open_record_manager).pack(fill='x',pady=3)
        ttk.Button(left,text='未検証ツールボックス',command=self.open_placement_lab).pack(fill='x',pady=3)
        self.review_csv=tk.BooleanVar(value=False)
        self.review_csv_check=ttk.Checkbutton(left,text='振り返り連携：全候補CSVも保存',variable=self.review_csv)
        self.initial_bonus=tk.BooleanVar(value=False)
        ttk.Label(right,text='② 解析する',font=('',11,'bold')).pack(anchor='w',padx=8)
        ttk.Label(right,text='盤面の連鎖を見るなら「連鎖STATS」、NEXTを置く候補を探すなら「3手全探索」').pack(anchor='w',padx=8,pady=3)
        self.analysis_status=ttk.Label(right,text='盤面を入力して、解析してください。',foreground='#66717c',wraplength=700)
        self.analysis_status.pack(anchor='w',padx=8,pady=3)
        self.details_button=ttk.Button(right,text='詳細設定を開く ▾',command=self.toggle_details)
        self.details_button.pack(anchor='w',padx=8,pady=3)
        self.details_frame=ttk.LabelFrame(right,text='解析の詳細設定',padding=8)
        ttk.Checkbutton(self.details_frame,text='14段目・設置判定をON',variable=self.row14_enabled,command=self.toggle_row14).pack(anchor='w')
        timing_options=ttk.Frame(self.details_frame);timing_options.pack(anchor='w')
        ttk.Label(timing_options,text='回し追加時間(F)：').pack(side='left')
        ttk.Entry(timing_options,textvariable=self.mawashi_frames,width=5).pack(side='left')
        self.mawashi_frames.trace_add('write',lambda *_:self.update_analysis_status())
        ttk.Label(self.details_frame,text='回し・到達判定・仮想落下は未検証',foreground='#77818b').pack(anchor='w')
        ttk.Checkbutton(self.details_frame,text='全消しボーナスを持って開始',variable=self.initial_bonus).pack(anchor='w')
        ttk.Label(self.details_frame,text='連鎖効率への全消しボーナス反映',font=('',10,'bold')).pack(anchor='w',pady=(5,1))
        for label, value in [('加算しない','none'),('その手で使用したボーナスを加算','used'),('その手で獲得したボーナスを加算','earned')]:
            ttk.Radiobutton(self.details_frame,text=label,variable=self.eff_mode,value=value).pack(anchor='w')
        ttk.Checkbutton(self.details_frame,text='3手探索：未使用の全消しボーナスを合計得点に含める',variable=self.score_bonus).pack(anchor='w',pady=(5,0))

        for setting in (self.initial_bonus,self.eff_mode,self.score_bonus):
            setting.trace_add('write',lambda *_:self.update_analysis_status())
        self.tabs=ttk.Notebook(right);self.tabs.pack(fill='both',expand=True)
        self.tab1=ttk.Frame(self.tabs);self.tab2=ttk.Frame(self.tabs)
        self.tabs.add(self.tab1,text='連鎖STATS');self.tabs.add(self.tab2,text='3手全探索')
        self.tab_tenpai=ttk.Frame(self.tabs);self.tabs.add(self.tab_tenpai,text='テンパイ探索')
        self.build_tenpai_tab()
        self.tabs.bind('<<NotebookTabChanged>>',lambda _:self.update_analysis_status())
        chain_actions=ttk.Frame(self.tab1);chain_actions.pack(fill='x',padx=8,pady=5)
        ttk.Button(chain_actions,text='この盤面の連鎖を計算',command=self.calculate_chain).pack(side='left')
        ttk.Button(chain_actions,text='火力・効率の基準表',command=self.show_reference).pack(side='left',padx=8)
        # Boards, total stats and tables scroll together in that order.
        chain_area=ttk.Frame(self.tab1)
        chain_area.pack(fill='both',expand=True,padx=8,pady=8)
        self.chain_canvas=tk.Canvas(chain_area,highlightthickness=0)
        self.chain_scroll=ttk.Scrollbar(chain_area,orient='vertical',command=self.chain_canvas.yview)
        self.chain_canvas.configure(yscrollcommand=self.chain_scroll.set)
        chain_xscroll=ttk.Scrollbar(chain_area,orient='horizontal',command=self.chain_canvas.xview)
        self.chain_canvas.configure(xscrollcommand=chain_xscroll.set)
        chain_xscroll.pack(side='bottom',fill='x')
        self.chain_scroll.pack(side='right',fill='y')
        self.chain_canvas.pack(side='left',fill='both',expand=True)
        self.chain_body=ttk.Frame(self.chain_canvas)
        self.chain_overview=ttk.Frame(self.chain_body);self.chain_overview.pack(fill='x',padx=8)
        self.chain_primary=ttk.Frame(self.chain_overview);self.chain_primary.pack(anchor='w')
        self.chain_summary=ttk.Frame(self.chain_overview)
        self.chain_summary.pack(anchor='w',padx=0)
        self.chain_details=ttk.Frame(self.chain_body);self.chain_details.pack(anchor='w')
        self.chain_canvas.create_window((0,0),window=self.chain_body,anchor='nw')
        self.chain_body.bind('<Configure>',lambda e:self.chain_canvas.configure(scrollregion=self.chain_canvas.bbox('all')))
        self.chain_canvas.bind('<Enter>',self._chain_scroll_enter)
        self.chain_canvas.bind('<Leave>',self._chain_scroll_leave)

        bar=ttk.Frame(self.tab2);bar.pack(fill='x',pady=5)
        self.search_button=ttk.Button(bar,text='NEXT 3組で全探索',command=self.start_search)
        self.search_button.pack(side='left',padx=5)
        ttk.Label(bar,text='並び順:').pack(side='left')
        self.sort=ttk.Combobox(bar,values=['3手合計得点','1手の最高得点','最大連鎖数','合計消去数'],state='readonly',width=15)
        self.sort.set('3手合計得点');self.sort.pack(side='left');self.sort.bind('<<ComboboxSelected>>',lambda e:(setattr(self,'custom_sort',None),self.show_results()))
        self.status=ttk.Label(bar,text='未探索');self.status.pack(side='left',padx=10)
        modebar=ttk.Frame(self.tab2);modebar.pack(fill='x',padx=5)
        ttk.Radiobutton(modebar,text='同じ得点をまとめる',variable=self.view,value='summary',command=self.show_results).pack(side='left')
        ttk.Radiobutton(modebar,text='全候補を表示',variable=self.view,value='detail',command=self.show_results).pack(side='left',padx=12)
        self.representative_label=ttk.Label(self.tab2,wraplength=820,text='代表: ちぎり最少 → 全消し最多 → 探索順')
        self.representative_label.pack(anchor='w',padx=7)
        responsebar=ttk.Frame(self.details_frame);responsebar.pack(fill='x',pady=(8,3))
        self.response_mode=tk.BooleanVar(value=False)
        self.response_limit=tk.StringVar(value='5')
        self.response_ranks={}
        ttk.Checkbutton(responsebar,text='対応想定で絞る・代表を選ぶ',variable=self.response_mode,
                        command=self.change_response_mode).pack(side='left')
        ttk.Label(responsebar,text='連鎖数の上限:').pack(side='left',padx=(12,3))
        limit=ttk.Combobox(responsebar,textvariable=self.response_limit,values=[str(n) for n in range(1,20)],
                           state='readonly',width=3)
        limit.pack(side='left');limit.bind('<<ComboboxSelected>>',lambda e:self.change_response_mode())
        ttk.Label(responsebar,text='連鎖（各手）').pack(side='left')

        self.filters_visible=False
        self.filter_button=ttk.Button(self.tab2,text='絞り込みを表示 ▼',command=self.toggle_filters)
        self.filter_button.pack(anchor='w',padx=7,pady=3)
        filterbar=ttk.LabelFrame(self.tab2,text='絞り込み（最大3条件・AND）')
        self.filterbar=filterbar
        self.filter_fields=['（条件なし）','合計得点','実獲得合計得点','未使用の全消しボーナス点','評価合計得点','連鎖得点','使用全消しボーナス点','1手の最高得点','最大連鎖数','合計連鎖数','合計消した色ぷよ数','合計ちぎり回数','全消し回数','全消しボーナス使用回数','最終全消し','1手の最高連鎖効率']
        for j in range(1,4):
            self.filter_fields.extend([f'{j}手目得点',f'{j}手目連鎖数',f'{j}手目消した色ぷよ数',f'{j}手目連鎖時間(秒)',f'{j}手目補充時間(秒)',f'{j}手目合計時間(秒)',f'{j}手目効率',f'{j}手目全消し',f'{j}手目全消しボーナス使用',f'{j}手目ちぎり',f'{j}手目配置'])
        self.filter_fields=['（条件なし）']+[label for _,label in result_fields()]
        for n in range(3):
            row=ttk.Frame(filterbar);row.pack(anchor='w',fill='x',pady=1)
            ttk.Label(row,text=f'条件{n+1}').pack(side='left',padx=4)
            field=ttk.Combobox(row,values=self.filter_fields,width=19,state='readonly');field.set('（条件なし）');field.pack(side='left')
            op=ttk.Combobox(row,values=['>=','<=','=','!=','>','<','含む'],width=5,state='readonly');op.set('>=');op.pack(side='left',padx=3)
            value=ttk.Entry(row,width=15);value.pack(side='left')
            self.filters.append((field,op,value))
        actions=ttk.Frame(filterbar);actions.pack(fill='x',pady=3)
        ttk.Button(actions,text='フィルター適用',command=self.show_results).pack(side='left',padx=4)
        ttk.Button(actions,text='条件をクリア',command=self.clear_filters).pack(side='left')
        ttk.Button(actions,text='絞り込み結果をCSV保存',command=lambda:self.export_csv(False)).pack(side='left',padx=10)
        ttk.Button(actions,text='全候補をCSV保存',command=lambda:self.export_csv(True)).pack(side='left')
        ttk.Label(actions,text='CSVは詳細列をすべて出力').pack(side='left',padx=8)
        tablewrap=ttk.Frame(self.tab2);tablewrap.pack(fill='both',expand=False,padx=5)
        self.table=ttk.Treeview(tablewrap,show='headings',height=5,selectmode='browse')
        self.table.pack(side='left',fill='both',expand=True)
        self.table.tag_configure('unreachable',foreground='#b43c3c')
        ybar=ttk.Scrollbar(tablewrap,orient='vertical',command=self.table.yview);ybar.pack(side='right',fill='y')
        xbar=ttk.Scrollbar(self.tab2,orient='horizontal',command=self.table.xview);xbar.pack(fill='x',padx=5)
        self.table.configure(yscrollcommand=ybar.set,xscrollcommand=xbar.set)
        self.table.bind('<<TreeviewSelect>>',self.select_result)
        self.setup_columns()
        pager=ttk.Frame(self.tab2);pager.pack(fill='x',padx=6,pady=4)
        self.prev_button=ttk.Button(pager,text='◀ 前の250件',command=lambda:self.change_page(-1));self.prev_button.pack(side='left')
        self.page_label=ttk.Label(pager,text='');self.page_label.pack(side='left',padx=10)
        self.next_button=ttk.Button(pager,text='次の250件 ▶',command=lambda:self.change_page(1));self.next_button.pack(side='left')
        ttk.Label(self.tab2,text='赤字：設置不可の手あり ／ —：未計算・算出不可',foreground='#77818b',font=('',8)).pack(anchor='w',padx=8)
        ttk.Label(self.tab2,text='選択候補の盤面推移',font=('',10,'bold')).pack(anchor='w',padx=8)
        self.detail_canvas=tk.Canvas(self.tab2,height=120)
        scroll=ttk.Scrollbar(self.tab2,orient='vertical',command=self.detail_canvas.yview)
        self.detail_canvas.configure(yscrollcommand=scroll.set)
        detail_xscroll=ttk.Scrollbar(self.tab2,orient='horizontal',command=self.detail_canvas.xview)
        self.detail_canvas.configure(xscrollcommand=detail_xscroll.set)
        detail_xscroll.pack(side='bottom',fill='x')
        scroll.pack(side='right',fill='y');self.detail_canvas.pack(fill='both',expand=True)
        self.detail_body=ttk.Frame(self.detail_canvas)
        self.detail_primary=ttk.Frame(self.detail_body);self.detail_primary.pack(fill='x',padx=5)
        self.detail=ttk.Frame(self.detail_body);self.detail.pack(anchor='w')
        self.detail_canvas.create_window((0,0),window=self.detail_body,anchor='nw')
        self.detail_body.bind('<Configure>',lambda e:(self.detail_canvas.configure(scrollregion=self.detail_canvas.bbox('all')),self._bind_detail_children_wheel(self.detail_body)))
        # Scroll only the pane underneath the pointer; the Treeview keeps its native wheel handling.
        self.detail_canvas.bind('<MouseWheel>',self._detail_mousewheel)
        self.detail_canvas.bind('<Button-4>',self._detail_mousewheel)
        self.detail_canvas.bind('<Button-5>',self._detail_mousewheel)
        self.detail.bind('<MouseWheel>',self._detail_mousewheel)
        self.detail.bind('<Button-4>',self._detail_mousewheel)
        self.detail.bind('<Button-5>',self._detail_mousewheel)

    def left_mousewheel(self,event):
        amount=(-1 if event.num==4 else 1) if getattr(event,'num',None) in (4,5) else -int(event.delta/120)
        if amount and self.left_canvas.bbox('all') and self.left_canvas.bbox('all')[3]>self.left_canvas.winfo_height():
            self.left_canvas.yview_scroll(amount,'units')
        return 'break'

    def bind_left_scroll(self,widget):
        for child in widget.winfo_children():
            for event in ('<MouseWheel>','<Button-4>','<Button-5>'):child.bind(event,self.left_mousewheel)
            self.bind_left_scroll(child)

    def _detail_mousewheel(self,event):
        amount = (-1 if event.num==4 else 1) if getattr(event,'num',None) in (4,5) else -int(event.delta/120)
        if amount:self.detail_canvas.yview_scroll(amount,'units')
        return 'break'

    def _bind_detail_children_wheel(self,widget):
        for child in widget.winfo_children():
            for event in ('<MouseWheel>','<Button-4>','<Button-5>'):
                child.bind(event,self._detail_mousewheel)
            self._bind_detail_children_wheel(child)

    def toggle_filters(self):
        self.filters_visible = not self.filters_visible
        if self.filters_visible:
            self.filterbar.pack(fill='x',padx=5,pady=2,after=self.filter_button)
            self.filter_button.configure(text='絞り込みを隠す ▲')
        else:
            self.filterbar.pack_forget()
            self.filter_button.configure(text='絞り込みを表示 ▼')

    def setup_columns(self):
        if self.tenpai_evaluations:
            columns=[('rank','#',50),('ignition_score','最高発火得点',115),('count','候補数',80),('ignition_chains','連鎖数',80),('ignition_time','連鎖時間(秒)',115),('ignition_erased','消費色ぷよ',100),('moves','3手の置き方',340)]
            self.table.configure(columns=[c[0] for c in columns],displaycolumns=[c[0] for c in columns])
            for key,label,width in columns:
                self.table.heading(key,text=label,command=lambda k=key:self.sort_by_column(k));self.table.column(key,width=width,minwidth=width,stretch=key=='moves')
            return
        summary=self.view.get()=='summary'
        if summary:
            columns=[('rank','#',48),('total','合計得点',100),('count','候補数',75),('chigiri','代表ちぎり回数',125),('clearcount','代表全消し回数',120),('max','代表1手の最高得点',115),('chains','代表の連鎖数',120),('moves','代表の置き方',340)]
            if self.response_mode.get():
                columns[3:3]=[('response_fires','代表発火回数',100),('response_eff','代表最高効率（点/秒）',155)]
        else:
            columns=[('rank','探索番号',80)]+[(key,label,min(245,max(95,len(label)*9))) for key,label in result_fields()]
        if self.tenpai_evaluations:columns.insert(1,('field_score','フィールド点',115))
        displayed=[c[0] for c in columns] if summary else ['rank']+[key for key,_ in visible_result_fields((self.search_context or {}).get('row14_enabled',False))]
        if self.tenpai_evaluations and not summary:displayed.insert(1,'field_score')
        self.table.configure(columns=[c[0] for c in columns],displaycolumns=displayed)
        for key,title,width in columns:
            self.table.heading(key,text=title,command=lambda k=key:self.sort_by_column(k))
            self.table.column(key,width=width,minwidth=width,stretch=key=='moves',anchor='w' if key.startswith('m') else 'center')

    def sort_by_column(self,key):
        if key in ('rank','count') and self.view.get()!='summary':return
        self.custom_sort=(key,not self.custom_sort[1]) if self.custom_sort and self.custom_sort[0]==key else (key,True)
        self.table.yview_moveto(0)
        self.show_results()
        self.table.yview_moveto(0)

    def change_response_mode(self):
        self.custom_sort=None
        self.representative_label.configure(text=(
            '代表: 発火1回以上で回数最少 → 最高効率 → ちぎり最少 → 全消し最多'
            if self.response_mode.get() else '代表: ちぎり最少 → 全消し最多 → 探索順'))
        self.show_results()

    def clear_filters(self):
        for field,op,value in self.filters:
            field.set('（条件なし）');op.set('>=');value.delete(0,'end')
        self.show_results()

    def active_filters(self):
        return [(dict((label,key) for key,label in result_fields()).get(f.get(),f.get()),o.get(),v.get()) for f,o,v in self.filters if f.get()!='（条件なし）' and v.get().strip()]

    def row_for(self,i):
        context=self.search_context or {}
        row=detail_row(self.results[i],self.stats[i],context.get('score_bonus',self.applied_score_bonus),context.get('efficiency_bonus_mode',self.applied_eff_mode),row14=context.get('row14','......'),initial_board=context.get('board'),row14_enabled=context.get('row14_enabled',False),mawashi_frames=context.get('mawashi_frames',20))
        if self.tenpai_evaluations:row['フィールド点']=self.tenpai_evaluations[i]['score']
        return row

    def placement_mawashi(self):
        value=int(self.mawashi_frames.get())
        if value<0:raise ValueError('回し追加時間は0以上で指定してください')
        return value

    def toggle_details(self):
        if self.details_frame.winfo_manager():
            self.details_frame.pack_forget()
            self.details_button.configure(text='詳細設定を開く ▾')
        else:
            self.details_frame.pack(fill='x',padx=8,pady=4,before=self.tabs)
            self.details_button.configure(text='詳細設定を閉じる ▴')

    def update_analysis_status(self):
        if not hasattr(self,'analysis_status') or not hasattr(self,'tabs'):return
        if hasattr(self,'tab_tenpai') and self.tabs.select()==str(self.tab_tenpai):
            result=self.input_tenpai_result
            changed=result is not None and tuple(self.board())!=tuple(result['board'])
            self.analysis_status.configure(text='入力盤面が変更されています。テンパイ探索の結果は前回の盤面のものです。' if changed else '入力盤面からテンパイと準備手を探索します。',foreground='#96652c' if changed else '#66717c');return
        search=self.tabs.select()==str(self.tab2)
        context=self.search_context if search else self.chain_context
        if search and self.search_running:
            text='3手全探索中です。';color='#66717c'
        elif context is None:
            text='盤面とNEXTを入力して「NEXT 3組で全探索」を押してください。' if search else '盤面を入力して「この盤面の連鎖を計算」を押してください。'
            color='#66717c'
        else:
            try:
                changed=tuple(self.board())!=tuple(context['board']) or self.row14_enabled.get()!=context.get('row14_enabled',False)
                if self.row14_enabled.get():changed=changed or self.row14!=context.get('row14','......')
                changed=changed or self.initial_bonus.get()!=context.get('initial_bonus',self.applied_initial_bonus)
                changed=changed or self.eff_mode.get()!=context.get('efficiency_bonus_mode',self.applied_eff_mode)
                if search:
                    changed=changed or tuple(self.pairs_var.get().upper().replace(',',' ').split())!=tuple(context['next_pairs'])
                    changed=changed or self.score_bonus.get()!=context.get('score_bonus',self.applied_score_bonus)
                    if self.row14_enabled.get():changed=changed or self.placement_mawashi()!=context.get('mawashi_frames',20)
            except ValueError:changed=True
            text=('入力・設定が変更されています。表示中の結果は前回の解析時のものです。' if changed else
                  '入力中の盤面・NEXTの探索結果です。' if search else '入力中の盤面の解析結果です。')
            color='#96652c' if changed else '#527366'
        self.analysis_status.configure(text=text,foreground=color)

    def saved_candidate_rows(self):
        for i in range(len(self.results)):
            row={'探索番号':i+1,**export_row(self.row_for(i))}
            yield {k:('' if v is None else 'あり' if v is True else 'なし' if v is False else round(v,3) if isinstance(v,float) else v) for k,v in row.items()}

    def export_csv(self,all_candidates=False):
        if not self.results:
            messagebox.showinfo('CSV保存','先に3手全探索を実行してください');return
        filename=filedialog.asksaveasfilename(defaultextension='.csv',filetypes=[('CSV','*.csv')],initialfile='puyo_candidates.csv' if all_candidates else 'puyo_filtered.csv')
        if not filename:return
        try:
            indices=range(len(self.results)) if all_candidates else self.filtered
            with open(filename,'w',encoding='utf-8-sig',newline='') as f:
                writer=None
                for i in indices:
                    row={'探索番号':i+1,**export_row(self.row_for(i))}
                    if writer is None:
                        writer=csv.DictWriter(f,fieldnames=list(row),extrasaction='ignore')
                        writer.writeheader()
                    writer.writerow({k:('' if v is None else 'あり' if v is True else 'なし' if v is False else round(v,3) if isinstance(v,float) else v) for k,v in row.items()})
                if writer is None:
                    # Even an empty filtered export has headers.
                    sample={'探索番号':0,**export_row(self.row_for(0))}
                    writer=csv.DictWriter(f,fieldnames=list(sample));writer.writeheader()
            messagebox.showinfo('CSV保存',f'{len(indices):,}候補を書き出しました。')
        except OSError as exc:
            messagebox.showerror('CSV保存エラー',str(exc))

    def toggle_row14(self):
        if self.row14_enabled.get():self.hidden_line.pack(anchor='w',before=self.editor.master)
        else:self.hidden_line.pack_forget()
        self.redraw_editor()

    def edit_row14(self,event,ch):
        col=event.x//28
        if 0<=col<6:
            self.end_paint()
            old=self.editor_state()
            value=list(self.row14);value[col]=ch;self.row14=''.join(value)
            self.remember_board(old);self.redraw_editor()

    def redraw_editor(self):
        self.update_analysis_status()
        if hasattr(self,'hidden_editor'):
            self.hidden_editor.delete('all')
            for c,ch in enumerate(self.row14):
                self.hidden_editor.create_rectangle(c*28,0,c*28+28,14,outline='#d6dbe0')
                if ch!='.':self.hidden_editor.create_oval(c*28+10,3,c*28+18,11,fill=PALETTE[ch],outline='')
        cv=self.editor;cv.delete('all');cell=self.edit_cell
        for r,row in enumerate(self.cells):
            for c,ch in enumerate(row):
                x,y=c*cell,r*cell
                cv.create_rectangle(x,y,x+cell,y+cell,fill='#292f3e',outline='#465063')
                if ch!='.':cv.create_oval(x+3,y+3,x+cell-3,y+cell-3,fill=PALETTE[ch],outline='white')
        cv.create_line(0,cell,W*cell,cell,fill='#ff9b72',width=2)

    def snapshot_board(self):
        return tuple(''.join(row) for row in self.cells)

    def editor_state(self):
        return {'board':self.snapshot_board(),'row14':self.row14}

    def remember_board(self, snapshot):
        if not isinstance(snapshot,dict):snapshot={'board':snapshot,'row14':self.row14}
        if snapshot != self.editor_state():
            self.undo_stack.append(snapshot)
            if len(self.undo_stack) > 100:
                self.undo_stack.pop(0)

    def start_paint(self, event, ch):
        self._drag_snapshot = self.editor_state()
        self.edit_click(event, ch)

    def end_paint(self, event=None):
        if self._drag_snapshot is not None:
            self.remember_board(self._drag_snapshot)
            self._drag_snapshot = None

    def undo_board(self, event=None):
        self.end_paint()
        if self.undo_stack:
            snapshot=self.undo_stack.pop()
            self.cells = [list(row) for row in snapshot['board']]
            self.row14=snapshot['row14']
            self.redraw_editor()

    def restore_search_board(self):
        if self.search_board is None:
            messagebox.showinfo('盤面を戻す', 'まだ3手全探索を実行していません。')
            return
        old = self.editor_state()
        self.row14=(self.search_context or {}).get('row14','......')
        self.mawashi_frames.set(str((self.search_context or {}).get('mawashi_frames',20)))
        self.row14_enabled.set((self.search_context or {}).get('row14_enabled',False));self.toggle_row14()
        self.cells = [list(row) for row in self.search_board]
        self.remember_board(old)
        self.redraw_editor()

    def edit_click(self,event,ch):
        c=event.x//self.edit_cell;r=event.y//self.edit_cell
        if 0<=r<H and 0<=c<W:
            if self.cells[r][c]!=ch:
                self.cells[r][c]=ch;self.redraw_editor()

    def board(self):
        return parse_board('\n'.join(''.join(row) for row in self.cells))

    def load_board(self):
        try:
            normalized=self.board()
            if normalized!=self.snapshot_board():
                self.remember_board(self.snapshot_board())
                self.cells=[list(row) for row in normalized]
                self.redraw_editor()
            self.current=normalized
            return True
        except ValueError as exc:messagebox.showerror('盤面入力エラー',str(exc));return False

    def clear(self):
        old=self.editor_state();self.row14='......';self.cells=[list(row) for row in EMPTY];self.remember_board(old);self.redraw_editor()

    def redraw_pairs(self):
        raw=self.pairs_var.get().upper().replace(',',' ').split()
        pairs=[raw[i][:2].ljust(2,'.') if i<len(raw) else '..' for i in range(3)]
        cell=self.pair_cell
        for i,canvas in enumerate(self.pair_canvases):
            canvas.delete('all')
            for row,side in enumerate((1,0)):  # top=child, bottom=axis
                ch=pairs[i][side]
                if ch not in PALETTE:ch='.'
                y=row*cell
                canvas.create_rectangle(0,y,cell,y+cell,fill='#292f3e',outline='#465063')
                if ch!='.':
                    canvas.create_oval(3,y+3,cell-3,y+cell-3,
                                      fill=PALETTE[ch],outline='white')

    def click_pair(self,event,index,color):
        row=event.y//self.pair_cell
        if row in (0,1):
            self.paint_pair(index,1-row,color)  # UI top=child, bottom=axis

    def paint_pair(self,index,side,color):
        raw=self.pairs_var.get().upper().replace(',',' ').split()
        pairs=[list(raw[i][:2].ljust(2,'.')) if i<len(raw) else ['.','.'] for i in range(3)]
        if pairs[index][side] != color:
            pairs[index][side]=color
            self.pairs_var.set(' '.join(''.join(pair) for pair in pairs))

    def text_import(self):
        dialog=tk.Toplevel(self);dialog.title('盤面・ネクストのテキスト入力');dialog.transient(self);dialog.grab_set()
        ttk.Label(dialog,text='上から13行、各行6文字（. R B G Y P O）。保存したNEXT:行も貼り付け可能').pack(anchor='w',padx=10,pady=6)
        entry=tk.Text(dialog,width=18,height=14,font=('Consolas',12));entry.pack(padx=10)
        entry.insert('1.0','\n'.join(''.join(row) for row in self.cells))
        ttk.Label(dialog,text='ネクスト3組（テキストは軸→子の順）例: RB GY RR').pack(anchor='w',padx=10,pady=(8,0))
        pairs_entry=ttk.Entry(dialog,width=24)
        pairs_entry.insert(0,self.pairs_var.get());pairs_entry.pack(anchor='w',padx=10)
        def apply():
            try:
                # A pasted NEXT: line takes precedence over the separate field.
                board,pairs=parse_board_text(entry.get('1.0','end'),pairs_entry.get())
            except ValueError as exc:
                messagebox.showerror('入力エラー',str(exc),parent=dialog)
                return
            old=self.editor_state();self.row14='......';self.cells=[list(row) for row in board];self.remember_board(old);self.redraw_editor()
            self.pairs_var.set(pairs);dialog.destroy()
        ttk.Button(dialog,text='盤面に反映',command=apply).pack(pady=8)

    def image_import_clipboard(self):
        """Read copied screenshot or Explorer-copied image file."""
        try:
            content=ImageGrab.grabclipboard()
            if isinstance(content,Image.Image):
                self.image_import(source_image=content)
            elif isinstance(content,list):
                supported={'.png','.jpg','.jpeg','.webp','.bmp'}
                file=next((str(f) for f in content if Path(f).suffix.lower() in supported),None)
                if file:self.image_import(filename=file)
                else:messagebox.showinfo('クリップボード画像','画像ファイルが見つかりません。')
            else:
                messagebox.showinfo('クリップボード画像','クリップボードに画像がありません。画像をコピーしてからもう一度試してください。')
        except Exception as exc:
            messagebox.showerror('クリップボード画像',str(exc))

    def image_import(self, filename=None, source_image=None):
        try:
            from PIL import Image, ImageTk
        except ImportError:
            messagebox.showinfo('画像読み込み', '画像入力には Pillow が必要です。\nPowerShellで次を実行してください:\n\n.\\.venv\\Scripts\\python.exe -m pip install Pillow')
            return
        if source_image is None:
            filename=filename or filedialog.askopenfilename(title='盤面のスクリーンショットを選択',filetypes=[('画像','*.png *.jpg *.jpeg *.webp *.bmp'),('すべて','*.*')])
            if not filename:return
        try:
            source=source_image if source_image is not None else Image.open(filename)
            source.load()
            source=source.convert('RGB')
        except Exception as exc:
            messagebox.showerror('画像読み込みエラー',str(exc));return
        window=tk.Toplevel(self);window.title('画像から盤面入力（1P・2P範囲指定）')
        window.geometry('950x780');window.minsize(560,450)
        ttk.Label(window,text='盤面の左上と右下を順番にクリック。6列×12段（通常）または13段で読み取り、結果を確認して反映してください。',wraplength=850).pack(anchor='w',padx=10,pady=5)
        ttk.Label(window,text='1P（左）・2P（右）の範囲を個別に記憶します。Tabキーまたはボタンで切り替え。NEXTは自動推定します。',wraplength=850).pack(anchor='w',padx=10)
        opts=ttk.Frame(window);opts.pack(fill='x',padx=10,pady=6)
        rows=tk.IntVar(value=12)
        ttk.Radiobutton(opts,text='12段（Switch・配信の通常画面）',variable=rows,value=12).pack(side='left')
        ttk.Radiobutton(opts,text='13段（最上段も画像内にある）',variable=rows,value=13).pack(side='left',padx=12)
        active_player=tk.StringVar(value='1P')
        player_bar=ttk.Frame(window);player_bar.pack(fill='x',padx=10)
        ttk.Label(player_bar,text='選択するフィールド：').pack(side='left')
        info=ttk.Label(window,text='1Pの盤面左上をクリックしてください');info.pack(anchor='w',padx=10)
        wrapper=ttk.Frame(window);wrapper.pack(fill='both',expand=True,padx=10,pady=6)
        cv=tk.Canvas(wrapper,bg='#1c2230',highlightthickness=0)
        xscroll=ttk.Scrollbar(wrapper,orient='horizontal',command=cv.xview)
        yscroll=ttk.Scrollbar(wrapper,orient='vertical',command=cv.yview)
        cv.configure(xscrollcommand=xscroll.set,yscrollcommand=yscroll.set)
        cv.grid(row=0,column=0,sticky='nsew');yscroll.grid(row=0,column=1,sticky='ns');xscroll.grid(row=1,column=0,sticky='ew')
        wrapper.rowconfigure(0,weight=1);wrapper.columnconfigure(0,weight=1)
        scale=min(1.,850/source.width,600/source.height)
        preview=source.resize((max(1,round(source.width*scale)),max(1,round(source.height*scale))))
        photo=ImageTk.PhotoImage(preview,master=window)
        cv.image_reference=photo
        cv.create_image(0,0,anchor='nw',image=photo,tags='background')
        cv.configure(scrollregion=(0,0,preview.width,preview.height))
        points=[]
        slots={}
        auto_candidates = suggest_crop(source.width,source.height)
        for player,(rectangle,nrows,reason) in auto_candidates.items():
            slots[player] = {'crop':list(rectangle),'rows':nrows}
        if auto_candidates:
            info.configure(text='縦横比から盤面を仮選択しました。格子位置を必ず確認し、必要ならクリックで修正してください。')
        # Remember crop per source + source resolution. Use normalized coordinates
        # so the preview scale and the original pixel coordinates stay consistent.
        saved_crop=None
        crop_id=None
        if self.review_session is not None:
            try:
                from review_crop import crop_key, load_crops, player_crops, save_player_crop
                session=json.loads(self.review_session.read_text(encoding='utf-8'))
                crop_id=crop_key(session.get('source_type'),session.get('source'),(source.width,source.height))
                saved_crop=load_crops().get(crop_id)
                slots.update(player_crops(saved_crop))
            except (OSError,ValueError,ImportError,KeyError):pass
        def show_grid():
            cv.delete('selection')
            if not points:return
            x1,y1=points[0]
            if len(points)==1:
                cv.create_oval(x1-4,y1-4,x1+4,y1+4,fill='yellow',tags='selection');return
            x2,y2=points[1]
            x1,x2=sorted((x1,x2));y1,y2=sorted((y1,y2))
            cv.create_rectangle(x1,y1,x2,y2,outline='yellow',width=2,tags='selection')
            for i in range(1,6):
                x=x1+(x2-x1)*i/6
                cv.create_line(x,y1,x,y2,fill='yellow',tags='selection')
            for i in range(1,rows.get()):
                y=y1+(y2-y1)*i/rows.get()
                cv.create_line(x1,y,x2,y,fill='yellow',tags='selection')
        def pick(event):
            x=max(0,min(preview.width,cv.canvasx(event.x)))
            y=max(0,min(preview.height,cv.canvasy(event.y)))
            if len(points)==2:points.clear()
            points.append((x,y));show_grid()
            info.configure(text='右下をクリックしてください' if len(points)==1 else '黄色の格子が各マスに合っているか確認し、「盤面に反映」を押してください。ずれていれば再クリックで指定し直せます。')
        cv.bind('<Button-1>',pick)
        def save_active_points():
            if len(points)==2:
                (x1,y1),(x2,y2)=points
                slots[active_player.get()]={'crop':[round(min(x1,x2)/scale),round(min(y1,y2)/scale),round(max(x1,x2)/scale),round(max(y1,y2)/scale)],'rows':rows.get()}
        def select_player(player):
            if player==active_player.get():return
            save_active_points()
            active_player.set(player)
            restore_player()
        def restore_player():
            points.clear()
            slot=slots.get(active_player.get())
            if slot:
                rect=slot.get('crop',[])
                if len(rect)==4 and 0<=rect[0]<rect[2]<=source.width and 0<=rect[1]<rect[3]<=source.height:
                    rows.set(int(slot.get('rows',12)))
                    points.extend([(rect[0]*scale,rect[1]*scale),(rect[2]*scale,rect[3]*scale)])
            show_grid()
            info.configure(text=f'{active_player.get()}：' + ('記憶した範囲を復元しました。' if len(points)==2 else '盤面左上をクリックしてください。'))
        ttk.Button(player_bar,text='1P（左）',command=lambda:select_player('1P')).pack(side='left',padx=4)
        ttk.Button(player_bar,text='2P（右）',command=lambda:select_player('2P')).pack(side='left',padx=4)
        window.bind('<Tab>',lambda e:(select_player('2P' if active_player.get()=='1P' else '1P'),'break')[1])
        restore_player()
        if auto_candidates and not saved_crop:
            info.configure(text='縦横比から候補を選択しました（推定）。格子がずれていれば2点をクリックし直してください。')
        rows.trace_add('write',lambda *_:show_grid())
        buttons=ttk.Frame(window);buttons.pack(fill='x',padx=10,pady=8)
        def apply():
            if len(points)!=2:
                messagebox.showwarning('範囲未指定','盤面の左上と右下をクリックしてください',parent=window);return
            (x1,y1),(x2,y2)=points
            crop=(round(min(x1,x2)/scale),round(min(y1,y2)/scale),round(max(x1,x2)/scale),round(max(y1,y2)/scale))
            crop=(max(0,crop[0]),max(0,crop[1]),min(source.width,crop[2]),min(source.height,crop[3]))
            try:board=recognize_board(source,crop,rows.get())
            except ValueError as exc:
                messagebox.showerror('認識エラー',str(exc),parent=window);return
            old=self.editor_state()
            self.row14='......'
            self.cells=[list(row) for row in board]
            self.imported_image=source.copy()
            self.remember_board(old)
            self.redraw_editor()
            # Standard eSports side NEXT preview is approximate; never overwrite
            # existing manual entries unless the field was blank.
            if self.pairs_var.get().strip() in ('.. .. ..',''):
                guessed=recognize_esports_next(source,crop,active_player.get())
                if any(pair!='..' for pair in guessed):
                    self.pairs_var.set(' '.join(['..']+guessed))
            if crop_id:
                try:
                    save_active_points()
                    for player,slot in slots.items():
                        save_player_crop(crop_id,player,slot['crop'],slot['rows'])
                except (OSError,ValueError) as exc:
                    messagebox.showwarning('範囲の記憶',f'範囲を保存できませんでした: {exc}',parent=window)
            window.destroy()
            messagebox.showinfo('読み取り完了' ,'盤面に反映しました。色の誤認識はクリックやドラッグで修正してください。')
        ttk.Button(buttons,text='盤面に反映',command=apply).pack(side='left')
        ttk.Button(buttons,text='範囲を指定し直す',command=lambda:(points.clear(),show_grid(),info.configure(text='画像上の盤面左上をクリックしてください'))).pack(side='left',padx=8)
        ttk.Button(buttons,text='キャンセル',command=window.destroy).pack(side='right')

    def save_board(self):
        if not self.load_board():return
        filename=filedialog.asksaveasfilename(defaultextension='.txt',filetypes=[('Text','*.txt')])
        if filename:
            try:
                value=format_board_text(self.current,self.pairs_var.get())
                with open(filename,'w',encoding='utf-8') as f:
                    f.write(value)
            except (OSError,ValueError) as exc:
                messagebox.showerror('テキスト保存エラー',str(exc))

    def _chain_scroll_enter(self,event):
        self.bind_all('<MouseWheel>',self._chain_mousewheel)
        self.bind_all('<Button-4>',self._chain_mousewheel)
        self.bind_all('<Button-5>',self._chain_mousewheel)

    def _chain_scroll_leave(self,event):
        self.unbind_all('<MouseWheel>')
        self.unbind_all('<Button-4>')
        self.unbind_all('<Button-5>')

    def _chain_mousewheel(self,event):
        if event.num == 4:
            amount=-1
        elif event.num == 5:
            amount=1
        else:
            amount=-int(event.delta / 120) if event.delta else 0
        if amount:
            self.chain_canvas.yview_scroll(amount,'units')
        return 'break'

    def calculate_chain(self):
        if not self.load_board():return
        self.applied_eff_mode=self.eff_mode.get();self.applied_initial_bonus=self.initial_bonus.get()
        self.chain_context={'board':tuple(self.current),'row14':self.row14,'row14_enabled':self.row14_enabled.get(),'initial_bonus':self.applied_initial_bonus,'efficiency_bonus_mode':self.applied_eff_mode}
        self.last_chain=simulate(self.current);self.review_mode='連鎖効率';self.render_chain(self.last_chain)
        self.update_analysis_status()

    def ojama_display(self, parent, score, *, compact=False, subdued=False):
        """Game-style icon sequence followed by :N個; no textual icon names."""
        frame = tk.Frame(parent,bg='#f7f8fa') if subdued else ttk.Frame(parent)
        def label(**kwargs):
            if subdued:
                kwargs.update(bg='#f7f8fa',fg='#7b838c')
                return tk.Label(frame,**kwargs)
            return ttk.Label(frame,**kwargs)
        parts = nuisance_parts(score)
        total = nuisance(score)
        if not parts:
            label(text=':0個', font=('',9) if subdued else ('',11,'bold')).pack(side='left')
            return frame
        remaining_slots = 6
        for name, count in parts:
            if remaining_slots <= 0:
                break
            count = min(count, remaining_slots)
            remaining_slots -= count
            icon = (self.reference_icons if subdued else self.ojama_icons).get(name)
            for _ in range(count):
                if icon:
                    label(image=icon).pack(side='left', padx=0)
                else:
                    label(text=name).pack(side='left')
        label(text=f':{total:,}個', font=('',9) if subdued else ('',10 if compact else 12,'bold')).pack(side='left',padx=(4,0))
        return frame

    def show_ojama_icons(self, parent, score):
        frame = ttk.Frame(parent)
        frame.pack(anchor='w', padx=5, pady=4)
        self.ojama_display(frame, score).pack(side='left')
        return frame

    def metric_card(self, parent, label, value, width=190):
        frame = ttk.Frame(parent, padding=(9, 7))
        frame.pack(side='left', anchor='n', padx=3, pady=3)
        ttk.Label(frame, text=label, font=('', 10)).pack(anchor='w')
        ttk.Label(frame, text=value, font=('', 19, 'bold')).pack(anchor='w')
        return frame

    def render_chain(self,result):
        eff,seconds,consume=efficiency(result,self.applied_eff_mode=='earned')
        if self.applied_eff_mode=='used' and self.applied_initial_bonus and result.count and seconds>0:
            eff+=2100/seconds
        for w in self.chain_summary.winfo_children():w.destroy()
        for w in self.chain_primary.winfo_children():w.destroy()
        metrics=ttk.Frame(self.chain_summary)
        metrics.pack(anchor='w')
        self.metric_card(metrics,'連鎖数',f'{result.count}連鎖')
        self.metric_card(metrics,'得点',f'{result.score + (2100 if self.applied_initial_bonus and result.count else 0):,}点')
        self.metric_card(metrics,'連鎖効率',f'{eff:,.2f} 点/秒')
        ttk.Label(self.chain_summary,text=f'全消しボーナス：使用 {2100 if self.applied_initial_bonus and result.count else 0:,}点 / 獲得 {2100 if result.count and all_clear(result.final) else 0:,}点').pack(anchor='w',padx=8)
        ttk.Label(self.chain_summary,text='おじゃま換算',font=('',11,'bold')).pack(anchor='w',padx=8,pady=(5,0))
        self.ojama_display(self.chain_summary,result.score + (2100 if self.applied_initial_bonus and result.count else 0)).pack(anchor='w',padx=8,pady=2)
        ttk.Label(self.chain_summary,text=f'色ぷよ消去 {result.erased}個 / おじゃま消去 {result.ojama}個\n連鎖時間 {result.frames/60:.3f}秒 / 補充時間 {consume:.3f}秒\n連鎖時間＋補充時間 {seconds:.3f}秒 / 全消し {"あり" if all_clear(result.final) else "なし"}',wraplength=510,justify='left').pack(anchor='w',padx=8,pady=4)
        for w in self.chain_details.winfo_children():w.destroy()
        enabled=(self.chain_context or {}).get('row14_enabled',False)
        delta=ghost_frames(result,(self.chain_context or {}).get('row14','......')) if enabled else None
        ttk.Label(self.chain_summary,text=f'仮想落下分 {delta}F / {delta/60:.3f}秒' if delta is not None else '仮想落下：OFF',foreground='#66717c').pack(anchor='w',padx=8)
        self.chain_canvas.yview_moveto(0)
        self.render_step_table(self.chain_details,result)
        if result.steps:
            ChainAnimation(self.chain_primary,result,cell=18,on_copy=self.copy_timeline_board,
                           initial_bonus=2100 if self.applied_initial_bonus else 0,
                           static_parent=None).pack(anchor='w',pady=3)
        else:
            draw_board(self.chain_primary,self.current,18)

    def render_step_table(self, parent, chain):
        if not chain.steps:
            return
        columns=('step','groups','erased','score','frames','fall')
        table=ttk.Treeview(parent,columns=columns,show='headings',height=min(7,len(chain.steps)))
        for key,label,width in [('step','連鎖',55),('groups','連結',155),('erased','色消去',75),('score','得点',105),('frames','時間(F)',80),('fall','最大落下',75)]:
            table.heading(key,text=label);table.column(key,width=width,anchor='center',stretch=False)
        for st in chain.steps:
            table.insert('', 'end', values=(st.index, ' / '.join(f'{color}{n}' for color,n in st.groups),len(st.erased),f'{st.score:,}',st.frames,st.fall))
        table.pack(anchor='w',padx=5,pady=4)

    def show_reference(self):
        window=tk.Toplevel(self)
        window.title('基準火力・効率（4個消し / 2ダブ・2トリ・2クア）')
        window.geometry('1120x720')
        ttk.Label(window,text='おじゃま表示：王冠=720個 / 月=360個 / 星=180個 / 赤玉=30個 / 大玉=6個 / 小玉=1個（70点=1個）').pack(anchor='w',padx=10,pady=(8,0))
        ttk.Label(window,text='4個消し＝100万TAとの比較／2ダブ系＝同じ残し高さの3・4・5連鎖を参考行に表示').pack(anchor='w',padx=10,pady=(3,0))
        notebook=ttk.Notebook(window);notebook.pack(fill='both',expand=True,padx=8,pady=8)
        four=ttk.Frame(notebook);multiple=ttk.Frame(notebook)
        notebook.add(four,text='4個消し 1〜19連鎖')
        notebook.add(multiple,text='2ダブ・2トリ・2クア')
        ttk.Label(four,text='各連鎖4個消し / 毎回1段落下80F / 連鎖後1個残り / 全消しボーナスなし').pack(anchor='w',padx=5,pady=5)

        def make_table(parent, rows, multiple_groups=False, reference_height=5):
            # Limit Tk widget count, especially for the 705 multi-clear rows.
            PAGE_ROWS=36
            holder=ttk.Frame(parent);holder.pack(fill='both',expand=True,padx=5,pady=5)
            controls=ttk.Frame(holder);controls.pack(fill='x',pady=(0,4))
            page_label=ttk.Label(controls)
            prev=ttk.Button(controls,text='◀ 前の36件')
            next_btn=ttk.Button(controls,text='次の36件 ▶')
            prev.pack(side='left',padx=3)
            page_label.pack(side='left',padx=8)
            next_btn.pack(side='left',padx=3)
            canvas=tk.Canvas(holder,highlightthickness=0)
            scroll=ttk.Scrollbar(holder,orient='vertical',command=canvas.yview)
            canvas.configure(yscrollcommand=scroll.set)
            scroll.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True)
            content=ttk.Frame(canvas)
            window_id=canvas.create_window((0,0),window=content,anchor='nw')
            content.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
            canvas.bind('<Configure>',lambda e:canvas.itemconfigure(window_id,width=e.width))
            labels=(['種類','連結数（複数はクリックで内訳）'] if multiple_groups else ['連鎖数'])
            labels+=['得点','おじゃま表示','連鎖時間(秒)','連鎖時間＋補充時間(秒)','効率(点/秒)']
            for j,title in enumerate(labels):
                ttk.Label(content,text=title,font=('',10,'bold'),padding=(8,7)).grid(row=0,column=j,sticky='w')
            nuisance_col=3 if multiple_groups else 2
            content.columnconfigure(nuisance_col,weight=1)
            state={'data':[],'page':0,'height':reference_height}
            def wheel(event):
                if getattr(event,'num',None) in (4,5):
                    direction=-1 if event.num==4 else 1
                else:
                    delta=getattr(event,'delta',0)
                    direction=-1 if delta>0 else (1 if delta<0 else 0)
                if direction:canvas.yview_scroll(direction,'units')
                return 'break'
            def bind_wheel(widget):
                widget.bind('<MouseWheel>',wheel)
                widget.bind('<Button-4>',wheel)
                widget.bind('<Button-5>',wheel)
                for child in widget.winfo_children():bind_wheel(child)
            def show_page():
                for child in list(content.grid_slaves()):
                    if int(child.grid_info()['row'])>0:child.destroy()
                data=state['data']
                pages=max(1,(len(data)+PAGE_ROWS-1)//PAGE_ROWS)
                page=max(0,min(state['page'],pages-1));state['page']=page
                subset=data[page*PAGE_ROWS:(page+1)*PAGE_ROWS]
                page_label.configure(text=f'{page+1}/{pages} ページ（{len(data)}件）')
                prev.configure(state='normal' if page>0 else 'disabled')
                next_btn.configure(state='normal' if page+1<pages else 'disabled')
                for i,row in enumerate(subset,1):
                    passed=0 if multiple_groups else sum(row['efficiency']>=b for b in TA_PACES.values())
                    background=('#f2f5f9','#e9f0f7','#dae7f2','#c8dced','#aecce3')[passed]
                    if row.get('reference'):background='#f7f8fa'
                    foreground='#7b838c' if row.get('reference') else '#162533'
                    values=([row['kind'],row['groups']] if multiple_groups else [f"{row['chain']}連鎖"])
                    values.append(f"{row['score']:,}")
                    for j,value in enumerate(values):
                        label=tk.Label(content,text=value,bg=background,fg=foreground,padx=8,pady=4,anchor='w')
                        label.grid(row=i,column=j,sticky='nsew')
                        if multiple_groups and j==1 and len(row.get('variants',[]))>1:
                            label.configure(cursor='hand2')
                            detail='\n'.join(f'{kind}：{groups}' for kind,groups in row['variants'])
                            label.bind('<Button-1>',lambda event,text=detail:messagebox.showinfo('同じ火力・効率の内訳',text,parent=window))
                    ojama_holder=tk.Frame(content,bg=background)
                    ojama_holder.grid(row=i,column=nuisance_col,sticky='nsew')
                    if row.get('reference'):
                        self.ojama_display(ojama_holder,row['score'],compact=True,subdued=True).pack(anchor='w',padx=8,pady=3)
                    else:
                        self.ojama_display(ojama_holder,row['score'],compact=True).pack(anchor='w',padx=8,pady=3)
                    time_values=[f"{row['frames']/60:.3f}",f"{row['seconds']:.3f}",f"{row['efficiency']:,.2f}"]
                    for j,value in enumerate(time_values,nuisance_col+1):
                        tk.Label(content,text=value,bg=background,fg=foreground,padx=8,pady=4,anchor='w').grid(row=i,column=j,sticky='nsew')
                bind_wheel(content)
                canvas.yview_moveto(0)
            def change_page(offset):state['page']+=offset;show_page()
            prev.configure(command=lambda:change_page(-1))
            next_btn.configure(command=lambda:change_page(1))
            for ev in ('<MouseWheel>','<Button-4>','<Button-5>'):canvas.bind(ev,wheel)
            def fill(data,reference_height=None):
                if reference_height is not None:state['height']=reference_height
                if multiple_groups:
                    data=group_equal_metrics(data)+[dict(four_clear_at_height(n,state['height']),kind=f'参考：{n}連鎖',groups='各連鎖4個消し',reference=True) for n in (3,4,5)]
                state['data']=sorted(data,key=lambda row:(row['efficiency'],row['score']))
                state['page']=0
                show_page()
            fill(rows)
            return fill
        ttk.Label(four,text='100万TA基準：12分 = 1,388.89 ／ 10分 = 1,666.67 ／ 8分 = 2,083.33 ／ 6分 = 2,777.78 点/秒').pack(anchor='w',padx=5)
        make_table(four,four_clear_rows())
        options=ttk.Frame(multiple);options.pack(fill='x',padx=5,pady=5)
        ttk.Label(options,text='連鎖後の高さ（全6列均一）:').pack(side='left')
        height=tk.IntVar(value=5);quick=tk.BooleanVar(value=False)
        spin=tk.Spinbox(options,from_=0,to=12,width=4,textvariable=height);spin.pack(side='left',padx=5)
        ttk.Checkbutton(options,text='2連鎖目クイック（55F） / OFF: 1段落下（80F）',variable=quick).pack(side='left',padx=8)
        ttk.Label(multiple,text='1連鎖目: 4個消し・1段落下80F固定 / 2連鎖目: 異なる2〜4色の同時消し').pack(anchor='w',padx=5)
        benchmark_label=ttk.Label(multiple)
        benchmark_label.pack(anchor='w',padx=5,pady=3)
        refresh_table=make_table(multiple,multi_rows(5,False),True,reference_height=5)
        def refresh(*_):
            try:
                h=int(height.get())
                benchmark_label.configure(text='効率の低い順に表示。灰色の参考行は同じ残し高さの4個消し3・4・5連鎖（積み込み時間を除く）。')
                refresh_table(multi_rows(h,quick.get()),reference_height=h)
            except (ValueError,tk.TclError):pass
        spin.configure(command=refresh)
        spin.bind('<KeyRelease>',refresh)
        quick.trace_add('write',refresh)
        refresh()

    def start_search(self):
        if not self.load_board():return
        try:
            parts=self.pairs_var.get().upper().replace(',',' ').split()
            if len(parts)!=3 or any(len(x)!=2 or not set(x)<=set(COLORS) for x in parts):raise ValueError('ネクストは「RB GY RR」の形式で3組指定')
            if dead(self.current):raise ValueError('開始盤面が窒息しています')
            mawashi=self.placement_mawashi() if self.row14_enabled.get() else 20
        except ValueError as exc:messagebox.showerror('入力エラー',str(exc));return
        self.pending_search_context={'board':tuple(self.current),'row14':self.row14,'row14_enabled':self.row14_enabled.get(),'mawashi_frames':mawashi,'next_pairs':tuple(parts),
            'tenpai_mode':False,
            'initial_bonus':self.initial_bonus.get(),'efficiency_bonus_mode':self.eff_mode.get(),
            'score_bonus':self.score_bonus.get(),
            'image':self.imported_image.copy() if self.imported_image is not None else None}
        self.search_running=True
        self.update_analysis_status()
        self.search_button.configure(state='disabled');self.status.configure(text='探索中…')
        board=self.current;bonus=self.pending_search_context['initial_bonus']
        def work():
            try:
                candidates=solve(board,tuple(parts),bonus)
                self.queue.put(('ok',(candidates,[])))
            except Exception as exc:self.queue.put(('error',str(exc)))
        Thread(target=work,daemon=True).start()

    def poll(self):
        try:
            kind,value=self.queue.get_nowait()
            if kind=='progress':
                self.status.configure(text=value);self.after(100,self.poll);return
            self.search_button.configure(state='normal')
            self.search_running=False
            if kind=='error':messagebox.showerror('探索エラー',value);self.status.configure(text='エラー')
            else:
                try:
                    self.search_context=self.pending_search_context
                    self.search_board=self.search_context['board']
                    self.applied_initial_bonus=self.search_context['initial_bonus']
                    self.applied_eff_mode=self.search_context['efficiency_bonus_mode']
                    self.applied_score_bonus=self.search_context['score_bonus']
                    self.review_mode='3手全探索'
                    self.results,self.tenpai_evaluations=value
                    self.stats=[candidate_stats(c,self.search_board,self.applied_initial_bonus) for c in self.results]
                    if self.tenpai_evaluations:
                        self.view.set('summary');self.sort.configure(values=['最高発火得点']);self.sort.set('最高発火得点');self.response_mode.set(False)
                    else:
                        self.sort.configure(values=['3手合計得点','1手の最高得点','最大連鎖数','合計消去数'])
                        if self.sort.get() in ('フィールド点','最高発火得点'):self.sort.set('3手合計得点')
                    self.custom_sort=None
                    self.show_results()
                except Exception as exc:
                    self.status.configure(text='結果表示エラー')
                    messagebox.showerror('結果表示エラー',str(exc))
            self.update_analysis_status()
        except Empty:pass
        self.after(100,self.poll)

    def candidate_unreachable(self,index):
        return index in getattr(self,'unreachable_candidates',set())

    def sorted_indices(self):
        if self.tenpai_evaluations:
            def key(i):
                response=self.best_tenpai_response(i)
                field=self.custom_sort[0] if self.custom_sort else 'ignition_score'
                return {'ignition_score':response['score'],'ignition_chains':response['chains'],'ignition_time':response['frames'],'ignition_erased':response['erased'],'moves':' / '.join(str(t.move) for t in self.results[i].turns)}.get(field,response['score'])
            return sorted(self.filtered,key=key,reverse=self.custom_sort[1] if self.custom_sort else True)
        if self.custom_sort:
            key,descending=self.custom_sort
            if key=='rank':return sorted(self.filtered,reverse=descending)
            if key in ('count','response_fires','response_eff'):return list(self.filtered)
            mapping={'actual':'実獲得合計得点','pending':'未使用の全消しボーナス点','total':'合計得点','raw':'連鎖得点','bonus':'使用全消しボーナス点','max':'1手の最高得点','maxchain':'最大連鎖数','erased':'合計消した色ぷよ数','chigiri':'合計ちぎり回数','clearcount':'全消し回数','bonuscount':'全消しボーナス使用回数','finalclear':'最終全消し','maxeff':'1手の最高連鎖効率','moves':'3手の置き方'}
            for j in range(1,4):
                mapping.update({f's{j}':f'{j}手目得点',f'c{j}':f'{j}手目連鎖数',f'n{j}':f'{j}手目消した色ぷよ数',f'cf{j}':f'{j}手目連鎖時間(秒)',f'ct{j}':f'{j}手目補充時間(秒)',f'tm{j}':f'{j}手目合計時間(秒)',f'e{j}':f'{j}手目効率',f'a{j}':f'{j}手目全消し',f'b{j}':f'{j}手目全消しボーナス使用',f't{j}':f'{j}手目ちぎり',f'm{j}':f'{j}手目配置'})
            name=mapping.get(key,key)
            if key=='field_score':return sorted(self.filtered,key=lambda i:self.tenpai_evaluations[i]['score'],reverse=descending)
            return sorted(self.filtered,key=lambda i:(self.row_for(i)[name] is not None,self.row_for(i)[name] if self.row_for(i)[name] is not None else 0),reverse=descending)
        def key(i):
            c=self.results[i];s=self.stats[i]
            selected=self.sort.get()
            if selected=='フィールド点':return (self.tenpai_evaluations[i]['score'] if self.tenpai_evaluations else 0,-s.chigiri_total,-i)
            if selected=='3手合計得点':return (s.total + (2100 if self.applied_score_bonus and s.pending_bonus else 0),-s.chigiri_total,s.clear_count,-i)
            if selected=='1手の最高得点':return (max(t.points for t in c.turns),s.total)
            if selected=='最大連鎖数':return (s.max_chain,s.total)
            return (s.erased,s.total)
        return sorted(self.filtered,key=key,reverse=True)

    def show_results(self):
        self.setup_columns();self.page=0
        if not self.results:
            self.order=[];self.groups=[];self.filtered=[];self.render_page();return
        conditions=self.active_filters()
        self.filtered=[i for i in range(len(self.results)) if matches_filters(self.row_for(i),conditions)] if conditions else list(range(len(self.results)))
        self.response_ranks={}
        if self.response_mode.get():
            mode=(self.search_context or {}).get('efficiency_bonus_mode',self.applied_eff_mode)
            for i in self.filtered:
                rank=response_priority(self.results[i],self.stats[i],int(self.response_limit.get()),mode)
                if rank is not None:self.response_ranks[i]=rank
            self.filtered=[i for i in self.filtered if i in self.response_ranks]
        if (self.search_context or {}).get('row14_enabled',False):
            self.unreachable_candidates=set()
            for i in self.filtered:
                row=self.row_for(i)
                if any(str(row.get(f'{n}手目設置判定','')).startswith('設置不可') for n in range(1,4)):self.unreachable_candidates.add(i)
        else:self.unreachable_candidates=set()
        self.order=sorted(self.sorted_indices(),key=self.candidate_unreachable)
        prefix='到達可能を優先 → ' if (self.search_context or {}).get('row14_enabled',False) else ''
        self.representative_label.configure(text='代表: '+prefix+('発火1回以上で回数最少 → 最高効率 → ちぎり最少 → 全消し最多' if self.response_mode.get() else 'ちぎり最少 → 全消し最多 → 探索順'))
        if self.tenpai_evaluations:self.representative_label.configure(text='最高発火得点で表示・グループ化 ／ 選択すると発火一覧を表示 ／ スコアは試作・別ボタン')
        self.groups=[]
        if self.view.get()=='summary':
            grouped={}
            for i in self.filtered:
                stat=self.stats[i];score=self.best_tenpai_response(i)['score'] if self.tenpai_evaluations else stat.total + (2100 if self.applied_score_bonus and stat.pending_bonus else 0)
                grouped.setdefault(score,[]).append(i)
            def representative_key(i):
                if self.tenpai_evaluations:
                    response=self.best_tenpai_response(i)
                    return (self.candidate_unreachable(i),response['frames'],response['erased'],i)
                if self.response_mode.get():return (self.candidate_unreachable(i),*self.response_ranks[i],i)
                return (self.candidate_unreachable(i),self.stats[i].chigiri_total,-self.stats[i].clear_count,i)
            self.groups=[(score,indices,min(indices,key=representative_key)) for score,indices in grouped.items()]
            if self.custom_sort and self.custom_sort[0]=='count':
                self.groups.sort(key=lambda g:len(g[1]),reverse=self.custom_sort[1])
            elif self.custom_sort and self.custom_sort[0] in ('response_fires','response_eff'):
                offset=0 if self.custom_sort[0]=='response_fires' else 1
                sign=1 if offset==0 else -1
                self.groups.sort(key=lambda g:sign*self.response_ranks[g[2]][offset],reverse=self.custom_sort[1])
            elif self.custom_sort and self.custom_sort[0] in ('chigiri','clearcount','max','chains','moves'):
                key=self.custom_sort[0]
                def val(g):
                    i=g[2];s=self.stats[i];c=self.results[i]
                    return {'chigiri':s.chigiri_total,'clearcount':s.clear_count,'max':s.max_fire,'chains':s.max_chain,'moves':' / '.join(str(t.move) for t in c.turns)}[key]
                self.groups.sort(key=val,reverse=self.custom_sort[1])
            elif not self.tenpai_evaluations and (self.sort.get()=='3手合計得点' or (self.custom_sort and self.custom_sort[0]=='total')):
                self.groups.sort(key=lambda g:g[0],reverse=self.custom_sort[1] if self.custom_sort and self.custom_sort[0]=='total' else True)
            else:
                rank={idx:pos for pos,idx in enumerate(self.order)}
                self.groups.sort(key=lambda g:min(rank[i] for i in g[1]))
            self.groups.sort(key=lambda group:self.candidate_unreachable(group[2]))
        self.render_page()

    def change_page(self,delta):
        size=len(self.groups) if self.view.get()=='summary' else len(self.order)
        next_page=self.page+delta
        if 0<=next_page<max(1,(size+PAGE_SIZE-1)//PAGE_SIZE):self.page=next_page;self.render_page()

    def render_page(self):
        summary=self.view.get()=='summary';items=self.groups if summary else self.order
        total=len(items);start=self.page*PAGE_SIZE;page_items=items[start:start+PAGE_SIZE]
        self.table.delete(*self.table.get_children());self.visible=[]
        def yes(x):return 'あり' if x else 'なし'
        def ef(x):return f'{x:,.1f}' if x is not None else '—'
        for n,item in enumerate(page_items,start+1):
            i=item[2] if summary else item
            cand=self.results[i];stat=self.stats[i];row=self.row_for(i)
            if summary:
                values=(n,f'{item[0]:,}',len(item[1]),stat.chigiri_total,stat.clear_count,f'{row["1手の最高得点"]:,}', '-'.join(str(t.chain.count) for t in cand.turns),row['3手の置き方'])
                if self.response_mode.get():
                    rank=self.response_ranks[i]
                    values=values[:3]+(rank[0],ef(-rank[1]))+values[3:]
            else:
                def formatted(value):
                    if value is None:return '—'
                    if isinstance(value,bool):return yes(value)
                    if isinstance(value,float):return f'{value:,.3f}'
                    if isinstance(value,int):return f'{value:,}'
                    return value
                values=[i+1]+[formatted(row.get(key)) for key,_ in result_fields()]
            if self.tenpai_evaluations:
                response=self.best_tenpai_response(i)
                values=(n,f'{response["score"]:,}',len(item[1]) if summary else 1,response['chains'],f'{response["frames"]/60:.3f}',response['erased'],row['3手の置き方'])
            self.table.insert('','end',iid=str(n-start-1),values=values,tags=('unreachable',) if self.candidate_unreachable(i) else ())
            self.visible.append(i)
        pages=max(1,(total+PAGE_SIZE-1)//PAGE_SIZE)
        self.page_label.configure(text=f'{self.page+1}/{pages} ページ（{start+1 if total else 0}–{min(start+PAGE_SIZE,total)} / {total:,}）')
        self.prev_button.configure(state='normal' if self.page>0 else 'disabled')
        self.next_button.configure(state='normal' if self.page+1<pages else 'disabled')
        self.status.configure(text=f'全{len(self.results):,}候補 / 条件一致{len(self.filtered):,}件 / {len(self.groups):,}得点グループ' if summary else f'全{len(self.results):,}候補 / 条件一致{len(self.filtered):,}件')
        if self.visible:self.table.selection_set('0');self.table.focus('0');self.select_result(None)
        else:
            for w in self.detail_primary.winfo_children():w.destroy()
            for w in self.detail.winfo_children():w.destroy()

    def load_saved_review(self, path):
        """Restore a previously saved board and options for editing or re-analysis."""
        try:
            data=json.loads(Path(path).read_text(encoding='utf-8'))
            board=parse_board('\n'.join(data['board']))
            old=self.editor_state()
            self.cells=[list(row) for row in board]
            self.remember_board(old)
            self.redraw_editor()
            self.current=board
            pairs=data.get('next_pairs')
            if isinstance(pairs,list) and pairs:
                self.pairs_var.set(' '.join(pairs))
            self.initial_bonus.set(bool(data.get('initial_bonus',False)))
            self.eff_mode.set(data.get('efficiency_bonus_mode', 'earned' if data.get('include_future_bonus',False) else 'none'))
            mode=data.get('analysis_type')
            if mode=='連鎖効率':
                self.tabs.select(self.tab1)
                self.calculate_chain()
            elif mode=='3手全探索':
                self.tabs.select(self.tab2)
                # Do not automatically run an expensive exhaustive search.
            messagebox.showinfo('盤面・NEXTを読み込む','保存済みの盤面を読み込みました。\n必要に応じて修正・再計算してください。')
        except (OSError,KeyError,TypeError,ValueError) as e:
            messagebox.showerror('盤面の再読み込み',str(e))

    def configure_review(self, session_path):
        """A session is a private one-shot JSON file exchanged with the video player."""
        path=Path(session_path).resolve()
        if not path.is_file():
            messagebox.showerror('振り返り連携','セッションファイルが見つかりません。')
            return
        try:
            info=json.loads(path.read_text(encoding='utf-8'))
            if info.get('session_version') != 1 or not info.get('id'):
                raise ValueError('セッション形式が不正です')
        except (OSError,ValueError) as exc:
            messagebox.showerror('振り返り連携',str(exc));return
        self.review_session=path
        self.review_save_btn.configure(state='normal')
        self.review_save_btn.pack(fill='x',pady=(12,3))
        self.review_csv_check.pack(anchor='w',pady=3)

    @staticmethod
    def serialize_chain(chain):
        return {
            'chains':chain.count,'score':chain.score,'erased_colors':chain.erased,
            'erased_ojama':chain.ojama,'frames':chain.frames,
            'final_board':list(chain.final),
            'steps':[{'index':t.index,'score':t.score,'frames':t.frames,
                      'fall':t.fall,'groups':[list(g) for g in t.groups],
                      'before':list(t.before),'after':list(t.after),
                      'erased_colors':len(t.erased),'erased_ojama':len(t.erased_ojama)}
                     for t in chain.steps],
        }


    def open_tenpai_probe(self):
        self.tabs.select(self.tab_tenpai)

    def standalone_result(self):
        """Save a snapshot even when no exhaustive search candidate is selected."""
        if self.tabs.select()==str(self.tab_tenpai):
            if self.input_tenpai_result:
                data=self.input_tenpai_result
                return {'type':'テンパイ探索','board':list(data['board']),'analysis_input':{'board':list(data['board'])},'tenpai_search':data}
            return {'type':'盤面のみ','board':list(self.current)}
        if self.review_mode == '3手全探索' and self.results and self.visible and self.table.selection():
            chosen=int(self.table.selection()[0])
            if 0 <= chosen < len(self.visible):
                index=self.visible[chosen]
                result=self.results[index]
                stats=self.stats[index]
                return {'type':'3手全探索','board':list(self.search_board or self.current),
                        'tenpai_evaluation':self.tenpai_evaluations[index] if self.tenpai_evaluations else None,
                        'selected_index':index,'total_score':stats.total,
                        'chigiri':stats.chigiri_total,'all_clears':stats.clear_count,
                        'turns':[{'move':str(t.move),'score':t.points,
                                  'placed_board':list(t.placed),
                                  'chain':self.serialize_chain(t.chain)} for t in result.turns]}
        if self.review_mode in ('連鎖効率','連鎖STATS'):
            chain=simulate(self.current)
            return {'type':'連鎖STATS','board':list(self.current),
                    'chain':self.serialize_chain(chain)}
        return {'type':'盤面のみ','board':list(self.current)}

    def save_standalone(self,use_search=None):
        if self.search_running or self.input_tenpai_running:
            messagebox.showinfo('探索中','探索が完了してから保存してください。');return
        if not self.load_board():return
        context=self.search_context if self.review_mode=='3手全探索' and self.tabs.select()!=str(self.tab_tenpai) else None
        pairs=self.pairs_var.get().upper().replace(',',' ').split()
        if context and use_search is None and (tuple(self.current)!=tuple(context['board']) or tuple(pairs)!=tuple(context['next_pairs']) or self.row14_enabled.get()!=context.get('row14_enabled',False) or (self.row14_enabled.get() and (self.row14!=context.get('row14','......') or self.placement_mawashi()!=context.get('mawashi_frames',20)))):
            choice=tk.Toplevel(self);choice.title('保存する盤面・NEXTを選択')
            choice.transient(self);choice.grab_set();choice.resizable(False,False)
            ttk.Label(choice,text='探索後に盤面またはNEXTが変更されています。\nどちらを保存しますか？',padding=14).pack()
            def choose(original):
                choice.destroy()
                self.save_standalone(original)
            ttk.Button(choice,text='探索時の盤面・NEXT（探索結果・CSV付き）',command=lambda:choose(True)).pack(fill='x',padx=14,pady=5)
            ttk.Button(choice,text='現在の盤面・NEXT＋前回の探索結果・CSV',command=lambda:choose(False)).pack(fill='x',padx=14,pady=5)
            ttk.Label(choice,text='解析結果・CSVはどちらも前回の探索時のものを保存します。',padding=10).pack()
            ttk.Button(choice,text='キャンセル',command=choice.destroy).pack(pady=(0,12))
            return
        dialog=tk.Toplevel(self);dialog.title('解析・盤面を記録')
        dialog.geometry('520x380');dialog.transient(self);dialog.grab_set()
        ttk.Label(dialog,text='保存先フォルダ').pack(anchor='w',padx=12,pady=(12,2))
        folders=record_store.folders()
        folder=tk.StringVar(value=folders[0])
        combo=ttk.Combobox(dialog,textvariable=folder,values=folders,state='readonly')
        combo.pack(fill='x',padx=12)
        ttk.Label(dialog,text='名前（動画の時刻・試合名など自由入力）').pack(anchor='w',padx=12,pady=(10,2))
        name=tk.StringVar()
        ttk.Entry(dialog,textvariable=name).pack(fill='x',padx=12)
        ttk.Label(dialog,text='メモ').pack(anchor='w',padx=12,pady=(10,2))
        memo=tk.Text(dialog,height=7);memo.pack(fill='both',expand=True,padx=12)
        def do_save():
            try:
                board=list(context['board']) if context and use_search is not False else list(self.current)
                pairs=list(context['next_pairs']) if context and use_search is not False else self.pairs_var.get().upper().replace(',',' ').split()
                result=self.standalone_result()
                if context:
                    result.update(type='3手全探索',board=list(context['board']),next_pairs=list(context['next_pairs']),
                        initial_bonus=context['initial_bonus'],efficiency_bonus_mode=context['efficiency_bonus_mode'],
                        score_bonus=context['score_bonus'])
                    result['analysis_input']={'board':list(context['board']),'next_pairs':list(context['next_pairs']),'row14':context.get('row14','......'),'row14_enabled':context.get('row14_enabled',False)}
                    result['saved_input_differs']=board!=list(context['board']) or pairs!=list(context['next_pairs'])
                result['row14']=context.get('row14','......') if context and use_search is not False else self.row14
                result['row14_enabled']=context.get('row14_enabled',False) if context and use_search is not False else self.row14_enabled.get()
                result['mawashi_frames']=context.get('mawashi_frames',20) if context and use_search is not False else (self.placement_mawashi() if self.row14_enabled.get() else 20)
                result['analysis_mawashi_frames']=context.get('mawashi_frames',20) if context else result['mawashi_frames']
                result['analysis_row14_enabled']=context.get('row14_enabled',False) if context else self.row14_enabled.get()
                result['analysis_row14']=context.get('row14','......') if context else self.row14
                if not context and result['type']=='連鎖STATS':result['ghost_frames']=ghost_frames(simulate(self.current),self.row14) if self.row14_enabled.get() else None
                image=context['image'] if context and use_search is not False else self.imported_image
                record_store.save(folder.get(),name.get(),result['type'],
                                  memo.get('1.0','end-1c'),board,pairs,
                                  result,image,self.saved_candidate_rows() if context else None)
                dialog.destroy()
                messagebox.showinfo('保存','記録に保存しました。')
            except Exception as exc:messagebox.showerror('保存エラー',str(exc),parent=dialog)
        ttk.Button(dialog,text='保存',command=do_save).pack(pady=10)

    def open_placement_lab(self):
        from placement_lab import open_lab
        try:open_lab(self)
        except ValueError as exc:messagebox.showerror('未検証ツールボックス',str(exc))

    def open_record_manager(self):
        window=tk.Toplevel(self);window.title('保存した記録の管理')
        window.geometry('1200x650');window.minsize(950,560)
        bar=ttk.Frame(window);bar.pack(fill='x',padx=10,pady=8)
        ttk.Label(bar,text='表示するフォルダ：').pack(side='left')
        folder=tk.StringVar(value='すべて')
        combo=ttk.Combobox(bar,textvariable=folder,state='readonly',width=27)
        combo.pack(side='left',padx=4)
        search=tk.StringVar()
        ttk.Label(bar,text='記録名・メモを検索：').pack(side='left',padx=(15,2))
        ttk.Entry(bar,textvariable=search,width=27).pack(side='left')
        ttk.Label(window,text='列名をクリックで並べ替え ／ 記録をダブルクリックで盤面・NEXTを読み込み',foreground='#66717c').pack(anchor='w',padx=10)
        columns=('name','analysis_type','memo','saved_at','folder')
        content=ttk.Frame(window);content.pack(fill='both',expand=True,padx=10,pady=4)
        listing=ttk.Frame(content);listing.pack(side='left',fill='both',expand=True)
        preview=ttk.LabelFrame(content,text='選択中の記録',padding=10,width=210)
        preview.pack(side='right',fill='y',padx=(10,0));preview.pack_propagate(False)
        table=ttk.Treeview(listing,columns=columns,show='headings',height=18)
        table.grid(row=0,column=0,sticky='nsew')
        vertical=ttk.Scrollbar(listing,orient='vertical',command=table.yview)
        vertical.grid(row=0,column=1,sticky='ns')
        horizontal=ttk.Scrollbar(listing,orient='horizontal',command=table.xview)
        horizontal.grid(row=1,column=0,sticky='ew')
        table.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set)
        listing.rowconfigure(0,weight=1);listing.columnconfigure(0,weight=1)
        sort_state={'key':None,'reverse':False}
        headings={}
        def sort_by(key):
            sort_state['reverse']=not sort_state['reverse'] if sort_state['key']==key else False
            sort_state['key']=key
            refresh()
        for key,label,width in [('name','記録名',180),
                                ('analysis_type','保存した内容',110),('memo','メモ',260),
                                ('saved_at','保存日時',180),('folder','保存先フォルダ',150)]:
            headings[key]=label
            table.heading(key,text=label,command=lambda k=key:sort_by(k));table.column(key,width=width,minwidth=45)
        def refresh(*_):
            selection=table.selection()
            choices=['すべて']+record_store.folders()
            combo['values']=choices
            if folder.get() not in choices:folder.set('すべて')
            table.delete(*table.get_children())
            records=record_store.list_records(None if folder.get()=='すべて' else folder.get())
            key=sort_state['key']
            if key:
                if key=='saved_at':
                    from datetime import datetime
                    def sort_value(record):
                        try:return datetime.fromisoformat(record.get(key,'')).timestamp()
                        except (ValueError,TypeError):return 0
                else:
                    def sort_value(record):return str(record.get(key,'')).casefold()
                records=sorted(records,key=sort_value,reverse=sort_state['reverse'])
            for column,label in headings.items():
                suffix=(' ▼' if sort_state['reverse'] else ' ▲') if column==key else ''
                table.heading(column,text=label+suffix)
            for r in records:
                if search.get().lower() not in (r.get('name','')+' '+r.get('memo','')).lower():continue
                table.insert('','end',iid=r['id'],values=tuple(r.get(k,'') for k in columns))
            if selection and table.exists(selection[0]):table.selection_set(selection[0])
            update_buttons()
        def chosen():
            selection=table.selection()
            return selection[0] if selection else None
        def restore():
            if not chosen():return
            try:
                item=record_store.load(chosen())
                old=self.editor_state()
                self.row14=validate_row14((item.get('analysis_result') or {}).get('row14','......'))
                self.mawashi_frames.set(str((item.get('analysis_result') or {}).get('mawashi_frames',20)))
                self.row14_enabled.set(bool((item.get('analysis_result') or {}).get('row14_enabled',False)));self.toggle_row14()
                self.cells=[list(row) for row in item['board']]
                self.remember_board(old);self.redraw_editor()
                self.pairs_var.set(' '.join(item.get('next_pairs') or ['..','..','..']))
                self.imported_image=None
                picture=record_store.attachment(chosen(),'screenshot')
                if picture:
                    from PIL import Image
                    with Image.open(picture) as source:self.imported_image=source.convert('RGB')
                self.search_context=None;self.search_board=None
                self.tenpai_evaluations=[]
                self.chain_context=None
                self.results=[];self.stats=[];self.visible=[];self.review_mode=None
                self.table.delete(*self.table.get_children())
                self.latest_record_result=item.get('analysis_result')
                settings=item.get('analysis_result') or {}
                self.initial_bonus.set(bool(settings.get('initial_bonus',False)))
                self.eff_mode.set(settings.get('efficiency_bonus_mode','used'))
                self.score_bonus.set(bool(settings.get('score_bonus',False)))
                self.update_analysis_status()
                window.destroy()
                messagebox.showinfo('復元','盤面とNEXTを復元しました。保存済み解析結果は記録JSONにも残っています。')
            except Exception as exc:messagebox.showerror('復元エラー',str(exc),parent=window)
        def open_saved_file(kind):
            if not chosen():return
            try:
                item=record_store.load(chosen())
                directory=record_store.record_directory(chosen())
                target=(directory if kind=='folder' else directory/'record.json' if kind=='json'
                        else record_store.attachment(chosen(),'screenshot' if kind=='image' else 'csv_file'))
                if target is None or not target.exists():raise FileNotFoundError('保存ファイルがありません。')
                os.startfile(str(target))
            except Exception as exc:messagebox.showerror('ファイルを開く',str(exc),parent=window)
        def make_folder():
            value=simpledialog.askstring('フォルダを作成','フォルダ名',parent=window)
            if not value:return
            try:record_store.add_folder(value);folder.set(value);refresh()
            except Exception as exc:messagebox.showerror('フォルダ',str(exc),parent=window)
        def move():
            if not chosen():return
            record_id=chosen()
            current=record_store.load(record_id)['folder']
            destinations=[name for name in record_store.folders() if name!=current]
            if not destinations:
                messagebox.showinfo('記録を移動','移動先のフォルダを先に作成してください。',parent=window);return
            dialog=tk.Toplevel(window);dialog.title('移動先フォルダを選択')
            dialog.transient(window);dialog.grab_set()
            ttk.Label(dialog,text='移動先フォルダを選択',padding=10).pack(anchor='w')
            options=tk.Listbox(dialog,height=min(10,len(destinations)),width=42,exportselection=False)
            for destination in destinations:options.insert('end',destination)
            options.pack(fill='both',expand=True,padx=12,pady=4)
            options.selection_set(0);options.activate(0);options.focus_set()
            def confirm(*_):
                selected=options.curselection()
                if not selected:return
                try:
                    record_store.move(record_id,options.get(selected[0]))
                    dialog.destroy();refresh()
                except Exception as exc:messagebox.showerror('移動エラー',str(exc),parent=dialog)
            buttons=ttk.Frame(dialog);buttons.pack(padx=12,pady=10)
            ttk.Button(buttons,text='このフォルダへ移動',command=confirm).pack(side='left',padx=4)
            ttk.Button(buttons,text='キャンセル',command=dialog.destroy).pack(side='left',padx=4)
            options.bind('<Double-Button-1>',confirm)
            dialog.bind('<Return>',confirm);dialog.bind('<Escape>',lambda _:dialog.destroy())
        def edit():
            if not chosen():return
            item=record_store.load(chosen())
            new_name=simpledialog.askstring('名前を変更','名前',initialvalue=item['name'],parent=window)
            if new_name is None:return
            new_memo=simpledialog.askstring('メモを編集','メモ',initialvalue=item.get('memo',''),parent=window)
            if new_memo is None:return
            try:record_store.update(chosen(),new_name,new_memo);refresh()
            except Exception as exc:messagebox.showerror('編集エラー',str(exc),parent=window)
        controls=ttk.Frame(window);controls.pack(fill='x',padx=10,pady=8)
        ttk.Button(controls,text='フォルダを作成',command=make_folder).pack(side='left',padx=4)
        selection_buttons=[]
        for position,(label,callback) in enumerate([('盤面・NEXTを読み込む',restore),('記録を別フォルダへ移動',move),
                               ('記録名・メモを編集',edit),('記録データを開く（JSON）',lambda:open_saved_file('json')),
                               ('保存画像を開く',lambda:open_saved_file('image')),
                               ('3手探索結果を開く（CSV）',lambda:open_saved_file('csv')),
                               ('保存フォルダを開く',lambda:open_saved_file('folder'))]):
            if position==4:
                controls=ttk.Frame(window);controls.pack(fill='x',padx=10,pady=(0,8))
            button=ttk.Button(controls,text=label,command=callback,state='disabled')
            button.pack(side='left',padx=4)
            selection_buttons.append((label,button))
        ttk.Button(controls,text='一覧を更新',command=refresh).pack(side='left',padx=4)
        def update_buttons(*_):
            record_id=chosen()
            for child in preview.winfo_children():child.destroy()
            if not record_id:
                ttk.Label(preview,text='一覧から記録を選ぶと\n盤面とNEXTを表示します。',foreground='#66717c',wraplength=185).pack(anchor='w')
            else:
                try:
                    item=record_store.load(record_id)
                    board=item.get('board')
                    if not isinstance(board,(list,tuple)) or len(board)!=H or any(
                        not isinstance(row,str) or len(row)!=W or not set(row)<=set(PALETTE) for row in board):
                        raise ValueError('保存された盤面の形式が正しくありません。')
                    pairs=item.get('next_pairs') or ['..']*3
                    if not isinstance(pairs,(list,tuple)) or len(pairs)!=3 or any(
                        not isinstance(pair,str) or len(pair)!=2 or not set(pair)<=set('.'+COLORS) for pair in pairs):
                        raise ValueError('保存されたNEXTの形式が正しくありません。')
                    ttk.Label(preview,text=item.get('name') or '名前なし',wraplength=185).pack(anchor='w',pady=(0,8))
                    ttk.Label(preview,text='保存した盤面',foreground='#66717c').pack(anchor='w')
                    draw_board(preview,board,cell=20)
                    ttk.Label(preview,text='NEXT 3組（上：子／下：軸）',foreground='#66717c').pack(anchor='w',pady=(10,4))
                    next_canvas=tk.Canvas(preview,name='record_next',width=156,height=52,bg='#202634',highlightthickness=0)
                    next_canvas.pack()
                    for index,pair in enumerate(pairs):
                        for row,ch in enumerate((pair[1],pair[0])):
                            x=12+index*50;y=3+row*24
                            next_canvas.create_rectangle(x,y,x+22,y+22,fill='#292f3e',outline='#465063')
                            if ch!='.':next_canvas.create_oval(x+2,y+2,x+20,y+20,fill=PALETTE[ch],outline='#ffffff')
                    ttk.Label(preview,text='読み込む前に内容を確認できます。',wraplength=185,foreground='#66717c').pack(anchor='w',pady=(10,0))
                except Exception:
                    for child in preview.winfo_children():child.destroy()
                    ttk.Label(preview,text='プレビューを表示できません。\n記録ファイルを確認してください。',wraplength=185,foreground='#a34c00').pack(anchor='w')
            has_image=False
            has_csv=False
            if record_id:
                try:
                    has_image=record_store.attachment(record_id,'screenshot') is not None
                    has_csv=record_store.attachment(record_id,'csv_file') is not None
                except Exception:pass
            for label,button in selection_buttons:
                button.configure(state='normal' if record_id and (label!='保存画像を開く' or has_image) and (label!='3手探索結果を開く（CSV）' or has_csv) else 'disabled')
        table.bind('<<TreeviewSelect>>',update_buttons)
        table.bind('<Double-Button-1>',lambda _:restore())
        combo.bind('<<ComboboxSelected>>',refresh)
        search.trace_add('write',refresh)
        refresh()
        update_buttons()

    def save_review(self):
        if self.search_running:
            messagebox.showinfo('探索中','探索が完了してから保存してください。');return
        if self.review_session is None:
            messagebox.showwarning('振り返り連携','録画ツールから起動してください。');return
        if not self.load_board():return
        if self.review_mode == '3手全探索':
            selection=self.table.selection()
            if not selection or not self.visible:
                messagebox.showwarning('候補未選択','3手全探索で候補を選択してください。');return
            row_index=int(selection[0])
            if not 0 <= row_index < len(self.visible):return
            index=self.visible[row_index]
            candidate=self.results[index]
            stats=self.stats[index]
            data={
                'type':'3手全探索','board':list(self.search_board),
                'next_pairs':list(self.search_context['next_pairs']),
                'initial_bonus':self.search_context['initial_bonus'],
                'selected_index':index,'total_score':stats.total,
                'chigiri':stats.chigiri_total,'all_clears':stats.clear_count,
                'turns':[{
                    'move':str(t.move),'score':t.points,
                    'earned_all_clear_bonus':2100 if t.used_bonus else 0,
                    'placed_board':list(t.placed),
                    'chain':self.serialize_chain(t.chain)
                } for t in candidate.turns]
            }
        elif self.review_mode == '連鎖効率':
            from common.engine import efficiency
            chain=simulate(self.current)
            eff,seconds,consume=efficiency(chain,self.applied_eff_mode=='earned')
            if self.applied_eff_mode=='used' and self.applied_initial_bonus and chain.count and seconds>0:
                eff+=2100/seconds
            data={'type':'連鎖効率','board':list(self.current),
                  'chain':self.serialize_chain(chain),
                  'efficiency':eff,'seconds':seconds,'consumption_seconds':consume,
                  'used_all_clear_bonus':2100 if self.applied_initial_bonus and chain.count else 0,
                  'earned_all_clear_bonus':2100 if chain.count and all_clear(chain.final) else 0,
                  'include_future_bonus':self.applied_eff_mode=='earned', 'efficiency_bonus_mode':self.applied_eff_mode, 'initial_bonus':self.applied_initial_bonus}
        else:
            # A board-only bookmark can be analyzed later from the review list.
            data={'type':'盤面のみ','board':list(self.current),
                  'next_pairs':self.pairs_var.get().upper().split(),
                  'initial_bonus':bool(self.initial_bonus.get()),
                  'efficiency_bonus_mode':self.eff_mode.get()}
        try:
            session=json.loads(self.review_session.read_text(encoding='utf-8'))
            out=Path(session['output']).resolve()
            if out.parent != self.review_session.parent:
                raise ValueError('保存先がセッションフォルダ外です')
            if data['type']=='3手全探索' and self.review_csv.get():
                csv_dir=Path.home()/'PuyoReview'/'csv'
                csv_dir.mkdir(parents=True,exist_ok=True)
                csv_path=csv_dir/('candidates_'+session['id'][:12]+'.csv')
                # Export every candidate using the same columns as the standalone CSV export.
                with csv_path.open('w',encoding='utf-8-sig',newline='') as f:
                    writer=None
                    for i in range(len(self.results)):
                        row={'探索番号':i+1,**export_row(self.row_for(i))}
                        if writer is None:
                            writer=csv.DictWriter(f,fieldnames=list(row),extrasaction='ignore')
                            writer.writeheader()
                        writer.writerow({k:('' if v is None else 'あり' if v is True else 'なし' if v is False else round(v,3) if isinstance(v,float) else v) for k,v in row.items()})
                data['csv_path']=str(csv_path)
                data['csv_count']=len(self.results)
            result={'session_id':session['id'],'analysis':data}
            tmp=out.with_suffix('.tmp')
            tmp.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            tmp.replace(out)
            # Keep the analysis window open. The review app will foreground itself
            # when it receives the result; do not emit an extra success dialog.
            self.lower()
        except (OSError,KeyError,ValueError) as exc:
            messagebox.showerror('保存エラー',str(exc))

    def copy_timeline_board(self, board):
        target=tuple(board)
        if len(target)!=H or any(len(row)!=W for row in target):
            raise ValueError('盤面のサイズが正しくありません')
        old=self.editor_state()
        if target!=old['board']:
            self.cells=[list(row) for row in target]
            self.remember_board(old)
            self.redraw_editor()
        self.status.configure(text='盤面推移から入力盤面にコピーしました。再計算するとこの盤面を使います。')

    def timeline_menu(self,event,board):
        menu=tk.Menu(self,tearoff=0)
        menu.add_command(label='入力にコピー',command=lambda b=tuple(board):self.copy_timeline_board(b))
        try:menu.tk_popup(event.x_root,event.y_root)
        finally:menu.grab_release()
        return 'break'

    def select_result(self,event):
        selected=self.table.selection()
        if not selected:return
        idx=int(selected[0])
        if not 0<=idx<len(self.visible):return
        cand=self.results[self.visible[idx]]
        for w in self.detail_primary.winfo_children():w.destroy()
        for w in self.detail.winfo_children():w.destroy()
        self.detail_canvas.yview_moveto(0)
        turn_summaries=[]
        tables=ttk.Frame(self.detail);tables.pack(anchor='w')
        for j,t in enumerate(cand.turns,1):
            if t.chain.count:
                eff, seconds, consumed = efficiency(t.chain,self.applied_eff_mode=='earned')
                from_bonus = 2100 if t.used_bonus else 0
                if self.applied_eff_mode=='used' and seconds > 0: eff += from_bonus / seconds
                delta=self.row_for(self.visible[idx])[f'{j}手目仮想落下分(F)']
                ghost_text=f'{delta}F ({delta/60:.3f}秒)' if delta is not None else 'OFF'
                turn_summaries.append(f'{j}手目：{t.chain.count}連鎖 / {t.points:,}点 / 効率 {eff:,.2f}点/秒 / {seconds:.3f}秒 / 仮想落下 {ghost_text}')
                ttk.Label(tables,text=f'{j}手目・各連鎖の詳細',font=('',10,'bold')).pack(anchor='w',padx=5,pady=(8,0))
                self.render_step_table(tables,t.chain)
        line=ttk.Frame(self.detail_primary);line.pack(anchor='w')
        initial=(self.search_context or {}).get('board',self.search_board or self.current)
        sequence=[('開始',initial,None,())]
        chain_bonuses={id(t.chain):2100 if t.used_bonus else 0 for t in cand.turns}
        for j,t in enumerate(cand.turns,1):
            previous=initial if j==1 else cand.turns[j-2].chain.final
            overflow_note='（子14段目）' if (t.move.direction=='U' and previous[0][t.move.col]=='.' and previous[1][t.move.col]!='.') else ''
            sequence.append((f'{j}手目 {t.move}{overflow_note}\n配置後',t.placed,None,new_placement_cells(previous,t.placed)))
            if t.chain.count:
                sequence.append((f'{j}手目 {t.chain.count}連鎖',t.chain.final,t.chain,()))
        row=ttk.Frame(line);row.pack(anchor='w')
        cards=[]
        for i,(title,board,chain,highlight) in enumerate(sequence):
            frame=ttk.Frame(row);frame.grid(row=i//7,column=i%7,padx=5,pady=5,sticky='n')
            heading=ttk.Frame(frame,width=125);heading.pack()
            heading_label=ttk.Label(heading,text=title,justify='center',wraplength=125);heading_label.pack()
            if chain:
                animation=ChainAnimation(frame,chain,cell=14,on_copy=self.copy_timeline_board,
                               initial_bonus=chain_bonuses.get(id(chain),0),static_parent=None,
                               caption_width=125,title=title)
                animation.pack()
                cards.append((heading,heading_label,animation,None))
            else:
                spacer=ttk.Frame(frame,width=125,height=1);spacer.pack()
                cards.append((heading,heading_label,None,spacer))
                canvas=draw_board(frame,board,14,highlight=highlight)
                canvas.configure(cursor='hand2')
                canvas.bind('<Button-1>',lambda event,b=tuple(board):self.timeline_menu(event,b))
                canvas.bind('<Button-3>',lambda event,b=tuple(board):self.timeline_menu(event,b))
        title_height=max(label.winfo_reqheight() for _,label,_,_ in cards)
        caption_height=max((animation.caption_height for _,_,animation,_ in cards if animation),default=0)
        icon_height=max((animation.ojama_holder.winfo_reqheight() for _,_,animation,_ in cards if animation),default=0)
        for heading,_,animation,spacer in cards:
            heading.configure(height=title_height);heading.pack_propagate(False)
            if animation:
                animation.caption_holder.configure(height=caption_height)
                animation.ojama_holder.configure(width=125,height=icon_height);animation.ojama_holder.pack_propagate(False)
            else:spacer.configure(height=caption_height+icon_height+(5 if caption_height else 0))
        ttk.Label(self.detail_primary,text=f'3手合計 {self.row_for(self.visible[idx])["合計得点"]:,}点 / ちぎり {self.stats[self.visible[idx]].chigiri_total}回 / 全消し {self.stats[self.visible[idx]].clear_count}回',font=('',11,'bold')).pack(anchor='w',padx=5,pady=(5,1))
        if turn_summaries:
            ttk.Label(self.detail_primary,text='\n'.join(turn_summaries),justify='left',wraplength=900).pack(anchor='w',padx=5)
        ttk.Label(self.detail_primary,text='薄い枠＝今回置いたぷよ ／ 盤面クリックでコピー・静止盤面の展開',foreground='#66717c').pack(anchor='w',padx=5,pady=(2,4))
        if self.tenpai_evaluations:
            data=self.tenpai_evaluations[self.visible[idx]]
            ttk.Label(self.detail,text='3手後のテンパイ発火一覧',font=('',10,'bold')).pack(anchor='w',pady=6,before=tables)
            ttk.Button(self.detail,text='対応スコア・フィールド点を開く（試作）',command=lambda:self.open_evaluation(data)).pack(anchor='w',before=tables)
            preview=ttk.Frame(self.detail)
            ResponseList(self.detail,data['responses'],lambda response:self.show_response_preview(preview,tuple(data['board']),response)).pack(fill='x',before=tables)
            preview.pack(anchor='w',before=tables)

    def best_tenpai_response(self,index):
        return min(self.tenpai_evaluations[index]['responses'],key=lambda r:(-r['score'],r['frames'],r['erased']),default=dict(score=0,chains=0,frames=0,erased=0))

    def open_evaluation(self,evaluation):
        win=tk.Toplevel(self);win.title('対応スコア・フィールド点（試作）');win.geometry('1120x560')
        self.render_tenpai_evaluation(win,evaluation)

    def show_response_preview(self,parent,initial,response):
        for child in parent.winfo_children():child.destroy()
        ready=tuple(response.get('ready_board',initial));placed=ready
        for color in response['pieces']:placed=add_color(placed,response['column']-1,color)
        for label,board,highlight in [('探索元',initial,()),('準備後（枠＝追加）',ready,new_placement_cells(initial,ready)),('発火前（枠＝追加）',placed,new_placement_cells(initial,placed))]:
            holder=ttk.Frame(parent);holder.pack(side='left',anchor='n',padx=6)
            ttk.Label(holder,text=label,wraplength=110).pack();draw_board(holder,board,14,highlight=highlight).pack()
        ChainAnimation(parent,simulate(placed),cell=14,on_copy=self.copy_timeline_board,title='発火後',caption_width=140).pack(side='left',anchor='n',padx=6)

    def build_tenpai_tab(self):
        actions=ttk.Frame(self.tab_tenpai);actions.pack(fill='x',padx=8,pady=6)
        self.input_shanten=tk.StringVar(value='1')
        ttk.Label(actions,text='最大シャンテン:').pack(side='left')
        ttk.Combobox(actions,textvariable=self.input_shanten,values=('0','1','2','3'),state='readonly',width=3).pack(side='left',padx=5)
        self.input_tenpai_button=ttk.Button(actions,text='入力盤面から探索',command=self.start_input_tenpai);self.input_tenpai_button.pack(side='left',padx=5)
        ttk.Label(self.tab_tenpai,text='準備は色ぷよのみ。発火手だけ「色」または「おじゃま＋色」。20秒を超えたら中断ボタンを表示し、探索は続けます。',wraplength=850).pack(anchor='w',padx=8)
        self.input_tenpai_status=ttk.Label(self.tab_tenpai,text='未探索。0＝テンパイ、1＝色ぷよ1個を準備してテンパイ。');self.input_tenpai_status.pack(anchor='w',padx=8,pady=5)
        area=ttk.Frame(self.tab_tenpai);area.pack(fill='both',expand=True)
        canvas=tk.Canvas(area,highlightthickness=0);ys=ttk.Scrollbar(area,orient='vertical',command=canvas.yview);xs=ttk.Scrollbar(area,orient='horizontal',command=canvas.xview)
        canvas.configure(yscrollcommand=ys.set,xscrollcommand=xs.set);ys.pack(side='right',fill='y');xs.pack(side='bottom',fill='x');canvas.pack(fill='both',expand=True)
        self.input_tenpai_body=ttk.Frame(canvas);canvas.create_window((0,0),window=self.input_tenpai_body,anchor='nw')
        self.input_tenpai_body.bind('<Configure>',lambda _:canvas.configure(scrollregion=canvas.bbox('all')))

    def start_input_tenpai(self):
        if not self.load_board():return
        board=tuple(self.current);depth=int(self.input_shanten.get())
        self.input_tenpai_running=True
        self.input_tenpai_cancel=Event();cancel=self.input_tenpai_cancel
        self.input_tenpai_progress=None
        self.input_tenpai_button.configure(state='disabled');self.input_tenpai_status.configure(text='探索中…')
        self.input_tenpai_notice_timer=self.after(20000,self.show_input_tenpai_notice)
        def work():
            try:self.input_tenpai_queue.put(('ok',search_tenpai(board,depth,seconds_limit=None,state_limit=None,cancelled=cancel.is_set,progress=lambda d,n:setattr(self,'input_tenpai_progress',(d,n)))))
            except Exception as exc:self.input_tenpai_queue.put(('error',str(exc)))
        Thread(target=work,daemon=True).start();self.after(100,self.poll_input_tenpai)

    def poll_input_tenpai(self):
        try:kind,result=self.input_tenpai_queue.get_nowait()
        except Empty:
            if self.input_tenpai_progress:
                depth,checked=self.input_tenpai_progress
                text=f'{depth}シャンテン探索中… {checked:,}盤面を確認'
                if self.input_tenpai_cancel.is_set():text='中断処理中…'
                self.input_tenpai_status.configure(text=text)
                if self.input_tenpai_notice and self.input_tenpai_notice.winfo_exists():self.input_tenpai_notice_status.configure(text=text)
            self.after(100,self.poll_input_tenpai);return
        self.input_tenpai_button.configure(state='normal')
        self.input_tenpai_running=False
        self.close_input_tenpai_notice()
        if kind=='error':self.input_tenpai_status.configure(text=result);return
        self.input_tenpai_result=result
        for child in self.input_tenpai_body.winfo_children():child.destroy()
        preview=ttk.Frame(self.input_tenpai_body)
        ResponseList(self.input_tenpai_body,result['responses'],lambda response:self.show_response_preview(preview,tuple(result['board']),response)).pack(fill='x')
        preview.pack(anchor='w',pady=8)
        done=f'{result["completed_shanten"]}シャンテンまで完了' if result['completed_shanten']>=0 else '完了した深さなし'
        state='完了' if result['complete'] else ('中断・未完了' if result.get('stop_reason')=='cancelled' else '打ち切り・未完了')+f'（{done}）'
        self.input_tenpai_status.configure(text=f'{state}／{result["checked_boards"]:,}盤面／発火{len(result["responses"]):,}候補／{result["seconds"]:.2f}秒')
        self.update_analysis_status()

    def show_input_tenpai_notice(self):
        self.input_tenpai_notice_timer=None
        if not self.input_tenpai_running:return
        win=tk.Toplevel(self);self.input_tenpai_notice=win
        win.title('テンパイ探索中');win.transient(self);win.resizable(False,False)
        self.input_tenpai_notice_status=ttk.Label(win,text='探索を続けています。',padding=12)
        self.input_tenpai_notice_status.pack()
        self.input_tenpai_cancel_button=ttk.Button(win,text='中断',command=self.cancel_input_tenpai)
        self.input_tenpai_cancel_button.pack(padx=12,pady=(0,12),fill='x')
        win.protocol('WM_DELETE_WINDOW',self.cancel_input_tenpai)

    def cancel_input_tenpai(self):
        self.input_tenpai_cancel.set()
        self.input_tenpai_status.configure(text='中断処理中…')
        if self.input_tenpai_notice and self.input_tenpai_notice.winfo_exists():
            self.input_tenpai_notice_status.configure(text='中断処理中…')
            self.input_tenpai_cancel_button.configure(state='disabled')

    def close_input_tenpai_notice(self):
        if self.input_tenpai_notice_timer is not None:
            self.after_cancel(self.input_tenpai_notice_timer);self.input_tenpai_notice_timer=None
        if self.input_tenpai_notice and self.input_tenpai_notice.winfo_exists():self.input_tenpai_notice.destroy()
        self.input_tenpai_notice=None

    def render_tenpai_evaluation(self,parent,evaluation):
        ttk.Label(parent,text=f'テンパイ対応一覧：フィールド点 {evaluation["score"]:.4f}（試作）',font=('',10,'bold')).pack(anchor='w',pady=(10,3))
        ttk.Label(parent,text='4個消し・毎連鎖80Fを攻撃基準に使用。全消しボーナス・補充時間・仮想落下は評価に含めません。',wraplength=800).pack(anchor='w')
        holder=ttk.Frame(parent);holder.pack(fill='x',pady=4)
        columns=('attack','attack_score','response','chains','score','seconds','erased','power','time','use','total')
        table=ttk.Treeview(holder,columns=columns,show='headings',height=min(10,max(1,len(evaluation['attacks']))))
        for key,label,width in zip(columns,('攻撃連鎖','攻撃得点','対応の発火手','対応連鎖','対応得点','連鎖時間(秒)','消費色ぷよ','火力点','時間点','消費点','対応スコア'),(80,90,140,80,90,110,95,75,75,75,100)):
            table.heading(key,text=label);table.column(key,width=width,minwidth=width,stretch=False,anchor='center')
        table.pack(fill='x');scroll=ttk.Scrollbar(holder,orient='horizontal',command=table.xview);scroll.pack(fill='x');table.configure(xscrollcommand=scroll.set)
        for row in evaluation['attacks']:
            response=row['response']
            values=(row['attack_chains'],row['attack_score'])
            if response:values+=(f'{response["column"]}列：'+''.join(NAMES[c] for c in response['pieces']),response['chains'],response['score'],f'{response["frames"]/60:.3f}',response['erased'])
            else:values+=('対応なし','—','—','—','—')
            table.insert('','end',values=values+tuple(f'{row[key]:.4f}' for key in ('power','timing','consumption','score')))
        ttk.Button(parent,text='発火候補の全データを保存（評価式の調整用）',command=lambda:self.export_tenpai_data(evaluation)).pack(anchor='w',pady=4)

    def export_tenpai_data(self,evaluation):
        path=filedialog.asksaveasfilename(defaultextension='.json',filetypes=[('JSON','*.json')],initialfile='tenpai-evaluation.json')
        if path:
            try:Path(path).write_text(json.dumps(evaluation,ensure_ascii=False,indent=2),encoding='utf-8')
            except OSError as exc:messagebox.showerror('保存エラー',str(exc))

if __name__=='__main__':
    app=App()
    if '--load-review' in sys.argv:
        pos=sys.argv.index('--load-review')
        if pos+1<len(sys.argv):
            app.after(300,lambda p=sys.argv[pos+1]:app.load_saved_review(p))
    if '--review-session' in sys.argv:
        pos=sys.argv.index('--review-session')
        if pos+1<len(sys.argv):
            app.configure_review(sys.argv[pos+1])
    if '--image' in sys.argv:
        pos=sys.argv.index('--image')
        if pos+1<len(sys.argv):
            app.after(300,lambda:app.image_import(sys.argv[pos+1]))
    app.mainloop()
