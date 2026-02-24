# Workflow Overview

These protocols were designed to automate a full 16S microbiome sequencing workflow beginning with DNA extraction and progressing through library preparation.

## 1. DNA Extraction – ZymoBIOMICS 96 MagBead DNA Kit

Initial automation focused on adapting the Zymo Research ZymoBIOMICS 96 MagBead DNA Kit for the Opentrons OT-2 platform. The design prioritized:

Reproducibility across 96-well plates

Reduction of manual pipetting variability

Modular step structure for future adaptation

In addition to extraction, general-purpose automation utilities were developed for:

Plate pooling

Plate consolidation

Equimolar normalization

These were implemented on the OT-2 due to existing lab infrastructure and consumables. The workflow is structured such that migration to Opentrons Flex would primarily involve hardware optimization rather than logical redesign.

## 2. DNA Cleanup – ZR-96 DNA Sequencing Clean-up Kit

The ZR-96 cleanup workflow was automated on the OT-2 to improve reproducibility and throughput during bead-based purification steps.

This stage emphasized:

Consistent magnetic engagement timing

Controlled aspiration heights, centrifuge pause steps

Reduced operator-dependent variability

This protocol is a strong candidate for migration to Opentrons Flex for improved performance and runtime efficiency.

## 3. 16S Library Preparation – Zymo Quick-16S Full-Length Kit

Automation of the Zymo Quick-16S Full-Length Library Prep Kit was developed in collaboration with Zymo Research.

Additional custom automation steps were implemented to:

Meet updated procedural recommendations

Automate supplemental PCR product cleanup

Enable processing of 96 samples prior to Take3 analysis

Support equimolar pooling workflows

Design decisions focused on parameterization to allow adjustments in reaction volumes and sample counts without rewriting core logic.

## 4. Planned Integration – Oxford Nanopore Ligation Sequencing (SQK-LSK114)

The next development step is automation of the Oxford Nanopore Ligation Sequencing Amplicons V14 (SQK-LSK114) protocol.

This would enable:

Raw sample → DNA extraction → Cleanup → 16S amplification → Cleanup → Library prep

A fully automated, end-to-end workflow.

## System Design Principles

Across protocols, emphasis was placed on:

Modular step abstraction

Reusable utility functions

Parameter-driven configuration

Clear separation of lab logic from hardware execution

This architecture supports future integration of adaptive workflows, runtime optimization, and AI-driven protocol tuning as lab automation platforms continue to evolve.
