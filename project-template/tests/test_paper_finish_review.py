"""Independent fault tests for the bounded layout finalizer.

The TeX compiler and renderer are intentionally synthetic fixtures. These tests
audit control decisions, never certify real TeX output or visual quality.
"""
import importlib.util
import json
import os
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import patch


AUTHOR_TEST = Path(__file__).with_name('test_paper_finish.py')
SPEC = importlib.util.spec_from_file_location('paper_finish_review_fixtures', AUTHOR_TEST)
fixtures = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixtures)
finish = fixtures.finish


def append_pdf_text(path, text, size):
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import DecodedStreamObject, NameObject
    writer = PdfWriter(clone_from=PdfReader(path))
    page = writer.pages[0]
    previous = page.get_contents().get_data()
    stream = DecodedStreamObject()
    stream.set_data(previous + f'\nBT /F1 {size} Tf 25 640 Td ({text}) Tj ET'.encode('ascii'))
    page[NameObject('/Contents')] = writer._add_object(stream)
    with path.open('wb') as target:
        writer.write(target)


class FinalFontCompiler(fixtures.FixtureCompiler):
    def run(self, command, working, env, controls):
        result = super().run(command, working, env, controls)
        if command[0] != 'fixture-renderer':
            append_pdf_text(working / 'out/main.pdf', 'Tiny figure axis label', 5)
        return result


class CorruptRenderer(fixtures.FixtureCompiler):
    def run(self, command, working, env, controls):
        result = super().run(command, working, env, controls)
        if command[0] == 'fixture-renderer':
            Path(command[-1] + '-1.png').write_bytes(b'\x89PNG\r\n\x1a\n' + b'not-a-valid-image' * 2)
        return result


class TwoPageCompiler(fixtures.FixtureCompiler):
    def run(self, command, working, env, controls):
        result = super().run(command, working, env, controls)
        if command[0] != 'fixture-renderer':
            from pypdf import PdfReader, PdfWriter
            path = working / 'out/main.pdf'
            reader = PdfReader(path)
            writer = PdfWriter()
            writer.add_page(reader.pages[0])
            writer.add_page(reader.pages[0])
            with path.open('wb') as target:
                writer.write(target)
        return result


