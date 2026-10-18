"""Offline protocol/gate checks; no native model or network invocation."""
import copy,json,tempfile,unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import semantic_relations as r
import semantic_quality as q
import semantic_review as s
import semantic_blind as blind


class RelationTests(unittest.TestCase):
    def setUp(self):
        self.source='The sensors beside the pump measure the temperature.'
        self.target='水泵测量旁边传感器的温度。'
        self.pairs={'pair_0':{'source':self.source,'target':self.target}}
        self.claim={'kind':'predicate','status':'changed','source_quote':self.source,'target_quote':self.target,
            'source_subject':'The sensors','source_predicate':'measure','source_object':'the temperature',
            'target_subject':'水泵','target_predicate':'测量','target_object':'传感器的温度','explanation':'The measured-temperature actor and possessive relation differ.'}
        self.value={'pairs':{'pair_0':{'status':'different','summary':'The actor differs.','alignments':[self.claim]}}}

    def test_anchored_role_change_produces_standard_finding_and_coverage_evidence(self):
        self.assertEqual(r.checked(self.value,self.pairs),self.value)
        self.assertTrue(r.coverage(self.value,self.pairs)['lexical_witness_coverage_complete'])
        self.assertEqual(r.as_review(self.value,self.pairs)['pairs']['pair_0']['findings'][0]['category'],'semantic_role')

    def test_legacy_false_equivalent_without_witness_is_rejected(self):
        legacy={'pairs':{'pair_0':{'status':'equivalent','summary':'Meaning is retained.','findings':[]}}}
        self.assertEqual(s.screening_status(legacy,self.pairs),'semantic_model_screened')
        with self.assertRaisesRegex(ValueError,'INVALID_RELATION_ROW'):r.checked(legacy,self.pairs)

    def test_vacuous_equivalence_empty_witness_and_unknown_keys_fail(self):
        for rows in ([],[dict(self.claim,extra='coordinate')]):
            value=copy.deepcopy(self.value);value['pairs']['pair_0']['alignments']=rows
            with self.assertRaises(ValueError):r.checked(value,self.pairs)

    def test_role_anchor_cannot_be_invented_and_quotes_cannot_be_normalized(self):
        for field,text in [('source_subject','the nonexistent controller'),('source_quote',self.source.lower()),('target_quote','不在目标中的引文')]:
            value=copy.deepcopy(self.value);value['pairs']['pair_0']['alignments'][0][field]=text
            with self.assertRaises(ValueError):r.checked(value,self.pairs)

    def test_partial_quotes_cannot_certify_complete_proposition_coverage(self):
        claim={**self.claim,'source_quote':'sensors beside the pump','source_subject':'sensors','source_predicate':'beside','source_object':'the pump'}
        value={'pairs':{'pair_0':{**self.value['pairs']['pair_0'],'alignments':[claim]}}}
        with self.assertRaisesRegex(ValueError,'INCOMPLETE_RELATION_SOURCE_COVERAGE'):r.checked(value,self.pairs)

    def test_uncertainty_and_changed_alignment_cannot_be_renamed_equivalent(self):
        for status in ('changed','uncertain','missing'):
            value=copy.deepcopy(self.value);value['pairs']['pair_0']['status']='equivalent'
            value['pairs']['pair_0']['alignments'][0]['status']=status
            with self.assertRaisesRegex(ValueError,'CONCLUSION_INCONSISTENT'):r.checked(value,self.pairs)

    def test_short_ambiguous_quote_needs_context(self):
        pairs={'pair_0':{'source':'The pump is near the pump.','target':'水泵在另一水泵旁。'}}
        claim={**self.claim,'source_quote':'pump','source_subject':'pump','source_predicate':'pump','source_object':''}
        value={'pairs':{'pair_0':{**self.value['pairs']['pair_0'],'alignments':[claim]}}}
        with self.assertRaisesRegex(ValueError,'QUOTE_AMBIGUOUS'):r.checked(value,pairs)

    def test_quoted_coverage_is_not_automatically_a_quality_certificate(self):
        decision=q.decide(execution_completed=True,model_status='model_screened',requested_pages=[1],image_pages=[1],
            uncertain_count=0,relation_witness_coverage_complete=True,known_regressions=[])
        self.assertFalse(decision['quality_passed'])
        self.assertEqual(decision['quality_status'],'blocked_unvalidated_protocol')
        self.assertFalse(decision['promotion_allowed'])

    def test_risk_priority_uses_source_only_not_known_answers_or_target_status(self):
        first={'pair_0':{'source':'A short sentence.','target':'一个短句。'},'pair_1':{'source':'A longer clause, with {v1}, another condition; and {v2}.','target':'目标文本。'}}
        second={key:{**row,'target':'完全不同的候选文本。'} for key,row in first.items()}
        self.assertEqual(r.source_risk_profile(first),r.source_risk_profile(second))
        self.assertEqual(r.source_risk_profile(first)[0]['pair_id'],'pair_1')


