Lab Automation — Opentrons Protocol Suite (Portfolio)

Curated, sanitized Opentrons protocols for an end-to-end automation workflow supporting microbiome sample processing and library preparation.


## End-to-End 16S Workflow

![16S Workflow](assets/16S_flowchart.png)

PDF version: [Download Flowchart](assets/16S_flowchart.pdf)



## What this repo demonstrates
- Production-style protocol organization for **OT-2** and **Opentrons Flex**
- Reusable helper functions and consistent configuration patterns (where applicable)
- Clear separation of protocol stages + run assumptions

## Repository structure
- `protocols/OT-2/` — OT-2 protocols
- `protocols/Flex/` — Flex protocols
- `docs/` — workflow overview, run instructions, redaction notes

## Workflow overview
High-level stages (typical):
1. Setup / reagent staging
2. Normalization / pooling
3. Library prep steps
4. Cleanup / QC handoffs + run logging

See `docs/workflow_overview.md`.

## Redaction / privacy
This repo omits any sensitive sample identifiers and internal operational details.  
See `docs/safety_and_redaction.md`.

## Attribution
Protocols were developed collaboratively in a lab environment; this repository is a portfolio mirror containing sanitized versions authored primarily by Tavis Goldwire.
