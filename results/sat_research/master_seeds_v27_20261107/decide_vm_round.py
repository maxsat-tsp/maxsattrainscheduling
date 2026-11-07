from pathlib import Path
import json,sys
sys.path.insert(0,'quick_scripts/analyze')
import targeted_order_cycles as t
import extended_timeout_experiments as e
reference=Path('/home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling/results/aglr/core-exhaust-v17-full216')
trial=Path('/home/tuyenkv/projects/master-batch-v26/maxsattrainscheduling/results/aglr/master-batch-v26-unresolved300')
r=t.audit_saved(trial,reference)
assert r['complete'] and not r['errors'],'V26 has not completed cleanly; inspect before changing method'
root=Path('results/aglr/master-seeds-v27-decision');root.mkdir(parents=True,exist_ok=True)
e.save(root/'decision.json',dict(v26_completed_runs=r['completed_runs'],v26_gains=r['newly_solved'],run_seeds=not bool(r['newly_solved']),
 preceding_report_sha256=e.focus.sha(trial/'order_master_batch_audit.json'),
 reason='Only seed initial cost paths if complete audited V26 has no gain; otherwise finish its confirmations and regressions.'))
if r['newly_solved']:
 print('V26 has gains; keep the existing method and followup, do not run V27.',flush=True)
 sys.exit(0)
print('V26 completed without gains; proceed with the single-component initial-cost seed contrast.',flush=True)
