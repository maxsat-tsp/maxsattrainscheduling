use std::{
    cell::RefCell,
    collections::{BTreeMap, HashMap, HashSet},
    time::{Duration, Instant},
};

#[allow(unused)]
use crate::{
    debug::{ResourceInterval, SolverAction},
    minimize_core,
    problem::Problem,
    trim_core,
};
use satcoder::{
    constraints::{BooleanFormulas, Totalizer},
    prelude::{Binary, SymbolicModel},
    Bool, SatInstance, SatSolverWithCore,
};
use typed_index_collections::TiVec;

// -----------------------------------------------------------------------------
// SC-style encoding for fixed-precedence cliques (rail-path precedence).
//
// In the IAP/DDD formulation, a fixed precedence clique for two consecutive
// visits r \prec q on the SAME train has the staircase form:
//   x_{ir}^p + \sum_{t=1}^{K(p)} x_{iq}^t \le 1.
//
// This solver represents each visit by a monotone ladder of time-point literals
// (Occ::delays): for increasing times t_1 < t_2 < ... we maintain literals
//   d(t)  ==  ("arrival time at least t").
// The ladder clauses ensure d(t_j) => d(t_{j-1}) and d(t_{j+1}) => d(t_j).
//
// Under this representation, the clique above compresses to ONE implication per
// time point (the SC idea):
//   d_r(t) -> d_q(t + travel_r).
// which forbids all too early choices at q without enumerating them.
// -----------------------------------------------------------------------------

#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
pub(super) struct VisitId(pub(super) u32);

impl From<VisitId> for usize {
    fn from(v: VisitId) -> Self {
        v.0 as usize
    }
}

impl From<usize> for VisitId {
    fn from(x: usize) -> Self {
        VisitId(x as u32)
    }
}

#[derive(Clone, Copy, Debug)]
struct ResourceId(u32);

impl From<ResourceId> for usize {
    fn from(v: ResourceId) -> Self {
        v.0 as usize
    }
}

impl From<usize> for ResourceId {
    fn from(x: usize) -> Self {
        ResourceId(x as u32)
    }
}

#[derive(PartialEq, Eq, PartialOrd, Ord, Debug)]
pub enum IterationType {
    Objective,
    TravelTimeConflict,
    ResourceConflict,
    TravelAndResourceConflict,
    Solution,
}

#[derive(Default)]
pub struct SolveStats {
    pub sat_calls: usize,
    pub partial_sat_calls: usize,
    pub cost_terms: usize,
    pub resource_order_pairs: usize,
    pub resource_order_rows: usize,
    pub resource_order_triangles: usize,
    pub core_literals: usize,
    pub max_core_size: usize,
    pub unit_weight_cores: usize,
    pub n_sat: usize,
    pub n_unsat: usize,
    pub n_travel: usize,
    pub n_conflict: usize,
    pub satsolver: String,
}

// Settings + tunable constants moved to `super::settings`.
// SC AMO helpers moved to `super::sc_amo`.
// Precedence helpers moved to `super::precedence`.
use super::aglr::{
    select as select_aglr_candidates, Candidate as AglrCandidate, CandidateHistory, ConflictKey,
    Selection as AglrSelection, VisitTime,
};
use super::precedence::{add_fixed_precedence_row, propagate_precedence};
use super::sc_amo::{add_hybrid_amo, build_active_lit};
use super::settings::{MaxSatDddLadderScSettings, RefinementPolicy};

enum Soft<L: satcoder::Lit> {
    Primary,
    Totalizer(Totalizer<L>, usize),
}

fn bits_needed(max_value: usize) -> usize {
    if max_value == 0 {
        1
    } else {
        (usize::BITS as usize) - (max_value.leading_zeros() as usize)
    }
}

fn build_binary_register<L: satcoder::Lit + Copy + 'static>(reg_bits: &[Bool<L>]) -> Binary<L> {
    Binary::from_list(reg_bits.iter().copied())
}

fn build_weighted_binary_term<L: satcoder::Lit + Copy + 'static>(
    lit: Bool<L>,
    weight: usize,
) -> Binary<L> {
    if weight == 0 || lit == false.into() {
        return Binary::constant(0);
    }

    let mut bits = Vec::new();
    let mut remaining = weight;
    while remaining > 0 {
        bits.push(if (remaining & 1usize) == 1usize {
            lit
        } else {
            false.into()
        });
        remaining >>= 1;
    }

    Binary::from_list(bits)
}

fn subtract_binary<L: satcoder::Lit + Copy + 'static>(
    solver: &mut impl SatInstance<L>,
    a: &Binary<L>,
    b: &Binary<L>,
) -> (Binary<L>, Bool<L>) {
    use std::iter::repeat;

    let len = a.clone().into_list().len().max(b.clone().into_list().len());
    let a_bits = a
        .clone()
        .into_list()
        .into_iter()
        .chain(repeat(false.into()))
        .take(len)
        .collect::<Vec<_>>();
    let b_bits = b
        .clone()
        .into_list()
        .into_iter()
        .chain(repeat(false.into()))
        .take(len)
        .collect::<Vec<_>>();

    let mut diff_bits = Vec::with_capacity(len);
    let mut borrow = false.into();

    for idx in 0..len {
        let ai = a_bits[idx];
        let bi = b_bits[idx];

        let diff = solver.xor_literal([ai, bi, borrow]);
        let bi_or_borrow = solver.or_literal([bi, borrow]);
        let borrow_from_subtrahend = solver.and_literal([!ai, bi_or_borrow]);
        let borrow_from_borrow = solver.and_literal([bi, borrow]);
        let next_borrow = solver.or_literal([borrow_from_subtrahend, borrow_from_borrow]);

        diff_bits.push(diff);
        borrow = next_borrow;
    }

    (Binary::from_list(diff_bits), borrow)
}

fn binary_le_literal_bits<L: satcoder::Lit + Copy>(
    solver: &mut impl SatInstance<L>,
    a: &[Bool<L>], // MSB -> LSB
    b: &[Bool<L>], // MSB -> LSB
) -> Bool<L> {
    assert_eq!(a.len(), b.len());

    if a.is_empty() {
        return true.into();
    }

    if a.len() == 1 {
        let le_lit = solver.new_var();
        solver.add_clause(vec![!le_lit, !a[0], b[0]]);
        return le_lit;
    }

    let rest = binary_le_literal_bits(solver, &a[1..], &b[1..]);
    let le_lit = solver.new_var();

    solver.add_clause(vec![!le_lit, !a[0], b[0]]);
    solver.add_clause(vec![!le_lit, a[0], b[0], rest]);
    solver.add_clause(vec![!le_lit, !a[0], !b[0], rest]);

    le_lit
}

fn assert_binary_le<L: satcoder::Lit + Copy + 'static>(
    solver: &mut impl SatInstance<L>,
    a: &Binary<L>,
    b: &Binary<L>,
) {
    use std::iter::repeat;

    let len = a.clone().into_list().len().max(b.clone().into_list().len());
    if len == 0 {
        return;
    }

    let mut a_bits = a
        .clone()
        .into_list()
        .into_iter()
        .chain(repeat(false.into()))
        .take(len)
        .collect::<Vec<_>>();
    a_bits.reverse();

    let mut b_bits = b
        .clone()
        .into_list()
        .into_iter()
        .chain(repeat(false.into()))
        .take(len)
        .collect::<Vec<_>>();
    b_bits.reverse();

    let le = binary_le_literal_bits(solver, &a_bits, &b_bits);
    solver.add_clause(vec![le]);
}

struct BinaryObjective<L: satcoder::Lit> {
    reg_bits: Vec<Bool<L>>,
    remaining: Binary<L>,
    upper_bound: usize,
}

impl<L: satcoder::Lit + Copy + 'static> BinaryObjective<L> {
    /// Reserve an unsigned budget B <= UB. Every original weighted cost term
    /// is subtracted exactly once, with underflow forbidden. No new soft
    /// objective is introduced: RC2 keeps minimizing the original costs.
    fn new(solver: &mut impl SatInstance<L>, upper_bound: usize) -> Self {
        let reg_bits = (0..bits_needed(upper_bound)).map(|_| solver.new_var()).collect::<Vec<_>>();
        let remaining = build_binary_register(&reg_bits);
        assert_binary_le(solver, &remaining, &Binary::constant(upper_bound));
        Self {
            reg_bits,
            remaining,
            upper_bound,
        }
    }

    fn add_term(&mut self, solver: &mut impl SatInstance<L>, lit: Bool<L>, weight: usize) {
        if weight == 0 || lit == false.into() {
            return;
        }

        let term = build_weighted_binary_term(lit, weight);
        let (next_remaining, underflow) = subtract_binary(solver, &self.remaining, &term);
        solver.add_clause(vec![!underflow]);
        self.remaining = next_remaining;
    }

    fn tighten(&mut self, solver: &mut impl SatInstance<L>, upper_bound: usize) -> bool {
        if upper_bound < self.upper_bound {
            assert_binary_le(solver, &build_binary_register(&self.reg_bits), &Binary::constant(upper_bound));
            self.upper_bound = upper_bound;
            true
        } else {
            false
        }
    }
}

