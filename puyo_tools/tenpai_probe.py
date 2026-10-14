"""Experimental single-column ignition probe.

This is NOT a next-3-pairs solver. It tests one freely chosen color, or one
nuisance puyo under a freely chosen color, dropped vertically into one column.
It does not model input sequence, nuisance arrival, or multi-column patterns.
"""
from common.engine import W, H, COLORS, simulate

def probe(board, include_nuisance=True):
    if len(board) != H or any(len(row) != W for row in board):
        raise ValueError("盤面は13行×6列です")
    if simulate(board).count:
        raise ValueError("すでに発火する盤面です。発火前の盤面を入力してください")
    results=[]
    for col in range(W):
        for color in COLORS:
            for base in ("", "O") if include_nuisance else ("",):
                pieces = base + color
                grid=[list(row) for row in board]
                empty=[row for row in range(H-1,-1,-1) if grid[row][col]=="."]
                if len(empty) < len(pieces):
                    continue
                for row,ch in zip(empty,pieces):
                    grid[row][col]=ch
                placed=tuple("".join(row) for row in grid)
                chain=simulate(placed)
                if chain.count:
                    results.append({"column":col+1,"pieces":pieces,
                                    "chains":chain.count,"score":chain.score,
                                    "frames":chain.frames,
                                    "after":chain.final})
    results.sort(key=lambda x:(-x["chains"],-x["score"],x["column"],x["pieces"]))
    return results
