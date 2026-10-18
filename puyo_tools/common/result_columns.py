"""One ordered set of labels for detailed results, filters and CSV exports."""


def result_fields():
    fields=[('合計得点','合計得点'),('実獲得合計得点','獲得得点'),
            ('最大連鎖数','最大連鎖数'),('1手の最高得点','1手の最高得点'),
            ('1手の最高連鎖効率','最高連鎖効率(点/秒)'),
            ('合計設置時間(F)','3手合計設置時間(F)'),('合計設置時間(秒)','3手合計設置時間(秒)'),
            ('合計ちぎり回数','ちぎり回数'),('全消し回数','全消し回数'),
            ('合計消した色ぷよ数','色ぷよ消去数'),('合計連鎖数','合計連鎖数'),
            ('3手の置き方','3手の置き方'),('設置不可の手を含む','設置不可の手を含む')]
    for n in range(1,4):
        for name,label in [('配置','配置'),('得点','得点'),('連鎖数','連鎖数'),
                           ('設置判定','設置判定'),('設置時間(F)','設置時間(F)'),('設置時間(秒)','設置時間(秒)'),
                           ('移動時間(F)','移動時間(F)'),('回し','回し'),('回し時間(F)','回し時間(F)'),
                           ('ちぎり','ちぎり'),('ちぎり段数','ちぎり段数'),('ちぎり時間(F)','ちぎり時間(F)'),
                           ('連鎖時間(秒)','連鎖時間(秒)'),('仮想落下分(F)','仮想落下分(F)'),
                           ('仮想落下分(秒)','仮想落下分(秒)'),('補充時間(秒)','補充時間(秒)'),
                           ('合計時間(秒)','連鎖＋補充時間(秒)'),('効率','連鎖効率(点/秒)'),
                           ('消した色ぷよ数','色ぷよ消去数'),('全消し','全消し'),('全消しボーナス使用','全消しボーナス使用')]:
            fields.append((f'{n}手目{name}',f'{n}手目 {label}'))
    fields.extend([('連鎖得点','連鎖得点'),('使用全消しボーナス点','使用全消しボーナス点'),
                   ('未使用の全消しボーナス点','未使用全消しボーナス点'),
                   ('全消しボーナス使用回数','全消しボーナス使用回数'),('最終全消し','最終全消し'),
                   ('14段目使用','14段目使用'),('回し追加設定(F)','回し追加設定(F)')])
    return fields


def export_row(row):
    # Old duplicate aliases remain available internally for existing filters.
    aliases={'評価合計得点'}|{f'{n}手目消費ぷよ数' for n in range(1,4)}|{f'{n}手目消費時間(秒)' for n in range(1,4)}
    result={label:row[key] for key,label in result_fields() if key in row}
    known={key for key,_ in result_fields()}
    result.update({k:v for k,v in row.items() if k not in known and k not in aliases})
    return result


def visible_result_fields(row14_enabled):
    if row14_enabled:return result_fields()
    hidden=('設置','移動時間','回し','ちぎり段数','ちぎり時間','仮想落下')
    return [(key,label) for key,label in result_fields()
            if key!='14段目使用' and not any(word in key for word in hidden)]
