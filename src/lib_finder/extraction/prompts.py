"""Prompt templates for package-document extraction."""

from __future__ import annotations

import langextract as lx

PACKAGE_EXTRACTION_PROMPT = """
Extract grounded facts from package documentation.

Rules:
- Only extract claims that are explicitly present in the source text.
- Every claim must be grounded to at least one exact source snippet.
- Prefer short fact values and stable fact types.
- Do not paraphrase source spans.

Focus on package metadata that is useful for downstream qualification:
- supported Python versions
- installation or runtime prerequisites
- deprecation or archival signals
- compatibility notes
- maintainership signals
- explicit external service dependencies
""".strip()


def build_package_extraction_prompt() -> str:
    """Return the default prompt for package-document extraction."""

    return PACKAGE_EXTRACTION_PROMPT


def build_package_extraction_examples() -> tuple[lx.data.ExampleData, ...]:
    """Return a small example set for grounded package extraction."""

    return (
        lx.data.ExampleData(
            text="Requests supports Python >=3.9 and is actively maintained.",
            extractions=[
                lx.data.Extraction(
                    extraction_class="supported_python",
                    extraction_text="Python >=3.9",
                    attributes={"package": "requests"},
                ),
                lx.data.Extraction(
                    extraction_class="maintainership",
                    extraction_text="actively maintained",
                    attributes={"package": "requests"},
                ),
            ],
        ),
        lx.data.ExampleData(
            text="Example project requires a network service at runtime.",
            extractions=[
                lx.data.Extraction(
                    extraction_class="external_dependency",
                    extraction_text="a network service at runtime",
                    attributes={"package": "example-project"},
                ),
            ],
        ),
    )
