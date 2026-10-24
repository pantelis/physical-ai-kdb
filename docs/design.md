# The VLA profile

The checks themselves are [aegean-ai/kdb-tools](https://github.com/aegean-ai/kdb-tools). Its
[`docs/design.md`](https://github.com/aegean-ai/kdb-tools/blob/main/docs/design.md) describes the
bundle layout, how paths and bbox coordinates are read, every rule `okf-validate`, `okf-ground`
and `okf-diff` check for any kDB, and the ontology machinery. This repository is the profile for
the Physical AI kDB project: the rules for its own page types and its seed ontology.

## Rules

`okf-validate` checks these on every page, after the rules of kdb-tools.

| Rule | Level | Check |
|---|---|---|
| `project.result` | error | a `Result` page has `conditions` with `task`, `benchmark`, `suite`, `trials` and `embodiment` |
| `project.condition` | error | each of `task`, `benchmark`, `suite`, `embodiment` and, when present, `perturbation` is the path of a Term page under `/ontology/<domain>/`; so is a page's `model_class` when it has one |
| `project.dataset` | error | a `Dataset` page has a non-empty `collection` of terms from the `datasets` ontology or one that extends it, and its `embodiments`, `tasks` and `modalities`, when present, are Term paths |
| `project.trained-on` | error | each `trained_on` entry has a `dataset` that is a `Dataset` page, a `role` term from the `datasets` ontology or one that extends it, and a `source` that is a source id on the same page |

## The seed ontology

The seed ships as three specs in `src/physical_ai_kdb/seeds/`. `robotics.yaml` covers tasks,
benchmarks and suites, robots, perturbations and the vision-language-action model class.
`datasets.yaml` covers how any dataset is collected and the roles a dataset plays in training.
`vla-datasets.yaml` extends `datasets` for robot learning data: teleoperation is a kind of
human-collected data, cross-embodiment pooling a kind of pooled data, LoRA fine-tuning a kind of
fine-tuning.
