"""Structural, font-size and export checks for original schematic recipes."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from PIL import Image
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'skill-overlays/nature-figure/scripts/mcm-schematics.py'
SPEC=importlib.util.spec_from_file_location('mcm_schematics_test',SOURCE)
m=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(m)
STYLE=ROOT/'bundle/src/figure-style.json'


class SchematicRecipes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='mcm-schematic-test-')
        cls.base=Path(cls.temp.name)
        cls.maps={name:m.export(name,cls.base/name,STYLE) for name in m.RECIPES}

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def test_classification_links_are_not_causal_arrows(self):
        graph=m.topology('taxonomy');m.validate_topology(graph)
        self.assertEqual(len(graph['edges']),9)
        self.assertTrue(all(not e['directed'] for e in graph['edges']))
        graph['edges'][0]['directed']=True
        with self.assertRaisesRegex(ValueError,'Classification'):m.validate_topology(graph)

    def test_shared_input_and_weights_bind_to_actual_candidate_branches(self):
        graph=m.topology('ensemble');m.validate_topology(graph)
        shared=[(e['source'],e['target']) for e in graph['edges'] if e['kind']=='shared_input']
        weighted=[e for e in graph['edges'] if e['kind']=='weighted_prediction']
        self.assertEqual(shared,[('input','a'),('input','b'),('input','c')])
        self.assertEqual([(e['source'],e['target'],e['weight']) for e in weighted],
                         [('a','mix',.5),('b','mix',.3),('c','mix',.2)])
        self.assertTrue(all(e['directed'] for e in graph['edges']))
        for invalid in [float('nan'),-.1,True,.8]:
            broken=copy.deepcopy(graph)
            next(e for e in broken['edges'] if e['kind']=='weighted_prediction')['weight']=invalid
            with self.assertRaisesRegex(ValueError,'weights'):m.validate_topology(broken)

    def test_constraint_gate_only_processes_actions(self):
        graph=m.topology('feedback');m.validate_topology(graph)
        observations=[e for e in graph['edges'] if e['kind'] in ('observed_state','measured_feedback')]
        self.assertEqual([(e['source'],e['target']) for e in observations],[('environment','agent')]*2)
        observations[0]['target']='gate'
        with self.assertRaisesRegex(ValueError,'gate'):m.validate_topology(graph)

    def test_invalid_identity_and_edge_endpoint_are_refused(self):
        graph=m.topology('ensemble');graph['edges'][0]['target']='not-a-node'
        with self.assertRaisesRegex(ValueError,'endpoint'):m.validate_topology(graph)
        graph=m.topology('ensemble');graph['nodes'].append(graph['nodes'][0])
        with self.assertRaisesRegex(ValueError,'unique'):m.validate_topology(graph)

    def test_actual_layout_checks_are_clean_and_all_labels_are_editable_svg_text(self):
        for name,graph in self.maps.items():
            self.assertTrue(graph['geometry_check']['passed'])
            self.assertEqual(graph['geometry_check']['errors'],[])
            tree=ET.parse(self.base/name/(name+'.svg'))
            visible=' '.join(' '.join(tree.getroot().itertext()).split())
            for node in graph['nodes']:
                self.assertIn(' '.join(node['label'].split()),visible)
            self.assertIn('Synthetic schematic',visible)

    def test_exports_have_actual_final_size_minimum_glyph_and_300dpi(self):
        for name,graph in self.maps.items():
            with Image.open(self.base/name/(name+'.png')) as image:
                self.assertEqual(image.size,(round(graph['final_width_mm']/25.4*300),round(graph['final_height_mm']/25.4*300)))
                self.assertAlmostEqual(image.info['dpi'][0],300,places=2)
            page=PdfReader(self.base/name/(name+'.pdf')).pages[0]
            self.assertAlmostEqual(float(page.mediabox.width)/72*25.4,graph['final_width_mm'],places=2)
            self.assertAlmostEqual(float(page.mediabox.height)/72*25.4,graph['final_height_mm'],places=2)
            sizes=[]
            def visit(text,cm,tm,font,size):
                if text.strip():sizes.append(float(size))
            page.extract_text(visitor_text=visit)
            self.assertTrue(sizes)
            self.assertGreaterEqual(min(sizes),12-.001)

    def test_files_and_fixed_topology_are_bound_to_true_hashes(self):
        for name,graph in self.maps.items():
            self.assertEqual(graph['script_sha256'],m.digest(SOURCE))
            self.assertEqual(graph['style_sha256'],m.digest(STYLE))
            for relative,sha in graph['files'].items():
                self.assertEqual(sha,m.digest(self.base/name/relative))
            self.assertTrue(graph['synthetic'])
            self.assertEqual(graph['visual_review']['status'],'pending')

    def test_existing_output_is_preserved(self):
        path=self.base/'occupied';path.mkdir();sentinel=path/'keep.txt';sentinel.write_bytes(b'keep')
        with self.assertRaisesRegex(ValueError,'already exists'):m.export('feedback',path,STYLE)
        self.assertEqual(sentinel.read_bytes(),b'keep')

    def test_compact_examples_retain_readable_labels_without_presentation_sized_canvas(self):
        for name,graph in self.maps.items():
            self.assertLessEqual(graph['final_height_mm'],100)
            self.assertEqual(graph['minimum_core_font_pt'],12)
            self.assertEqual(graph['geometry_check']['errors'],[])
            self.assertIn('compact scientific schematic',graph['presentation_profile'])


if __name__=='__main__':unittest.main()
