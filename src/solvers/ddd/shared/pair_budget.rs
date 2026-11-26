//! Additive lower bounds from disjoint pairs of trains on conflicting resources.

use super::precedence::chain_earliest;
use crate::problem::{DelayCostType, Problem};
use std::collections::{BTreeMap, BTreeSet};

pub(crate) struct PairBudget {
    earliest: Vec<Vec<i32>>,
    matched_extra: Vec<u64>,
    lower: u64,
}

impl PairBudget {
    pub(crate) fn new(problem: &Problem, objective: DelayCostType, chain_cost: i32) -> Self {
        let earliest = chain_earliest(problem);
        let mut uses = BTreeMap::<_, Vec<_>>::new();
        for (ti, train) in problem.trains.iter().enumerate() {
            for (vi, visit) in train.visits.iter().enumerate() {
                uses.entry(visit.resource_id).or_default().push((ti, vi));
            }
        }
        let conflicts: BTreeSet<_> = problem.conflicts.iter().map(|&(a, b)| (a.min(b), a.max(b))).collect();
        let mut bound = Self {
            earliest,
            matched_extra: vec![0; problem.trains.len()],
            lower: chain_cost as u64,
        };
        let mut weights = BTreeMap::<_, u64>::new();
        for (a, b) in conflicts {
            let (Some(left), Some(right)) = (uses.get(&a), uses.get(&b)) else { continue; };
            for &(i, v) in left {
                for &(j, w) in right {
                    if i == j || (a == b && i > j) {
                        continue;
                    }
                    let release = |train: usize, visit: usize| {
                        bound.earliest[train].get(visit + 1).copied().unwrap_or_else(|| {
                            bound.earliest[train][visit].saturating_add(problem.trains[train].visits[visit].travel_time)
                        })
                    };
                    let extra = bound.extra(problem, objective, j, w, release(i, v))
                        .min(bound.extra(problem, objective, i, v, release(j, w)));
                    if extra != 0 {
                        let old = weights.entry((i.min(j), i.max(j))).or_default();
                        *old = (*old).max(extra);
                    }
                }
            }
        }
        let mut edges: Vec<_> = weights.into_iter().collect();
        edges.sort_by_key(|&(pair, extra)| (std::cmp::Reverse(extra), pair));
        for ((i, j), extra) in edges {
            if bound.matched_extra[i] == 0 && bound.matched_extra[j] == 0 {
                bound.matched_extra[i] = extra;
                bound.matched_extra[j] = extra;
                bound.lower = bound.lower.saturating_add(extra);
            }
        }
        bound
    }

    fn extra(&self, problem: &Problem, objective: DelayCostType, train: usize, from: usize, mut time: i32) -> u64 {
        let route = &problem.trains[train];
        let mut extra = 0u64;
        for (visit, &earliest) in self.earliest[train].iter().enumerate().skip(from) {
            time = time.max(earliest);
            if route.visits[visit].aimed.is_some() {
                let cost = route.visit_delay_cost(objective, visit, time);
                let minimum = route.visit_delay_cost(objective, visit, earliest);
                extra = extra.saturating_add(cost.saturating_sub(minimum) as u64);
            }
            time = time.saturating_add(route.visits[visit].travel_time);
        }
        extra
    }

    pub(crate) fn lower(&self) -> u64 {
        self.lower
    }

    pub(crate) fn point_lower(
        &self, problem: &Problem, objective: DelayCostType, train: usize, visit: usize, time: i32,
    ) -> u64 {
        // The chosen pair involving this train might pay for the same delay.
        // Charge only the disjoint pairs that do not involve it.
        (self.lower - self.matched_extra[train])
            .saturating_add(self.extra(problem, objective, train, visit, time))
    }
}
