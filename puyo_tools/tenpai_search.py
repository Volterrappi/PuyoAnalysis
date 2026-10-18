"""Bounded preparation search. Colored preparation; nuisance only on ignition."""
import time
from common import engine as e
from tenpai_evaluation import collect_responses

def add_color(board,column,color):
    row=next((r for r in range(e.H-1,-1,-1) if board[r][column]=='.'),None)
    if row is None:return None
    changed=list(board);line=list(changed[row]);line[column]=color;changed[row]=''.join(line)
    return tuple(changed)

def search(board,max_shanten=1,*,seconds_limit=20,state_limit=30000,progress=None,cancelled=None):
    if max_shanten not in range(4):raise ValueError('シャンテン数は0〜3')
    if e.simulate(board).count:raise ValueError('すでに発火する盤面です。発火前の盤面を入力してください。')
    if e.dead(board):raise ValueError('開始盤面が窒息しています。')
    start=time.perf_counter();frontier={board:()};seen={board};responses=[];checked=0;completed=-1
    def report(complete,stop_reason=None):
        return dict(board=list(board),responses=responses,complete=complete,requested_shanten=max_shanten,
                    completed_shanten=completed,checked_boards=checked,seconds=time.perf_counter()-start,stop_reason=stop_reason)
    for depth in range(max_shanten+1):
        following={}
        for current,path in frontier.items():
            if cancelled and cancelled():return report(False,'cancelled')
            if state_limit is not None and checked>=state_limit:return report(False,'state_limit')
            if seconds_limit is not None and time.perf_counter()-start>=seconds_limit:return report(False,'time_limit')
            for response in collect_responses(current):
                responses.append(dict(response,shanten=depth,preparation=[list(step) for step in path],ready_board=list(current)))
            checked+=1
            if progress and checked%100==0:progress(depth,checked)
            if depth==max_shanten:continue
            for col in range(e.W):
                for color in e.COLORS:
                    if cancelled and cancelled():return report(False,'cancelled')
                    placed=add_color(current,col,color)
                    if placed is None or placed in seen:continue
                    seen.add(placed)
                    if state_limit is not None and len(seen)>state_limit:return report(False,'state_limit')
                    if e.dead(placed) or e.simulate(placed).count:continue
                    following[placed]=path+((col+1,color),)
        completed=depth;frontier=following
        if not frontier:break
    return report(True)

def group_responses(responses):
    groups={}
    for response in responses:groups.setdefault(response['score'],[]).append(response)
    return [(score,items,min(items,key=lambda r:(r.get('shanten',0),r['frames'],r['erased'])))
            for score,items in sorted(groups.items(),reverse=True)]
