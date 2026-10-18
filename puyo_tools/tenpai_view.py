"""Shared ignition list for the input field and next-three final fields."""
import tkinter as tk
from tkinter import ttk
from tenpai_search import group_responses

class ResponseList(ttk.Frame):
    def __init__(self,parent,responses,on_select=None):
        super().__init__(parent)
        self.responses=responses;self.on_select=on_select;self.visible=[]
        self.grouped=tk.BooleanVar(value=True)
        ttk.Checkbutton(self,text='同じ発火得点をまとめる',variable=self.grouped,command=self.refresh).pack(anchor='w')
        columns=('score','count','shanten','chains','seconds','erased','preparation','ignition')
        self.table=ttk.Treeview(self,columns=columns,show='headings',height=7)
        labels=('発火得点','発火候補数','シャンテン','連鎖数','連鎖時間(秒)','消費色ぷよ','準備（列・色）','発火（列・下→上）')
        for key,label,width in zip(columns,labels,(100,90,90,75,110,95,240,160)):
            self.table.heading(key,text=label);self.table.column(key,width=width,minwidth=width,stretch=False)
        y=ttk.Scrollbar(self,orient='vertical',command=self.table.yview);y.pack(side='right',fill='y')
        x=ttk.Scrollbar(self,orient='horizontal',command=self.table.xview);x.pack(side='bottom',fill='x')
        self.table.configure(yscrollcommand=y.set,xscrollcommand=x.set);self.table.pack(fill='both',expand=True)
        self.table.bind('<<TreeviewSelect>>',self.selected);self.refresh()

    def refresh(self):
        self.table.delete(*self.table.get_children());self.visible=[]
        groups=group_responses(self.responses) if self.grouped.get() else [(r['score'],[r],r) for r in sorted(self.responses,key=lambda r:(-r['score'],r.get('shanten',0),r['frames']))]
        # Grouped is the default. Large raw lists are paged to keep Tk responsive.
        self.groups=groups;self.page=getattr(self,'page',0)
        if not hasattr(self,'pager'):
            self.pager=ttk.Frame(self);self.pager.pack(side='bottom',fill='x')
            ttk.Button(self.pager,text='前へ',command=lambda:self.change_page(-1)).pack(side='left')
            self.page_label=ttk.Label(self.pager);self.page_label.pack(side='left',padx=8)
            ttk.Button(self.pager,text='次へ',command=lambda:self.change_page(1)).pack(side='left')
        self.page=min(self.page,max(0,(len(groups)-1)//250))
        names={'R':'赤','B':'青','G':'緑','Y':'黄','P':'紫','O':'おじゃま'}
        for score,items,r in groups[self.page*250:(self.page+1)*250]:
            prep=' → '.join(f'{col}列・{names[color]}' for col,color in r.get('preparation',[])) or 'なし'
            values=(f'{score:,}',len(items),r.get('shanten',0),r['chains'],f'{r["frames"]/60:.3f}',r['erased'],prep,f'{r["column"]}列・'+''.join(names[c] for c in r['pieces']))
            self.table.insert('','end',iid=str(len(self.visible)),values=values);self.visible.append(r)
        self.page_label.configure(text=f'{self.page+1}/{max(1,(len(groups)+249)//250)} ページ・{len(groups):,}行')
        if self.visible:self.table.selection_set('0');self.selected()

    def change_page(self,delta):
        self.page=max(0,min(self.page+delta,max(0,(len(self.groups)-1)//250)));self.refresh()

    def selected(self,event=None):
        chosen=self.table.selection()
        if chosen and self.on_select:self.on_select(self.visible[int(chosen[0])])
