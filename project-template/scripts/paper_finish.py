#!/usr/bin/env python3
"""Bounded draft layout correction in new, reviewable candidate directories.

This command never promotes a candidate, changes a registry, or supplies a visual
review. It only repairs a plain oversized PDF insertion after TeX has measured the
actual line width and the existing figure checker proves the final font floor.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

IGNORED = {'.git', '.venv', 'venv', 'node_modules', '__pycache__', '.pytest_cache', 'build'}
WIDTH = re.compile(r'\\includegraphics\[(?P<option>width\s*=\s*(?P<factor>(?:\d+(?:\.\d*)?|\.\d+))\s*\\(?P<unit>linewidth|textwidth))\]\{(?P<file>[^{}\n]+)\}')
GRAPHIC = re.compile(r'\\includegraphics\*?(?:\[[^\]\n]*\])?\{([^{}\n]+)\}')
PROBE = re.compile(r'MCMFINISHWIDTH:([a-f0-9]+):([\d.]+)pt:([\d.]+)pt')


def load_sibling(name):
    spec = importlib.util.spec_from_file_location('paper_finish_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path):
    checksum = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            checksum.update(chunk)
    return checksum.hexdigest()


def read_tex(path):
    with Path(path).open(encoding='utf-8', newline='') as stream:
        return stream.read()


def json_write(path, data):
    path = Path(path)
    # Evidence files are append-only at the directory level; no silent reuse.
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def selected_files(root):
    """Inventory copied project inputs, pruning dependency/build trees first."""
    root = Path(root).resolve()
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in IGNORED)
        for name in dirs + files:
            path = Path(current) / name
            if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
                raise ValueError('Candidate inputs cannot contain symlinks/reparse points: ' + str(path))
        for name in sorted(files):
            yield Path(current) / name


def snapshot(root):
    root = Path(root).resolve()
    return {p.relative_to(root).as_posix(): digest(p) for p in selected_files(root)}


def snapshot_hash(hashes):
    return hashlib.sha256(json.dumps(hashes, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def copy_inputs(source, destination):
    destination.mkdir(parents=True, exist_ok=False)
    for path in selected_files(source):
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def read_config(project):
    path = Path(project) / 'config/runtime.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def parse_deadline(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Deadline needs an explicit timezone')
    return parsed.astimezone(timezone.utc)


class StopWork(ValueError):
    pass


class Controls:
    def __init__(self, project, deadline, timeout_seconds):
        self.project = project
        self.started = time.monotonic()
        self.timeout_seconds = timeout_seconds
        self.deadline = parse_deadline(deadline)
        config = read_config(project)
        # A real contest stop remains binding even when a later CLI deadline is supplied.
        paper = load_sibling('paper')
        rule_stop = parse_deadline(paper.project_rules(project).get('stop_work_at'))
        stops = [x for x in (self.deadline, rule_stop, parse_deadline(config.get('paper_finish_deadline'))) if x]
        self.deadline = min(stops) if stops else None

    def check(self):
        config = read_config(self.project)
        pause = config.get('pause_state', {})
        if not isinstance(pause, dict):
            raise StopWork('Invalid pause_state; no further work permitted')
        if config.get('paused') is True or pause.get('paused') is True:
            raise StopWork('User pause is active; candidate work stopped')
        if self.deadline and datetime.now(timezone.utc) >= self.deadline:
            raise StopWork('Work deadline reached; candidate work stopped')
        if time.monotonic() - self.started >= self.timeout_seconds:
            raise StopWork('Finish time budget exhausted; candidate work stopped')


def _stop_process(process):
    if os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, timeout=10)
    else:
        import signal
        os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=10)


def run_command(command, working, env, controls):
    controls.check()
    kwargs = {'start_new_session': True} if os.name != 'nt' else {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP}
    process = subprocess.Popen(command, cwd=working, env=env, text=True, encoding='utf-8', errors='replace',
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kwargs)
    try:
        while True:
            try:
                output, _ = process.communicate(timeout=.25)
                controls.check()
                return process.returncode, output
            except subprocess.TimeoutExpired:
                controls.check()
    except BaseException:
        if process.poll() is None:
            _stop_process(process)
        raise


def strip_comments(text):
    """Mask comments and literal TeX code while preserving every source offset.

    This is deliberately a lexical filter, not a TeX interpreter. Literal code
    must never receive a probe: a typeout inside verbatim is visible document
    content. Escaped backslashes are also masked to avoid matching their tail.
    """
    result = list(text)
    literal_envs = {'verbatim', 'verbatim*', 'Verbatim', 'Verbatim*', 'BVerbatim', 'LVerbatim',
                    'lstlisting', 'lstlisting*', 'minted', 'comment', 'filecontents', 'filecontents*'}

    def mask(start, end):
        result[start:end] = [' ' if value not in '\r\n' else value for value in text[start:end]]

    def skip_space(start):
        while start < len(text) and text[start].isspace():
            start += 1
        return start

    def group_end(start, opener='{', closer='}'):
        depth, stop = 1, start + 1
        while stop < len(text) and depth:
            if text[stop] == '\\':
                stop += 2
                continue
            depth += (text[stop] == opener) - (text[stop] == closer)
            stop += 1
        return min(stop, len(text))

    index = 0
    while index < len(text):
        if text[index] == '%':
            end = text.find('\n', index)
            end = len(text) if end == -1 else end
            mask(index, end)
            index = end
            continue
        if text[index] != '\\':
            index += 1
            continue
        command = re.match(r'\\([A-Za-z@]+)', text[index:])
        if not command:
            mask(index, min(index + 2, len(text)))
            index += 2
            continue
        name = command[1]
        end_command = index + len(command[0])
        if name in {'string', 'meaning'}:
            quoted = re.match(r'\s*(?:\\[A-Za-z@]+|\\.|.)', text[end_command:])
            stop = end_command + len(quoted[0]) if quoted else end_command
            mask(index, stop)
            index = stop
            continue
        if name in {'detokenize', 'unexpanded', 'url', 'nolinkurl', 'path'}:
            start_argument = end_command
            while start_argument < len(text) and text[start_argument].isspace():
                start_argument += 1
            if text[start_argument:start_argument + 1] == '{':
                depth, stop = 1, start_argument + 1
                while stop < len(text) and depth:
                    if text[stop] == '\\':
                        stop += 2
                        continue
                    depth += (text[stop] == '{') - (text[stop] == '}')
                    stop += 1
                mask(index, stop)
                index = stop
                continue
        if name == 'begin':
            environment = re.match(r'\{([^{}]+)\}', text[end_command:])
            if environment and environment[1] in literal_envs:
                end_marker = '\\end{' + environment[1] + '}'
                stop = text.find(end_marker, end_command + len(environment[0]))
                stop = len(text) if stop == -1 else stop + len(end_marker)
                mask(index, stop)
                index = stop
                continue
        if name in {'verb', 'Verb', 'EscVerb', 'SaveVerb', 'lstinline', 'mintinline'}:
            start_delimiter = end_command
            if start_delimiter < len(text) and text[start_delimiter] == '*':
                start_delimiter += 1
            if name != 'verb':
                start_delimiter = skip_space(start_delimiter)
                if text[start_delimiter:start_delimiter + 1] == '[':
                    start_delimiter = skip_space(group_end(start_delimiter, '[', ']'))
            if name in {'mintinline', 'SaveVerb'}:
                # minted's language and FancyVerb's saved-name argument precede
                # the literal body; neither is the body's delimiter.
                if text[start_delimiter:start_delimiter + 1] == '{':
                    start_delimiter = skip_space(group_end(start_delimiter))
                else:
                    # Malformed literal syntax is not safe to instrument.
                    stop = text.find('\n', index)
                    stop = len(text) if stop == -1 else stop
                    mask(index, stop)
                    index = stop
                    continue
            if start_delimiter < len(text) and not text[start_delimiter].isspace():
                delimiter = text[start_delimiter]
                if name != 'verb' and delimiter == '{':
                    stop = group_end(start_delimiter)
                    mask(index, stop)
                    index = stop
                    continue
                line_end = text.find('\n', start_delimiter)
                line_end = len(text) if line_end == -1 else line_end
                closing_delimiter = '}' if name == 'lstinline' and delimiter == '{' else delimiter
                stop = text.find(closing_delimiter, start_delimiter + 1, line_end)
                stop = line_end if stop == -1 else stop + 1
                mask(index, stop)
                index = stop
                continue
        index = end_command
    return ''.join(result)


def source_files(project, stem):
    """Follow literal TeX inputs only; conditionals are conservatively included."""
    paper = project / 'paper'
    pending, found = [paper / (stem + '.tex')], {}
    while pending:
        path = pending.pop().resolve()
        if not path.is_relative_to(project):
            raise ValueError('TeX input escapes candidate project')
        if path in found:
            continue
        if not path.is_file():
            continue  # Compiler reports missing/dynamic inputs without guessing their content.
        text = read_tex(path)
        found[path] = text
        for relative in re.findall(r'\\(?:input|include)\{([^{}\n]+)\}', strip_comments(text)):
            if '\\' in relative or '#' in relative:
                continue
            relative = relative if Path(relative).suffix else relative + '.tex'
            options = [paper / relative, path.parent / relative]
            existing = next((x for x in options if x.is_file()), options[0])
            pending.append(existing)
    return found


def issue(kind, owner, detail, **fields):
    return {'kind': kind, 'owner_role': owner, 'detail': detail, 'status': 'open',
            'automatic_fix': False, **fields}


def figure_path(project, source, relative, texts):
    if any(x in relative for x in ('\\', '#', '{', '}')):
        return None
    paper = project / 'paper'
    bases = [paper, source.parent]
    for text in texts:
        for block in re.findall(r'\\graphicspath\{((?:\{[^{}]*\})+)\}', strip_comments(text)):
            bases += [paper / value for value in re.findall(r'\{([^{}]*)\}', block)]
    matches = set()
    for base in bases:
        path = (base / relative).resolve()
        options = [path] if path.suffix else [path.with_suffix(ext) for ext in ('.pdf', '.png', '.jpg', '.jpeg')]
        for option in options:
            if option.is_relative_to(project) and option.is_file():
                matches.add(option)
                break
    # Ambiguous TeX search paths cannot support an automatic proof.
    return next(iter(matches)) if len(matches) == 1 else None


def audit_sources(project, stem):
    files = source_files(project, stem)
    issues, insertions, graphics = [], [], []
    uncertain_literal = []
    for path, original in files.items():
        if re.search(r'\\(?:newmintinline|newminted|newmint|CustomVerbatimCommand|RecustomVerbatimCommand|DefineVerbatimEnvironment|RecustomVerbatimEnvironment|lstnewenvironment|DefineShortVerb|MakeShortVerb|lstMakeShortInline|catcode)\b', strip_comments(original)):
            uncertain_literal.append(path.relative_to(project).as_posix())
    if uncertain_literal:
        issues.append(issue('unsupported_literal_syntax', 'mcm-typesetter',
                            'Custom literal commands or catcode changes require lexical review; no source in this input closure receives probes or automatic edits',
                            sources=uncertain_literal))
    labels, references = {}, []
    for path, original in files.items():
        text = strip_comments(original)
        relative = path.relative_to(project).as_posix()
        for label in re.findall(r'\\label\{([^{}]+)\}', text):
            labels.setdefault(label, []).append(relative)
        references += [(relative, x) for x in re.findall(r'\\(?:ref|eqref|pageref|autoref)\{([^{}]+)\}', text)]
        figures = list(re.finditer(r'\\begin\{figure\*?\}(.*?)\\end\{figure\*?\}', text, re.S))
        for block in figures:
            if GRAPHIC.search(block.group()) and not re.search(r'\\caption(?:\[[^\]]*\])?\{', block.group()):
                issues.append(issue('missing_caption', 'mcm-figure', 'Figure caption needs evidence-grounded author text', source=relative,
                                    line=text.count('\n', 0, block.start()) + 1))
        for graphic in GRAPHIC.finditer(text):
            if uncertain_literal:
                continue
            width = WIDTH.fullmatch(graphic.group())
            enclosing = next((x for x in figures if x.start() <= graphic.start() < x.end()), None)
            prefix = text[enclosing.start():graphic.start()] if enclosing else ''
            outer_group_depth = text.count('{', 0, graphic.start()) - text.count('}', 0, graphic.start())
            simple = bool(enclosing and re.fullmatch(r'\\begin\{figure\*?\}(?:\[[^\]]*\])?\s*(?:\\centering\s*)?', prefix)
                          and outer_group_depth == 0
                          and not re.search(r'\\(?:resizebox|scalebox|rotatebox|put|newcommand|def)\b', text))
            identifier = hashlib.sha256((relative + ':' + str(graphic.start())).encode()).hexdigest()[:12]
            image = figure_path(project, path, graphic[1], files.values())
            item = {'id': identifier, 'source': relative, 'start': graphic.start(), 'end': graphic.end(),
                    'before': original[graphic.start():graphic.end()], 'simple': simple,
                    'probe_allowed': outer_group_depth == 0,
                    'figure': image.relative_to(project).as_posix() if image else None}
            graphics.append(item)
            if width and float(width['factor']) > 1:
                insertions.append({**item, 'after': r'\includegraphics[width=\linewidth]{' + graphic[1] + '}',
                                   'factor': float(width['factor']), 'unit': width['unit']})
    for relative, label in references:
        if label not in labels:
            issues.append(issue('missing_reference', 'mcm-typesetter', 'Resolve reference without inventing a label: ' + label, source=relative))
    for label, paths in labels.items():
        if len(paths) > 1:
            issues.append(issue('duplicate_label', 'mcm-typesetter', 'Label occurs more than once: ' + label, sources=paths))
    return {'issues': issues, 'insertions': insertions, 'graphics': graphics,
            'probes_disabled_for_literal_uncertainty': bool(uncertain_literal),
            'source_scope': 'Literal input closure; inactive conditional branches may require reviewer dismissal.'}


def choose_tools(engine, tex_command, renderer):
    executable = str(Path(tex_command).resolve()) if tex_command else None
    if engine == 'auto' and executable:
        name = Path(executable).stem.lower()
        engine = next((x for x in ('latexmk', 'xelatex', 'tectonic') if x in name), None)
        if not engine:
            raise ValueError('Select --engine for a compiler with a nonstandard filename')
    if engine == 'auto':
        engine = next((x for x in ('latexmk', 'xelatex', 'tectonic') if shutil.which(x)), None)
    if not engine:
        raise ValueError('No configured TeX compiler available; pass --tex-command; this command never installs a runtime')
    executable = executable or shutil.which(engine)
    renderer = str(Path(renderer).resolve()) if renderer else shutil.which('pdftoppm')
    if not executable or not Path(executable).is_file():
        raise ValueError('TeX executable not found')
    if not renderer or not Path(renderer).is_file():
        raise ValueError('pdftoppm is required; no automatic installation is performed')
    return engine, executable, renderer


def minimum_font(project):
    path = Path(project) / 'config/figure-style.json'
    minimum = float(json.loads(path.read_text(encoding='utf-8')).get('minimum_final_glyph_pt', 12)) if path.exists() else 12
    if not math.isfinite(minimum):
        raise ValueError('Final font floor must be finite')
    return max(12, minimum)


def audit_final_fonts(reader, minimum):
    """Check transformed extractable text in the actual assembled PDF.

    The contest/body setting is in TeX pt (1/72.27 inch); PDF text operators
    measure bp (1/72 inch). Figure contracts separately retain a 12 PDF-bp floor.
    Small text is a review defect, not permission to enlarge scientific symbols.
    Raster and outlined labels are separately left in the figure review queue.
    """
    minimum_pdf_bp = minimum * 72 / 72.27
    smallest, checked, small, unknown = None, 0, [], []
    for number, page in enumerate(reader.pages, 1):
        def visit(text, cm, tm, font, size):
            nonlocal smallest, checked
            if not text.strip():
                return
            if font is None:
                unknown.append({'page': number, 'text': text.strip()[:60], 'reason': 'Missing font dictionary'})
                return
            a, b = tm[0] * cm[0] + tm[1] * cm[2], tm[0] * cm[1] + tm[1] * cm[3]
            c, d = tm[2] * cm[0] + tm[3] * cm[2], tm[2] * cm[1] + tm[3] * cm[3]
            effective = abs(float(size)) * min(math.hypot(a, b), math.hypot(c, d))
            if not math.isfinite(effective) or effective <= 0:
                unknown.append({'page': number, 'text': text.strip()[:60], 'reason': 'Unusable text transform'})
                return
            checked += 1
            smallest = effective if smallest is None else min(smallest, effective)
            if effective < minimum_pdf_bp - .03:
                small.append({'page': number, 'text': text.strip()[:60], 'final_size_pt': round(effective, 3),
                              'final_size_pdf_bp': round(effective, 3),
                              'font': str(font.get('/BaseFont', 'unknown'))})
        page.extract_text(visitor_text=visit)
    return {'ok': bool(checked) and not small and not unknown, 'minimum_required_pt': minimum,
            'minimum_required_tex_pt': minimum, 'minimum_required_pdf_bp': minimum_pdf_bp,
            'requirement_unit': 'TeX pt (1/72.27 inch)', 'measurement_unit': 'PDF bp (1/72 inch)',
            'minimum_observed_pt': round(smallest, 3) if smallest is not None else None,
            'minimum_observed_pdf_bp': round(smallest, 3) if smallest is not None else None,
            'checked_text_runs': checked, 'small_text_runs': small, 'unverified_text_runs': unknown,
            'coverage': 'Extractable text only; raster and outlined labels require actual visual size verification',
            'small_text_interpretation': 'Needs context review: ordinary body text and figure labels differ from necessary mathematical superscripts/subscripts. Never enlarge a whole equation or alter mathematical scripts automatically.',
            'visual_status': 'pending'}


def validate_page_png(path):
    """Validate PNG structure/CRC, then decode all pixels, one page at a time."""
    try:
        import warnings
        from PIL import Image
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(path) as image:
                if image.format != 'PNG' or min(image.size) <= 0:
                    raise ValueError('Not a nonempty PNG page')
                size = list(image.size)
                image.verify()
            with Image.open(path) as image:
                image.load()
                if list(image.size) != size:
                    raise ValueError('PNG dimensions changed between verification and pixel decode')
        return {'ok': True, 'size_px': size, 'pixel_decode': 'complete'}
    except Exception as exc:
        return {'ok': False, 'error': str(exc), 'pixel_decode': 'failed_or_unavailable'}


def graphic_final_size(item, probe, width, height):
    """Resolve only a plain single-option graphic size; complex transforms queue."""
    if not item['simple']:
        return None
    options = re.search(r'\\includegraphics(?:\[([^\]]*)\])?\{', item['before'])
    if not options:
        return None
    option = (options[1] or '').strip()
    if not option:
        width_mm = width / 72 * 25.4
    else:
        match = re.fullmatch(r'width\s*=\s*((?:\d+(?:\.\d*)?|\.\d+))?\s*\\(linewidth|textwidth)', option)
        absolute = re.fullmatch(r'width\s*=\s*([\d.]+)\s*(in|cm|mm|pt|bp)', option)
        scale = re.fullmatch(r'scale\s*=\s*([\d.]+)', option)
        if match:
            factor = float(match[1]) if match[1] else 1
            width_mm = factor * probe[match[2] + '_pt'] / 72.27 * 25.4
        elif absolute:
            width_mm = float(absolute[1]) * {'in': 25.4, 'cm': 10, 'mm': 1, 'pt': 25.4 / 72.27, 'bp': 25.4 / 72}[absolute[2]]
        elif scale:
            width_mm = float(scale[1]) * width / 72 * 25.4
        else:
            return None
    if width_mm <= 0 or not math.isfinite(width_mm):
        return None
    return {'width': width_mm, 'height': height / width * width_mm}


def audit_graphic_fonts(project, audit, probes):
    checker = load_sibling('figure_check')
    checks, queue = [], []
    for item in audit.get('graphics', []):
        if item.get('probe_allowed') is False:
            queue.append(issue('unprobed_graphic_context', 'mcm-typesetter',
                               'Graphic-like tokens inside a macro argument/group cannot safely receive a probe; verify execution and final size manually',
                               source=item['source'], insertion_id=item['id']))
            continue
        probe = probes.get(item['id'])
        if not probe:
            continue  # No measurement means the literal conditional branch was not executed.
        fields = {'source': item['source'], 'figure': item['figure'], 'insertion_id': item['id']}
        if not item['figure'] or Path(item['figure']).suffix.lower() != '.pdf':
            queue.append(issue('figure_font_visual_verification', 'mcm-figure',
                               'Raster, missing, or ambiguous figure text needs actual final-size visual verification', **fields))
            continue
        try:
            from pypdf import PdfReader
            page = PdfReader(project / item['figure']).pages[0]
            if int(page.get('/Rotate', 0)) % 360:
                raise ValueError('Rotated PDF figure size needs review')
            size = graphic_final_size(item, probe, float(page.cropbox.width), float(page.cropbox.height))
            if size is None:
                raise ValueError('Complex insertion size or enclosing transform cannot be proved automatically')
            checked = checker.audit_pdf(project / item['figure'], size, minimum_font(project))
            checks.append({**fields, 'final_size_mm': size, 'figure_sha256': digest(project / item['figure']), **checked})
            if not checked['ok']:
                queue.append(issue('figure_final_font_defect', 'mcm-figure', '; '.join(checked['errors']), **fields))
        except Exception as exc:
            queue.append(issue('figure_font_visual_verification', 'mcm-figure', str(exc), **fields))
    return {'checks': checks, 'fix_queue': queue, 'visual_status': 'pending'}


def compile_candidate(candidate, stem, audit, tools, controls):
    """Compile a scratch copy, preserving candidate source bytes and all logs."""
    paper = load_sibling('paper')
    engine, executable, renderer = tools
    output = candidate / 'build/paper'
    output.mkdir(parents=True, exist_ok=False)
    before = snapshot(candidate)
    with tempfile.TemporaryDirectory(prefix='mcm-finish-') as temporary:
        scratch = Path(temporary) / 'project'
        copy_inputs(candidate, scratch)
        # Probe only direct commands, outside comments, in the scratch copy.
        instrumented_sources = {}
        observed_graphics = [item for item in audit.get('graphics', audit['insertions']) if item.get('probe_allowed') is not False]
        for relative in sorted({x['source'] for x in observed_graphics}):
            source = scratch / relative
            text = read_tex(source)
            for item in sorted((x for x in observed_graphics if x['source'] == relative), key=lambda x: -x['start']):
                text = text[:item['start']] + r'\typeout{MCMFINISHWIDTH:' + item['id'] + r':\the\linewidth:\the\textwidth}' + text[item['start']:]
            source.write_text(text, encoding='utf-8', newline='')
            retained = output / 'compile-inputs' / relative
            retained.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, retained)
            instrumented_sources[relative] = {'path': retained.relative_to(candidate).as_posix(), 'sha256': digest(retained),
                                               'candidate_sha256': before[relative]}
        compile_input_manifest = {'candidate_input_hashes': before, 'compiled_input_hashes': snapshot(scratch),
                                  'instrumented_source_refs': instrumented_sources,
                                  'instrumentation': 'Nonprinting width probes outside lexically masked comments and literal code'}
        json_write(output / 'compile-inputs.json', compile_input_manifest)
        working = scratch / 'paper'
        (working / 'out').mkdir()
        env = paper.tex_environment()
        env['PATH'] = str(Path(executable).parent) + os.pathsep + env.get('PATH', '')
        env['BIBINPUTS'] = working.as_posix() + os.pathsep + env.get('BIBINPUTS', '')
        env['BSTINPUTS'] = working.as_posix() + os.pathsep + env.get('BSTINPUTS', '')
        commands = []
        if engine == 'latexmk':
            commands.append([executable, '-xelatex', '-bibtex', '-no-shell-escape', '-interaction=nonstopmode',
                             '-halt-on-error', '-file-line-error', '-recorder', '-outdir=out', stem + '.tex'])
        elif engine == 'tectonic':
            commands.append([executable, '--untrusted', '--only-cached', '--keep-logs', '--keep-intermediates', '--outdir', 'out', stem + '.tex'])
        else:
            commands.append([executable, '-no-shell-escape', '-interaction=nonstopmode', '-halt-on-error',
                             '-file-line-error', '-recorder', '-output-directory=out', stem + '.tex'])
            if 'miktex' in str(executable).lower():
                commands[0].insert(1, '-disable-installer')
                commands[0].insert(2, '-dont-parse-first-line')
        console, returncode, executed = '', 0, []
        for command in commands:
            returncode, text = run_command(command, working, env, controls)
            executed.append(command)
            console += text + '\n'
            if returncode:
                break
        if not returncode and engine == 'xelatex':
            aux = working / 'out' / (stem + '.aux')
            if aux.exists() and r'\bibdata' in aux.read_text(encoding='utf-8', errors='replace'):
                bibtex = shutil.which('bibtex', path=env['PATH'])
                if not bibtex:
                    returncode, console = 1, console + '\nBibTeX required by source but unavailable.\n'
                else:
                    code, text = run_command([bibtex, stem], working / 'out', env, controls)
                    executed.append([bibtex, stem])
                    returncode, console = code, console + text + '\n'
            if not returncode:
                for _ in range(2):
                    returncode, text = run_command(commands[0], working, env, controls)
                    executed.append(commands[0])
                    console += text + '\n'
                    if returncode:
                        break
        (output / (stem + '.console.log')).write_text(console, encoding='utf-8')
        for suffix in ('.pdf', '.log', '.aux', '.bbl', '.blg', '.fls'):
            source = working / 'out' / (stem + suffix)
            if source.exists():
                shutil.copy2(source, output / source.name)
        logpath = output / (stem + '.log')
        log = logpath.read_text(encoding='utf-8', errors='replace') if logpath.exists() else ''
        probes = {key: {'linewidth_pt': float(line), 'textwidth_pt': float(full)} for key, line, full in PROBE.findall(log + '\n' + console)}
        pdf = output / (stem + '.pdf')
        if returncode or not pdf.is_file():
            return {'compile_passed': False, 'errors': ['Compiler failed or produced no PDF'], 'width_probes': probes,
                    'commands': executed, 'returncode': returncode, 'rendered_pages': [],
                    'compile_inputs': compile_input_manifest,
                    'output_hashes': {p.relative_to(candidate).as_posix(): digest(p) for p in output.rglob('*') if p.is_file()}}
    if before != snapshot(candidate):
        raise ValueError('Candidate inputs changed during compilation')
    from pypdf import PdfReader
    reader = PdfReader(pdf)
    total_pages = len(reader.pages)
    if not total_pages:
        raise ValueError('Compiler produced a PDF with no pages')
    try:
        main_pages = paper.main_report_pages(output / (stem + '.aux'), total_pages)
        boundary_errors = []
    except ValueError as exc:
        main_pages, boundary_errors = total_pages, [str(exc)]
    report = paper.audit_pdf(pdf, main_pages, rules=paper.project_rules(candidate))
    report['errors'].extend(boundary_errors)
    final_floor = max(12, float(paper.project_rules(candidate).get('minimum_font_pt', 12)))
    report['final_font_audit'] = audit_final_fonts(reader, final_floor)
    fonts = report['final_font_audit']
    for row in fonts['small_text_runs']:
        report['errors'].append(f"Page {row['page']}: final PDF text below {final_floor:g} TeX pt "
                                f"({fonts['minimum_required_pdf_bp']:.5f} PDF bp required; measured {row['final_size_pdf_bp']:g} PDF bp): {row['text']}")
    if fonts['unverified_text_runs'] or not fonts['checked_text_runs']:
        report['errors'].append('Final PDF contains text whose actual font size could not be verified')
    report['graphic_font_audit'] = audit_graphic_fonts(candidate, audit, probes)
    report['sparse_pages_for_review'] = []
    for number, page in enumerate(reader.pages, 1):
        # A cue for review, never an automatic delete/reflow instruction.
        if 1 < number < main_pages and len((page.extract_text() or '').strip()) < 120 and not page.get('/Resources', {}).get('/XObject'):
            report['sparse_pages_for_review'].append(number)
    warnings = [line for line in log.splitlines() if re.search(r'Overfull \\[hv]box|Underfull \\[hv]box|undefined|LaTeX Warning:|Package .+ Warning:|Missing character:', line)]
    blg = output / (stem + '.blg')
    if blg.exists():
        warnings += [line for line in blg.read_text(encoding='utf-8', errors='replace').splitlines() if re.search(r'Warning--|I found no|I couldn.t open|error message', line)]
    renders = output / (stem + '-pages')
    renders.mkdir()
    code, text = run_command([renderer, '-r', '110', '-png', str(pdf), str(renders / 'page')], candidate, os.environ.copy(), controls)
    (output / (stem + '.render.log')).write_text(text, encoding='utf-8')
    pages = sorted(renders.glob('page-*.png'))
    page_numbers = {int(p.stem.split('-')[-1]) for p in pages}
    render_checks = {p.relative_to(candidate).as_posix(): validate_page_png(p) for p in pages}
    for path in pages:
        number = int(path.stem.split('-')[-1])
        if not 1 <= number <= total_pages:
            continue
        row, page = render_checks[path.relative_to(candidate).as_posix()], reader.pages[number - 1]
        unit = float(page.get('/UserUnit', 1))
        width, height = float(page.mediabox.width) * unit, float(page.mediabox.height) * unit
        if int(page.get('/Rotate', 0)) % 180:
            width, height = height, width
        expected = [math.ceil(width / 72 * 110), math.ceil(height / 72 * 110)]
        row['expected_size_px'] = expected
        if row['ok'] and any(abs(actual - wanted) > 2 for actual, wanted in zip(row['size_px'], expected)):
            row['ok'], row['error'] = False, 'PNG dimensions do not match the full PDF page at 110dpi'
    valid_png = all(row['ok'] for row in render_checks.values())
    if code or len(pages) != total_pages or not pages or page_numbers != set(range(1, total_pages + 1)) or not valid_png:
        report['errors'].append('Rendered page count differs from PDF page count, or renderer failed')
    report.update({'compile_passed': True, 'warnings': warnings, 'width_probes': probes, 'commands': executed,
                   'pdf': pdf.relative_to(candidate).as_posix(), 'pdf_sha256': digest(pdf),
                   'source_hashes': paper.sources(candidate), 'candidate_input_hashes': before,
                   'compile_inputs': compile_input_manifest,
                   'rendered_pages': [x.relative_to(candidate).as_posix() for x in pages],
                   'render_validation': render_checks,
                   'rendered_page_sha256': {x.relative_to(candidate).as_posix(): digest(x) for x in pages},
                   'source_unchanged': True, 'shell_escape_enabled': False, 'instrumentation': 'Scratch-only nonprinting width probes',
                   'visual_review_status': 'pending', 'human_release_approved': False, 'release_ready': False})
    report['output_hashes'] = {p.relative_to(candidate).as_posix(): digest(p) for p in sorted(output.rglob('*')) if p.is_file()}
    report.update(paper.result_snapshot(candidate))
    report['mechanical_passed'] = not report['errors'] and not warnings and not report['graphic_font_audit']['fix_queue']
    json_write(output / (stem + '.build.json'), report)
    return report


def safe_repairs(project, source_audit, compiled):
    changes, queue = [], []
    checker = load_sibling('figure_check')
    minimum = minimum_font(project)
    for item in source_audit['insertions']:
        fields = {'source': item['source'], 'figure': item['figure'], 'insertion_id': item['id']}
        measure = compiled.get('width_probes', {}).get(item['id'])
        if not measure:
            # Inactive conditional branches do not justify a source edit.
            continue
        reason = None
        if not item['simple']:
            reason = 'Complex or transformed figure insertion needs layout review'
        elif not item['figure'] or Path(item['figure']).suffix.lower() != '.pdf':
            reason = 'Final figure text cannot be proved for a missing, ambiguous, raster, or outlined source'
        elif measure['linewidth_pt'] <= 0:
            reason = 'TeX reported a nonpositive line width'
        else:
            try:
                from pypdf import PdfReader
                page = PdfReader(project / item['figure']).pages[0]
                if int(page.get('/Rotate', 0)) % 360:
                    raise ValueError('Rotated figure PDF needs final-size review')
                width, height = float(page.cropbox.width), float(page.cropbox.height)
                size = {'width': measure['linewidth_pt'] / 72.27 * 25.4,
                        'height': height / width * measure['linewidth_pt'] / 72.27 * 25.4}
                checked = checker.audit_pdf(project / item['figure'], size, minimum)
                if not checked['ok']:
                    reason = '; '.join(checked['errors'])
                else:
                    changes.append({**item, 'reason': 'Oversized direct PDF insertion clamped to the measured line width',
                                    'measured_linewidth_tex_pt': measure['linewidth_pt'], 'final_size_mm': size,
                                    'font_check': checked, 'source_sha256_before': digest(project / item['source']),
                                    'figure_sha256': digest(project / item['figure']), 'status': 'proposed'})
            except (OSError, ValueError, ImportError, IndexError) as exc:
                reason = str(exc)
        if reason:
            queue.append(issue('overwide_figure', 'mcm-figure', reason, **fields))
    return changes, queue


def apply_repairs(previous, candidate, changes):
    for item in changes:
        if digest(previous / item['figure']) != item['figure_sha256']:
            raise ValueError('Figure changed after the final-size font proof')
    copy_inputs(previous, candidate)
    for relative in sorted({x['source'] for x in changes}):
        path = candidate / relative
        original = read_tex(path)
        for item in sorted((x for x in changes if x['source'] == relative), key=lambda x: -x['start']):
            if digest(previous / relative) != item['source_sha256_before'] or original[item['start']:item['end']] != item['before']:
                raise ValueError('Proposed source replacement no longer matches its exact baseline')
            original = original[:item['start']] + item['after'] + original[item['end']:]
        path.write_text(original, encoding='utf-8', newline='')


def output_queue(compiled):
    queue = []
    for error in compiled.get('errors', []):
        if 'final PDF text below' in error:
            queue.append(issue('small_text_context_review', 'mcm-typesetter', error +
                               '. Distinguish ordinary body/figure text from necessary mathematical superscripts/subscripts before deciding a fix.',
                               escalation_role='mcm-modeler', constraint='Do not automatically enlarge equations, remove scripts, or change mathematical meaning'))
            continue
        kind = 'missing_or_clipped_page' if re.search(r'page|CropBox|boundary', error, re.I) else 'compile_or_pdf_error'
        queue.append(issue(kind, 'mcm-typesetter', error))
    for warning in compiled.get('warnings', []):
        if 'Overfull' in warning:
            queue.append(issue('formula_or_text_overflow', 'mcm-typesetter', warning,
                               escalation_role='mcm-modeler', constraint='Preserve formula semantics; no whole-equation scaling'))
        elif 'Underfull' in warning:
            queue.append(issue('excess_blank_area', 'mcm-typesetter', warning))
        else:
            queue.append(issue('unresolved_reference_or_tex_warning', 'mcm-typesetter', warning))
    for number in compiled.get('sparse_pages_for_review', []):
        queue.append(issue('suspected_excess_blank_area', 'mcm-typesetter', 'Sparse interior page needs rendered-page assessment; content may be intentional', page=number))
    queue.extend(compiled.get('graphic_font_audit', {}).get('fix_queue', []))
    return queue


def finish(project, output, demo=False, max_rounds=3, deadline=None, timeout_seconds=300,
           engine='auto', tex_command=None, renderer=None):
    project, output = Path(project).resolve(), Path(output).resolve()
    if not 1 <= max_rounds <= 3:
        raise ValueError('max_rounds must be between 1 and 3')
    if not 1 <= timeout_seconds <= 900:
        raise ValueError('timeout_seconds must be between 1 and 900')
    if output.exists():
        raise ValueError('Output already exists; choose a new versioned directory')
    if output == project or project.is_relative_to(output):
        raise ValueError('Output cannot replace or contain the source project')
    if output.is_relative_to(project) and output.relative_to(project).parts[0] != 'build':
        raise ValueError('An output inside the project must be under build/')
    stem = 'demo' if demo else 'main'
    if not (project / 'paper' / (stem + '.tex')).is_file():
        raise ValueError('Missing paper entry point')
    controls = Controls(project, deadline, timeout_seconds)
    controls.check()
    baseline = snapshot(project)
    tools = choose_tools(engine, tex_command, renderer)
    output.mkdir(parents=True, exist_ok=False)
    json_write(output / 'baseline.json', {'format_version': 1, 'source_hashes': baseline, 'source_set_sha256': snapshot_hash(baseline),
                                        'created_at': datetime.now(timezone.utc).isoformat(), 'source_project': str(project)})
    result = {'format_version': 1, 'status': 'needs_rework', 'mechanical_passed': False, 'rounds': [],
              'baseline_sha256': digest(output / 'baseline.json'), 'source_set_sha256': snapshot_hash(baseline),
              'original_unchanged': False, 'candidate': None, 'release_ready': False,
              'human_release_approved': False, 'visual_review_status': 'pending', 'independent_review_status': 'pending',
              'limitations': ['Rendered pages still require actual non-author inspection for image clipping, overlap, equation readability, and excess whitespace.',
                              'No semantic, data, caption, citation, model, formula or approval edits are automatic.']}
    candidate, proposed, previous_inputs = None, [], None
    try:
        for number in range(1, max_rounds + 1):
            controls.check()
            if snapshot(project) != baseline:
                raise StopWork('Original input mutation detected; no further candidate work')
            previous = candidate
            candidate = output / f'candidate-v{number:03d}'
            if proposed:
                if snapshot(previous) != previous_inputs:
                    raise StopWork('Prior candidate mutation detected; no further candidate work')
                apply_repairs(previous, candidate, proposed)
            else:
                copy_inputs(project, candidate)
            inputs = snapshot(candidate)
            if previous is None and inputs != baseline:
                raise StopWork('Original inputs changed while preparing the first candidate')
            previous_inputs = inputs
            source_audit = audit_sources(candidate, stem)
            (candidate / 'build').mkdir()
            json_write(candidate / 'build/finish-inputs.json', {'source_hashes': inputs, 'source_set_sha256': snapshot_hash(inputs)})
            controls.check()
            compiled = compile_candidate(candidate, stem, source_audit, tools, controls)
            controls.check()
            if snapshot(project) != baseline:
                raise StopWork('Original input mutation detected after compilation')
            changes, repair_queue = safe_repairs(candidate, source_audit, compiled)
            queue = source_audit['issues'] + output_queue(compiled) + repair_queue
            can_continue = bool(changes) and compiled.get('compile_passed') and number < max_rounds
            if changes and not can_continue:
                queue += [issue('bounded_repair_pending', 'mcm-typesetter', 'Proved repair remains unapplied because the round limit or build failure stopped the loop', source=x['source']) for x in changes]
            # A prior source edit is only verified when the exact new PDF and every page render exist.
            verified = bool(compiled.get('compile_passed') and compiled.get('pdf_sha256') and compiled.get('rendered_pages') and
                            len(compiled['rendered_pages']) == compiled.get('total_pdf_pages') and
                            not any('render' in x.lower() for x in compiled.get('errors', [])) and
                            compiled.get('final_font_audit', {}).get('ok') and
                            not compiled.get('graphic_font_audit', {}).get('fix_queue'))
            applied = [{**x, 'status': 'mechanically_rechecked' if verified else 'verification_failed'} for x in proposed]
            round_report = {'round': number, 'candidate': candidate.name, 'source_set_sha256': snapshot_hash(inputs),
                            'source_audit': source_audit, 'build': compiled, 'applied_changes': applied,
                            'proposed_changes': changes, 'fix_queue': queue, 'visual_review_status': 'pending',
                            'human_release_approved': False, 'independent_review_status': 'pending'}
            json_write(output / f'round-{number:03d}.json', round_report)
            result['rounds'].append({'round': number, 'report': f'round-{number:03d}.json', 'report_sha256': digest(output / f'round-{number:03d}.json'),
                                     'candidate': candidate.name, 'applied_change_count': len(applied), 'open_issue_count': len(queue)})
            result['candidate'] = candidate.name
            result['fix_queue'] = queue
            result['mechanical_passed'] = bool(compiled.get('mechanical_passed') and not queue)
            if not can_continue:
                result['status'] = 'ready_for_independent_review' if result['mechanical_passed'] else 'needs_rework'
                break
            proposed = changes
    except Exception as exc:
        result['status'] = 'stopped' if isinstance(exc, StopWork) else 'failed'
        result['mechanical_passed'] = False
        result['errors'] = [str(exc)]
    result['original_unchanged'] = snapshot(project) == baseline
    if not result['original_unchanged']:
        result['status'], result['mechanical_passed'] = 'input_changed', False
    if digest(output / 'baseline.json') != result['baseline_sha256']:
        result['status'], result['mechanical_passed'] = 'baseline_changed', False
    result['elapsed_seconds'] = round(time.monotonic() - controls.started, 3)
    json_write(output / 'finish.json', result)
    return {'output': str(output), 'report': str(output / 'finish.json'), **result}


def add_arguments(parser):
    parser.add_argument('--output', type=Path, required=True, help='New directory; existing paths are refused')
    parser.add_argument('--demo', action='store_true')
    parser.add_argument('--max-rounds', type=int, default=3, choices=(1, 2, 3))
    parser.add_argument('--deadline', help='ISO-8601 work stop with timezone')
    parser.add_argument('--timeout-seconds', type=int, default=300)
    parser.add_argument('--engine', choices=('auto', 'latexmk', 'xelatex', 'tectonic'), default='auto')
    parser.add_argument('--tex-command', type=Path, help='Existing compiler executable; no runtime installation')
    parser.add_argument('--renderer', type=Path, help='Existing pdftoppm executable')


def from_args(args):
    return finish(args.root, args.output, args.demo, args.max_rounds, args.deadline, args.timeout_seconds,
                  args.engine, args.tex_command, args.renderer)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    add_arguments(parser)
    args = parser.parse_args()
    try:
        result = from_args(args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result['mechanical_passed'] else 1
    except (OSError, ValueError, ImportError, subprocess.SubprocessError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
