Task 1: complete (commits 79edc20, review clean)
Task 2: complete (commits bf8719d, 8214464; review approved; focused and full regression passed)
Task 3: complete (vernier standardization contract, structured curves, UI reuse, focused regression passed)
Task 4: complete (sample exporter, six-image export, README and project manual updates)
Task 5: complete (121 tests passed, 5 subtests; compileall and diff check passed; 49-image readings identical to baseline)

Verification:
- Full suite: 120 passed, 5 subtests passed.
- Final full suite after review fixes: 121 passed, 5 subtests passed.
- Batch baseline comparison: `debug_tupian_batch_evaluation_20260813_research_audit_v2` vs `debug_tupian_batch_evaluation_20260814_standardization`; changed reading/main/vernier/zero fields: 0.
- Metrics unchanged: 28/48 within 0.02 mm, 43/48 within 0.10 mm, 46/48 within 0.50 mm, MAE 3.5967 mm.
- Standardization exports: `debug_tupian_standardization_20260814`.