#[derive(Default)]
struct AglrTelemetry {
    detection_time: Duration,
    selection_time: Duration,
    application_time: Duration,
    candidates_detected: usize,
    candidates_selected: usize,
    all_growth: usize,
    selected_growth: usize,
    mandatory_selected: usize,
    rescue_iterations: usize,
    max_age: usize,
    duplicate_clauses_skipped: usize,
    model_progress_iterations: usize,
    heuristic_submissions: usize,
    objective_bound_terms: usize,
    objective_bound_updates: usize,
    objective_bound_time: Duration,
    duplicate_candidates_filtered: usize,
    refinement_clauses_added: usize,
    refinement_points_added: usize,
    rescue_candidates_selected: usize,
    final_validation_time: Duration,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
enum AglrClauseKey {
    Travel {
        from: VisitId,
        from_time: i32,
        to: VisitId,
        required_time: i32,
    },
    Resource {
        first: VisitId,
        first_exit: i32,
        second: VisitId,
        second_exit: i32,
    },
}

enum RefinementAction<L: satcoder::Lit> {
    Travel {
        visit_id: VisitId,
        next_visit: VisitId,
        in_var: Bool<L>,
        in_t: i32,
        required_t: i32,
        interval: ResourceInterval,
    },
    Resource {
        visit_id: VisitId,
        other_visit: VisitId,
        resource_id: usize,
        other_resource_id: usize,
        t1_out: i32,
        t2_out: i32,
        t1_out_lit: Bool<L>,
        t2_out_lit: Bool<L>,
    },
}

struct DetectedRefinement<L: satcoder::Lit> {
    candidate: AglrCandidate,
    action: RefinementAction<L>,
}

impl<L: satcoder::Lit> DetectedRefinement<L> {
    fn clause_key(&self) -> AglrClauseKey {
        match &self.action {
            RefinementAction::Travel { visit_id, next_visit, in_t, required_t, .. } => AglrClauseKey::Travel {
                from: *visit_id, from_time: *in_t, to: *next_visit, required_time: *required_t,
            },
            RefinementAction::Resource { visit_id, other_visit, t1_out, t2_out, .. } => {
                if visit_id.0 <= other_visit.0 {
                    AglrClauseKey::Resource { first: *visit_id, first_exit: *t1_out, second: *other_visit, second_exit: *t2_out }
                } else {
                    AglrClauseKey::Resource { first: *other_visit, first_exit: *t2_out, second: *visit_id, second_exit: *t1_out }
                }
            }
        }
    }
}

#[derive(Default)]
struct RefinementOutcome {
    found_travel: bool,
    found_resource: bool,
    model_progress: bool,
}

#[allow(clippy::too_many_arguments)]
fn detect_and_apply_aglr<L: satcoder::Lit + Copy + 'static>(
    solver: &mut impl SatInstance<L>,
    problem: &Problem,
    visits: &TiVec<VisitId, (usize, usize)>,
    resource_visits: &[Vec<VisitId>],
    conflicts: &HashMap<usize, Vec<usize>>,
    occupations: &mut TiVec<VisitId, Occ<L>>,
    new_time_points: &mut Vec<(VisitId, Bool<L>, i32)>,
    fixed_prec_rows: &mut HashSet<(VisitId, i32)>,
    clique_amo_encoded: &mut HashSet<Vec<VisitId>>,
    encoded_refinement_clauses: &mut HashSet<AglrClauseKey>,
    settings: MaxSatDddLadderScSettings,
    history: &mut CandidateHistory,
    rescue: bool,
    stats: &mut SolveStats,
    debug_actions: &mut Vec<SolverAction>,
    n_conflict_constraints: &mut usize,
    telemetry: &mut AglrTelemetry,
) -> RefinementOutcome {
    let detect_start = Instant::now();
    let mut detected = Vec::<DetectedRefinement<L>>::new();

    for visit_id in visits.keys() {
        let (train_idx, visit_idx) = visits[visit_id];
        if visit_idx + 1 >= problem.trains[train_idx].visits.len() {
            continue;
        }
        let next_visit: VisitId = (usize::from(visit_id) + 1).into();
        let in_t = occupations[visit_id].incumbent_time();
        let out_t = occupations[next_visit].incumbent_time();
        let visit = problem.trains[train_idx].visits[visit_idx];
        if in_t + visit.travel_time <= out_t {
            continue;
        }

        let required_t = in_t + visit.travel_time;
        detected.push(DetectedRefinement {
            candidate: AglrCandidate {
                key: ConflictKey::Travel {
                    from: visit_id.0,
                    to: next_visit.0,
                },
                points: vec![VisitTime {
                    visit: next_visit.0,
                    time: required_t,
                }],
            },
            action: RefinementAction::Travel {
                visit_id,
                next_visit,
                in_var: occupations[visit_id].delays[occupations[visit_id].incumbent_idx].0,
                in_t,
                required_t,
                interval: ResourceInterval {
                    train_idx,
                    visit_idx,
                    resource_idx: visit.resource_id,
                    time_in: in_t,
                    time_out: out_t,
                },
            },
        });
    }

    let mut seen_pairs = HashSet::<(VisitId, VisitId)>::new();
    for visit_id in visits.keys() {
        let (train_idx, visit_idx) = visits[visit_id];
        let visit = problem.trains[train_idx].visits[visit_idx];
        let t1_in = occupations[visit_id].incumbent_time();
        let next_visit = (visit_idx + 1 < problem.trains[train_idx].visits.len())
            .then(|| VisitId(visit_id.0 + 1));
        let t1_out = next_visit
            .map(|next| occupations[next].incumbent_time())
            .unwrap_or(t1_in + visit.travel_time);

        let Some(conflicting_resources) = conflicts.get(&visit.resource_id) else {
            continue;
        };
        for &other_resource in conflicting_resources {
            for &other_visit in &resource_visits[other_resource] {
                if other_visit == visit_id {
                    continue;
                }
                let pair = if visit_id.0 < other_visit.0 {
                    (visit_id, other_visit)
                } else {
                    (other_visit, visit_id)
                };
                if !seen_pairs.insert(pair) {
                    continue;
                }

                let (other_train_idx, other_visit_idx) = visits[other_visit];
                if train_idx == other_train_idx {
                    continue;
                }
                let other = problem.trains[other_train_idx].visits[other_visit_idx];
                let t2_in = occupations[other_visit].incumbent_time();
                let other_next_visit = (other_visit_idx + 1
                    < problem.trains[other_train_idx].visits.len())
                .then(|| VisitId(other_visit.0 + 1));
                let t2_out = other_next_visit
                    .map(|next| occupations[next].incumbent_time())
                    .unwrap_or(t2_in + other.travel_time);
                if t1_out <= t2_in || t2_out <= t1_in {
                    continue;
                }

                let t1_out_lit = next_visit
                    .map(|next| occupations[next].delays[occupations[next].incumbent_idx].0)
                    .unwrap_or_else(|| true.into());
                let t2_out_lit = other_next_visit
                    .map(|next| occupations[next].delays[occupations[next].incumbent_idx].0)
                    .unwrap_or_else(|| true.into());
                detected.push(DetectedRefinement {
                    candidate: AglrCandidate {
                        key: ConflictKey::resource(visit_id.0, other_visit.0),
                        points: vec![
                            VisitTime {
                                visit: visit_id.0,
                                time: t2_out,
                            },
                            VisitTime {
                                visit: other_visit.0,
                                time: t1_out,
                            },
                        ],
                    },
                    action: RefinementAction::Resource {
                        visit_id,
                        other_visit,
                        resource_id: visit.resource_id,
                        other_resource_id: other_resource,
                        t1_out,
                        t2_out,
                        t1_out_lit,
                        t2_out_lit,
                    },
                });
            }
        }
    }
    telemetry.detection_time += detect_start.elapsed();

    let mut outcome = RefinementOutcome {
        found_travel: detected
            .iter()
            .any(|item| matches!(&item.action, RefinementAction::Travel { .. })),
        found_resource: detected
            .iter()
            .any(|item| matches!(&item.action, RefinementAction::Resource { .. })),
        model_progress: false,
    };
    telemetry.candidates_detected += detected.len();
    if settings.aglr.filter_duplicates {
        let keys = detected.iter().map(DetectedRefinement::clause_key).collect::<Vec<_>>();
        let keep = super::aglr::unique_action_indices(&keys, encoded_refinement_clauses).into_iter().collect::<HashSet<_>>();
        let before = detected.len();
        detected = detected.into_iter().enumerate().filter_map(|(index, action)| keep.contains(&index).then_some(action)).collect();
        telemetry.duplicate_candidates_filtered += before - detected.len();
    }

    let existing = occupations
        .iter_enumerated()
        .flat_map(|(visit, occupation)| {
            occupation.delays[..occupation.delays.len() - 1]
                .iter()
                .map(move |(_, time)| VisitTime {
                    visit: visit.0,
                    time: *time,
                })
        })
        .collect::<HashSet<_>>();
    let candidates = detected
        .iter()
        .map(|item| item.candidate.clone())
        .collect::<Vec<_>>();
    let selection_start = Instant::now();
    let selection: AglrSelection = select_aglr_candidates(
        &candidates,
        &existing,
        settings.aglr,
        rescue && settings.aglr.policy == RefinementPolicy::Adaptive,
        history,
    );
    telemetry.selection_time += selection_start.elapsed();
    telemetry.candidates_selected += selection.indices.len();
    telemetry.all_growth += selection.all_growth;
    telemetry.selected_growth += selection.selected_growth;
    telemetry.mandatory_selected += selection.mandatory;
    telemetry.max_age = telemetry.max_age.max(selection.max_age);
    if selection.rescued {
        telemetry.rescue_iterations += 1;
        telemetry.rescue_candidates_selected += selection.indices.len();
    }

    let before_clauses = encoded_refinement_clauses.len();
    let before_sat_clauses = crate::solvers::util::counting_solver::get_counts().1;
    let before_time_points = new_time_points.len();
    let apply_start = Instant::now();
    let mut touched_pair_cliques: HashMap<(usize, i32), HashSet<VisitId>> = HashMap::new();
    let selected_indices = selection.indices.into_iter().collect::<HashSet<_>>();
    for (idx, refinement) in detected.into_iter().enumerate() {
        if !selected_indices.contains(&idx) {
            continue;
        }
        match refinement.action {
            RefinementAction::Travel {
                visit_id,
                next_visit,
                in_var,
                in_t,
                required_t,
                interval,
            } => {
                debug_actions.push(SolverAction::TravelTimeConflict(interval));
                let clause_key = AglrClauseKey::Travel {
                    from: visit_id,
                    from_time: in_t,
                    to: next_visit,
                    required_time: required_t,
                };
                if !encoded_refinement_clauses.insert(clause_key) {
                    telemetry.duplicate_clauses_skipped += 1;
                    continue;
                }
                if settings.use_eager_chain_expansion {
                    let _ = add_fixed_precedence_row(
                        solver,
                        problem,
                        visits,
                        occupations,
                        new_time_points,
                        fixed_prec_rows,
                        visit_id,
                        in_var,
                        in_t,
                        true,
                    );
                } else {
                    let (required_var, is_new) =
                        occupations[next_visit].time_point(solver, required_t);
                    solver.add_clause(vec![!in_var, required_var]);
                    if is_new {
                        new_time_points.push((next_visit, required_var, required_t));
                    }
                }
                stats.n_travel += 1;
            }
            RefinementAction::Resource {
                visit_id,
                other_visit,
                resource_id,
                other_resource_id,
                t1_out,
                t2_out,
                t1_out_lit,
                t2_out_lit,
            } => {
                let clause_key = if visit_id.0 <= other_visit.0 {
                    AglrClauseKey::Resource {
                        first: visit_id,
                        first_exit: t1_out,
                        second: other_visit,
                        second_exit: t2_out,
                    }
                } else {
                    AglrClauseKey::Resource {
                        first: other_visit,
                        first_exit: t2_out,
                        second: visit_id,
                        second_exit: t1_out,
                    }
                };
                if !encoded_refinement_clauses.insert(clause_key) {
                    telemetry.duplicate_clauses_skipped += 1;
                    continue;
                }
                let (delay_t2, t2_is_new) = occupations[other_visit].time_point(solver, t1_out);
                let (delay_t1, t1_is_new) = occupations[visit_id].time_point(solver, t2_out);
                if t1_is_new {
                    new_time_points.push((visit_id, delay_t1, t2_out));
                }
                if t2_is_new {
                    new_time_points.push((other_visit, delay_t2, t1_out));
                }

                if settings.use_eager_chain_expansion {
                    let _ = add_fixed_precedence_row(
                        solver,
                        problem,
                        visits,
                        occupations,
                        new_time_points,
                        fixed_prec_rows,
                        visit_id,
                        delay_t1,
                        t2_out,
                        true,
                    );
                    let _ = add_fixed_precedence_row(
                        solver,
                        problem,
                        visits,
                        occupations,
                        new_time_points,
                        fixed_prec_rows,
                        other_visit,
                        delay_t2,
                        t1_out,
                        true,
                    );
                }

                solver.add_clause(vec![!t1_out_lit, !t2_out_lit, delay_t1, delay_t2]);
                *n_conflict_constraints += 1;
                stats.n_conflict += 1;

                if settings.use_touched_clique_amo && resource_id == other_resource_id {
                    let tau_plus_1 = t1_out.min(t2_out);
                    let entry = touched_pair_cliques
                        .entry((other_resource_id, tau_plus_1))
                        .or_default();
                    entry.insert(visit_id);
                    entry.insert(other_visit);
                }
            }
        }
    }

    if settings.use_touched_clique_amo {
        let mut active_lit_cache = HashMap::<(VisitId, i32), Bool<L>>::new();
        for ((_, tau_plus_1), visit_set) in touched_pair_cliques {
            if visit_set.len() < 3 {
                continue;
            }
            let mut visits_sorted = visit_set.into_iter().collect::<Vec<_>>();
            visits_sorted.sort_by_key(|visit| visit.0);
            if !clique_amo_encoded.insert(visits_sorted.clone()) {
                continue;
            }
            let active_lits = visits_sorted
                .iter()
                .map(|&visit| {
                    build_active_lit(
                        solver,
                        problem,
                        visits,
                        occupations,
                        new_time_points,
                        fixed_prec_rows,
                        &mut active_lit_cache,
                        settings.use_eager_chain_expansion,
                        visit,
                        tau_plus_1,
                    )
                })
                .collect::<Vec<_>>();
            add_hybrid_amo(solver, &active_lits, settings.use_sc_amo);
            *n_conflict_constraints += 1;
        }
    }
    telemetry.application_time += apply_start.elapsed();
    let added_clauses = encoded_refinement_clauses.len() - before_clauses;
    let added_points = new_time_points.len() - before_time_points;
    telemetry.refinement_clauses_added += crate::solvers::util::counting_solver::get_counts().1 - before_sat_clauses;
    telemetry.refinement_points_added += added_points;
    outcome.model_progress = added_clauses > 0 || added_points > 0;
    outcome
}

