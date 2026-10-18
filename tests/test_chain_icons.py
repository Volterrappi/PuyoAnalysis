from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'puyo_tools'))
from app import App, ChainAnimation
from common.engine import EMPTY

def chain():
    return NS(steps=tuple(NS(index=i+1,score=score,frames=80,before=EMPTY,after=EMPTY,
                            erased=(),erased_ojama=()) for i,score in enumerate((40,320))),
              final=EMPTY)

class ChainNuisanceTests(unittest.TestCase):
    def setUp(self):
        self.app=App();self.app.withdraw()
        def cleanup():
            for event in self.app.tk.call('after','info'):self.app.after_cancel(event)
            self.app.destroy()
        self.addCleanup(cleanup)

    def test_animation_and_static_use_identical_step_scores_and_quiet_icons(self):
        with patch.object(self.app,'ojama_display',wraps=self.app.ojama_display) as renderer:
            animation=ChainAnimation(self.app,chain())
            self.assertEqual(renderer.call_args.args[1],40)
            packed=animation.pack_slaves()
            self.assertLess(packed.index(animation.ojama_holder),packed.index(animation.canvas))
            self.assertEqual(renderer.call_args.kwargs,{'compact':True,'subdued':True})
            calls=renderer.call_count
            animation._draw_frame(1)  # same clear, next visual phase
            self.assertEqual(renderer.call_count,calls)
            animation._draw_frame(3)
            self.assertEqual(renderer.call_args.args[1],320)
            renderer.reset_mock();animation.toggle_static()
            self.assertEqual([call.args[1] for call in renderer.call_args_list],[40,320,320])
            self.assertTrue(all(call.kwargs=={'compact':True,'subdued':True} for call in renderer.call_args_list))
            animation._draw_frame(0)
            self.assertEqual(renderer.call_args.args[1],40)
            animation.destroy()

    def test_used_bonus_added_once_and_no_chain_has_no_attack(self):
        with patch.object(self.app,'ojama_display',wraps=self.app.ojama_display) as renderer:
            animation=ChainAnimation(self.app,chain(),initial_bonus=2100)
            self.assertEqual(animation._frames[0][3],2140)
            self.assertEqual(animation._frames[3][3],320)
            renderer.reset_mock();animation.toggle_static()
            self.assertEqual([call.args[1] for call in renderer.call_args_list],[2140,320,320])
            animation.destroy()
            empty=ChainAnimation(self.app,NS(steps=(),final=EMPTY),initial_bonus=2100)
            self.assertEqual(renderer.call_args.args[1],0)
            empty.destroy()

    def test_static_copy_still_uses_board_without_icon_data(self):
        copy=lambda board:None
        animation=ChainAnimation(self.app,chain(),on_copy=copy)
        animation.toggle_static()
        self.assertEqual(len(animation.static.winfo_children()),3)
        for frame in animation.static.winfo_children():
            canvas=next(w for w in frame.winfo_children() if w.winfo_class()=='Canvas')
            self.assertTrue(canvas.bind('<Button-1>'))
        animation.destroy()

    def test_expanded_history_can_scroll_separately_and_is_cleaned_up(self):
        import tkinter.ttk as ttk
        scroll_body=ttk.Frame(self.app)
        animation=ChainAnimation(self.app,chain(),static_parent=scroll_body)
        history=animation.static
        self.assertIs(history.master,scroll_body)
        animation.toggle_static()
        for frame in history.winfo_children():
            widgets=frame.pack_slaves()
            self.assertEqual(widgets[-1].winfo_class(),'Canvas')
            self.assertEqual(widgets[-2].winfo_class(),'TFrame')
        animation.destroy()
        self.assertFalse(history.winfo_exists())

if __name__=='__main__':unittest.main()
