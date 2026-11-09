#!/usr/bin/env python3
"""Audit the tight rerun and derive corrected CSVs, preserving original data."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import tarfile
import tempfile

import extended_timeout_experiments as ex


def audit_native(archive,original):
    with tempfile.TemporaryDirectory(prefix='cplex-bound-recheck-') as folder:
        base=Path(folder)
        with tarfile.open(archive) as t:
            for member in t.getmembers():
                dest=(base/member.name).resolve()
                if base.resolve() not in dest.parents or member.issym() or member.islnk():raise ValueError('unsafe recheck archive')
            t.extractall(base)
        root=base/'tight_recheck';m=json.loads((root/'manifest.json').read_text())
        if m['schema']!='cplex-disputed-bound-recheck-v1' or m['dataset_sha256']!=ex.focus.dataset_hash() or m['uses_witness_inside_solver'] is not False or m['timeout_seconds']!=120:
            raise ValueError('wrong native rerun or dataset')
        lps=list(root.glob('*.lp'))
        if len(lps)!=1 or ex.focus.sha(lps[0])!=m['lp_sha256'] or ex.focus.sha(root/'independent_witness.json')!=m['witness_sha256']:
            raise ValueError('changed native LP or comparison witness')
        o,n=m['objective'],m['name']
        saved=ex.common.load_rows(root/(o+'.json'))
        if len(saved)!=1 or saved[0][0]!=n:raise ValueError('wrong rerun identity')
        solve=saved[0][1]
        rebuilt=ex.cplex_result(root/'schedule.sol',root/'cplex.log',n,o,m['timeout_seconds'],solve['total_time'])
        if rebuilt!=solve or not ex.audit.bounds_prove_optimal(solve):raise ValueError('native rerun does not prove its checked optimum')
        witness=json.loads((root/'independent_witness.json').read_text())
        if ex.common.independently_verify_solution(n,o,witness) or solve['cost']>witness['cost']:
            raise ValueError('rerun conflicts with the independent witness')
        with tarfile.open(original) as t:
            prefix=f'cases/BigM-CPLEX/{o}/{n}/'
            old_lps=[x for x in t.getmembers() if x.name.startswith(prefix) and x.name.endswith('.lp')]
            if len(old_lps)!=1 or hashlib.sha256(t.extractfile(old_lps[0]).read()).hexdigest()!=m['lp_sha256']:
                raise ValueError('rerun changed the original LP')
            old=json.load(t.extractfile(prefix+o+'.json'))[0]['solves'][0]
        return dict(manifest=m,solve=solve,original_solve=old,audit_passed=True)


def run(args):
    report=audit_native(args.archive,args.original_archive);m=report['manifest'];solve=report['solve']
    output=args.output;output.mkdir(parents=True,exist_ok=True);csv_dir=output/'cplex_csv';csv_dir.mkdir(exist_ok=True)
    inputs={str(args.archive):ex.focus.sha(args.archive),str(args.original_archive):ex.focus.sha(args.original_archive)}
    for o in ex.audit.OBJECTIVES:
        path=args.reference_csv/f'results_bigm_{o}_120s.csv';inputs[str(path)]=ex.focus.sha(path)
        with path.open(newline='') as f:reader=csv.DictReader(f);fields=reader.fieldnames;rows=list(reader)
        if len(rows)!=72 or {r['name'] for r in rows}!=set(ex.common.EXPECTED_NAMES):raise ValueError('incomplete/duplicate CSV cases')
        if o==m['objective']:
            row=next(r for r in rows if r['name']==m['name'])
            if float(row['cost'])!=report['original_solve']['cost']:raise ValueError('CSV is not the original disputed result')
            # Reuse the measured export of exactly the same LP; do not attach
            # the invalid proof's old solve time to the new optimum.
            row.update(status='ok',cost=solve['cost'],lb=solve['lb'],ub=solve['ub'],valid='true',validation_status='passed',
                total_time=solve['total_time']+report['original_solve']['build_time'])
        with (csv_dir/path.name).open('w',newline='') as f:
            w=csv.DictWriter(f,fields,lineterminator='\n');w.writeheader();w.writerows(rows)
    report.update(schema='cplex-tight-csv-correction-v1',input_sha256=inputs,coverage=dict(finsteps123=72,infsteps180=67,cont=66),
        total_proven=205,runtime_scope='diagnostic; corrected row combines original identical LP export time and new tight solve time',
        submission_passed=False)
    ex.save(output/'independent_audit.json',report)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('archive','original-archive','reference-csv','output'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
