//! Precedence preprocessing for TRP — Contribution 2 of the thesis.
//!
//! [`chain_earliest`] — within-train chain propagation
//! `est[v+1] = max(visit.earliest, est[v] + travel[v])`. Sound for all
//! objectives; used by `incremental_sat`, `puresat`, and
//! `maxsat_ladder_sc`.
//!
//! **New (journal extension):**
//! - [`propagate_bounds`]      — propagate L/U along each train's chain (§4.4)
//! - [`find_forced_orders`]    — detect cross-train mandatory orderings (§4.5)
//! - [`tighten_ub_from_cost`]  — cost-budget upper bound tightening (§4.6)

use crate::problem::{DelayCostType, Problem};

// ─────────────────────────────────────────────────────────────────────────────
// §0  Existing: within-train earliest-start propagation
// ─────────────────────────────────────────────────────────────────────────────

/// Simple within-train chain propagation of earliest start times.
///
/// For each train, iterate visits in order and set
/// `earliest[v] = max(visit.earliest, earliest[v-1] + travel[v-1])`.
///
/// Returns `effective_lb[train][visit]`.
pub fn chain_earliest(problem: &Problem) -> Vec<Vec<i32>> {
    let mut effective = Vec::with_capacity(problem.trains.len());
    for train in &problem.trains {
        let mut train_bounds = Vec::with_capacity(train.visits.len());
        let mut propagated_lb: Option<i32> = None;
        for visit in &train.visits {
            let lb =
                propagated_lb.map_or(visit.earliest, |prev_lb: i32| prev_lb.max(visit.earliest));
            train_bounds.push(lb);
            propagated_lb = Some(lb.saturating_add(visit.travel_time));
        }
        effective.push(train_bounds);
    }
    effective
}

// ─────────────────────────────────────────────────────────────────────────────
// §4.4  Propagate L and U along each train's chain
// ─────────────────────────────────────────────────────────────────────────────

/// Propagate lower bounds (forward) and upper bounds (backward) along every
/// train's chain of visits.
///
/// # Arguments
/// * `lb[train][visit]` — current earliest start (L_v). Typically the output
///   of [`chain_earliest`] or `visit.earliest`.
/// * `ub[train][visit]` — current latest start (U_v). Pass `i32::MAX` if
///   unconstrained.
///
/// # Returns
/// Updated `(lb, ub)` tables.  The function iterates until no value changes
/// (fixed point), so it is safe to call once after any external update.
///
/// # Soundness
/// A constraint `t_{s(v)} >= t_v + p_v` (travel time) gives:
///   - Forward:  `L_{s(v)} <- max(L_{s(v)}, L_v + p_v)`
///   - Backward: `U_v      <- min(U_v,      U_{s(v)} - p_v)`
pub fn propagate_bounds(
    problem: &Problem,
    mut lb: Vec<Vec<i32>>,
    mut ub: Vec<Vec<i32>>,
) -> (Vec<Vec<i32>>, Vec<Vec<i32>>) {
    let mut changed = true;
    while changed {
        changed = false;

        for (ti, train) in problem.trains.iter().enumerate() {
            // Forward pass: propagate lower bounds along hành trình
            // L_{v+1} <- max(L_{v+1}, L_v + travel_v)
            for vi in 0..train.visits.len().saturating_sub(1) {
                let p = train.visits[vi].travel_time;
                let new_lb = lb[ti][vi].saturating_add(p);
                if new_lb > lb[ti][vi + 1] {
                    lb[ti][vi + 1] = new_lb;
                    changed = true;
                }
            }

            // Backward pass: propagate upper bounds ngược hành trình
            // U_v <- min(U_v, U_{v+1} - travel_v)
            for vi in (0..train.visits.len().saturating_sub(1)).rev() {
                let p = train.visits[vi].travel_time;
                let new_ub = ub[ti][vi + 1].saturating_sub(p);
                if new_ub < ub[ti][vi] {
                    ub[ti][vi] = new_ub;
                    changed = true;
                }
            }
        }
    }
    (lb, ub)
}

// ─────────────────────────────────────────────────────────────────────────────
// §4.5  Detect cross-train mandatory orderings
// ─────────────────────────────────────────────────────────────────────────────

/// A forced ordering: visit `a` must finish before visit `b` starts,
/// with a safety gap `gap` (usually 0).
///
/// In the DDD solver this translates to a hard clause:
///   `t_b >= e_a + gap`
/// where `e_a = t_{s(a)}` (the start time of `a`'s successor).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct ForcedOrder {
    /// (train_idx, visit_idx) of the visit that goes FIRST
    pub first: (usize, usize),
    /// (train_idx, visit_idx) of the visit that goes SECOND
    pub second: (usize, usize),
    /// Minimum separation: t_second >= e_first + gap
    pub gap: i32,
}

