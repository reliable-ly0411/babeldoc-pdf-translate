from pathlib import Path
import json,sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import semantic_review as s
import chat_bridge as b
import source_repair as sr


class SemanticReviewTests(unittest.TestCase):
    def setUp(self):
        self.pairs={'pair_0':{'source':'The functions of {v1} form a basis.',
            'target':'以{v1}为基底的函数。'}}
        self.finding={'category':'semantic_role','severity':'major',
            'source_quote':'functions of {v1} form a basis','target_quote':'以{v1}为基底','reason':'The argument and basis roles differ.'}
        self.review={'pairs':{'pair_0':{'status':'different','summary':'A role changed.','findings':[self.finding]}}}

    def test_real_evidence_and_complete_coverage_are_required(self):
        self.assertEqual(s.checked(self.review,self.pairs),self.review)
        with self.assertRaises(ValueError):s.checked({'pairs':{}},self.pairs)
        self.finding['source_quote']='a source claim that never appeared'
        with self.assertRaisesRegex(ValueError,'SOURCE_EVIDENCE'):s.checked(self.review,self.pairs)

    def test_target_evidence_cannot_be_invented_or_omitted_for_role_claim(self):
        for quote in ('','invented target claim'):
            self.finding['target_quote']=quote
            with self.assertRaises(ValueError):s.checked(self.review,self.pairs)

    def test_empty_equivalent_and_unknown_are_distinct(self):
        row=self.review['pairs']['pair_0'];row.update(status='equivalent',findings=[])
        self.assertEqual(s.summary(s.checked(self.review,self.pairs))['equivalent'],1)
        row['status']='uncertain'
        self.assertEqual(s.summary(s.checked(self.review,self.pairs))['uncertain'],1)
        row.update(status='different',findings=[])
        with self.assertRaises(ValueError):s.checked(self.review,self.pairs)

    def test_actual_missing_reference_relation_blocks_even_with_all_markers_preserved(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/l1quad-reference-connector.json').read_text(encoding='utf8'))
        pairs=fixture['pairs'];review=fixture['actual_review']
        # Existing literal/math/style checks alone accept this real bad row.
        targets={key:row['target'] for key,row in pairs.items()}
        self.assertEqual(s.checked_replacements({'replacements':targets},pairs),targets)
        self.assertEqual(s.screening_status(review,pairs),'needs_manual_review')

    def test_semantic_gate_cannot_clear_incomplete_or_uncertain_screen(self):
        with self.assertRaises(ValueError):s.screening_status({'pairs':{}},self.pairs)
        row=self.review['pairs']['pair_0'];row.update(status='uncertain',findings=[])
        self.assertEqual(s.screening_status(self.review,self.pairs),'needs_manual_review')
        row.update(status='equivalent')
        self.assertEqual(s.screening_status(self.review,self.pairs),'semantic_model_screened')

    def test_source_faithful_basis_and_reference_corrections_keep_math(self):
        good={'replacements':{'pair_0':'关于{v1}的函数构成一组基。'}}
        self.assertEqual(s.checked_replacements(good,self.pairs),good['replacements'])
        for text in ('关于{v2}的函数构成基。','这些函数构成基。'):
            with self.assertRaises(b.BridgeError):s.checked_replacements({'replacements':{'pair_0':text}},self.pairs)

    def test_model_cannot_add_coordinates_or_unknown_pair_keys(self):
        self.finding['bbox']=[0,0,200,200]
        with self.assertRaises(ValueError):s.checked(self.review,self.pairs)
        with self.assertRaises(ValueError):s.checked_replacements({'replacements':{'pair_1':'文本'}},self.pairs)

    def test_verified_plain_prose_does_not_require_a_math_glyph(self):
        units=[{'source':'The voltage is stable.','paragraph':0,'left_literal':'','right_literal':''}]
        result=sr.restored_semantic_pair(units,['电压稳定。'],[])
        self.assertEqual(result['pair']['source'],'The voltage is stable.')
        self.assertEqual(result['pair']['target'],'电压稳定。')
        self.assertIsNone(sr.restored_semantic_pair([],[],[]))

    def test_replayed_source_prose_replaces_a_stale_native_pair_only_with_unique_evidence(self):
        restored=sr.restored_semantic_pair([{'source':'where','paragraph':0,'right_literal':'unchanged math'},
            {'source':'and','paragraph':0,'right_literal':'another unchanged object'},
            {'source':'is the initial state.','paragraph':0,'right_literal':''}],['其中','且','为初始状态。'],[('font','x',10,(5,5))])
        pairs={'pair_0':{'source':'where {v1} and{v2}is the initial state.','target':'原始译文'}}
        updated,decisions=s.reflect_source_restorations(pairs,[restored])
        self.assertEqual(updated['pair_0'],restored['pair']);self.assertEqual(len(decisions),1)
        with self.assertRaisesRegex(ValueError,'AMBIGUOUS'):
            s.reflect_source_restorations({**pairs,'pair_1':pairs['pair_0']},[restored])


if __name__=='__main__':unittest.main()
