# Starter for your kDB agent

Copy this directory into your own project repository to start your agent. It contains the
plumbing that every solution needs, so you can spend your time on reading papers well.

```bash
cp -r starter/ ../my-kdb-agent && cd ../my-kdb-agent
cp kdb.toml.example kdb.toml     # point it at your model server
uv sync
uv run pytest                    # offline: a scripted model stands in for the server
uv run kdb ingest kdb/papers/2406.09246.pdf
```

## What it does

`kdbagent/config.py` reads the server's `base_url`, the model name and its context size from
`kdb.toml`, and builds a Pydantic AI model for any OpenAI-compatible server: a local one or
OpenRouter. For OpenRouter, set `api_key_env` to the name of the environment variable that holds
your key, such as `OPENROUTER_API_KEY`. A key written in `kdb.toml` is refused, so it cannot end up
in a commit. Use a free model or set a credit limit on the key. `reasoning_effort = "none"`
stops a model such as Gemma 4 from writing hidden reasoning before every answer, which makes
each answer several times faster; remove it for a model where reasoning helps. We grade your agent against our
own server by changing this file, so keep every server setting in it.

`kdbagent/guard.py` refuses a prompt that would not fit the context. A server that receives a
longer prompt cuts it without an error, and the model then answers from what is left.

`kdbagent/ingest.py` has an agent whose output is a typed list of facts. Its output validator
looks up every quote on the page the model named, with `kdb_tools.locate.find_quote`, and sends
the ones it cannot find back to the model to fix. `ingest()` reads the paper, sends three pages
at a time and collects the facts. The agent also has the `kdb-tools` agent tools, `find_quote`,
`find_value` and `check_pages`, so the model can look a quote up before it answers.

`kdbagent/ask.py` has an agent with two tools, `list_pages` and `read_page`, and an answer
whose every claim must cite source ids that exist on the page it names. The validator sends
back any claim that does not.

`kdbagent/cli.py` is the `kdb` command, with `ingest`, `ask` and `history`.

## What is yours

Everything that turns this into a kDB: the instructions, how pages are chunked, table cells
and their conditions, ontology terms, one page per entity with its aliases, contested claims,
writing the pages with their sources and highlights, `index.md` and `log.md`, and leaving pages
that a paper does not touch byte-identical. `write_pages` raises `NotImplementedError` until you
write it.

For `ask`, `list_pages` returns every page, which stops fitting the context once the kDB has a
few hundred of them. Replace it with tools that search: by ontology term, by benchmark, or with
a query over a table you build from the pages. Printing the citations, `--show`, `--save` and
the SQLite history are yours too, and `kdb history` says so until you write them.

The project page lists everything the kDB and the program must do, and how they are graded.