#[allow(dead_code)]
fn compute_initial_heuristic_upper_bound<L: satcoder::Lit>(
    mk_env: &impl Fn() -> grb::Env,
    problem: &Problem,
    delay_cost_type: DelayCostType,
    occupations: &TiVec<VisitId, Occ<L>>,
) -> Result<Option<(i32, Vec<Vec<i32>>)>, SolverError> {
    let initial_solution = extract_solution(problem, occupations);
    let env = mk_env();

    for use_strong_branching in [false, true] {
        if let Some(ub_sol) = heuristic::solve_heuristic_better(
            &env,
            problem,
            delay_cost_type,
            use_strong_branching,
            Some(&initial_solution),
        )? {
            let ub_cost = problem.verify_solution(&ub_sol, delay_cost_type).unwrap();
            return Ok(Some((ub_cost, ub_sol)));
        }
    }

    Ok(None)
}

// `compute_effective_earliest` has moved to
// `super::ddd::shared::precedence::chain_earliest` so that
// `maxsat_ladder_sc` and `incremental_sat` use byte-identical
// chain-propagation logic for `delays[0]` setup.

pub fn solve<L: satcoder::Lit + Copy + std::fmt::Debug + 'static>(
    mk_env: impl Fn() -> grb::Env + Send + 'static,
    solver: impl SatInstance<L> + SatSolverWithCore<Lit = L> + std::fmt::Debug,
    problem: &Problem,
    timeout: f64,
    delay_cost_type: DelayCostType,
    output_stats: impl FnMut(String, serde_json::Value),
) -> Result<(Vec<Vec<i32>>, SolveStats), SolverError> {
    solve_with_settings(
        mk_env,
        solver,
        problem,
        timeout,
        delay_cost_type,
        MaxSatDddLadderScSettings::default(),
        output_stats,
    )
}

pub fn solve_with_settings<L: satcoder::Lit + Copy + std::fmt::Debug + 'static>(
    mk_env: impl Fn() -> grb::Env + Send + 'static,
    solver: impl SatInstance<L> + SatSolverWithCore<Lit = L> + std::fmt::Debug,
    problem: &Problem,
    timeout: f64,
    delay_cost_type: DelayCostType,
    settings: MaxSatDddLadderScSettings,
    output_stats: impl FnMut(String, serde_json::Value),
) -> Result<(Vec<Vec<i32>>, SolveStats), SolverError> {
    solve_debug_with_settings(
        mk_env,
        solver,
        problem,
        timeout,
        delay_cost_type,
        settings,
        |_| {},
        output_stats,
    )
}

thread_local! { pub static  WATCH : std::cell::RefCell<Option<(usize,usize)>>  = RefCell::new(None);}

use crate::{debug::DebugInfo, problem::DelayCostType, solvers::util::heuristic};

use crate::solvers::{ddd::shared::costtree::CostTree, SolverError};
pub fn solve_debug<L: satcoder::Lit + Copy + std::fmt::Debug>(
    mk_env: impl Fn() -> grb::Env + Send + 'static,
    solver: impl SatInstance<L> + SatSolverWithCore<Lit = L> + std::fmt::Debug,
    problem: &Problem,
    timeout: f64,
    delay_cost_type: DelayCostType,
    debug_out: impl Fn(DebugInfo),
    output_stats: impl FnMut(String, serde_json::Value),
) -> Result<(Vec<Vec<i32>>, SolveStats), SolverError>
where
    L: 'static,
{
    solve_debug_with_settings(
        mk_env,
        solver,
        problem,
        timeout,
        delay_cost_type,
        MaxSatDddLadderScSettings::default(),
        debug_out,
        output_stats,
    )
}

