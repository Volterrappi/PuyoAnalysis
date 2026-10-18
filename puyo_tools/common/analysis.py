"""Candidate analytics, independent of the graphical interface."""
from dataclasses import dataclass
from .engine import COLORS, all_clear, count, consumption_frames


def is_chigiri(before, move):
    """Whether a horizontal pair lands at different column heights."""
    if move.direction not in ('L', 'R'):
        return False
    c1 = move.col
    c2 = c1 + (-1 if move.direction == 'L' else 1)
    return sum(row[c1] != '.' for row in before) != sum(row[c2] != '.' for row in before)


def turn_efficiency(turn, mode="earned", include_future=None):
    """Return points/sec, or None if this turn did not fire a chain."""
    if include_future is not None:  # legacy boolean arguments
        mode = 'earned' if include_future else ('used' if mode else 'none')
    elif isinstance(mode, bool):
        mode = 'used' if mode else 'none'
    chain = turn.chain
    if not chain.count:
        return None
    remain = count(chain.final, COLORS) + count(chain.final, 'O')
    frames = chain.frames + consumption_frames(count(chain.final, COLORS), count(chain.final, 'O'), chain.erased)
    if frames <= 0:
        return None
    score = chain.score + (2100 if mode=='used' and turn.used_bonus else 0) + (2100 if mode=='earned' and all_clear(chain.final) else 0)
    return score * 60 / frames


@dataclass(frozen=True)
class CandidateStats:
    raw_total: int
    bonus_total: int
    total: int
    max_fire: int
    max_chain: int
    chain_sum: int
    erased: int
    chigiri: tuple
    chigiri_total: int
    clear: tuple
    clear_count: int
    bonus_awards: tuple
    bonus_count: int
    efficiencies_raw: tuple
    efficiencies_bonus: tuple
    final_clear: bool
    pending_bonus: bool


def candidate_stats(candidate, initial_board, initial_bonus=False):
    prev = initial_board
    chigiri = []
    clears = []
    used = []
    eff_raw = []
    eff_bonus = []
    held = bool(initial_bonus)
    for turn in candidate.turns:
        chigiri.append(int(is_chigiri(prev, turn.move)))
        clears.append(int(turn.chain.count > 0 and all_clear(turn.chain.final)))
        used.append(int(turn.used_bonus))
        eff_raw.append(turn_efficiency(turn, False, False))
        eff_bonus.append(turn_efficiency(turn, True, True))
        held = (held and not turn.used_bonus) or (turn.chain.count > 0 and all_clear(turn.chain.final))
        prev = turn.chain.final
    raw = sum(t.chain.score for t in candidate.turns)
    bonus = 2100 * sum(used)
    return CandidateStats(
        raw, bonus, raw + bonus, max(t.points for t in candidate.turns),
        max(t.chain.count for t in candidate.turns),
        sum(t.chain.count for t in candidate.turns),
        sum(t.chain.erased for t in candidate.turns),
        tuple(chigiri), sum(chigiri), tuple(clears), sum(clears),
        tuple(used), sum(used), tuple(eff_raw), tuple(eff_bonus),
        all_clear(candidate.final), held,
    )


def group_by_score(candidates, stats, include_pending=False):
    """Return score groups sorted by descending score, with a representative.

    Representative: fewest chigiri, then most all-clears, then earliest path.
    """
    groups = {}
    for i, stat in enumerate(stats):
        key = stat.total + (2100 if include_pending and stat.pending_bonus else 0)
        groups.setdefault(key, []).append(i)
    return [(score, indices, min(indices, key=lambda i: (stats[i].chigiri_total, -stats[i].clear_count, i)))
            for score, indices in sorted(groups.items(), reverse=True)]


def response_priority(candidate, stat, max_chain, efficiency_mode='used'):
    """Rank eligible response paths; None excludes no-fire/over-limit paths.

    Minimize firing turns, maximize the best firing turn's existing efficiency,
    minimize chigiri, maximize all-clears. Caller breaks exact ties by path index.
    """
    if max_chain < 1:
        raise ValueError('連鎖数の上限は1以上で指定してください')
    firing = [turn for turn in candidate.turns if turn.chain.count > 0]
    if not firing or any(turn.chain.count > max_chain for turn in firing):
        return None
    best_efficiency = max((turn_efficiency(turn, efficiency_mode) or 0) for turn in firing)
    return (len(firing), -best_efficiency, stat.chigiri_total, -stat.clear_count)


