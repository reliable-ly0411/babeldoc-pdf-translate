"""New rendered-page role failure; not a new blind-model score or detector."""
import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import semantic_review as review,semantic_quality as quality


class PolicyRoleRegressionTests(unittest.TestCase):
    def setUp(self):
        self.path=Path(__file__).parent/'fixtures/r1-policy-known-failure.json'
        self.data=json.loads(self.path.read_text(encoding='utf8'));self.row=self.data['failures'][0]

    def test_literal_fidelity_alone_cannot_detect_actual_policy_role_error(self):
        pair={'pair_0':{'source':self.row['source'],'target':self.row['target']}}
        faithful='针对每个问题{v1}，GRPO采样一组输出{v2}，所用旧策略为{v3}，随后通过最大化下述目标优化策略模型{v4}：'
        for text in [self.row['target'],faithful]:
            self.assertEqual(review.checked_replacements({'replacements':{'pair_0':text}},pair)['pair_0'],text)
        corpus=quality.load_corpora([self.path])
        self.assertEqual(quality.known_failures(pair,corpus,self.data['source_document_sha256'])[0]['case_id'],'R1-P07-POLICY-ROLE')
        self.assertEqual(quality.known_failures({'pair_0':{'source':self.row['source'],'target':faithful}},corpus,self.data['source_document_sha256']),[])

    def test_known_failure_still_vetoes_claimed_protocol_success_and_binds_document(self):
        pair={'pair_0':{'source':self.row['source'],'target':self.row['target']}}
        corpus=quality.load_corpora([self.path]);hits=quality.known_failures(pair,corpus,self.data['source_document_sha256'])
        result=quality.decide(execution_completed=True,model_status='model_screened',requested_pages=[7],image_pages=[7],
            uncertain_count=0,relation_witness_coverage_complete=True,known_regressions=hits,protocol_validated=True)
        self.assertEqual(result['quality_status'],'blocked_known_regression');self.assertFalse(result['quality_passed'])
        self.assertEqual(quality.known_failures(pair,corpus,'0'*64),[])


if __name__=='__main__':unittest.main()
