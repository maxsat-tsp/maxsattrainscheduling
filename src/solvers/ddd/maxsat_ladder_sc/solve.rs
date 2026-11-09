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
    pub order_cycle_checks: usize,
    pub order_cycles_blocked: usize,
    pub order_cycle_time: Duration,
    pub order_path_checks: usize,
    pub order_paths_added: usize,
    pub order_path_new_points: usize,
    pub order_path_guards: usize,
    pub order_path_time: Duration,
    pub order_master_models: usize,
    pub order_master_schedules: usize,
    pub order_master_max_batch: usize,
    pub order_master_seed_clauses: usize,
    pub order_master_seed_points: usize,
    pub core_literals: usize,
    pub max_core_size: usize,
    pub unit_weight_cores: usize,
    pub core_minimize_calls: usize,
    pub core_minimize_removed: usize,
    pub core_minimize_weight_increases: usize,
    pub core_minimize_inconclusive: usize,
    pub core_minimize_time: Duration,
    pub core_trim_calls: usize,
    pub core_trim_removed: usize,
    pub core_trim_weight_increases: usize,
    pub core_trim_inconclusive: usize,
    pub core_trim_time: Duration,
    pub am1_calls: usize,
    pub am1_groups: usize,
    pub am1_literals: usize,
    pub am1_inconclusive: usize,
    pub am1_fixed_cost: usize,
    pub am1_time: Duration,
    pub core_exhaust_calls: usize,
    pub core_exhaust_steps: usize,
    pub core_exhaust_inconclusive: usize,
    pub core_exhaust_time: Duration,
    pub hardening_scans: usize,
    pub hardened_primary: usize,
    pub hardened_totalizer: usize,
    pub hardening_time: Duration,
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

fn apply_residual_hardening<L: satcoder::Lit>(
    solver: &mut impl SatInstance<L>,
    soft: &mut HashMap<Bool<L>, (Soft<L>, usize, usize)>,
    lower: i32,
    upper: i32,
    stats: &mut SolveStats,
) -> Result<(), SolverError> {
    let started = Instant::now();
    stats.hardening_scans += 1;
    let fixed = super::hardening::select(
        soft.iter().map(|(literal, (_, residual, _))| (*literal, *residual)), lower, upper,
    ).map_err(SolverError::InvalidSolution)?;
    for literal in fixed {
        solver.add_clause(vec![literal]);
        let (kind, _, _) = soft.remove(&literal).expect("selected residual preference is present");
        match kind {
            Soft::Primary => stats.hardened_primary += 1,
            Soft::Totalizer(_, _) => stats.hardened_totalizer += 1,
        }
    }
    stats.hardening_time += started.elapsed();
    Ok(())
}

fn bits_needed(max_value: usize) -> usize {
    if max_value == 0 {
        1
    } else {
        (usize::BITS as usize) - (max_value.leading_zeros() as usize)
    }
}

/// Adapt only residual Primary preferences. Totalizer preferences are left to
/// RC2's existing bound/weight restoration path. No pair is assumed exclusive
/// from a schedule or resource label: every added edge is proved by SAT.
#[allow(clippy::too_many_arguments)]
fn adapt_intrinsic_am1<L: satcoder::Lit + Copy + 'static>(
    solver: &mut (impl SatInstance<L> + SatSolverWithCore<Lit=L>),
    soft: &mut HashMap<Bool<L>, (Soft<L>, usize, usize)>,
    core: &[Bool<L>],
    settings: MaxSatDddLadderScSettings,
    total_cost: &mut i32,
    stats: &mut SolveStats,
    solver_time: &mut Duration,
    started: Instant,
    timeout: f64,
) -> Result<bool,SolverError> {
    if core.len()!=2 || core.iter().any(|lit|!matches!(soft.get(lit),Some((Soft::Primary,_,_)))) {
        return Ok(false);
    }
    let begin=Instant::now();
    let mut candidates=soft.iter().filter_map(|(&lit,(kind,weight,_))|
        (matches!(kind,Soft::Primary) && matches!(lit,Bool::Lit(_))).then_some((lit,*weight)))
        .collect::<Vec<_>>();
    candidates.sort_unstable_by(|a,b|b.1.cmp(&a.1).then_with(||a.0.cmp(&b.0)));
    let clique=super::intrinsic_am1::grow([core[0],core[1]],
        candidates.into_iter().map(|(lit,_)|lit).collect(),settings.am1_checks,
        |left,right| {
            let query_start=Instant::now();stats.sat_calls+=1;
            let result=match std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                crate::solvers::util::minisat_deadline::with_core_check_limit(settings.core_minimize_conflicts,|| {
                    match solver.solve_with_assumptions([left,right]) {
                        satcoder::SatResultWithCore::Sat(_)=>Ok(false),
                        satcoder::SatResultWithCore::Unsat(proof)=> {
                            if proof.is_empty() {Err("hard model is UNSAT during AM1 detection".to_string())}
                            else {Ok(true)}
                        },
                    }
                })
            })) {
                Ok(result)=>result,
                Err(payload) if payload.is::<crate::solvers::util::minisat_deadline::CoreCheckInconclusive>()=>{
                    stats.am1_inconclusive+=1;Ok(false)
                },
                Err(payload)=>std::panic::resume_unwind(payload),
            };
            *solver_time+=query_start.elapsed();result
        },||started.elapsed().as_secs_f64()>=timeout,
    ).map_err(SolverError::InvalidSolution)?;
    stats.am1_calls+=clique.checks;
    if clique.literals.len()<3 {stats.am1_time+=begin.elapsed();return Ok(false);}
    let weights=clique.literals.iter().map(|lit|soft[lit].1).collect::<Vec<_>>();
    let (fixed,minimum,residual)=super::intrinsic_am1::reweight(&weights)
        .map_err(SolverError::InvalidSolution)?;
    // Keep ordinary RC2 if a low-weight extension would charge no more
    // than the already proved seed core. Its normal processing stays valid.
    if fixed<=soft[&core[0]].1.min(soft[&core[1]].1) {
        stats.am1_time+=begin.elapsed();return Ok(false);
    }
    let next_cost=i32::try_from(fixed).ok().and_then(|v|total_cost.checked_add(v))
        .ok_or_else(||SolverError::InvalidSolution("AM1 lower-bound overflow".into()))?;
    let combined=solver.or_literal(clique.literals.iter().copied());
    for (&lit,&weight) in clique.literals.iter().zip(&residual) {
        if weight==0 {soft.remove(&lit);} else {soft.get_mut(&lit).unwrap().1=weight;}
    }
    if combined!=true.into() {soft.insert(combined,(Soft::Primary,minimum,minimum));}
    *total_cost=next_cost;
    stats.am1_groups+=1;stats.am1_literals+=clique.literals.len();stats.am1_fixed_cost+=fixed;
    stats.am1_time+=begin.elapsed();
    Ok(true)
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

    /// A diagnostic asks about one fixed threshold. Pin the initial budget
    /// to that value instead of making SAT search an unnecessary B <= UB.
    /// Unspent budget remains allowed: this still encodes sum(costs) <= UB.
    fn fix_budget(&self, solver: &mut impl SatInstance<L>) {
        for (index, bit) in self.reg_bits.iter().enumerate() {
            solver.add_clause([if self.upper_bound & (1usize << index) != 0 { *bit } else { !*bit }]);
        }
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
    solver: impl SatInstance<L> + SatSolverWithCore<Lit = L> + std::fmt::Debug,
    problem: &Problem,
    timeout: f64,
    delay_cost_type: DelayCostType,
    settings: MaxSatDddLadderScSettings,
    debug_out: impl Fn(DebugInfo),
    output_stats: impl FnMut(String, serde_json::Value),
) -> Result<(Vec<Vec<i32>>, SolveStats), SolverError> {
    solve_inner(mk_env, solver, problem, timeout, delay_cost_type, settings, None,
        debug_out, output_stats)
}

/// Separate diagnostic entry point. Oracle-assisted results must never enter
/// coverage tables. A fixed threshold is a SAT decision, not an RC2 lower bound.
pub enum BoundDiagnostic<'a> {
    Control,
    VerifiedUpper(&'a [Vec<i32>]),
    Decision(i32),
}

pub fn solve_bound_diagnostic<L: satcoder::Lit + Copy + std::fmt::Debug + 'static>(
    mk_env: impl Fn() -> grb::Env + Send + 'static,
    solver: impl SatInstance<L> + SatSolverWithCore<Lit = L> + std::fmt::Debug,
    problem: &Problem,
    timeout: f64,
    delay_cost_type: DelayCostType,
    settings: MaxSatDddLadderScSettings,
    diagnostic: BoundDiagnostic<'_>,
    output_stats: impl FnMut(String, serde_json::Value),
) -> Result<(Vec<Vec<i32>>, SolveStats), SolverError> {
    solve_inner(mk_env, solver, problem, timeout, delay_cost_type, settings,
        Some(&diagnostic), |_| {}, output_stats)
}

/// Solve a cost decision chosen by an optimizer, without any optimum oracle.
/// Reuse the tested fixed-budget DDD path and give its events neutral names.
pub fn solve_cost_threshold<L: satcoder::Lit + Copy + std::fmt::Debug + 'static>(
    solver: impl SatInstance<L> + SatSolverWithCore<Lit = L> + std::fmt::Debug,
    problem: &Problem,
    timeout: f64,
    delay_cost_type: DelayCostType,
    settings: MaxSatDddLadderScSettings,
    target: i32,
    mut output_stats: impl FnMut(String, serde_json::Value),
) -> Result<(Vec<Vec<i32>>, SolveStats), SolverError> {
    solve_inner(|| panic!("a threshold decision never starts a MIP heuristic"),
        solver, problem, timeout, delay_cost_type, settings,
        Some(&BoundDiagnostic::Decision(target)), |_| {}, |key,value| {
            if key=="diagnostic_only" || key=="diagnostic_supplied_ub" {return;}
            let key=key.strip_prefix("diagnostic_")
                .map(|suffix|format!("threshold_{suffix}")).unwrap_or(key);
            output_stats(key,value);
        })
}

