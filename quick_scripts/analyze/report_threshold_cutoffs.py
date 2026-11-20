"""Count checked proofs by cutoff and identify missing SAT baseline cases."""
import argparse
import json
from pathlib import Path
import tarfile
import tempfile

import extended_timeout_experiments as ex
from inventory_gurobi_reference import summarize

RESEARCH = ex.REPO/'results/sat_research'
SAT_SOURCES = (
    'extended_300_20261106/progress_82/raw_snapshot.tar.gz',
    'cadical_300_20261106/minisat_diagnostic/raw_snapshot.tar.gz',
)


def baseline_rows(snapshot):
    """Use on-time verified proofs and keep incomplete observations visible."""
    tags = {'CSOnet': 'maxsat_ddd_ladder_sc', 'MaxSAT-Journal': 'maxsat_ddd_ladder'}
    observations = {tag: [] for tag in tags}
    with tempfile.TemporaryDirectory(prefix='sat-baseline-120-') as folder:
        root = Path(folder)
        with tarfile.open(snapshot) as archive:
            for tag in tags:
                (root/tag).mkdir()
                for filename in ('config.txt', *(o+'.json' for o in ex.audit.OBJECTIVES)):
                    member = f'{tag}/{filename}'
                    (root/tag/filename).write_bytes(archive.extractfile(member).read())
        for tag, solver in tags.items():
            config = ex.audit.read_config(root/tag/'config.txt')
            if config['tag'] != tag or config['solver'] != solver:
                raise ValueError('bad full baseline solver configuration')
            rows = ex.audit.load_json_method(root/tag, config, 120)
            if len(rows) != 216 or any(r['errors'] for r in rows):
                raise ValueError('bad full baseline observations')
            observations[tag] += [dict(objective=r['objective'],name=r['name'],proven=r['proven'],
                upper_witness_verified=r['proven'],seconds=r['time'],cost=r['solve'].get('cost'),
                timeout_seconds=120,source=str(snapshot)) for r in rows]
    for relative in SAT_SOURCES:
        path = RESEARCH/relative
        with tarfile.open(path) as archive:
            manifest = json.load(archive.extractfile('manifest.json'))
            report = json.load(archive.extractfile('extended_audit.json'))
            if report['errors']:
                raise ValueError('historical baseline audit contains errors')
            if (manifest['methods']['CSOnet']['backend'] != 'minisat'
                    or manifest['methods']['MaxSAT-Journal']['solver'] != 'maxsat_ddd'):
                raise ValueError('historical baseline uses a different solver')
            for row in report['case_bounds']:
                tag, objective, name = (row[k] for k in ('method','objective','name'))
                if tag not in tags:
                    continue
                member = f'cases/{tag}/{objective}/{name}/{objective}.json'
                raw = json.load(archive.extractfile(member))
                if len(raw) != 1 or raw[0]['name'] != name or len(raw[0]['solves']) != 1:
                    raise ValueError('bad historical case identity')
                solve = raw[0]['solves'][0]
                if (tag == 'CSOnet' and solve.get('maxsat_backend') != 'minisat'
                        or tag == 'MaxSAT-Journal' and solve['solver_name'] != 'MaxSatDddLadderRC2'):
                    raise ValueError('bad historical SAT backend')
                if row['proven'] and (solve['status'] != 'ok'
                        or not ex.audit.bounds_prove_optimal(solve)
                        or ex.common.independently_verify_solution(name,objective,solve)):
                    raise ValueError('historical proof has an invalid schedule or bound')
                observations[tag].append(dict(objective=objective,name=name,proven=row['proven'],
                    upper_witness_verified=row['proven'],seconds=solve['total_time'],cost=solve.get('cost'),
                    timeout_seconds=solve['timeout_seconds'],source=f'{relative}#{member}'))
    return observations


def report(snapshot, candidate):
    comparison = json.loads(candidate.read_text())
    rows = comparison['cases']
    expected = {(o,n) for o in ex.audit.OBJECTIVES for n in ex.common.EXPECTED_NAMES}
    if (not comparison.get('candidate_audit_passed') or not comparison['full_comparison']['complete']
            or len(rows) != 216 or {(r['objective'],r['name']) for r in rows} != expected):
        raise ValueError('compare cutoffs only for a complete audited candidate')
    observations = baseline_rows(snapshot)
    by_cutoff = {}
    for limit in sorted({120,150,300,comparison['candidate_cutoff_seconds']}):
        if limit > comparison['candidate_cutoff_seconds']:
            continue
        baseline = {tag:summarize(records,limit) for tag,records in observations.items()}
        for data in baseline.values():
            del data['proof_sources']
        coverage = {o:sum(r['proven'] and r['seconds'] <= limit for r in rows if r['objective']==o)
                    for o in ex.audit.OBJECTIVES}
        by_cutoff[str(limit)] = dict(candidate_coverage=coverage,
            candidate_total=sum(coverage.values()), audited_sat_baselines=baseline)
    return dict(by_cutoff=by_cutoff, data_sha256=ex.focus.dataset_hash(),
        inputs_sha256={str(p):ex.focus.sha(p) for p in (snapshot,candidate,*(RESEARCH/r for r in SAT_SOURCES))},
        scope='shorter cutoffs count proofs within the recorded elapsed time; mixed source timings are diagnostic')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-snapshot',type=Path,required=True)
    parser.add_argument('--full-candidate',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    ex.save(args.output,report(args.baseline_snapshot,args.full_candidate))
