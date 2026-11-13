"""Finish-loop regression tests. The compiler below is explicitly a fixture."""
import base64
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import re
import struct
import tempfile
import unittest
import zlib
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'scripts/paper_finish.py'
SPEC = importlib.util.spec_from_file_location('finish_loop_tests', SOURCE)
finish = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(finish)
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC')


def page_png(width, height):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    pixels = (b'\0' + b'\xff\xff\xff' * width) * height
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(pixels)) + chunk(b'IEND', b'')


def text_pdf(path, text, width=612, height=792, font_size=12):
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    writer = PdfWriter()
    page = writer.add_blank_page(width=width, height=height)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'),
                             NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
    stream = DecodedStreamObject()
    stream.set_data(f'BT /F1 {font_size} Tf 25 {height - 50} Td ({text}) Tj ET'.encode('ascii'))
    page[NameObject('/Contents')] = writer._add_object(stream)
    with path.open('wb') as output:
        writer.write(output)


class FixtureCompiler:
    """Creates a real PDF and real PNG while simulating only TeX execution."""
    def __init__(self, fail_round=None, missing_pdf=False, missing_render=False, mutate=None):
        self.fail_round = fail_round
        self.missing_pdf = missing_pdf
        self.missing_render = missing_render
        self.mutate = mutate
        self.render_count = 0
        self.commands = []

    def run(self, command, working, env, controls):
        controls.check()
        self.commands.append(command)
        if command[0] == 'fixture-renderer':
            self.render_count += 1
            if not self.missing_render:
                from pypdf import PdfReader
                import math
                page = PdfReader(command[-2]).pages[0]
                Path(command[-1] + '-1.png').write_bytes(page_png(math.ceil(float(page.mediabox.width) / 72 * 110),
                                                               math.ceil(float(page.mediabox.height) / 72 * 110)))
            return 0, 'SYNTHETIC renderer fixture'
        source = (working / 'main.tex').read_text(encoding='utf-8')
        if self.mutate:
            self.mutate()
            self.mutate = None
        out = working / 'out'
        if self.fail_round == self.render_count + 1:
            return 1, 'SYNTHETIC compiler fixture failure'
        probes = ''.join(f'MCMFINISHWIDTH:{identifier}:420.0pt:420.0pt\n' for identifier in re.findall(r'MCMFINISHWIDTH:([a-f0-9]+):', source))
        log = probes + ('Overfull \\hbox (84.0pt too wide) at lines 4--5\n' if '1.2\\linewidth' in source else '')
        (out / 'main.log').write_text(log, encoding='utf-8')
        (out / 'main.aux').write_text(r'\newlabel{main-report-end}{{1}{1}{}{section.1}{}}', encoding='utf-8')
        if not self.missing_pdf:
            text_pdf(out / 'main.pdf', 'Team 1234567 Summary Sheet Page 1')
        return 0, probes + 'SYNTHETIC compiler fixture; never an actual TeX verification'


class FinishLoopChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'project'
        (self.root / 'paper').mkdir(parents=True)
        (self.root / 'figures').mkdir()
        (self.root / 'config').mkdir()
        (self.root / '.mcm').mkdir()
        (self.root / '.mcm/artifacts.json').write_text('{"records":[]}', encoding='utf-8')
        (self.root / 'config/runtime.json').write_text('{}', encoding='utf-8')
        self.tex = self.root / 'paper/main.tex'
        self.tex.write_bytes((r'\documentclass{article}' + '\r\n' + r'\begin{document}' + '\r\n' +
                              r'\begin{figure}\centering' + '\r\n' + r'\includegraphics[width=1.2\linewidth]{../figures/chart.pdf}' + '\r\n' +
                              r'\caption{Evidence-based comparison}\label{fig:chart}\end{figure}' + '\r\n' +
                              r'\end{document}' + '\r\n').encode())
        text_pdf(self.root / 'figures/chart.pdf', 'Measured comparison', 400, 250, 18)
        self.output = self.base / 'finish-v001'

    def execute(self, compiler=None, **kwargs):
        compiler = compiler or FixtureCompiler()
        with (patch.object(finish, 'choose_tools', return_value=('xelatex', 'fixture-compiler', 'fixture-renderer')),
              patch.object(finish, 'run_command', side_effect=compiler.run)):
            return finish.finish(self.root, self.output, **kwargs)

    def test_actual_invalid_width_is_repaired_and_recompiled_in_new_copy(self):
        before = finish.snapshot(self.root)
        result = self.execute()
        self.assertEqual(result['status'], 'ready_for_independent_review')
        self.assertTrue(result['mechanical_passed'])
        self.assertEqual(len(result['rounds']), 2)
        self.assertEqual(finish.snapshot(self.root), before)
        first = (self.output / 'candidate-v001/paper/main.tex').read_bytes()
        second = (self.output / 'candidate-v002/paper/main.tex').read_bytes()
        self.assertIn(b'width=1.2\\linewidth', first)
        self.assertEqual(second, first.replace(b'width=1.2\\linewidth', b'width=\\linewidth'))
        last = json.loads((self.output / 'round-002.json').read_text(encoding='utf-8'))
        self.assertEqual(last['applied_changes'][0]['status'], 'mechanically_rechecked')
        self.assertGreaterEqual(last['applied_changes'][0]['font_check']['minimum_final_font_pt'], 12)
        self.assertFalse(result['human_release_approved'])
        self.assertFalse(result['release_ready'])
        self.assertEqual(result['independent_review_status'], 'pending')
        self.assertEqual(last['build']['visual_review_status'], 'pending')
        compiled = last['build']['compile_inputs']
        retained = compiled['instrumented_source_refs']['paper/main.tex']
        retained_path = self.output / 'candidate-v002' / retained['path']
        self.assertIn(b'MCMFINISHWIDTH:', retained_path.read_bytes())
        self.assertNotIn(b'MCMFINISHWIDTH:', second)
        self.assertEqual(finish.digest(retained_path), retained['sha256'])
        self.assertEqual(compiled['compiled_input_hashes']['paper/main.tex'], retained['sha256'])
        for relative, expected in last['build']['output_hashes'].items():
            self.assertEqual(finish.digest(self.output / 'candidate-v002' / relative), expected)
        self.assertEqual(finish.digest(self.output / 'baseline.json'), result['baseline_sha256'])

    def test_font_floor_blocks_shrink_and_creates_figure_queue(self):
        text_pdf(self.root / 'figures/chart.pdf', 'Small axes', 800, 250, 12)
        result = self.execute()
        self.assertFalse(result['mechanical_passed'])
        self.assertEqual(len(result['rounds']), 1)
        self.assertTrue(any(x['owner_role'] == 'mcm-figure' and 'below 12' in x['detail'] for x in result['fix_queue']))
        self.assertEqual((self.output / 'candidate-v001/paper/main.tex').read_bytes(), self.tex.read_bytes())

    def test_existing_output_is_never_overwritten(self):
        self.output.mkdir()
        marker = self.output / 'keep.txt'
        marker.write_text('Keep existing candidate')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.execute()
        self.assertEqual(marker.read_text(), 'Keep existing candidate')
        self.assertEqual(list(self.output.iterdir()), [marker])

    def test_second_round_failure_retains_first_candidate_without_false_pass(self):
        result = self.execute(FixtureCompiler(fail_round=2))
        self.assertFalse(result['mechanical_passed'])
        self.assertEqual(result['status'], 'needs_rework')
        self.assertTrue((self.output / 'candidate-v001/build/paper/main.pdf').is_file())
        self.assertFalse((self.output / 'candidate-v002/build/paper/main.pdf').exists())
        last = json.loads((self.output / 'round-002.json').read_text())
        self.assertEqual(last['applied_changes'][0]['status'], 'verification_failed')
        self.assertFalse(last['build']['compile_passed'])

    def test_success_return_without_pdf_cannot_pass(self):
        result = self.execute(FixtureCompiler(missing_pdf=True))
        self.assertFalse(result['mechanical_passed'])
        self.assertTrue(any('no PDF' in x['detail'] for x in result['fix_queue']))
        self.assertEqual(len(result['rounds']), 1)

    def test_missing_render_cannot_verify_applied_repair(self):
        result = self.execute(FixtureCompiler(missing_render=True))
        self.assertFalse(result['mechanical_passed'])
        last = json.loads((self.output / 'round-002.json').read_text())
        self.assertEqual(last['applied_changes'][0]['status'], 'verification_failed')
        self.assertTrue(any('Rendered page count' in x['detail'] for x in result['fix_queue']))

    def test_input_mutation_stops_without_overwriting_user_change(self):
        def mutate():
            self.tex.write_text('User changed this input', encoding='utf-8')
        result = self.execute(FixtureCompiler(mutate=mutate))
        self.assertEqual(result['status'], 'input_changed')
        self.assertFalse(result['original_unchanged'])
        self.assertFalse(result['mechanical_passed'])
        self.assertEqual(self.tex.read_text(), 'User changed this input')
        self.assertFalse((self.output / 'candidate-v002').exists())
        self.assertTrue((self.output / 'finish.json').is_file())

    def test_pause_before_work_creates_no_output(self):
        (self.root / 'config/runtime.json').write_text('{"pause_state":{"paused":true}}')
        with self.assertRaisesRegex(ValueError, 'pause'):
            self.execute()
        self.assertFalse(self.output.exists())

    def test_pause_during_compile_stops_before_further_work(self):
        def pause():
            (self.root / 'config/runtime.json').write_text('{"pause_state":{"paused":true}}')
        result = self.execute(FixtureCompiler(mutate=pause))
        self.assertFalse(result['mechanical_passed'])
        self.assertTrue(any('pause' in text for text in result['errors']))
        self.assertFalse((self.output / 'candidate-v002').exists())

    def test_expired_deadline_and_round_limit(self):
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        with self.assertRaisesRegex(ValueError, 'deadline'):
            self.execute(deadline=yesterday)
        self.assertFalse(self.output.exists())
        with self.assertRaisesRegex(ValueError, 'max_rounds'):
            self.execute(max_rounds=4)
        result = self.execute(max_rounds=1)
        self.assertFalse(result['mechanical_passed'])
        self.assertTrue(any(x['kind'] == 'bounded_repair_pending' for x in result['fix_queue']))

    def test_semantic_defects_stay_explicitly_unfixed(self):
        text = finish.read_tex(self.tex).replace(r'\caption{Evidence-based comparison}', '')
        self.tex.write_text(text.replace(r'\end{document}', r'\ref{missing}\end{document}'), newline='')
        result = self.execute()
        self.assertFalse(result['mechanical_passed'])
        kinds = {x['kind'] for x in result['fix_queue']}
        self.assertIn('missing_caption', kinds)
        self.assertIn('missing_reference', kinds)
        self.assertTrue(all(x['status'] == 'open' and not x['automatic_fix'] for x in result['fix_queue']))
        self.assertEqual(result['rounds'][-1]['applied_change_count'], 1)

    def test_comments_do_not_trigger_source_edits(self):
        self.tex.write_text('% ' + finish.read_tex(self.tex).replace('\r\n', '\n').replace('\n', '\n% '))
        audit = finish.audit_sources(self.root, 'main')
        self.assertEqual(audit['insertions'], [])
        self.assertEqual(audit['issues'], [])

    def test_inside_project_output_must_be_in_build(self):
        self.output = self.root / 'paper/new-output'
        with self.assertRaisesRegex(ValueError, 'under build'):
            self.execute()
        self.output = self.root / 'build/finish-v001'
        result = self.execute()
        self.assertTrue(result['original_unchanged'])
        self.assertTrue(result['mechanical_passed'])

    def test_declared_contest_stop_cannot_be_extended_by_cli(self):
        (self.root / 'config/contest-mcm-2027.json').write_text('{"stop_work_at":"2000-01-01T00:00:00Z"}')
        with self.assertRaisesRegex(ValueError, 'deadline'):
            self.execute(deadline='2099-01-01T00:00:00Z')

    def test_literal_listing_and_inline_code_never_receive_width_probes(self):
        source = (r'\documentclass{article}\begin{document}' + '\n' +
                  r'\begin{lstlisting}[language=TeX]' + '\n' +
                  r'\begin{figure}\includegraphics[width=1.2\linewidth]{../figures/chart.pdf}\end{figure}' + '\n' +
                  r'\end{lstlisting}' + '\n' +
                  r'\verb*|\includegraphics[width=1.2\linewidth]{../figures/chart.pdf}|' + '\n' +
                  r'\lstinline!\includegraphics[width=1.2\linewidth]{../figures/chart.pdf}!' + '\n' +
                  r'\end{document}')
        self.tex.write_text(source, encoding='utf-8', newline='')
        audit = finish.audit_sources(self.root, 'main')
        self.assertEqual(audit['insertions'], [])
        self.assertEqual(audit['graphics'], [])
        masked = finish.strip_comments(source)
        self.assertEqual(len(masked), len(source))
        self.assertEqual([i for i, x in enumerate(masked) if x == '\n'], [i for i, x in enumerate(source) if x == '\n'])

    def test_normal_width_pdf_figure_still_requires_final_font_floor(self):
        self.tex.write_bytes(self.tex.read_bytes().replace(b'width=1.2\\linewidth', b'width=\\linewidth'))
        text_pdf(self.root / 'figures/chart.pdf', 'Tiny source axis label', 400, 250, 5)
        result = self.execute()
        self.assertFalse(result['mechanical_passed'])
        self.assertEqual(len(result['rounds']), 1)
        self.assertTrue(any(x['kind'] == 'figure_final_font_defect' and 'below 12' in x['detail'] for x in result['fix_queue']))

    def test_tex_body_points_are_converted_without_weakening_pdf_figure_floor(self):
        from pypdf import PdfReader
        body = self.base / 'body-12-tex-pt.pdf'
        text_pdf(body, 'Team 1234567 Summary Sheet 12 TeX pt body', font_size=12 * 72 / 72.27)
        audit = finish.audit_final_fonts(PdfReader(body), 12)
        self.assertTrue(audit['ok'])
        self.assertEqual(audit['minimum_required_tex_pt'], 12)
        self.assertAlmostEqual(audit['minimum_required_pdf_bp'], 11.955168119551683)
        tiny = self.base / 'five-pdf-bp.pdf'
        text_pdf(tiny, 'Known five bp figure axis label', font_size=5)
        self.assertFalse(finish.audit_final_fonts(PdfReader(tiny), 12)['ok'])
        # Figure QA uses PDF bp, so the body-unit conversion is never applied here.
        checker = finish.load_sibling('figure_check')
        self.assertFalse(checker.audit_pdf(body, min_font_pt=12)['ok'])
        self.assertEqual(finish.minimum_font(self.root), 12)

    def test_fancyverb_and_minted_inline_are_not_graphics_or_probe_targets(self):
        fake = r'\includegraphics[width=1.2\linewidth]{../figures/chart.pdf}'
        literal = '\n'.join((r'\Verb|' + fake + '|', r'\Verb[breaklines=true]!' + fake + '!',
                              r'\mintinline{tex}{' + fake + '}', r'\mintinline[breaklines]{tex}|' + fake + '|',
                              r'\mintinline{tex}{\begin{figure}\centering ' + fake + r'\caption{Literal}\end{figure}}'))
        source = r'\documentclass{article}\begin{document}' + '\n' + literal + '\n' + r'\end{document}'
        self.tex.write_text(source, encoding='utf-8', newline='')
        audit = finish.audit_sources(self.root, 'main')
        self.assertEqual(audit['insertions'], [])
        self.assertEqual(audit['graphics'], [])
        self.execute()
        report = json.loads((self.output / 'round-001.json').read_text())
        self.assertEqual(report['build']['compile_inputs']['instrumented_source_refs'], {})
        self.assertEqual(report['build']['compile_inputs']['compiled_input_hashes']['paper/main.tex'], finish.digest(self.tex))
        self.assertEqual((self.output / 'candidate-v001/paper/main.tex').read_bytes(), self.tex.read_bytes())

    def test_custom_literal_declarations_disable_all_source_probes(self):
        source = (r'\newmintinline[showtex]{tex}{}' + '\n' + finish.read_tex(self.tex) + '\n' +
                  r'\showtex{\begin{figure}\includegraphics[width=1.2\linewidth]{../figures/chart.pdf}\end{figure}}')
        self.tex.write_text(source, encoding='utf-8', newline='')
        audit = finish.audit_sources(self.root, 'main')
        self.assertTrue(audit['probes_disabled_for_literal_uncertainty'])
        self.assertEqual(audit['graphics'], [])
        self.assertEqual(audit['insertions'], [])
        self.assertTrue(any(row['kind'] == 'unsupported_literal_syntax' for row in audit['issues']))

    def test_unrecognized_macro_argument_never_receives_probe(self):
        source = (r'\documentclass{article}\begin{document}' + '\n' +
                  r'\customLiteral{\begin{figure}\centering\includegraphics[width=1.2\linewidth]{../figures/chart.pdf}\caption{Literal}\end{figure}}' + '\n' +
                  r'\end{document}')
        self.tex.write_text(source, encoding='utf-8', newline='')
        audit = finish.audit_sources(self.root, 'main')
        self.assertEqual(len(audit['graphics']), 1)
        self.assertFalse(audit['graphics'][0]['probe_allowed'])
        self.assertFalse(audit['insertions'][0]['simple'])
        result = self.execute()
        report = json.loads((self.output / 'round-001.json').read_text())
        self.assertEqual(report['build']['compile_inputs']['instrumented_source_refs'], {})
        self.assertTrue(any(row['kind'] == 'unprobed_graphic_context' for row in result['fix_queue']))

    def test_raster_and_outlined_text_remain_explicit_visual_queue(self):
        self.tex.write_bytes(self.tex.read_bytes().replace(b'width=1.2\\linewidth', b'width=\\linewidth').replace(b'chart.pdf', b'chart.png'))
        (self.root / 'figures/chart.png').write_bytes(PNG)
        result = self.execute()
        self.assertFalse(result['mechanical_passed'])
        self.assertTrue(any(x['kind'] == 'figure_font_visual_verification' for x in result['fix_queue']))
        self.output = self.base / 'finish-outlined-v001'
        self.tex.write_bytes(self.tex.read_bytes().replace(b'chart.png', b'chart.pdf'))
        from pypdf import PdfWriter
        writer = PdfWriter()
        writer.add_blank_page(width=400, height=250)
        with (self.root / 'figures/chart.pdf').open('wb') as target:
            writer.write(target)
        result = self.execute()
        self.assertFalse(result['mechanical_passed'])
        self.assertTrue(any('No auditable text' in x['detail'] for x in result['fix_queue']))

    def test_decodable_tiny_png_is_not_a_complete_page_render(self):
        class TinyRenderer(FixtureCompiler):
            def run(self, command, working, env, controls):
                response = super().run(command, working, env, controls)
                if command[0] == 'fixture-renderer':
                    Path(command[-1] + '-1.png').write_bytes(PNG)
                return response
        self.tex.write_bytes(self.tex.read_bytes().replace(b'width=1.2\\linewidth', b'width=\\linewidth'))
        result = self.execute(TinyRenderer())
        self.assertFalse(result['mechanical_passed'])
        report = json.loads((self.output / 'round-001.json').read_text())
        self.assertTrue(any('dimensions' in row.get('error', '') for row in report['build']['render_validation'].values()))


if __name__ == '__main__':
    unittest.main()
