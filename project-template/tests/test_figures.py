import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('figure_checks',ROOT/'scripts/figure_check.py')
figure=importlib.util.module_from_spec(spec);spec.loader.exec_module(figure)

def text_pdf(path,size=12,x=50,y=150,width=300,height=200):
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject
    writer=PdfWriter();page=writer.add_blank_page(width=width,height=height)
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
    stream=DecodedStreamObject();stream.set_data(f'BT /F1 {size} Tf {x} {y} Td (Synthetic text) Tj ET'.encode('ascii'))
    page[NameObject('/Contents')]=writer._add_object(stream)
    with Path(path).open('wb') as f:writer.write(f)

class FigureChecks(unittest.TestCase):
    def test_small_final_font_is_blocked(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'figure.pdf';text_pdf(p,size=8)
            self.assertFalse(figure.audit_pdf(p)['ok'])
    def test_insertion_scale_is_included_in_font_floor(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'figure.pdf';text_pdf(p,size=16)
            r=figure.audit_pdf(p,{'width':300/72*25.4/2,'height':200/72*25.4/2})
            self.assertFalse(r['ok']);self.assertAlmostEqual(r['minimum_final_font_pt'],8)
    def test_visible_origin_outside_cropbox_is_blocked(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'figure.pdf';text_pdf(p,x=400)
            self.assertTrue(any('CropBox' in x for x in figure.audit_pdf(p)['errors']))
    def test_valid_font_does_not_claim_visual_pass(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'figure.pdf';text_pdf(p)
            r=figure.audit_pdf(p);self.assertTrue(r['ok']);self.assertEqual(r['visual_status'],'pending')
    def test_data_hash_drift_and_template_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);p=root/'data.csv';p.write_text('x,y\n1,2\n')
            c={'_template_only':True,'data_inputs':[{'path':'data.csv','sha256':figure.digest(p)}]}
            p.write_text('x,y\n1,99\n')
            r=figure.check_contract(root,c)
            self.assertFalse(r['ok']);self.assertTrue(any('changed' in x for x in r['errors']))
    def test_qa_readback_and_source_hash_are_enforced(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'draw.py').write_text('# source')
            c={'figure_id':'F1','argument_sentence':'A claim','figure_type':'schematic','transformation':'None',
               'caption_english':'A caption','script_path':'draw.py','script_sha256':figure.digest(root/'draw.py'),
               'size_mm':{'width':100,'height':70},'skill_read':[{'document':'local guidance'}],
               'skill_executed':[{'status':'passed','output_refs':[{'path':'missing.json','sha256':'x'}]}]}
            r=figure.check_contract(root,c);self.assertFalse(r['ok']);self.assertTrue(any('QA readback' in x for x in r['errors']))
    def test_low_resolution_png_is_blocked(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);p=root/'chart.png';Image.new('RGB',(300,200),'white').save(p,dpi=(72,72))
            c={'outputs':[{'path':'chart.png','sha256':figure.digest(p)}]}
            result=figure.check_contract(root,c)
            self.assertFalse(result['ok'])
            self.assertTrue(any('300dpi' in x for x in result['errors']))
    def test_demo_numerics_are_actual_and_deterministic(self):
        spec=importlib.util.spec_from_file_location('figure_demo',ROOT/'scripts/figure_demo.py')
        demo=importlib.util.module_from_spec(spec);spec.loader.exec_module(demo)
        rows=demo.demo_rows();self.assertEqual(rows,demo.demo_rows());self.assertEqual(len(rows),41)
        self.assertLess(max(abs(x['rk4']-x['exact']) for x in rows),1e-5)
        self.assertTrue(all(x['p10']<=x['exact']<=x['p90'] for x in rows))

    def test_double_panel_template_has_equal_rendered_widths(self):
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        spec=importlib.util.spec_from_file_location('figure_demo',ROOT/'scripts/figure_demo.py')
        demo=importlib.util.module_from_spec(spec);spec.loader.exec_module(demo)
        fig,axes=demo.new_plot_canvas({'final_width_mm':165.1},panels=2)
        try:
            fig.canvas.draw();bounds=[ax.get_window_extent().bounds for ax in axes]
            self.assertEqual(len(bounds),2)
            self.assertAlmostEqual(bounds[0][0],bounds[1][0])
            self.assertAlmostEqual(bounds[0][2],bounds[1][2])
            self.assertAlmostEqual(bounds[0][3],bounds[1][3])
        finally:plt.close(fig)

if __name__=='__main__':unittest.main()
