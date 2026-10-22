# Physical AI Wiki

Student project for Introduction to AI. The project page on aegean.ai describes the task:
compile a library of 30 physical AI papers into a grounded wiki in the
[Open Knowledge Format (OKF) v0.2](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md),
then ingest one held-out paper and keep the wiki correct.

This repository will hold the tools you use to check your work, the same ones used for grading:

- `okf-validate`: checks that a directory is a valid OKF v0.2 bundle under the project's rules.
- `okf-ground`: checks that every cited sentence appears on its cited page and every cited table cell holds its cited value.
- `okf-diff`: compares two versions of a bundle and lists every page that changed.

The tools are not written yet.