pub fn solve_debug_with_settings<L: satcoder::Lit + Copy + std::fmt::Debug + 'static>(
    mk_env: impl Fn() -> grb::Env + Send + 'static,
    mut solver: impl SatInstance<L> + SatSolverWithCore<Lit = L> + std::fmt::Debug,
    problem: &Problem,
    timeout: f64,
    delay_cost_type: DelayCostType,
    settings: MaxSatDddLadderScSettings,
    debug_out: impl Fn(DebugInfo),
    mut output_stats: impl FnMut(String, serde_json::Value),
) -> Result<(Vec<Vec<i32>>, SolveStats), SolverError> {
    // TODO
    //  - more eager constraint generation
    //    - propagate simple presedences?
    //    - update all conflicts and presedences when adding new time points?
    //    - smt refinement of the simple presedences?
    //  - get rid of the multiple adding of constraints
    //  - cadical doesn't use false polarity, so it can generate unlimited conflicts when cost is maxed. Two trains pushing each other forward.

    let _p = hprof::enter("solver");

    let start_time: Instant = Instant::now();
    let mut solver_time = std::time::Duration::ZERO;
    let mut stats = SolveStats::default();

    assert!(
        settings.aglr.policy == RefinementPolicy::Legacy
            || !settings.use_eager_chain_expansion,
        "AGLR policies require eager chain expansion to be disabled so the growth budget matches the applied refinement"
    );
    assert!(
        settings.aglr.min_growth > 0,
        "AGLR min_growth must be positive"
    );
    assert!(
        settings.aglr.fraction.is_finite() && (0.0..=1.0).contains(&settings.aglr.fraction),
        "AGLR fraction must be finite and between zero and one"
    );
    assert!(settings.aglr.max_wait > 0, "AGLR max_wait must be positive");
    assert!(!settings.resource_orders || settings.aglr.policy == RefinementPolicy::Legacy,
            "resource-order experiments currently require legacy refinement");
    assert!(!settings.order_transitivity || settings.resource_orders,
            "order transitivity requires resource-order decisions");
    let use_objective_bound = settings.use_objective_bound
        || (settings.aglr.use_objective_bound && settings.aglr.policy != RefinementPolicy::Legacy);

    output_stats(
        "aglr_policy".to_string(),
        settings.aglr.policy.as_str().into(),
    );
    output_stats(
        "aglr_min_growth".to_string(),
        settings.aglr.min_growth.into(),
    );
    output_stats("aglr_fraction".to_string(), settings.aglr.fraction.into());
    output_stats("aglr_max_wait".to_string(), settings.aglr.max_wait.into());
    output_stats(
        "aglr_rescue_progress".to_string(),
        settings.aglr.rescue_progress.as_str().into(),
    );
    output_stats(
        "aglr_heuristic_period".to_string(),
        settings.aglr.heuristic_period.into(),
    );
    output_stats(
        "aglr_heuristic_min_gap".to_string(),
        settings.aglr.heuristic_min_gap.into(),
    );
    output_stats(
        "aglr_use_objective_bound".to_string(),
        settings.aglr.use_objective_bound.into(),
    );
    output_stats("aglr_filter_duplicates".to_string(), settings.aglr.filter_duplicates.into());
    output_stats("maxsat_assumptions".to_string(), settings.assumption_strategy.as_str().into());
    output_stats("maxsat_sparse_costs".to_string(), settings.sparse_costs.into());
    output_stats("maxsat_resource_orders".to_string(), settings.resource_orders.into());
    output_stats("maxsat_order_transitivity".to_string(), settings.order_transitivity.into());
    output_stats("maxsat_objective_bound".to_string(), use_objective_bound.into());

    let mut visits: TiVec<VisitId, (usize, usize)> = TiVec::new();
    let mut resource_visits: Vec<Vec<VisitId>> = Vec::new();
    let mut occupations: TiVec<VisitId, Occ<_>> = TiVec::new();
    let mut touched_intervals = Vec::new();
    let mut conflicts: HashMap<usize, Vec<usize>> = HashMap::new();
    let mut new_time_points = Vec::new();
    let effective_earliest = settings
        .use_precedence_graph
        .then(|| crate::solvers::ddd::shared::precedence::chain_earliest(problem));

    #[allow(unused)]
    let mut core_sizes: BTreeMap<usize, usize> = BTreeMap::new();
    #[allow(unused)]
    let mut processed_core_sizes: BTreeMap<usize, usize> = BTreeMap::new();
    let mut iteration_types: BTreeMap<IterationType, usize> = BTreeMap::new();

    let mut n_timepoints = 0;
    let mut n_conflict_constraints = 0;

    //Build conflict adjacency
    for (a, b) in problem.conflicts.iter() {
        conflicts.entry(*a).or_default().push(*b);
        if *a != *b {
            conflicts.entry(*b).or_default().push(*a);
        }
    }

    //Build Occ
    for (train_idx, train) in problem.trains.iter().enumerate() {
        for (visit_idx, visit) in train.visits.iter().enumerate() {
            let visit_id: VisitId = visits.push_and_get_key((train_idx, visit_idx));
            let earliest = effective_earliest
                .as_ref()
                .map(|bounds| bounds[train_idx][visit_idx])
                .unwrap_or(visit.earliest);

            occupations.push(Occ {
                cost: vec![true.into()],
                cost_tree: if settings.sparse_costs { CostTree::new_sparse() } else { CostTree::new() },
                delays: vec![(true.into(), earliest), (false.into(), i32::MAX)],
                incumbent_idx: 0,
            });
            n_timepoints += 1;

            while resource_visits.len() <= visit.resource_id {
                resource_visits.push(Vec::new());
            }

            // (1.1)
            resource_visits[visit.resource_id].push(visit_id);
            //

            touched_intervals.push(visit_id);
            new_time_points.push((visit_id, true.into(), earliest));

            // Pre-allocate SAT vars + monotonicity clauses for each cost-step
            // threshold time.
            if settings.prealloc_cost_thresholds {
                for t in problem.trains[train_idx].visit_cost_threshold_times(
                    delay_cost_type,
                    visit_idx,
                    earliest,
                ) {
                    let (var, is_new) = occupations[visit_id].time_point(&mut solver, t);
                    if is_new {
                        n_timepoints += 1;
                        new_time_points.push((visit_id, var, t));
                    }
                }
            }
        }
    }

    // The first iteration (0) does not need a solve call; we
    // know it's SAT because there are no constraints yet.
    let mut iteration = 1;
    let mut is_sat = true;

    let mut total_cost = 0;
    let mut soft_constraints = HashMap::new();
    let mut debug_actions = Vec::new();

    // Remember which cliques have already had their full AMO encoded
    // (keyed by sorted visit-set) to dedup AMO emission across iterations.
    //SEED PRECEDENCE ROWS
    let mut clique_amo_encoded: HashSet<Vec<VisitId>> = HashSet::new();
    // Rows already added for fixed-precedence encoding: (visit_id, time).
    let mut fixed_prec_rows: HashSet<(VisitId, i32)> = HashSet::new();
    let mut encoded_refinement_clauses = HashSet::<AglrClauseKey>::new();
    let mut resource_orders = super::resource_orders::ResourceOrders::new(settings.order_transitivity);

    // Optional: seed fixed-precedence (travel-time) constraints from the earliest
    // time points to reduce the number of "travel-time conflict" iterations.
    if settings.seed_sc_from_earliest {
        for visit_id in visits.keys() {
            let (train_idx, visit_idx) = visits[visit_id];
            if visit_idx + 1 >= problem.trains[train_idx].visits.len() {
                continue;
            }
            let (in_var, in_t) = occupations[visit_id].delays[0];
            if settings.use_precedence_graph {
                propagate_precedence(
                    &mut solver,
                    problem,
                    &visits,
                    &mut occupations,
                    &mut new_time_points,
                    &mut fixed_prec_rows,
                    visit_id,
                    in_var,
                    in_t,
                    settings.use_eager_chain_expansion,
                );
            } else if settings.use_eager_chain_expansion {
                let _ = add_fixed_precedence_row(
                    &mut solver,
                    problem,
                    &visits,
                    &mut occupations,
                    &mut new_time_points,
                    &mut fixed_prec_rows,
                    visit_id,
                    in_var,
                    in_t,
                    settings.use_eager_chain_expansion,
                );
            }
        }
    }

    // Async heuristic: instead of blocking on initial heuristic computation
    // at init (5-30s of Gurobi call time), spawn the heuristic thread
    // immediately and let SAT solver start working in parallel. The heuristic
    // result flows in via `heur_thread`'s channel during the main loop, where
    // we update `best_heur` and inject solution timepoints when it arrives.
    const USE_HEURISTIC: bool = true;
    let mut best_heur: Option<(i32, Vec<Vec<i32>>)> = None;
    let mut injected_heuristic_cost: Option<i32> = None;

    // Seed `best_heur` with a quick greedy schedule. Gives a sound UB even
    // when the Gurobi-based heuristic thread isn't running (e.g. license
    // expired), so timeout cases can still report a finite `ub` and
    // downstream tooling can compute a real GAP.
    {
        let greedy_sol = crate::solvers::ddd::shared::greedy::greedy_schedule(problem);
        if let Some(cost) = problem.verify_solution(&greedy_sol, delay_cost_type) {
            best_heur = Some((cost, greedy_sol));
        }
    }

    let heuristic_filter = std::sync::Arc::new(heuristic::HeuristicFilter::new(
        best_heur
            .as_ref()
            .map(|(cost, _)| *cost)
            .unwrap_or(i32::MAX),
    ));

    //UB from Gurobi
    let heur_thread = USE_HEURISTIC.then(|| {
        let (sol_in_tx, sol_in_rx) = std::sync::mpsc::channel();
        let (sol_out_tx, sol_out_rx) = std::sync::mpsc::channel();
        let problem = problem.clone();
        if settings.aglr.policy == RefinementPolicy::Legacy {
            heuristic::spawn_heuristic_thread(
                mk_env,
                sol_in_rx,
                problem,
                delay_cost_type,
                sol_out_tx,
            );
        } else {
            heuristic::spawn_filtered_heuristic_thread(
                mk_env,
                sol_in_rx,
                problem,
                delay_cost_type,
                sol_out_tx,
                heuristic_filter.clone(),
            );
        }
        (sol_in_tx, sol_out_rx)
    });

    let mut aglr_history = CandidateHistory::default();
    let mut aglr_telemetry = AglrTelemetry::default();
    let mut binary_objective = if use_objective_bound {
        let upper = best_heur.as_ref().ok_or_else(|| SolverError::InvalidSolution(
            "objective bound requires a verified initial feasible schedule".to_string()
        ))?.0;
        Some(BinaryObjective::new(&mut solver, upper.try_into().map_err(|_| {
            SolverError::InvalidSolution("negative objective upper bound".to_string())
        })?))
    } else {
        None
    };
    let mut last_progress_iteration = 0usize;
    let mut last_heuristic_submission_iteration = None;

    // Main DDD loop.
    loop {
        // Check timeout at the start of each iteration.
        if start_time.elapsed().as_secs_f64() > timeout {
            let ub = best_heur.map(|(c, _)| c).unwrap_or(i32::MAX);
            println!("TIMEOUT LB={} UB={}", total_cost, ub);

            do_output_stats(
                &mut output_stats,
                iteration,
                &iteration_types,
                &stats,
                &occupations,
                start_time,
                solver_time,
                total_cost,
                ub,
                &aglr_telemetry,
                &heuristic_filter,
            );
            return Err(SolverError::Timeout);
        }

        // Check SAT/UNSAT of the current iteration's formula.
        let _p = hprof::enter("iteration");
        if is_sat {
            // If SAT, extract the solution and check for optimality via the async.
            if let Some((sol_tx, sol_rx)) = heur_thread.as_ref() {
                let period_ready = last_heuristic_submission_iteration
                    .map(|last| {
                        iteration.saturating_sub(last) >= settings.aglr.heuristic_period
                    })
                    .unwrap_or(true);
                let gap_ready = best_heur
                    .as_ref()
                    .map(|(ub, _)| {
                        (*ub - total_cost)
                            .max(0)
                            .try_into()
                            .unwrap_or(usize::MAX)
                            >= settings.aglr.heuristic_min_gap
                    })
                    .unwrap_or(true);
                if period_ready && gap_ready {
                    let sol = extract_solution(problem, &occupations);
                    let _ = sol_tx.send(sol);
                    last_heuristic_submission_iteration = Some(iteration);
                    aglr_telemetry.heuristic_submissions += 1;
                }

                while let Ok((ub_cost, ub_sol)) = sol_rx.try_recv() {
                    if ub_cost < total_cost as i32 {
                        if settings.aglr.policy != RefinementPolicy::Legacy || use_objective_bound {
                            return Err(SolverError::InvalidSolution(format!(
                                "verified AGLR heuristic upper bound {} is below lower bound {}",
                                ub_cost, total_cost
                            )));
                        }
                        println!(
                            "HEURISTIC UB={} is below current LB={}; keeping UB but skipping LB==UB termination this iteration",
                            ub_cost, total_cost
                        );
                        if ub_cost < best_heur.as_ref().map(|(c, _)| *c).unwrap_or(i32::MAX) {
                            best_heur = Some((ub_cost, ub_sol));
                            heuristic_filter.update_best(ub_cost);
                            last_progress_iteration = iteration;
                        }
                        continue;
                    }
                    if ub_cost == total_cost as i32 {
                        println!("HEURISTIC UB=LB");
                        println!("TERMINATE HEURISTIC");
                        println!(
                            "MAXSAT ITERATIONS {}  {}",
                            n_conflict_constraints, iteration
                        );
                        do_output_stats(
                            &mut output_stats,
                            iteration,
                            &iteration_types,
                            &stats,
                            &occupations,
                            start_time,
                            solver_time,
                            total_cost,
                            ub_cost,
                            &aglr_telemetry,
                            &heuristic_filter,
                        );

                        return Ok((ub_sol, stats));
                    }

                    if ub_cost < best_heur.as_ref().map(|(c, _)| *c).unwrap_or(i32::MAX) {
                        best_heur = Some((ub_cost, ub_sol));
                        heuristic_filter.update_best(ub_cost);
                        last_progress_iteration = iteration;
                    }
                }
            }

            // Extract the current solution and check for travel-time and resource conflicts.
            let mut found_travel_time_conflict = false;
            let mut found_resource_conflict = false;

            if settings.aglr.policy == RefinementPolicy::Legacy {
                // travel time conflict check.
                for visit_id in touched_intervals.iter().copied() {
                    let _p = hprof::enter("travel time check");
                    let (train_idx, visit_idx) = visits[visit_id];
                    let next_visit: Option<VisitId> =
                        if visit_idx + 1 < problem.trains[train_idx].visits.len() {
                            Some((usize::from(visit_id) + 1).into())
                        } else {
                            None
                        };

                    // GATHER INFORMATION ABOUT TWO CONSECUTIVE TIME POINTS
                    let t1_in = occupations[visit_id].incumbent_time();
                    let visit = problem.trains[train_idx].visits[visit_idx];

                    if let Some(next_visit) = next_visit {
                        let v1 = &occupations[visit_id];
                        let v2 = &occupations[next_visit];
                        let t1_out = v2.incumbent_time();

                        // TRAVEL TIME CONFLICT
                        if t1_in + visit.travel_time > t1_out {
                            found_travel_time_conflict = true;

                            debug_actions.push(SolverAction::TravelTimeConflict(
                                ResourceInterval {
                                    train_idx,
                                    visit_idx,
                                    resource_idx: visit.resource_id,
                                    time_in: t1_in,
                                    time_out: t1_out,
                                },
                            ));

                            // When `use_eager_chain_expansion` is OFF, emit the
                            // travel-time clause inline — matches ladder semantics
                            // exactly (no dedup, no short-circuit). The dedup +
                            // earliest-next short-circuit inside
                            // `add_fixed_precedence_row` change the emitted CNF in
                            // subtle ways that make `ScNothing != Ldr` even when
                            // every other flag is off.
                            if settings.use_eager_chain_expansion {
                                let in_var = v1.delays[v1.incumbent_idx].0;
                                let in_t = v1.incumbent_time();
                                let _ = add_fixed_precedence_row(
                                    &mut solver,
                                    problem,
                                    &visits,
                                    &mut occupations,
                                    &mut new_time_points,
                                    &mut fixed_prec_rows,
                                    visit_id,
                                    in_var,
                                    in_t,
                                    settings.use_eager_chain_expansion,
                                );
                            } else {
                                let t1_in_var = v1.delays[v1.incumbent_idx].0;
                                let new_t = v1.incumbent_time() + visit.travel_time;
                                let (t1_earliest_out_var, t1_is_new) =
                                    occupations[next_visit].time_point(&mut solver, new_t);
                                SatInstance::add_clause(
                                    &mut solver,
                                    vec![!t1_in_var, t1_earliest_out_var],
                                );
                                if t1_is_new {
                                    new_time_points.push((next_visit, t1_earliest_out_var, new_t));
                                }
                            }
                            stats.n_travel += 1;
                        }
                    }
                }

                //Resource conflict check: find all pairs of overlapping visits on conflicting resources,
                //and add a clause to forbid the current overlap.
                let _p = hprof::enter("conflict check");
                let mut deconflicted_train_pairs: HashSet<(usize, usize)> = HashSet::new();

                // Lite clique aggregation for the pair-based scan: each
                // (resource, tau_plus_1) accumulates visits that ended up in a
                // detected conflict. After the scan, cliques with ≥3 members
                // are encoded as a single AMO over `active(v, tau_plus_1)`
                // literals — opt-in via `use_touched_clique_amo`. This lets
                // SC AMO encoding fire WITHOUT the heavier interval-
                // graph clique-cover pass.
                let mut touched_pair_cliques: HashMap<(usize, i32), HashSet<VisitId>> =
                    HashMap::new();

                touched_intervals.retain(|visit_id| {
                    let visit_id = *visit_id;
                    let (train_idx, visit_idx) = visits[visit_id];
                    let next_visit: Option<VisitId> =
                        if visit_idx + 1 < problem.trains[train_idx].visits.len() {
                            Some((usize::from(visit_id) + 1).into())
                        } else {
                            None
                        };

                    let t1_in = occupations[visit_id].incumbent_time();
                    let visit = problem.trains[train_idx].visits[visit_idx];
                    let mut retain = false;

                    if let Some(conflicting_resources) = conflicts.get(&visit.resource_id) {
                        for other_resource in conflicting_resources.iter().copied() {
                            let t1_out = next_visit
                                .map(|nx| occupations[nx].incumbent_time())
                                .unwrap_or(t1_in + visit.travel_time);

                            for other_visit in resource_visits[other_resource].iter().copied() {
                                if usize::from(visit_id) == usize::from(other_visit) {
                                    continue;
                                }

                                let v2 = &occupations[other_visit];
                                let t2_in = v2.incumbent_time();
                                let (other_train_idx, other_visit_idx) = visits[other_visit];

                                if other_train_idx == train_idx {
                                    continue;
                                }

                                let other_next_visit: Option<VisitId> = if other_visit_idx + 1
                                    < problem.trains[other_train_idx].visits.len()
                                {
                                    Some((usize::from(other_visit) + 1).into())
                                } else {
                                    None
                                };

                                let t2_out = other_next_visit
                                    .map(|v| occupations[v].incumbent_time())
                                    .unwrap_or_else(|| {
                                        let other_v =
                                            problem.trains[other_train_idx].visits[other_visit_idx];
                                        t2_in + other_v.travel_time
                                    });

                                if t1_out <= t2_in || t2_out <= t1_in {
                                    continue;
                                }

                                if !deconflicted_train_pairs.insert((train_idx, other_train_idx))
                                    || !deconflicted_train_pairs
                                        .insert((other_train_idx, train_idx))
                                {
                                    retain = true;
                                    continue;
                                }

                                found_resource_conflict = true;
                                stats.n_conflict += 1;

                                let (delay_t2, t2_is_new) =
                                    occupations[other_visit].time_point(&mut solver, t1_out);
                                let (delay_t1, t1_is_new) =
                                    occupations[visit_id].time_point(&mut solver, t2_out);

                                if t1_is_new {
                                    new_time_points.push((visit_id, delay_t1, t2_out));
                                }
                                if t2_is_new {
                                    new_time_points.push((other_visit, delay_t2, t1_out));
                                }

                                // Eager SC-style precedence propagation: pre-emptively add a
                                // fixed-precedence row at the new time point (delay_t1, delay_t2)
                                // for the train's NEXT visit, propagating travel time forward.
                                //
                                // Gated on `use_eager_chain_expansion` so that this entire block
                                // is a no-op when the flag is OFF — that yields semantics
                                // equivalent to `maxsat_ladder.rs` (which only enforces travel
                                // time lazily in the dedicated travel-time-conflict branch above).
                                //
                                // With the flag ON we keep the previous eager behaviour: better
                                // unit propagation, but +50–70% more time points per benchmark
                                // (see sc-vs-ladder analysis).
                                if settings.use_eager_chain_expansion {
                                    let _ = add_fixed_precedence_row(
                                        &mut solver,
                                        problem,
                                        &visits,
                                        &mut occupations,
                                        &mut new_time_points,
                                        &mut fixed_prec_rows,
                                        visit_id,
                                        delay_t1,
                                        t2_out,
                                        settings.use_eager_chain_expansion,
                                    );

                                    let _ = add_fixed_precedence_row(
                                        &mut solver,
                                        problem,
                                        &visits,
                                        &mut occupations,
                                        &mut new_time_points,
                                        &mut fixed_prec_rows,
                                        other_visit,
                                        delay_t2,
                                        t1_out,
                                        settings.use_eager_chain_expansion,
                                    );
                                }

                                let t1_out_lit = next_visit
                                    .map(|v| occupations[v].delays[occupations[v].incumbent_idx].0)
                                    .unwrap_or_else(|| true.into());
                                let t2_out_lit = other_next_visit
                                    .map(|v| occupations[v].delays[occupations[v].incumbent_idx].0)
                                    .unwrap_or_else(|| true.into());

                                if settings.resource_orders {
                                    // A last visit has no next-time variable: its exit
                                    // threshold is guarded by its own entry threshold.
                                    let first_guard = next_visit.map(|_| t1_out_lit)
                                        .unwrap_or(occupations[visit_id].delays[occupations[visit_id].incumbent_idx].0);
                                    let second_guard = other_next_visit.map(|_| t2_out_lit)
                                        .unwrap_or(occupations[other_visit].delays[occupations[other_visit].incumbent_idx].0);
                                    let (created, rows, triangles) = resource_orders.add(
                                        &mut solver, visit_id.0, other_visit.0, t1_out, t2_out,
                                        first_guard, second_guard, delay_t1, delay_t2,
                                    );
                                    stats.resource_order_pairs += usize::from(created);
                                    stats.resource_order_rows += rows;
                                    stats.resource_order_triangles += triangles;
                                    n_conflict_constraints += rows + 2 * triangles;
                                } else {
                                    n_conflict_constraints += 1;
                                    SatInstance::add_clause(
                                        &mut solver,
                                        vec![!t1_out_lit, !t2_out_lit, delay_t1, delay_t2],
                                    );
                                }

                                // Touched-clique-AMO aggregation: record
                                // both visits at the (resource, tau_plus_1)
                                // of their overlap. Only meaningful for
                                // self-conflicts (both on same resource);
                                // cross-resource conflicts skipped.
                                if settings.use_touched_clique_amo
                                    && visit.resource_id == other_resource
                                {
                                    let tau_plus_1 = t1_out.min(t2_out);
                                    let entry = touched_pair_cliques
                                        .entry((other_resource, tau_plus_1))
                                        .or_default();
                                    entry.insert(visit_id);
                                    entry.insert(other_visit);
                                }

                                retain = true;
                            }
                        }
                    }
                    retain
                });

                // ───────── Touched-clique AMO (post-retain) ─────────
                // For each (resource, tau_plus_1) that accumulated ≥ 3
                // visits during the pair-based scan, emit a single AMO
                // over their `active(v, tau_plus_1)` literals. Choice of
                // pairwise vs SC encoding follows `use_sc_amo`.
                if settings.use_touched_clique_amo {
                    let mut active_lit_cache_tcamo: HashMap<(VisitId, i32), Bool<L>> =
                        HashMap::new();
                    let entries: Vec<((usize, i32), HashSet<VisitId>)> =
                        touched_pair_cliques.into_iter().collect();
                    for ((_, tau_plus_1), visit_set) in entries {
                        if visit_set.len() < 3 {
                            continue;
                        }
                        let mut visits_sorted: Vec<VisitId> = visit_set.into_iter().collect();
                        visits_sorted.sort_by_key(|v| v.0);
                        if !clique_amo_encoded.insert(visits_sorted.clone()) {
                            continue;
                        }
                        let mut active_lits: Vec<Bool<L>> = Vec::with_capacity(visits_sorted.len());
                        for &v in &visits_sorted {
                            let lit = build_active_lit(
                                &mut solver,
                                problem,
                                &visits,
                                &mut occupations,
                                &mut new_time_points,
                                &mut fixed_prec_rows,
                                &mut active_lit_cache_tcamo,
                                settings.use_eager_chain_expansion,
                                v,
                                tau_plus_1,
                            );
                            active_lits.push(lit);
                        }
                        add_hybrid_amo(&mut solver, &active_lits, settings.use_sc_amo);
                        n_conflict_constraints += 1;
                    }
                }
            } else {
                let rescue_after = settings.aglr.max_wait.saturating_mul(2);
                let rescue = rescue_after > 0
                    && iteration.saturating_sub(last_progress_iteration) >= rescue_after;
                let outcome = detect_and_apply_aglr(
                    &mut solver,
                    problem,
                    &visits,
                    &resource_visits,
                    &conflicts,
                    &mut occupations,
                    &mut new_time_points,
                    &mut fixed_prec_rows,
                    &mut clique_amo_encoded,
                    &mut encoded_refinement_clauses,
                    settings,
                    &mut aglr_history,
                    rescue,
                    &mut stats,
                    &mut debug_actions,
                    &mut n_conflict_constraints,
                    &mut aglr_telemetry,
                );
                found_travel_time_conflict = outcome.found_travel;
                found_resource_conflict = outcome.found_resource;
                if outcome.model_progress
                    && settings.aglr.rescue_progress
                        == super::settings::RescueProgressPolicy::Model
                {
                    last_progress_iteration = iteration;
                    aglr_telemetry.model_progress_iterations += 1;
                }
                touched_intervals.clear();
            }

            // If UNSAT, add conflict-graph-based constraints, optimal check
            let iterationtype = if found_travel_time_conflict && found_resource_conflict {
                IterationType::TravelAndResourceConflict
            } else if found_travel_time_conflict {
                IterationType::TravelTimeConflict
            } else if found_resource_conflict {
                IterationType::ResourceConflict
            } else {
                IterationType::Solution
            };

            *iteration_types.entry(iterationtype).or_default() += 1;

            if !(found_resource_conflict || found_travel_time_conflict) {
                // Incumbent times are feasible and optimal.

                const USE_LP_MINIMIZE: bool = false;

                let trains = if !USE_LP_MINIMIZE {
                    extract_solution(problem, &occupations)
                } else {
                    panic!()
                };

                if settings.aglr.policy != RefinementPolicy::Legacy || settings.resource_orders || use_objective_bound {
                    let validation_start = Instant::now();
                    let verified_cost = problem.verify_solution(&trains, delay_cost_type);
                    aglr_telemetry.final_validation_time += validation_start.elapsed();
                    if verified_cost != Some(total_cost) {
                        return Err(SolverError::InvalidSolution(format!(
                            "AGLR final validation returned {:?}, expected {}",
                            verified_cost, total_cost
                        )));
                    }
                }

                println!(
                    "Finished with cost {} iterations {} solver {:?}",
                    total_cost, iteration, solver
                );
                println!("Core size bins {:?}", core_sizes);
                println!("Iteration types {:?}", iteration_types);
                debug_out(DebugInfo {
                    iteration,
                    actions: std::mem::take(&mut debug_actions),
                    solution: extract_solution(problem, &occupations),
                });

                stats.satsolver = format!("{:?}", solver);

                println!(
                    "STATS {} {} {} {} {} {} {} {}",
                    /* iter */ iteration,
                    /* objective iters */
                    iteration_types.get(&IterationType::Objective).unwrap_or(&0),
                    /* travel iters */
                    iteration_types
                        .get(&IterationType::TravelTimeConflict)
                        .unwrap_or(&0),
                    /* resource iters */
                    iteration_types
                        .get(&IterationType::ResourceConflict)
                        .unwrap_or(&0),
                    /* both iters */
                    iteration_types
                        .get(&IterationType::TravelAndResourceConflict)
                        .unwrap_or(&0),
                    /* solution iters */
                    iteration_types.get(&IterationType::Solution).unwrap_or(&0),
                    /* num traveltime */ stats.n_travel,
                    /* num conflicts */ stats.n_conflict,
                );

                do_output_stats(
                    &mut output_stats,
                    iteration,
                    &iteration_types,
                    &stats,
                    &occupations,
                    start_time,
                    solver_time,
                    total_cost,
                    total_cost,
                    &aglr_telemetry,
                    &heuristic_filter,
                );

                println!("VARSCLAUSES {:?}", solver);

                println!(
                    "MAXSAT ITERATIONS {}  {}",
                    n_conflict_constraints, iteration
                );
                return Ok((trains, stats));
            }
        }

        // Only original CostTree terms enter the hard objective bound; RC2
        // relaxation totalizers are not costs and must never be counted twice.
        let mut new_objective_terms = Vec::new();
        // Add new time points and their costs to the solver.
        for (visit, new_timepoint_var, new_t) in new_time_points.drain(..) {
            n_timepoints += 1;
            let (train_idx, visit_idx) = visits[visit];

            let new_timepoint_cost =
                problem.trains[train_idx].visit_delay_cost(delay_cost_type, visit_idx, new_t);

            if new_timepoint_cost > 0 {
                const USE_COST_TREE: bool = true;
                if !USE_COST_TREE {
                    for cost in occupations[visit].cost.len()..=new_timepoint_cost {
                        let prev_cost_var = occupations[visit].cost[cost - 1];
                        let next_cost_var = SatInstance::new_var(&mut solver);

                        SatInstance::add_clause(&mut solver, vec![!next_cost_var, prev_cost_var]);

                        occupations[visit].cost.push(next_cost_var);
                        assert!(cost + 1 == occupations[visit].cost.len());

                        soft_constraints.insert(!next_cost_var, (Soft::Primary, 1, 1));
                    }

                    SatInstance::add_clause(
                        &mut solver,
                        vec![
                            !new_timepoint_var,
                            occupations[visit].cost[new_timepoint_cost],
                        ],
                    );
                } else {
                    // Direct insertion in callback — no Vec buffering overhead.
                    // Matches the ladder (non-SC) pattern for lower allocation cost.
                    occupations[visit].cost_tree.add_cost(
                        &mut solver,
                        new_timepoint_var,
                        new_timepoint_cost,
                        &mut |weight, cost_var| {
                            stats.cost_terms += 1;
                            soft_constraints.insert(!cost_var, (Soft::Primary, weight, weight));
                            if binary_objective.is_some() {
                                new_objective_terms.push((cost_var, weight));
                            }
                        },
                    );
                }
            }

            // set the cost for this new time point.
        }

        if let Some(objective) = binary_objective.as_mut() {
            let encoding_start = Instant::now();
            if let Some((upper, _)) = best_heur.as_ref() {
                if objective.tighten(&mut solver, *upper as usize) {
                    aglr_telemetry.objective_bound_updates += 1;
                }
            }
            for (literal, weight) in new_objective_terms {
                objective.add_term(&mut solver, literal, weight);
                aglr_telemetry.objective_bound_terms += 1;
            }
            aglr_telemetry.objective_bound_time += encoding_start.elapsed();
        }

        //Solve
        //Build asssumption
        let mut n_assumps = settings.assumption_strategy.initial(soft_constraints.len());
        let mut assumptions = soft_constraints
            .iter()
            .map(|(k, (_, w, _))| (*k, *w))
            .collect::<Vec<_>>();
        assumptions.sort_by(|a, b| b.1.cmp(&a.1));

        log::info!(
            "solving it{} with {} timepoints {} conflicts",
            iteration,
            n_timepoints,
            n_conflict_constraints
        );

        //grow assumptions
        let core = loop {
            stats.sat_calls += 1;
            let solve_start = Instant::now();
            let result = {
                let _p = hprof::enter("sat check");
                SatSolverWithCore::solve_with_assumptions(
                    &mut solver,
                    assumptions.iter().map(|(k, _)| *k).take(n_assumps),
                )
            };
            solver_time += solve_start.elapsed();

            //Update incumbent
            match result {
                satcoder::SatResultWithCore::Sat(_) if n_assumps < soft_constraints.len() => {
                    stats.partial_sat_calls += 1;
                    n_assumps = settings.assumption_strategy.next(n_assumps, soft_constraints.len());
                }
                satcoder::SatResultWithCore::Sat(model) => {
                    is_sat = true;
                    stats.n_sat += 1;
                    let _p = hprof::enter("update times");

                    for (visit, this_occ) in occupations.iter_mut_enumerated() {
                        let mut touched = false;

                        while model.value(&this_occ.delays[this_occ.incumbent_idx + 1].0) {
                            this_occ.incumbent_idx += 1;
                            touched = true;
                        }
                        while !model.value(&this_occ.delays[this_occ.incumbent_idx].0) {
                            this_occ.incumbent_idx -= 1;
                            touched = true;
                        }
                        let (_train_idx, visit_idx) = visits[visit];

                        if touched {
                            // We are really interested not in the visits, but the resource occupation
                            // intervals. Therefore, also the previous visit has been touched by this visit.
                            if visit_idx > 0 {
                                let prev_visit = (Into::<usize>::into(visit) - 1).into();
                                if touched_intervals.last() != Some(&prev_visit) {
                                    touched_intervals.push(prev_visit);
                                }
                            }
                            touched_intervals.push(visit);
                        }
                    }

                    //Local Minimization: Optimize incumbent solution by trying to move each visit earlier as much as possible
                    const USE_LOCAL_MINIMIZE: bool = true;
                    if USE_LOCAL_MINIMIZE {
                        let mut last_mod = 0;
                        let mut i = 0;
                        let occs_len = occupations.len();
                        assert!(visits.len() == occupations.len());
                        while last_mod < occs_len {
                            let mut touched = false;

                            let visit_id = VisitId(i % occs_len as u32);
                            while occupations[visit_id].incumbent_idx > 0 {
                                // We can always leave earlier, so the critical interval is
                                // from this event to the next.

                                let t1_in = occupations[visit_id].delays
                                    [occupations[visit_id].incumbent_idx]
                                    .1;
                                let t1_in_new = occupations[visit_id].delays
                                    [occupations[visit_id].incumbent_idx - 1]
                                    .1;

                                let (train_idx, visit_idx) = visits[visit_id];
                                let visit = problem.trains[train_idx].visits[visit_idx];

                                let next_visit: Option<VisitId> =
                                    if visit_idx + 1 < problem.trains[train_idx].visits.len() {
                                        Some((usize::from(visit_id) + 1).into())
                                    } else {
                                        None
                                    };

                                let prev_visit: Option<VisitId> = if visit_idx > 0 {
                                    Some((usize::from(visit_id) - 1).into())
                                } else {
                                    None
                                };

                                let t1_prev_earliest_out = prev_visit
                                    .map(|v| {
                                        let (tidx, vidx) = visits[v];
                                        let travel_time =
                                            problem.trains[tidx].visits[vidx].travel_time;
                                        occupations[v].incumbent_time() + travel_time
                                    })
                                    .unwrap_or(i32::MIN);

                                let travel_ok = t1_prev_earliest_out <= t1_in_new;

                                let t1_out = next_visit
                                    .map(|nx| occupations[nx].incumbent_time())
                                    .unwrap_or(t1_in + visit.travel_time);

                                let can_reduce = travel_ok
                                    && conflicts
                                        .get(&visit.resource_id)
                                        .iter()
                                        .flat_map(|rs| rs.iter())
                                        .copied()
                                        .all(|other_resource| {
                                            resource_visits[other_resource]
                                                .iter()
                                                .copied()
                                                .filter(|other_visit| {
                                                    usize::from(visit_id)
                                                        != usize::from(*other_visit)
                                                })
                                                .filter(|other_visit| {
                                                    visits[*other_visit].0 != train_idx
                                                })
                                                .all(|other_visit| {
                                                    let v2 = &occupations[other_visit];
                                                    let t2_in = v2.incumbent_time();
                                                    let (other_train_idx, other_visit_idx) =
                                                        visits[other_visit];
                                                    let other_next_visit: Option<VisitId> =
                                                        if other_visit_idx + 1
                                                            < problem.trains[other_train_idx]
                                                                .visits
                                                                .len()
                                                        {
                                                            Some(
                                                                (usize::from(other_visit) + 1)
                                                                    .into(),
                                                            )
                                                        } else {
                                                            None
                                                        };

                                                    let t2_out = other_next_visit
                                                        .map(|v| occupations[v].incumbent_time())
                                                        .unwrap_or_else(|| {
                                                            let other_visit = problem.trains
                                                                [other_train_idx]
                                                                .visits[other_visit_idx];
                                                            t2_in + other_visit.travel_time
                                                        });
                                                    t1_out <= t2_in || t2_out <= t1_in_new
                                                })
                                        });

                                if can_reduce {
                                    occupations[visit_id].incumbent_idx -= 1;
                                    touched = true;
                                    last_mod = 0;
                                } else {
                                    break;
                                }
                            }

                            i += 1;

                            if touched {
                                let visit_idx = visits[visit_id].1;
                                if visit_idx > 0 {
                                    let prev_visit = (Into::<usize>::into(visit_id) - 1).into();
                                    if touched_intervals.last() != Some(&prev_visit) {
                                        touched_intervals.push(prev_visit);
                                    }
                                }
                                touched_intervals.push(visit_id);
                            } else {
                                last_mod += 1;
                            }
                        }
                    }

                    debug_out(DebugInfo {
                        iteration,
                        actions: std::mem::take(&mut debug_actions),
                        solution: extract_solution(problem, &occupations),
                    });

                    break None;
                }

                satcoder::SatResultWithCore::Unsat(core) => {
                    is_sat = false;
                    stats.n_unsat += 1;
                    break Some(core);
                }
            }
        };

        //Core handling RC2
        if let Some(core) = core {
            let _p = hprof::enter("treat core");

            if core.len() == 0 {
                // SC-specific fallback: when the precedence graph is OFF but
                // some other SC feature is ON, an empty core may indicate
                // missing precedence info rather than true infeasibility — try
                // injecting the best heuristic as a recovery step.
                //
                // Pure-ladder mode (all SC features off) skips this branch
                // entirely so behaviour matches `maxsat_ladder.rs` exactly.
                let any_other_sc_feature =
                    settings.use_eager_chain_expansion || settings.use_touched_clique_amo;
                if !settings.use_precedence_graph && any_other_sc_feature {
                    if let Some((ub_cost, ub_sol)) = best_heur.as_ref() {
                        if injected_heuristic_cost != Some(*ub_cost) {
                            inject_solution_timepoints_maxsat(
                                &mut solver,
                                problem,
                                &visits,
                                &mut occupations,
                                &mut new_time_points,
                                &mut fixed_prec_rows,
                                settings.use_eager_chain_expansion,
                                ub_sol,
                            );
                            injected_heuristic_cost = Some(*ub_cost);
                            iteration += 1;
                            continue;
                        }
                    }
                }
                if binary_objective.is_some() {
                    return Err(SolverError::InvalidSolution(
                        "bounded model is UNSAT despite a verified feasible upper bound".to_string()
                    ));
                }
                return Err(SolverError::NoSolution); // UNSAT
            }

            let core = core.iter().map(|c| Bool::Lit(*c)).collect::<Vec<_>>();

            *iteration_types.entry(IterationType::Objective).or_default() += 1;
            debug_actions.push(SolverAction::Core(core.len()));

            let min_weight = core.iter().map(|c| soft_constraints[c].1).min().unwrap();
            assert!(min_weight >= 1);
            stats.core_literals += core.len();
            stats.max_core_size = stats.max_core_size.max(core.len());
            stats.unit_weight_cores += usize::from(min_weight == 1);

            for c in core.iter() {
                let (soft, cost, original_cost) = soft_constraints.remove(c).unwrap();

                assert!(cost >= min_weight);
                let new_cost = cost - min_weight;
                match soft {
                    Soft::Primary => {
                        if new_cost > 0 {
                            soft_constraints.insert(*c, (Soft::Primary, new_cost, original_cost));
                        } else {
                        }
                        /* primary soft constraint, when we relax to new_cost=0 we are done */
                    }
                    Soft::Totalizer(mut tot, bound) => {
                        if new_cost > 0 {
                            soft_constraints
                                .insert(*c, (Soft::Totalizer(tot, bound), new_cost, original_cost));
                        } else {
                            let new_bound = bound + 1;
                            tot.increase_bound(&mut solver, new_bound as u32);
                            if new_bound < tot.rhs().len() {
                                soft_constraints.insert(
                                    !tot.rhs()[new_bound], // tot <= 2, 3, 4...
                                    (
                                        Soft::Totalizer(tot, new_bound),
                                        original_cost,
                                        original_cost,
                                    ),
                                );
                            } else {
                            }
                        }
                    }
                }
            }

            total_cost += min_weight as i32;
            last_progress_iteration = iteration;
            println!("    LB={}", total_cost);

            if total_cost as i32 == best_heur.as_ref().map(|(c, _)| *c).unwrap_or(i32::MAX) {
                println!("TERMINATE HEURISTIC");
                println!(
                    "MAXSAT ITERATIONS {}  {}",
                    n_conflict_constraints, iteration
                );
                do_output_stats(
                    &mut output_stats,
                    iteration,
                    &iteration_types,
                    &stats,
                    &occupations,
                    start_time,
                    solver_time,
                    total_cost,
                    total_cost,
                    &aglr_telemetry,
                    &heuristic_filter,
                );

                return Ok((best_heur.unwrap().1, stats));
            }

            if core.len() > 1 {
                let bound = 1;
                let tot = Totalizer::count(&mut solver, core.iter().map(|c| !*c), bound as u32);
                assert!(bound < tot.rhs().len());

                soft_constraints.insert(
                    !tot.rhs()[bound], // tot <= 1
                    (Soft::Totalizer(tot, bound), min_weight, min_weight),
                );
            } else {
                SatInstance::add_clause(&mut solver, vec![!core[0]]);
            }
        }

        iteration += 1;
    }
}

