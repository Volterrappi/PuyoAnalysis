from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'puyo_tools'))
from common.engine import EMPTY,simulate,Placement,Turn,Candidate
from common.ghost_fall import ghost_frames,ghost_steps,advance_row14
from common.analysis import candidate_stats,detail_row


class GhostFallTests(unittest.TestCase):
    def test_empty_markers_do_not_change_chain(self):
        chain=simulate(EMPTY[:-1]+('RRRR..',))
        self.assertEqual(ghost_frames(chain),0)
        self.assertEqual(chain.frames,55)
        self.assertEqual(ghost_frames(chain,'O.....'),49)
        self.assertEqual(chain.frames,55)

    def test_support_height_and_multiple_columns(self):
        chain=simulate(EMPTY[:-2]+('B.....','RRRR..'))
        self.assertEqual(ghost_frames(chain,'O.....'),22)
        self.assertEqual(ghost_frames(chain,'O....O'),24)
        self.assertEqual(ghost_frames(chain,'......'),0)

    def test_no_chain_has_zero_difference(self):
        self.assertEqual(ghost_frames(simulate(EMPTY),'O.....'),0)

    def test_search_csv_uses_passed_snapshot(self):
        board=EMPTY[:-1]+('RRRR..',);chain=simulate(board)
        turn=Turn(Placement(0,'U'),board,chain,chain.score,False)
        idle=Turn(Placement(0,'U'),EMPTY,simulate(EMPTY),0,False)
        candidate=Candidate((turn,idle,idle),chain.score,chain.score,EMPTY)
        stats=candidate_stats(candidate,board)
        row=detail_row(candidate,stats,row14='O.....',initial_board=board)
        self.assertEqual(row['1手目仮想落下分(F)'],49)
        self.assertEqual(row['1手目仮想落下分(秒)'],49/60)
        self.assertEqual(row['2手目仮想落下分(F)'],0)

    def test_off_skips_calculation_even_after_overflow(self):
        from unittest.mock import patch
        board=EMPTY[:-1]+('RRRR..',);chain=simulate(board)
        turn=Turn(Placement(0,'U'),board,chain,chain.score,False)
        candidate=Candidate((turn,turn,turn),chain.score*3,chain.score,chain.final)
        with patch('common.ghost_fall.ghost_frames',side_effect=AssertionError('must not calculate')):
            row=detail_row(candidate,candidate_stats(candidate,board),row14='O.....',initial_board=board,row14_enabled=False)
        self.assertFalse(row['14段目使用'])
        self.assertIsNone(row['1手目仮想落下分(F)'])

    def test_evidence_totals_match_stats(self):
        chain=simulate(EMPTY[:-2]+('B.....','RRRR..'))
        rows=ghost_steps(chain,'O....O')
        self.assertEqual(sum(r['extra_frames'] for r in rows),ghost_frames(chain,'O....O'))
        self.assertEqual(rows[0]['virtual_falls'],(12,0,0,0,0,13))
        self.assertEqual(rows[0]['virtual_frames'],104)

    def test_search_child_row14_is_retained(self):
        before=('......',)+('R.....',)*12
        self.assertEqual(advance_row14('......',before,Placement(0,'U')),'O.....')


class GhostToolboxTests(unittest.TestCase):
    def test_switch_and_breakdown_reload(self):
        from app import App
        app=App();app.withdraw()
        try:
            self.assertFalse(app.row14_enabled.get())
            self.assertFalse(app.hidden_line.winfo_manager())
            app.row14='O.....';app.cells=[list(r) for r in EMPTY[:-1]+('RRRR..',)]
            app.row14_enabled.set(True);app.toggle_row14()
            self.assertEqual(app.hidden_line.winfo_manager(),'pack')
            app.open_placement_lab();app.update_idletasks()
            window=next(w for w in app.winfo_children() if w.winfo_class()=='Toplevel')
            self.assertEqual(window.title(),'未検証ツールボックス')
            def children(w):
                for child in w.winfo_children():yield child;yield from children(child)
            table=next(w for w in children(window) if w.winfo_name()=='ghost_steps')
            values=table.item(table.get_children()[0],'values')
            self.assertEqual(tuple(map(int,values[-3:])),(55,104,49))
            app.row14_enabled.set(False);app.toggle_row14()
            reload=next(w for w in children(table.master.master) if w.winfo_class()=='TButton' and w.cget('text')=='入力盤面から更新')
            reload.invoke()
            self.assertEqual(table.item(table.get_children()[0],'values')[-1],'—')
            self.assertFalse(app.hidden_line.winfo_manager())
        finally:
            for window in list(app.winfo_children()):
                if window.winfo_class()=='Toplevel':window.destroy()
            for event in app.tk.call('after','info'):app.after_cancel(event)
            app.destroy()


if __name__=='__main__':unittest.main()
