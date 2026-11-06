//! Bounded RC2 core exhaustion: raise a cardinality floor only after UNSAT.
//! A SAT or inconclusive check never changes the last proved floor.

#[derive(Debug, PartialEq, Eq)]
pub(super) struct Outcome {
    pub bound: usize,
    pub checks: usize,
    pub inconclusive: usize,
}

/// The input core already proves at least one violated preference. Query
/// whether at most `bound` violations remain possible in the hard formula.
/// `Some(true)` means proved UNSAT; `Some(false)` means SAT; None is UNKNOWN.
/// The caller owns the incremental totalizer and validates returned cores.
pub(super) fn exhaust(
    inputs: usize,
    max_checks: usize,
    mut query: impl FnMut(usize) -> Result<Option<bool>, String>,
    expired: impl Fn() -> bool,
) -> Result<Outcome, String> {
    if inputs < 2 {
        return Err("core exhaustion requires at least two inputs".to_string());
    }
    let mut outcome = Outcome { bound: 1, checks: 0, inconclusive: 0 };
    while outcome.bound < inputs && outcome.checks < max_checks && !expired() {
        outcome.checks += 1;
        match query(outcome.bound)? {
            Some(true) => outcome.bound += 1,
            Some(false) => break,
            None => { outcome.inconclusive += 1; break; }
        }
    }
    Ok(outcome)
}

#[cfg(test)]
mod tests {
    use super::*;
    use satcoder::{constraints::Totalizer, Bool, SatInstance, SatResultWithCore, SatSolverWithCore};

    #[test]
    fn only_new_unsat_proofs_raise_the_floor_and_budgets_are_respected() {
        for (limit, answer, expected) in [
            (0, Some(true), Outcome { bound: 1, checks: 0, inconclusive: 0 }),
            (2, Some(true), Outcome { bound: 3, checks: 2, inconclusive: 0 }),
            (9, Some(true), Outcome { bound: 4, checks: 3, inconclusive: 0 }),
            (9, Some(false), Outcome { bound: 1, checks: 1, inconclusive: 0 }),
            (9, None, Outcome { bound: 1, checks: 1, inconclusive: 1 }),
        ] {
            assert_eq!(exhaust(4, limit, |_| Ok(answer), || false).unwrap(), expected);
        }
        assert_eq!(exhaust(4, 9, |_| panic!("expired queries must not run"), || true).unwrap().bound, 1);
        let mut answers = [Some(true), None].into_iter();
        assert_eq!(exhaust(4, 9, |_| Ok(answers.next().unwrap()), || false).unwrap(),
                   Outcome { bound: 2, checks: 2, inconclusive: 1 });
        assert!(exhaust(1, 4, |_| Ok(Some(true)), || false).is_err());
        assert!(exhaust(3, 4, |_| Err("invalid native proof".to_string()), || false).is_err());
    }

    #[test]
    fn native_proofs_preserve_every_feasible_weighted_assignment() {
        for inputs in 2..=5 {
            for max_true in 0..inputs {
                for budget in [0, 1, 4] {
                    let mut solver = satcoder::solvers::minisat::Solver::new();
                    let preferences = (0..inputs).map(|_| solver.new_var()).collect::<Vec<_>>();
                    // At most max_true preferences may hold. This hard formula
                    // proves at least inputs-max_true violations, independently
                    // of every other soft preference in the global problem.
                    let hard = Totalizer::count(&mut solver, preferences.iter().copied(), max_true as u32);
                    SatInstance::add_clause(&mut solver, [!hard.rhs()[max_true]]);
                    let mut totalizer = Totalizer::count(&mut solver, preferences.iter().map(|p| !*p), 1);
                    let outcome = exhaust(inputs, budget, |bound| {
                        totalizer.increase_bound(&mut solver, bound as u32);
                        let assumption = !totalizer.rhs()[bound];
                        match solver.solve_with_assumptions([assumption]) {
                            SatResultWithCore::Sat(_) => Ok(Some(false)),
                            SatResultWithCore::Unsat(core) => {
                                assert_eq!(core.iter().copied().map(Bool::Lit).collect::<Vec<_>>(), vec![assumption]);
                                Ok(Some(true))
                            },
                        }
                    }, || false).unwrap();
                    assert_eq!(outcome.bound, (inputs-max_true).min(1+budget));
                    let weights = (0..inputs).map(|i| 2+i*3).collect::<Vec<_>>();
                    let minimum = *weights.iter().min().unwrap();
                    for mask in 0..(1usize<<inputs) {
                        let n_true = mask.count_ones() as usize;
                        if n_true > max_true { continue; }
                        let violated = inputs-n_true;
                        let original: usize = weights.iter().enumerate()
                            .filter(|(i,_)| mask&(1<<i)==0).map(|(_,w)| *w).sum();
                        let residual: usize = weights.iter().enumerate()
                            .filter(|(i,_)| mask&(1<<i)==0).map(|(_,w)| *w-minimum).sum();
                        assert!(violated >= outcome.bound);
                        assert_eq!(original, minimum*outcome.bound+residual+minimum*(violated-outcome.bound));
                    }
                }
            }
        }
    }
}
