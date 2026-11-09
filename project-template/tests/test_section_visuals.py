import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('section_visuals',Path(__file__).parents[1]/'scripts/section_visuals.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)

class SectionVisualTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        for d in ('config','paper','figures'):(self.root/d).mkdir()
        (self.root/'config/runtime.json').write_text('{"require_section_visual_coverage":true}')
        (self.root/'paper/s.tex').write_text('\\section{Results}\\label{sec:r} See Figure~\\ref{fig:r}.\\label{fig:r}')
        (self.root/'figures/r.svg').write_text('<svg/>')
        def ref(p):return {'path':p,'sha256':hashlib.sha256((self.root/p).read_bytes()).hexdigest()}
        self.row={'section_id':'sec:r','title':'Results','conclusion':'A exceeds B','visual_required':True,'section_source':ref('paper/s.tex'),'visual_refs':[dict(ref('figures/r.svg'),kind='figure',label='fig:r',caption='A compared with B') ]}

    def check(self,rows=None):
        (self.root/'paper/section-visual-map.json').write_text(json.dumps({'sections':rows if rows is not None else [self.row]}))
        return mod.audit(self.root)

    def test_bound_conclusion(self):self.assertTrue(self.check()['ok'])
    def test_missing_visual(self):self.row['visual_refs']=[];self.assertFalse(self.check()['ok'])
    def test_changed_bytes(self):(self.root/'figures/r.svg').write_text('changed');self.assertFalse(self.check()['ok'])
    def test_missing_caption(self):self.row['visual_refs'][0]['caption']='';self.assertFalse(self.check()['ok'])
    def test_missing_anchor(self):self.row['visual_refs'][0]['label']='fig:missing';self.assertFalse(self.check()['ok'])
    def test_reasoned_exception(self):self.row.update(visual_required=False,reason_without_visual='Definitions only');self.assertTrue(self.check()['ok'])
    def test_unexplained_exception(self):self.row.update(visual_required=False);self.assertFalse(self.check()['ok'])
    def test_empty_codex_map(self):self.assertFalse(self.check([])['ok'])
    def test_old_project_compatible(self):(self.root/'config/runtime.json').write_text('{}');self.assertTrue(mod.audit(self.root)['ok'])
    def test_aesthetic_not_auto_certified(self):self.assertEqual(self.check()['aesthetic_status'],'not_assessed')

if __name__=='__main__':unittest.main()
