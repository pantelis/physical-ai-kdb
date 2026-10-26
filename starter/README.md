# Starter for your kDB agent

Copy this directory into your own project repository to start your agent. It holds the plumbing
that every solution needs, so you can spend your time on reading papers well.

```bash
cp -r starter/ ../my-kdb-agent && cd ../my-kdb-agent
cp kdb.toml.example kdb.toml     # point it at your model server
uv sync
uv run pytest                    # no model server: a scripted model stands in for it
uv run kdb lake init --team team-7
uv run okf-seed kdb              # the term ontologies; needs the ten papers listed below
uv run kdb ingest kdb/papers/2406.09246.pdf
```

The first test run downloads the DuckLake extension for DuckDB, so it needs the network once.

Use your team id in place of `team-7`, or your own id if you work alone. It goes into the IRI of every row you
write, so use lowercase letters, digits and hyphens.

`okf-seed` defines each term with a sentence it quotes from a library paper, so it needs these ten
papers in `kdb/papers/`, each saved as `<arxiv-id>.pdf` at the version the project page links:
2112.03227, 2306.03310, 2307.15818, 2308.12952, 2310.08864, 2405.05941, 2405.12213, 2410.24164,
2502.19645 and 2510.13626. The last one is the paper you ingest last. The seed quotes it, but no
row may cite it before Submission 2. The project page lists the papers by name.

## Where things live

Your kDB holds types. These are the classes, their properties and the ontology terms, written as
pages in `kdb/`. Your lake holds everything else. Each paper, model, dataset, training link and
result is a row in a table, and each PDF is a file in the lake's media table. A row cites its
evidence as a MediaRef: the sha256 of the PDF, the page, the bbox and the quote.

Every change goes through a typed action, and each action is logged in the lake. `RegisterMedia`
adds a file. `UpsertObjects` writes rows. `okf-validate` reports a page that changed outside an
action, and `okf-diff --snapshots` reports a row that changed outside one.

## Setting up the lake

`kdb lake init --team <team>` makes a lake you can use at once. It adds a `[lake]` table to
`kdb.toml`, with a catalog file in `lake/` and a data folder next to it. It writes `compose.yml`
for RustFS. It creates the action log and the media table, seeds the core and VLA ontologies, and
binds each VLA class to its table. Running it again changes nothing that is already in place.

Paths in `kdb.toml` are relative to the folder that holds it. `kdb` finds `kdb.toml` in the
current folder or a folder above it, so you can run it from anywhere in your project.
`okf-validate` and `okf-ground` search from the bundle you name instead: they use the `kdb.toml`
in that folder or the nearest folder above it, wherever you run them.

The local lake needs nothing else, and the tests use it. If you want S3 storage, you can run
RustFS in Docker on your own machine instead. Choose this before your first `lake init`, as
`kdb.toml.example` explains. The first `lake init` writes `compose.yml` and then stops, because
RustFS is not running yet. Start it with `docker compose up -d`, create the bucket that `data_path`
names, and run `lake init` again. The RustFS key and secret come from the environment variables
that `kdb.toml` names in `key_env` and `secret_env`. `compose.yml` uses local defaults when they are not
set, and it opens its ports only on your own machine. Never run `docker compose down -v`, because
it deletes the volume that holds your data.

You never need a cloud credential. Nothing in this starter reads one.

## The model server

`kdb_tools.config` reads the server's `base_url`, the model name and its context size from
`kdb.toml`. It builds a Pydantic AI model for any OpenAI-compatible server, either a local one or
OpenRouter. For OpenRouter, set `api_key_env` to the name of the environment variable that holds
your key, such as `OPENROUTER_API_KEY`. A key written in `kdb.toml` is refused, so it cannot end up
in a commit. Use a free model or set a credit limit on the key.

`reasoning_effort = "none"` stops a model such as Gemma 4 from writing hidden reasoning before
every answer, which makes each answer several times faster. Remove it for a model where reasoning
helps. We grade your agent against our own server by changing this file, so keep every server
setting in it.

`kdb_tools.guard` refuses a prompt that would not fit the context. A server that receives a
longer prompt cuts it without an error, and the model then answers from what is left.

## What the starter does

`kdbagent/ingest.py` registers the PDF with `RegisterMedia`. It then reads the paper three pages
at a time with the kdb-tools extraction agent and collects your typed facts. A `Fact` is a
`kdb_tools.agent.Quote`, so the agent looks up every quote on the page the model named. It sends
the ones it cannot find back to the model to fix. The agent also has the kdb-tools tools
`find_quote`, `find_value`, `find_cell` and `check_pages`, so the model can look a quote up before
it answers. After `write_rows`, ingest runs `okf-validate` and `okf-ground` on the rows it wrote
and on nothing else, so an error that an earlier ingest left does not fail this one.

`kdbagent/ask.py` builds an agent that reads rows with three tools: `list_classes`,
`query_objects` and `get_object`. Each claim in its answer names a row and the entries of that
row's evidence that support it. The validator sends back a claim whose row or evidence entry does
not exist. The ask agent has no action tools, so it cannot change the lake.

`kdbagent/lake.py` holds `lake init` and `open_context`, which gives every command the Context
that actions run in.

`kdbagent/cli.py` is the `kdb` command, with `lake init`, `ingest`, `ask`, `export` and `history`.

## What is yours

`write_rows` turns the facts into rows, and it raises `NotImplementedError` until you write it.
Write each row with `UpsertObjects`. Call `dry_run` first to see the rows it would write and what
it refuses, then `submit` that plan. Every Result states its conditions as ontology terms. Every
row cites its evidence with a bbox from `kdb_tools.locate.find_quote`. Highlight each quote with
`kdb_tools.annotate.highlight` and register the highlighted copy with `RegisterMedia`, giving
`annotates` the sha256 of the paper. A highlight passes when any registered annotated copy
has it, so register the copy again each time you add highlights. One entity gets one row, and its aliases go on that row.
Contested claims are rows too. The instructions and the chunking are yours to improve.

For `ask`, `query_objects` compares columns with plain equality and returns at most 50 rows unless
you ask for more. Add tools that search: by condition term, by benchmark, or with SQL over the
tables. Printing the citations, `--show`, `--save` and the SQLite history are yours too. `kdb
history` says so until you write them.

## Submitting

`kdb export <folder>` writes your lake into a folder: the catalog file, the data files, every media
file and a manifest with the sha256 of each. Export into your team's shared Google Drive folder.
The course restores it with `okf-restore`, which checks every hash before it reads anything.
Export the lake at the commit of your kDB that you submit.

The project page lists everything the kDB and the program must do, and how they are graded.
