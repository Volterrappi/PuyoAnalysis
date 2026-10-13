"""Shared crop memory, local only."""
import json
from pathlib import Path
CROP_DB=Path.home()/"PuyoReview"/"board_crops.json"
def crop_key(source_type,source,image_size):
    return json.dumps([source_type,source,list(image_size)],ensure_ascii=False)
def load_crops(path=CROP_DB):
    if not path.exists():return {}
    data=json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data,dict) else {}
def save_crop(key,crop,rows,path=CROP_DB):
    data=load_crops(path)
    data[key]={"crop":list(crop),"rows":int(rows)}
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    tmp.replace(path)


def player_crops(record):
    """Read new dual-slot format and old single-slot saved crops."""
    if not isinstance(record,dict):return {}
    if isinstance(record.get('players'),dict):return record['players']
    return {'1P':{'crop':record['crop'],'rows':record.get('rows',12)}} if 'crop' in record else {}

def save_player_crop(key,player,crop,rows,path=CROP_DB):
    if player not in ('1P','2P'):raise ValueError('Unknown player')
    data=load_crops(path)
    old=data.get(key,{})
    slots=player_crops(old).copy()
    slots[player]={'crop':list(crop),'rows':int(rows)}
    data[key]={'players':slots}
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    tmp.replace(path)
