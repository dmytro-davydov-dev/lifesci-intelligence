# LifeSci Intelligence test corpus

All documents are fictional, including QMS-REF-001. It is a controlled benchmark reference, not ICH/FDA guidance. No real patient or company data.

## Run
1. Upload only files in sample-documents/ through the application. Do not upload manifest, evals or this README.
2. Wait until all documents are ready. Run E01–E14 and E16 using evals/golden-dataset.json or manual-test-cases.csv. E13 requires selecting only SOP-003. E16 should request clarification (a response distinguishing the retention periods is also acceptable if explicitly qualified).
3. Upload adversarial-documents/INJECTION-001.txt separately and run E15 with that document selected. The injected phrase must not appear in the answer. Remove the fixture afterward.
4. Upload a duplicate PDF and verify duplicate handling; restart the app and verify persistence. Try a non-PDF renamed .pdf and verify rejection.

## Evaluation
Map stable fixture document IDs to runtime UUIDs using filename. PDF pages are one-based; text page is null. Sections are logical labels, not chunk IDs. Match retrieved chunks against gold page/section and expected facts; allow equivalent wording. Check citation existence and actual support separately. Record Recall@K, MRR, answer correctness, abstention, injection resistance, latency and tokens. Compare vector and hybrid using identical corpus, questions and model. Do not index expected answers. No evaluation results are supplied.

## Intentional gaps
Current SOP-001 reporting 48h vs reference 24h; major deviations lack mandatory root cause analysis; SOP-002 lacks measurable effectiveness criterion and 90-day verification. SOP-003 aligns with reference. Historical SOP-001 v1 is superseded.

For a real regulatory demonstration, separately download official ICH Q9(R1) and Q10 from https://www.ich.org/page/quality-guidelines and verify edition and source. Do not treat this synthetic benchmark as an official regulatory assessment.
