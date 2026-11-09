"""Check declared section-to-visual evidence; aesthetics require actual review."""
import hashlib
import json
from pathlib import Path
import re


def audit(project):
    root = Path(project).resolve()
    runtime = root / 'config/runtime.json'
    config = json.loads(runtime.read_text(encoding='utf-8')) if runtime.exists() else {}
    path = root / 'paper/section-visual-map.json'
    required = config.get('require_section_visual_coverage') is True
    if not path.is_file():
        return {'ok': not required, 'errors': ['Missing section visual coverage map'] if required else [], 'status': 'missing', 'aesthetic_status': 'not_assessed'}
    try:
        if not path.resolve().is_relative_to(root):
            raise ValueError('Section visual map must stay in the project')
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict) or not isinstance(data.get('sections'), list):
            raise ValueError('Section visual map needs a sections list')
    except (OSError, ValueError) as exc:
        return {'ok': False, 'errors': [str(exc)], 'status': 'invalid', 'aesthetic_status': 'not_assessed'}
    if data.get('_template_only') or not data.get('sections'):
        return {'ok': not required, 'errors': ['Section visual map is empty or a template'] if required else [], 'status': 'template', 'aesthetic_status': 'not_assessed'}
    errors, checked, seen = [], [], set()

    def read_ref(ref):
        if not isinstance(ref, dict):
            raise ValueError('Section/visual reference must be an object')
        rel = ref.get('path', '')
        if not isinstance(rel, str):
            raise ValueError('Section/visual reference path must be a string')
        p = root / rel
        if not rel or Path(rel).is_absolute() or '..' in Path(rel).parts or not p.resolve().is_relative_to(root):
            raise ValueError('Unsafe section/visual source path')
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != ref.get('sha256'):
            raise ValueError('Section/visual source is missing or changed: ' + rel)
        return p

    for row in data['sections']:
        if not isinstance(row, dict):
            errors.append('Section record must be an object')
            continue
        sid = row.get('section_id')
        try:
            if not isinstance(sid, str) or not sid or sid in seen or not row.get('title'):
                raise ValueError('Missing/duplicate section identity or title')
            seen.add(sid)
            if not isinstance(row.get('visual_required'), bool):
                raise ValueError('Declare whether this section needs visual evidence')
            source = read_ref(row.get('section_source', {})).read_text(encoding='utf-8')
            if '\\label{' + sid + '}' not in source:
                raise ValueError('Section anchor not found: ' + sid)
            if not row['visual_required']:
                if not row.get('reason_without_visual'):
                    raise ValueError('A section without a visual needs an explicit reason')
            else:
                refs = row.get('visual_refs')
                if not row.get('conclusion') or not isinstance(refs, list) or not refs:
                    raise ValueError('Necessary section must bind a conclusion and a figure/table')
                for ref in refs:
                    read_ref(ref)
                    if ref.get('kind') not in {'figure', 'table', 'schematic'} or not ref.get('caption'):
                        raise ValueError('Visual must declare its kind and an informative caption')
                    label = ref.get('label', '')
                    definition = source
                    if 'definition_source' in ref:
                        definition = read_ref(ref['definition_source']).read_text(encoding='utf-8')
                    if not isinstance(label, str) or not label or '\\label{' + label + '}' not in definition:
                        raise ValueError('Visual anchor is missing in its definition source: ' + str(label))
                    if not re.search(r'\\(?:ref|autoref|cref)\{' + re.escape(label) + r'\}', source):
                        raise ValueError('Visual is not referenced in the declared section source: ' + label)
            checked.append(sid)
        except (OSError, ValueError, TypeError) as exc:
            errors.append(str(sid) + ': ' + str(exc))
    return {'ok': not errors, 'errors': errors, 'checked_sections': checked,
            'status': 'checked', 'aesthetic_status': 'not_assessed',
            'limitations': ['Declared coverage only: a non-author must check omitted subsections and whether visuals support the actual conclusions.',
                           'Source anchors and file hashes do not prove final-page legibility or aesthetic quality.']}
