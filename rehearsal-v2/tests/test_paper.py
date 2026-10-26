import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SOURCE=Path(__file__).resolve().parents[1]/'scripts/paper.py'
spec=importlib.util.spec_from_file_location('paper_tools',SOURCE)
paper=importlib.util.module_from_spec(spec);spec.loader.exec_module(paper)

def text_pdf(path,text='Team 1234567  Page 1  Summary Sheet',crop=None):
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject,NameObject,NumberObject,DecodedStreamObject
    writer=PdfWriter();p=writer.add_blank_page(width=612,height=792)
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    p[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
    stream=DecodedStreamObject();stream.set_data(f'BT /F1 12 Tf 50 700 Td ({text}) Tj ET'.encode('ascii'))
    p[NameObject('/Contents')]=writer._add_object(stream)
    if crop:p.cropbox.upper_right=crop
    with open(path,'wb') as out:writer.write(out)

class PaperChecks(unittest.TestCase):
    def test_pending_result_marker_is_content_failure(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'unfinished.pdf';text_pdf(p,'Team 1234567 Summary Sheet RESULT PENDING no_run_yet')
            self.assertTrue(paper.audit_pdf(p,1)['mechanical_passed'])
            self.assertFalse(paper.audit_pdf(p,1,release=True)['mechanical_passed'])
    def test_cropped_text_rejected_even_when_pdf_is_readable(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'clipped.pdf';text_pdf(p,crop=(612,650))
            r=paper.audit_pdf(p,1)
            self.assertFalse(r['mechanical_passed'])
            self.assertTrue(any('CropBox' in e for e in r['errors']))
    def test_template_team_and_demo_not_release_ready(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'demo.pdf';text_pdf(p,'Team 0000000 Summary Sheet Demonstration only')
            self.assertTrue(paper.audit_pdf(p,1)['mechanical_passed'])
            self.assertFalse(paper.audit_pdf(p,1,release=True)['mechanical_passed'])
    def test_page_limit_excludes_only_confirmed_ai_boundary(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'one.pdf';text_pdf(p)
            self.assertTrue(paper.audit_pdf(p,1)['mechanical_passed'])
            self.assertFalse(paper.audit_pdf(p,26)['mechanical_passed'])
    def test_boundary_cannot_be_guessed(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'main.aux';p.write_text('')
            with self.assertRaises(ValueError):paper.main_report_pages(p,26)
            p.write_text('\\newlabel{main-report-end}{{5}{24}{}{section.5}{}}')
            self.assertEqual(paper.main_report_pages(p,26),24)
    def test_pdf_and_source_drift_detected(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'paper').mkdir();tex=root/'paper/main.tex';tex.write_text('approved source')
            p=root/'main.pdf';text_pdf(p)
            manifest={'main_report_pages':1,'source_hashes':paper.sources(root),'pdf_sha256':paper.digest(p),'warnings':[]}
            p.with_suffix('.build.json').write_text(json.dumps(manifest))
            self.assertTrue(paper.check(root,p)['mechanical_passed'])
            tex.write_text('changed source')
            self.assertFalse(paper.check(root,p)['mechanical_passed'])

    def visual_fixture(self,root):
        # Test-only records exercise validation; never production attestations.
        p=root/'main.pdf';text_pdf(p);renders=root/'renders';renders.mkdir();png=renders/'page-1.png';png.write_bytes(b'test-only-render')
        manifest={'rendered_pages':['renders/page-1.png'],'rendered_page_sha256':{'renders/page-1.png':paper.digest(png)},'paper_author_agent_ids':['fixture-author']}
        p.with_suffix('.build.json').write_text(json.dumps(manifest))
        attestation={'status':'passed','reviewer_agent_id':'fixture-independent','reviewed_at':'fixture-time','pdf_sha256':paper.digest(p),
            'build_manifest_sha256':paper.digest(p.with_suffix('.build.json')),'pages':[{'path':'renders/page-1.png','sha256':paper.digest(png),
            'checks':{x:True for x in ('no_clipping','no_overlap','readable_text','readable_figures','consistent_headers','readable_equations','figure_font_at_final_size')}}]}
        review=root/'review.json';review.write_text(json.dumps(attestation));return p,png,manifest,attestation,review

    def test_visual_missing_page_failed_check_and_author_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);p,png,m,a,r=self.visual_fixture(root)
            self.assertTrue(paper.visual_review_report(root,p,m,r)['ok'])
            a['pages']=[];r.write_text(json.dumps(a));self.assertFalse(paper.visual_review_report(root,p,m,r)['ok'])
            p,png,m,a,r=self.visual_fixture_after_reset(root)
            a['pages'][0]['checks']['readable_equations']=False;r.write_text(json.dumps(a));self.assertFalse(paper.visual_review_report(root,p,m,r)['ok'])
            a['pages'][0]['checks']['readable_equations']=True;a['reviewer_agent_id']='fixture-author';r.write_text(json.dumps(a));self.assertFalse(paper.visual_review_report(root,p,m,r)['ok'])

    def visual_fixture_after_reset(self,root):
        import shutil
        shutil.rmtree(root/'renders');return self.visual_fixture(root)

    def test_visual_render_hash_or_build_change_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);p,png,m,a,r=self.visual_fixture(root)
            png.write_bytes(b'changed-render');self.assertFalse(paper.visual_review_report(root,p,m,r)['ok'])
            p,png,m,a,r=self.visual_fixture_after_reset(root)
            p.with_suffix('.build.json').write_text('{}');self.assertFalse(paper.visual_review_report(root,p,m,r)['ok'])

    def test_legend_overlap_and_small_final_figure_cannot_pass_visual_review(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);p,png,m,a,r=self.visual_fixture(root)
            for failed_check in ('no_overlap','figure_font_at_final_size','no_clipping'):
                with self.subTest(failed_check=failed_check):
                    a['pages'][0]['checks'][failed_check]=False
                    r.write_text(json.dumps(a))
                    result=paper.visual_review_report(root,p,m,r)
                    self.assertFalse(result['ok'])
                    self.assertTrue(any(failed_check in error for error in result['errors']))
                    a['pages'][0]['checks'][failed_check]=True

    def test_unknown_paper_authors_cannot_claim_independent_review(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);p,png,m,a,r=self.visual_fixture(root)
            m['paper_author_agent_ids']=[]
            self.assertFalse(paper.visual_review_report(root,p,m,r)['ok'])

    def test_declared_figure_contract_cannot_silently_change(self):
        with tempfile.TemporaryDirectory() as t:
            import shutil
            root=Path(t);(root/'paper').mkdir();(root/'scripts').mkdir()
            shutil.copy2(SOURCE.parent/'figure_check.py',root/'scripts/figure_check.py')
            contract=root/'figure.json';contract.write_text('{}')
            refs=[{'figure_id':'F1','contract_ref':{'path':'figure.json','sha256':paper.digest(contract)}}]
            (root/'paper/paper-plan.json').write_text(json.dumps({'figures':refs}))
            contract.write_text('{"changed":true}')
            result=paper.check_paper_figures(root,{'figure_refs':refs})
            self.assertFalse(result['ok'])
            self.assertTrue(any('contract missing or changed' in x for x in result['errors']))

    def test_no_result_manifest_cannot_satisfy_release(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertFalse(paper.check_paper_results(Path(t),{})['ok'])

if __name__=='__main__':unittest.main()
