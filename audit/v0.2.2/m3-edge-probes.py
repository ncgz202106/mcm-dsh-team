#!/usr/bin/env python3
"""Portable synthetic offline checks; never certify model or visual behavior.

Uses a temporary schema fixture and three new mathematical examples. Does not
run DSH/SDK/Host, call a model, install anything or write persistent reports.
"""
from pathlib import Path
import importlib.util
import json
import math
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]


def load_verifier():
    spec = importlib.util.spec_from_file_location('m3_probe_verifier', ROOT/'tools/verify-v022.py')
    if spec is None or spec.loader is None:
        raise ValueError('Repository verifier is unavailable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expect_rejection(verifier, fixture, expected):
    try:
        verifier.validate_library(fixture)
    except ValueError as exc:
        if expected not in str(exc):
            raise AssertionError('Unexpected validation rejection') from exc
    else:
        raise AssertionError('Invalid metadata was accepted')


def metadata_probes(verifier):
    # This synthetic declaration tests schema/byte validation only. It is not
    # a real paper, a claimed award identity or remote-source authentication.
    case_id = 'mcm-2000-a-0000001'
    case = {
        'format_version': 1, 'id': case_id, 'year': 2000, 'problem': 'A', 'team': '0000001',
        'pdf_sha256': '1'*64, 'physical_page_count': 1,
        'public_source': {'url': 'https://example.org/synthetic-paper.pdf'},
        'award_evidence': {'url': 'https://example.org/synthetic-result.pdf',
                           'source_sha256': '2'*64, 'physical_page': 1,
                           'status': 'official_result_row_checked', 'designation': 'Outstanding Winner'},
        'observed_pages': {'rendered_and_viewed': [1], 'text_context_reviewed': [1]},
        'answer_chain': ['Synthetic schema fixture'], 'good_practices': ['No empirical claim'],
        'risks': ['No real source or award identity'],
        'validation': {'official_award_identity_verified': True, 'level': 'synthetic_schema_fixture'}
    }
    row = {
        'id': 'synthetic-binding', 'category': 'result-evidence', 'roles': ['mcm-reviewer'],
        'keywords': ['synthetic'], 'file': 'patterns/fixture.md', 'source_case_ids': [case_id],
        'validation_status': 'observed_pattern_not_causal_award_rule'
    }
    probes = []
    with tempfile.TemporaryDirectory(prefix='mcm-m3-probes-') as temporary:
        fixture = Path(temporary).resolve()
        # Verify the absolute cleanup target stays in the named temp workspace.
        if fixture.parent != Path(tempfile.gettempdir()).resolve() or not fixture.name.startswith('mcm-m3-probes-'):
            raise ValueError('Unexpected temporary workspace')
        library = fixture/'project-template/references/award-patterns'
        (library/'cases').mkdir(parents=True)
        (library/'patterns').mkdir()
        (library/'cases'/f'{case_id}.json').write_text(json.dumps(case), encoding='utf-8')
        card = library/'patterns/fixture.md'
        card.write_text('Synthetic authored reference for metadata checks.', encoding='utf-8')

        def set_row(value):
            (library/'catalog.json').write_text(
                json.dumps({'format_version': 1, 'patterns': [value]}), encoding='utf-8')

        set_row(row)
        assert verifier.validate_library(fixture)['versioned_patterns'] == 0
        probes.append({'id': 'legacy-entry', 'passed': True,
                       'observation': 'Omitting both optional fields remains compatible.'})

        pin = {**row, 'version': 2, 'sha256': verifier.digest(card)}
        set_row(pin)
        result = verifier.validate_library(fixture)
        assert result['declared_pattern_refs'][row['id']]['version'] == 2
        assert result['declared_pattern_refs'][row['id']]['sha256'] == verifier.digest(card)
        probes.append({'id': 'complete-current-pin', 'passed': True,
                       'observation': 'A complete typed pin binds the actual current file.'})

        card.write_text('Changed bytes with a stale declared SHA.', encoding='utf-8')
        expect_rejection(verifier, fixture, 'Pattern entry digest mismatch')
        probes.append({'id': 'byte-drift-denies', 'passed': True,
                       'observation': 'Changing bytes without changing the declared pin is rejected.'})

        bad_pins = [
            {'version': True, 'sha256': verifier.digest(card)},
            {'version': 0, 'sha256': verifier.digest(card)},
            {'version': '2', 'sha256': verifier.digest(card)},
            {'version': 2}, {'sha256': verifier.digest(card)},
            {'version': 2, 'sha256': None}, {'version': 2, 'sha256': 'f'*63}
        ]
        for fields in bad_pins:
            set_row({**row, **fields})
            expect_rejection(verifier, fixture, 'Pattern entry')
        probes.append({'id': 'typed-complete-opt-in', 'passed': True, 'negative_cases': len(bad_pins),
                       'cases': ['boolean version', 'zero version', 'string version', 'missing digest',
                                 'missing version', 'null digest', 'short digest']})
    return probes


def mathematical_probes():
    # New synthetic operands, unrelated to held-out competition answers.
    beta_a, beta_b, demand_a, demand_b = 3, 1, 100, 160
    coefficient_ratio = beta_a/beta_b
    per_volume_ratio = (beta_a/demand_a)/(beta_b/demand_b)
    assert math.isclose(coefficient_ratio, 3) and math.isclose(per_volume_ratio, 4.8)

    observed, predicted = [2, 3], [3, 4]
    residuals = [actual-forecast for actual, forecast in zip(observed, predicted)]
    mean_error = sum(residuals)/len(residuals)
    assert mean_error == -1 and all(forecast > actual for actual, forecast in zip(observed, predicted))

    parameter_endpoints = [0, 2]
    parameter_midpoint = sum(parameter_endpoints)/2
    response_at_parameter_midpoint = parameter_midpoint**2
    midpoint_of_endpoint_envelope = sum(x**2 for x in parameter_endpoints)/2
    assert response_at_parameter_midpoint == 1 and midpoint_of_endpoint_envelope == 2
    return [
        {'id': 'normalization-meaning', 'passed': True,
         'operands': {'beta_a': beta_a, 'beta_b': beta_b, 'demand_a': demand_a, 'demand_b': demand_b},
         'penalty_expression': 'J = beta_a*(shortfall_a/demand_a) + beta_b*(shortfall_b/demand_b)',
         'unit_condition': 'Both demands and shortfalls use the same arbitrary volume unit.',
         'coefficient_ratio_expression': 'beta_a/beta_b', 'coefficient_ratio': coefficient_ratio,
         'per_volume_ratio_expression': '(beta_a/demand_a)/(beta_b/demand_b)', 'per_volume_ratio': per_volume_ratio},
        {'id': 'residual-sign-meaning', 'passed': True,
         'operands': {'observed': observed, 'predicted': predicted},
         'expression': 'e_i = observed_i - predicted_i; mean_e = sum(e_i)/n',
         'residuals': residuals, 'mean_error': mean_error,
         'interpretation': 'Predictions are higher than observations in this synthetic example.'},
        {'id': 'reference-not-envelope-midline', 'passed': True,
         'operands': {'parameter_endpoints': parameter_endpoints}, 'response_expression': 'y(x) = x**2',
         'reference_expression': 'y((x_low+x_high)/2)',
         'envelope_midpoint_expression': '(y(x_low)+y(x_high))/2',
         'parameter_midpoint': parameter_midpoint, 'reference_response': response_at_parameter_midpoint,
         'endpoint_envelope_midpoint': midpoint_of_endpoint_envelope,
         'scope': 'A nonlinear scalar response example, not a predictive or confidence interval.'}
    ]


def main():
    if not __debug__:
        raise ValueError('Run probes without Python optimization so assertions remain enabled')
    probes = metadata_probes(load_verifier()) + mathematical_probes()
    assert len(probes) == 7 and all(probe['passed'] for probe in probes)
    print(json.dumps({
        'status': 'passed', 'passed': len(probes), 'failed': 0, 'assertions_enabled': __debug__, 'probes': probes,
        'scope': 'Portable synthetic schema/byte checks and mathematical meaning examples only.',
        'new_M3_model_behavior_verified': False, 'native_runtime_verified': False, 'release_ready': False,
        'persistent_reports_written': False,
        'limits': ['No DSH, SDK, Host, model API, installation, original paper or evaluation data is used.',
                   'Schema-fixture award fields are test declarations, not real source or award authentication.',
                   'Arithmetic checks do not prove that a model follows the revised instructions or that a figure is attractive.']
    }, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (AssertionError, ValueError, OSError) as exc:
        reason = str(exc).replace(str(ROOT), '<REPO_ROOT>').replace(str(Path.home()), '<USER_HOME>')
        print(json.dumps({'status': 'failed', 'error_type': type(exc).__name__, 'reason': reason[:300],
                          'release_ready': False}, ensure_ascii=False))
        raise SystemExit(1)