class IndependentFinishReview(unittest.TestCase):
    setUp = fixtures.FinishLoopChecks.setUp
    execute = fixtures.FinishLoopChecks.execute

    def normal_width(self):
        self.tex.write_bytes(self.tex.read_bytes().replace(b'width=1.2\\linewidth', b'width=\\linewidth'))

    def test_scientific_bytes_and_original_registry_remain_unchanged(self):
        payload = (r'Fixed observations: $x_{i+1}=2.99792458\times 10^8 x_i-\alpha_i$, '
                   r'$\Delta E=-1.25\times10^{-7}$; confidence=0.975, seed=20261113.' + '\r\n')
        source = finish.read_tex(self.tex).replace(r'\end{document}', payload + r'\end{document}')
        self.tex.write_text(source, encoding='utf-8', newline='')
        before = self.tex.read_bytes()
        registry = (self.root / '.mcm/artifacts.json').read_bytes()
        result = self.execute()
        candidate = self.output / result['candidate'] / 'paper/main.tex'
        self.assertEqual(candidate.read_bytes(), before.replace(b'width=1.2\\linewidth', b'width=\\linewidth'))
        self.assertEqual(self.tex.read_bytes(), before)
        self.assertEqual((self.root / '.mcm/artifacts.json').read_bytes(), registry)
        self.assertFalse(result['human_release_approved'])
        self.assertFalse(result['release_ready'])
        self.assertEqual(result['visual_review_status'], 'pending')

    def test_verbatim_code_example_is_neither_repaired_nor_probed(self):
        literal = (r'\begin{verbatim}' + '\n' + r'\begin{figure}\centering' + '\n' +
                   r'\includegraphics[width=1.2\linewidth]{../figures/chart.pdf}' + '\n' +
                   r'\caption{A source-code example}\end{figure}' + '\n' + r'\end{verbatim}')
        self.tex.write_text(r'\documentclass{article}\begin{document}' + '\n' + literal + '\n' + r'\end{document}', encoding='utf-8')
        audit = finish.audit_sources(self.root, 'main')
        self.assertEqual(audit['insertions'], [], 'Verbatim code must not be treated as an executed insertion')

    def test_inline_verb_example_is_neither_repaired_nor_probed(self):
        self.normal_width()
        source = finish.read_tex(self.tex).replace(r'\end{document}',
            r'\verb|\includegraphics[width=1.2\linewidth]{../figures/chart.pdf}|' + '\n' + r'\end{document}')
        self.tex.write_text(source, encoding='utf-8', newline='')
        self.assertEqual(finish.audit_sources(self.root, 'main')['insertions'], [])

    def test_final_pdf_tiny_text_cannot_receive_mechanical_pass(self):
        self.normal_width()
        result = self.execute(FinalFontCompiler())
        self.assertFalse(result['mechanical_passed'], 'A known 5pt figure label in the final PDF must remain an open defect')
        self.assertTrue(result.get('fix_queue'))

    def test_corrupt_png_with_valid_signature_is_not_a_complete_render(self):
        self.normal_width()
        result = self.execute(CorruptRenderer())
        self.assertFalse(result['mechanical_passed'], 'A signature alone must not certify a decodable rendered page')

    def test_all_pdf_pages_require_rendering_including_ai_or_appendix(self):
        self.normal_width()
        result = self.execute(TwoPageCompiler())
        self.assertFalse(result['mechanical_passed'])
        self.assertTrue(any('Rendered page count' in x['detail'] for x in result['fix_queue']))

    def test_open_reference_queue_does_not_become_pass_after_width_fix(self):
        self.tex.write_text(finish.read_tex(self.tex).replace(r'\end{document}', r'\ref{unresolved-science}\end{document}'), encoding='utf-8', newline='')
        result = self.execute()
        self.assertFalse(result['mechanical_passed'])
        self.assertTrue(any(x['kind'] == 'missing_reference' and x['status'] == 'open' for x in result['fix_queue']))
        self.assertEqual(len(result['rounds']), 2)

    def test_changed_figure_invalidates_width_proof_before_copy(self):
        audit = finish.audit_sources(self.root, 'main')
        probes = {item['id']: {'linewidth_pt': 420.0, 'textwidth_pt': 420.0} for item in audit['insertions']}
        changes, queue = finish.safe_repairs(self.root, audit, {'width_probes': probes})
        self.assertTrue(changes)
        self.assertEqual(queue, [])
        figure = self.root / 'figures/chart.pdf'
        figure.write_bytes(figure.read_bytes() + b'\n% changed after font proof\n')
        with self.assertRaisesRegex(ValueError, 'Figure changed'):
            finish.apply_repairs(self.root, self.output, changes)
        self.assertFalse(self.output.exists())

    def test_real_subprocess_stops_when_time_budget_expires(self):
        controls = finish.Controls(self.root, None, 1)
        started = time.monotonic()
        with self.assertRaisesRegex(finish.StopWork, 'time budget'):
            finish.run_command([sys.executable, '-c', 'import time; time.sleep(10)'],
                               self.root, os.environ.copy(), controls)
        self.assertLess(time.monotonic() - started, 5)

    def test_real_subprocess_stops_on_runtime_pause(self):
        runtime = self.root / 'config/runtime.json'
        controls = finish.Controls(self.root, None, 8)
        timer = threading.Timer(.35, lambda: runtime.write_text('{"paused":true}', encoding='utf-8'))
        timer.start()
        self.addCleanup(timer.cancel)
        started = time.monotonic()
        with self.assertRaisesRegex(finish.StopWork, 'pause'):
            finish.run_command([sys.executable, '-c', 'import time; time.sleep(10)'],
                               self.root, os.environ.copy(), controls)
        self.assertLess(time.monotonic() - started, 5)

    def test_custom_literal_declaration_in_child_disables_whole_closure(self):
        child = self.root / 'paper/literal-config.tex'
        child.write_text(r'\newmintinline[showtex]{tex}{}', encoding='utf-8')
        self.tex.write_text(finish.read_tex(self.tex).replace(r'\begin{document}',
            r'\input{literal-config}\begin{document}'), encoding='utf-8', newline='')
        before = self.tex.read_bytes()
        audit = finish.audit_sources(self.root, 'main')
        self.assertTrue(audit['probes_disabled_for_literal_uncertainty'])
        self.assertEqual(audit['graphics'], [])
        self.assertEqual(audit['insertions'], [])
        result = self.execute()
        self.assertFalse(result['mechanical_passed'])
        self.assertTrue(any(x['kind'] == 'unsupported_literal_syntax' for x in result['fix_queue']))
        report = json.loads((self.output / 'round-001.json').read_text(encoding='utf-8'))
        self.assertEqual(report['build']['compile_inputs']['instrumented_source_refs'], {})
        self.assertEqual((self.output / 'candidate-v001/paper/main.tex').read_bytes(), before)
        self.assertEqual((self.output / 'candidate-v001/paper/literal-config.tex').read_bytes(), child.read_bytes())

    def test_mathematical_scripts_only_request_context_review(self):
        class MathScriptCompiler(fixtures.FixtureCompiler):
            def run(self, command, working, env, controls):
                result = super().run(command, working, env, controls)
                if command[0] != 'fixture-renderer':
                    append_pdf_text(working / 'out/main.pdf', 'i', 7)
                return result

        self.normal_width()
        self.tex.write_text(finish.read_tex(self.tex).replace(r'\end{document}',
            r'Necessary mathematics: $x_i^2=2.99792458\times10^8$.\end{document}'), encoding='utf-8', newline='')
        before = self.tex.read_bytes()
        result = self.execute(MathScriptCompiler())
        rows = [x for x in result['fix_queue'] if x['kind'] == 'small_text_context_review']
        self.assertTrue(rows)
        self.assertTrue(all(not x['automatic_fix'] and x['status'] == 'open' for x in rows))
        self.assertTrue(all('superscripts/subscripts' in x['detail'] for x in rows))
        self.assertTrue(all('Do not automatically enlarge equations' in x['constraint'] for x in rows))
        self.assertEqual((self.output / 'candidate-v001/paper/main.tex').read_bytes(), before)
        self.assertEqual(self.tex.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
