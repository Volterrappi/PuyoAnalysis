"""Raw ignition data and replaceable scoring policy. No Tk dependencies."""
from dataclasses import dataclass,asdict
from common import engine as e
from tenpai_probe import probe

@dataclass(frozen=True)
class ScoringPolicy:
    version:str='linear-product-v1'
    power_full_ratio:float=2.0
    time_full_extra:int=1
    time_zero_extra:int=4
    consumption_full_extra:int=5
    consumption_zero_ratio:float=2.0

def clamp(value):return max(0.0,min(1.0,value))

def attack_score(chains):
    return sum(40*max(1,e.CHAIN_BONUS[k]) for k in range(1,chains+1))

def collect_responses(board):
    """Only the final ignition may add a nuisance puyo. Keep all alternatives."""
    result=[]
    before=e.count(board,e.COLORS)
    for option in probe(board,include_nuisance=True):
        result.append(dict(column=option['column'],pieces=option['pieces'],chains=option['chains'],
                           score=option['score'],frames=option['frames'],
                           erased=before+1-e.count(option['after'],e.COLORS)))
    return result

def score_response(response,k,policy=ScoringPolicy()):
    power=clamp((response['score']/attack_score(k)-1)/(policy.power_full_ratio-1))
    # Four-clear reference: one-cell fall on every link, 80F per link.
    full_time=80*(k+policy.time_full_extra);zero_time=80*(k+policy.time_zero_extra)
    timing=clamp((zero_time-response['frames'])/(zero_time-full_time))
    full_count=4*k+policy.consumption_full_extra;zero_count=4*k*policy.consumption_zero_ratio
    consumption=clamp((zero_count-response['erased'])/(zero_count-full_count))
    return dict(power=power,timing=timing,consumption=consumption,score=power*timing*consumption)

def evaluate(board,responses,policy=ScoringPolicy()):
    rows=[]
    for k in range(2,min(19,e.count(board,e.COLORS)//4)+1):
        best=None;components=dict(power=0.0,timing=0.0,consumption=0.0,score=0.0)
        for response in responses:
            trial=score_response(response,k,policy)
            if best is None or (trial['score'],trial['power'],trial['timing'],trial['consumption'])>(components['score'],components['power'],components['timing'],components['consumption']):
                best=response;components=trial
        rows.append(dict(attack_chains=k,attack_score=attack_score(k),attack_frames=80*k,
                         attack_erased=4*k,response=best,**components))
    return dict(board=list(board),score=sum(row['score'] for row in rows),attacks=rows,policy=asdict(policy),
                responses=responses)

def evaluate_candidates(candidates,progress=None):
    """Deduplicate exact final boards, preserving raw data for rescoring."""
    boards=dict.fromkeys(candidate.final for candidate in candidates)
    total=len(boards)
    for n,board in enumerate(boards,1):
        boards[board]=evaluate(board,collect_responses(board))
        if progress and (n%500==0 or n==total):progress(n,total)
    return [boards[candidate.final] for candidate in candidates]