fn solve_inner<L: satcoder::Lit + Copy + std::fmt::Debug + 'static>(
    mk_env: impl Fn() -> grb::Env + Send + 'static,
    mut solver: impl SatInstance<L> + SatSolverWithCore<Lit = L> + std::fmt::Debug,
    problem: &Problem,
    timeout: f64,
    delay_cost_type: DelayCostType,
    settings: MaxSatDddLadderScSettings,
    diagnostic: Option<&BoundDiagnostic<'_>>,
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

    let fixed_target = match diagnostic {
        Some(BoundDiagnostic::Decision(target)) if *target >= 0 => Some(*target),
        Some(BoundDiagnostic::Decision(_)) => return Err(SolverError::InvalidSolution(
            "diagnostic threshold must be nonnegative".into())),
        _ => None,
    };
    let oracle_upper = match diagnostic {
        Some(BoundDiagnostic::VerifiedUpper(solution)) => {
            if solution.len() != problem.trains.len() || solution.iter().zip(&problem.trains)
                .any(|(times, train)| times.len() != train.visits.len() + 1) {
                return Err(SolverError::InvalidSolution("diagnostic incumbent has wrong dimensions".into()));
            }
            let cost = problem.verify_solution(solution, delay_cost_type).ok_or_else(||
                SolverError::InvalidSolution("diagnostic incumbent is not feasible".into()))?;
            Some((cost, solution.to_vec()))
        }
        _ => None,
    };
    if diagnostic.is_some() {
        if settings.order_master || settings.extract_initial_cost || settings.residual_hardening {
            return Err(SolverError::InvalidSolution(
                "bound diagnostics require ordinary DDD, no initial cost offset or residual hardening".into()));
        }
        output_stats("diagnostic_only".into(), true.into());
        output_stats("diagnostic_target".into(), fixed_target.into());
        output_stats("diagnostic_supplied_ub".into(), oracle_upper.as_ref().map(|x|x.0).into());
    }

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
    assert!((settings.core_trim_checks == 0 && settings.am1_checks == 0) || settings.core_minimize_conflicts > 0,
            "bounded core adaptation requires a positive conflict budget");
    assert!(!settings.resource_orders || settings.aglr.policy == RefinementPolicy::Legacy,
            "resource-order experiments currently require legacy refinement");
    assert!(!settings.order_transitivity || settings.resource_orders,
            "order transitivity requires resource-order decisions");
    assert!(!settings.order_cycle_cuts || settings.resource_orders,
            "temporal cycle cuts require resource-order decisions");
    assert!(!settings.order_path_cuts || settings.resource_orders,
            "temporal path cuts require resource-order decisions");
    assert!(!settings.order_master || (settings.resource_orders && settings.aglr.policy==RefinementPolicy::Legacy
        && !settings.seed_sc_from_earliest && !settings.prealloc_cost_thresholds),
        "order master requires resource orders, legacy policy and no seeded time-point expansion");
    assert!(!settings.order_master_cost_levels || settings.order_master,"canonical master cost levels require order master mode");
    assert!(!settings.order_master_batch_cuts || settings.order_master,"batched objective paths require order master mode");
    assert!(!settings.order_master_seed_costs || settings.order_master,"initial order costs require order master mode");
    let use_objective_bound = fixed_target.is_some() || settings.use_objective_bound
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
    output_stats("maxsat_order_cycle_cuts".to_string(), settings.order_cycle_cuts.into());
    output_stats("maxsat_order_path_cuts".to_string(), settings.order_path_cuts.into());
    output_stats("maxsat_order_master".to_string(),settings.order_master.into());
    output_stats("maxsat_order_master_cost_levels".to_string(),settings.order_master_cost_levels.into());
    output_stats("maxsat_order_master_batch_cuts".to_string(),settings.order_master_batch_cuts.into());
    output_stats("maxsat_order_master_seed_costs".to_string(),settings.order_master_seed_costs.into());
    output_stats("maxsat_extract_initial_cost".to_string(), settings.extract_initial_cost.into());
    output_stats("maxsat_objective_bound".to_string(), use_objective_bound.into());
    output_stats("maxsat_residual_hardening".to_string(), settings.residual_hardening.into());
    output_stats("maxsat_core_minimize_checks".to_string(), settings.core_minimize_checks.into());
    output_stats("maxsat_core_minimize_conflicts".to_string(), settings.core_minimize_conflicts.into());
    output_stats("maxsat_core_trim_checks".to_string(), settings.core_trim_checks.into());
    output_stats("maxsat_am1_checks".to_string(), settings.am1_checks.into());
    output_stats("maxsat_core_exhaust_checks".to_string(), settings.core_exhaust_checks.into());

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
    let mut is_sat = !settings.order_master && fixed_target.is_none();

    // Every feasible entry is >= its propagated earliest time. Separate that
    // unavoidable constant from all future CostTree increments, exactly once.
    // An empty vector preserves the published encoding when the flag is off.
    let initial_costs=if settings.extract_initial_cost {
        visits.iter_enumerated().map(|(id,&(train,index))|
            problem.trains[train].visit_delay_cost(delay_cost_type,index,occupations[id].delays[0].1)
        ).collect::<Vec<_>>()
    } else {Vec::new()};
    let initial_cost_offset=i32::try_from(initial_costs.iter().try_fold(0usize,|sum,&cost|sum.checked_add(cost))
        .ok_or_else(||SolverError::InvalidSolution("initial objective cost overflow".into()))?)
        .map_err(|_|SolverError::InvalidSolution("initial objective cost exceeds i32".into()))?;
    output_stats("maxsat_initial_cost_offset".to_string(),initial_cost_offset.into());
    let mut total_cost = initial_cost_offset;
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
    if settings.order_master {
        // One bit per cross-train conflicting pair, including pairs not yet
        // encountered by a time-point DDD model. No time-indexed overlap rows.
        let mut pairs=std::collections::BTreeSet::new();
        for first in visits.keys(){
            let (train,index)=visits[first];let resource=problem.trains[train].visits[index].resource_id;
            if let Some(others)=conflicts.get(&resource){for &other_resource in others{
                if let Some(candidates)=resource_visits.get(other_resource){for &second in candidates{
                    if first.0<second.0 && visits[second].0!=train{pairs.insert((first.0,second.0));}
                }}
            }}
        }
        for (a,b) in pairs{if resource_orders.ensure_pair(&mut solver,a,b){stats.resource_order_pairs+=1;}}
    }
    let order_topology=(settings.order_cycle_cuts && !settings.order_path_cuts && !settings.order_master).then(|| {
        let mut next=Vec::with_capacity(visits.len());let mut positive=Vec::with_capacity(visits.len());
        for (id,&(train,index)) in visits.iter_enumerated() {
            let route=&problem.trains[train].visits;
            assert!(route[index].travel_time>=0,"temporal cycle cuts require nonnegative travel times");
            next.push((index+1<route.len()).then_some(usize::from(id)+1));
            positive.push(route[index].travel_time>0);
        }
        super::order_cycles::Topology{next,positive}
    });
    let path_topology=(settings.order_path_cuts || settings.order_master).then(||{
        let mut next=Vec::with_capacity(visits.len());let mut travel=Vec::with_capacity(visits.len());
        let mut earliest=Vec::with_capacity(visits.len());
        for (id,&(train,index)) in visits.iter_enumerated(){
            let route=&problem.trains[train].visits;
            assert!(route[index].travel_time>=0,"temporal paths require nonnegative travel times");
            next.push((index+1<route.len()).then_some(usize::from(id)+1));
            travel.push(route[index].travel_time);earliest.push(occupations[id].delays[0].1);
        }
        super::order_paths::Topology{next,travel,earliest}
    });

    if settings.order_master_seed_costs {
        let cuts=resource_orders.seed_paths(path_topology.as_ref().unwrap(),|v,bound,base|{
            let (train,index)=visits[VisitId::from(v)];
            problem.trains[train].visit_delay_cost(delay_cost_type,index,bound)
                >problem.trains[train].visit_delay_cost(delay_cost_type,index,base)
        }).map_err(SolverError::InvalidSolution)?;
        for mut cut in cuts {
            if let super::order_paths::Cut::Path{visit,time,..}=&mut cut {
                let (train,index)=visits[VisitId::from(*visit)];
                if settings.order_master_cost_levels {
                    *time=super::order_paths::cost_threshold(occupations[VisitId::from(*visit)].delays[0].1,*time,
                        |t|problem.trains[train].visit_delay_cost(delay_cost_type,index,t))
                        .map_err(SolverError::InvalidSolution)?;
                }
            }
            resource_orders.remember(&cut).map_err(SolverError::InvalidSolution)?;
            if let super::order_paths::Cut::Path{visit,time,mut prefix}=cut {
                let visit=VisitId::from(visit);
                let (literal,is_new)=occupations[visit].time_point(&mut solver,time);
                if is_new{new_time_points.push((visit,literal,time));stats.order_master_seed_points+=1;}
                prefix.push(literal);solver.add_clause(prefix);stats.order_master_seed_clauses+=1;
            }
        }
    }

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

    if let Some(incumbent) = oracle_upper {
        // Supply only a verified upper bound. Never assign RC2's lower bound
        // from an oracle, and do not inject oracle time points into the model.
        best_heur = Some(incumbent);
    }

    let heuristic_filter = std::sync::Arc::new(heuristic::HeuristicFilter::new(
        best_heur
            .as_ref()
            .map(|(cost, _)| *cost)
            .unwrap_or(i32::MAX),
    ));

    //UB from Gurobi
    let heur_thread = (USE_HEURISTIC && !settings.order_master
        && !matches!(diagnostic, Some(BoundDiagnostic::VerifiedUpper(_) | BoundDiagnostic::Decision(_)))).then(|| {
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
        let upper = if let Some(target) = fixed_target { target } else { best_heur.as_ref().ok_or_else(|| SolverError::InvalidSolution(
            "objective bound requires a verified initial feasible schedule".to_string()
        ))?.0 };
        let residual_upper=upper.checked_sub(initial_cost_offset).filter(|v|*v>=0)
            .ok_or_else(||SolverError::InvalidSolution("verified upper bound is below initial cost".into()))?;
        let objective = BinaryObjective::new(&mut solver, residual_upper.try_into().map_err(|_| {
            SolverError::InvalidSolution("negative objective upper bound".to_string())
        })?);
        if fixed_target.is_some() { objective.fix_budget(&mut solver); }
        Some(objective)
    } else {
        None
    };
    let mut last_progress_iteration = 0usize;
    let mut last_heuristic_submission_iteration = None;

    // Main DDD loop.
    loop {
        if diagnostic.is_some() {
            output_stats("diagnostic_lb".into(), total_cost.into());
            output_stats("diagnostic_ub".into(), best_heur.as_ref().map(|x|x.0).into());
            output_stats("diagnostic_iterations".into(), iteration.into());
            output_stats("diagnostic_checkpoint".into(), start_time.elapsed().as_secs_f64().into());
        }
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

        if settings.order_master{
            if let Some((upper,solution))=&best_heur{
                if *upper<total_cost{return Err(SolverError::InvalidSolution("order master LB exceeds verified schedule cost".into()));}
                if *upper==total_cost{
                    do_output_stats(&mut output_stats,iteration,&iteration_types,&stats,&occupations,
                        start_time,solver_time,total_cost,*upper,&aglr_telemetry,&heuristic_filter);
                    return Ok((solution.clone(),stats));
                }
            }
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
                        if settings.aglr.policy != RefinementPolicy::Legacy || use_objective_bound || settings.residual_hardening || settings.core_minimize_checks > 0 {
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

                if let Some(target) = fixed_target {
                    let cost = problem.verify_solution(&trains, delay_cost_type)
                        .filter(|cost| *cost <= target)
                        .ok_or_else(|| SolverError::InvalidSolution(
                            "fixed-bound SAT model failed full schedule/cost validation".into()))?;
                    do_output_stats(&mut output_stats, iteration, &iteration_types, &stats,
                        &occupations, start_time, solver_time, initial_cost_offset, cost,
                        &aglr_telemetry, &heuristic_filter);
                    output_stats("diagnostic_outcome".into(), "sat".into());
                    return Ok((trains, stats));
                }

                if settings.aglr.policy != RefinementPolicy::Legacy || settings.resource_orders || use_objective_bound || settings.residual_hardening || settings.core_minimize_checks > 0 || settings.extract_initial_cost {
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
                problem.trains[train_idx].visit_delay_cost(delay_cost_type, visit_idx, new_t)
                    .saturating_sub(initial_costs.get(usize::from(visit)).copied().unwrap_or(0));

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
            if let Some((upper, _)) = best_heur.as_ref().filter(|_| fixed_target.is_none()) {
                let residual_upper=upper.checked_sub(initial_cost_offset).filter(|v|*v>=0)
                    .ok_or_else(||SolverError::InvalidSolution("verified upper bound is below initial cost".into()))?;
                if objective.tighten(&mut solver, residual_upper as usize) {
                    aglr_telemetry.objective_bound_updates += 1;
                }
            }
            for (literal, weight) in new_objective_terms {
                objective.add_term(&mut solver, literal, weight);
                aglr_telemetry.objective_bound_terms += 1;
            }
            aglr_telemetry.objective_bound_time += encoding_start.elapsed();
        }

        if settings.residual_hardening {
            if let Some((upper, _)) = best_heur.as_ref() {
                apply_residual_hardening(&mut solver, &mut soft_constraints, total_cost, *upper, &mut stats)?;
            }
        }

        //Solve
        //Build asssumption
        let assumption_count = if fixed_target.is_some() { 0 } else { soft_constraints.len() };
        let mut n_assumps = if fixed_target.is_some() { 0 }
            else { settings.assumption_strategy.initial(assumption_count) };
        let mut assumptions = soft_constraints
            .iter()
            .map(|(k, (_, w, _))| (*k, *w))
            .collect::<Vec<_>>();
        // HashMap iteration order is deliberately unspecified.  Keeping only
        // the weight in the comparator therefore changed the SAT branching
        // order between runs, even when the input and binary were identical.
        // Break equal-weight ties by the literal value so a run is
        // reproducible without changing the RC2 objective or its proof.
        assumptions.sort_by(|a, b| {
            b.1.cmp(&a.1).then_with(|| a.0.cmp(&b.0))
        });
        if fixed_target.is_some() { assumptions.clear(); }

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
            let mut cycle_clause=None;
            let mut path_cuts=Vec::new();
            let mut master_solution=None;
            let mut master_return=None;
            {
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
                satcoder::SatResultWithCore::Sat(_) if n_assumps < assumption_count => {
                    stats.partial_sat_calls += 1;
                    n_assumps = settings.assumption_strategy.next(n_assumps, assumption_count);
                }
                satcoder::SatResultWithCore::Sat(model) => {
                    if settings.order_master{
                        stats.order_master_models+=1;stats.order_path_checks+=1;stats.order_cycle_checks+=1;
                        let path_start=Instant::now();
                        match resource_orders.analyse(path_topology.as_ref().unwrap(),|lit|model.value(&lit))
                            .map_err(SolverError::InvalidSolution)?{
                            super::order_paths::Analysis::Cycle(clause)=>{
                                resource_orders.remember(&super::order_paths::Cut::Cycle(clause.clone()))
                                    .map_err(SolverError::InvalidSolution)?;
                                cycle_clause=Some(clause);
                            }
                            super::order_paths::Analysis::Feasible(schedule)=>{
                                stats.order_master_schedules+=1;
                                let mut times=problem.trains.iter().map(|train|Vec::with_capacity(train.visits.len()+1)).collect::<Vec<_>>();
                                let mut cost=0i32;
                                for (id,&(train,index)) in visits.iter_enumerated(){
                                    let time=schedule.times[usize::from(id)];times[train].push(time);
                                    cost=cost.checked_add(i32::try_from(problem.trains[train].visit_delay_cost(delay_cost_type,index,time))
                                        .map_err(|_|SolverError::InvalidSolution("order master cost exceeds i32".into()))?)
                                        .ok_or_else(||SolverError::InvalidSolution("order master cost overflow".into()))?;
                                }
                                for (train,route) in problem.trains.iter().enumerate(){
                                    if let Some(last)=route.visits.last(){
                                        let exit=times[train].last().unwrap().checked_add(last.travel_time)
                                            .ok_or_else(||SolverError::InvalidSolution("order master completion time overflow".into()))?;
                                        times[train].push(exit);
                                    }else{times[train].push(0);}
                                }
                                if cost<total_cost{return Err(SolverError::InvalidSolution("order graph cost below RC2 lower bound".into()));}
                                if cost<best_heur.as_ref().map_or(i32::MAX,|(upper,_)|*upper) || cost==total_cost{
                                    if problem.verify_solution(&times,delay_cost_type)!=Some(cost){
                                        return Err(SolverError::InvalidSolution("complete order graph returned an invalid schedule".into()));
                                    }
                                    master_solution=Some((cost,times));
                                }
                                if cost==total_cost{master_return=Some(cost);}else{
                                    let model_times=occupations.iter().map(|occ|{
                                        let index=occ.delays.partition_point(|(lit,_)|model.value(lit));
                                        assert!(index>0 && index<occ.delays.len());occ.delays[index-1].1
                                    }).collect::<Vec<_>>();
                                    let mut cuts=schedule.violated_batch(&model_times,|v,bound,current|{
                                        let (train,index)=visits[VisitId::from(v)];
                                        problem.trains[train].visit_delay_cost(delay_cost_type,index,bound)
                                            .saturating_sub(problem.trains[train].visit_delay_cost(delay_cost_type,index,current))
                                    },true,if settings.order_master_batch_cuts{usize::MAX}else{1})
                                        .map_err(SolverError::InvalidSolution)?;
                                    if cuts.is_empty(){return Err(SolverError::InvalidSolution("order master cost gap has no violated objective path".into()));}
                                    stats.order_master_max_batch=stats.order_master_max_batch.max(cuts.len());
                                    for cut in &mut cuts {
                                        if settings.order_master_cost_levels {
                                            if let super::order_paths::Cut::Path{visit,time,..}=cut {
                                                let (train,index)=visits[VisitId::from(*visit)];
                                                *time=super::order_paths::cost_threshold(occupations[VisitId::from(*visit)].delays[0].1,*time,
                                                    |t|problem.trains[train].visit_delay_cost(delay_cost_type,index,t))
                                                    .map_err(SolverError::InvalidSolution)?;
                                            }
                                        }
                                        resource_orders.remember(cut).map_err(SolverError::InvalidSolution)?;
                                    }
                                    for cut in cuts{if let super::order_paths::Cut::Path{visit,time,prefix}=cut{path_cuts.push((visit,time,prefix));}}
                                }
                            }
                        }
                        stats.order_path_time+=path_start.elapsed();
                    }else if let Some(topology)=&path_topology{
                        let path_start=Instant::now();stats.order_path_checks+=1;stats.order_cycle_checks+=1;
                        let model_times=occupations.iter().map(|occ|{
                            let index=occ.delays.partition_point(|(lit,_)|model.value(lit));
                            assert!(index>0 && index<occ.delays.len());occ.delays[index-1].1
                        }).collect::<Vec<_>>();
                        match resource_orders.separate_path(topology,&model_times,|lit|model.value(&lit),|v,bound,current|{
                            let (train,index)=visits[VisitId::from(v)];
                            problem.trains[train].visit_delay_cost(delay_cost_type,index,bound)
                                .saturating_sub(problem.trains[train].visit_delay_cost(delay_cost_type,index,current))
                        }).expect("invalid temporal path separation"){
                            Some(super::order_paths::Cut::Cycle(clause))=>cycle_clause=Some(clause),
                            Some(super::order_paths::Cut::Path{visit,time,prefix})=>path_cuts.push((visit,time,prefix)),
                            None=>{}
                        }
                        stats.order_path_time+=path_start.elapsed();
                    }
                    if let Some(topology)=&order_topology {
                        let cycle_start=Instant::now();stats.order_cycle_checks+=1;
                        cycle_clause=resource_orders.separate_cycle(topology,|lit|model.value(&lit))
                            .expect("invalid temporal cycle separation");
                        stats.order_cycle_time+=cycle_start.elapsed();
                    }
                    if !settings.order_master && cycle_clause.is_none() && path_cuts.is_empty() {
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
                }

                satcoder::SatResultWithCore::Unsat(core) => {
                    is_sat = false;
                    stats.n_unsat += 1;
                    break Some(core);
                }
            }
            } // Drop both the model and SAT result before mutating the solver.
            if let Some((cost,times))=master_solution{
                heuristic_filter.update_best(cost);best_heur=Some((cost,times));
            }
            if let Some(cost)=master_return{
                do_output_stats(&mut output_stats,iteration,&iteration_types,&stats,&occupations,
                    start_time,solver_time,total_cost,cost,&aglr_telemetry,&heuristic_filter);
                return Ok((best_heur.unwrap().1,stats));
            }
            if !path_cuts.is_empty(){
                for (index,time,mut prefix) in path_cuts {
                    let visit=VisitId::from(index);
                    let (literal,is_new)=occupations[visit].time_point(&mut solver,time);
                    if is_new{new_time_points.push((visit,literal,time));stats.order_path_new_points+=1;}
                    stats.order_path_guards+=prefix.len();prefix.push(literal);solver.add_clause(prefix);
                    stats.order_paths_added+=1;
                }
                output_stats("maxsat_order_path_checks".into(),stats.order_path_checks.into());
                output_stats("maxsat_order_paths_added".into(),stats.order_paths_added.into());
                output_stats("maxsat_order_path_new_points".into(),stats.order_path_new_points.into());
                output_stats("maxsat_order_path_guards".into(),stats.order_path_guards.into());
                output_stats("maxsat_order_path_time".into(),stats.order_path_time.as_secs_f64().into());
                // New ladder points must receive their objective costs before
                // another SAT call. Skip conflict detection on the stale model.
                is_sat=false;break None;
            }
            if let Some(clause)=cycle_clause {
                solver.add_clause(clause);
                stats.order_cycles_blocked+=1;
                output_stats("maxsat_order_cycle_checks".to_string(),stats.order_cycle_checks.into());
                output_stats("maxsat_order_cycles_blocked".to_string(),stats.order_cycles_blocked.into());
                output_stats("maxsat_order_cycle_time".to_string(),stats.order_cycle_time.as_secs_f64().into());
            }
        };

        //Core handling RC2
        if let Some(core) = core {
            let _p = hprof::enter("treat core");

            if let Some(target) = fixed_target {
                // No cost assumptions were used. UNSAT of this relaxation
                // proves that no valid schedule can meet the fixed threshold.
                if !core.is_empty() {
                    return Err(SolverError::InvalidSolution(
                        "fixed-bound decision unexpectedly returned an assumption core".into()));
                }
                do_output_stats(&mut output_stats, iteration, &iteration_types, &stats,
                    &occupations, start_time, solver_time, target.saturating_add(1),
                    best_heur.as_ref().map(|x|x.0).unwrap_or(i32::MAX),
                    &aglr_telemetry, &heuristic_filter);
                output_stats("diagnostic_outcome".into(), "unsat".into());
                return Err(SolverError::NoSolution);
            }

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
                if binary_objective.is_some() || (settings.residual_hardening && best_heur.is_some()) {
                    return Err(SolverError::InvalidSolution(
                        "bounded or hardened model is UNSAT despite a verified feasible upper bound".to_string()
                    ));
                }
                return Err(SolverError::NoSolution); // UNSAT
            }

            let mut core = core.iter().map(|c| Bool::Lit(*c)).collect::<Vec<_>>();
            if settings.core_trim_checks > 0 && core.len() > 1 {
                let trim_started = Instant::now();
                let outcome = super::core_minimize::trim(
                    core, settings.core_trim_checks,
                    |literal| soft_constraints[&literal].1,
                    |assumptions| {
                        let started = Instant::now();
                        stats.sat_calls += 1;
                        let result = match std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                            crate::solvers::util::minisat_deadline::with_core_check_limit(
                                settings.core_minimize_conflicts, || {
                                    match solver.solve_with_assumptions(assumptions.iter().copied()) {
                                        satcoder::SatResultWithCore::Sat(_) => Err(
                                            "SAT contradicts the proved core during trimming".to_string()),
                                        satcoder::SatResultWithCore::Unsat(proof) => Ok(Some(
                                            proof.iter().map(|&literal| Bool::Lit(literal)).collect())),
                                    }
                                },
                            )
                        })) {
                            Ok(result) => result,
                            Err(payload) if payload.is::<crate::solvers::util::minisat_deadline::CoreCheckInconclusive>() => {
                                stats.core_trim_inconclusive += 1;
                                Ok(None)
                            },
                            Err(payload) => std::panic::resume_unwind(payload),
                        };
                        solver_time += started.elapsed();
                        result
                    },
                    || start_time.elapsed().as_secs_f64() >= timeout,
                ).map_err(SolverError::InvalidSolution)?;
                stats.core_trim_calls += outcome.checks;
                stats.core_trim_removed += outcome.removed;
                stats.core_trim_weight_increases += usize::from(outcome.minimum_weight_increased);
                stats.core_trim_time += trim_started.elapsed();
                core = outcome.core;
                // Preserve completed trimming telemetry even if a later native
                // SAT query reaches its watchdog deadline and unwinds the loop.
                output_trim_stats(&mut output_stats, &stats);
            }
            if settings.core_minimize_checks > 0 && core.len() > 1 {
                let minimize_start = Instant::now();
                let outcome = super::core_minimize::minimize(
                    core, settings.core_minimize_checks,
                    |literal| soft_constraints[&literal].1,
                    |assumptions| {
                        let call_start = Instant::now();
                        stats.sat_calls += 1;
                        let result = match std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                            crate::solvers::util::minisat_deadline::with_core_check_limit(settings.core_minimize_conflicts,|| {
                                match solver.solve_with_assumptions(assumptions.iter().copied()) {
                                    satcoder::SatResultWithCore::Sat(_)=>None,
                                    satcoder::SatResultWithCore::Unsat(proved)=>Some(
                                        proved.iter().map(|&literal|Bool::Lit(literal)).collect()),
                                }
                            })
                        })) {
                            Ok(result)=>result,
                            Err(payload) if payload.is::<crate::solvers::util::minisat_deadline::CoreCheckInconclusive>()=>{
                                stats.core_minimize_inconclusive+=1;
                                None // No new UNSAT proof: preserve the already proved core.
                            },
                            Err(payload)=>std::panic::resume_unwind(payload),
                        };
                        solver_time += call_start.elapsed();
                        result
                    },
                    || start_time.elapsed().as_secs_f64() >= timeout,
                ).map_err(SolverError::InvalidSolution)?;
                stats.core_minimize_calls += outcome.checks;
                stats.core_minimize_removed += outcome.removed;
                stats.core_minimize_weight_increases += usize::from(outcome.minimum_weight_increased);
                stats.core_minimize_time += minimize_start.elapsed();
                core = outcome.core;
            }

            if settings.am1_checks>0 {
                let applied=adapt_intrinsic_am1(&mut solver,&mut soft_constraints,&core,settings,
                    &mut total_cost,&mut stats,&mut solver_time,start_time,timeout)?;
                output_am1_stats(&mut output_stats,&stats);
                if applied {
                    *iteration_types.entry(IterationType::Objective).or_default()+=1;
                    last_progress_iteration=iteration;
                    if let Some((upper,solution))=&best_heur {
                        if total_cost>*upper {return Err(SolverError::InvalidSolution("AM1 bound exceeds verified feasible cost".into()));}
                        if total_cost==*upper {
                            do_output_stats(&mut output_stats,iteration,&iteration_types,&stats,&occupations,
                                start_time,solver_time,total_cost,*upper,&aglr_telemetry,&heuristic_filter);
                            return Ok((solution.clone(),stats));
                        }
                    }
                    println!("    LB={}",total_cost);
                    iteration+=1;
                    continue;
                }
            }

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
            if (settings.residual_hardening || settings.core_minimize_checks > 0) && best_heur.as_ref().is_some_and(|(upper, _)| *upper < total_cost) {
                return Err(SolverError::InvalidSolution(
                    "lower bound exceeds a verified feasible cost during residual hardening".to_string()
                ));
            }
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
                let mut bound = 1;
                let mut tot = Totalizer::count(&mut solver, core.iter().map(|c| !*c), bound as u32);
                if settings.core_exhaust_checks > 0 {
                    let exhaust_start = Instant::now();
                    let outcome = super::core_exhaust::exhaust(core.len(), settings.core_exhaust_checks,
                        |tested_bound| {
                            tot.increase_bound(&mut solver, tested_bound as u32);
                            let assumption = !tot.rhs()[tested_bound];
                            let call_start = Instant::now();
                            stats.sat_calls += 1;
                            let result = match std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                                crate::solvers::util::minisat_deadline::with_core_check_limit(settings.core_minimize_conflicts, || {
                                    match solver.solve_with_assumptions([assumption]) {
                                        satcoder::SatResultWithCore::Sat(_) => Ok(Some(false)),
                                        satcoder::SatResultWithCore::Unsat(proof) => {
                                            if proof.len()!=1 || Bool::Lit(proof[0])!=assumption {
                                                Err("core-exhaustion proof is empty or contains an unqueried literal".to_string())
                                            } else { Ok(Some(true)) }
                                        },
                                    }
                                })
                            })) {
                                Ok(answer) => answer,
                                Err(payload) if payload.is::<crate::solvers::util::minisat_deadline::CoreCheckInconclusive>() => Ok(None),
                                Err(payload) => std::panic::resume_unwind(payload),
                            };
                            let elapsed = call_start.elapsed();
                            solver_time += elapsed;
                            crate::solvers::util::minisat_deadline::record_exhaust_check(
                                elapsed, matches!(result, Ok(Some(true))), matches!(result, Ok(None)));
                            if matches!(result, Ok(Some(true))) {
                                // F AND assumption was proved UNSAT: its negation
                                // is entailed by F and may be made permanent.
                                SatInstance::add_clause(&mut solver, [!assumption]);
                            }
                            result
                        }, || start_time.elapsed().as_secs_f64() >= timeout,
                    ).map_err(SolverError::InvalidSolution)?;
                    stats.core_exhaust_calls += outcome.checks;
                    stats.core_exhaust_steps += outcome.bound-1;
                    stats.core_exhaust_inconclusive += outcome.inconclusive;
                    stats.core_exhaust_time += exhaust_start.elapsed();
                    bound = outcome.bound;
                    let extra_cost = min_weight.checked_mul(bound-1).and_then(|n| i32::try_from(n).ok())
                        .ok_or_else(|| SolverError::InvalidSolution("core-exhaustion cost overflow".to_string()))?;
                    total_cost = total_cost.checked_add(extra_cost)
                        .ok_or_else(|| SolverError::InvalidSolution("core-exhaustion lower-bound overflow".to_string()))?;
                    if best_heur.as_ref().is_some_and(|(upper,_)| *upper < total_cost) {
                        return Err(SolverError::InvalidSolution("core exhaustion exceeded a verified feasible cost".to_string()));
                    }
                    if extra_cost > 0 { println!("    EXHAUST LB={} STEPS={}",total_cost,bound-1); }
                    if best_heur.as_ref().is_some_and(|(upper,_)| *upper == total_cost) {
                        do_output_stats(&mut output_stats, iteration, &iteration_types, &stats,
                            &occupations, start_time, solver_time, total_cost, total_cost,
                            &aglr_telemetry, &heuristic_filter);
                        return Ok((best_heur.unwrap().1, stats));
                    }
                }
                if bound < core.len() {
                    // The floor has already been charged to LB. Further
                    // violations retain their original minimum core weight.
                    tot.increase_bound(&mut solver, bound as u32);
                    assert!(bound < tot.rhs().len());
                    soft_constraints.insert(
                        !tot.rhs()[bound],
                        (Soft::Totalizer(tot, bound), min_weight, min_weight),
                    );
                }
            } else {
                SatInstance::add_clause(&mut solver, vec![!core[0]]);
            }
        }

        iteration += 1;
    }
}

