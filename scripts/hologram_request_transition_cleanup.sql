BEGIN;

WITH required_transitions(from_stage_id, to_stage_id, action_name) AS (
    VALUES
        (82, 86, 'issue'),
        (86, 85, 'complete')
)
DELETE FROM public.workflow_workflowtransition AS t
WHERE t.workflow_id = 7
  AND (
      lower(COALESCE(t.condition ->> 'action', '')) = 'view'
      OR NOT EXISTS (
          SELECT 1
          FROM required_transitions AS r
          WHERE t.from_stage_id = r.from_stage_id
            AND t.to_stage_id = r.to_stage_id
            AND lower(COALESCE(t.condition ->> 'action', '')) = r.action_name
      )
  );

COMMIT;

-- Verify remaining transitions for workflow_id=7
SELECT
    id,
    condition,
    from_stage_id,
    to_stage_id,
    workflow_id
FROM public.workflow_workflowtransition
WHERE workflow_id = 7
ORDER BY id ASC;
