//! Pure selection logic for Adaptive Growth-Limited Refinement (AGLR).
//!
//! The solver-specific code detects conflicts and turns them into the small,
//! solver-independent records in this module.  Keeping selection pure makes
//! its budget, ageing, and tie-breaking rules directly testable.

use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};

use super::settings::{AglrSettings, RefinementPolicy};

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub(super) struct VisitTime {
    pub visit: u32,
    pub time: i32,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub(super) enum ConflictKey {
    Travel { from: u32, to: u32 },
    Resource { first: u32, second: u32 },
}

impl ConflictKey {
    pub fn resource(a: u32, b: u32) -> Self {
        let (first, second) = if a <= b { (a, b) } else { (b, a) };
        Self::Resource { first, second }
    }
}

#[derive(Clone, Debug)]
pub(super) struct Candidate {
    pub key: ConflictKey,
    pub points: Vec<VisitTime>,
}

impl Candidate {
    fn unique_points(&self) -> BTreeSet<VisitTime> {
        self.points.iter().copied().collect()
    }
}

#[derive(Clone, Copy, Debug, Default)]
struct HistoryEntry {
    age: usize,
    recurrence: usize,
    pending: bool,
}

#[derive(Clone, Debug, Default)]
pub(super) struct CandidateHistory {
    entries: BTreeMap<ConflictKey, HistoryEntry>,
}

impl CandidateHistory {
    fn observe(&mut self, candidates: &[Candidate]) -> BTreeMap<ConflictKey, HistoryEntry> {
        let seen = candidates
            .iter()
            .map(|candidate| candidate.key)
            .collect::<BTreeSet<_>>();

        for (key, entry) in self.entries.iter_mut() {
            if !seen.contains(key) {
                entry.pending = false;
                entry.age = 0;
            }
        }

        for key in seen {
            let entry = self.entries.entry(key).or_default();
            entry.recurrence += 1;
            entry.age = if entry.pending { entry.age + 1 } else { 0 };
            entry.pending = true;
        }

        self.entries.clone()
    }

    fn mark_selected(&mut self, key: ConflictKey) {
        if let Some(entry) = self.entries.get_mut(&key) {
            entry.pending = false;
            entry.age = 0;
        }
    }
}

#[derive(Clone, Debug, Default, PartialEq)]
pub(super) struct Selection {
    pub indices: Vec<usize>,
    pub all_growth: usize,
    pub selected_growth: usize,
    pub budget: usize,
    pub mandatory: usize,
    pub max_age: usize,
    pub rescued: bool,
}

fn marginal_growth(
    candidate: &Candidate,
    existing: &HashSet<VisitTime>,
    selected_points: &HashSet<VisitTime>,
) -> usize {
    1 + candidate
        .unique_points()
        .into_iter()
        .filter(|point| !existing.contains(point) && !selected_points.contains(point))
        .count()
}

fn all_growth(candidates: &[Candidate], existing: &HashSet<VisitTime>) -> usize {
    let new_points = candidates
        .iter()
        .flat_map(Candidate::unique_points)
        .filter(|point| !existing.contains(point))
        .collect::<BTreeSet<_>>()
        .len();
    candidates.len() + new_points
}

fn utility(entry: HistoryEntry, shared_points: usize, max_wait: usize) -> f64 {
    let wait = max_wait.max(1);
    1.0 + (entry.age.min(wait) as f64 / wait as f64)
        + ((1 + entry.recurrence) as f64).log2()
        + ((1 + shared_points) as f64).log2()
}

/// Select candidates without mutating the SAT model.
///
/// Mandatory candidates may exceed the budget.  If the budget cannot fit any
/// candidate, one candidate is still selected so that the DDD loop progresses.
pub(super) fn select(
    candidates: &[Candidate],
    existing: &HashSet<VisitTime>,
    settings: AglrSettings,
    rescue: bool,
    history: &mut CandidateHistory,
) -> Selection {
    if candidates.is_empty() {
        history.observe(candidates);
        return Selection::default();
    }

    let states = history.observe(candidates);
    let all_growth = all_growth(candidates, existing);
    let budget = settings
        .min_growth
        .max((settings.fraction * all_growth as f64).ceil() as usize);

    let point_frequency = candidates.iter().flat_map(Candidate::unique_points).fold(
        HashMap::<VisitTime, usize>::new(),
        |mut counts, point| {
            *counts.entry(point).or_default() += 1;
            counts
        },
    );
    let shared = candidates
        .iter()
        .map(|candidate| {
            candidate
                .unique_points()
                .iter()
                .filter(|point| point_frequency.get(point).copied().unwrap_or(1) > 1)
                .count()
        })
        .collect::<Vec<_>>();

    let mut result = Selection {
        all_growth,
        budget,
        max_age: states.values().map(|entry| entry.age).max().unwrap_or(0),
        rescued: rescue,
        ..Selection::default()
    };
    let mut selected = HashSet::<usize>::new();
    let mut selected_points = HashSet::<VisitTime>::new();

    let select_one = |idx: usize,
                      result: &mut Selection,
                      selected: &mut HashSet<usize>,
                      selected_points: &mut HashSet<VisitTime>| {
        if !selected.insert(idx) {
            return;
        }
        result.selected_growth += marginal_growth(&candidates[idx], existing, selected_points);
        selected_points.extend(candidates[idx].unique_points());
        result.indices.push(idx);
    };

    if settings.policy == RefinementPolicy::AllScanned || rescue {
        let mut order = (0..candidates.len()).collect::<Vec<_>>();
        order.sort_by_key(|&idx| candidates[idx].key);
        for idx in order {
            select_one(idx, &mut result, &mut selected, &mut selected_points);
        }
    } else {
        let mut mandatory = (0..candidates.len())
            .filter(|&idx| states[&candidates[idx].key].age >= settings.max_wait)
            .collect::<Vec<_>>();
        mandatory.sort_by_key(|&idx| candidates[idx].key);
        result.mandatory = mandatory.len();
        for idx in mandatory {
            select_one(idx, &mut result, &mut selected, &mut selected_points);
        }

        loop {
            let best = (0..candidates.len())
                .filter(|idx| !selected.contains(idx))
                .map(|idx| {
                    let growth = marginal_growth(&candidates[idx], existing, &selected_points);
                    let score =
                        utility(states[&candidates[idx].key], shared[idx], settings.max_wait)
                            / growth as f64;
                    (idx, growth, score)
                })
                .filter(|(_, growth, _)| result.selected_growth + *growth <= budget)
                .max_by(|left, right| {
                    left.2
                        .total_cmp(&right.2)
                        .then_with(|| candidates[right.0].key.cmp(&candidates[left.0].key))
                });

            let Some((idx, growth, _)) = best else {
                break;
            };
            debug_assert!(result.selected_growth + growth <= budget);
            select_one(idx, &mut result, &mut selected, &mut selected_points);
        }

        if result.indices.is_empty() {
            let best = (0..candidates.len())
                .map(|idx| {
                    let growth = marginal_growth(&candidates[idx], existing, &selected_points);
                    let score =
                        utility(states[&candidates[idx].key], shared[idx], settings.max_wait)
                            / growth as f64;
                    (idx, score)
                })
                .max_by(|left, right| {
                    left.1
                        .total_cmp(&right.1)
                        .then_with(|| candidates[right.0].key.cmp(&candidates[left.0].key))
                })
                .unwrap();
            select_one(best.0, &mut result, &mut selected, &mut selected_points);
        }
    }

    for &idx in &result.indices {
        history.mark_selected(candidates[idx].key);
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;

    fn point(visit: u32, time: i32) -> VisitTime {
        VisitTime { visit, time }
    }

    fn candidate(key: ConflictKey, points: &[(u32, i32)]) -> Candidate {
        Candidate {
            key,
            points: points
                .iter()
                .map(|&(visit, time)| point(visit, time))
                .collect(),
        }
    }

    fn adaptive(min_growth: usize, fraction: f64, max_wait: usize) -> AglrSettings {
        AglrSettings {
            policy: RefinementPolicy::Adaptive,
            min_growth,
            fraction,
            max_wait,
        }
    }

    #[test]
    fn growth_counts_each_clause_and_each_distinct_new_point_once() {
        let candidates = vec![
            candidate(ConflictKey::Travel { from: 0, to: 1 }, &[(1, 10), (2, 20)]),
            candidate(ConflictKey::resource(2, 3), &[(2, 20), (3, 30)]),
        ];
        let existing = HashSet::from([point(1, 10)]);
        assert_eq!(all_growth(&candidates, &existing), 4); // 2 clauses + points (2,20), (3,30)
    }

    #[test]
    fn selection_is_deterministic_and_rewards_shared_points() {
        let candidates = vec![
            candidate(ConflictKey::resource(0, 1), &[(0, 10), (1, 10)]),
            candidate(ConflictKey::resource(2, 3), &[(2, 10), (3, 10)]),
            candidate(ConflictKey::resource(1, 4), &[(1, 10), (4, 10)]),
        ];
        let mut history_a = CandidateHistory::default();
        let mut history_b = CandidateHistory::default();
        let settings = adaptive(3, 0.0, 5);
        let a = select(
            &candidates,
            &HashSet::new(),
            settings,
            false,
            &mut history_a,
        );
        let b = select(
            &candidates,
            &HashSet::new(),
            settings,
            false,
            &mut history_b,
        );
        assert_eq!(a, b);
        assert_eq!(a.indices, vec![0]);
    }

    #[test]
    fn waiting_candidate_becomes_mandatory_and_may_overflow_budget() {
        let candidates = vec![candidate(
            ConflictKey::Travel { from: 0, to: 1 },
            &[(1, 10), (2, 20), (3, 30)],
        )];
        let settings = adaptive(1, 0.0, 2);
        let existing = HashSet::new();
        let mut history = CandidateHistory::default();

        // Simulate two rounds in which the conflict was seen but not applied.
        history.observe(&candidates);
        history.observe(&candidates);
        let selection = select(&candidates, &existing, settings, false, &mut history);

        assert_eq!(selection.mandatory, 1);
        assert_eq!(selection.indices, vec![0]);
        assert!(selection.selected_growth > selection.budget);
    }

    #[test]
    fn rescue_and_all_scanned_select_every_candidate() {
        let candidates = vec![
            candidate(ConflictKey::Travel { from: 0, to: 1 }, &[(1, 10)]),
            candidate(ConflictKey::resource(2, 3), &[(2, 10), (3, 10)]),
        ];
        let existing = HashSet::new();
        let mut rescued_history = CandidateHistory::default();
        let rescued = select(
            &candidates,
            &existing,
            adaptive(1, 0.0, 5),
            true,
            &mut rescued_history,
        );
        assert_eq!(rescued.indices.len(), candidates.len());

        let mut all_history = CandidateHistory::default();
        let all = select(
            &candidates,
            &existing,
            AglrSettings {
                policy: RefinementPolicy::AllScanned,
                min_growth: 1,
                fraction: 0.0,
                max_wait: 5,
            },
            false,
            &mut all_history,
        );
        assert_eq!(all.indices.len(), candidates.len());
    }
}
