# Documentation Standard — EmbedIQ

## Why this exists

EmbedIQ's framework and cloud are open source. As AI writes more of the code, our differentiator is no
longer typing code — it is the quality of our architecture, our process, and how clearly we explain both.
Our documents are Ritzy Lab's portfolio. A reader should finish any EmbedIQ document understanding the
decision and trusting the team that made it. This standard makes that the default everywhere.

## What it governs

Every piece of prose: READMEs, design docs, ADRs, pull-request descriptions, code comments, and the
private planning docs in `pm/`. Public or private makes no difference to writing quality — it changes only
what content we expose, never how well we write it.

## The five questions every document answers (up front)

A reader with no prior context must be able to answer these after reading:

1. **Why** — the problem or purpose.
2. **What** — the thing itself: the feature, decision, or change, stated plainly.
3. **Where it impacts** — the components, layers, users, or systems it touches.
4. **How it impacts** — the effect: what changes in behavior, performance, or contract.
5. **Caveats & edges** — what is handled, known limitations, edge cases, trade-offs, what is deferred.

A document missing any of these is incomplete.

## How we write

- First principles. Explain from base truths; assume no prior project knowledge; define every term on first use.
- To the point. No storytelling, no marketing voice, no filler. If a sentence can lose words and keep its meaning, cut them.
- Low cognitive load. One idea per paragraph. Short sentences. Concrete nouns. Structure so a reader can scan.
- Self-contained. No "as discussed," no undefined acronyms, no implicit context.
- Honest. State limitations and trade-offs plainly. Precision without proof is worse than honest approximation.

## Where this is enforced

- Machine (CI, blocks merge): markdownlint (format), a section-presence check (the five questions in
  design docs and ADRs), and vale (prose: sentence length, filler words, passive voice).
- Review (the doc gate): clarity, no-prior-knowledge readability, and honest caveats are checked in PR
  review. A PR whose docs read as a story, assume context, or hide trade-offs is sent back.

## Caveats

- Prose linting catches mechanics, not meaning; the review gate is the backstop.
- The section check applies to design docs and ADRs, not every README stub or one-line comment. The spirit (the five questions) always applies.
- The style ratchets like coverage: tightened over time, never loosened.
