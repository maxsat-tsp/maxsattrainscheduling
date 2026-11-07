//! Reuse one optional order literal for each *detected* pair of occupations.
//! Every feasible schedule admits an orientation for that pair. Keeping the
//! same orientation across time thresholds strengthens the SAT relaxation.
use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};

use satcoder::{Bool, Lit, SatInstance};

pub(super) struct ResourceOrders<L: Lit> {
    bits: HashMap<(u32, u32), Bool<L>>,
    rows: HashSet<(u32, u32, i32)>,
    transitivity: bool,
    neighbors: BTreeMap<u32, BTreeSet<u32>>,
    cycle_clauses: HashSet<Vec<Bool<L>>>,
}

impl<L: Lit> ResourceOrders<L> {
    pub fn new(transitivity: bool) -> Self {
        Self {
            bits: HashMap::new(),
            rows: HashSet::new(),
            transitivity,
            neighbors: BTreeMap::new(),
            cycle_clauses: HashSet::new(),
        }
    }

    pub fn separate_cycle(
        &mut self,
        topology: &super::order_cycles::Topology,
        mut value: impl FnMut(Bool<L>) -> bool,
    ) -> Result<Option<Vec<Bool<L>>>, String> {
        let mut arcs=topology.arcs();
        let mut pairs=self.bits.iter().collect::<Vec<_>>();
        pairs.sort_unstable_by_key(|(key,_)| **key);
        for (&(a,b), &bit) in pairs {
            let (first,second,guard)=if value(bit) {(a,b,bit)} else {(b,a,!bit)};
            arcs.push(topology.ordered(first as usize,second as usize,guard));
        }
        if let Some(clause)=super::order_cycles::separate(topology.next.len(),arcs)? {
            if !self.cycle_clauses.insert(clause.clone()) {
                return Err("SAT model violates an already added temporal cycle clause".into());
            }
            Ok(Some(clause))
        } else { Ok(None) }
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
    ) -> (bool, usize, usize) {
        assert_ne!(first, second);
        let key = if first < second {
            (first, second)
        } else {
            (second, first)
        };
        let created = !self.bits.contains_key(&key);
        let canonical = *self.bits.entry(key).or_insert_with(|| solver.new_var());
        let mut triangles = 0;
        if created && self.transitivity {
            // Only close triangles whose other two order bits already exist.
            // Sorted neighbors give a fixed clause order without creating any
            // additional pair variables. Each triangle is closed exactly once.
            if let (Some(left), Some(right)) =
                (self.neighbors.get(&first), self.neighbors.get(&second))
            {
                for third in left.intersection(right) {
                    let mut visits = [first, second, *third];
                    visits.sort_unstable();
                    let [a, b, c] = visits;
                    let ab = self.bits[&(a, b)];
                    let bc = self.bits[&(b, c)];
                    let ac = self.bits[&(a, c)];
                    solver.add_clause(vec![!ab, !bc, ac]);
                    solver.add_clause(vec![ab, bc, !ac]);
                    triangles += 1;
                }
            }
            self.neighbors.entry(first).or_default().insert(second);
            self.neighbors.entry(second).or_default().insert(first);
        }
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
        (created, added, triangles)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use satcoder::prelude::SymbolicModel;
    use satcoder::{SatResultWithCore, SatSolverWithCore};

    fn add_unrestricted_pair(
        orders: &mut ResourceOrders<satcoder::solvers::minisat::Lit>,
        solver: &mut satcoder::solvers::minisat::Solver,
        first: u32,
        second: u32,
    ) -> usize {
        // False guards leave the orientation free, for testing transitivity.
        orders
            .add(
                solver,
                first,
                second,
                1,
                1,
                false.into(),
                false.into(),
                true.into(),
                true.into(),
            )
            .2
    }

    #[test]
    fn temporal_cycle_cut_blocks_only_impossible_orders_and_respects_exact_exit() {
        use super::super::order_cycles::Topology;
        for zero in [false,true] {
          for a in [false,true] { for b in [false,true] {
            let mut solver=satcoder::solvers::minisat::Solver::new();
            let mut orders=ResourceOrders::new(false);
            add_unrestricted_pair(&mut orders,&mut solver,0,2);
            add_unrestricted_pair(&mut orders,&mut solver,1,2);
            let x=orders.bits[&(0,2)];let y=orders.bits[&(1,2)];
            let assumptions=[if a {x}else{!x},if b{y}else{!y}];
            let topology=Topology{next:vec![Some(1),None,None],positive:vec![true,true,!zero]};
            let cut=match solver.solve_with_assumptions(assumptions) {
                SatResultWithCore::Sat(model)=>orders.separate_cycle(&topology,|l|model.value(&l)).unwrap(),
                _=>panic!("free orders must be SAT"),
            };
            let forbidden=a!=b && !(zero && a && !b);
            assert_eq!(cut.is_some(),forbidden);
            if let Some(clause)=cut {
                SatInstance::add_clause(&mut solver,clause);
                assert!(matches!(solver.solve_with_assumptions(assumptions),SatResultWithCore::Unsat(_)));
            }
          }}
        }
    }

    #[test]
    fn triangle_truth_table_removes_exactly_the_two_cyclic_orientations() {
        for transitivity in [false, true] {
            for mask in 0..8 {
                let mut solver = satcoder::solvers::minisat::Solver::new();
                let mut orders = ResourceOrders::new(transitivity);
                assert_eq!(add_unrestricted_pair(&mut orders, &mut solver, 2, 0), 0);
                assert_eq!(add_unrestricted_pair(&mut orders, &mut solver, 1, 2), 0);
                assert_eq!(
                    add_unrestricted_pair(&mut orders, &mut solver, 1, 0),
                    usize::from(transitivity)
                );
                assert_eq!(add_unrestricted_pair(&mut orders, &mut solver, 0, 1), 0);
                let [ab, bc, ac] = [mask & 1 != 0, mask & 2 != 0, mask & 4 != 0];
                let expected = !transitivity || !(ab && bc && !ac || !ab && !bc && ac);
                let result = solver.solve_with_assumptions(
                    [
                        (orders.bits[&(0, 1)], ab),
                        (orders.bits[&(1, 2)], bc),
                        (orders.bits[&(0, 2)], ac),
                    ]
                    .into_iter()
                    .map(|(lit, value)| if value { lit } else { !lit }),
                );
                assert_eq!(matches!(result, SatResultWithCore::Sat(_)), expected);
            }
        }
    }

    #[test]
    fn closing_triangles_creates_no_new_pairs_or_duplicate_clauses() {
        // K4 has four triangles, regardless of the order of inserted edges.
        for edges in [
            vec![(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)],
            vec![(3, 2), (3, 1), (2, 1), (3, 0), (2, 0), (1, 0)],
        ] {
            let mut solver = satcoder::solvers::minisat::Solver::new();
            let mut orders = ResourceOrders::new(true);
            let mut triangles = 0;
            for &(a, b) in &edges {
                triangles += add_unrestricted_pair(&mut orders, &mut solver, a, b);
            }
            assert_eq!(triangles, 4);
            assert_eq!(orders.bits.len(), 6);
            for &(a, b) in &edges {
                assert_eq!(add_unrestricted_pair(&mut orders, &mut solver, b, a), 0);
            }
        }
    }

    #[test]
    fn triangles_preserve_every_feasible_three_occupation_schedule() {
        for a in 0..=6 {
            for b in 0..=6 {
                for c in 0..=6 {
                    let starts = [a, b, c];
                    let pairs = [(0, 1), (1, 2), (0, 2)];
                    if pairs
                        .iter()
                        .any(|&(i, j)| !(starts[i] + 2 <= starts[j] || starts[j] + 2 <= starts[i]))
                    {
                        continue;
                    }
                    let mut solver = satcoder::solvers::minisat::Solver::new();
                    let mut orders = ResourceOrders::new(true);
                    for threshold in [2, 4, 6, 8] {
                        for (i, j) in pairs {
                            orders.add(
                                &mut solver,
                                i as u32,
                                j as u32,
                                threshold,
                                threshold,
                                Bool::Const(starts[i] + 2 >= threshold),
                                Bool::Const(starts[j] + 2 >= threshold),
                                Bool::Const(starts[i] >= threshold),
                                Bool::Const(starts[j] >= threshold),
                            );
                        }
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

    #[test]
    fn a_single_refinement_projects_to_the_original_overlap_clause() {
        for mask in 0..16 {
            let mut solver = satcoder::solvers::minisat::Solver::new();
            let variables = (0..4).map(|_| solver.new_var()).collect::<Vec<_>>();
            let mut orders = ResourceOrders::new(false);
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
        let mut orders = ResourceOrders::new(false);
        assert_eq!(
            orders.add(&mut solver, 0, 1, 10, 20, v[0], v[1], v[2], v[3]),
            (true, 2, 0)
        );
        assert_eq!(
            orders.add(&mut solver, 0, 1, 10, 20, v[0], v[1], v[2], v[3]),
            (false, 0, 0)
        );
        assert_eq!(
            orders.add(&mut solver, 1, 0, 20, 10, v[1], v[0], v[3], v[2]),
            (false, 0, 0)
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
                let mut orders = ResourceOrders::new(false);
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
