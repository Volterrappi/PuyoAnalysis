from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'puyo_tools'))
from common.analysis import candidate_stats, response_priority
from common.engine import EMPTY, Placement
from app import App

BOARD=EMPTY[:-1]+('R.....',)

def candidate(counts, scores=None, frames=120, final=BOARD, used=False):
    scores=scores or [1000 if n else 0 for n in counts]
    turns=tuple(NS(move=Placement(0,'U'),used_bonus=used,
                   chain=NS(count=n,score=score,frames=frames if n else 0,
                            erased=4*n,ojama=0,final=final),
                   points=score+(2100 if used else 0))
                for n,score in zip(counts,scores))
    return NS(turns=turns,final=final)

class ResponseRankingTests(unittest.TestCase):
    def rank(self,c,limit=5,mode='used',chigiri=0,clears=0):
        return response_priority(c,NS(chigiri_total=chigiri,clear_count=clears),limit,mode)

    def test_excludes_no_fire_and_checks_every_turn_against_limit(self):
        self.assertIsNone(self.rank(candidate([0,0,0])))
        self.assertIsNone(self.rank(candidate([1,6,0]),limit=5))
        self.assertIsNotNone(self.rank(candidate([0,5,0]),limit=5))
        with self.assertRaises(ValueError):self.rank(candidate([1,0,0]),limit=0)

    def test_fewer_fires_precedes_efficiency(self):
        one=self.rank(candidate([0,2,0],frames=900))
        two=self.rank(candidate([1,1,0],frames=1))
        self.assertLess(one,two)

    def test_efficiency_precedes_chigiri_and_clear_tiebreaks(self):
        fast=candidate([2,0,0],frames=60)
        slow=candidate([2,0,0],frames=300)
        self.assertLess(self.rank(fast,chigiri=3),self.rank(slow,clears=3))
        self.assertLess(self.rank(fast,chigiri=0),self.rank(fast,chigiri=1,clears=3))
        self.assertLess(self.rank(fast,clears=1),self.rank(fast,clears=0))

    def test_efficiency_follows_bonus_setting_and_uses_best_firing_turn(self):
        c=candidate([1,0,0],final=EMPTY)
        self.assertLess(self.rank(c,mode='earned'),self.rank(c,mode='none'))
        c=candidate([1,0,0],used=True)
        self.assertLess(self.rank(c,mode='used'),self.rank(c,mode='none'))
        c=candidate([1,2,0],scores=[100,2000,0])
        self.assertEqual(self.rank(c)[1],self.rank(candidate([0,2,0],scores=[0,2000,0]))[1])

class ResponseGuiTests(unittest.TestCase):
    def setUp(self):
        self.app=App();self.app.withdraw()
        def cleanup():
            for event in self.app.tk.call('after','info'):self.app.after_cancel(event)
            self.app.destroy()
        self.addCleanup(cleanup)
        self.app.select_result=lambda e:None
        self.app.results=[candidate([1,1,0],scores=[1000,1000,0]),
                          candidate([2,0,0],scores=[2000,0,0],frames=300),
                          candidate([0,2,0],scores=[0,2000,0],frames=60),
                          candidate([5,0,0],scores=[2000,0,0],frames=1),
                          candidate([0,0,0])]
        self.app.stats=[candidate_stats(c,BOARD) for c in self.app.results]

    def test_mode_filters_and_selects_representative_without_changing_results(self):
        self.app.show_results()
        self.assertEqual(self.app.groups[0][2],0)
        self.app.response_mode.set(True);self.app.response_limit.set('2')
        self.app.change_response_mode()
        self.assertEqual(self.app.filtered,[0,1,2])
        self.assertEqual(self.app.groups[0][2],2)
        self.assertIn('response_eff',self.app.table['columns'])
        self.assertEqual(len(self.app.table.item('0','values')),len(self.app.table['columns']))
        self.app.sort_by_column('response_eff')
        self.app.view.set('detail');self.app.show_results()
        self.assertEqual(set(self.app.order),{0,1,2})
        self.app.response_limit.set('5');self.app.change_response_mode()
        self.assertEqual(set(self.app.filtered),{0,1,2,3})
        self.app.response_mode.set(False);self.app.change_response_mode()
        self.assertEqual(len(self.app.filtered),5)
        self.assertEqual(len(self.app.results),5)

    def test_no_match_then_restores_when_limit_relaxed(self):
        self.app.results=[candidate([3,0,0])]
        self.app.stats=[candidate_stats(self.app.results[0],BOARD)]
        self.app.response_mode.set(True);self.app.response_limit.set('2')
        self.app.change_response_mode()
        self.assertEqual(self.app.visible,[])
        self.app.response_limit.set('3');self.app.change_response_mode()
        self.assertEqual(self.app.visible,[0])

    def test_response_controls_are_not_shown_in_details(self):
        def children(parent):
            for w in parent.winfo_children():yield w;yield from children(w)
        controls=[w for w in children(self.app.details_frame) if w.winfo_class()=='TCheckbutton']
        self.assertFalse(any(w.cget('text')=='対応想定で絞る・代表を選ぶ' for w in controls))
        self.assertFalse(self.app.details_frame.winfo_manager())
        self.app.toggle_details()
        self.assertEqual(self.app.details_frame.winfo_manager(),'pack')
        self.app.response_mode.set(True);self.app.change_response_mode()
        self.assertEqual(self.app.groups[0][2],2)  # efficiency includes replenishment time

if __name__=='__main__':unittest.main()
