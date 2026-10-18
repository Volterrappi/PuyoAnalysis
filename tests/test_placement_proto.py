from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'puyo_tools'))
from common.engine import EMPTY, simulate, count
from common.placement_proto import EMPTY14, Timing, landings, neighbors, simulate14, placement_animation
from app import App

def board_with_column(col,height):
    g=[list(row) for row in EMPTY14]
    for i in range(height):g[13-i][col]='GB'[i%2]
    return tuple(''.join(row) for row in g)

def high_mawashi_board():
    g=[list(''.join('GB'[(r+c)%2] if r>=3 else '.' for c in range(6))) for r in range(14)]
    g[2][0]='R'
    return tuple(''.join(row) for row in g)

class PlacementPrototypeTests(unittest.TestCase):
    def test_empty_board_all_22_geometric_placements_reachable_and_conserve_pair(self):
        rows=landings(EMPTY14,'RB')
        self.assertEqual(len(rows),22)
        self.assertTrue(all(row.reachable for row in rows))
        for row in rows:
            self.assertEqual(count(row.placed,'R'),1);self.assertEqual(count(row.placed,'B'),1)
            self.assertEqual(row.frames,row.move_frames+row.rotation_frames+row.drop_frames+row.chigiri_frames+row.lock_frames+row.mawashi_frames)
        self.assertEqual(next(row for row in rows if row.column==2 and row.direction==0).rotation_frames,0)

    def test_row14_piece_is_not_discarded_and_horizontal_separation_has_cost(self):
        board=high_mawashi_board()
        row=next(row for row in landings(board,'RP') if row.column==0 and row.direction==0)
        self.assertTrue(row.reachable)
        self.assertEqual(row.placed[0][0],'P')
        self.assertEqual(count(row.placed,'R'),count(board,'R')+1)
        self.assertEqual(count(row.placed,'P'),1)
        row=next(row for row in landings(board_with_column(0,4),'RP') if row.column==0 and row.direction==1)
        self.assertTrue(row.reachable)
        self.assertEqual(row.chigiri_cells,4)
        self.assertEqual(row.chigiri_frames,31)

    def test_source_table_and_split_cost_without_double_counting(self):
        for col,expected in enumerate((54,52,50,52,54,56)):
            row=next(r for r in landings(EMPTY14,'RP') if r.column==col and r.direction==0)
            self.assertEqual(row.frames,expected)
            self.assertEqual(row.rotation_frames+row.drop_frames+row.lock_frames,0)
        row=next(r for r in landings(board_with_column(0,4),'RP') if r.column==0 and r.direction==1)
        self.assertEqual(row.frames,46+31)

    def test_top_row_and_maximum_split_have_numeric_duration(self):
        for row in landings(high_mawashi_board(),'RP'):
            if row.reachable:self.assertIsInstance(row.frames,int)
        board=tuple(''.join(a if a!='.' else b for a,b in zip(x,y)) for x,y in zip(board_with_column(0,12),board_with_column(2,11)))
        row=next(r for r in landings(board,'RP') if r.column==0 and r.direction==1)
        self.assertTrue(row.reachable)
        self.assertEqual(row.chigiri_cells,12)
        self.assertEqual(row.chigiri_frames,50)
        self.assertEqual(row.move_frames,34)
        self.assertEqual(row.frames,row.move_frames+row.mawashi_frames+50)

    def test_animation_replays_route_and_finishes_at_actual_placement(self):
        for board in (EMPTY14,board_with_column(0,4),high_mawashi_board()):
            for landing in landings(board,'RP'):
                frames=placement_animation(board,'RP',landing)
                if not landing.reachable:
                    self.assertEqual(frames,[]);continue
                self.assertEqual(frames[-2][0],landing.placed)
                self.assertEqual(frames[-1][0],landing.placed)
                for picture,_,_ in frames:
                    self.assertEqual(count(picture,'RGBYPO'),count(board,'RGBYPO')+2)

    def test_full_height_wall_makes_otherwise_empty_column_unreachable(self):
        board=board_with_column(1,14)
        row=next(row for row in landings(board,'RP') if row.column==0 and row.direction==0)
        self.assertFalse(row.reachable)
        self.assertIn('経路なし',row.reason)

    def test_spawn_blocked_and_no_space_have_separate_reasons(self):
        board=board_with_column(2,13)
        self.assertTrue(all('出現位置' in row.reason for row in landings(board,'RB')))
        board=board_with_column(0,14)
        row=next(row for row in landings(board,'RP') if row.column==0 and row.direction==0)
        self.assertIn('空間なし',row.reason)

    def test_optional_quick_turn_and_parameters(self):
        g=[list(row) for row in EMPTY14];g[2][1]=g[2][3]='O';board=tuple(''.join(row) for row in g)
        rows=list(neighbors(board,(2,2,0),Timing(wall_kicks=False)))
        self.assertTrue(any(state==(1,2,2) and 'クイック' in label for state,label,*_ in rows))
        self.assertFalse(any('クイック' in label for _,label,*_ in neighbors(board,(2,2,0),Timing(wall_kicks=False,quick_turn=False))))
        with self.assertRaises(ValueError):Timing(lock=-1)
        with self.assertRaises(ValueError):landings(EMPTY14,'..')

    def test_normal_chain_matches_existing_simulation_when_row14_empty(self):
        for board in (EMPTY,EMPTY[:-1]+('RRRR..',),EMPTY[:-2]+('B.....','RRRRB.')):
            old=simulate(board);new,evidence=simulate14(('......',)+board)
            self.assertEqual((new.score,new.frames,new.count),(old.score,old.frames,old.count))
            self.assertEqual(new.final[1:],old.final)
            self.assertTrue(all(e['extra_frames']==0 for e in evidence))

    def test_virtual_fall_is_explicit_hypothesis_and_not_enabled_by_default(self):
        g=[list(row) for row in board_with_column(5,14)]
        g[13][:4]=list('RRRR');board=tuple(''.join(row) for row in g)
        normal,_=simulate14(board)
        virtual,evidence=simulate14(board,1)
        self.assertEqual(normal.frames,55)
        self.assertEqual(virtual.frames,80)
        self.assertEqual(evidence[0],{'natural_fall':0,'virtual_fall':1,'extra_frames':25})
        self.assertEqual(normal.final,virtual.final)
        self.assertEqual(normal.score,virtual.score)

    def test_row14_stays_fixed_after_clear_and_prevents_false_all_clear(self):
        g=[list(row) for row in board_with_column(0,14)]
        g[13][:4]=list('RRRR');board=tuple(''.join(row) for row in g)
        chain,evidence=simulate14(board)
        self.assertGreater(count(chain.final,'GB'),0)
        self.assertEqual(chain.final[0],board[0])
        self.assertEqual(evidence[0]['natural_fall'],1)
        self.assertEqual(count(chain.final,'RGBPO'),count(board,'RGBPO')-chain.erased-chain.ojama)

    def test_height11_corridor_needs_no_mawashi_and_axis_never_enters_row14(self):
        import random
        rng=random.Random(17)
        for heights in [[h]*6 for h in range(12)]+[[rng.randrange(12) for _ in range(6)] for _ in range(50)]:
            board=tuple(''.join('GB'[(r+c)%2] if r>=14-heights[c] else '.' for c in range(6)) for r in range(14))
            rows=landings(board,'RP')
            self.assertTrue(all(row.reachable and not row.needs_mawashi for row in rows),heights)
        rows=landings(high_mawashi_board(),'RP')
        up=next(r for r in rows if r.column==0 and r.direction==0)
        down=next(r for r in rows if r.column==0 and r.direction==2)
        self.assertTrue(up.reachable and up.needs_mawashi)
        self.assertEqual(up.mawashi_frames,20)
        self.assertFalse(down.reachable)
        self.assertFalse(any(state[0]==0 for state,*_ in neighbors(EMPTY14,(1,2,0),Timing())))

    def test_mawashi_cost_is_editable_and_does_not_change_normal_placements(self):
        board=high_mawashi_board()
        a=next(r for r in landings(board,'RP',Timing(mawashi=20)) if r.column==0 and r.direction==0)
        b=next(r for r in landings(board,'RP',Timing(mawashi=37)) if r.column==0 and r.direction==0)
        self.assertIsInstance(a.frames,int)
        self.assertIsInstance(b.frames,int)
        self.assertEqual(b.frames-a.frames,17)
        self.assertEqual(b.mawashi_frames-a.mawashi_frames,17)
        normal=next(r for r in landings(EMPTY14,'RP',Timing(mawashi=37)) if r.column==0 and r.direction==0)
        self.assertEqual(normal.mawashi_frames,0)

    def test_floor_lift_only_when_child_rotates_down_into_support(self):
        g=[list(row) for row in EMPTY14]
        g[5][1]=g[5][3]='O'
        board=tuple(''.join(row) for row in g)
        rotations=[target for target,_,_,kind in neighbors(board,(5,2,0),Timing(quick_turn=False)) if kind=='rotation']
        self.assertTrue(all(target[0]==5 for target in rotations))
        g[6][2]='O';board=tuple(''.join(row) for row in g)
        rotations=[target for target,_,_,kind in neighbors(board,(5,2,1),Timing(quick_turn=False)) if kind=='rotation']
        self.assertIn((4,2,2),rotations)

    def test_row14_obstacle_blocks_repeated_top_placement(self):
        g=[list(row) for row in high_mawashi_board()];g[0][0]='B'
        result=next(r for r in landings(tuple(''.join(row) for row in g),'RP') if r.column==0 and r.direction==0)
        self.assertFalse(result.reachable)

