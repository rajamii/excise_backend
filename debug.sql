
SELECT 
    src.our_ref_no,
    src.status,
    src.approval_date,
    NOW() AS current_db_time,
    (NOW() - INTERVAL '1 minute') AS cutoff_time,
    (src.approval_date < (NOW() - INTERVAL '1 minute')) AS is_expired,
    (SELECT status_name FROM status_master WHERE status_code = 'RV_18') AS target_status_value,
    EXISTS (
        SELECT 1 
        FROM ena_revalidation_detail target 
        WHERE target.our_ref_no = src.our_ref_no
    ) AS already_exists_target
FROM ena_requisition_detail src
WHERE src.status = 'Approved';