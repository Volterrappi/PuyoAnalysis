"""Standalone deterministic Puyo simulation. Rows top to bottom, row 0 hidden."""
from dataclasses import dataclass
from functools import lru_cache

W,H=6,13
COLORS='RBGYP'
CHARS='.'+COLORS
VALID=set('.RBGYPO')
Board=tuple[str,...]
EMPTY=tuple('.'*W for _ in range(H))
CHAIN_BONUS=(0,0,8,16,32,64,96,128,160,192,224,256,288,320,352,384,416,448,480,512)
COLOR_BONUS=(0,0,3,6,12,24)

def parse_board(s:str)->Board:
    lines=tuple(x.strip().upper() for x in s.splitlines() if x.strip())
    if len(lines)!=H or any(len(x)!=W or not set(x)<=VALID for x in lines):
        raise ValueError('盤面は上から13行×6文字（. R B G Y P O）で入力してください')
    # Normalize user-entered boards: settle every column before calculation.
    # Keep each column's relative top-to-bottom order, including nuisance puyos.
    columns=[]
    for c in range(W):
        pieces=[lines[r][c] for r in range(H) if lines[r][c]!='.']
        columns.append(['.']*(H-len(pieces))+pieces)
    return tuple(''.join(columns[c][r] for c in range(W)) for r in range(H))

def count(board,chars):return sum(ch in chars for row in board for ch in row)
def all_clear(board):return count(board,'RBGYPO')==0

def _groups(g):
    visited=set();groups=[]
    for r in range(1,H):
        for c in range(W):
            color=g[r][c]
            if color not in COLORS or (r,c) in visited:continue
            stack=[(r,c)];visited.add((r,c));group=[]
            while stack:
                y,x=stack.pop();group.append((y,x))
                for ny,nx in ((y-1,x),(y+1,x),(y,x-1),(y,x+1)):
                    if 1<=ny<H and 0<=nx<W and (ny,nx) not in visited and g[ny][nx]==color:
                        visited.add((ny,nx));stack.append((ny,nx))
            if len(group)>=4:groups.append((color,tuple(group)))
    return groups

def _group_bonus(n):
    if n <= 4: return 0
    if n >= 11: return 10
    return n - 3

@dataclass(frozen=True)
class Step:
    index:int
    erased:tuple
    erased_ojama:tuple
    groups:tuple
    score:int
    fall:int
    frames:int
    before:Board
    after:Board

@dataclass(frozen=True)
class Chain:
    steps:tuple[Step,...]
    final:Board
    score:int
    erased:int
    ojama:int
    frames:int
    @property
    def count(self):return len(self.steps)

@lru_cache(maxsize=50000)
def simulate(board:Board)->Chain:
    g=[list(x) for x in board];steps=[];total=0;removed=0;ojama=0;frames=0
    for idx in range(1,40):
        groups=_groups(g)
        if not groups:break
        before=tuple(''.join(row) for row in g)
        erased={cell for _,cells in groups for cell in cells}
        trash=set()
        for y,x in erased:
            for ny,nx in ((y-1,x),(y+1,x),(y,x-1),(y,x+1)):
                if 0<=ny<H and 0<=nx<W and g[ny][nx]=='O':trash.add((ny,nx))
        color_count=len({color for color,_ in groups})
        bonus=max(1,(CHAIN_BONUS[idx] if idx<len(CHAIN_BONUS) else 512)+sum(_group_bonus(len(cells)) for _,cells in groups)+COLOR_BONUS[color_count])
        score=10*len(erased)*bonus
        for y,x in erased|trash:g[y][x]='.'
        fall=0
        for x in range(W):
            target=H-1
            for y in range(H-1,-1,-1):
                if g[y][x]!='.':
                    fall=max(fall,target-y)
                    g[target][x]=g[y][x]
                    if target!=y:g[y][x]='.'
                    target-=1
        duration=55 if fall==0 else 78+2*fall
        after=tuple(''.join(row) for row in g)
        steps.append(Step(idx,tuple(sorted(erased)),tuple(sorted(trash)),tuple((col,len(cells)) for col,cells in groups),score,fall,duration,before,after))
        total+=score;removed+=len(erased);ojama+=len(trash);frames+=duration
    return Chain(tuple(steps),tuple(''.join(row) for row in g),total,removed,ojama,frames)

