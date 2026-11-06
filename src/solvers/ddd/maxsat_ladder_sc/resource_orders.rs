//! Reuse one optional order literal for each *detected* pair of occupations.
//! Every feasible schedule admits an orientation for that pair. Keeping the
//! same orientation across time thresholds strengthens the SAT relaxation.
use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};

use satcoder::{Bool, Lit, SatInstance};

#[derive(Clone, Copy, Debug)]
pub(super) struct TemporalVisit {
    pub next: Option<u32>,
    pub travel_time: i32,
}

#[derive(Clone, Copy)]
struct TemporalEdge<L: Lit> {
    from: u32,
    to: u32,
    weight: i32,
    selected: Option<Bool<L>>,
}

fn dfs_temporal_cycle<L: Lit>(
    node: usize,
    outgoing: &[Vec<usize>],
    edges: &[TemporalEdge<L>],
    colors: &mut [u8],
    nodes: &mut Vec<usize>,
    edge_stack: &mut Vec<usize>,
) -> Option<Vec<usize>> {
    colors[node] = 1;
    nodes.push(node);
    for &edge_index in &outgoing[node] {
        let edge = edges[edge_index];
        let target = edge.to as usize;
        if colors[target] == 0 {
            edge_stack.push(edge_index);
            if let Some(cycle) = dfs_temporal_cycle(target, outgoing, edges, colors, nodes, edge_stack) {
                return Some(cycle);
            }
            edge_stack.pop();
        } else if colors[target] == 1 {
            let start = nodes.iter().position(|&entry| entry == target)?;
            let mut cycle = edge_stack[start..].to_vec();
            cycle.push(edge_index);
            if cycle.iter().map(|&index| edges[index].weight).sum::<i32>() > 0 {
                return Some(cycle);
            }
        }
    }
    nodes.pop();
    colors[node] = 2;
    None
}

pub(super) struct ResourceOrders<L: Lit> {
    bits: HashMap<(u32, u32), Bool<L>>,
    rows: HashSet<(u32, u32, i32)>,
    transitivity: bool,
    neighbors: BTreeMap<u32, BTreeSet<u32>>,
}

impl<L: Lit> ResourceOrders<L> {
    pub fn new(transitivity: bool) -> Self {
        Self {
            bits: HashMap::new(),
            rows: HashSet::new(),
            transitivity,
            neighbors: BTreeMap::new(),
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

    pub(super) fn pairs(&self) -> Vec<(u32, u32, Bool<L>)> {
        let mut pairs = self
            .bits
            .iter()
            .map(|(&(first, second), &literal)| (first, second, literal))
            .collect::<Vec<_>>();
        pairs.sort_by_key(|(first, second, _)| (*first, *second));
        pairs
    }

    pub(super) fn positive_cycle_cut<M: satcoder::prelude::SymbolicModel<L> + ?Sized>(
        &self,
        visits: &[TemporalVisit],
        model: &M,
    ) -> Option<Vec<Bool<L>>> {
        let mut edges = Vec::<TemporalEdge<L>>::new();
        for (id, visit) in visits.iter().enumerate() {
            if let Some(next) = visit.next {
                edges.push(TemporalEdge {
                    from: id as u32,
                    to: next,
                    weight: visit.travel_time,
                    selected: None,
                });
            }
        }
        for (first, second, bit) in self.pairs() {
            let first_selected = model.value(&bit);
            let (from, to, selected) = if first_selected {
                (self.exit_node(first, visits), second, bit)
            } else {
                (self.exit_node(second, visits), first, !bit)
            };
            edges.push(TemporalEdge {
                from,
                to,
                weight: if from == first || from == second {
                    visits[from as usize].travel_time
                } else {
                    0
                },
                selected: Some(selected),
            });
        }
        edges.sort_by_key(|edge| (edge.from, edge.to, edge.weight, edge.selected.is_some()));
        let n = visits.len();
        let mut outgoing = vec![Vec::<usize>::new(); n];
        for (index, edge) in edges.iter().enumerate() {
            if (edge.from as usize) < n && (edge.to as usize) < n {
                outgoing[edge.from as usize].push(index);
            }
        }
        let mut colors = vec![0u8; n];
        let mut nodes = Vec::new();
        let mut found = None;
        for node in 0..n {
            if colors[node] == 0 {
                let mut edge_stack = Vec::new();
                found = dfs_temporal_cycle(node, &outgoing, &edges, &mut colors, &mut nodes, &mut edge_stack);
                if found.is_some() {
                    break;
                }
            }
        }
        let cycle = found?;
        let mut clause = cycle
            .iter()
            .filter_map(|&index| edges[index].selected.map(|literal| !literal))
            .collect::<Vec<_>>();
        clause.sort();
        clause.dedup();
        (!clause.is_empty()).then_some(clause)
    }

    fn exit_node(&self, visit: u32, visits: &[TemporalVisit]) -> u32 {
        visits[visit as usize].next.unwrap_or(visit)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
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
    fn positive_temporal_cycle_returns_the_clause_that_breaks_the_cycle() {
        let visits = vec![
            TemporalVisit { next: Some(1), travel_time: 2 },
            TemporalVisit { next: None, travel_time: 2 },
            TemporalVisit { next: Some(3), travel_time: 2 },
            TemporalVisit { next: None, travel_time: 2 },
        ];
        let mut solver = satcoder::solvers::minisat::Solver::new();
        let mut orders = ResourceOrders::new(false);
        orders.add(&mut solver, 0, 3, 1, 1, false.into(), false.into(), true.into(), true.into());
        orders.add(&mut solver, 1, 2, 1, 1, false.into(), false.into(), true.into(), true.into());
        let p03 = orders.bits[&(0, 3)];
        let p12 = orders.bits[&(1, 2)];

        let cut = match solver.solve_with_assumptions([!p03, p12]) {
            SatResultWithCore::Sat(model) => orders.positive_cycle_cut(&visits, model.as_ref()),
            SatResultWithCore::Unsat(_) => panic!("test formula must be SAT"),
        };
        assert_eq!(cut, Some(vec![p03, !p12]));

        let cut = match solver.solve_with_assumptions([p03, !p12]) {
            SatResultWithCore::Sat(model) => orders.positive_cycle_cut(&visits, model.as_ref()),
            SatResultWithCore::Unsat(_) => panic!("test formula must be SAT"),
        };
        assert_eq!(cut, None);
    }

    #[test]
    fn zero_duration_routes_do_not_create_temporal_cuts() {
        let visits = vec![
            TemporalVisit { next: Some(1), travel_time: 0 },
            TemporalVisit { next: None, travel_time: 0 },
            TemporalVisit { next: Some(3), travel_time: 0 },
            TemporalVisit { next: None, travel_time: 0 },
        ];
        let mut solver = satcoder::solvers::minisat::Solver::new();
        let mut orders = ResourceOrders::new(false);
        orders.add(&mut solver, 0, 3, 1, 1, false.into(), false.into(), true.into(), true.into());
        orders.add(&mut solver, 1, 2, 1, 1, false.into(), false.into(), true.into(), true.into());
        let p03 = orders.bits[&(0, 3)];
        let p12 = orders.bits[&(1, 2)];
        let cut = match solver.solve_with_assumptions([!p03, p12]) {
            SatResultWithCore::Sat(model) => orders.positive_cycle_cut(&visits, model.as_ref()),
            SatResultWithCore::Unsat(_) => panic!("test formula must be SAT"),
        };
        assert_eq!(cut, None);
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
