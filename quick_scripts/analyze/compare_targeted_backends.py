#!/usr/bin/env python3
"""Independently audit a paired backend screen and compare coverage first."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import extended_timeout_experiments as extended
import targeted_order_cycles as trial


def compare_pair(mini, cadi, mini_report, cadi_report):
    shared = (
        'solver_source_commit', 'binary_sha256', 'build_manifest_sha256',
        'dataset_sha256', 'timeout_seconds', 'ram_kb', 'instances_by_objective',
        'objective_filter', 'reference_manifest_sha256', 'reference_report_sha256',
        'reference_raw_sha256', 'runner_commit', 'runner_script_sha256',
        'run_script_sha256', 'cargo_lock_sha256', 'salvers', 'ipamir', 'component',
        'core_conflicts_override',
    )
    for key in shared:
        if mini.get(key) != cadi.get(key):
            raise ValueError(f'backend comparison changes {key}')
    for manifest, backend in [(mini, 'minisat'), (cadi, 'cadical')]:
        if manifest.get('measurement_context') != 'paired-screen' or not manifest.get('paired_run_id'):
            raise ValueError('comparison needs an explicit paired-screen context')
        if manifest['definition'].get('backend') != backend or manifest.get('backend_override') != backend:
            raise ValueError('backend labels differ from the locked method')
        if manifest['definition'].get('core_minimize_conflicts') != '0':
            raise ValueError('both backends need the same implemented core conflict budget')
    if mini['paired_run_id'] != cadi['paired_run_id']:
        raise ValueError('different paired run IDs')
    if cadi['definition'] != dict(mini['definition'], backend='cadical'):
        raise ValueError('methods differ in more than their SAT backend')
    mini_cpus, cadi_cpus = set(mini['cpu_affinity']), set(cadi['cpu_affinity'])
    if not mini_cpus or len(mini_cpus) != len(cadi_cpus) or mini_cpus & cadi_cpus:
        raise ValueError('backend screens need disjoint, equally sized CPU groups')

    for report in [mini_report, cadi_report]:
        if not report.get('audit_passed') or report.get('errors'):
            raise ValueError('compare only independently audited results')
    if mini_report['expected_runs'] != cadi_report['expected_runs']:
        raise ValueError('backend reports have different scopes')
    complete = mini_report['complete'] and cadi_report['complete']
    gain_maps = []
    for report in [mini_report, cadi_report]:
        gains = {(r['objective'], r['name']): r for r in report['newly_solved']}
        if len(gains) != len(report['newly_solved']):
            raise ValueError('duplicate gains')
        gain_maps.append(gains)
    a, b = gain_maps
    for key in a.keys() & b.keys():
        if not extended.common.same_number(a[key]['cost'], b[key]['cost']):
            raise ValueError('two claimed optima disagree')
    ratios = []
    for key in sorted(a.keys() & b.keys()):
        am, bc = a[key]['seconds'], b[key]['seconds']
        if not all(isinstance(t, (float, int)) and math.isfinite(t) and t > 0 for t in [am, bc]):
            raise ValueError('invalid paired runtime')
        ratios.append(dict(objective=key[0], name=key[1], minisat_seconds=am,
                           cadical_seconds=bc, cadical_speedup=am / bc))

    scores = {}
    for backend, report, gains in [('minisat', mini_report, a), ('cadical', cadi_report, b)]:
        total = sum(row['par2_seconds'] * row['instances'] for row in report['summary'])
        scores[backend] = dict(completed_runs=report['completed_runs'], proven=len(gains),
                               par2_total_seconds=total)
    winner = None
    if complete:
        sa, sb = scores['minisat'], scores['cadical']
        if sa['proven'] != sb['proven']:
            winner = 'minisat' if sa['proven'] > sb['proven'] else 'cadical'
        elif math.isclose(sa['par2_total_seconds'], sb['par2_total_seconds'], rel_tol=1e-12, abs_tol=1e-12):
            winner = 'tie'
        else:
            winner = 'minisat' if sa['par2_total_seconds'] < sb['par2_total_seconds'] else 'cadical'
    names = lambda items: [dict(objective=o, name=n) for o, n in sorted(items)]
    return dict(
        schema='paired-targeted-backends-v1', complete=complete,
        expected_runs_per_backend=mini_report['expected_runs'], scores=scores,
        winner_on_this_screen=winner,
        only_minisat=names(a.keys() - b.keys()) if complete else [],
        only_cadical=names(b.keys() - a.keys()) if complete else [],
        paired_runtime=ratios,
        cadical_paired_geomean_speedup=math.exp(sum(math.log(r['cadical_speedup']) for r in ratios) / len(ratios)) if ratios else None,
        measurement_context='paired-screen', paired_run_id=mini['paired_run_id'],
        runtime_scope='diagnostic concurrent measurements; serial reruns are required for the main runtime table',
        scope='only the locked unresolved objective/instance subset; full coverage and confirmation remain separate',
        errors=[], submission_passed=False,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--minisat', type=Path, required=True)
    parser.add_argument('--cadical', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--allow-partial', action='store_true')
    args = parser.parse_args()
    reports = [trial.audit_saved(root, args.reference) for root in [args.minisat, args.cadical]]
    manifests = [json.loads((root / 'manifest.json').read_text()) for root in [args.minisat, args.cadical]]
    result = compare_pair(*manifests, *reports)
    if not result['complete'] and not args.allow_partial:
        raise ValueError('finish both backend screens or explicitly request a partial comparison')
    result['source_manifest_sha256'] = {name: extended.focus.sha(root / 'manifest.json')
                                      for name, root in [('minisat', args.minisat), ('cadical', args.cadical)]}
    result['comparator_sha256'] = extended.focus.sha(Path(__file__))
    extended.save(args.output, result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