fn do_output_stats<L: satcoder::Lit>(
    output_stats: &mut impl FnMut(String, serde_json::Value),
    iteration: usize,
    iteration_types: &BTreeMap<IterationType, usize>,
    stats: &SolveStats,
    occupations: &TiVec<VisitId, Occ<L>>,
    start_time: Instant,
    solver_time: std::time::Duration,
    lb: i32,
    ub: i32,
    aglr: &AglrTelemetry,
    heuristic_filter: &heuristic::HeuristicFilter,
) {
    output_stats("iterations".to_string(), iteration.into());
    output_stats("maxsat_sat_calls".to_string(), stats.sat_calls.into());
    output_stats("maxsat_partial_sat_calls".to_string(), stats.partial_sat_calls.into());
    output_stats("maxsat_cost_terms".to_string(), stats.cost_terms.into());
    output_stats("maxsat_resource_order_pairs".to_string(), stats.resource_order_pairs.into());
    output_stats("maxsat_resource_order_rows".to_string(), stats.resource_order_rows.into());
    output_stats("maxsat_resource_order_triangles".to_string(), stats.resource_order_triangles.into());
    output_stats("maxsat_core_literals".to_string(), stats.core_literals.into());
    output_stats("maxsat_core_max_size".to_string(), stats.max_core_size.into());
    output_stats("maxsat_unit_weight_cores".to_string(), stats.unit_weight_cores.into());
    output_stats("maxsat_objective_bound_terms".to_string(), aglr.objective_bound_terms.into());
    output_stats("maxsat_objective_bound_updates".to_string(), aglr.objective_bound_updates.into());
    output_stats("maxsat_objective_bound_time".to_string(), aglr.objective_bound_time.as_secs_f64().into());
    output_stats(
        "objective_iters".to_string(),
        (*iteration_types.get(&IterationType::Objective).unwrap_or(&0)).into(),
    );
    output_stats(
        "travel_iters".to_string(),
        (*iteration_types
            .get(&IterationType::TravelTimeConflict)
            .unwrap_or(&0))
        .into(),
    );
    output_stats(
        "resource_iters".to_string(),
        (*iteration_types
            .get(&IterationType::ResourceConflict)
            .unwrap_or(&0))
        .into(),
    );
    output_stats(
        "travel_and_resource_iters".to_string(),
        (*iteration_types
            .get(&IterationType::TravelAndResourceConflict)
            .unwrap_or(&0))
        .into(),
    );
    output_stats("num_traveltime".to_string(), stats.n_travel.into());
    output_stats("num_conflicts".to_string(), stats.n_conflict.into());
    // Total SAT variables allocated and CNF clauses added throughout the
    // entire solve (initial encoding + every DDD refinement iteration).
    // Counts come from the per-thread `CountingSolver` wrapper around the
    // underlying solver; caller must reset before invoking `solve()`.
    let (n_vars_total, n_clauses_total) = crate::solvers::util::counting_solver::get_counts();
    output_stats("num_vars_total".to_string(), n_vars_total.into());
    output_stats("num_clauses_total".to_string(), n_clauses_total.into());
    output_stats(
        "num_time_points".to_string(),
        occupations
            .iter()
            .map(|o| o.delays.len() - 1)
            .sum::<usize>()
            .into(),
    );
    output_stats(
        "max_time_points".to_string(),
        occupations
            .iter()
            .map(|o| o.delays.len() - 1)
            .max()
            .unwrap()
            .into(),
    );
    output_stats(
        "avg_time_points".to_string(),
        ((occupations
            .iter()
            .map(|o| o.delays.len() - 1)
            .sum::<usize>() as f64)
            / (occupations.len() as f64))
            .into(),
    );

    output_stats(
        "total_time".to_string(),
        start_time.elapsed().as_secs_f64().into(),
    );
    output_stats("solver_time".to_string(), solver_time.as_secs_f64().into());
    output_stats(
        "algorithm_time".to_string(),
        (start_time.elapsed().as_secs_f64() - solver_time.as_secs_f64()).into(),
    );
    output_stats("lb".to_string(), lb.into());
    output_stats("ub".to_string(), ub.into());
    output_stats(
        "aglr_detection_time".to_string(),
        aglr.detection_time.as_secs_f64().into(),
    );
    output_stats(
        "aglr_selection_time".to_string(),
        aglr.selection_time.as_secs_f64().into(),
    );
    output_stats(
        "aglr_application_time".to_string(),
        aglr.application_time.as_secs_f64().into(),
    );
    output_stats(
        "aglr_candidates_detected".to_string(),
        aglr.candidates_detected.into(),
    );
    output_stats(
        "aglr_candidates_selected".to_string(),
        aglr.candidates_selected.into(),
    );
    output_stats("aglr_all_growth".to_string(), aglr.all_growth.into());
    output_stats(
        "aglr_selected_growth".to_string(),
        aglr.selected_growth.into(),
    );
    output_stats(
        "aglr_mandatory_selected".to_string(),
        aglr.mandatory_selected.into(),
    );
    output_stats(
        "aglr_rescue_iterations".to_string(),
        aglr.rescue_iterations.into(),
    );
    output_stats("aglr_max_age".to_string(), aglr.max_age.into());
    output_stats(
        "aglr_duplicate_clauses_skipped".to_string(),
        aglr.duplicate_clauses_skipped.into(),
    );
    output_stats(
        "aglr_model_progress_iterations".to_string(),
        aglr.model_progress_iterations.into(),
    );
    output_stats(
        "aglr_heuristic_submissions".to_string(),
        aglr.heuristic_submissions.into(),
    );
    output_stats("aglr_objective_bound_terms".to_string(), aglr.objective_bound_terms.into());
    output_stats("aglr_objective_bound_updates".to_string(), aglr.objective_bound_updates.into());
    output_stats("aglr_objective_bound_time".to_string(), aglr.objective_bound_time.as_secs_f64().into());
    output_stats("aglr_duplicate_candidates_filtered".to_string(), aglr.duplicate_candidates_filtered.into());
    output_stats("aglr_refinement_clauses_added".to_string(), aglr.refinement_clauses_added.into());
    output_stats("aglr_refinement_points_added".to_string(), aglr.refinement_points_added.into());
    output_stats("aglr_rescue_candidates_selected".to_string(), aglr.rescue_candidates_selected.into());
    output_stats("aglr_growth_ratio".to_string(), if aglr.all_growth == 0 { 0.0 } else { aglr.selected_growth as f64 / aglr.all_growth as f64 }.into());
    let heuristic = heuristic_filter.snapshot();
    output_stats(
        "heuristic_candidates_received".to_string(),
        heuristic.received.into(),
    );
    output_stats(
        "heuristic_validation_skipped_non_improving".to_string(),
        heuristic.skipped_non_improving.into(),
    );
    output_stats(
        "heuristic_validation_skipped_duplicate".to_string(),
        heuristic.skipped_duplicate.into(),
    );
    output_stats(
        "heuristic_candidates_verified".to_string(),
        heuristic.verified.into(),
    );
    output_stats(
        "heuristic_verification_time".to_string(),
        heuristic.verification_seconds.into(),
    );
    output_stats(
        "validation_time_seconds".to_string(),
        (aglr.final_validation_time.as_secs_f64() + heuristic.verification_seconds).into(),
    );
}