/// For every pair of conflicting visits, check whether one ordering is
/// **already impossible** given the current `lb` / `ub` bounds.
///
/// # Condition (from §4.5, Eq. reject-vw / reject-wv)
/// Ordering *v before w* is impossible when:
///   `L_{s(v)} + gap_vw  >  U_w`
/// i.e. even if v leaves at its earliest possible exit, w would have to
/// start later than its latest permitted start.
///
/// If only one direction is rejected we record the surviving direction as a
/// `ForcedOrder`.  If both are rejected the problem is infeasible in the
/// current bounds (the caller should handle this case).
///
/// # Returns
/// `(forced_orders, infeasible)`
/// * `forced_orders` — list of orderings that are now mandatory.
/// * `infeasible`    — true if any conflict pair has **no** valid ordering.
pub fn find_forced_orders(
    problem: &Problem,
    lb: &[Vec<i32>],
    ub: &[Vec<i32>],
) -> (Vec<ForcedOrder>, bool) {
    let mut forced = Vec::new();
    let mut infeasible = false;

    let visits: Vec<_> = problem
        .trains
        .iter()
        .enumerate()
        .flat_map(|(train_index, train)| {
            train
                .visits
                .iter()
                .enumerate()
                .map(move |(visit_index, visit)| (train_index, visit_index, visit))
        })
        .collect();

    for left in 0..visits.len() {
        let (ti1, vi1, v1) = visits[left];
        for &(ti2, vi2, v2) in &visits[left + 1..] {
            if ti1 == ti2 {
                continue;
            }
            let resources_conflict = problem.conflicts.iter().any(|&(r1, r2)| {
                (r1 == v1.resource_id && r2 == v2.resource_id)
                    || (r1 == v2.resource_id && r2 == v1.resource_id)
            });
            if !resources_conflict {
                continue;
            }

            let train1 = &problem.trains[ti1];
            let train2 = &problem.trains[ti2];
            let exit_lb_v1 = if vi1 + 1 < train1.visits.len() {
                lb[ti1][vi1 + 1]
            } else {
                lb[ti1][vi1].saturating_add(v1.travel_time)
            };
            let exit_lb_v2 = if vi2 + 1 < train2.visits.len() {
                lb[ti2][vi2 + 1]
            } else {
                lb[ti2][vi2].saturating_add(v2.travel_time)
            };

            let v1_before_v2_impossible = exit_lb_v1 > ub[ti2][vi2];
            let v2_before_v1_impossible = exit_lb_v2 > ub[ti1][vi1];
            match (v1_before_v2_impossible, v2_before_v1_impossible) {
                (true, true) => infeasible = true,
                (true, false) => forced.push(ForcedOrder {
                    first: (ti2, vi2),
                    second: (ti1, vi1),
                    gap: 0,
                }),
                (false, true) => forced.push(ForcedOrder {
                    first: (ti1, vi1),
                    second: (ti2, vi2),
                    gap: 0,
                }),
                (false, false) => {}
            }
        }
    }

    (forced, infeasible)
}

