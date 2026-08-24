# Sample documents

Five generated chemistry sample PDFs are included here, meeting the
brief's "at least 5 documents" bar out of the box:

- `atomic_structure.pdf`
- `periodic_table_basics.pdf`
- `chemical_bonding.pdf`
- `acids_and_bases.pdf`
- `states_of_matter.pdf`

Upload them (or your own chemistry PDF/TXT/Markdown files — textbook
chapters, lecture notes, problem sets) through the web UI's Knowledge
Base view, which uses the same `/api/documents/upload` ingestion
pipeline either way.

`evals/benchmark.json` contains questions written to match these five
sample documents. If you replace them with your own files, either
update the benchmark questions to match your content, or expect some
benchmark cases to correctly return "I cannot confirm this from the
available documents" since that content won't exist in your knowledge
base.

Note: PDFs with heavy mathematical notation or symbol fonts (chemistry
and physics textbooks often have this) can sometimes extract with
garbled characters depending on how the PDF encodes its glyphs — if you
see corrupted text in citations for a particular PDF, that's a
PDF-text-extraction limitation of the underlying library, not a bug in
the retrieval or generation pipeline. See the README's "Known
Limitations" section.