fn extract_solution<L: satcoder::Lit>(
    problem: &Problem,
    occupations: &TiVec<VisitId, Occ<L>>,
) -> Vec<Vec<i32>> {
    let _p = hprof::enter("extract solution");
    let mut trains = Vec::new();
    let mut i = 0;
    for (train_idx, train) in problem.trains.iter().enumerate() {
        let mut train_times = Vec::new();
        for _ in train.visits.iter().enumerate() {
            train_times.push(occupations[VisitId(i)].incumbent_time());
            i += 1;
        }

        let visit = problem.trains[train_idx].visits[train_times.len() - 1];
        let last_t = train_times[train_times.len() - 1] + visit.travel_time;
        train_times.push(last_t);

        trains.push(train_times);
    }
    trains
}

fn inject_solution_timepoints_maxsat<L: satcoder::Lit>(
    solver: &mut impl SatInstance<L>,
    problem: &Problem,
    visits: &TiVec<VisitId, (usize, usize)>,
    occupations: &mut TiVec<VisitId, Occ<L>>,
    new_time_points: &mut Vec<(VisitId, Bool<L>, i32)>,
    fixed_prec_rows: &mut HashSet<(VisitId, i32)>,
    use_eager_chain_expansion: bool,
    sol: &[Vec<i32>],
) {
    let mut flat_visit = 0usize;
    for (train_idx, train) in problem.trains.iter().enumerate() {
        for visit_idx in 0..train.visits.len() {
            let visit_id = VisitId(flat_visit as u32);
            flat_visit += 1;
            let time = sol[train_idx][visit_idx];
            let (lit, is_new) = occupations[visit_id].time_point(solver, time);
            if is_new {
                new_time_points.push((visit_id, lit, time));
            }
            if visit_idx + 1 < train.visits.len() {
                let _ = add_fixed_precedence_row(
                    solver,
                    problem,
                    visits,
                    occupations,
                    new_time_points,
                    fixed_prec_rows,
                    visit_id,
                    lit,
                    time,
                    use_eager_chain_expansion,
                );
            }
        }
    }
}

