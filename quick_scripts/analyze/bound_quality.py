"""Minimization research priorities: optimality, new bounds, then time.

The caller validates solver evidence. This module never turns a timeout
into an optimum and never replaces a method's bounds by pooled bounds.
"""
import math

PRIORITIES=('proven_optimal','new_best_bound_cases','mean_unsolved_relative_gap','runtime')
EPS=1e-6


def number(value):
    if isinstance(value,bool):return None
    try:value=float(value)
    except (TypeError,ValueError):return None
    return value if math.isfinite(value) else None


def lower(value):
    value=number(value)
    if value is None:return None
    # All three TRP objectives are nonnegative integers. Do not count a
    # ceiling of the same fractional MILP bound as a new lower bound.
    nearest=round(value)
    return max(0,nearest if abs(value-nearest)<=EPS else math.ceil(value))


def upper(value):
    value=number(value)
    if value is None or value<0 or value>=2**31-1:return None
    nearest=round(value)
    return nearest if abs(value-nearest)<=EPS else math.floor(value)


def interval(lb,ub):
    lo,hi=lower(lb),upper(ub)
    if lo is not None and hi is not None and lo>hi:
        raise ValueError('inconsistent minimization bounds')
    return lo,hi


def relative_gap(lb,ub):
    lo,hi=interval(lb,ub)
    return None if lo is None or hi is None else (hi-lo)/max(1,abs(hi))


def summarize(records):
    pending=[r for r in records if not r['proven']]
    gaps=[relative_gap(r.get('lb'),r.get('ub')) for r in pending]
    known=[g for g in gaps if g is not None]
    missing=len(pending)-len(known)
    return dict(unsolved_instances=len(pending),unsolved_bounds_missing=missing,
        unsolved_gap_sum=sum(known),mean_unsolved_relative_gap=(sum(known)/len(known) if known else 0.0) if not missing else None,
        bounds_complete=not missing,
        bounds_verified=not missing and all(r.get('bounds_verified',False) for r in pending))


def compare(lb,ub,reference_lb,reference_ub):
    lo,hi=interval(lb,ub);rl,ru=interval(reference_lb,reference_ub)
    if (lo is not None and ru is not None and lo>ru) or (hi is not None and rl is not None and hi<rl):
        raise ValueError('candidate contradicts known bounds')
    better_lb=lo is not None and rl is not None and lo>rl
    better_ub=hi is not None and ru is not None and hi<ru
    worse_lb=lo is not None and rl is not None and lo<rl
    worse_ub=hi is not None and ru is not None and hi>ru
    return dict(lb=lo,ub=hi,reference_lb=rl,reference_ub=ru,
        lb_improved=better_lb,ub_improved=better_ub,lb_worse=worse_lb,ub_worse=worse_ub,
        lb_gain=lo-rl if lo is not None and rl is not None else None,
        ub_gain=ru-hi if hi is not None and ru is not None else None,
        new_bound=better_lb or better_ub,
        interval_dominates=(better_lb or better_ub) and not (worse_lb or worse_ub),
        tradeoff=(better_lb or better_ub) and (worse_lb or worse_ub),
        relative_gap=relative_gap(lo,hi),reference_relative_gap=relative_gap(rl,ru),
        reference_incomplete=rl is None or ru is None)


def envelope(records):
    lows=[];highs=[]
    for r in records:
        lo,hi=interval(r.get('lb'),r.get('ub'))
        if lo is not None:lows.append(lo)
        if hi is not None:highs.append(hi)
    lo=max(lows) if lows else None;hi=min(highs) if highs else None
    interval(lo,hi)
    return dict(lb=lo,ub=hi,
        lb_sources=[r['source'] for r in records if lo is not None and lower(r.get('lb'))==lo],
        ub_sources=[r['source'] for r in records if hi is not None and upper(r.get('ub'))==hi])


def preference(candidate,baseline):
    """Compare already aggregated, equal-scope summaries; missing bounds block time."""
    if candidate['proven_total']!=baseline['proven_total']:
        return (candidate['proven_total']>baseline['proven_total'],'optimal_coverage')
    # New-best counts are meaningful only against the same frozen pool.
    a=int(candidate.get('new_best_bound_cases') or 0);b=int(baseline.get('new_best_bound_cases') or 0)
    if a!=b:return (a>b,'new_best_bounds')
    if not candidate.get('bounds_verified') or not baseline.get('bounds_verified'):
        return (None,'bound_evidence_incomplete')
    a=candidate['mean_unsolved_relative_gap'];b=baseline['mean_unsolved_relative_gap']
    if not math.isclose(a,b,rel_tol=0,abs_tol=1e-12):return (a<b,'remaining_bound_gap')
    return (candidate['par2_sum']<baseline['par2_sum'],'runtime_after_equal_bounds')


def aggregate_summary(rows):
    pending=sum(int(r.get('not_proven',int(r['instances'])-int(r['proven_optimal']))) for r in rows)
    missing=sum(int(r.get('unsolved_bounds_missing',int(r['instances'])-int(r['proven_optimal']))) for r in rows)
    gap_sum=sum(float(r.get('unsolved_gap_sum') or 0) for r in rows)
    verified=not missing and all(r.get('bounds_verified',int(r['instances'])==int(r['proven_optimal'])) for r in rows)
    return dict(proven_total=sum(int(r['proven_optimal']) for r in rows),
        new_best_bound_cases=sum(int(r.get('new_best_bound_cases') or 0) for r in rows),
        unsolved_instances=pending,unsolved_bounds_missing=missing,
        mean_unsolved_relative_gap=(gap_sum/pending if pending else 0.0) if not missing else None,
        bounds_verified=bool(verified))


def rank_key(row):
    gap=row.get('mean_unsolved_relative_gap')
    return (-row['proven_total'],-int(row.get('new_best_bound_cases') or 0),
        gap if gap is not None else math.inf,
        row['par2_sum'] if row.get('bounds_verified') else math.inf,row.get('tag',''))
