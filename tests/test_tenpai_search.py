from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'puyo_tools'))
from common import engine as e
from tenpai_evaluation import collect_responses
from tenpai_search import search,add_color,group_responses

class TenpaiSearchTests(unittest.TestCase):
    def test_zero_matches_existing_ignitions(self):
        board=e.EMPTY[:-1]+('RRR...',)
        result=search(board,0)
        self.assertTrue(result['complete']);self.assertEqual(result['completed_shanten'],0)
        self.assertEqual([(r['score'],r['pieces'],r['column']) for r in result['responses']],[(r['score'],r['pieces'],r['column']) for r in collect_responses(board)])

    def test_preparation_is_colored_nonfiring_and_shanten_counts_it(self):
        board=e.EMPTY[:-1]+('RR....',)
        result=search(board,1)
        self.assertTrue(result['complete']);self.assertTrue(result['responses'])
        self.assertTrue(all(r['shanten']==1 for r in result['responses']))
        for response in result['responses']:
            prepared=board
            self.assertEqual(len(response['preparation']),response['shanten'])
            for col,color in response['preparation']:
                self.assertIn(color,e.COLORS);prepared=add_color(prepared,col-1,color)
                self.assertEqual(e.simulate(prepared).count,0)
            self.assertEqual(tuple(response['ready_board']),prepared)
            for color in response['pieces']:prepared=add_color(prepared,response['column']-1,color)
            self.assertEqual(e.simulate(prepared).score,response['score'])

    def test_limits_never_claim_complete(self):
        result=search(e.EMPTY,3,seconds_limit=0)
        self.assertFalse(result['complete']);self.assertEqual(result['completed_shanten'],-1)
        result=search(e.EMPTY,3,state_limit=1)
        self.assertFalse(result['complete'])

    def test_group_by_score_and_keep_all_options(self):
        responses=search(e.EMPTY[:-1]+('RR....',),1)['responses']
        groups=group_responses(responses)
        self.assertEqual(sum(len(items) for _,items,_ in groups),len(responses))
        self.assertEqual([score for score,_,_ in groups],sorted({r['score'] for r in responses},reverse=True))

    def test_optional_limits_and_user_cancellation(self):
        complete=search(e.EMPTY,1,seconds_limit=None,state_limit=None)
        self.assertTrue(complete['complete'])
        checks=0
        def cancelled():
            nonlocal checks
            checks+=1
            return checks>5
        result=search(e.EMPTY[:-1]+('RRR...',),3,seconds_limit=None,state_limit=None,cancelled=cancelled)
        self.assertFalse(result['complete']);self.assertEqual(result['stop_reason'],'cancelled')
        self.assertTrue(result['responses'])

if __name__=='__main__':unittest.main()