def consumption_frames(remaining_colors:int,remaining_ojama:int,erased_colors:int)->float:
    values=(remaining_colors,remaining_ojama,erased_colors)
    if any(type(v)!=int or v<0 for v in values):raise ValueError('ぷよ数は非負整数')
    r=remaining_colors+remaining_ojama;n=erased_colors
    return n*(27-r/6-n/12)

def efficiency(chain:Chain,include_future_all_clear=False):
    remaining_colors=count(chain.final,COLORS);remaining_ojama=count(chain.final,'O')
    consume=consumption_frames(remaining_colors,remaining_ojama,chain.erased)
    time=(chain.frames+consume)/60
    score=chain.score+(2100 if include_future_all_clear and chain.count and all_clear(chain.final) else 0)
    return (score/time if time>0 else 0.0),time,consume/60

@dataclass(frozen=True)
class Placement:
    col:int
    direction:str
    def __str__(self):
        axis=self.col+1
        if self.direction in ('U','D'):position=f'{axis}縦'
        else:
            other=axis+(-1 if self.direction=='L' else 1)
            position=f'{min(axis,other)}{max(axis,other)}'
        return f'{position}・子{dict(U="上",D="下",L="左",R="右")[self.direction]}'

def moves(pair):
    same=pair[0]==pair[1]
    for c in range(W):
        yield Placement(c,'U')
        if not same:yield Placement(c,'D')
        if c<W-1:yield Placement(c,'R')
        if c>0 and not same:yield Placement(c,'L')

def place(board:Board,pair:str,move:Placement):
    c=move.col;d=move.direction
    if not 0<=c<W:return None
    def landing(x):
        for y in range(H-1,-1,-1):
            if board[y][x]=='.':return y
        return -1
    g=[list(row) for row in board];y=landing(c)
    if y<0:return None
    if d in 'UD':
        if y==0 and d=='U':
            # Tsu-style 14th row: axis fits on the 13th row, while the
            # child rests in the off-screen 14th row. We deliberately keep
            # this potential placement as the solver is an overapproximation.
            # The 14th-row child is not tracked in the 13-row board model.
            g[0][c]=pair[0]
        elif y<1:
            return None
        else:
            g[y][c],g[y-1][c]=(pair[0],pair[1]) if d=='U' else (pair[1],pair[0])
    else:
        other=c+(-1 if d=='L' else 1)
        if not 0<=other<W:return None
        yy=landing(other)
        if yy<0:return None
        g[y][c]=pair[0];g[yy][other]=pair[1]
    return tuple(''.join(row) for row in g)

def dead(board):return board[1][2]!='.'

@dataclass(frozen=True)
class Turn:
    move:Placement
    placed:Board
    chain:Chain
    points:int
    used_bonus:bool

@dataclass(frozen=True)
class Candidate:
    turns:tuple[Turn,...]
    total:int
    max_fire:int
    final:Board


def solve(board:Board,pairs:tuple[str,...],initial_bonus=False,limit=None,*,tenpai_only=False):
    """Enumerate potential 3-move paths; reachability is intentionally permissive.

    A child in row 14 is omitted from the 13-row state, so follow-up turns,
    all-clear status, and nuisance/scoring around that child are approximate.
    """
    if len(pairs)!=3 or any(len(p)!=2 or not set(p)<=set(COLORS) for p in pairs):raise ValueError('ネクストは通常色2個×3組')
    if dead(board):raise ValueError('開始盤面が窒息しています')
    results=[]
    def dfs(current,depth,held,turns,total,max_fire):
        if depth==3:
            results.append(Candidate(tuple(turns),total,max_fire,current));return
        for move in moves(pairs[depth]):
            placed=place(current,pairs[depth],move)
            if placed is None:continue
            chain=simulate(placed)
            if tenpai_only and (chain.count>1 or sum(bool(t.chain.count) for t in turns)+bool(chain.count)>1):continue
            if dead(chain.final):continue
            used=held and chain.count>0
            points=chain.score+(2100 if used else 0)
            next_held=(held and not used) or all_clear(chain.final)
            dfs(chain.final,depth+1,next_held,turns+[Turn(move,placed,chain,points,used)],total+points,max(max_fire,points))
            if limit is not None and len(results)>=limit:return
    dfs(board,0,initial_bonus,[],0,0)
    return results
