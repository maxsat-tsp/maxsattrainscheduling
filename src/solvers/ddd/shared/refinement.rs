//! Selective refinement for the DDD MaxSAT solver — Contribution 3.
//!
//! Instead of adding every discovered time point to the solver immediately,
//! we:
//!   1. Collect violations into [`RefinementPackage`]s.
//!   2. Score each package with a greedy marginal-gain criterion.
//!   3. Select the best K packages (or all, when `budget = None`).
//!   4. Apply only the selected ones to the SAT solver.
//!   5. Fallback: if selection is empty, force the oldest package in.
//!
//! # Budget parameter
//! `budget = None`  → add all (identical to baseline; use this first to
//!                    verify results match before enabling selection).
//! `budget = Some(K)` → add at most K new time points per iteration.
//!
//! Recommended test sequence: None → Some(128) → Some(32) → Some(8).

use std::collections::{HashMap, HashSet};
use satcoder::{Bool, SatInstance};
use typed_index_collections::TiVec;
use super::common::{Occ, VisitId};

// ─────────────────────────────────────────────────────────────────────────────
// Public types
// ─────────────────────────────────────────────────────────────────────────────

/// Identifies a violation uniquely for deduplication across iterations.
/// Canonical form: for Resource conflicts, smaller VisitId comes first.
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub enum ViolationId {
    TravelTime(VisitId),
    Resource(VisitId, VisitId), // always (min, max)
}

impl ViolationId {
    pub fn resource(a: VisitId, b: VisitId) -> Self {
        if usize::from(a) <= usize::from(b) {
            ViolationId::Resource(a, b)
        } else {
            ViolationId::Resource(b, a)
        }
    }
}

/// What the solver needs to do when a package is applied.
///
/// All fields are captured at **detection time** (before `time_point()` is
/// called), so the application phase is a pure mechanical step.
pub enum PackageAction<L: satcoder::Lit> {
    /// Travel-time violation: t_{next} must be ≥ t_cur + travel_time.
    TravelTime {
        /// Lit that is TRUE when the incumbent "t_cur ≥ t1_in" holds.
        t1_in_var: Bool<L>,
        next_visit: VisitId,
        /// The minimum time next_visit must start.
        new_t: i32,
    },
    /// Resource conflict: two trains overlap on the same resource.
    Resource {
        visit1: VisitId,
        visit2: VisitId,
        /// Time point to add to visit2 (= t1_out of visit1).
        tp_for_v2: i32,
        /// Time point to add to visit1 (= t2_out of visit2).
        tp_for_v1: i32,
        /// Lit: "train1 is currently occupying" (= incumbent of next_visit1).
        t1_out_lit: Bool<L>,
        /// Lit: "train2 is currently occupying" (= incumbent of next_visit2).
        t2_out_lit: Bool<L>,
    },
}

/// One refinement package: a single violation and everything needed to fix it.
pub struct RefinementPackage<L: satcoder::Lit> {
    pub violation: ViolationId,
    /// `(visit_id, time)` pairs this package will add (used for scoring).
    pub planned_points: Vec<(VisitId, i32)>,
    /// First iteration in which this violation was observed.
    pub first_seen: usize,
    pub action: PackageAction<L>,
}

// ─────────────────────────────────────────────────────────────────────────────
// Selection
// ─────────────────────────────────────────────────────────────────────────────

