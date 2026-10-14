//! Selective refinement for the DDD MaxSAT solver.
//!
//! Each detected violation becomes a package. A package contains the hard
//! clause that removes the violation and the time points needed by that
//! clause. The selector can add every package or limit the number of new time
//! points added in one iteration.

use std::collections::{HashMap, HashSet};

use satcoder::{Bool, SatInstance};
use typed_index_collections::TiVec;

use super::common::{Occ, VisitId};

/// Stable identity of one concrete violation.
///
/// The incumbent times are part of the identity. If the same visits conflict
/// again at different times, that is a new violation and receives a new age.
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub enum ViolationId {
    TravelTime {
        visit: VisitId,
        current_time: i32,
        required_time: i32,
    },
    Resource {
        first: VisitId,
        second: VisitId,
        first_in: i32,
        first_out: i32,
        second_in: i32,
        second_out: i32,
    },
    ForcedOrder {
        first: VisitId,
        second: VisitId,
        source_time: i32,
        required_time: i32,
    },
}

impl ViolationId {
    pub fn resource(a: VisitId, a_in: i32, a_out: i32, b: VisitId, b_in: i32, b_out: i32) -> Self {
        if usize::from(a) <= usize::from(b) {
            Self::Resource {
                first: a,
                second: b,
                first_in: a_in,
                first_out: a_out,
                second_in: b_in,
                second_out: b_out,
            }
        } else {
            Self::Resource {
                first: b,
                second: a,
                first_in: b_in,
                first_out: b_out,
                second_in: a_in,
                second_out: a_out,
            }
        }
    }
}

/// What must be added to the SAT model when a package is selected.
pub enum PackageAction<L: satcoder::Lit> {
    /// If the current visit starts at this incumbent value, the next visit
    /// must start at or after `new_t`.
    TravelTime {
        t1_in_var: Bool<L>,
        next_visit: VisitId,
        new_t: i32,
    },
    /// Generic precedence implication used for a forced resource order.
    Precedence {
        source_lit: Bool<L>,
        target_visit: VisitId,
        new_t: i32,
    },
    /// Two trains overlap on a conflicting resource.
    Resource {
        visit1: VisitId,
        visit2: VisitId,
        tp_for_v2: i32,
        tp_for_v1: i32,
        t1_out_lit: Bool<L>,
        t2_out_lit: Bool<L>,
    },
}

/// Metadata used by the package selector. Keeping it independent from SAT
/// literals makes the fairness policy easy to test.
#[derive(Clone, Debug)]
pub struct RefinementPlan {
    pub violation: ViolationId,
    /// Only points that are absent from the current DDD model belong here.
    pub planned_points: Vec<(VisitId, i32)>,
    pub first_seen: usize,
}

pub struct RefinementPackage<L: satcoder::Lit> {
    pub plan: RefinementPlan,
    pub action: PackageAction<L>,
}

/// Select package indices with a budget on distinct new time points.
///
/// Packages waiting at least `max_wait_iterations` are selected first. They
/// may exceed the budget; this is deliberate and prevents starvation. The
/// remaining space is filled greedily. If nothing fits, the oldest package is
/// selected so every iteration makes progress.
pub fn select_plans(
    plans: &[RefinementPlan],
    budget: Option<usize>,
    current_iteration: usize,
    max_wait_iterations: usize,
) -> Vec<usize> {
    if plans.is_empty() {
        return Vec::new();
    }
    let budget = match budget {
        None => return (0..plans.len()).collect(),
        Some(value) => value,
    };

    let mut selected = Vec::new();
    let mut selected_violations = HashSet::new();
    let mut selected_points = HashSet::new();

    // Oldest packages come first. The index is a deterministic tie breaker.
    let mut mandatory: Vec<usize> = plans
        .iter()
        .enumerate()
        .filter(|(_, plan)| {
            current_iteration.saturating_sub(plan.first_seen) >= max_wait_iterations
        })
        .map(|(index, _)| index)
        .collect();
    mandatory.sort_by_key(|index| (plans[*index].first_seen, *index));

    for index in mandatory {
        let plan = &plans[index];
        if selected_violations.insert(plan.violation.clone()) {
            selected_points.extend(plan.planned_points.iter().copied());
            selected.push(index);
        }
    }

    loop {
        let mut best: Option<(usize, usize)> = None;
        for (index, plan) in plans.iter().enumerate() {
            if selected.contains(&index) || selected_violations.contains(&plan.violation) {
                continue;
            }
            let new_points = plan
                .planned_points
                .iter()
                .filter(|point| !selected_points.contains(point))
                .count();
            if selected_points.len().saturating_add(new_points) > budget {
                continue;
            }

            // One package resolves one concrete violation, so fewer required
            // points means a larger marginal-gain score.
            if best.map_or(true, |(best_points, best_index)| {
                (new_points, index) < (best_points, best_index)
            }) {
                best = Some((new_points, index));
            }
        }

        let Some((_, index)) = best else { break };
        let plan = &plans[index];
        selected_violations.insert(plan.violation.clone());
        selected_points.extend(plan.planned_points.iter().copied());
        selected.push(index);
    }

    if selected.is_empty() {
        let oldest = plans
            .iter()
            .enumerate()
            .min_by_key(|(index, plan)| (plan.first_seen, *index))
            .map(|(index, _)| index)
            .expect("plans is non-empty");
        selected.push(oldest);
    }

    selected
}

