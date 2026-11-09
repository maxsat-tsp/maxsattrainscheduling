//! Grow an intrinsic AM1 clique from an already proved two-preference core.
//! Every additional edge needs a fresh UNSAT proof; SAT/UNKNOWN adds no edge.
use satcoder::{Bool, Lit};
use std::collections::HashSet;

pub(super) struct Clique<L: Lit> {
    pub literals: Vec<Bool<L>>,
    pub checks: usize,
}

pub(super) fn grow<L: Lit>(
    seed: [Bool<L>; 2],
    candidates: Vec<Bool<L>>,
    budget: usize,
    mut proved_incompatible: impl FnMut(Bool<L>, Bool<L>) -> Result<bool, String>,
    expired: impl Fn() -> bool,
) -> Result<Clique<L>, String> {
    if seed[0] == seed[1] { return Err("AM1 seed requires two distinct preferences".into()); }
    let mut literals=seed.to_vec();
    let mut seen=seed.into_iter().collect::<HashSet<_>>();
    let mut checks=0;
    for candidate in candidates {
        if !seen.insert(candidate) { continue; }
        if checks>=budget || expired() { break; }
        let mut compatible_with_clique=true;
        for &member in &literals {
            if checks>=budget || expired() { compatible_with_clique=false;break; }
            checks+=1;
            if !proved_incompatible(candidate,member)? {
                compatible_with_clique=false;break;
            }
        }
        if compatible_with_clique { literals.push(candidate); }
    }
    Ok(Clique {literals,checks})
}

/// Under AM1, sum w_i * !s_i = m*(n-1) + m*!(OR s_i)
///                              + sum (w_i-m)*!s_i.
pub(super) fn reweight(weights: &[usize]) -> Result<(usize,usize,Vec<usize>),String> {
    if weights.len()<2 || weights.contains(&0) {return Err("AM1 needs positive residual weights".into());}
    let minimum=*weights.iter().min().unwrap();
    let fixed=minimum.checked_mul(weights.len()-1).ok_or("AM1 cost overflow")?;
    Ok((fixed,minimum,weights.iter().map(|w|w-minimum).collect()))
}

#[cfg(test)]
mod tests {
    use super::*;
    use satcoder::{SatInstance,SatResultWithCore,SatSolverWithCore};

    #[test]
    fn weighted_am1_identity_holds_for_every_allowed_assignment() {
        for weights in [vec![1,1,1],vec![5,7,1],vec![2,9,4,8]] {
            let (fixed,minimum,residual)=reweight(&weights).unwrap();
            for mask in 0usize..(1<<weights.len()) {
                if mask.count_ones()>1 {continue;}
                let original=weights.iter().enumerate().filter(|(i,_)|mask&(1<<i)==0).map(|(_,w)|w).sum::<usize>();
                let rewritten=fixed+minimum*usize::from(mask==0)+residual.iter().enumerate()
                    .filter(|(i,_)|mask&(1<<i)==0).map(|(_,w)|w).sum::<usize>();
                assert_eq!(original,rewritten);
            }
        }
        assert!(reweight(&[0,1]).is_err());assert!(reweight(&[1]).is_err());
        assert!(reweight(&[usize::MAX,usize::MAX,usize::MAX]).is_err());
    }

    #[test]
    fn real_sat_proofs_grow_a_clique_but_reject_a_feasible_pair() {
        let mut solver=satcoder::solvers::minisat::Solver::new();
        let a=solver.new_var();let b=solver.new_var();let c=solver.new_var();let d=solver.new_var();
        for pair in [[a,b],[a,c],[b,c]] {SatInstance::add_clause(&mut solver,vec![!pair[0],!pair[1]]);}
        let result=grow([a,b],vec![c,d],8,|x,y|Ok(matches!(
            solver.solve_with_assumptions([x,y]),SatResultWithCore::Unsat(_))),||false).unwrap();
        assert_eq!(result.literals,vec![a,b,c]);
        assert_eq!(result.checks,3);
    }

    #[test]
    fn partial_proofs_unknowns_and_deadlines_never_complete_a_clique() {
        let mut solver=satcoder::solvers::minisat::Solver::new();
        let a=solver.new_var();let b=solver.new_var();let c=solver.new_var();
        for (budget,expired,expected_checks) in [(0,false,0),(1,false,1),(4,true,0)] {
            let result=grow([a,b],vec![c,c],budget,|_,_|Ok(true),||expired).unwrap();
            assert_eq!(result.literals,vec![a,b]);assert_eq!(result.checks,expected_checks);
        }
        let result=grow([a,b],vec![c],4,|_,_|Ok(false),||false).unwrap();
        assert_eq!(result.literals,vec![a,b]);assert_eq!(result.checks,1);
        assert!(grow([a,a],vec![],0,|_,_|Ok(true),||false).is_err());
        assert!(grow([a,b],vec![c],4,|_,_|Err("query failure".into()),||false).is_err());
    }
}
