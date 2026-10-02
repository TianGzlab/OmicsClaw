# <NN_slug>

<!-- Written by the agent. The step runner only checks that this file exists. -->

## Purpose

<What this module answers, in one paragraph.>

## Inputs

<Upstream modules and data files this module reads.>

## Steps

<One line per step file: what it does.>

## Decisions

<Choices made in this module and why.>

## Running outside OmicsClaw

    PYTHONPATH=<checkout> python analysis/<NN_slug>/<step>.py      # one step, from the project root
    python <checkout>/skills/_sdk/notebook/run.py replay analysis/<NN_slug>