pub fn select_packages<L: satcoder::Lit>(
    packages: &[RefinementPackage<L>],
    budget: Option<usize>,
    current_iteration: usize,
    max_wait_iterations: usize,
) -> Vec<usize> {
    let plans: Vec<_> = packages
        .iter()
        .map(|package| package.plan.clone())
        .collect();
    select_plans(&plans, budget, current_iteration, max_wait_iterations)
}

/// Apply one package and return the time points that were actually created.
pub fn apply_package<L: satcoder::Lit + Copy>(
    package: RefinementPackage<L>,
    solver: &mut impl SatInstance<L>,
    occupations: &mut TiVec<VisitId, Occ<L>>,
    n_conflict_constraints: &mut usize,
    n_conflicts: &mut usize,
    n_travel: &mut usize,
) -> Vec<(VisitId, Bool<L>, i32)> {
    let mut added = Vec::new();
    match package.action {
        PackageAction::TravelTime {
            t1_in_var,
            next_visit,
            new_t,
        } => {
            let (target_lit, is_new) = occupations[next_visit].time_point(solver, new_t);
            solver.add_clause(vec![!t1_in_var, target_lit]);
            *n_travel += 1;
            if is_new {
                added.push((next_visit, target_lit, new_t));
            }
        }
        PackageAction::Precedence {
            source_lit,
            target_visit,
            new_t,
        } => {
            let (target_lit, is_new) = occupations[target_visit].time_point(solver, new_t);
            solver.add_clause(vec![!source_lit, target_lit]);
            *n_travel += 1;
            if is_new {
                added.push((target_visit, target_lit, new_t));
            }
        }
        PackageAction::Resource {
            visit1,
            visit2,
            tp_for_v2,
            tp_for_v1,
            t1_out_lit,
            t2_out_lit,
        } => {
            let (delay_v2, v2_new) = occupations[visit2].time_point(solver, tp_for_v2);
            let (delay_v1, v1_new) = occupations[visit1].time_point(solver, tp_for_v1);
            if v1_new {
                added.push((visit1, delay_v1, tp_for_v1));
            }
            if v2_new {
                added.push((visit2, delay_v2, tp_for_v2));
            }
            solver.add_clause(vec![!t1_out_lit, !t2_out_lit, delay_v1, delay_v2]);
            *n_conflict_constraints += 1;
            *n_conflicts += 1;
        }
    }
    added
}

#[derive(Default)]
pub struct ViolationAgeTracker {
    map: HashMap<ViolationId, usize>,
}

impl ViolationAgeTracker {
    pub fn record(&mut self, id: ViolationId, iteration: usize) -> usize {
        *self.map.entry(id).or_insert(iteration)
    }

    /// Forget violations absent from the current full scan. If they reappear
    /// later at another incumbent, they start with a fresh waiting age.
    pub fn retain_active(&mut self, active: &HashSet<ViolationId>) {
        self.map.retain(|id, _| active.contains(id));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn travel_plan(id: usize, first_seen: usize, points: &[(usize, i32)]) -> RefinementPlan {
        RefinementPlan {
            violation: ViolationId::TravelTime {
                visit: VisitId::from(id),
                current_time: 0,
                required_time: 1,
            },
            planned_points: points
                .iter()
                .map(|(visit, time)| (VisitId::from(*visit), *time))
                .collect(),
            first_seen,
        }
    }

    #[test]
    fn budget_counts_distinct_new_points() {
        let plans = vec![
            travel_plan(0, 1, &[(0, 10), (1, 20)]),
            travel_plan(1, 1, &[(1, 20), (2, 30)]),
        ];
        assert_eq!(select_plans(&plans, Some(3), 1, 5), vec![0, 1]);
    }

    #[test]
    fn old_package_is_not_starved_by_budget() {
        let plans = vec![
            travel_plan(0, 1, &[(0, 10), (1, 20)]),
            travel_plan(1, 9, &[(2, 30)]),
        ];
        let selected = select_plans(&plans, Some(1), 10, 5);
        assert!(selected.contains(&0));
    }

    #[test]
    fn fallback_selects_oldest_when_budget_is_zero() {
        let plans = vec![travel_plan(0, 3, &[(0, 10)]), travel_plan(1, 2, &[(1, 10)])];
        assert_eq!(select_plans(&plans, Some(0), 3, 5), vec![1]);
    }
}
