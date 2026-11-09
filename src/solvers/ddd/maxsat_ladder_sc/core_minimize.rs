//! Shrink an already proved UNSAT core using a fixed number of extra checks.
use std::collections::HashSet;

use satcoder::{Bool, Lit};

pub(super) struct Outcome<L: Lit> {
    pub core: Vec<Bool<L>>,
    pub checks: usize,
    pub removed: usize,
    pub minimum_weight_increased: bool,
}

/// Re-query the complete proved core before deletion-based minimization.
/// A bounded/UNKNOWN query preserves the old proof. SAT contradicts that
/// proof and is an error; a returned core must be a nonempty unique subset.
pub(super) fn trim<L: Lit>(
    mut core: Vec<Bool<L>>,
    max_checks: usize,
    weight: impl Fn(Bool<L>) -> usize,
    mut query: impl FnMut(&[Bool<L>]) -> Result<Option<Vec<Bool<L>>>, String>,
    expired: impl Fn() -> bool,
) -> Result<Outcome<L>, String> {
    if core.is_empty() || core.iter().copied().collect::<HashSet<_>>().len() != core.len() {
        return Err("core trimming requires a nonempty core without duplicates".into());
    }
    let before = core.len();
    let initial_weight = core.iter().map(|&literal| weight(literal)).min().unwrap();
    let mut checks = 0;
    while checks < max_checks && core.len() > 1 && !expired() {
        checks += 1;
        let Some(mut reduced) = query(&core)? else { break; };
        if reduced.is_empty()
            || reduced.iter().copied().collect::<HashSet<_>>().len() != reduced.len()
            || reduced.iter().any(|literal| !core.contains(literal))
        {
            return Err("core trimming returned an empty, duplicate, or out-of-query core".into());
        }
        if reduced.len() == core.len() { break; }
        reduced.sort_unstable();
        core = reduced;
    }
    let final_weight = core.iter().map(|&literal| weight(literal)).min().unwrap();
    Ok(Outcome { removed: before - core.len(), core, checks,
                 minimum_weight_increased: final_weight > initial_weight })
}

/// `query` returns a newly proved UNSAT core, or None for SAT or an explicitly
/// abandoned inconclusive check. Neither permits removing an assumption.
/// Try removing low-weight assumptions first:
/// excluding one can increase the weight of the subsequent RC2 relaxation.
pub(super) fn minimize<L: Lit>(
    mut core: Vec<Bool<L>>,
    max_checks: usize,
    weight: impl Fn(Bool<L>) -> usize,
    mut query: impl FnMut(&[Bool<L>]) -> Option<Vec<Bool<L>>>,
    expired: impl Fn() -> bool,
) -> Result<Outcome<L>, String> {
    if core.is_empty() || core.iter().copied().collect::<HashSet<_>>().len() != core.len() {
        return Err("core minimization requires a nonempty core without duplicates".to_string());
    }
    let before = core.len();
    let initial_minimum = core.iter().map(|&literal| weight(literal)).min().unwrap();
    let mut order = core.clone();
    order.sort_by_key(|&literal| (weight(literal), literal));
    let mut checks = 0;
    for literal in order {
        if checks >= max_checks || core.len() <= 1 || expired() {
            break;
        }
        if !core.contains(&literal) {
            continue;
        }
        let trial = core.iter().copied().filter(|&item| item != literal).collect::<Vec<_>>();
        checks += 1;
        if let Some(mut reduced) = query(&trial) {
            let unique = reduced.iter().copied().collect::<HashSet<_>>();
            if reduced.is_empty() || unique.len() != reduced.len()
                || reduced.iter().any(|item| !trial.contains(item))
            {
                return Err("core minimization returned an empty, duplicate, or out-of-query core".to_string());
            }
            reduced.sort_unstable();
            core = reduced;
        }
    }
    let final_minimum = core.iter().map(|&literal| weight(literal)).min().unwrap();
    Ok(Outcome { removed: before-core.len(), core, checks,
                 minimum_weight_increased: final_minimum > initial_minimum })
}

#[cfg(test)]
mod tests {
    use super::*;
    use satcoder::{SatInstance, SatResultWithCore, SatSolverWithCore};

    fn query<L: Lit>(solver: &mut impl SatSolverWithCore<Lit=L>, assumptions: &[Bool<L>]) -> Option<Vec<Bool<L>>> {
        match solver.solve_with_assumptions(assumptions.iter().copied()) {
            SatResultWithCore::Sat(_) => None,
            SatResultWithCore::Unsat(core) => Some(core.iter().map(|&literal| Bool::Lit(literal)).collect()),
        }
    }

