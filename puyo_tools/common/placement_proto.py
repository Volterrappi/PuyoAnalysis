"""Explicitly provisional 14-row reachability and timing sandbox.

No automatic gravity while input is held, lock reset, DAS or game-specific
rotation table is emulated. Weights and the row-14 ghost-fall hypothesis are
parameters, not measured Puyo eSports timings. Existing solve() is unchanged.
"""
from dataclasses import dataclass
from heapq import heappush, heappop
from itertools import count as serial
from .engine import COLORS, Step, Chain, CHAIN_BONUS, COLOR_BONUS, _group_bonus

WIDTH, HEIGHT = 6, 14
OFFSETS = ((-1,0),(0,1),(1,0),(0,-1))  # child U,R,D,L
EMPTY14 = tuple('......' for _ in range(HEIGHT))

@dataclass(frozen=True)
class Timing:
    horizontal: int = 2
    rotation: int = 0
    drop_per_cell: int = 2
    lock: int = 16
    chigiri_per_cell: int = 2
    mawashi: int = 20
    wall_kicks: bool = True
    quick_turn: bool = True
    virtual_fall: int = 0

    def __post_init__(self):
        for name in ('horizontal','rotation','drop_per_cell','lock','chigiri_per_cell','mawashi','virtual_fall'):
            value=getattr(self,name)
            if type(value) is not int or value<0:raise ValueError('時間・仮想落下段数は0以上の整数です')

def validate(board):
    if len(board)!=HEIGHT or any(len(row)!=WIDTH or not set(row)<=set('.'+COLORS+'O') for row in board):
        raise ValueError('盤面は14段×6列で指定してください')
    return tuple(board)

def cells(state):
    row,col,direction=state;dy,dx=OFFSETS[direction]
    return (row,col),(row+dy,col+dx)

def free(board,state):
    # The axis cannot enter row14, including during rotations/quick turns.
    return state[0]>=1 and all(0<=row<HEIGHT and 0<=col<WIDTH and board[row][col]=='.' for row,col in cells(state))

def neighbors(board,state,timing):
    row,col,d=state
    for dx,label in ((-1,'左'),(1,'右')):
        target=(row,col+dx,d)
        if free(board,target):yield target,label,timing.horizontal,'move'
    target=(row+1,col,d)
    if free(board,target):yield target,'落下',timing.drop_per_cell,'drop'
    for delta,label in ((1,'右回転'),(-1,'左回転')):
        # Simple test policy: plain rotation, then opposite-child wall kick,
        # then one-cell floor kick. Not a claim of the game's kick priorities.
        nd=(d+delta)%4
        shifts=[(0,0)]
        if timing.wall_kicks:
            shifts += [(0,-OFFSETS[nd][1])] if OFFSETS[nd][1] else []
            if nd==2 and (row+1>=HEIGHT or board[row+1][col]!='.'):
                shifts += [(-1,0)]
        for dy,dx in shifts:
            target=(row+dy,col+dx,nd)
            if free(board,target):
                yield target,label+('（補正）' if dy or dx else ''),timing.rotation,'rotation'
                break
    # A separate, optional narrow-column quick-turn hypothesis.
    if timing.quick_turn and d in (0,2):
        blocked=lambda dx: col+dx<0 or col+dx>=WIDTH or board[row][col+dx]!='.'
        if blocked(-1) and blocked(1):
            target=(row+OFFSETS[d][0],col,(d+2)%4)
            if free(board,target):yield target,'クイックターン（仮）',timing.rotation*2,'rotation'

@dataclass(frozen=True)
class Landing:
    column: int
    direction: int
    reachable: bool
    reason: str
    placed: tuple | None = None
    route: tuple = ()
    move_frames: int = 0
    rotation_frames: int = 0
    drop_frames: int = 0
    chigiri_frames: int = 0
    lock_frames: int = 0
    chigiri_cells: int = 0
    needs_mawashi: bool = False
    mawashi_frames: int = 0

    timing_note: str = ""

    @property
    def frames(self):
        if self.timing_note:return None
        return self.move_frames+self.rotation_frames+self.drop_frames+self.chigiri_frames+self.lock_frames+self.mawashi_frames

