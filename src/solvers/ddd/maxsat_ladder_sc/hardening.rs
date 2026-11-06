//! Fix a residual soft preference when violating it alone exceeds a verified UB.
use satcoder::{Bool, Lit};

pub(super) fn select<L: Lit>(
    terms: impl IntoIterator<Item = (Bool<L>, usize)>,
    lower: i32,
    upper: i32,
) -> Result<Vec<Bool<L>>, String> {
    if lower < 0 || upper < lower {
        return Err(format!(
            "invalid verified bounds for cost hardening: LB={lower}, UB={upper}"
        ));
    }
    let gap = (upper - lower) as usize;
    let mut selected = Vec::new();
    for (preference, weight) in terms {
        // Equality is allowed: an optimum can cost exactly UB.
        if weight > gap && preference != Bool::Const(true) {
            if preference == Bool::Const(false) {
                return Err("an unavoidable residual cost exceeds the verified budget".to_string());
            }
            selected.push(preference);
        }
    }
    selected.sort_unstable();
    selected.dedup();
    Ok(selected)
}

#[cfg(test)]
mod tests {
    use super::*;
    use satcoder::{constraints::Totalizer, SatInstance, SatResultWithCore, SatSolverWithCore};

    #[test]
    fn every_assignment_within_the_weighted_budget_survives() {
        for weights in [[1, 3, 8], [0, 2, 2], [4, 4, 4]] {
            for lower in 0..=3 {
                for upper in lower..=16 {
                    let mut solver = satcoder::solvers::minisat::Solver::new();
                    let vars = (0..3).map(|_| solver.new_var()).collect::<Vec<_>>();
                    let fixed = select(vars.iter().copied().zip(weights), lower, upper).unwrap();
                    for literal in fixed {
                        SatInstance::add_clause(&mut solver, vec![literal]);
                    }
                    for mask in 0..8 {
                        let violated = (0..3)
                            .filter(|i| mask & (1 << i) == 0)
                            .map(|i| weights[i])
                            .sum::<usize>();
                        if lower as usize + violated <= upper as usize {
                            let assumptions = vars.iter().enumerate().map(|(i, v)| {
                                if mask & (1 << i) != 0 {
                                    *v
                                } else {
                                    !*v
                                }
                            });
                            assert!(matches!(
                                solver.solve_with_assumptions(assumptions),
                                SatResultWithCore::Sat(_)
                            ));
                        }
                    }
                }
            }
        }
    }

    #[test]
    fn residual_weights_after_a_core_keep_every_original_feasible_budget_assignment() {
        // Original costs: 3*!a + 5*!b + 8*!c, with !a OR !b.
        // After processing core {a,b} at weight 3, the residual objective is
        // 3 + 2*!b + 3*(count(!a,!b)>1) + 8*!c.
        for upper in 3..=16 {
            let mut solver = satcoder::solvers::minisat::Solver::new();
            let a = solver.new_var();
            let b = solver.new_var();
            let c = solver.new_var();
            SatInstance::add_clause(&mut solver, vec![!a, !b]);
            let counter = Totalizer::count(&mut solver, [!a, !b], 1);
            for literal in select([(b, 2), (!counter.rhs()[1], 3), (c, 8)], 3, upper).unwrap() {
                SatInstance::add_clause(&mut solver, vec![literal]);
            }
            for mask in 0..8 {
                let values = [mask & 1 != 0, mask & 2 != 0, mask & 4 != 0];
                let original = 3 * usize::from(!values[0])
                    + 5 * usize::from(!values[1])
                    + 8 * usize::from(!values[2]);
                if !(values[0] && values[1]) && original <= upper as usize {
                    let assumptions =
                        [a, b, c]
                            .into_iter()
                            .zip(values)
                            .map(|(lit, value)| if value { lit } else { !lit });
                    assert!(matches!(
                        solver.solve_with_assumptions(assumptions),
                        SatResultWithCore::Sat(_)
                    ));
                }
            }
        }
    }

    #[test]
    fn equality_is_not_hardened_and_tightening_is_deterministic() {
        let mut solver = satcoder::solvers::minisat::Solver::new();
        let a = solver.new_var();
        let b = solver.new_var();
        assert!(select([(a, 4)], 1, 5).unwrap().is_empty());
        assert!(select([(a, 6), (b, 3)], 0, 8).unwrap().is_empty());
        assert_eq!(select([(a, 6), (b, 3)], 0, 5).unwrap(), vec![a]);
        let mut expected = vec![a, b];
        expected.sort_unstable();
        assert_eq!(select([(b, 3), (a, 6)], 3, 5).unwrap(), expected);
        assert_eq!(select([(a, 6), (b, 3)], 3, 5).unwrap(), expected);
    }

    #[test]
    fn inconsistent_verified_bounds_fail_instead_of_restricting_the_model() {
        type L = satcoder::solvers::minisat::Lit;
        assert!(select(std::iter::empty::<(Bool<L>, usize)>(), -1, 2).is_err());
        assert!(select(std::iter::empty::<(Bool<L>, usize)>(), 3, 2).is_err());
        assert!(select([(Bool::<L>::Const(false), 2)], 0, 1).is_err());
        assert!(select([(Bool::<L>::Const(true), 2)], 0, 1)
            .unwrap()
            .is_empty());
    }
}
