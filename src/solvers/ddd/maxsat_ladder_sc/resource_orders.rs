//! Reuse one optional order literal for each *detected* pair of occupations.
//! Every feasible schedule admits an orientation for that pair. Keeping the
//! same orientation across time thresholds strengthens the SAT relaxation.
use std::collections::{HashMap, HashSet};

use satcoder::{Bool, Lit, SatInstance};

pub(super) struct ResourceOrders<L: Lit> {
    bits: HashMap<(u32, u32), Bool<L>>,
    rows: HashSet<(u32, u32, i32)>,
}

impl<L: Lit> ResourceOrders<L> {
    pub fn new() -> Self {
        Self {
            bits: HashMap::new(),
            rows: HashSet::new(),
        }
    }

    /// `first_after_second` means first entry >= the current second exit;
    /// `second_after_first` means second entry >= the current first exit.
    /// Guards mean the corresponding exit is at least the supplied threshold.
    #[allow(clippy::too_many_arguments)]
    pub fn add(
        &mut self,
        solver: &mut impl SatInstance<L>,
        first: u32,
        second: u32,
        first_exit: i32,
        second_exit: i32,
        first_guard: Bool<L>,
        second_guard: Bool<L>,
        first_after_second: Bool<L>,
        second_after_first: Bool<L>,
    ) -> (bool, usize) {
        assert_ne!(first, second);
        let key = if first < second {
            (first, second)
        } else {
            (second, first)
        };
        let created = !self.bits.contains_key(&key);
        let canonical = *self.bits.entry(key).or_insert_with(|| solver.new_var());
        let first_before_second = if first < second {
            canonical
        } else {
            !canonical
        };
        let mut added = 0;
        if self.rows.insert((first, second, first_exit)) {
            solver.add_clause(vec![!first_before_second, !first_guard, second_after_first]);
            added += 1;
        }
        if self.rows.insert((second, first, second_exit)) {
            solver.add_clause(vec![first_before_second, !second_guard, first_after_second]);
            added += 1;
        }
        (created, added)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use satcoder::{SatResultWithCore, SatSolverWithCore};

    #[test]
    fn a_single_refinement_projects_to_the_original_overlap_clause() {
        for mask in 0..16 {
            let mut solver = satcoder::solvers::minisat::Solver::new();
            let variables = (0..4).map(|_| solver.new_var()).collect::<Vec<_>>();
            let mut orders = ResourceOrders::new();
            orders.add(
                &mut solver,
                0,
                1,
                10,
                20,
                variables[0],
                variables[1],
                variables[2],
                variables[3],
            );
            let values = (0..4).map(|i| mask & (1 << i) != 0).collect::<Vec<_>>();
            let expected = !values[0] || !values[1] || values[2] || values[3];
            let result = solver.solve_with_assumptions(
                variables
                    .iter()
                    .zip(&values)
                    .map(|(literal, value)| if *value { *literal } else { !*literal }),
            );
            assert_eq!(matches!(result, SatResultWithCore::Sat(_)), expected);
        }
    }

    #[test]
    fn reversed_and_repeated_pairs_reuse_the_same_order_and_rows() {
        let mut solver = satcoder::solvers::minisat::Solver::new();
        let v = (0..4).map(|_| solver.new_var()).collect::<Vec<_>>();
        let mut orders = ResourceOrders::new();
        assert_eq!(
            orders.add(&mut solver, 0, 1, 10, 20, v[0], v[1], v[2], v[3]),
            (true, 2)
        );
        assert_eq!(
            orders.add(&mut solver, 0, 1, 10, 20, v[0], v[1], v[2], v[3]),
            (false, 0)
        );
        assert_eq!(
            orders.add(&mut solver, 1, 0, 20, 10, v[1], v[0], v[3], v[2]),
            (false, 0)
        );
        assert_eq!(orders.bits.len(), 1);
    }

    #[test]
    fn several_thresholds_preserve_both_orders_of_every_feasible_schedule() {
        // Two length-2 occupations; check all starts in [0, 6], with order
        // implications learned at two different exit thresholds.
        for first in 0..=6 {
            for second in 0..=6 {
                if !(first + 2 <= second || second + 2 <= first) {
                    continue;
                }
                let mut solver = satcoder::solvers::minisat::Solver::new();
                let mut orders = ResourceOrders::new();
                for threshold in [2, 4] {
                    orders.add(
                        &mut solver,
                        0,
                        1,
                        threshold,
                        threshold,
                        Bool::Const(first + 2 >= threshold),
                        Bool::Const(second + 2 >= threshold),
                        Bool::Const(first >= threshold),
                        Bool::Const(second >= threshold),
                    );
                }
                assert!(matches!(
                    solver.solve_with_assumptions(std::iter::empty::<
                        Bool<satcoder::solvers::minisat::Lit>,
                    >()),
                    SatResultWithCore::Sat(_)
                ));
            }
        }
    }
}