def _settle_pair(board,pair,state):
    positions=list(cells(state));g=[list(row) for row in board];distances=[0,0]
    for index in sorted(range(2),key=lambda i:positions[i][0],reverse=True):
        row,col=positions[index]
        while row+1<HEIGHT and g[row+1][col]=='.':row+=1;distances[index]+=1
        g[row][col]=pair[index]
    return tuple(''.join(row) for row in g),max(distances)

def direct_without_mawashi(board,placed):
    """User-confirmed sufficient corridor rule, not a complete reachability test.

    Row12 is clear from the cross to both landing columns. Horizontal pairs
    finish at/below row12; vertical pairs may extend to row13. Ordinary turns,
    including orientation changes at contact, are not counted as mawashi.
    """
    added=[(r,c) for r in range(HEIGHT) for c in range(WIDTH)
           if board[r][c]=='.' and placed[r][c]!='.']
    if len(added)!=2:return False
    cols=[c for _,c in added]
    if not all(board[2][c]=='.' for c in range(min(2,*cols),max(2,*cols)+1)):return False
    return min(r for r,_ in added)>=(1 if cols[0]==cols[1] else 2)

def landings(board,pair,timing=Timing()):
    board=validate(board)
    if len(pair)!=2 or not set(pair)<=set(COLORS):raise ValueError('軸→子の通常色2個を指定してください')
    spawn=(2,2,0)  # axis row12 (the cross), child row13, column3
    best={};terminal={};queue=[];order=serial()
    if free(board,spawn):
        best[(spawn,False)]=(0,(),0,0,0)
        heappush(queue,(False,0,next(order),spawn))
    while queue:
        needs_mawashi,cost,_,state=heappop(queue)
        if best[(state,needs_mawashi)][0]!=cost:continue
        _,route,moves,rotations,drops=best[(state,needs_mawashi)]
        row,col,d=state
        if not free(board,(row+1,col,d)):
            placed,separation=_settle_pair(board,pair,state)
            chigiri=separation if d in (1,3) else 0
            special=needs_mawashi and not direct_without_mawashi(board,placed)
            # Axis position at first contact, before the separated piece falls.
            # Source: Ratty, puyo-camp/posts/71019. Position table includes
            # ordinary travel/rotation/locking; do not add route weights again.
            base_frames=(54,52,50,52,54,56)[col]-2*(13-row)
            note=''
            if row==1:base_frames=(54,52,50,52,54,56)[col]-20
            # Upper-board splitting correction intentionally omitted.
            chigiri_table=(0,19,24,28,31,34,37,40,42,44,46,48,50)
            if chigiri>=len(chigiri_table):raise ValueError('ちぎり段数が範囲外です')
            chigiri_cost=chigiri_table[chigiri] if chigiri<len(chigiri_table) else 0
            result=Landing(col,d,True,'到達可能（試作モデル）',placed,route,base_frames,0,0,
                           chigiri_cost,0,chigiri,special,
                           timing.mawashi if special else 0,note)
            key=(col,d)
            if key not in terminal or (result.needs_mawashi,result.frames if result.frames is not None else float('inf'))<(terminal[key].needs_mawashi,terminal[key].frames if terminal[key].frames is not None else float('inf')):terminal[key]=result
        for target,label,weight,kind in neighbors(board,state,timing):
            next_mawashi=needs_mawashi or target[0]<state[0]
            total=cost+weight
            key=(target,next_mawashi)
            if key not in best or total<best[key][0]:
                best[key]=(total,route+(label,),moves+(weight if kind=='move' else 0),
                              rotations+(weight if kind=='rotation' else 0),drops+(weight if kind=='drop' else 0))
                heappush(queue,(next_mawashi,total,next(order),target))
    result=[]
    for col in range(WIDTH):
        for d in range(4):
            if not 0<=col+OFFSETS[d][1]<WIDTH:continue
            if (col,d) in terminal:result.append(terminal[col,d]);continue
            geometric=any(free(board,(row,col,d)) for row in range(HEIGHT))
            reason=('出現位置が塞がれています' if not free(board,spawn) else
                    '組ぷよが入る空間なし' if not geometric else '操作経路なし（試作モデル）')
            result.append(Landing(col,d,False,reason))
    return result

