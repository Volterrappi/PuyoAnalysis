"""Cached placement-time lookup shared by exhaustive candidate details."""
from functools import lru_cache
from .placement_proto import Timing,landings


@lru_cache(maxsize=2048)
def placement_times(board,row14,mawashi=20):
    # Pair colors do not affect reachability or timing; use fixed distinct colors.
    return tuple(landings((row14,)+tuple(board),'RP',Timing(mawashi=mawashi)))


def placement_time(board,row14,move,mawashi=20):
    direction={'U':0,'R':1,'D':2,'L':3}[move.direction]
    return next(r for r in placement_times(tuple(board),row14,mawashi)
                if r.column==move.col and r.direction==direction)