#[cfg(test)]
mod binary_objective_tests {
    use super::*;
    use satcoder::{SatResult, SatSolver};

    #[test]
    fn comparator_and_subtraction_match_exhaustive_truth_tables() {
        for a in 0..16 {
            for b in 0..16 {
                let mut solver = satcoder::solvers::minisat::Solver::new();
                let (diff, borrow) = subtract_binary(&mut solver, &Binary::constant(a), &Binary::constant(b));
                let bits = diff.into_list();
                let width = bits.len();
                match SatSolver::solve(&mut solver) {
                    SatResult::Sat(model) => {
                        assert_eq!(model.value(&borrow), a < b);
                        let value = bits.iter().enumerate().fold(0, |acc, (i, bit)| acc | ((model.value(bit) as usize) << i));
                        assert_eq!(value, a.wrapping_sub(b) & ((1 << width) - 1));
                    }
                    _ => panic!("arithmetic encoding must be satisfiable"),
                };
                let mut solver = satcoder::solvers::minisat::Solver::new();
                assert_binary_le(&mut solver, &Binary::constant(a), &Binary::constant(b));
                assert_eq!(matches!(SatSolver::solve(&mut solver), SatResult::Sat(_)), a <= b);
            }
        }
    }

    #[test]
    fn incremental_weighted_bound_handles_zero_large_terms_and_tightening() {
        for initial_upper in [0, 1, 3, 7, 10, 16] {
            let mut solver = satcoder::solvers::minisat::Solver::new();
            let literals = (0..3).map(|_| SatInstance::new_var(&mut solver)).collect::<Vec<_>>();
            let weights = [1, 3, 17];
            let mut objective = BinaryObjective::new(&mut solver, initial_upper);
            for i in 0..3 {
                objective.add_term(&mut solver, literals[i], weights[i]);
                for mask in 0..8 {
                    let cost = (0..=i).filter(|j| mask & (1 << j) != 0).map(|j| weights[j]).sum::<usize>();
                    let result = SatSolverWithCore::solve_with_assumptions(&mut solver,
                        literals.iter().enumerate().map(|(j, lit)| if mask & (1 << j) != 0 { *lit } else { !*lit }));
                    assert_eq!(matches!(result, satcoder::SatResultWithCore::Sat(_)), cost <= initial_upper);
                }
            }
            for upper in (0..initial_upper).rev() {
                assert!(objective.tighten(&mut solver, upper));
                for mask in 0..8 {
                    let cost = (0..3).filter(|j| mask & (1 << j) != 0).map(|j| weights[j]).sum::<usize>();
                    let result = SatSolverWithCore::solve_with_assumptions(&mut solver,
                        literals.iter().enumerate().map(|(j, lit)| if mask & (1 << j) != 0 { *lit } else { !*lit }));
                    assert_eq!(matches!(result, satcoder::SatResultWithCore::Sat(_)), cost <= upper);
                }
            }
        }
    }