    #[test]
    fn trimming_accepts_only_proved_reductions_and_preserves_weighted_cost() {
        let mut solver = satcoder::solvers::minisat::Solver::new();
        let a=solver.new_var(); let b=solver.new_var(); let c=solver.new_var();
        SatInstance::add_clause(&mut solver,vec![!a,!b]);
        let weights=[(a,5),(b,7),(c,1)];
        let result=trim(vec![a,b,c],3,
            |literal| weights.iter().find(|(l,_)|*l==literal).unwrap().1,
            |assumptions| Ok(query(&mut solver,assumptions)),||false).unwrap();
        assert_eq!(result.core.len(),2); assert_eq!(result.removed,1);
        assert!(result.minimum_weight_increased); assert!(result.checks<=3);
        assert!(result.core.contains(&a) && result.core.contains(&b));
        assert!(query(&mut solver,&result.core).is_some());
        for mask in 0..8 {
            let values=[mask&1!=0,mask&2!=0,mask&4!=0];
            if values[0] && values[1] {continue;}
            let old=5*usize::from(!values[0])+7*usize::from(!values[1])+usize::from(!values[2]);
            let violations=usize::from(!values[0])+usize::from(!values[1]);
            let residual=5+2*usize::from(!values[1])+usize::from(!values[2])+5*(violations-1);
            assert_eq!(old,residual);
        }
    }

    #[test]
    fn trimming_fixed_point_budget_and_unknown_never_remove_assumptions() {
        let mut solver=satcoder::solvers::minisat::Solver::new();
        let a=solver.new_var(); let b=solver.new_var();
        for (budget,expired,calls) in [(0,false,0),(3,true,0),(3,false,1)] {
            let result=trim(vec![a,b],budget,|_|1,|_|Ok(None),||expired).unwrap();
            assert_eq!(result.core,vec![a,b]);assert_eq!(result.checks,calls);
        }
        let result=trim(vec![a,b],3,|_|1,|core|Ok(Some(core.to_vec())),||false).unwrap();
        assert_eq!(result.checks,1);assert_eq!(result.removed,0);
    }

    #[test]
    fn trimming_rejects_malformed_proofs_and_unexpected_sat() {
        let mut solver=satcoder::solvers::minisat::Solver::new();
        let a=solver.new_var();let b=solver.new_var();let c=solver.new_var();
        for proof in [vec![],vec![c],vec![a,a]] {
            assert!(trim(vec![a,b],3,|_|1,|_|Ok(Some(proof.clone())),||false).is_err());
        }
        assert!(trim(vec![a,b],3,|_|1,|_|Err("SAT contradicts proved core".into()),||false).is_err());
        assert!(trim(vec![a,a],0,|_|1,|_|Ok(None),||false).is_err());
    }

    #[test]
    fn low_weight_redundancy_is_removed_only_after_a_real_unsat_proof() {
        let mut solver = satcoder::solvers::minisat::Solver::new();
        let a = solver.new_var();
        let b = solver.new_var();
        let c = solver.new_var();
        SatInstance::add_clause(&mut solver, vec![!a,!b]);
        let weights = [(a,5),(b,7),(c,1)];
        let outcome = minimize(vec![c,b,a],4,
            |literal| weights.iter().find(|(l,_)| *l==literal).unwrap().1,
            |assumptions| query(&mut solver,assumptions), || false).unwrap();
        assert_eq!(outcome.removed,1);
        assert_eq!(outcome.checks,3);
        assert!(outcome.minimum_weight_increased);
        assert!(outcome.core.contains(&a) && outcome.core.contains(&b));
        assert!(query(&mut solver,&outcome.core).is_some());
        for literal in &outcome.core {
            let trial=outcome.core.iter().copied().filter(|item| item!=literal).collect::<Vec<_>>();
            assert!(query(&mut solver,&trial).is_none());
        }
        // Every feasible original assignment has exactly the same weighted
        // cost after RC2 processes the reduced core at minimum weight 5.
        for mask in 0..8 {
            let values=[mask&1!=0,mask&2!=0,mask&4!=0];
            if values[0] && values[1] { continue; }
            let old=5*usize::from(!values[0])+7*usize::from(!values[1])+usize::from(!values[2]);
            let count=usize::from(!values[0])+usize::from(!values[1]);
            let residual=5+2*usize::from(!values[1])+usize::from(!values[2])+5*(count-1);
            assert_eq!(old,residual);
        }
    }

    #[test]
    fn sat_deletion_budget_and_expired_deadline_preserve_the_proved_core() {
        let mut solver = satcoder::solvers::minisat::Solver::new();
        let a=solver.new_var(); let b=solver.new_var();
        SatInstance::add_clause(&mut solver,vec![!a,!b]);
        for (limit,expired,expected) in [(0,false,0),(1,false,1),(4,true,0)] {
            let original=vec![a,b];
            let outcome=minimize(original.clone(),limit,|_|1,
                |trial| query(&mut solver,trial),||expired).unwrap();
            assert_eq!(outcome.core,original);
            assert_eq!(outcome.checks,expected);
            assert_eq!(outcome.removed,0);
        }
    }

    #[test]
    fn malformed_solver_cores_fail_instead_of_changing_the_cost_bound() {
        let mut solver=satcoder::solvers::minisat::Solver::new();
        let a=solver.new_var(); let b=solver.new_var(); let c=solver.new_var();
        for reduced in [vec![],vec![c],vec![b,b]] {
            assert!(minimize(vec![a,b],1,|_|1,|_|Some(reduced.clone()),||false).is_err());
        }
        assert!(minimize(vec![a,a],1,|_|1,|_|None,||false).is_err());
    }
}
