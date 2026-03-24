BEGIN;

-- Keep only the required transitions for workflow_id = 6 (Hologram Procurement)
-- and remove redundant VIEW/self-loop or any other obsolete rows.
WITH required AS (
    SELECT from_id, to_id
    FROM (VALUES
        (75, 76), -- Submitted -> Under IT Cell Review
        (76, 77), -- Under IT Cell Review -> Forwarded to Commissioner
        (77, 78), -- Forwarded to Commissioner -> Approved by Commissioner
        (77, 79), -- Forwarded to Commissioner -> Rejected by Commissioner
        (78, 80), -- Approved by Commissioner -> Payment Completed
        (80, 81)  -- Payment Completed -> Cartoon Assigned
    ) AS t(from_id, to_id)
)
DELETE FROM public.workflow_workflowtransition wt
WHERE wt.workflow_id = 6
  AND (
    COALESCE(LOWER(wt.condition->>'action'), '') = 'view'
    OR NOT EXISTS (
      SELECT 1
      FROM required r
      WHERE r.from_id = wt.from_stage_id
        AND r.to_id = wt.to_stage_id
    )
  );

COMMIT;