class QualityTests(unittest.TestCase):
    def decide(self,**changes):
        args=dict(execution_completed=True,model_status='model_screened',requested_pages=[1,2],image_pages=[1,2],
            uncertain_count=0,relation_witness_coverage_complete=True,known_regressions=[],protocol_validated=True)
        args.update(changes);return q.decide(**args)

    def test_known_regression_vetoes_unanimous_model_success(self):
        result=self.decide(known_regressions=[{'case_id':'actual-failed-row'}])
        self.assertEqual(result['quality_status'],'blocked_known_regression')
        self.assertFalse(result['candidate_ready_for_independent_validation']);self.assertFalse(result['quality_passed'])

    def test_uncertain_unknown_partial_coverage_and_execution_failures_block(self):
        for changes,expected in [({'uncertain_count':1},'blocked_uncertainty'),({'uncertain_count':None},'blocked_uncertainty'),
            ({'image_pages':[1]},'blocked_incomplete_evidence'),({'relation_witness_coverage_complete':False},'blocked_incomplete_evidence'),
            ({'execution_completed':False},'blocked_model_or_execution'),({'inputs_unchanged':False},'blocked_input_change')]:
            result=self.decide(**changes);self.assertEqual(result['quality_status'],expected)
            self.assertFalse(result['quality_passed'])

    def test_data_corpus_binds_source_target_and_document_not_specific_words(self):
        root=Path(__file__).parent/'fixtures';cases=json.loads((root/'semantic-known-failures.json').read_text(encoding='utf8'))
        corpus=q.load_corpora([root/'semantic-known-failures.json']);row=next(x for x in cases['failures'] if x['id']=='D02')
        pairs={'pair_0':{'source':row['source'],'target':row['target']}}
        self.assertEqual(q.known_failures(pairs,corpus,cases['source_document_sha256'])[0]['case_id'],'D02')
        self.assertEqual(q.known_failures(pairs,corpus,'0'*64),[])
        self.assertEqual(q.known_failures({'pair_0':{'source':'A different source with the same target.','target':row['target']}},corpus,cases['source_document_sha256']),[])

    def test_new_controls_both_sides_pass_literal_guards_without_being_semantically_equal(self):
        data=json.loads((Path(__file__).parent/'fixtures/semantic-relation-controls.json').read_text(encoding='utf8'))
        self.assertEqual(len(data['cases']),12)
        self.assertEqual(sum(x['kind']=='new_synthetic' for x in data['cases']),8)
        for case in data['cases']:
            for side in ('good','bad'):
                pair={'pair_0':{'source':case['source'],'target':case[side]}}
                self.assertEqual(s.checked_replacements({'replacements':{'pair_0':case[side]}},pair)['pair_0'],case[side])

    def test_blind_arms_have_no_same_source_answer_alternatives_or_labels(self):
        data=json.loads((Path(__file__).parent/'fixtures/semantic-relation-controls.json').read_text(encoding='utf8'))
        arms,truth=blind.build_arms(data['cases'],61016)
        for name,pairs in arms.items():
            self.assertEqual(len({x['source'] for x in pairs.values()}),12)
            payload=blind.model_payload(pairs)
            for label in [x['id'] for x in data['cases']]:self.assertNotIn(label,payload['prompt'])
            self.assertEqual(sum(x['expected']=='different' for x in truth[name].values()),6)
            for key,row in pairs.items():
                case=next(x for x in data['cases'] if x['id']==truth[name][key]['case_id'])
                alternative=case['good'] if row['target']==case['bad'] else case['bad']
                self.assertNotIn(alternative,[x['target'] for x in pairs.values()])
                if alternative!=case['source']:self.assertNotIn(alternative,payload['prompt'])
        with self.assertRaises(ValueError):blind.model_payload({'pair_0':arms['A'][next(iter(arms['A']))],'pair_1':arms['A'][next(iter(arms['A']))]})

    def test_a_unanimous_equivalent_control_response_cannot_pass_blind_evaluation(self):
        data=json.loads((Path(__file__).parent/'fixtures/semantic-relation-controls.json').read_text(encoding='utf8'))
        arms,truth=blind.build_arms(data['cases'],61016);pairs=arms['A']
        review={'pairs':{key:{'status':'equivalent','summary':'Claimed equivalent.','findings':[]} for key in pairs}}
        result=blind.score(review,pairs,truth['A'])
        self.assertEqual(result['false_negative'],6);self.assertFalse(result['pilot_passed']);self.assertFalse(result['quality_passed'])


if __name__=='__main__':unittest.main()