    #[test]
    fn bound_preserves_cost_tree_choices_when_thresholds_arrive_out_of_order() {
        let costs = [7, 3, 11, 5, 7];
        for upper in 0..=12 {
            let mut solver = satcoder::solvers::minisat::Solver::new();
            let mut objective = BinaryObjective::new(&mut solver, upper);
            let mut tree = CostTree::new();
            let mut inputs = Vec::new();
            for &cost in &costs {
                let input = SatInstance::new_var(&mut solver);
                inputs.push(input);
                let mut terms = Vec::new();
                tree.add_cost(&mut solver, input, cost, &mut |weight, lit| terms.push((lit, weight)));
                for (literal, weight) in terms {
                    objective.add_term(&mut solver, literal, weight);
                }
            }
            for mask in 0..(1 << costs.len()) {
                let required = costs.iter().enumerate().filter(|(i, _)| mask & (1 << i) != 0).map(|(_, c)| *c).max().unwrap_or(0);
                let result = SatSolverWithCore::solve_with_assumptions(&mut solver,
                    inputs.iter().enumerate().map(|(i, lit)| if mask & (1 << i) != 0 { *lit } else { !*lit }));
                assert_eq!(matches!(result, satcoder::SatResultWithCore::Sat(_)), required <= upper,
                           "upper={upper}, mask={mask}, required={required}");
            }
        }
    }

    #[test]
    fn sparse_cost_tree_matches_all_threshold_subsets_and_bounds() {
        // Costs arrive out of order, include a duplicate and several gaps
        // that the legacy tree would expand into unit-cost nodes.
        let costs = [7, 3, 11, 5, 7];
        for upper in 0..=12 {
            let mut solver = satcoder::solvers::minisat::Solver::new();
            let mut objective = BinaryObjective::new(&mut solver, upper);
            let mut tree = CostTree::new_sparse();
            let mut inputs = Vec::new();
            for &cost in &costs {
                let input = SatInstance::new_var(&mut solver);
                inputs.push(input);
                let mut terms = Vec::new();
                tree.add_cost(&mut solver, input, cost, &mut |weight, lit| terms.push((lit, weight)));
                for (literal, weight) in terms {
                    objective.add_term(&mut solver, literal, weight);
                }
            }
            for mask in 0..(1 << costs.len()) {
                let required = costs.iter().enumerate()
                    .filter(|(i, _)| mask & (1 << i) != 0)
                    .map(|(_, cost)| *cost).max().unwrap_or(0);
                let result = SatSolverWithCore::solve_with_assumptions(&mut solver,
                    inputs.iter().enumerate().map(|(i, literal)|
                        if mask & (1 << i) != 0 { *literal } else { !*literal }));
                assert_eq!(matches!(result, satcoder::SatResultWithCore::Sat(_)), required <= upper,
                           "sparse upper={upper}, mask={mask}, required={required}");
            }
        }
    }
}

#[cfg(test)]
mod aglr_end_to_end_tests {
    use super::*;
    use crate::problem::{Problem, Train, Visit};
    use crate::solvers::ddd::maxsat_ladder_sc::AglrSettings;
    use grb::parameter::IntParam::OutputFlag;

    fn two_train_problem() -> Problem {
        let visit = || Visit {
            resource_id: 0,
            earliest: 0,
            aimed: Some(0),
            travel_time: 2,
        };
        Problem {
            name: "two-train-exhaustive".to_string(),
            trains: vec![
                Train {
                    visits: vec![visit()],
                },
                Train {
                    visits: vec![visit()],
                },
            ],
            conflicts: vec![(0, 0)],
        }
    }

    fn exhaustive_optimum(problem: &Problem) -> i32 {
        (0..=4)
            .flat_map(|first| (0..=4).map(move |second| (first, second)))
            .filter_map(|(first, second)| {
                let solution = vec![vec![first, first + 2], vec![second, second + 2]];
                problem.verify_solution(&solution, DelayCostType::Continuous)
            })
            .min()
            .unwrap()
    }

    fn quiet_env() -> grb::Env {
        let mut env = grb::Env::new("").unwrap();
        env.set(OutputFlag, 0).unwrap();
        env
    }

    fn solve_cost(problem: &Problem, policy: RefinementPolicy) -> i32 {
        solve_cost_with_bound(problem, policy, false)
    }

    fn solve_cost_with_bound(problem: &Problem, policy: RefinementPolicy, use_bound: bool) -> i32 {
        let mut settings = MaxSatDddLadderScSettings::default();
        settings.aglr = AglrSettings {
            policy,
            min_growth: 1,
            fraction: 0.5,
            max_wait: 2,
            use_objective_bound: use_bound,
            ..AglrSettings::default()
        };
        let solution = solve_with_settings(
            &quiet_env,
            satcoder::solvers::minisat::Solver::new(),
            problem,
            30.0,
            DelayCostType::Continuous,
            settings,
            |_, _| {},
        )
        .unwrap()
        .0;
        problem
            .verify_solution(&solution, DelayCostType::Continuous)
            .unwrap()
    }

    #[test]
    fn legacy_and_aglr_match_exhaustive_optimum_on_tiny_problem() {
        let problem = two_train_problem();
        let optimum = exhaustive_optimum(&problem);
        assert_eq!(solve_cost(&problem, RefinementPolicy::Legacy), optimum);
        assert_eq!(solve_cost(&problem, RefinementPolicy::Adaptive), optimum);
        assert_eq!(solve_cost_with_bound(&problem, RefinementPolicy::Adaptive, true), optimum);
    }

    #[test]
    fn transitive_resource_orders_match_exhaustive_three_train_optimum() {
        let problem = Problem {
            name: "three-train-orders".to_string(),
            trains: (0..3).map(|_| Train { visits: vec![
                Visit { resource_id: 0, earliest: 0, aimed: Some(0), travel_time: 2 },
            ] }).collect(),
            conflicts: vec![(0, 0)],
        };
        for objective in [DelayCostType::Continuous, DelayCostType::FiniteSteps123,
                          DelayCostType::InfiniteSteps180] {
            let mut optimum = i32::MAX;
            // An optimum is contained in [0, 6]: order three length-2 visits
            // at 0,2,4, and moving any of them later cannot reduce its cost.
            for a in 0..=6 {
                for b in 0..=6 {
                    for c in 0..=6 {
                        if let Some(cost) = problem.verify_solution(
                            &vec![vec![a, a + 2], vec![b, b + 2], vec![c, c + 2]], objective,
                        ) {
                            optimum = optimum.min(cost);
                        }
                    }
                }
            }
            assert_ne!(optimum, i32::MAX);
            for transitivity in [false, true] {
                for sparse in [false, true] {
                  for use_bound in [false, true] {
                    let mut settings = MaxSatDddLadderScSettings::default();
                    settings.resource_orders = true;
                    settings.order_transitivity = transitivity;
                    settings.sparse_costs = sparse;
                    settings.use_objective_bound = use_bound;
                    let mut telemetry = BTreeMap::new();
                    let (solution, _) = solve_with_settings(
                        &quiet_env, satcoder::solvers::minisat::Solver::new(),
                        &problem, 30.0, objective, settings, |key, value| {
                            telemetry.insert(key, value);
                        },
                    ).unwrap();
                    assert_eq!(problem.verify_solution(&solution, objective), Some(optimum));
                    if use_bound {
                        assert!(telemetry["maxsat_objective_bound"].as_bool().unwrap());
                        assert!(telemetry["maxsat_objective_bound_terms"].as_u64().unwrap() > 0);
                    }
                  }
                }
            }
            for use_bound in [false, true] {
                let mut settings = MaxSatDddLadderScSettings::default();
                settings.resource_orders = true;
                settings.order_transitivity = true;
                settings.use_objective_bound = use_bound;
                let (solution, _) = solve_with_settings(
                    &quiet_env,
                    crate::solvers::ddd::incremental_sat::new_maxsat_glucose_solver(),
                    &problem, 30.0, objective, settings, |_, _| {},
                ).unwrap();
                assert_eq!(problem.verify_solution(&solution, objective), Some(optimum));
            }
        }
    }

    #[test]
    fn assumption_strategies_match_enumeration_with_travel_and_resource_conflicts() {
        use super::super::settings::AssumptionStrategy;
        let visits = vec![
            Visit { resource_id: 0, earliest: 0, aimed: Some(0), travel_time: 2 },
            Visit { resource_id: 1, earliest: 2, aimed: Some(2), travel_time: 2 },
        ];
        let problem = Problem {
            name: "assumptions-exhaustive".to_string(),
            trains: vec![Train { visits: visits.clone() }, Train { visits }],
            conflicts: vec![(0, 0), (1, 1)],
        };
        for objective in [DelayCostType::Continuous, DelayCostType::FiniteSteps123,
                          DelayCostType::InfiniteSteps180] {
            // Enumerate all feasible integer schedules in [0, 8]. A schedule
            // of cost 4 (continuous), or 2 (step objectives), is attainable
            // here, so a later start outside this interval cannot improve it.
            let mut optimum = i32::MAX;
            for a in 0..=8 {
                for b in (a + 2)..=8 {
                    for c in 0..=8 {
                        for d in (c + 2)..=8 {
                            if !(b <= c || d <= a) || !(b + 2 <= d || d + 2 <= b) {
                                continue;
                            }
                            let solution = vec![vec![a, b, b + 2], vec![c, d, d + 2]];
                            if let Some(cost) = problem.verify_solution(&solution, objective) {
                                optimum = optimum.min(cost);
                            }
                        }
                    }
                }
            }
            assert_ne!(optimum, i32::MAX);
            for policy in [RefinementPolicy::Legacy, RefinementPolicy::Adaptive] {
                for strategy in [AssumptionStrategy::Legacy, AssumptionStrategy::Full,
                                 AssumptionStrategy::Geometric] {
                  for sparse_costs in [false, true] {
                   for resource_orders in [false, true] {
                    if resource_orders && policy != RefinementPolicy::Legacy { continue; }
                    let mut settings = MaxSatDddLadderScSettings::default();
                    settings.assumption_strategy = strategy;
                    settings.sparse_costs = sparse_costs;
                    settings.resource_orders = resource_orders;
                    settings.aglr.policy = policy;
                    let (solution, stats) = solve_with_settings(
                        &quiet_env, satcoder::solvers::minisat::Solver::new(), &problem,
                        30.0, objective, settings, |_, _| {},
                    ).unwrap();
                    assert_eq!(problem.verify_solution(&solution, objective), Some(optimum));
                    if resource_orders {
                        assert!(stats.resource_order_pairs > 0);
                        assert!(stats.resource_order_rows > 0);
                    }
                   }
                  }
                }
            }
        }
    }
}

#[derive(Debug)]
pub(super) struct Occ<L: satcoder::Lit> {
    pub(super) cost: Vec<Bool<L>>,
    pub(super) cost_tree: CostTree<L>,
    pub(super) delays: Vec<(Bool<L>, i32)>,
    pub(super) incumbent_idx: usize,
}

impl<L: satcoder::Lit> Occ<L> {
    pub fn incumbent_time(&self) -> i32 {
        self.delays[self.incumbent_idx].1
    }

    pub fn time_point(&mut self, solver: &mut impl SatInstance<L>, t: i32) -> (Bool<L>, bool) {
        let idx = self.delays.partition_point(|(_, t0)| *t0 < t);

        assert!(idx > 0 || t == self.delays[0].1); // cannot insert before the earliest time.
        assert!(idx < self.delays.len()); // cannot insert after infinity.

        assert!(idx == 0 || self.delays[idx - 1].1 < t);
        assert!(self.delays[idx].1 >= t);

        if self.delays[idx].1 == t || (idx > 0 && self.delays[idx - 1].1 == t) {
            return (self.delays[idx].0, false);
        }

        let var = solver.new_var();
        self.delays.insert(idx, (var, t));

        // Keep `incumbent_idx` pointing to the same logical timepoint after
        // insertion. If we inserted at or before the incumbent's array slot,
        // the old incumbent shifted forward by one — compensate so callers
        // reading `incumbent_time()` or `delays[incumbent_idx]` still see
        // the same data they had before this call. Without this, an insertion
        // before the incumbent leaves `delays[incumbent_idx]` pointing to the
        // newly-inserted (wrong) timepoint, causing travel-time violations.
        if idx <= self.incumbent_idx {
            self.incumbent_idx += 1;
        }

        if idx > 0 {
            solver.add_clause(vec![!var, self.delays[idx - 1].0]);
        }

        if idx < self.delays.len() {
            solver.add_clause(vec![!self.delays[idx + 1].0, var]);
        }

        (var, true)
    }
}
