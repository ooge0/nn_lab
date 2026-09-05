# Test Report

Total tests: 29


| # | Test Name | Description |
|---|-----------|-------------|
| 1 | test_full_pipeline_alignment | Ensures raw JSON data correctly flows through the Bridge into the Schema and finally into a DataFrame with the exact keys required by Plotly. |
| 2 | test_alias_regression_check | Verify that providing 'neuro_self_focus' directly works and isn't ignored in favor of an old 'self_focus' alias. |
| 3 | test_schema_parsing | Validate that LabSchema can parse the flattened data correctly. |
| 4 | test_dataframe_build | Ensure the build_dataframe function creates columns and retains data. |
| 5 | test_no_nan_critical | Check for missing values in critical numeric columns. |
| 6 | test_pos_mapping | Verify the POS distribution is flattened correctly for Ternary plots. |
| 7 | test_neuro_fields_prefixed | Verify that psychological fields use the 'neuro_' prefix in the DF. |
| 8 | test_load_knowledge_base_error_handling | Verify engine raises correct errors for missing or empty paths. |
| 9 | test_metadata_integrity | Best Practice: Ensure archetype label is correctly mapped from filename. |
| 10 | test_retrieval_isolation_negative | Critical Test: Ensure that asking for a archetype that exists returns data, but asking for one that doesn't returns an empty list (Isolation check). |
| 11 | test_chunk_granularity | Verify that every line in a file is treated as a unique chunk. |
| 12 | test_query_before_load_safety | Ensure the app doesn't crash if a user triggers a query before RAG is loaded. |
| 13 | test_chunks_loaded | Ensure the knowledge base is not empty after ingestion. |
| 14 | test_all_archetypes_present | Ensure all expected archetype categories exist in the loaded dataset. |
| 15 | test_valid_domains | Ensure all ingested chunks adhere to the allowed domain labels (schema validation). |
| 16 | test_no_empty_chunks | Safety check: Ensure no empty or broken content chunks were ingested. |
| 17 | test_chunk_length_quality | Quality Gate: Ensure chunks are not degenerate (too short to provide context). Allow max 10% of short chunks if they are specific triggers. |
| 18 | test_retrieval_returns_results | Verify that the vector store (e.g., FAISS) returns valid results for a basic query. |
| 19 | test_paranoid_signal_retrieval | Semantic test: Ensure a query with strong paranoid keywords returns paranoid-tagged content. |
| 20 | test_retrieval_boundary_isolation | Isolation test: Ensure a query for 'Structured' traits does not leak 'Expressive' content. Prevents cross-contamination in the vector space. |
| 21 | test_cosine_alignment_integrity | Validate that the embedding model correctly ranks semantic similarity. Reference RAG chunk should have higher similarity to a relevant query than to noise. |
| 22 | test_weighted_drift_calculation | Validate the Drift Index formula. Checks if the system correctly identifies 'Out of Character' responses based on weighted attributes. |
| 23 | test_retrieval_sanity_loop | Comprehensive smoke test for a variety of archetype queries. Prints retrieval details for manual inspection during debugging. |
| 24 | test_feature_correlation_consistency | Structural Integrity Check: Ensures that the correlation between traits in the model output matches the correlation structure of the 'Ground Truth' dataset. This detects 'Psychological Chimera'—responses where individual scores might seem okay, but the combination of traits is logically impossible for the given archetype. |
| 25 | test_filtered_semantic_retrieval_old | Test that filtering correctly isolates the target archetype even when 'baseline' has similar semantic content. |
| 26 | test_filtered_semantic_retrieval | Description is missing |
| 27 | test_unfiltered_retrieval_ranking | Debug test: See what is actually coming back first when unfiltered. |
| 28 | test_empty_query_handling | Ensure the system doesn't crash on empty or nonsensical input. |

Summary line: 28 tests collected in 0.16s