fn output_trim_stats(output: &mut impl FnMut(String, serde_json::Value), stats: &SolveStats) {
    output("maxsat_core_trim_calls".into(), stats.core_trim_calls.into());
    output("maxsat_core_trim_removed".into(), stats.core_trim_removed.into());
    output("maxsat_core_trim_weight_increases".into(), stats.core_trim_weight_increases.into());
    output("maxsat_core_trim_inconclusive".into(), stats.core_trim_inconclusive.into());
    output("maxsat_core_trim_time".into(), stats.core_trim_time.as_secs_f64().into());
}

fn output_am1_stats(output: &mut impl FnMut(String, serde_json::Value), stats: &SolveStats) {
    output("maxsat_am1_calls".into(),stats.am1_calls.into());
    output("maxsat_am1_groups".into(),stats.am1_groups.into());
    output("maxsat_am1_literals".into(),stats.am1_literals.into());
    output("maxsat_am1_inconclusive".into(),stats.am1_inconclusive.into());
    output("maxsat_am1_fixed_cost".into(),stats.am1_fixed_cost.into());
    output("maxsat_am1_time".into(),stats.am1_time.as_secs_f64().into());
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
    output_trim_stats(output_stats, stats);
    output_am1_stats(output_stats, stats);
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
    output_stats("maxsat_core_minimize_calls".to_string(), stats.core_minimize_calls.into());
    output_stats("maxsat_core_minimize_removed".to_string(), stats.core_minimize_removed.into());
    output_stats("maxsat_core_minimize_weight_increases".to_string(), stats.core_minimize_weight_increases.into());
    output_stats("maxsat_core_minimize_inconclusive".to_string(), stats.core_minimize_inconclusive.into());
    output_stats("maxsat_core_minimize_time".to_string(), stats.core_minimize_time.as_secs_f64().into());
    output_stats("maxsat_core_exhaust_calls".to_string(), stats.core_exhaust_calls.into());
    output_stats("maxsat_order_cycle_checks".to_string(), stats.order_cycle_checks.into());
    output_stats("maxsat_order_cycles_blocked".to_string(), stats.order_cycles_blocked.into());
    output_stats("maxsat_order_cycle_time".to_string(), stats.order_cycle_time.as_secs_f64().into());
    output_stats("maxsat_order_path_checks".to_string(),stats.order_path_checks.into());
    output_stats("maxsat_order_paths_added".to_string(),stats.order_paths_added.into());
    output_stats("maxsat_order_path_new_points".to_string(),stats.order_path_new_points.into());
    output_stats("maxsat_order_path_guards".to_string(),stats.order_path_guards.into());
    output_stats("maxsat_order_path_time".to_string(),stats.order_path_time.as_secs_f64().into());
    output_stats("maxsat_order_master_models".to_string(),stats.order_master_models.into());
    output_stats("maxsat_order_master_schedules".to_string(),stats.order_master_schedules.into());
    output_stats("maxsat_order_master_max_batch".to_string(),stats.order_master_max_batch.into());
    output_stats("maxsat_order_master_seed_clauses".to_string(),stats.order_master_seed_clauses.into());
    output_stats("maxsat_order_master_seed_points".to_string(),stats.order_master_seed_points.into());
    output_stats("maxsat_core_exhaust_steps".to_string(), stats.core_exhaust_steps.into());
    output_stats("maxsat_core_exhaust_inconclusive".to_string(), stats.core_exhaust_inconclusive.into());
    output_stats("maxsat_core_exhaust_time".to_string(), stats.core_exhaust_time.as_secs_f64().into());
    output_stats("maxsat_hardening_scans".to_string(), stats.hardening_scans.into());
    output_stats("maxsat_hardened_primary".to_string(), stats.hardened_primary.into());
    output_stats("maxsat_hardened_totalizer".to_string(), stats.hardened_totalizer.into());
    output_stats("maxsat_hardening_time".to_string(), stats.hardening_time.as_secs_f64().into());
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
    fn fixed_diagnostic_budget_matches_weighted_truth_table() {
        for upper in [0,1,7,31] {
            let mut solver=satcoder::solvers::minisat::Solver::new();
            let literals=(0..3).map(|_|solver.new_var()).collect::<Vec<_>>();
            let mut objective=BinaryObjective::new(&mut solver,upper);
            objective.fix_budget(&mut solver);
            for (&literal,weight) in literals.iter().zip([1,3,17]) {
                objective.add_term(&mut solver,literal,weight);
            }
            for mask in 0..8 {
                let cost=[1,3,17].iter().enumerate().filter(|(i,_)|mask&(1<<i)!=0)
                    .map(|(_,weight)|weight).sum::<usize>();
                match solver.solve_with_assumptions(literals.iter().enumerate()
                    .map(|(i,lit)|if mask&(1<<i)!=0{*lit}else{!*lit})) {
                    satcoder::SatResultWithCore::Sat(model) => {
                        assert!(cost<=upper);
                        let budget=objective.reg_bits.iter().enumerate()
                            .map(|(i,bit)|usize::from(model.value(bit))<<i).sum::<usize>();
                        assert_eq!(budget,upper);
                    }
                    satcoder::SatResultWithCore::Unsat(_) => assert!(cost>upper),
                };
            }
        }
    }

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

    #[test]
    fn bound_diagnostic_decisions_match_exhaustive_optima() {
        let problem = two_train_problem();
        for objective in [DelayCostType::Continuous, DelayCostType::FiniteSteps123,
            DelayCostType::InfiniteSteps180] {
            let optimum = (0..=4).flat_map(|a| (0..=4).map(move |b|(a,b)))
                .filter_map(|(a,b)|problem.verify_solution(&[vec![a,a+2],vec![b,b+2]],objective))
                .min().unwrap();
            for resource_orders in [false, true] {
                for target in 0..=optimum+1 {
                    let mut settings = MaxSatDddLadderScSettings::default();
                    settings.resource_orders = resource_orders;
                    settings.order_transitivity = resource_orders;
                    let mut output = serde_json::Map::new();
                    let result = solve_bound_diagnostic(||panic!("decision must not start a MIP heuristic"),
                        satcoder::solvers::minisat::Solver::new(), &problem, 5.0, objective,
                        settings, BoundDiagnostic::Decision(target), |k,v|{output.insert(k,v);});
                    if target < optimum {
                        assert!(matches!(result,Err(SolverError::NoSolution)),"target={target}");
                        assert_eq!(output["diagnostic_outcome"],"unsat");
                    } else {
                        let solution = result.unwrap().0;
                        assert!(problem.verify_solution(&solution,objective).unwrap() <= target);
                        assert_eq!(output["diagnostic_outcome"],"sat");
                    }
                    assert_eq!(output["maxsat_core_literals"],0);
                    assert_eq!(output["maxsat_partial_sat_calls"],0);
                }
            }
        }
    }

    #[test]
    fn bound_diagnostic_upper_is_verified_and_not_assigned_to_lower_bound() {
        let problem = two_train_problem();
        let schedule = vec![vec![0,2],vec![2,4]];
        let mut first_lb = None;
        let result = solve_bound_diagnostic(||panic!("oracle UB must not start a MIP heuristic"),
            satcoder::solvers::minisat::Solver::new(), &problem, 5.0, DelayCostType::Continuous,
            MaxSatDddLadderScSettings::default(), BoundDiagnostic::VerifiedUpper(&schedule),
            |key,value|{if key=="diagnostic_lb" && first_lb.is_none(){first_lb=Some(value);}}).unwrap();
        assert_eq!(first_lb,Some(serde_json::json!(0)));
        assert_eq!(problem.verify_solution(&result.0,DelayCostType::Continuous),Some(exhaustive_optimum(&problem)));
        for invalid in [vec![vec![0,2]], vec![vec![0,2],vec![0,2]]] {
            assert!(matches!(solve_bound_diagnostic(||panic!("invalid incumbent must be rejected"),
                satcoder::solvers::minisat::Solver::new(), &problem, 5.0, DelayCostType::Continuous,
                MaxSatDddLadderScSettings::default(), BoundDiagnostic::VerifiedUpper(&invalid),
                |_,_|{}),Err(SolverError::InvalidSolution(_))));
        }
    }

    #[test]
    fn bound_diagnostic_zero_cost_and_negative_threshold() {
        let mut problem = two_train_problem();
        problem.trains.truncate(1);
        let result = solve_bound_diagnostic(||panic!("SAT decision starts no heuristic"),
            satcoder::solvers::minisat::Solver::new(), &problem, 5.0, DelayCostType::Continuous,
            MaxSatDddLadderScSettings::default(), BoundDiagnostic::Decision(0), |_,_|{}).unwrap();
        assert_eq!(problem.verify_solution(&result.0,DelayCostType::Continuous),Some(0));
        assert!(matches!(solve_bound_diagnostic(||panic!("invalid threshold"),
            satcoder::solvers::minisat::Solver::new(), &problem, 5.0, DelayCostType::Continuous,
            MaxSatDddLadderScSettings::default(), BoundDiagnostic::Decision(-1), |_,_|{}),
            Err(SolverError::InvalidSolution(_))));
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
                   for hardening in [false, true] {
                    let mut settings = MaxSatDddLadderScSettings::default();
                    settings.resource_orders = true;
                    settings.order_transitivity = transitivity;
                    settings.sparse_costs = sparse;
                    settings.use_objective_bound = use_bound;
                    settings.residual_hardening = hardening;
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
            }
            for use_bound in [false, true] {
              for hardening in [false, true] {
                let mut settings = MaxSatDddLadderScSettings::default();
                settings.resource_orders = true;
                settings.order_transitivity = true;
                settings.use_objective_bound = use_bound;
                settings.residual_hardening = hardening;
                let (solution, _) = solve_with_settings(
                    &quiet_env,
                    crate::solvers::ddd::incremental_sat::new_maxsat_glucose_solver(),
                    &problem, 30.0, objective, settings, |_, _| {},
                ).unwrap();
                assert_eq!(problem.verify_solution(&solution, objective), Some(optimum));
              }
            }
        }
    }

    #[test]
    fn residual_hardening_actually_fixes_an_expensive_alternative_and_preserves_optimum() {
        let problem = Problem {
            name: "short-before-long".to_string(),
            trains: [1, 10].into_iter().map(|travel_time| Train { visits: vec![
                Visit { resource_id: 0, earliest: 0, aimed: Some(0), travel_time },
            ] }).collect(),
            conflicts: vec![(0, 0)],
        };
        let mut optimum = i32::MAX;
        for a in 0..=12 {
            for b in 0..=12 {
                if let Some(cost) = problem.verify_solution(
                    &vec![vec![a,a+1], vec![b,b+10]], DelayCostType::Continuous,
                ) { optimum = optimum.min(cost); }
            }
        }
        assert_eq!(optimum, 1);
        for hardening in [false, true] {
            let mut settings = MaxSatDddLadderScSettings::default();
            settings.resource_orders = true;
            settings.order_transitivity = true;
            settings.residual_hardening = hardening;
            let (solution, stats) = solve_with_settings(
                &quiet_env, satcoder::solvers::minisat::Solver::new(),
                &problem, 30.0, DelayCostType::Continuous, settings, |_, _| {},
            ).unwrap();
            assert_eq!(problem.verify_solution(&solution, DelayCostType::Continuous), Some(optimum));
            if hardening { assert!(stats.hardened_primary > 0); }
        }
    }

    #[test]
    fn order_master_matches_exhaustive_optima_with_final_occupations_and_constant_costs(){
        let problem=Problem{name:"order-master-final-visits".into(),trains:[1,2,3].into_iter().map(|aimed|Train{
            visits:vec![Visit{resource_id:7,earliest:5,aimed:Some(aimed),travel_time:2}],
        }).collect(),conflicts:vec![(7,7)]};
        let mut observed_paths=0;
        for objective in [DelayCostType::Continuous,DelayCostType::FiniteSteps123,DelayCostType::InfiniteSteps180]{
            let mut optimum=i32::MAX;
            for a in 5..=9{for b in 5..=9{for c in 5..=9{
                if a+2<=b || b+2<=a{if a+2<=c || c+2<=a{if b+2<=c || c+2<=b{
                    let times=vec![vec![a,a+2],vec![b,b+2],vec![c,c+2]];
                    optimum=optimum.min(problem.verify_solution(&times,objective).unwrap());
                }}}
            }}}
            assert_ne!(optimum,i32::MAX);
            for offset in [false,true]{for bound in [false,true]{for sparse in [false,true]{for levels in [false,true]{for batch in [false,true]{for seeds in [false,true]{
                let mut settings=MaxSatDddLadderScSettings::default();settings.resource_orders=true;settings.order_master=true;
                settings.order_master_cost_levels=levels;
                settings.order_master_batch_cuts=batch;settings.order_master_seed_costs=seeds;
                settings.extract_initial_cost=offset;settings.use_objective_bound=bound;settings.sparse_costs=sparse;
                settings.assumption_strategy=super::super::settings::AssumptionStrategy::Full;
                settings.core_minimize_checks=4;settings.core_minimize_conflicts=100;settings.core_exhaust_checks=4;
                let mut telemetry=BTreeMap::new();
                let (solution,stats)=solve_with_settings(&quiet_env,crate::solvers::util::minisat_deadline::Solver::new(30.0),
                    &problem,30.0,objective,settings,|k,v|{telemetry.insert(k,v);}).unwrap();
                assert_eq!(problem.verify_solution(&solution,objective),Some(optimum));
                assert_eq!(telemetry["lb"].as_i64(),Some(optimum as i64));assert_eq!(telemetry["ub"].as_i64(),Some(optimum as i64));
                assert_eq!(stats.resource_order_pairs,3);assert_eq!(stats.resource_order_rows,0);assert_eq!(stats.n_conflict,0);
                observed_paths+=stats.order_paths_added;
                settings.core_exhaust_checks=0;settings.core_minimize_checks=0;settings.core_minimize_conflicts=0;
                let (solution,_)=solve_with_settings(&quiet_env,satcoder::solvers::cadical::Solver::new(),
                    &problem,30.0,objective,settings,|_,_|{}).unwrap();
                assert_eq!(problem.verify_solution(&solution,objective),Some(optimum));
            }}}}}}
        }
        assert!(observed_paths>0,"the master must learn a cost path rather than enumerate times in SAT");
        // A feasible initial schedule with positive cost must not skip initial costs.
        let independent=Problem{name:"order-master-positive-initial-cost".into(),
            trains:vec![Train{visits:vec![Visit{resource_id:1,earliest:5,aimed:Some(0),travel_time:0}]}],conflicts:vec![]};
        for objective in [DelayCostType::Continuous,DelayCostType::FiniteSteps123,DelayCostType::InfiniteSteps180]{
            let mut settings=MaxSatDddLadderScSettings::default();settings.resource_orders=true;settings.order_master=true;
            let expected=independent.cost(&[vec![5,5]],objective);
            let (solution,_)=solve_with_settings(&quiet_env,satcoder::solvers::minisat::Solver::new(),
                &independent,30.0,objective,settings,|_,_|{}).unwrap();
            assert_eq!(independent.verify_solution(&solution,objective),Some(expected));
        }
    }

    #[test]
    fn order_master_crossing_routes_match_exhaustive_time_schedules(){
        let mut observed_batch=0;let mut observed_seeds=0;
        let routes=[vec![1,2],vec![1,2],vec![2,1]];
        let problem=Problem{name:"order-master-crossing".into(),trains:routes.iter().map(|route|Train{
            visits:route.iter().enumerate().map(|(i,&resource_id)|Visit{resource_id,earliest:(2*i) as i32,
                aimed:(i==1).then_some(2),travel_time:2}).chain(std::iter::once(Visit{resource_id:0,earliest:4,aimed:None,travel_time:0})).collect(),
        }).collect(),conflicts:vec![(1,1),(2,2)]};
        let choices=(0..=6).flat_map(|a|(a+2..=8).map(move|b|(a,b))).collect::<Vec<_>>();
        for objective in [DelayCostType::Continuous,DelayCostType::FiniteSteps123,DelayCostType::InfiniteSteps180]{
            let mut optimum=i32::MAX;
            for &(a,b) in &choices{for &(c,d) in &choices{for &(e,f) in &choices{
                let ts=[[a,b],[c,d],[e,f]];
                let valid=(0..3).all(|i|(i+1..3).all(|j|(0..2).all(|v|(0..2).all(|w|{
                    routes[i][v]!=routes[j][w] || (if v==0{ts[i][1]}else{ts[i][1]+2})<=ts[j][w]
                        || (if w==0{ts[j][1]}else{ts[j][1]+2})<=ts[i][v]
                }))));
                if valid{let sol=ts.iter().map(|t|vec![t[0],t[1],t[1]+2,t[1]+2]).collect::<Vec<_>>();
                    optimum=optimum.min(problem.verify_solution(&sol,objective).unwrap());}
            }}}
            assert_eq!(optimum,if matches!(objective,DelayCostType::Continuous){4}else{1});
            for strategy in [super::super::settings::AssumptionStrategy::Legacy,super::super::settings::AssumptionStrategy::Full]{for batch in [false,true]{for seeds in [false,true]{
                let mut settings=MaxSatDddLadderScSettings::default();settings.resource_orders=true;settings.order_master=true;
                settings.order_master_cost_levels=true;
                settings.order_master_batch_cuts=batch;settings.order_master_seed_costs=seeds;
                settings.assumption_strategy=strategy;settings.core_minimize_checks=4;settings.core_minimize_conflicts=100;settings.core_exhaust_checks=4;
                let (solution,stats)=solve_with_settings(&quiet_env,crate::solvers::util::minisat_deadline::Solver::new(30.0),
                    &problem,30.0,objective,settings,|_,_|{}).unwrap();
                assert_eq!(problem.verify_solution(&solution,objective),Some(optimum));
                assert_eq!(stats.resource_order_pairs,6);assert_eq!(stats.resource_order_rows,0);assert!(stats.order_master_schedules>0);
                if seeds{observed_seeds=observed_seeds.max(stats.order_master_seed_clauses);}else{assert_eq!(stats.order_master_seed_clauses,0);}
                if batch{observed_batch=observed_batch.max(stats.order_master_max_batch);}else{assert!(stats.order_master_max_batch<=1);}
                settings.core_minimize_checks=0;settings.core_minimize_conflicts=0;settings.core_exhaust_checks=0;
                let (solution,_)=solve_with_settings(&quiet_env,satcoder::solvers::cadical::Solver::new(),
                    &problem,30.0,objective,settings,|_,_|{}).unwrap();
                assert_eq!(problem.verify_solution(&solution,objective),Some(optimum));
            }}}
        }
        assert!(observed_seeds>0,"exercise guarded initial costs independently of dynamic path cuts");
        assert!(observed_batch>1,"exercise simultaneous path-cost registration before the next SAT call");
    }

    #[test]
    fn temporal_paths_match_exhaustive_cross_route_optima_with_cost_registration(){
        let routes=[vec![1,2],vec![1,2],vec![2,1]];
        let problem=Problem{name:"whole-path-three-trains".into(),
            trains:routes.iter().map(|route|Train{visits:route.iter().enumerate().map(|(i,&resource_id)|Visit{
                resource_id,earliest:(2*i) as i32,aimed:(i==1).then_some(2),travel_time:2,
            }).chain(std::iter::once(Visit{resource_id:0,earliest:4,aimed:None,travel_time:0})).collect()}).collect(),
            conflicts:vec![(1,1),(2,2)]};
        let choices=(0..=6).flat_map(|a|(a+2..=8).map(move|b|(a,b))).collect::<Vec<_>>();
        let mut observed_paths=0;
        for objective in [DelayCostType::Continuous,DelayCostType::FiniteSteps123,DelayCostType::InfiniteSteps180]{
            let mut optimum=i32::MAX;
            for &(a,b) in &choices{for &(c,d) in &choices{for &(e,f) in &choices{
                let times=[[a,b],[c,d],[e,f]];
                let valid=(0..3).all(|i|(i+1..3).all(|j|(0..2).all(|v|(0..2).all(|w|{
                    if routes[i][v]!=routes[j][w]{return true;}
                    let exit_i=if v==0{times[i][1]}else{times[i][1]+2};
                    let exit_j=if w==0{times[j][1]}else{times[j][1]+2};
                    exit_i<=times[j][w] || exit_j<=times[i][v]
                }))));
                if valid{let solution=times.iter().map(|ts|vec![ts[0],ts[1],ts[1]+2,ts[1]+2]).collect::<Vec<_>>();
                    let cost=problem.verify_solution(&solution,objective).unwrap();optimum=optimum.min(cost);}
            }}}
            // With cost <=4 every continuous target is <=8. For step costs,
            // zero is impossible because the first two trains share a target.
            assert_eq!(optimum,if matches!(objective,DelayCostType::Continuous){4}else{1});
            // The greedy seed is infeasible on these crossing routes. Test
            // the experimental configuration, which leaves objective bounds off;
            // bound interaction is covered by the valid-seed residual test.
            for paths in [false,true]{
                let mut settings=MaxSatDddLadderScSettings::default();settings.resource_orders=true;
                settings.order_transitivity=true;settings.order_path_cuts=paths;
                settings.core_minimize_checks=4;settings.core_minimize_conflicts=100;settings.core_exhaust_checks=4;
                let (solution,stats)=solve_with_settings(&quiet_env,
                    crate::solvers::util::minisat_deadline::Solver::new(30.0),&problem,30.0,objective,settings,|_,_|{}).unwrap();
                assert_eq!(problem.verify_solution(&solution,objective),Some(optimum));
                if !paths{assert_eq!(stats.order_path_checks,0);}
                assert!(stats.order_path_new_points<=stats.order_paths_added);observed_paths+=stats.order_paths_added;
                if paths{
                    settings.core_minimize_checks=0;settings.core_minimize_conflicts=0;settings.core_exhaust_checks=0;
                    let (solution,stats)=solve_with_settings(&quiet_env,satcoder::solvers::cadical::Solver::new(),
                        &problem,30.0,objective,settings,|_,_|{}).unwrap();
                    assert_eq!(problem.verify_solution(&solution,objective),Some(optimum));observed_paths+=stats.order_paths_added;
                }
            }
        }
        assert!(observed_paths>0,"must exercise a learned path and register its cost before re-solving");
    }

    #[test]
    fn extracting_initial_cost_fixes_a_feasible_positive_cost_initial_schedule() {
        let problem=Problem{name:"feasible-initial-positive-cost".into(),
            trains:[vec![1,2],vec![2,1]].into_iter().map(|route|Train{
                visits:route.into_iter().enumerate().map(|(i,resource_id)|Visit{
                    resource_id,earliest:(2*i) as i32,aimed:Some(0),travel_time:2,
                }).chain(std::iter::once(Visit{resource_id:0,earliest:4,aimed:None,travel_time:0})).collect(),
            }).collect(),conflicts:vec![(1,1),(2,2)]};
        for objective in [DelayCostType::Continuous,DelayCostType::FiniteSteps123,DelayCostType::InfiniteSteps180] {
            let expected=problem.verify_solution(&vec![vec![0,2,4,4];2],objective).unwrap();
            assert!(expected>0);
            for bound in [false,true] {
                let mut settings=MaxSatDddLadderScSettings::default();
                settings.resource_orders=true;settings.extract_initial_cost=true;settings.use_objective_bound=bound;
                let mut telemetry=BTreeMap::new();
                let (solution,_)=solve_with_settings(&quiet_env,
                    crate::solvers::util::minisat_deadline::Solver::new(30.0),
                    &problem,30.0,objective,settings,|k,v|{telemetry.insert(k,v);}).unwrap();
                assert_eq!(problem.verify_solution(&solution,objective),Some(expected));
                assert_eq!(telemetry["maxsat_initial_cost_offset"].as_i64(),Some(expected as i64));
                assert_eq!(telemetry["lb"].as_i64(),Some(expected as i64));
                assert_eq!(telemetry["ub"].as_i64(),Some(expected as i64));
            }
        }
    }

    #[test]
    fn initial_cost_residuals_preserve_exhaustive_optima_and_verified_bounds() {
        let problem=Problem{name:"initial-offset-residual-choices".into(),
            trains:(1..=3).map(|aimed|Train{visits:vec![
                Visit{resource_id:1,earliest:5,aimed:Some(aimed),travel_time:2},
                Visit{resource_id:0,earliest:7,aimed:None,travel_time:0},
            ]}).collect(),conflicts:vec![(1,1)]};
        for objective in [DelayCostType::Continuous,DelayCostType::FiniteSteps123,DelayCostType::InfiniteSteps180] {
            let mut optimum=i32::MAX;
            for a in 5..=9 {for b in 5..=9 {for c in 5..=9 {
                if let Some(cost)=problem.verify_solution(&vec![vec![a,a+2,a+2],vec![b,b+2,b+2],vec![c,c+2,c+2]],objective) {
                    optimum=optimum.min(cost);
                }
            }}}
            assert_ne!(optimum,i32::MAX);
            for offset in [false,true] {for bound in [false,true] {for sparse in [false,true] {for hardening in [false,true] {
                let mut settings=MaxSatDddLadderScSettings::default();settings.resource_orders=true;
                settings.order_transitivity=true;settings.order_cycle_cuts=true;settings.order_path_cuts=true;
                settings.extract_initial_cost=offset;settings.use_objective_bound=bound;
                settings.sparse_costs=sparse;settings.residual_hardening=hardening;
                settings.core_minimize_checks=4;settings.core_minimize_conflicts=100;settings.core_exhaust_checks=4;
                let (solution,_)=solve_with_settings(&quiet_env,
                    crate::solvers::util::minisat_deadline::Solver::new(30.0),
                    &problem,30.0,objective,settings,|_,_|{}).unwrap();
                assert_eq!(problem.verify_solution(&solution,objective),Some(optimum));
                // Independent SAT backend, without MiniSAT-only exhaustion.
                if offset && !hardening {
                    settings.core_minimize_checks=0;settings.core_minimize_conflicts=0;settings.core_exhaust_checks=0;
                    let (solution,_)=solve_with_settings(&quiet_env,satcoder::solvers::cadical::Solver::new(),
                        &problem,30.0,objective,settings,|_,_|{}).unwrap();
                    assert_eq!(problem.verify_solution(&solution,objective),Some(optimum));
                }
            }}}}
        }
    }

    #[test]
    fn temporal_cycle_cuts_match_exhaustive_two_route_optima() {
        let problem=Problem{
            name:"crossing-routes-order-cycles".into(),
            // No unavoidable initial cost: the published path does not account
            // for a constant delay introduced by preprocessing an aimed=0
            // successor. Stagger the routes so resource refinement is needed.
            trains:[vec![1,2],vec![2,1]].into_iter().enumerate().map(|(train,route)|Train{
                // As in TXT instances, resource 0 is a nonconflicting terminal.
                visits:route.into_iter().enumerate().map(|(index,resource_id)|Visit{
                    resource_id,earliest:(2*index+train) as i32,
                    aimed:Some((2*index+train) as i32),travel_time:2,
                }).chain(std::iter::once(Visit{resource_id:0,earliest:(4+train) as i32,
                    aimed:None,travel_time:0})).collect(),
            }).collect(),conflicts:vec![(1,1),(2,2)],
        };
        for objective in [DelayCostType::Continuous,DelayCostType::FiniteSteps123,DelayCostType::InfiniteSteps180] {
            let mut optimum=i32::MAX;
            for a in 0..=6 {for b in a+2..=6 {for c in 0..=6 {for d in c+2..=6 {
                if let Some(cost)=problem.verify_solution(&vec![vec![a,b,b+2,b+2],vec![c,d,d+2,d+2]],objective) {
                    optimum=optimum.min(cost);
                }
            }}}}
            assert_ne!(optimum,i32::MAX);
            for cycles in [false,true] {
                let mut settings=MaxSatDddLadderScSettings::default();
                settings.resource_orders=true;settings.order_transitivity=true;settings.order_cycle_cuts=cycles;
                let (solution,stats)=solve_with_settings(&quiet_env,
                    crate::solvers::util::minisat_deadline::Solver::new(30.0),
                    &problem,30.0,objective,settings,|_,_|{}).unwrap();
                assert_eq!(problem.verify_solution(&solution,objective),Some(optimum));
                // A verified heuristic can close LB=UB before a full SAT model.
                // The forced-model truth table in resource_orders tests the cut.
                assert!(stats.order_cycle_checks<=stats.sat_calls);
                if !cycles {assert_eq!(stats.order_cycle_checks,0);}
                let (solution,_)=solve_with_settings(&quiet_env,satcoder::solvers::cadical::Solver::new(),
                    &problem,30.0,objective,settings,|_,_|{}).unwrap();
                assert_eq!(problem.verify_solution(&solution,objective),Some(optimum));
            }
        }
    }

    #[test]
    fn bounded_core_minimization_matches_exhaustive_three_train_optimum() {
        let problem = Problem {
            name: "core-minimization-three-train".to_string(),
            trains: (0..3).map(|_| Train { visits: vec![
                Visit { resource_id: 0, earliest: 0, aimed: Some(0), travel_time: 2 },
            ] }).collect(),
            conflicts: vec![(0,0)],
        };
        let mut observed_checks = 0;
        let mut observed_exhaust_checks = 0;
        for objective in [DelayCostType::Continuous, DelayCostType::FiniteSteps123,
                          DelayCostType::InfiniteSteps180] {
            let mut optimum = i32::MAX;
            for a in 0..=6 { for b in 0..=6 { for c in 0..=6 {
                if let Some(cost) = problem.verify_solution(
                    &vec![vec![a,a+2],vec![b,b+2],vec![c,c+2]], objective,
                ) { optimum = optimum.min(cost); }
            } } }
            for checks in [0,4] {
                let mut settings = MaxSatDddLadderScSettings::default();
                settings.resource_orders = true;
                settings.order_transitivity = true;
                settings.core_minimize_checks = checks;
                let (solution, stats) = solve_with_settings(
                    &quiet_env, satcoder::solvers::minisat::Solver::new(),
                    &problem, 30.0, objective, settings, |_,_| {},
                ).unwrap();
                assert_eq!(problem.verify_solution(&solution, objective),Some(optimum));
                assert!(stats.core_minimize_calls <= checks*stats.n_unsat);
                if checks == 0 { assert_eq!(stats.core_minimize_calls,0); }
                observed_checks += stats.core_minimize_calls;
            }
            for conflicts in [1,1000] {
              for exhaust_checks in [0,4] {
                let mut settings=MaxSatDddLadderScSettings::default();
                settings.resource_orders=true;
                settings.order_transitivity=true;
                settings.core_minimize_checks=4;
                settings.core_minimize_conflicts=conflicts;
                settings.core_exhaust_checks=exhaust_checks;
                let (solution,stats)=solve_with_settings(
                    &quiet_env,crate::solvers::util::minisat_deadline::Solver::new(30.0),
                    &problem,30.0,objective,settings,|_,_| {},
                ).unwrap();
                assert_eq!(problem.verify_solution(&solution,objective),Some(optimum));
                if exhaust_checks==0 { assert_eq!(stats.core_exhaust_calls,0); }
                assert!(stats.core_exhaust_steps<=stats.core_exhaust_calls);
                observed_exhaust_checks += stats.core_exhaust_calls;
              }
            }
            for checks in [0,4] {
                let mut settings = MaxSatDddLadderScSettings::default();
                settings.resource_orders = true;
                settings.order_transitivity = true;
                settings.core_minimize_checks = checks;
                let (solution, _) = solve_with_settings(
                    &quiet_env, satcoder::solvers::cadical::Solver::new(),
                    &problem, 30.0, objective, settings, |_,_| {},
                ).unwrap();
                assert_eq!(problem.verify_solution(&solution, objective), Some(optimum));
            }
        }
        assert!(observed_checks > 0, "test must exercise the extra SAT queries");
        assert!(observed_exhaust_checks > 0, "test must exercise native cardinality-floor queries");
    }

    #[test]
    fn bounded_core_trimming_matches_exhaustive_three_train_schedules() {
        let problem=Problem {
            name:"bounded-core-trimming".into(),
            trains:(0..3).map(|_|Train {visits:vec![Visit {
                resource_id:0, earliest:0, aimed:Some(0), travel_time:2,
            }]}).collect(),
            conflicts:vec![(0,0)],
        };
        let mut observed_checks=0;
        for objective in [DelayCostType::Continuous,DelayCostType::FiniteSteps123,
                          DelayCostType::InfiniteSteps180] {
            let mut optimum=i32::MAX;
            for a in 0..=6 {for b in 0..=6 {for c in 0..=6 {
                if let Some(cost)=problem.verify_solution(
                    &vec![vec![a,a+2],vec![b,b+2],vec![c,c+2]],objective) {
                    optimum=optimum.min(cost);
                }
            }}}
            for budget in [1,100] {for checks in [0,3] {
                let mut settings=MaxSatDddLadderScSettings::default();
                settings.resource_orders=true;settings.order_transitivity=true;
                settings.core_minimize_checks=4;settings.core_minimize_conflicts=budget;
                settings.core_exhaust_checks=4;settings.core_trim_checks=checks;
                let (solution,stats)=solve_with_settings(
                    &quiet_env,crate::solvers::util::minisat_deadline::Solver::new(30.0),
                    &problem,30.0,objective,settings,|_,_|{},
                ).unwrap();
                assert_eq!(problem.verify_solution(&solution,objective),Some(optimum));
                assert!(stats.core_trim_calls<=checks*stats.n_unsat);
                if checks==0 {assert_eq!(stats.core_trim_calls,0);}
                observed_checks+=stats.core_trim_calls;
            }}
        }
        assert!(observed_checks>0,"test must exercise whole-core trimming");
    }

    #[test]
    fn intrinsic_am1_reweighting_matches_all_sat_assignments() {
        let mut solver=crate::solvers::util::minisat_deadline::Solver::new(30.0);
        let a=solver.new_var();let b=solver.new_var();let c=solver.new_var();
        for pair in [[a,b],[a,c],[b,c]] {solver.add_clause(vec![!pair[0],!pair[1]]);}
        assert!(matches!(solver.solve_with_assumptions([a,b]),satcoder::SatResultWithCore::Unsat(_)));
        let mut soft=HashMap::from([(a,(Soft::Primary,2,2)),(b,(Soft::Primary,3,3)),(c,(Soft::Primary,4,4))]);
        let mut settings=MaxSatDddLadderScSettings::default();settings.am1_checks=16;
        settings.core_minimize_conflicts=100;
        let mut bound=0;let mut stats=SolveStats::default();let mut elapsed=Duration::ZERO;
        assert!(adapt_intrinsic_am1(&mut solver,&mut soft,&[a,b],settings,&mut bound,
            &mut stats,&mut elapsed,Instant::now(),30.0).unwrap());
        assert_eq!(bound,4);assert_eq!(stats.am1_groups,1);assert_eq!(stats.am1_literals,3);
        for mask in [0usize,1,2,4] {
            let assumptions=[a,b,c].into_iter().enumerate().map(|(i,lit)|if mask&(1<<i)!=0{lit}else{!lit});
            let model=match solver.solve_with_assumptions(assumptions) {
                satcoder::SatResultWithCore::Sat(model)=>model,_=>panic!("allowed AM1 assignment was removed"),
            };
            let original=[2usize,3,4].into_iter().enumerate().filter(|(i,_)|mask&(1<<i)==0).map(|(_,w)|w).sum::<usize>();
            let transformed=bound as usize+soft.iter().filter(|(lit,_)|!model.value(*lit)).map(|(_,(_,w,_))|w).sum::<usize>();
            assert_eq!(original,transformed);
        }
        let mut unequal=HashMap::from([(a,(Soft::Primary,5,5)),(b,(Soft::Primary,7,7)),(c,(Soft::Primary,1,1))]);
        let mut unchanged_bound=0;let mut unchanged_stats=SolveStats::default();
        assert!(!adapt_intrinsic_am1(&mut solver,&mut unequal,&[a,b],settings,&mut unchanged_bound,
            &mut unchanged_stats,&mut elapsed,Instant::now(),30.0).unwrap());
        assert_eq!(unchanged_bound,0);assert_eq!(unequal.len(),3);
        assert_eq!(unequal[&a].1,5);assert_eq!(unequal[&b].1,7);assert_eq!(unequal[&c].1,1);
    }

    #[test]
    fn bounded_intrinsic_am1_matches_exhaustive_schedules() {
        let problem=Problem {name:"intrinsic-am1-schedules".into(),
            trains:(0..3).map(|_|Train {visits:vec![Visit {resource_id:0,earliest:0,aimed:Some(0),travel_time:2}]}).collect(),
            conflicts:vec![(0,0)]};
        for objective in [DelayCostType::Continuous,DelayCostType::FiniteSteps123,DelayCostType::InfiniteSteps180] {
            let mut optimum=i32::MAX;
            for a in 0..=6 {for b in 0..=6 {for c in 0..=6 {
                if let Some(cost)=problem.verify_solution(&vec![vec![a,a+2],vec![b,b+2],vec![c,c+2]],objective) {
                    optimum=optimum.min(cost);
                }
            }}}
            for budget in [1,100] {for checks in [0,16] {
                let mut settings=MaxSatDddLadderScSettings::default();
                settings.resource_orders=true;settings.order_transitivity=true;
                settings.core_minimize_checks=4;settings.core_minimize_conflicts=budget;
                settings.core_exhaust_checks=4;settings.am1_checks=checks;
                let (solution,stats)=solve_with_settings(&quiet_env,
                    crate::solvers::util::minisat_deadline::Solver::new(30.0),
                    &problem,30.0,objective,settings,|_,_|{}).unwrap();
                assert_eq!(problem.verify_solution(&solution,objective),Some(optimum));
                assert!(stats.am1_calls<=checks*stats.n_unsat);
                if checks==0 {assert_eq!(stats.am1_groups,0);assert_eq!(stats.am1_calls,0);}
            }}
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