def detail_row(candidate, stat, include_pending=False, efficiency_mode='used', include_future_eff=None, row14='......', initial_board=None, row14_enabled=True, mawashi_frames=20):
    if include_future_eff is not None:
        efficiency_mode = 'earned' if include_future_eff else ('used' if efficiency_mode else 'none')
    from .ghost_fall import ghost_frames, advance_row14
    from .placement_time import placement_time
    hidden=row14
    placement_totals=[]
    previous=initial_board
    eff = tuple(turn_efficiency(t, efficiency_mode) for t in candidate.turns)
    row = {
        '合計得点': stat.total + (2100 if include_pending and stat.pending_bonus else 0),
        '実獲得合計得点': stat.total,
        '未使用の全消しボーナス点': 2100 if stat.pending_bonus else 0,
        '評価合計得点': stat.total + (2100 if include_pending and stat.pending_bonus else 0),
        '連鎖得点': stat.raw_total,
        '使用全消しボーナス点': stat.bonus_total,
        '1手の最高得点': max(t.points for t in candidate.turns),
        '最大連鎖数': stat.max_chain,
        '合計連鎖数': stat.chain_sum,
        '合計消した色ぷよ数': stat.erased,
        '合計ちぎり回数': stat.chigiri_total,
        '全消し回数': stat.clear_count,
        '全消しボーナス使用回数': stat.bonus_count,
        '最終全消し': stat.final_clear,
        '14段目使用': bool(row14_enabled),
    }
    for j, turn in enumerate(candidate.turns):
        n = j + 1
        placement=placement_time(previous,hidden,turn.move,mawashi_frames) if row14_enabled and previous is not None else None
        duration=placement.frames if placement is not None and placement.reachable else None
        placement_totals.append(duration)
        row[f'{n}手目設置判定']=('到達可能' if placement.reachable else '設置不可（試作）') if placement is not None else None
        row[f'{n}手目設置時間(F)']=duration
        row[f'{n}手目設置時間(秒)']=duration/60 if duration is not None else None
        row[f'{n}手目移動時間(F)']=placement.move_frames if duration is not None else None
        row[f'{n}手目回し']=placement.needs_mawashi if placement is not None and placement.reachable else None
        row[f'{n}手目回し時間(F)']=placement.mawashi_frames if duration is not None else None
        row[f'{n}手目ちぎり段数']=placement.chigiri_cells if placement is not None and placement.reachable else None
        row[f'{n}手目ちぎり時間(F)']=placement.chigiri_frames if duration is not None else None
        if row14_enabled and previous is not None:hidden=advance_row14(hidden,previous,turn.move)
        delta=ghost_frames(turn.chain,hidden) if row14_enabled else None
        row[f'{n}手目仮想落下分(F)']=delta
        row[f'{n}手目仮想落下分(秒)']=delta/60 if delta is not None else None
        previous=turn.chain.final
        row[f'{n}手目配置'] = str(turn.move)
        row[f'{n}手目得点'] = turn.points
        row[f'{n}手目連鎖数'] = turn.chain.count
        row[f'{n}手目消した色ぷよ数'] = turn.chain.erased
        # Keep the old CSV field for compatibility with existing exports.
        row[f'{n}手目消費ぷよ数'] = turn.chain.erased
        row[f'{n}手目連鎖時間(秒)'] = turn.chain.frames / 60 if turn.chain.count else None
        if turn.chain.count:
            remaining_colors = count(turn.chain.final, COLORS)
            remaining_ojama = count(turn.chain.final, 'O')
            consumed_frames = consumption_frames(remaining_colors, remaining_ojama, turn.chain.erased)
            row[f'{n}手目補充時間(秒)'] = consumed_frames / 60
            row[f'{n}手目合計時間(秒)'] = (turn.chain.frames + consumed_frames) / 60
        else:
            row[f'{n}手目補充時間(秒)'] = None
            row[f'{n}手目合計時間(秒)'] = None
        row[f'{n}手目効率'] = eff[j]
        row[f'{n}手目全消し'] = bool(stat.clear[j])
        row[f'{n}手目全消しボーナス使用'] = bool(stat.bonus_awards[j])
        row[f'{n}手目ちぎり'] = bool(stat.chigiri[j])
    total=sum(placement_totals) if all(v is not None for v in placement_totals) else None
    row['設置不可の手を含む']=any(row[f'{n}手目設置判定']=='設置不可（試作）' for n in range(1,4)) if row14_enabled and initial_board is not None else None
    row['合計設置時間(F)']=total
    row['合計設置時間(秒)']=total/60 if total is not None else None
    row['回し追加設定(F)']=mawashi_frames if row14_enabled else None
    row['1手の最高連鎖効率'] = max((x for x in eff if x is not None), default=None)
    # Legacy CSV field; new UI uses 補充時間.
    for n in range(1,4):
        row[f'{n}手目消費時間(秒)'] = row[f'{n}手目補充時間(秒)']
    row['3手の置き方'] = ' / '.join(str(t.move) for t in candidate.turns)
    return row


def matches_filters(row, conditions):
    """conditions: iterable of (column, operator, value)."""
    for key, op, raw in conditions:
        if not key or not raw.strip():
            continue
        val = row.get(key)
        if val is None:
            return False
        if isinstance(val, bool):
            actual = int(val)
            wanted = {'あり': 1, 'なし': 0, 'true': 1, 'false': 0, '1': 1, '0': 0}.get(raw.strip().lower())
            if wanted is None:
                return False
        elif isinstance(val, (int, float)):
            actual = val
            try:
                wanted = float(raw.replace(',', ''))
            except ValueError:
                return False
        else:
            actual = str(val)
            wanted = raw
        if op == '含む':
            valid = str(wanted).lower() in str(actual).lower()
        elif op == '=':
            valid = actual == wanted
        elif op == '!=':
            valid = actual != wanted
        elif op == '>=':
            valid = actual >= wanted
        elif op == '<=':
            valid = actual <= wanted
        elif op == '>':
            valid = actual > wanted
        elif op == '<':
            valid = actual < wanted
        else:
            valid = False
        if not valid:
            return False
    return True
