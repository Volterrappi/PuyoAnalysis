"""GUI laboratory for provisional placement and row-14 timing models."""
import tkinter as tk
from tkinter import ttk, messagebox
from common.engine import parse_board, simulate, Placement
from common.ghost_fall import ghost_steps, ghost_frames
from common.placement_proto import Timing, landings, placement_animation

def open_lab(app):
    window=tk.Toplevel(app);window.title('未検証ツールボックス');window.geometry('1250x790')
    tabs=ttk.Notebook(window);tabs.pack(fill='both',expand=True)
    lab=ttk.Frame(tabs);ghost=ttk.Frame(tabs)
    tabs.add(lab,text='設置・回し検証');tabs.add(ghost,text='仮想落下の計算過程')
    build_ghost_tab(ghost,app)
    base=[parse_board('\n'.join(app.snapshot_board()))]
    top=tk.StringVar(value=getattr(app,'row14','......'));pair=tk.StringVar(value=app.pairs_var.get().split()[0] if app.pairs_var.get().split() else 'RB')
    bar=ttk.Frame(lab,padding=8);bar.pack(fill='x')
    ttk.Label(bar,text='14段目（左から6文字）：').pack(side='left')
    ttk.Entry(bar,textvariable=top,width=10,state='readonly').pack(side='left')
    ttk.Label(bar,text='組ぷよ（軸→子）：').pack(side='left',padx=(12,0))
    ttk.Entry(bar,textvariable=pair,width=5).pack(side='left')
    def reload_board():
        try:
            base[0]=parse_board('\n'.join(app.snapshot_board()))
            top.set(app.row14)
            pair.set(app.pairs_var.get().split()[0] if app.pairs_var.get().split() else 'RB')
            calculate(silent=True)
        except ValueError as exc:messagebox.showerror('盤面',str(exc),parent=window)
    ttk.Button(bar,text='入力盤面から更新',command=reload_board).pack(side='left',padx=12)
    params=ttk.Frame(lab,padding=(8,0));params.pack(fill='x')
    fields={}
    for key,label,default in [('mawashi','回し追加F',20)]:
        ttk.Label(params,text=label).pack(side='left',padx=(6,2))
        var=app.mawashi_frames;fields[key]=var
        ttk.Entry(params,textvariable=var,width=4).pack(side='left')
    ttk.Label(lab,text='設置表の基本時間＋回し追加＋段差別ちぎり時間。13段目は11段目相当・12段差は50F・上部ちぎり補正未反映。到達判定は試作。設置時間は連鎖効率に加算しません。',foreground='#a34c00',wraplength=1180).pack(anchor='w',padx=10)
    ttk.Label(lab,text='仮想落下は隣のタブで、入力盤面の各連鎖の計算過程を確認できます（未検証）。',wraplength=1180).pack(anchor='w',padx=10)
    body=ttk.Frame(lab,padding=8);body.pack(fill='both',expand=True)
    left=ttk.Frame(body);left.pack(side='left',fill='both',expand=True)
    columns=('move','mawashi','chigiri','base','spin','split','time')
    table=ttk.Treeview(left,columns=columns,show='headings',height=18,selectmode='browse')
    for key,label,width in [('move','配置',85),('mawashi','回し',50),('chigiri','ちぎり段数',70),('base','移動F',65),('spin','回しF',65),('split','ちぎりF',65),('time','設置F',85)]:
        table.heading(key,text=label);table.column(key,width=width,minwidth=45)
    table.pack(fill='both',expand=True)
    right=ttk.Frame(body);right.pack(side='right',fill='both',padx=(12,0))
    pictures=ttk.Frame(right);pictures.pack(anchor='n')
    boards=[]
    for title in ('元盤面','配置後','設置アニメーション'):
        frame=ttk.Frame(pictures);frame.pack(side='left',padx=3)
        ttk.Label(frame,text=title).pack()
        canvas=tk.Canvas(frame,width=150,height=310,bg='#202634',highlightthickness=0)
        canvas.pack();boards.append(canvas)
    detail=ttk.Label(right,text='',wraplength=460,justify='left');detail.pack(anchor='w',pady=10)
    route=ttk.Label(right,text='',wraplength=460,justify='left');route.pack(anchor='w')
    palette={'.':'#202634','R':'#e94f58','B':'#438be5','G':'#4fc475','Y':'#f6d451','P':'#ba73e6','O':'#999fa9'}
    def draw(canvas,board):
        canvas.delete('all')
        if board is None:return
        for row,line in enumerate(board):
            canvas.create_text(12,10+row*21,text=str(14-row),fill='#ffa77d' if row<2 else '#bac3ca')
            for col,ch in enumerate(line):
                x=24+col*21;y=row*21
                canvas.create_rectangle(x,y,x+21,y+21,fill='#292f3e',outline='#465063')
                if ch!='.':canvas.create_oval(x+2,y+2,x+19,y+19,fill=palette[ch],outline='#ffffff')
        canvas.create_line(24,42,150,42,fill='#ff9b72',width=2)
    rows=[];source=[None];timing=[Timing()]
    job=[None];playback=[];phase=[0];paused=[False]
    animation_status=ttk.Label(right,text='経路をゆっくり再生',foreground='#66717c',name='placement_animation_status');animation_status.pack(anchor='w')
    def stop_animation():
        if job[0] is not None:
            window.after_cancel(job[0]);job[0]=None
    def tick(schedule=True):
        job[0]=None
        if phase[0]>=len(playback):return
        board,label,delay=playback[phase[0]];phase[0]+=1
        draw(boards[2],board);animation_status.configure(text=f'{phase[0]}/{len(playback)}：{label}')
        if schedule and not paused[0] and phase[0]<len(playback):job[0]=window.after(delay,tick)
    def replay():
        stop_animation();phase[0]=0;paused[0]=False;pause_button.configure(text='一時停止')
        if playback:tick()
    def pause():
        if not playback:return
        paused[0]=not paused[0];pause_button.configure(text='再開' if paused[0] else '一時停止')
        if paused[0]:stop_animation()
        elif phase[0]<len(playback):tick()
    def step():
        if not playback:return
        stop_animation();paused[0]=True;pause_button.configure(text='再開');tick(schedule=False)
    controls=ttk.Frame(right);controls.pack(anchor='w',pady=4)
    ttk.Button(controls,text='もう一度再生',command=replay).pack(side='left')
    pause_button=ttk.Button(controls,text='一時停止',command=pause);pause_button.pack(side='left',padx=4)
    ttk.Button(controls,text='1コマ進む',command=step).pack(side='left')
    def select(*_):
        selected=table.selection()
        if not selected:return
        stop_animation();playback.clear()
        landing=rows[int(selected[0])]
        draw(boards[0],source[0]);draw(boards[1],landing.placed);draw(boards[2],None)
        if not landing.reachable:
            detail.configure(text=landing.reason);route.configure(text='');animation_status.configure(text='到達経路なし');return
        detail.configure(text=(f'設置：{landing.frames}F（{landing.frames/60:.3f}秒）\n'
             f'移動（設置表）：{landing.move_frames}F / 回し：{landing.mawashi_frames}F / ちぎり：{landing.chigiri_frames}F\n'
             f'回し：'+('有' if landing.needs_mawashi else '無')+f' / ちぎり：{landing.chigiri_cells}段\n'
             f'配置後14段目：{landing.placed[0]}'))
        playback.extend(placement_animation(source[0],pair.get().strip().upper(),landing,timing[0]))
        replay()
        route.configure(text='経路：'+(' → '.join(landing.route) or '出現位置で接地'))
    def calculate(silent=False):
        stop_animation();playback.clear();animation_status.configure(text='')
        rows.clear();table.delete(*table.get_children());detail.configure(text='');route.configure(text='')
        for canvas in boards:draw(canvas,None)
        try:
            timing[0]=Timing(**{key:int(var.get()) for key,var in fields.items()},wall_kicks=True,quick_turn=True)
            source[0]=((top.get().strip().upper() if app.row14_enabled.get() else '......'),)+base[0]
            rows.extend(landings(source[0],pair.get().strip().upper(),timing[0]))
            for i,landing in enumerate(rows):
                label=str(Placement(landing.column,('U','R','D','L')[landing.direction]))
                table.insert('','end',iid=str(i),values=(label,('有' if landing.needs_mawashi else '無') if landing.reachable else '設置不可',
                         landing.chigiri_cells if landing.reachable else '—',landing.move_frames if landing.reachable else '—',
                         landing.mawashi_frames if landing.reachable else '—',
                         (landing.chigiri_frames if not landing.timing_note else '未確定') if landing.reachable else '—',
                         (landing.frames if landing.frames is not None else '未確定') if landing.reachable else '—'))
            selected=next((str(i) for i,row in enumerate(rows) if row.reachable),'0')
            if rows:table.selection_set(selected);select()
        except (ValueError,TypeError) as exc:
            if silent:detail.configure(text=str(exc))
            else:messagebox.showerror('検証入力',str(exc),parent=window)
    table.bind('<<TreeviewSelect>>',select)
    traces=[(var,var.trace_add('write',lambda *_:calculate(silent=True))) for var in (pair,*fields.values())]
    def cleanup(event):
        if event.widget is window:
            stop_animation()
            for var,trace in traces:var.trace_remove('write',trace)
    window.bind('<Destroy>',cleanup,add='+')
    calculate(silent=True)
    return window