/// Greedy package selection.
///
/// Scores each package as:
///   score(b) = |new violations resolved| / (1 + |new time points needed|)
///
/// Selects packages one by one (highest score first) until the cumulative
/// number of new time points would exceed `budget`.
///
/// **Fallback**: if no package is selected after the greedy loop (e.g. every
/// package would immediately exceed the budget), force in the package with
/// the smallest `first_seen` value (i.e. the longest-pending violation).
/// This guarantees progress on every iteration.
///
/// Returns indices into `packages` of the selected ones.
pub fn select_packages<L: satcoder::Lit>(
    packages: &[RefinementPackage<L>],
    budget: Option<usize>,
) -> Vec<usize> {
    if packages.is_empty() {
        return vec![];
    }

    // budget = None  ⟹  select all
    let budget = match budget {
        None => return (0..packages.len()).collect(),
        Some(b) => b,
    };

    let mut selected: Vec<usize> = Vec::new();
    let mut sel_violations: HashSet<&ViolationId> = HashSet::new();
    let mut sel_points: HashSet<(VisitId, i32)> = HashSet::new();
    let mut total_new_points: usize = 0;

    // Greedy loop
    loop {
        let mut best_score = 0.0_f64;
        let mut best_idx: Option<usize> = None;

        for (i, pkg) in packages.iter().enumerate() {
            if selected.contains(&i) {
                continue;
            }

            // marginal violations this package resolves
            let new_v = if sel_violations.contains(&pkg.violation) { 0usize } else { 1 };
            if new_v == 0 {
                // violation already covered — skip
                continue;
            }

            // marginal time points this package adds
            let new_pts: usize = pkg
                .planned_points
                .iter()
                .filter(|p| !sel_points.contains(p))
                .count();

            // budget check: would adding this package exceed the limit?
            if total_new_points + new_pts > budget {
                continue;
            }

            let score = new_v as f64 / (1.0 + new_pts as f64);
            if score > best_score {
                best_score = score;
                best_idx = Some(i);
            }
        }

        match best_idx {
            None => break, // no more packages fit
            Some(i) => {
                let pkg = &packages[i];
                let new_pts: usize = pkg
                    .planned_points
                    .iter()
                    .filter(|p| !sel_points.contains(p))
                    .count();
                sel_violations.insert(&pkg.violation);
                sel_points.extend(pkg.planned_points.iter().copied());
                total_new_points += new_pts;
                selected.push(i);
            }
        }
    }

    // Fallback: ensure at least one package is always selected so that the
    // DDD loop makes progress.
    if selected.is_empty() {
        let oldest = packages
            .iter()
            .enumerate()
            .min_by_key(|(_, p)| p.first_seen)
            .map(|(i, _)| i)
            .unwrap(); // packages is non-empty, so unwrap is safe
        selected.push(oldest);
    }

    selected
}

// ─────────────────────────────────────────────────────────────────────────────
// Application
// ─────────────────────────────────────────────────────────────────────────────

/// Apply one package to the solver.
///
/// Returns the list of `(visit_id, var, time)` triples that were **newly**
/// created, ready to be pushed into `new_time_points` for cost registration.
pub fn apply_package<L: satcoder::Lit + Copy>(
    pkg: RefinementPackage<L>,
    solver: &mut impl SatInstance<L>,
    occupations: &mut TiVec<VisitId, Occ<L>>,
    n_conflict_constraints: &mut usize,
    n_conflicts: &mut usize,
    n_travel: &mut usize,
) -> Vec<(VisitId, Bool<L>, i32)> {
    let mut added = Vec::new();
    match pkg.action {
        PackageAction::TravelTime { t1_in_var, next_visit, new_t } => {
            let (out_var, is_new) = occupations[next_visit].time_point(solver, new_t);
            // t1_in_var ⟹ out_var  (if t_cur ≥ t1_in, then t_next ≥ new_t)
            solver.add_clause(vec![!t1_in_var, out_var]);
            *n_travel += 1;
            if is_new {
                added.push((next_visit, out_var, new_t));
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
            // Add time points for both sides.
            let (delay_v2, v2_new) = occupations[visit2].time_point(solver, tp_for_v2);
            let (delay_v1, v1_new) = occupations[visit1].time_point(solver, tp_for_v1);

            if v1_new { added.push((visit1, delay_v1, tp_for_v1)); }
            if v2_new { added.push((visit2, delay_v2, tp_for_v2)); }

            // AMO clause: ¬t1_out_lit ∨ ¬t2_out_lit ∨ delay_v1 ∨ delay_v2
            // "if both trains currently overlap, at least one must be pushed out"
            solver.add_clause(vec![!t1_out_lit, !t2_out_lit, delay_v1, delay_v2]);
            *n_conflict_constraints += 1;
            *n_conflicts += 1;
        }
    }
    added
}

// ─────────────────────────────────────────────────────────────────────────────
// Violation-age tracker
// ─────────────────────────────────────────────────────────────────────────────

/// Tracks the first iteration in which each violation was observed.
/// Reused across DDD iterations so `first_seen` accumulates correctly.
#[derive(Default)]
pub struct ViolationAgeTracker {
    map: HashMap<ViolationId, usize>,
}

impl ViolationAgeTracker {
    /// Record a violation at `iteration`. Returns `first_seen`.
    pub fn record(&mut self, id: ViolationId, iteration: usize) -> usize {
        *self.map.entry(id).or_insert(iteration)
    }
}
