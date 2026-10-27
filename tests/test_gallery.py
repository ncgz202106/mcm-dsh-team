"""Numeric semantics and fixed-artifact integrity; no aesthetic approval."""
import hashlib,importlib.util,json,math,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('mcm_figure_gallery',ROOT/'tools/figure-gallery.py')
gallery=importlib.util.module_from_spec(spec);spec.loader.exec_module(gallery)

class GallerySemantics(unittest.TestCase):
    def test_paired_gain_uses_identical_scenarios_and_correct_sign(self):
        rows=gallery.synthetic_data()['comparison']
        self.assertEqual(len(rows),9)
        self.assertEqual(len({r['load_per_hour'] for r in rows}),9)
        for r in rows:
            self.assertAlmostEqual(r['delay_saved_min'],r['baseline_delay_min']-r['improved_delay_min'])
            self.assertGreater(r['delay_saved_min'],0)

    def test_failure_window_is_not_hidden_by_aggregate_trajectory(self):
        for r in gallery.synthetic_data()['forecast']:
            error=r['prediction_units']-r['reference_units']
            self.assertAlmostEqual(error,r['signed_error_units'])
            self.assertEqual(abs(error)>5,r['time_h']>=18)
            self.assertEqual(r['shift_window'],r['time_h']>=18)

    def test_action_boundary_follows_analytical_cost_crossing(self):
        p=14/9
        self.assertAlmostEqual(20+12*p,34+3*p)
        for r in gallery.synthetic_data()['sensitivity']:
            expected='A' if r['cost_A']<=r['cost_B'] else 'B'
            self.assertEqual(r['chosen_policy'],expected)
            self.assertEqual(r['chosen_policy']=='A',r['parameter']<=p)

    def test_uncertainty_sources_have_correct_bounds_and_probability(self):
        data=gallery.synthetic_data()
        for row in data['envelope']:
            self.assertLessEqual(row['lower_units'],row['center_units'])
            self.assertLessEqual(row['center_units'],row['upper_units'])
            self.assertAlmostEqual(row['lower_units'],100*math.exp(-.25*row['time_h']))
        z=1.6448536269514722
        self.assertAlmostEqual(math.erf(z/math.sqrt(2)),.9,places=12)
        for r in data['density']:
            self.assertEqual(r['inside_model_90pct_PI'],6-z*1.2<=r['response_units']<=6+z*1.2)
        spec=next(x for x in gallery.family_specs() if x['id']=='05-uncertainty-semantics')
        self.assertIn('not empirical coverage',spec['caption'])
        self.assertIn('no probability',spec['panels'][0][4].lower().replace('has no assigned coverage probability','has no probability'))

    def test_discrete_frontier_and_budget_selection_are_independently_recomputed(self):
        rows=gallery.synthetic_data()['decisions']
        for r in rows:
            dominated=any(s['cost_units']<=r['cost_units'] and s['effect_units']>=r['effect_units'] and (s['cost_units']<r['cost_units'] or s['effect_units']>r['effect_units']) for s in rows)
            self.assertEqual(r['frontier'],not dominated)
        best=max((r for r in rows if r['cost_units']<=25),key=lambda r:r['effect_units'])
        self.assertEqual(best['policy'],'D')
        self.assertEqual([r['policy'] for r in rows if r['selected']],['D'])

    def test_fixed_exports_contracts_and_final_dimensions(self):
        from PIL import Image
        out=ROOT/'gallery';manifest=json.loads((out/'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['status'],'mechanical_passed_visual_pending')
        self.assertEqual(manifest['visual_status'],'pending')
        self.assertEqual(len(manifest['figures']),6)
        self.assertEqual((out/'config/figure-style.json').read_bytes(),(ROOT/'bundle/src/figure-style.json').read_bytes())
        for f in manifest['figures']:
            contract=json.loads((out/f['contract']['path']).read_text(encoding='utf-8'))
            self.assertTrue(f['passed_mechanical'])
            self.assertTrue(contract['synthetic'])
            self.assertFalse(contract['qa_readback']['visual_reviewed'])
            for artifact in contract['data_inputs']+contract['outputs']:
                path=out/artifact['path'];self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),artifact['sha256'])
                if path.suffix=='.png':
                    with Image.open(path) as im:
                        dpi=im.info['dpi'];self.assertGreaterEqual(min(dpi),299)
                        self.assertAlmostEqual(im.width/dpi[0]*25.4,contract['size_mm']['width'],delta=.15)
                        self.assertAlmostEqual(im.height/dpi[1]*25.4,contract['size_mm']['height'],delta=.15)

    def test_six_pages_cover_four_types_without_claiming_visual_approval(self):
        import fitz
        out=ROOT/'gallery';report=json.loads((out/'pages/build-report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['page_count'],6);self.assertEqual(report['warnings'],[])
        self.assertEqual(report['visual_status'],'pending');self.assertFalse(report['human_approval'])
        self.assertEqual([x['exit_code'] for x in report['commands']],[0,0])
        with fitz.open(out/'pages/page-examples.pdf') as pdf:
            text='\n'.join(page.get_text() for page in pdf)
            for kind in ['Model page:','Result page:','Sensitivity page:','Decision page:']:self.assertIn(kind,text)
            for page in pdf:self.assertGreater(len(page.get_text().strip()),300)
        source=(out/'latex/page-examples.tex').read_text(encoding='utf-8')
        self.assertNotIn('resizebox',source);self.assertNotIn('scalebox',source)

    def test_method_arrowheads_survive_the_actual_pdf_rendering_path(self):
        import xml.etree.ElementTree as ET
        import fitz
        svg=ET.parse(ROOT/'gallery/figures/01-method-interface.svg').getroot()
        heads=svg.findall('{http://www.w3.org/2000/svg}polygon')
        self.assertEqual(len(heads),5)
        with fitz.open(ROOT/'gallery/figures/01-method-interface.pdf') as pdf:
            page=pdf[0];scale=page.rect.width/float(svg.attrib['viewBox'].split()[2])
            filled=[d for d in page.get_drawings() if d.get('fill') and max(d['fill'])-min(d['fill'])>.1]
            for head in heads:
                points=[list(map(float,pair.split(','))) for pair in head.attrib['points'].split()]
                expected=fitz.Rect(min(p[0] for p in points)*scale,min(p[1] for p in points)*scale,max(p[0] for p in points)*scale,max(p[1] for p in points)*scale)
                self.assertTrue(any(max(abs(d['rect'][i]-expected[i]) for i in range(4))<.05 for d in filled),head.attrib['id'])

if __name__=='__main__':unittest.main()