def build_ghost_tab(parent,app):
    bar=ttk.Frame(parent,padding=8);bar.pack(fill='x')
    status=ttk.Label(parent,text='',foreground='#66717c');status.pack(anchor='w',padx=10)
    ttk.Label(parent,text='未検証：14段目のぷよが各列へ落下したと仮定。通常時間は変更しません。',foreground='#77818b').pack(anchor='w',padx=10,pady=4)
    area=ttk.Frame(parent,padding=8);area.pack(fill='both',expand=True)
    columns=('index','normal_fall','virtual_falls','effective_fall','normal_frames','virtual_frames','extra_frames')
    table=ttk.Treeview(area,columns=columns,show='headings',height=15,name='ghost_steps')
    for key,label,width in zip(columns,('連鎖','通常落差','14段目からの落差（1〜6列）','採用落差','通常(F)','仮想込み(F)','差分(F)'),(60,85,230,85,110,110,100)):
        table.heading(key,text=label);table.column(key,width=width,anchor='center')
    scroll=ttk.Scrollbar(area,orient='vertical',command=table.yview);table.configure(yscrollcommand=scroll.set)
    scroll.pack(side='right',fill='y');table.pack(fill='both',expand=True)
    total=ttk.Label(parent,text='',padding=10,name='ghost_total');total.pack(anchor='w')
    def reload():
        try:
            board=parse_board('\n'.join(app.snapshot_board()))
            chain=simulate(board);enabled=app.row14_enabled.get();hidden=app.row14
            table.delete(*table.get_children())
            status.configure(text=f'入力盤面を読込：{chain.count}連鎖 / 14段目 '+('ON：'+hidden if enabled else 'OFF（仮想落下は計算しません）'))
            rows=ghost_steps(chain,hidden) if enabled else [dict(index=s.index,normal_fall=s.fall,normal_frames=s.frames) for s in chain.steps]
            for row in rows:
                values=[row.get(key,'—') for key in columns]
                if enabled:values[2]=' / '.join(str(n) if hidden[c]!='.' else '—' for c,n in enumerate(row['virtual_falls']))
                table.insert('','end',values=values)
            if enabled:
                extra=sum(r['extra_frames'] for r in rows);modeled=chain.frames+extra
                total.configure(text=f'合計：通常 {chain.frames}F ({chain.frames/60:.3f}秒) / 仮想込み {modeled}F ({modeled/60:.3f}秒) / 仮想落下分 {extra}F ({extra/60:.3f}秒)')
            else:total.configure(text=f'合計：通常 {chain.frames}F ({chain.frames/60:.3f}秒) / 仮想落下 OFF')
        except ValueError as exc:messagebox.showerror('盤面入力',str(exc),parent=parent.winfo_toplevel())
    ttk.Button(bar,text='入力盤面から更新',command=reload).pack(side='left')
    reload()