def placement_animation(board,pair,landing,timing=Timing()):
    """Replay the exact prototype route, slowly; delays are presentation only."""
    if not landing.reachable:return []
    state=(2,2,0)
    frames=[]
    def picture(positions):
        grid=[list(row) for row in board]
        for (row,col),color in zip(positions,pair):grid[row][col]=color
        return tuple(''.join(row) for row in grid)
    frames.append((picture(cells(state)),'出現',350))
    for label in landing.route:
        state=next(target for target,name,*_ in neighbors(board,state,timing) if name==label)
        frames.append((picture(cells(state)),label,150 if label=='落下' else 280))
    positions=list(cells(state))
    while True:
        moved=False
        for i in sorted(range(2),key=lambda i:positions[i][0],reverse=True):
            row,col=positions[i];target=(row+1,col)
            if row+1<HEIGHT and board[row+1][col]=='.' and target!=positions[1-i]:
                positions[i]=target;moved=True
        if not moved:break
        frames.append((picture(positions),'ちぎり落下',150))
    frames.append((landing.placed,'設置完了',700))
    return frames


def simulate14(board,virtual_fall=0):
    """Clear rows1..12, drop row13, keep row14 fixed as an obstacle.

    Hypothesis: if row14 was occupied before a clear, give that step a minimum
    fall distance of virtual_fall. Zero disables it. Conditions are unverified.
    Returns normal Chain plus per-step natural/virtual timing evidence.
    """
    validate(board)
    if type(virtual_fall) is not int or virtual_fall<0:raise ValueError('仮想落下段数が不正です')
    g=[list(row) for row in board];steps=[];evidence=[];total=erased_total=trash_total=frames=0
    while True:
        groups=[];seen=set()
        for y in range(2,HEIGHT):
            for x in range(WIDTH):
                color=g[y][x]
                if color not in COLORS or (y,x) in seen:continue
                stack=[(y,x)];seen.add((y,x));group=[]
                while stack:
                    yy,xx=stack.pop();group.append((yy,xx))
                    for ny,nx in ((yy-1,xx),(yy+1,xx),(yy,xx-1),(yy,xx+1)):
                        if 2<=ny<HEIGHT and 0<=nx<WIDTH and (ny,nx) not in seen and g[ny][nx]==color:
                            seen.add((ny,nx));stack.append((ny,nx))
                if len(group)>=4:groups.append((color,group))
        if not groups:break
        index=len(steps)+1;before=tuple(''.join(row) for row in g)
        ghost=virtual_fall if any(ch!='.' for ch in before[0]) else 0
        erased={cell for _,group in groups for cell in group};trash=set()
        for y,x in erased:
            for ny,nx in ((y-1,x),(y+1,x),(y,x-1),(y,x+1)):
                if 1<=ny<HEIGHT and 0<=nx<WIDTH and g[ny][nx]=='O':trash.add((ny,nx))
        colors=len({color for color,_ in groups})
        bonus=max(1,CHAIN_BONUS[min(index,len(CHAIN_BONUS)-1)]+COLOR_BONUS[colors]+sum(_group_bonus(len(group)) for _,group in groups))
        score=10*len(erased)*bonus
        for y,x in erased|trash:g[y][x]='.'
        fall=0
        for x in range(WIDTH):
            target=HEIGHT-1
            for y in range(HEIGHT-1,0,-1):
                if g[y][x]!='.':
                    fall=max(fall,target-y);g[target][x]=g[y][x]
                    if y!=target:g[y][x]='.'
                    target-=1
        effective=max(fall,ghost)
        natural_frames=55 if fall==0 else 78+2*fall
        duration=55 if effective==0 else 78+2*effective
        after=tuple(''.join(row) for row in g)
        steps.append(Step(index,tuple(sorted(erased)),tuple(sorted(trash)),tuple((c,len(a)) for c,a in groups),score,effective,duration,before,after))
        evidence.append({'natural_fall':fall,'virtual_fall':ghost,'extra_frames':duration-natural_frames})
        total+=score;erased_total+=len(erased);trash_total+=len(trash);frames+=duration
    return Chain(tuple(steps),tuple(''.join(row) for row in g),total,erased_total,trash_total,frames),evidence
