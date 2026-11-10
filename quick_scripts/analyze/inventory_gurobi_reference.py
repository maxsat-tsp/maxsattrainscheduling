#!/usr/bin/env python3
"""Inventory audited Gurobi observations and identify missing longer-cutoff cases.

Reusing observations provides a coverage inventory, not paired runtime data.
"""
import argparse
import math
from pathlib import Path

import extended_timeout_experiments as ex


def summarize(records,cutoff):
    if not math.isfinite(cutoff) or cutoff<=0:raise ValueError('invalid inventory cutoff')
    coverage={};missing=[];censored=[];proof_sources={}
    for o in ex.audit.OBJECTIVES:
        count=0
        for n in ex.common.EXPECTED_NAMES:
            rows=[r for r in records if (r['objective'],r['name'])==(o,n)]
            def timed(r):return isinstance(r.get('seconds'),(float,int)) and math.isfinite(r['seconds']) and r['seconds']>=0
            proofs=[r for r in rows if r.get('proven') and r.get('upper_witness_verified') and timed(r) and r['seconds']<=cutoff]
            if proofs:
                count+=1;proof_sources[o+'/'+n]=[r['source'] for r in proofs]
            elif any(timed(r) and isinstance(r.get('timeout_seconds'),(float,int)) and r['timeout_seconds']>=cutoff and r['seconds']>=cutoff-.5 for r in rows):
                censored.append([o,n])
            else:missing.append([o,n])
        coverage[o]=count
    return dict(coverage=coverage,total=sum(coverage.values()),complete=not missing,
        missing_at_cutoff=missing,observed_no_proof_at_cutoff=censored,proof_sources=proof_sources)


def build_pool(references,archives):
    from compare_search_bounds import Pool
    class GurobiPool(Pool):
        def result(self,o,n,solve,method,budget,source,stdout=''):
            if method!='BigM-Gurobi':return
            before=len(self.records);super().result(o,n,solve,method,budget,source,stdout)
            if len(self.records)>before:
                self.records[-1].update(status=solve.get('status'),seconds=solve.get('total_time'),cost=solve.get('cost'),
                    proven=solve.get('status')=='ok' and ex.audit.bounds_prove_optimal(solve))
    if len(references)!=3 or {o for o,_ in references}!=set(ex.audit.OBJECTIVES):raise ValueError('supply each objective once')
    pool=GurobiPool([(o,n) for o in ex.audit.OBJECTIVES for n in ex.common.EXPECTED_NAMES])
    for o,path in references:
        path=Path(path);rows=ex.common.load_rows(path)
        if len(rows)!=72 or {n for n,_ in rows}!=set(ex.common.EXPECTED_NAMES):raise ValueError('incomplete/duplicate 72-instance source')
        pool.milp_json(o,path)
    for path in archives:pool.archive(Path(path))
    return pool


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference-json',nargs=2,action='append',required=True,metavar=('OBJECTIVE','JSON'))
    p.add_argument('--extended-archive',type=Path,action='append',default=[])
    p.add_argument('--cutoff',type=int,default=300);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();pool=build_pool(a.reference_json,a.extended_archive)
    report=dict(schema='gurobi-coverage-inventory-v1',dataset_sha256=ex.focus.dataset_hash(),cutoff_seconds=a.cutoff,
        evaluator_sha256=ex.focus.sha(Path(__file__)),
        at_120=summarize(pool.records,120),at_target=summarize(pool.records,a.cutoff),records=pool.records,
        source_sha256=pool.sources,submission_passed=False,runtime_comparable=False,
        scope='same-method reused observations; hardware equivalence and minor version differences accepted by the author; no paired runtime claim')
    ex.save(a.output,report)
    print(report['at_target']['coverage'], 'missing:',report['at_target']['missing_at_cutoff'])
