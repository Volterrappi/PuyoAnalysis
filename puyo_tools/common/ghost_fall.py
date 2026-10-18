"""Unverified row-14 timing model; never modifies ordinary chain or efficiency."""


def validate_row14(row):
    if not isinstance(row,str) or len(row)!=6 or not set(row)<=set('.RBGYPO'):
        raise ValueError('14段目は6マスのぷよで指定してください')
    return row


def advance_row14(row, before, move):
    """Track an upward child overflowing the normal 13-row search board."""
    validate_row14(row)
    if move.direction=='U' and sum(line[move.col]!='.' for line in before)==12:
        cells=list(row);cells[move.col]='O';return ''.join(cells)
    return row


def ghost_steps(chain,row14='......'):
    """Per-step evidence for the unverified row-14 model."""
    validate_row14(row14)
    rows=[]
    for step in chain.steps:
        distances=tuple(next((i for i,line in enumerate(step.after) if line[col]!='.'),13)
                        if ch!='.' else 0 for col,ch in enumerate(row14))
        fall=max(step.fall,max(distances,default=0))
        modeled=55 if fall==0 else 78+2*fall
        rows.append(dict(index=step.index,normal_fall=step.fall,virtual_falls=distances,
                         effective_fall=fall,normal_frames=step.frames,
                         virtual_frames=modeled,extra_frames=modeled-step.frames))
    return rows


def ghost_frames(chain,row14='......'):
    validate_row14(row14)
    if row14=='......':return 0
    return sum(row['extra_frames'] for row in ghost_steps(chain,row14))
