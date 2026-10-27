import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('figure_optional_design',ROOT/'project-template/scripts/figure_check.py')
figure=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(figure)


class OptionalFigureDesignTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);(self.root/'config').mkdir()
        self.style=self.root/'config/figure-style.json'
        self.style.write_text(json.dumps({'format_version':2,'minimum_final_glyph_pt':12}),encoding='utf-8')
        self.ref={'path':'config/figure-style.json','version':1,'sha256':figure.digest(self.style)}

    def panel(self,**changes):
        return {'panel':'a','question':'How much does the solver deviate?',
                'evidence_role':'reference-error comparison','input_fields':['time','absolute_error'],
                'main_takeaway':'The deviation grows under the same step size.',**changes}

    def style_contract(self):
        return {'style_config_ref':copy.deepcopy(self.ref),'data_inputs':[copy.deepcopy(self.ref)]}

    def test_legacy_omitted_null_and_empty_panel_contracts_are_compatible(self):
        for contract in [{},{'panel_plan':None,'style_config_ref':None},{'panel_plan':[]}]:
            with self.subTest(contract=contract):self.assertEqual(figure.check_optional_design(self.root,contract),[])

    def test_declared_panels_accept_complementary_roles_and_schematic_empty_fields(self):
        contract={'panel_plan':[self.panel(),self.panel(panel='b',question='What is transferred?',
                    evidence_role='interface schematic',input_fields=[],main_takeaway='State and uncertainty feed the next question.')]}
        self.assertEqual(figure.check_optional_design(self.root,contract),[])

    def test_malformed_panel_container_or_nonobject_is_rejected(self):
        for panels in ['a',{},[None],['a']]:
            with self.subTest(panels=panels):self.assertTrue(figure.check_optional_design(self.root,{'panel_plan':panels}))

    def test_panel_has_to_explain_question_evidence_and_takeaway(self):
        for key in ['panel','question','evidence_role','main_takeaway']:
            for invalid in [None,' ',3]:
                with self.subTest(key=key,invalid=invalid):
                    errors=figure.check_optional_design(self.root,{'panel_plan':[self.panel(**{key:invalid})]})
                    self.assertTrue(any(key in error for error in errors))

    def test_duplicate_panel_identifiers_are_not_silently_merged(self):
        errors=figure.check_optional_design(self.root,{'panel_plan':[self.panel(),self.panel(panel=' a ')]})
        self.assertTrue(any('duplicates' in error for error in errors))

    def test_input_fields_cannot_be_a_string_or_contain_empty_labels(self):
        for invalid in [None,'time',[''],[1]]:
            with self.subTest(invalid=invalid):
                self.assertTrue(figure.check_optional_design(self.root,{'panel_plan':[self.panel(input_fields=invalid)]}))

    def test_current_style_requires_the_same_fixed_task_input(self):
        self.assertEqual(figure.check_optional_design(self.root,self.style_contract()),[])
        for change in ['missing','version','hash']:
            contract=self.style_contract()
            if change=='missing':contract['data_inputs']=[]
            elif change=='version':contract['data_inputs'][0]['version']=2
            else:contract['data_inputs'][0]['sha256']='0'*64
            with self.subTest(change=change):
                self.assertTrue(any('same fixed' in error for error in figure.check_optional_design(self.root,contract)))

    def test_current_style_byte_change_is_detected(self):
        contract=self.style_contract();self.style.write_text('{"minimum_final_glyph_pt":14}',encoding='utf-8')
        errors=figure.check_optional_design(self.root,contract)
        self.assertTrue(any('missing or changed' in error for error in errors))

    def test_another_style_file_cannot_replace_the_project_style(self):
        other=self.root/'config/other.json';other.write_bytes(self.style.read_bytes())
        ref={**self.ref,'path':'config/other.json'}
        errors=figure.check_optional_design(self.root,{'style_config_ref':ref,'data_inputs':[copy.deepcopy(ref)]})
        self.assertTrue(any('project config/figure-style.json' in error for error in errors))

    def test_style_paths_cannot_escape_the_project(self):
        for path in ['../figure-style.json',str(self.style.resolve())]:
            ref={**self.ref,'path':path}
            with self.subTest(path=path):
                self.assertTrue(any('escapes project' in error for error in figure.check_optional_design(self.root,{'style_config_ref':ref,'data_inputs':[ref]})))

    def test_artifact_version_is_not_a_truthy_flag_or_format_version(self):
        for invalid in [True,False,0,-1,'1',None]:
            ref={**self.ref,'version':invalid}
            with self.subTest(invalid=invalid):
                self.assertTrue(any('artifact version' in error for error in figure.check_optional_design(self.root,{'style_config_ref':ref,'data_inputs':[ref]})))

    def test_style_ref_needs_a_digest_and_reference_object(self):
        self.assertTrue(figure.check_optional_design(self.root,{'style_config_ref':'config/figure-style.json'}))
        for sha in [None,'abc','G'*64,self.ref['sha256'].upper()]:
            ref={**self.ref,'sha256':sha}
            with self.subTest(sha=sha):
                self.assertTrue(any('SHA256' in error for error in figure.check_optional_design(self.root,{'style_config_ref':ref,'data_inputs':[ref]})))

    def test_structurally_valid_plan_never_creates_visual_approval(self):
        result=figure.check_contract(self.root,{'panel_plan':[self.panel()]})
        self.assertEqual(result['design_metadata_status'],'valid')
        self.assertEqual(result['visual_status'],'pending')
        self.assertIn('aesthetics remain unassessed',result['design_metadata_scope'])
        self.assertFalse(result['ok'],'A design plan cannot replace the actual figure files and contract.')

    def test_invalid_design_is_included_in_the_existing_contract_errors(self):
        result=figure.check_contract(self.root,{'panel_plan':[self.panel(),self.panel()]})
        self.assertFalse(result['ok']);self.assertEqual(result['design_metadata_status'],'invalid')
        self.assertTrue(any('duplicates' in error for error in result['errors']))


if __name__=='__main__':unittest.main()
