# The VLA profile

The checks themselves are [aegean-ai/kdb-tools](https://github.com/aegean-ai/kdb-tools). Its
[`docs/design.md`](https://github.com/aegean-ai/kdb-tools/blob/main/docs/design.md) describes the
bundle layout, how paths and bbox coordinates are read, every rule `okf-validate`, `okf-ground`
and `okf-diff` check for any kDB, and the ontology machinery. This repository is the profile for
the Physical AI kDB project: the VLA classes, the rules for their rows, and the seed ontologies.

The kDB holds types only. Papers, models, datasets, training links, results, contested claims,
computations and analyses are rows of lake tables, one table per VLA class in `seeds/vla.yaml`.
The starter's `kdb lake init` sets this up in one step. It seeds the core ontology and `vla.yaml`
through the SeedOntology action, then calls `physical_ai_kdb.bind_tables`, which runs the BindTable
action for each class, because only an action may create a table. (`okf-seed kdb --core` and
`okf-seed kdb` write the same pages as separate commands, and `okf-seed kdb` also writes the Term ontologies.)
Condition columns, `model_class`, `role` and the dataset lists hold Term IRIs.

Row IRIs start with the lake's `iri_base`, `https://data.aegean.ai/vla/<team>/` for a team. The
evidence column of every class is a list of MediaRefs: the sha256 of a registered PDF with a page,
a bbox, and a quote or a table value. okf-ground checks each one against the PDF and against the
highlights in the registered copy that annotates it.

## Rules

`okf-validate` checks these when it has a lake, after the rules of kdb-tools. A finding's path is
`<table>/<row iri>`. When a type breaks `project.iri`, the path is the type's page.

| Rule | Level | Check |
|---|---|---|
| `project.result` | error | a `results` row has `task`, `benchmark`, `suite` and `embodiment`, and `trials` unless `trials_reported` is false |
| `project.condition` | error | each of `task`, `benchmark`, `suite`, `embodiment` and, when set, `perturbation` is the IRI of a Term of the `robotics` ontology or one that extends it; so is a model's `model_class` when it has one |
| `project.dataset` | error | a `datasets` row has a non-empty `collection` of terms from the `datasets` ontology or one that extends it, and its `embodiments`, `tasks` and `modalities`, when set, are Term IRIs |
| `project.trained-on` | error | a `trained_on` row has a `model` that is a row of `models`, a `dataset` that is a row of `datasets`, a `role` term from the `datasets` ontology or one that extends it, and non-empty `evidence` |
| `project.entity` | error | no two rows of `papers`, `models` and `datasets` share a title or alias, compared after normalizing |
| `project.iri` | error | every row IRI starts with the lake's `iri_base`, and every type page that the seeds did not write has an IRI under `https://kdb.aegean.ai/vla/<team>/` |

## The seed ontology

The Term seeds ship as three specs in `src/physical_ai_kdb/seeds/`, beside `vla.yaml`. Their
quotes come from ten library papers, which `okf-seed` needs in `kdb/papers/`: 2112.03227,
2306.03310, 2307.15818, 2308.12952, 2310.08864, 2405.05941, 2405.12213, 2410.24164, 2502.19645
and 2510.13626. Each has a `base_iri` of `https://kdb.aegean.ai/<domain>/`, so every Term page gets an IRI. `robotics.yaml` covers tasks,
benchmarks and suites, robots, perturbations and the vision-language-action model class.
`datasets.yaml` covers how any dataset is collected and the roles a dataset plays in training.
`vla-datasets.yaml` extends `datasets` for robot learning data: teleoperation is a kind of
human-collected data, cross-embodiment pooling a kind of pooled data, LoRA fine-tuning a kind of
fine-tuning.
