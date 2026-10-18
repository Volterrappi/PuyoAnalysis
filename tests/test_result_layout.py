from pathlib import Path
import sys, unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'puyo_tools'))
from app import App, ChainAnimation
from common.engine import EMPTY,simulate,Turn,Candidate,Placement
from common.analysis import candidate_stats

def descendants(parent):
    for w in parent.winfo_children():yield w;yield from descendants(w)

class ResultLayoutTests(unittest.TestCase):
    def setUp(self):
        self.app=App()
        def cleanup():
            for w in list(descendants(self.app)):
                if isinstance(w,ChainAnimation):w.destroy()
            for event in self.app.tk.call('after','info'):self.app.after_cancel(event)
            self.app.destroy()
        self.addCleanup(cleanup)

    def test_chain_board_and_summary_are_outside_details_scroll(self):
        chain=simulate(EMPTY[:-1]+('RRRR..',))
        self.app.render_chain(chain);self.app.update()
        animation=next(w for w in self.app.chain_primary.winfo_children() if isinstance(w,ChainAnimation))
        self.assertIs(animation.static.master,animation)
        self.assertTrue(any(w.winfo_class()=='Treeview' for w in descendants(self.app.chain_details)))
        self.assertFalse(any(w.winfo_class()=='Treeview' for w in descendants(self.app.chain_overview)))
        self.assertIs(self.app.chain_overview.master,self.app.chain_body)
        self.assertLess(self.app.chain_overview.winfo_y(),self.app.chain_details.winfo_y())
        self.assertLessEqual(self.app.chain_summary.winfo_y()+self.app.chain_summary.winfo_height(),self.app.chain_overview.winfo_height())

    def test_search_board_and_stats_stay_fixed_above_detail_tables(self):
        app=self.app;board=EMPTY[:-1]+('RRRR..',);chain=simulate(board)
        first=Turn(Placement(0,'U'),board,chain,chain.score,False)
        idle=Turn(Placement(0,'U'),EMPTY,simulate(EMPTY),0,False)
        cand=Candidate((first,idle,idle),chain.score,chain.score,EMPTY)
        app.results=[cand];app.stats=[candidate_stats(cand,EMPTY)];app.search_context={'board':EMPTY,'next_pairs':('RB','GY','RP')}
        app.view.set('detail');app.tabs.select(app.tab2);app.show_results();app.update()
        animations=[w for w in descendants(app.detail_primary) if isinstance(w,ChainAnimation)]
        self.assertEqual(len(animations),1)
        self.assertIs(animations[0].static.master,animations[0])
        self.assertFalse(any(w.winfo_class()=='Treeview' for w in descendants(app.detail_primary)))
        self.assertTrue(any(w.winfo_class()=='Treeview' for w in descendants(app.detail)))
        self.assertTrue(any('3手合計' in str(w.cget('text')) for w in descendants(app.detail_primary) if 'text' in w.keys()))
        self.assertIs(app.detail_primary.master,app.detail_body)
        self.assertLess(app.detail_primary.winfo_y(),app.detail.winfo_y())
        self.assertLess(app.detail_primary.winfo_y()+app.detail_primary.winfo_height(),app.tab2.winfo_height())
        animations[0].toggle_static();app.update()
        self.assertEqual(animations[0].static.winfo_manager(),'pack')
        self.assertGreater(app.detail_canvas.bbox('all')[3],app.detail_canvas.winfo_height())
        app.detail_canvas.yview_moveto(1);app.update()
        self.assertGreater(app.detail_canvas.yview()[0],0)

    def test_tenpai_mode_uses_ignition_list_and_score_dialog(self):
        from common.engine import solve
        from tenpai_evaluation import evaluate_candidates
        app=self.app;board=EMPTY[:-3]+('B.....','BB....','RRR...')
        app.results=solve(board,('RB','GY','RP'),limit=12,tenpai_only=True)
        app.tenpai_evaluations=evaluate_candidates(app.results)
        app.stats=[candidate_stats(c,board) for c in app.results]
        app.search_context={'board':board,'next_pairs':('RB','GY','RP'),'tenpai_mode':True}
        app.view.set('detail');app.sort.set('最高発火得点');app.tabs.select(app.tab2)
        app.show_results();app.update()
        self.assertIn('ignition_score',app.table['columns'])
        self.assertNotIn('field_score',app.table['columns'])
        scores=[app.best_tenpai_response(i)['score'] for i in app.order]
        self.assertEqual(scores,sorted(scores,reverse=True))
        self.assertTrue(any('対応スコア・フィールド点を開く' in str(w.cget('text')) for w in descendants(app.detail) if 'text' in w.keys()))
        from tenpai_view import ResponseList
        self.assertTrue(any(isinstance(w,ResponseList) for w in descendants(app.detail)))
        self.assertIn('フィールド点',list(app.saved_candidate_rows())[0])
        app.view.set('summary');app.show_results();app.update()
        self.assertIn('ignition_score',app.table['columns'])

    def test_input_tenpai_tab_renders_completed_result_without_score_button(self):
        from tenpai_search import search
        from tenpai_view import ResponseList
        app=self.app;board=EMPTY[:-1]+('RR....',)
        app.input_tenpai_queue.put(('ok',search(board,1)))
        app.poll_input_tenpai();app.tabs.select(app.tab_tenpai);app.update()
        self.assertTrue(app.input_tenpai_result['complete'])
        self.assertIn('完了',app.input_tenpai_status.cget('text'))
        self.assertTrue(any(isinstance(w,ResponseList) for w in descendants(app.input_tenpai_body)))
        self.assertFalse(any('対応スコア' in str(w.cget('text')) for w in descendants(app.tab_tenpai) if 'text' in w.keys()))

    def test_long_search_notice_does_not_stop_until_user_cancels(self):
        from tenpai_search import search
        app=self.app;app.input_tenpai_running=True
        app.show_input_tenpai_notice();app.update()
        self.assertFalse(app.input_tenpai_cancel.is_set())
        self.assertTrue(app.input_tenpai_notice.winfo_exists())
        app.input_tenpai_cancel_button.invoke()
        self.assertTrue(app.input_tenpai_cancel.is_set())
        result=search(EMPTY,3,seconds_limit=None,state_limit=None,cancelled=app.input_tenpai_cancel.is_set)
        app.input_tenpai_queue.put(('ok',result));app.poll_input_tenpai()
        self.assertIsNone(app.input_tenpai_notice)
        self.assertIn('中断・未完了',app.input_tenpai_status.cget('text'))

    def test_release_has_single_tenpai_entry_and_added_cell_outlines(self):
        from tenpai_search import search
        from tkinter import ttk
        app=self.app
        texts=[str(w.cget('text')) for w in descendants(app) if 'text' in w.keys()]
        self.assertNotIn('テンパイ探索（試作）',texts)
        self.assertNotIn('3手後のテンパイ探索',texts)
        self.assertIn('テンパイ探索',[app.tabs.tab(tab,'text') for tab in app.tabs.tabs()])
        board=EMPTY[:-1]+('RR....',)
        response=next(r for r in search(board,1)['responses'] if len(r['pieces'])==1)
        preview=ttk.Frame(app.tab_tenpai);preview.pack()
        app.show_response_preview(preview,board,response);app.update()
        outlines=[len(w.find_withtag('added-puyo')) for w in descendants(preview) if w.winfo_class()=='Canvas']
        self.assertEqual(outlines[:3],[0,1,2])

if __name__=='__main__':unittest.main()