/// Propagate train-chain constraints and already known forced orders to a
/// fixed point. A forced order `a -> b` means that `b` starts no earlier than
/// the exit of `a` plus the safety gap.
pub fn propagate_bounds_with_orders(
    problem: &Problem,
    mut lb: Vec<Vec<i32>>,
    mut ub: Vec<Vec<i32>>,
    forced_orders: &[ForcedOrder],
) -> (Vec<Vec<i32>>, Vec<Vec<i32>>) {
    loop {
        let (chain_lb, chain_ub) = propagate_bounds(problem, lb, ub);
        lb = chain_lb;
        ub = chain_ub;
        let mut changed = false;

        for order in forced_orders {
            let (first_train, first_visit) = order.first;
            let (second_train, second_visit) = order.second;
            let first_route = &problem.trains[first_train];

            if first_visit + 1 < first_route.visits.len() {
                let exit_visit = first_visit + 1;
                let new_second_lb = lb[first_train][exit_visit].saturating_add(order.gap);
                if new_second_lb > lb[second_train][second_visit] {
                    lb[second_train][second_visit] = new_second_lb;
                    changed = true;
                }
                let new_exit_ub = ub[second_train][second_visit].saturating_sub(order.gap);
                if new_exit_ub < ub[first_train][exit_visit] {
                    ub[first_train][exit_visit] = new_exit_ub;
                    changed = true;
                }
            } else {
                let duration = first_route.visits[first_visit]
                    .travel_time
                    .saturating_add(order.gap);
                let new_second_lb = lb[first_train][first_visit].saturating_add(duration);
                if new_second_lb > lb[second_train][second_visit] {
                    lb[second_train][second_visit] = new_second_lb;
                    changed = true;
                }
                let new_first_ub = ub[second_train][second_visit].saturating_sub(duration);
                if new_first_ub < ub[first_train][first_visit] {
                    ub[first_train][first_visit] = new_first_ub;
                    changed = true;
                }
            }
        }

        if !changed {
            return (lb, ub);
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// §4.6  Cost-budget upper bound tightening (Continuous / InfiniteSteps only)
// ─────────────────────────────────────────────────────────────────────────────

/// Tighten the upper-bound time `U_v` for each visit using the budget
/// remaining after accounting for the minimum cost of every other visit.
///
/// Only meaningful for cost types where per-second delay maps linearly to
/// cost (`Continuous`) or in fixed intervals (`InfiniteSteps*`).
/// For `FiniteSteps*` the max penalty is capped so no finite time bound can
/// be inferred, and the function returns the input `ub` unchanged.
///
/// # Arguments
/// * `ub`        — current upper bounds (modified in place and returned).
/// * `best_cost` — UB on total cost, e.g. `best_heur.cost`.
///
/// # Returns
/// Updated `ub` table.
pub fn tighten_ub_from_cost(
    problem: &Problem,
    delay_cost_type: DelayCostType,
    lb: &[Vec<i32>],
    mut ub: Vec<Vec<i32>>,
    best_cost: i32,
) -> Vec<Vec<i32>> {
    // FiniteSteps: max penalty is bounded regardless of delay → cannot infer
    // a finite time limit from cost budget.
    match delay_cost_type {
        DelayCostType::FiniteSteps1_3Min
        | DelayCostType::FiniteSteps1_5Min
        | DelayCostType::FiniteSteps123
        | DelayCostType::FiniteSteps12345
        | DelayCostType::FiniteSteps139 => return ub,
        _ => {}
    }

    // Step 1: tính phạt tối thiểu của mỗi (train, visit)
    //         = chi phí khi tàu đến đúng thời điểm sớm nhất L_v
    let min_costs: Vec<Vec<i32>> = problem
        .trains
        .iter()
        .enumerate()
        .map(|(ti, train)| {
            train
                .visits
                .iter()
                .enumerate()
                .map(|(vi, _)| train.visit_delay_cost(delay_cost_type, vi, lb[ti][vi]) as i32)
                .collect()
        })
        .collect();

    let total_min_cost: i32 = min_costs.iter().flat_map(|t| t.iter()).sum();

    // Step 2: với mỗi (train, visit), tính ngân sách còn lại R_v
    //         và suy ra thời gian muộn nhất mới U_v
    for (ti, train) in problem.trains.iter().enumerate() {
        for vi in 0..train.visits.len() {
            let aimed = match train.visits[vi].aimed {
                Some(a) => a,
                None => continue, // visit không có aimed → không tính chi phí
            };

            let own_min = min_costs[ti][vi];
            // Ngân sách còn lại sau khi trừ chi phí tối thiểu của tất cả visit khác
            let remaining = best_cost - (total_min_cost - own_min);

            if remaining < 0 {
                // Budget đã âm — bài toán infeasible với cost ≤ best_cost
                // (caller xử lý; ta không thay đổi gì để tránh crash)
                continue;
            }

            // Tính delay tối đa được phép từ ngân sách còn lại
            let max_delay: i32 = match delay_cost_type {
                DelayCostType::Continuous => remaining, // 1 giây = 1 điểm
                DelayCostType::InfiniteSteps60 => {
                    // mỗi bậc 60s = 1 điểm → trễ tối đa = remaining * 60
                    remaining.saturating_mul(60)
                }
                DelayCostType::InfiniteSteps180 => remaining.saturating_mul(180),
                DelayCostType::InfiniteSteps360 => remaining.saturating_mul(360),
                _ => continue, // FiniteSteps đã lọc ở trên
            };

            let new_ub = aimed.saturating_add(max_delay);
            if new_ub < ub[ti][vi] {
                ub[ti][vi] = new_ub;
            }
        }
    }

    ub
}

// ─────────────────────────────────────────────────────────────────────────────
// Unit tests — chạy bằng `cargo test`
// ─────────────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use crate::problem::{DelayCostType, Problem, Train, Visit};

    fn make_visit(resource_id: usize, earliest: i32, aimed: i32, travel_time: i32) -> Visit {
        Visit {
            resource_id,
            earliest,
            aimed: Some(aimed),
            travel_time,
        }
    }

    /// Bài toán nhỏ T01: 1 tàu, 3 visit
    /// Kiểm tra: L_v được truyền đúng theo hành trình
    #[test]
    fn test_chain_earliest_propagates() {
        let problem = Problem {
            name: "T01".into(),
            trains: vec![Train {
                visits: vec![
                    make_visit(0, 10, 10, 5), // v0: sớm nhất=10, chạy 5s
                    make_visit(1, 8, 8, 3),   // v1: earliest=8 nhưng phải đợi v0
                    make_visit(2, 20, 20, 0), // v2: earliest=20
                ],
            }],
            conflicts: vec![],
        };

        let lb = chain_earliest(&problem);
        // v0: 10, v1: max(8, 10+5)=15, v2: max(20, 15+3)=20
        assert_eq!(lb[0], vec![10, 15, 20]);
    }

    /// T03: Chỉ một thứ tự khả thi — find_forced_orders phải phát hiện
    #[test]
    fn test_forced_order_detected() {
        // Tàu A: vào resource 0 lúc 10, thoát sớm nhất lúc 15 (travel=5)
        // Tàu B: vào resource 0 muộn nhất lúc 13 → A đi trước B impossible
        //         vì exit_lb_A = 15 > ub_B = 13
        let problem = Problem {
            name: "T03".into(),
            trains: vec![
                Train {
                    visits: vec![make_visit(0, 10, 10, 5)],
                },
                Train {
                    visits: vec![make_visit(0, 5, 5, 3)],
                },
            ],
            conflicts: vec![(0, 0)],
        };

        let lb = vec![vec![10], vec![5]];
        let ub = vec![vec![20], vec![13]]; // B muộn nhất 13

        let (forced, infeasible) = find_forced_orders(&problem, &lb, &ub);
        assert!(!infeasible, "bài toán vẫn khả thi");
        assert_eq!(forced.len(), 1, "phải có đúng 1 thứ tự bắt buộc");
        // B (train 1) phải đi trước A (train 0)
        assert_eq!(forced[0].first, (1, 0));
        assert_eq!(forced[0].second, (0, 0));
    }

    #[test]
    fn test_forced_order_detected_when_resource_pair_is_reversed() {
        let problem = Problem {
            name: "T04".into(),
            trains: vec![
                Train {
                    visits: vec![make_visit(1, 10, 10, 5)],
                },
                Train {
                    visits: vec![make_visit(0, 5, 5, 3)],
                },
            ],
            conflicts: vec![(0, 1)],
        };
        let (forced, infeasible) =
            find_forced_orders(&problem, &[vec![10], vec![5]], &[vec![20], vec![13]]);
        assert!(!infeasible);
        assert_eq!(forced.len(), 1);
        assert_eq!(forced[0].first, (1, 0));
        assert_eq!(forced[0].second, (0, 0));
    }

    #[test]
    fn test_forced_order_propagates_both_bounds() {
        let problem = Problem {
            name: "T05".into(),
            trains: vec![
                Train {
                    visits: vec![make_visit(0, 10, 10, 5)],
                },
                Train {
                    visits: vec![make_visit(0, 0, 0, 3)],
                },
            ],
            conflicts: vec![(0, 0)],
        };
        let order = ForcedOrder {
            first: (0, 0),
            second: (1, 0),
            gap: 0,
        };
        let (lb, ub) = propagate_bounds_with_orders(
            &problem,
            vec![vec![10], vec![0]],
            vec![vec![i32::MAX], vec![20]],
            &[order],
        );
        assert_eq!(lb[1][0], 15);
        assert_eq!(ub[0][0], 15);
    }

    /// T06: tighten_ub_from_cost với Continuous
    #[test]
    fn test_tighten_ub_continuous() {
        let problem = Problem {
            name: "T06".into(),
            trains: vec![
                Train {
                    visits: vec![make_visit(0, 100, 100, 0)],
                }, // tàu 0
                Train {
                    visits: vec![make_visit(1, 200, 200, 0)],
                }, // tàu 1
            ],
            conflicts: vec![],
        };

        // Tàu 0: aimed=100, lb=100 → min_cost = 0 (đến đúng giờ)
        // Tàu 1: aimed=200, lb=210 → min_cost = 10 (trễ 10s)
        // best_cost = 50
        // R_tàu0 = 50 - 10 = 40 → U_tàu0 = 100 + 40 = 140
        // R_tàu1 = 50 - 0  = 50 → U_tàu1 = 200 + 50 = 250

        let lb = vec![vec![100], vec![210]];
        let ub = vec![vec![i32::MAX], vec![i32::MAX]];

        let ub2 = tighten_ub_from_cost(&problem, DelayCostType::Continuous, &lb, ub, 50);

        assert_eq!(ub2[0][0], 140);
        assert_eq!(ub2[1][0], 250);
    }
}
