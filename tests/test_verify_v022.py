import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('verify_v022',ROOT/'tools/verify-v022.py')
verify=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(verify)


class VersionVerifierTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.library=self.root/'project-template/references/award-patterns'
        self.case_id='mcm-2024-a-2400001'
        self.case={'format_version':1,'id':self.case_id,'year':2024,'problem':'A','team':'2400001',
            'pdf_sha256':'1'*64,'physical_page_count':3,'public_source':{'url':'https://example.org/paper.pdf'},
            'award_evidence':{'url':'https://example.org/result.pdf','source_sha256':'2'*64,'physical_page':1,
                'status':'official_result_row_checked','designation':'Outstanding Winner'},
            'observed_pages':{'rendered_and_viewed':[1,3],'text_context_reviewed':[1,3]},
            'answer_chain':['A declared comparison'],'good_practices':['A source observation'],
            'risks':['No numeric reproduction'],'validation':{'level':'source_observation_with_selected_page_visual_review','official_award_identity_verified':True}}
        self.pattern={'id':'one-pattern','category':'result-evidence','roles':['mcm-reviewer'],
            'keywords':['baseline'],'file':'patterns/one.md','source_case_ids':[self.case_id],
            'validation_status':'observed_pattern_not_causal_award_rule'}

    def save(self,path,value):
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(value),encoding='utf-8');return path

    def library_fixture(self):
        self.save(self.library/'catalog.json',{'format_version':1,'patterns':[self.pattern]})
        self.save(self.library/'cases'/f'{self.case_id}.json',self.case)
        file=self.library/'patterns/one.md';file.parent.mkdir();file.write_text('An authored observation with explicit limits.',encoding='utf-8')

    def test_pending_stages_do_not_become_passed(self):
        self.assertEqual(verify.validate_library(self.root)['status'],'pending')
        self.assertEqual(verify.validate_gallery(self.root)['status'],'pending')

    def test_valid_library_does_not_force_a_paper_or_pattern_quota(self):
        self.library_fixture();report=verify.validate_library(self.root)
        self.assertEqual(report['status'],'passed');self.assertEqual(report['patterns'],1);self.assertEqual(report['source_cases'],1)
        self.assertIn('did not reauthenticate',report['limits'][0])
        self.assertEqual(report['versioned_patterns'],0)
        self.assertEqual(report['declared_pattern_refs'],{})

    def test_optional_pattern_pin_binds_current_bytes_and_rejects_unannounced_drift(self):
        self.library_fixture();path=self.library/'patterns/one.md'
        row={**self.pattern,'version':2,'sha256':verify.digest(path)}
        self.save(self.library/'catalog.json',{'format_version':1,'patterns':[row]})
        report=verify.validate_library(self.root)
        self.assertEqual(report['versioned_patterns'],1)
        self.assertEqual(report['declared_pattern_refs'][row['id']],{'path':'patterns/one.md','version':2,'sha256':row['sha256']})
        path.write_text('Changed authored conditions without updating the declared pin.',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'Pattern entry digest mismatch'):verify.validate_library(self.root)

    def test_optional_pattern_pin_requires_complete_typed_metadata(self):
        self.library_fixture();digest=verify.digest(self.library/'patterns/one.md')
        pins=[{'version':True,'sha256':digest},{'version':0,'sha256':digest},
              {'version':'2','sha256':digest},{'version':2},{'sha256':digest},
              {'version':2,'sha256':None},{'version':2,'sha256':'not-a-digest'}]
        for pin in pins:
            self.save(self.library/'catalog.json',{'format_version':1,'patterns':[{**self.pattern,**pin}]})
            with self.subTest(pin=pin),self.assertRaisesRegex(ValueError,'Pattern entry'):
                verify.validate_library(self.root)

    def test_duplicate_pattern_id_is_rejected(self):
        self.library_fixture();self.save(self.library/'catalog.json',{'format_version':1,'patterns':[self.pattern,copy.deepcopy(self.pattern)]})
        with self.assertRaisesRegex(ValueError,'Duplicate pattern ID'):verify.validate_library(self.root)

    def test_unknown_preset_and_causal_award_claims_are_rejected(self):
        self.library_fixture()
        for key,value in [('roles',['captain-by-name']),('validation_status','guaranteed_award_rule')]:
            row={**self.pattern,key:value};self.save(self.library/'catalog.json',{'format_version':1,'patterns':[row]})
            with self.subTest(key=key),self.assertRaises(ValueError):verify.validate_library(self.root)

    def test_pattern_path_cannot_escape_its_catalog(self):
        self.library_fixture()
        for path in ['../outside.md','C:\\outside.md']:
            row={**self.pattern,'file':path};self.save(self.library/'catalog.json',{'format_version':1,'patterns':[row]})
            with self.subTest(path=path),self.assertRaises(ValueError):verify.validate_library(self.root)

    def test_source_case_must_exist_and_bind_its_own_identity(self):
        self.library_fixture();case_path=self.library/'cases'/f'{self.case_id}.json'
        case_path.unlink()
        with self.assertRaisesRegex(ValueError,'absent'):verify.validate_library(self.root)
        self.save(case_path,{**self.case,'id':'another-paper'})
        with self.assertRaisesRegex(ValueError,'identity mismatch'):verify.validate_library(self.root)

    def test_metadata_requires_award_evidence_and_actual_page_locations(self):
        self.library_fixture();case_path=self.library/'cases'/f'{self.case_id}.json'
        bad=copy.deepcopy(self.case);bad['award_evidence']['status']='unverified';self.save(case_path,bad)
        with self.assertRaisesRegex(ValueError,'Outstanding'):verify.validate_library(self.root)
        bad=copy.deepcopy(self.case);bad['observed_pages']['rendered_and_viewed']=[4];self.save(case_path,bad)
        with self.assertRaisesRegex(ValueError,'observed pages'):verify.validate_library(self.root)

    def test_image_only_source_can_record_visual_reading_without_text_extraction(self):
        self.library_fixture();case=copy.deepcopy(self.case);case['observed_pages']['text_context_reviewed']=[]
        self.save(self.library/'cases'/f'{self.case_id}.json',case)
        self.assertEqual(verify.validate_library(self.root)['status'],'passed')

    def test_fixed_reference_rejects_byte_drift_and_boolean_versions(self):
        file=self.root/'artifact.txt';file.write_text('fixed',encoding='utf-8')
        ref={'path':'artifact.txt','version':1,'sha256':verify.digest(file)}
        self.assertEqual(verify.fixed_file(self.root,ref),file)
        with self.assertRaisesRegex(ValueError,'artifact version'):verify.fixed_file(self.root,{**ref,'version':True})
        file.write_text('changed',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'Changed reference bytes'):verify.fixed_file(self.root,ref)

    def gallery_fixture(self):
        from pypdf import PdfWriter
        base=self.root/'gallery';base.mkdir()
        source=self.save(self.root/'bundle/src/figure-style.json',{'minimum_final_glyph_pt':12})
        self.save(base/'config/figure-style.json',{'minimum_final_glyph_pt':12})
        script=self.root/'tools/figure-gallery.py';script.parent.mkdir();script.write_text('# synthetic fixture\n',encoding='utf-8')
        snapshot=base/'source/figure-gallery.py';snapshot.parent.mkdir();snapshot.write_bytes(script.read_bytes())
        check=base/'project-placeholder';check.write_text('not a full project',encoding='utf-8')
        own_checker=self.root/'project-template/scripts/figure_check.py';own_checker.parent.mkdir(parents=True)
        own_checker.write_bytes((ROOT/'project-template/scripts/figure_check.py').read_bytes())
        contract=self.save(base/'contracts/one.json',{'figure_id':'one','synthetic':True})
        tex=base/'latex/page-examples.tex';tex.parent.mkdir();tex.write_text('Synthetic page source.',encoding='utf-8')
        pages=base/'pages';pages.mkdir();pdf=pages/'page-examples.pdf';writer=PdfWriter();writer.add_blank_page(width=200,height=200)
        with pdf.open('wb') as stream:writer.write(stream)
        (pages/'page-01.png').write_bytes(b'synthetic-render-fixture')
        report=self.save(pages/'build-report.json',{'page_count':1,'pdf_sha256':verify.digest(pdf),
            'source_sha256':verify.digest(tex),'pages':[{'page':1,'render':'pages/page-01.png'}],
            'commands':[{'engine':'fixture','exit_code':0}],'full_competition_paper':False})
        def ref(path):return {'path':path.relative_to(base).as_posix(),'version':1,'sha256':verify.digest(path)}
        self.gallery={'version':'0.2.2','synthetic':True,'uses_heldout_answers':False,'status':'needs_repair',
            'style_source':{'path':'bundle/src/figure-style.json','sha256':verify.digest(source)},
            'style_snapshot':ref(base/'config/figure-style.json'),'source_script':ref(snapshot),
            'figures':[{'id':'one','contract':ref(contract),'passed_mechanical':False,'visual_status':'pending'}],
            'pages':{'pdf':ref(pdf),'build_report':ref(report),'page_count':1},
            'source_preflight':{'status':'failed','exit_code':1}}
        self.save(base/'checks/source-preflight.json',{'summary':{'ready':False,'counts':{'FAIL':1}}})
        self.save(base/'manifest.json',self.gallery)

    def test_incomplete_gallery_remains_pending_with_actual_errors(self):
        self.gallery_fixture();report=verify.validate_gallery(self.root)
        self.assertEqual(report['status'],'pending');self.assertEqual(report['visual_acceptance'],'not_assessed')
        self.assertEqual(len(report['failed_mechanical_figures']),1)

    def test_gallery_cannot_mark_failed_contract_as_mechanically_passed(self):
        self.gallery_fixture();self.gallery['figures'][0]['passed_mechanical']=True;self.save(self.root/'gallery/manifest.json',self.gallery)
        with self.assertRaisesRegex(ValueError,'disagree'):verify.validate_gallery(self.root)

    def test_gallery_stale_page_binding_is_rejected(self):
        self.gallery_fixture();self.gallery['pages']['page_count']=2;self.save(self.root/'gallery/manifest.json',self.gallery)
        with self.assertRaisesRegex(ValueError,'page count/hash'):verify.validate_gallery(self.root)

    def test_gallery_preflight_pass_cannot_override_a_failed_actual_report(self):
        self.gallery_fixture();self.gallery['source_preflight']={'status':'passed','exit_code':0}
        self.save(self.root/'gallery/manifest.json',self.gallery)
        with self.assertRaisesRegex(ValueError,'actual report'):verify.validate_gallery(self.root)


if __name__=='__main__':unittest.main()