class PlacementLabGuiTests(unittest.TestCase):
    def test_window_calculates_without_modifying_editor(self):
        app=App();app.withdraw()
        try:
            before=app.snapshot_board();app.pairs_var.set('RB GY PP')
            app.open_placement_lab();app.update()
            window=next(w for w in app.winfo_children() if w.winfo_class()=='Toplevel')
            def children(parent):
                for w in parent.winfo_children():yield w;yield from children(w)
            button=next(w for w in children(window) if w.winfo_class()=='TButton' and w.cget('text')=='入力盤面から更新')
            button.invoke();app.update()
            table=next(w for w in children(window) if w.winfo_class()=='Treeview')
            self.assertEqual(len(table.get_children()),22)
            self.assertFalse(any(w.winfo_class()=='TCheckbutton' for w in children(window)))
            self.assertFalse(any(w.winfo_class()=='TButton' and w.cget('text')=='設置候補を検証' for w in children(window)))
            self.assertEqual(len(table.get_children()),22)
            self.assertEqual(app.snapshot_board(),before)
            self.assertEqual(len([w for w in children(window) if w.winfo_class()=='Canvas']),3)
            pause=next(w for w in children(window) if w.winfo_class()=='TButton' and w.cget('text')=='一時停止')
            step=next(w for w in children(window) if w.winfo_class()=='TButton' and w.cget('text')=='1コマ進む')
            status=next(w for w in children(window) if w.winfo_name()=='placement_animation_status')
            pause.invoke();self.assertEqual(pause.cget('text'),'再開')
            before_frame=int(status.cget('text').split('/')[0]);step.invoke()
            self.assertEqual(int(status.cget('text').split('/')[0]),before_frame+1)
            self.assertEqual(pause.cget('text'),'再開')
            pause.invoke();self.assertEqual(pause.cget('text'),'一時停止')
        finally:
            for window in list(app.winfo_children()):
                if window.winfo_class()=='Toplevel':window.destroy()
            for event in app.tk.call('after','info'):app.after_cancel(event)
            app.destroy()

if __name__=='__main__':unittest.main()
