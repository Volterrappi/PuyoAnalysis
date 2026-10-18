from pathlib import Path
import sys,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'puyo_tools'))
from common.engine import EMPTY,solve,Placement
from common.analysis import candidate_stats,detail_row
from common.result_columns import result_fields,export_row


class CandidateTimingTests(unittest.TestCase):
    def test_times_sum_and_disabled_does_not_evaluate(self):
        candidate=solve(EMPTY,('RB','GY','RP'),limit=1)[0]
        stats=candidate_stats(candidate,EMPTY)
        row=detail_row(candidate,stats,initial_board=EMPTY,row14_enabled=True)
        self.assertEqual(row['1手目設置時間(F)'],54)
        total=0
        for n in range(1,4):
            value=row[f'{n}手目設置時間(F)'];total+=value
            self.assertEqual(value,sum(row[f'{n}手目{field}時間(F)'] for field in ('移動','回し','ちぎり')))
        self.assertEqual(row['合計設置時間(F)'],total)
        with patch('common.placement_time.placement_time',side_effect=AssertionError('OFF')):
            off=detail_row(candidate,stats,initial_board=EMPTY,row14_enabled=False)
        self.assertIsNone(off['合計設置時間(F)'])
        self.assertIsNone(off['設置不可の手を含む'])
        self.assertFalse(row['設置不可の手を含む'])
        self.assertEqual(off['1手目効率'],row['1手目効率'])
        exported=export_row(row)
        self.assertEqual(list(exported),[label for _,label in result_fields()])
        self.assertFalse(any('消費' in title for title in exported))

    def test_placement_names_and_unreachable_indicator(self):
        self.assertEqual(str(Placement(0,'U')),'1縦・子上')
        self.assertEqual(str(Placement(0,'D')),'1縦・子下')
        self.assertEqual(str(Placement(2,'R')),'34・子右')
        self.assertEqual(str(Placement(3,'L')),'34・子左')
        board=tuple('.'+('G' if r%2 else 'B')+'....' for r in range(13))
        candidate=solve(board,('RP','GY','RB'),limit=1)[0]
        row=detail_row(candidate,candidate_stats(candidate,board),initial_board=board,row14_enabled=True)
        self.assertTrue(row['設置不可の手を含む'])
        headers=list(export_row(row))
        self.assertEqual(headers[headers.index('3手の置き方')+1],'設置不可の手を含む')

    def test_reachable_first_for_representatives_sort_and_red_rows(self):
        from app import App,ChainAnimation
        from dataclasses import replace
        app=App();app.withdraw()
        try:
            candidates=solve(EMPTY,('RB','GY','RP'),limit=2)
            app.results=candidates
            app.stats=[replace(candidate_stats(c,EMPTY),chigiri_total=i) for i,c in enumerate(candidates)]
            app.search_context={'board':EMPTY,'row14_enabled':True,'row14':'......'}
            original=app.row_for
            def row_for(i):
                row=original(i)
                row['1手目設置判定']='設置不可（試作）' if i==0 else '到達可能'
                return row
            app.row_for=row_for
            app.view.set('summary');app.show_results()
            self.assertEqual(app.visible,[1])
            app.view.set('detail');app.show_results()
            self.assertEqual(app.visible,[1,0])
            self.assertIn('unreachable',app.table.item('1','tags'))
            self.assertNotIn('unreachable',app.table.item('0','tags'))
            for descending in (False,True):
                app.custom_sort=('1手目設置時間(F)',descending);app.show_results()
                self.assertEqual(app.visible,[1,0])
            app.search_context['row14_enabled']=False
            app.view.set('summary');app.custom_sort=None;app.show_results()
            self.assertEqual(app.visible,[0])
            self.assertFalse(app.table.item('0','tags'))
        finally:
            def children(parent):
                for child in parent.winfo_children():yield child;yield from children(child)
            for w in list(children(app)):
                if isinstance(w,ChainAnimation):w.destroy()
            for event in app.tk.call('after','info'):app.after_cancel(event)
            app.destroy()

    def test_table_and_csv_columns_match_and_summary_has_no_timing(self):
        from app import App,ChainAnimation
        app=App();app.withdraw()
        try:
            candidate=solve(EMPTY,('RB','GY','RP'),limit=1)[0]
            app.results=[candidate];app.stats=[candidate_stats(candidate,EMPTY)]
            app.search_context={'board':EMPTY,'row14':'......','row14_enabled':True,'mawashi_frames':20}
            app.view.set('detail');app.show_results()
            columns=app.table['columns']
            titles=[app.table.heading(c,'text') for c in columns]
            csv_row=next(app.saved_candidate_rows())
            self.assertEqual(titles,list(csv_row))
            self.assertIn('1手目設置時間(F)',app.table['displaycolumns'])
            values=app.table.item('0','values')
            self.assertEqual(values[titles.index('1手目 設置時間(F)')],'54')
            app.sort_by_column('合計設置時間(F)')
            app.search_context['row14_enabled']=False;app.show_results()
            self.assertNotIn('1手目設置時間(F)',app.table['displaycolumns'])
            self.assertNotIn('設置不可の手を含む',app.table['displaycolumns'])
            self.assertIn('1手目 設置時間(F)',next(app.saved_candidate_rows()))
            app.view.set('summary');app.show_results()
            self.assertFalse(any('設置時間' in app.table.heading(c,'text') for c in app.table['columns']))
        finally:
            def children(parent):
                for child in parent.winfo_children():yield child;yield from children(child)
            for w in list(children(app)):
                if isinstance(w,ChainAnimation):w.destroy()
            for event in app.tk.call('after','info'):app.after_cancel(event)
            app.destroy()


if __name__=='__main__':unittest.main()
