from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'puyo_tools'))
from common import engine as e
from tenpai_evaluation import collect_responses,evaluate,score_response,attack_score,ScoringPolicy

class TenpaiEvaluationTests(unittest.TestCase):
    def test_boundaries_and_linear_product(self):
        k=3;score=attack_score(k)
        self.assertEqual(score_response(dict(score=2*score,frames=320,erased=17),k)['score'],1)
        self.assertEqual(score_response(dict(score=score,frames=320,erased=17),k)['score'],0)
        self.assertAlmostEqual(score_response(dict(score=1.5*score,frames=440,erased=20.5),k)['score'],.125)
        for changes in (dict(frames=560),dict(erased=24)):
            response=dict(score=2*score,frames=320,erased=17);response.update(changes)
            self.assertEqual(score_response(response,k)['score'],0)

    def test_best_per_attack_not_sum_of_duplicate_ignitions(self):
        board=e.EMPTY[:-2]+('RRBBGG','YYPPRR')
        response=dict(column=1,pieces='R',chains=3,score=2000,frames=240,erased=12)
        first=evaluate(board,[response]);second=evaluate(board,[response,response])
        self.assertEqual(first['score'],second['score'])
        self.assertEqual([r['attack_chains'] for r in first['attacks']],[2,3])
        changed=evaluate(board,[response],ScoringPolicy(power_full_ratio=3))
        self.assertEqual(first['responses'],changed['responses'])
        self.assertNotEqual(first['score'],changed['score'])

    def test_collected_color_consumption_and_empty_result(self):
        board=e.EMPTY[:-1]+('RRR...',)
        responses=collect_responses(board)
        self.assertTrue(responses)
        self.assertTrue(all(r['erased']==4 for r in responses))
        self.assertEqual(evaluate(board,responses)['score'],0)

    def test_search_pruning_matches_post_filter(self):
        board=e.EMPTY[:-3]+('B.....','BB....','RRR...')
        pairs=('RB','GY','RP')
        expected=[c for c in e.solve(board,pairs) if all(t.chain.count<=1 for t in c.turns) and sum(bool(t.chain.count) for t in c.turns)<=1]
        self.assertEqual(e.solve(board,pairs,tenpai_only=True),expected)

if __name__=='__main__':unittest.main()
