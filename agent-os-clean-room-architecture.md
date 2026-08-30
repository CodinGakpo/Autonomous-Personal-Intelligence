# Agent OS — Clean-Room Architecture Analysis

> **Status:** Design exploration / decision record (clean-room).
> **Scope:** Architecture-neutral evaluation of how to build the "company second brain" described in *Agent OS — Capability Requirements*.
> **Method note:** This is a *clean-room* design. It deliberately reasons from the requirements alone and does **not** read or depend on any existing `brain/` implementation, PRD, or ADR, so as not to anchor on prior decisions. No existing files were modified.

---

## 1. The core problem, restated — and where the real difficulty hides

### 1.1 In plain terms

A company's knowledge lives in five or six disconnected systems (meeting transcripts in Fathom, tasks in ClickUp, chatter in Slack, code in git, claims in résumés, decisions in docs). Each system answers *its own* narrow question. Nobody can answer the **cross-cutting** ones:

- *Who is doing what, right now?*
- *What did we decide, and where is the code that implements it?*
- *I missed that meeting — what happened and what are my action items?*
- *Who is the right person for this task?*
- *Is this person as good as their résumé claims?*

So the system is, at heart, a **continuously-maintained, queryable, provenance-tracked projection** over many source systems, with a natural-language front door and role-based access control.

### 1.2 The requirements that are *secretly* the hard part

Most of the bullet list is ordinary integration work. Five requirements are load-bearing and quietly determine the entire architecture. If a design gets these wrong, no amount of polish saves it:

**H1 — The questions are mostly *joins and aggregations*, not *semantic recall*.**
"Who decided X **and** where's the code" is a graph traversal: `Decision → implemented_by → PR → touches → File → authored_by → Person`. "Who's doing what" is an aggregation over current assignments. "Assigned vs completed" is a `GROUP BY`. Only a minority of questions ("what did I miss") are true semantic-similarity questions. **This single observation kills pure vector-RAG as the spine** — vectors find text that *resembles* a query; they cannot reliably reconstruct an explicit relationship that isn't spelled out in a single chunk.

**H2 — "Every answer traceable to its sources" is an architectural constraint, not a feature.**
Verifiability forbids "stuff everything into the LLM and trust it." Every fact must carry a stable, addressable citation (source system + source ID + extraction run + content hash). This pushes provenance *into the data model* and rules out lossy-summary-only designs.

**H3 — Idempotent, duplicate-free, "lands on the right item" updates = entity resolution + change-data-capture.**
When a transcript says *"Sai will fix the login bug,"* is that a **new** task or an update to ClickUp #4127? Getting this right — deterministically, on every re-run — is the hardest *operational* problem in the system, and it is exactly where duplicates and mis-attributions come from. "Re-running changes nothing extra" is a demand for **idempotent writes keyed on deterministic identity**, which is a property you must design in from line one; you cannot bolt it on.

**H4 — Two memory planes + access control = isolation that can't be retrofitted.**
There is *shared, curated company knowledge* and there is *per-employee private conversation memory that must never pollute the shared brain*. On top of that, the shared plane has **attribute-level sensitivity** (comp, performance, HR) enforced **server-side, per-identity, at retrieval time**. Get the data model wrong and you leak — and you cannot patch isolation in later.

**H5 — "No reprocessing per question" + "incremental" + "LLM is the costly part" = cost scales with *change*, not *corpus*.**
The expensive resource (LLM tokens) must be spent **once per unit of new data** (extraction) and **once per question over a small retrieved context** (composition) — never on scanning the whole corpus. This forces a clear split between a *build/ingest pipeline* (writes, runs on change) and a *query path* (reads, runs per question), with precomputed/materialized intermediate state in between.

> **The thesis of this document:** the valuable, hard, differentiating work is on the **write path** (ingestion → extraction → entity resolution → idempotent upsert with provenance), **not** on the read path (retrieval). Most teams over-invest in clever retrieval and under-invest in entity resolution — and that is precisely why their "second brain" becomes untrustworthy and duplicate-ridden. *Trustworthy + duplicate-free is won or lost at write time.*

### 1.3 The real constraints, extracted

| # | Constraint | Type | Teeth |
|---|-----------|------|-------|
| C1 | Answers traceable to sources | Correctness | Provenance in the data model; no black-box summaries as truth |
| C2 | No full-corpus reprocessing per query | Cost/scale | Split build vs query; precompute |
| C3 | Cross-source joins incl. code | Capability | Relational/graph spine required |
| C4 | Idempotent, duplicate-free, "right item" updates | Correctness | Deterministic identity + upsert + entity resolution |
| C5 | Incremental processing (LLM = cost) | Cost | CDC + content hashing; spend per delta |
| C6 | Soft deletes + history | Correctness | Bitemporal validity, never hard-delete |
| C7 | Mid-stream import **and** greenfield | Lifecycle | Backfill path = steady-state path |
| C8 | Private per-user chat memory, isolated | Security | Separate memory plane |
| C9 | Role-based access; sensitive data restricted | Security | Server-side, attribute-level, pre-retrieval filter |
| C10 | LLM swappable (runtime / API / local CLI) | Portability | Provider abstraction; no provider in data model |
| C11 | Scheduled + manual triggers | Ops | Webhook + cron + on-demand, all idempotent |
| C12 | Browser never touches LLM/3rd-party directly | Security | Backend-for-frontend mediates; secrets server-side |

---

## 2. Three fundamentally different architectures

These differ at the level of **what is stored, how it is retrieved, and how it is updated** — not three flavors of one idea. A fourth (a summary tree) is introduced briefly because the winning design absorbs its one good idea as a *component*.

The deep design axis is: **what is the spine of the system?**

- **Architecture A — *No spine* (Federated / virtual).** Store nothing; query the source APIs live at question time with an LLM agent.
- **Architecture B — *Vectors are the spine* (RAG lake).** Embed everything; retrieve by semantic similarity.
- **Architecture C — *A canonical entity graph is the spine* (Structured + hybrid retrieval).** Normalize sources into typed entities and relationships with provenance; retrieve by a planned combination of structured traversal and semantic search.
- *(Architecture D — *Summaries are the spine* (Hierarchical digest tree). Discussed as a complement, not a contender.)*

---

### Architecture A — Federated Agent (virtual, no unified store)

**How it works.** No copy of the data. An LLM "planner" is given tools — ClickUp API, git, Fathom API, Slack API, a résumé blob store. Per question, it decides which tools to call, fetches live, reasons across the results, and answers, citing whatever it fetched. Storage: a thin response cache at most. Retrieval: agentic tool-use / query planning. Update: *nonexistent by construction* — there is nothing to keep in sync; every read is live.

**Tradeoffs.**
- *(+)* Always fresh. No sync, no dedup, no idempotency problem — because nothing is stored (C4/C5/C6 vanish… by not being attempted).
- *(+)* Minimal duplication; each source stays its own system of record; can defer access control to source systems' own permissions.
- *(+)* Cheapest thing to stand up; great for a demo.
- *(−)* **Violates C2 head-on:** every question re-fetches and re-reasons. LLM cost and latency are paid in full, per question, forever.
- *(−)* **Cross-source joins are reconstructed at query time by the LLM**, non-deterministically. "Decision X → its code" requires fanning out and entity-resolving on the fly, every time — unreliable and unrepeatable.
- *(−)* No precomputed profiles, no track record, no "who should do this task" without scanning live each time.
- *(−)* Historical/temporal questions fail when sources don't retain history (Slack edits, deleted tasks).

**Failure modes.** Source API rate limits and outages become *query-time* failures. Non-deterministic planning → the same question yields different answers on different days. Reproducibility is poor (sources mutate under you). Slack/transcript volume makes live scanning infeasible past a small company.

**As data & cost grow.** Cost and latency grow with **both** corpus size **and** number of sources (more fan-out per query). Degrades on the worst axis: every new source taxes *every* future question. This is the naive "MCP-tools-over-APIs" pattern; it is a fine *fallback retriever*, a poor *spine*.

---

### Architecture B — Vector RAG Lake (semantic index over everything)

**How it works.** Chunk every source — transcript segments, task descriptions, résumé sections, code files, decision docs — embed each chunk, store vectors + text in a vector DB. Per question: embed the query, ANN-retrieve top-k chunks, stuff them into the LLM, answer with citations to the chunks. Update: detect changed documents (by hash / source cursor), re-chunk and re-embed only those. Storage: vector DB + chunk/blob store.

**Tradeoffs.**
- *(+)* Excellent for the *semantic-recall* slice: "what did I miss in the meeting," "summarize the auth discussion." Chunk-level citations give decent provenance (C1, partially).
- *(+)* Incremental embedding of only changed docs is straightforward (C5, for text).
- *(+)* Mature tooling; fastest of the "real" designs to build.
- *(−)* **Structurally cannot do C3 (joins) or aggregations.** "Who's doing what" = enumerate all open tasks per person — similarity can't enumerate. "Decision X → its code" works only if some single chunk literally contains that link.
- *(−)* **C4 has no home.** Action items extracted from a transcript have no stable identity; re-embedding spawns near-duplicate chunks; "a status change lands on the right item" is meaningless when there is no canonical *item*, only chunks.
- *(−)* Track record / capability scoring needs *counting structured facts*, not similarity.
- *(−)* Access control is **chunk-metadata filtering** — coarse and leak-prone; one mis-tagged sensitive chunk surfaces in retrieval (weak C9).

**Failure modes.** Retrieval silently misses (top-k cutoff) and the LLM confabulates a connection from unrelated chunks. Near-duplicate chunks from re-ingestion poison ranking. Numeric/aggregate questions get plausible-but-wrong answers — the *most dangerous* failure because it looks authoritative.

**As data & cost grow.** Storage scales fine. But precision/recall on structured questions **never improves**, and near-duplicate accumulation makes it worse. Right for ~half the requirements; structurally wrong for the half that defines the product (H1).

---

### Architecture C — Canonical Entity Graph + Hybrid Retrieval ← *recommended*

**How it works.** A **canonical, normalized entity store is the spine.** Typed entities — `Person, Task, Decision, Meeting, ActionItem, Commit/PR, CodeArtifact, Skill` — and **explicit typed relationships**:

```
Person  —assigned→        Task
Person  —previously_on→    Task
Person  —has_skill→        Skill           (claimed | demonstrated)
Person  —authored→         Commit
Meeting —produced→         ActionItem
ActionItem —resolves_to→   Task            (the entity-resolution edge)
Decision —implemented_by→  PR
PR      —touches→          CodeArtifact(File/Symbol)
Task    —requires_skill→   Skill
```

Every node and edge carries **provenance** (`source_system`, `source_id`, `extraction_run`, `content_hash`) and an **access classification** (`public | team | sensitive`). Unstructured text (transcript passages, doc sections, résumé prose, code) is stored as content rows **linked to the entities they mention**, and *also* embedded into a **vector index** + indexed for **full-text** — but every vector points **back to a canonical entity**, so semantic hits become graph entry-points.

**Retrieval is hybrid and planned.** A lightweight planner (LLM, or a fixed router for known question shapes) maps the NL question to a combination of:
1. **structured queries / graph traversals** over the entity spine — for joins, aggregations, "who/what/where's-the-code"; and
2. **vector + full-text search** over content — for "what was said/decided/missed."

Results are fused; the LLM **composes a cited answer over a small retrieved context** (never the whole corpus).

**Update is a disciplined write path** (this is the heart of the design):

```
Connector (per source, CDC by cursor + content_hash)
   → only-changed raw records
      → Extractor (swappable LLM)  → candidate entities/edges + confidence + provenance
         → Entity Resolver / Linker → match to existing canonical entity via a
            DETERMINISTIC natural key (e.g. source_id when present; else a hash of
            normalized {assignee, normalized_title, meeting_id})
               → Idempotent UPSERT into the canonical store
                  (low-confidence → quarantine/review queue, not the live graph)
```

- **Idempotency (C4)** comes from deterministic keys + upsert, **not** from hoping the LLM returns identical text. The *extraction* is non-deterministic; the *write* is made idempotent by hashing inputs and reconciling on a natural key. Re-running an unchanged source is a no-op.
- **Deletions (C6)** are **soft** with bitemporal validity (`valid_from / valid_to`): a removed task is marked `valid_to = now`, history preserved.
- **Backfill = steady state (C7):** importing existing history is the same connector run with the cursor wound back to t₀. Greenfield just starts at t₀. One code path.
- **Expensive derivations are materialized views** (per-person profile, "who's doing what," per-person catch-up digest), recomputed **incrementally** only when their inputs change — this is where Architecture D's good idea lives, as a *cache*, not as the truth layer.

**The two memory planes (H4/C8)** fall out naturally: the **shared graph** is curated and provenance-tracked; **per-user private conversation memory** is a *separate* store keyed by user (its own small vector index / log), **never** written back into the shared graph. **Access control (C9)** is enforced **before** retrieval: identity → role → allowed `{access_class, ownership}` partition; the planner only ever queries within that partition, so sensitive nodes can't even enter a candidate set.

**Tradeoffs.**
- *(+)* The storage model **matches the shape of the questions** (H1): joins and aggregations are native; semantic recall is a first-class subsystem, not the whole thing.
- *(+)* Provenance (C1), idempotency (C4), soft-delete/history (C6), incremental cost (C2/C5), and attribute-level access control (C9) are **structural properties**, not bolt-ons.
- *(+)* LLM is just extractor/planner/composer behind an interface → **swappable (C10)**; the store is provider-agnostic.
- *(+)* Stakeholder "browse, not just ask" is trivial — the graph/entities *are* a browsable structure.
- *(−)* **Most complex to build.** Needs an ontology, an entity-resolution pipeline (the genuinely hard part), and a planner/router.
- *(−)* Entity resolution is where errors concentrate → needs confidence thresholds + a review queue. ("No babysitting" becomes "**cheap** babysitting" — see §6.)
- *(−)* More moving parts — though consolidatable (see §5.4): Postgres + `pgvector` + recursive CTEs (or Apache AGE for Cypher) can be **one** database.
- *(−)* Risk of over-engineering the ontology up front (mitigated by the phased rollout in §5.3).

**Failure modes.** Entity-resolution false-merges (two different tasks collapsed) or false-splits (one task duplicated) — bounded by confidence gating + review queue + the fact that source IDs (when present) are exact keys. Schema rigidity if the ontology is over-specified early. Planner mis-routes a question to the wrong retriever — mitigated by hybrid fusion (run both, merge) for ambiguous questions.

**As data & cost grow.** Structured queries scale with indexing (what databases are *for*); ANN scales sublinearly; **incremental updates mean ongoing cost scales with the *change rate*, not the corpus size** — the correct scaling property (H5). Dominant ongoing cost = LLM extraction on new data + per-query composition over small contexts — both bounded and predictable.

---

### Architecture D — Hierarchical Summary Tree *(complement, not a contender)*

**How it works.** Maintain LLM-built rolling summaries arranged in a tree (per-person, per-project, per-meeting, "state of the company"). Queries route to the relevant node and read a precomputed summary. Updates re-summarize the touched leaf and propagate upward.

**Why it's not the spine.** Summaries are **lossy and hard to cite precisely** (weak C1); they answer **only along pre-built axes** (no ad-hoc joins — fails C3); re-summarization is **non-deterministic** (fails C4); and absorbed-then-corrected facts cause drift (awkward C6). **But** it is an *excellent cheap-read cache* for "what did I miss" and "what's person Y on" — which is exactly why Architecture C **adopts it as the materialized-digest layer**, sitting *on top of* a provenance-tracked spine rather than replacing it.

---

## 3. Head-to-head against the requirements

Legend: **✓✓** native / structural · **✓** workable · **~** possible but awkward/leaky · **✗** structurally poor.

| Requirement | A — Federated | B — Vector RAG | **C — Entity Graph + Hybrid** |
|---|:---:|:---:|:---:|
| C1 Traceable / explainable answers | ✓ (live, but non-reproducible) | ✓ (chunk-level) | **✓✓ (node+edge provenance)** |
| C2 No full-corpus reprocessing / per-query cost | ✗ (re-reasons every query) | ✓✓ | **✓✓** |
| C3 Cross-source joins incl. code | ~ (LLM joins live, flaky) | ✗ | **✓✓ (traversal)** |
| C4 Idempotent, dup-free, "right item" | n/a (stores nothing) | ✗ | **✓✓ (keys+upsert+ER)** |
| C5 Incremental (LLM = cost) | ✗ | ✓ (text only) | **✓✓** |
| C6 Soft delete + history | ✗ (source-dependent) | ~ | **✓✓ (bitemporal)** |
| C7 Mid-stream import + greenfield | ✓ (no state) | ✓ | **✓✓ (one path)** |
| Profiles: claimed vs demonstrated | ~ (live recompute) | ✗ (no counting) | **✓✓ (claimed/demonstrated edges)** |
| Task↔people / "who should do this" | ~ | ✗ | **✓✓ (skill-match query)** |
| C8 Private per-user memory, isolated | ✓ | ~ (one index, leak risk) | **✓✓ (separate plane)** |
| C9 Role-based, attribute-level access | ~ (defers to sources) | ~ (chunk-tag, leaky) | **✓✓ (pre-retrieval filter)** |
| C10 LLM swappable | ✓✓ | ✓ (but embed-model lock, see §6) | **✓ (same caveat, isolated)** |
| C11 Scheduled + manual, idempotent | ✓ (trivial) | ✓ | **✓✓** |
| C12 Browser never calls LLM/3rd-party | ✓ (BFF) | ✓ (BFF) | **✓ (BFF)** |
| Build complexity / time-to-first-value | **✓✓ lowest** | ✓ medium | ~ highest |
| Scaling axis | corpus×sources (bad) | corpus (ok) | **change-rate (best)** |

**Reading the table:** A wins only on *build simplicity* and *freshness*, and loses the two requirements that define the product (C2, C3). B wins on *semantic recall and speed-to-build*, and is **structurally incapable** of C3/C4 — the joins and the dedup — which are non-negotiable. C wins or ties on every correctness/scale requirement and loses only on *build complexity*, which is a one-time cost mitigated by phasing.

---

## 4. Decision

### 4.1 Choose **Architecture C** — canonical entity graph as the spine, with hybrid (structured + semantic) retrieval, vector recall as a subsystem (B's good part), and materialized digests as a read cache (D's good part).

### 4.2 Why it beats the others

1. **It is the only design whose storage model matches the question mix (H1).** The defining questions are joins and aggregations over people/tasks/decisions/code. A reconstructs those unreliably and re-pays every query; B cannot do them at all. Only C makes them native.
2. **The hard requirements become structural properties, not patches (H2–H4).** Provenance, idempotency, soft-delete history, attribute-level access control, and the two memory planes are *consequences of the data model* in C. In A and B they are either impossible or fragile add-ons.
3. **It scales on the correct axis (H5):** cost tracks the *rate of change*, not corpus size — because the build path is incremental and the query path reads precomputed state over small contexts.
4. **It subsumes its rivals as components.** Vector search (B) is C's semantic retriever. Summary digests (D) are C's materialized read cache. A federated tool-call (A) is a legitimate *fallback retriever* for a source not yet ingested. C doesn't reject the others — it puts each where it belongs.

### 4.3 What would change my mind

- **If the real question mix is ~90% "summarize / what did I miss"** and almost never structured joins → **B** is enough and far cheaper. *Validate this with a question log before committing to C's complexity.*
- **If the corpus and team are tiny, sources few, query volume low, and freshness is paramount** → **A** (federated) is the pragmatic minimum; don't build a pipeline you don't need.
- **If the team cannot sustain ontology + entity-resolution complexity** → start at B with a *thin* structured layer for just `Person`/`Task` and grow toward C (see §5.3).
- **If a managed product already does graph + vector + provenance + access control acceptably** → buy, don't build. The differentiator is your *write path correctness*, not owning a database.

### 4.4 The less-obvious, contrarian point worth stating explicitly

Industry best practice has converged: **pure-vector RAG is insufficient for enterprise knowledge; hybrid "structured-spine + semantic" (often called GraphRAG) is the maturing standard.** That part is now conventional. The *non-obvious* claim is the one in §1.2: **the value and the difficulty are on the write path — connectors, extraction, and entity resolution — not the read path.** Teams reliably over-invest in retrieval cleverness and under-invest in deterministic identity and idempotent upserts, which is exactly why their second brain becomes untrustworthy. Spend the engineering there.

---

## 5. Concrete shape of the chosen system (actionable)

### 5.1 Components

- **Connectors** (one per source: Fathom, ClickUp, Slack, git, résumés, decision docs). Each tracks a **cursor** and **content hashes**; emits only changed records. Fathom via **webhook** (post-meeting); ClickUp/git/Slack via **cron reconcile**; all expose **manual refresh**.
- **Extractor** (swappable LLM behind an interface): raw record → candidate entities/edges + **confidence** + **provenance**.
- **Entity Resolver / Linker:** matches candidates to canonical entities via **deterministic natural keys**; **idempotent upsert**; low-confidence → **review queue**.
- **Canonical store:** entities + typed edges + **bitemporal validity** + **access class** + provenance.
- **Semantic + full-text indexes** over content rows, each pointing back to a canonical entity.
- **Materialized views:** per-person **profile** (claimed vs demonstrated), **"who's doing what,"** per-person **catch-up digest** — recomputed incrementally on input change.
- **Query layer:** planner/router → structured + semantic retrieval → fusion → **LLM composes a cited answer**. **Access filter applied before retrieval.**
- **Private memory plane:** per-user conversational store, isolated from the shared graph.
- **Backend-for-frontend (BFF):** holds **all** secrets; the browser talks only to it; it calls the LLM (via the provider abstraction) and the source APIs. **(C12.)**

### 5.2 Profiles — claimed vs demonstrated (the requirement made concrete)

- **Claimed** = LLM extraction from the résumé → `Person —has_skill{claimed, confidence, source=résumé§N}→ Skill`.
- **Demonstrated** = aggregation over delivered work → `Person —authored→ Commit —touches→ CodeArtifact —requires_skill→ Skill`, plus assigned-vs-completed `Task` counts.
- The profile view shows **both, side by side, with provenance**, and never collapses them into one number. (See the §6 pushback on scoring.)

### 5.3 Phased rollout (de-risks C's one real weakness: complexity)

1. **Phase 1 — Spine for the two highest-value entities.** `Person` + `Task` + assignment/skill edges + provenance + soft-delete, fed by ClickUp + résumés + git authorship. Add a vector index over transcripts/docs for "what did I miss." This already answers *"who's doing what," "what am I on," "what did I miss"* — most of the value, a fraction of the ontology.
2. **Phase 2 — Decisions ↔ code.** Add `Decision`, `PR`, `CodeArtifact` and the `implemented_by / touches` edges → unlock *"who decided X / where's the code."*
3. **Phase 3 — Matching + digests.** `requires_skill` matching ("who should do this"), materialized per-person digests, private chat memory, full role-based access classes.

Grow the graph **only as new join-questions prove their worth** — directly honoring "Simplicity First": no ontology you can't yet justify.

### 5.4 Technology stance (favor proven, fight sprawl)

Default to **one database** where possible: **Postgres + `pgvector`** (semantic) **+ full-text** (`tsvector`) **+ recursive CTEs or Apache AGE** (graph traversal). This gives the entity spine, vectors, full-text, transactions (for idempotent upserts), and row/attribute access control **in a single, proven, transactional system** — minimizing the "many moving parts" cost. Reach for a dedicated graph DB (Neo4j) **only if** traversal depth/complexity outgrows recursive SQL, and a dedicated vector store **only if** scale outgrows `pgvector`. Don't pay for that complexity before the data demands it.

---

## 6. Pushback — conflicts, ambiguities, and challenged assumptions

I was asked to be skeptical of the requirements themselves. Here is where they need sharpening or where I'd push back:

1. **"Single place" is a category error → want a single *interface*, not a single *store*.** The workload is genuinely multi-modal (entities+edges, semantic text, full-text, code). Read "one queryable place" as **one logical knowledge layer with a unified query surface**, which *may* be one physical DB (§5.4) but shouldn't be mandated to be.

2. **The brain is a *projection*, not the system of record.** ClickUp owns tasks; git owns code; Fathom owns transcripts. The brain is a **derived, provenance-tracked read-model**. Treating it as authoritative invites divergence. **"The agent writes back" is dangerously ambiguint** — write back *to the brain* (fine, that's ingestion) or *to ClickUp/Slack* (a side-effecting action with real consequences)? I'd scope write-back to upstream systems as a **separate, explicitly-gated capability** (confidence threshold + human confirmation), never conflated with the brain being "source of truth."

3. **"No babysitting" vs "trustworthy auto-extraction" are in tension.** LLM extraction *will* mis-attribute and hallucinate tasks. "Trustworthy" therefore requires a **confidence + quarantine** mechanism: high-confidence writes land automatically; low-confidence ones wait in a **cheap review queue**. The honest target is **"cheap oversight," not "zero oversight."** Promising zero is how trust erodes.

4. **"Scored strengths" is a trap if presented as objective.** LLM-derived numeric skill scores from a résumé are noisy and carry **bias and even employment-law risk** if used to make staffing/comp decisions. Present scores as **estimates with provenance**, **calibrate against demonstrated work**, show **claimed and demonstrated separately**, and treat "who should do this task" as **decision-support, never decision-maker**.

5. **Slack should be ingested *selectively*, not wholesale.** It's high-volume, low-signal, and laden with **privacy/consent** concerns (DMs, private channels). Ingest specific channels or threads referenced elsewhere; don't vacuum it. Wholesale Slack pollutes retrieval *and* expands the access-control blast radius.

6. **Access control needs a *sensitivity taxonomy*, not just ownership.** "Own + shared, never others' sensitive" requires defining the classes: what's *shared work context* ("Sai is on auth" — visible) vs *sensitive* ("Sai's performance/comp" — restricted). Without an explicit `{public | team | sensitive}` classification on every node, the boundary is undefined and unenforceable.

7. **Provenance vs summarization is a real tension — resolve it toward extraction-with-citation.** Summaries are convenient but lossy and hard to cite (C1). Use them as a **read cache**, and keep the **citable, extracted facts** as the truth layer underneath.

8. **Idempotency must come from deterministic *keys*, not deterministic *LLMs*.** A subtle but critical point: the extractor is non-deterministic, so re-running it yields *different text*. You achieve "re-running changes nothing extra" by making the **write** idempotent — hash the inputs, resolve to a **natural key**, **upsert** — so re-runs *reconcile* rather than *append*. Designs that hope the LLM is stable will accrete duplicates.

9. **"LLM swappable" is cheap for generation but *not* for embeddings.** Swapping the **generation** model is trivial (it sits behind an interface). Swapping the **embedding** model **invalidates the entire vector index** — every chunk must be re-embedded. So store the `embedding_model_version` in metadata and treat embedding-model changes as a **migration**, not a config flip. C10, read naively, hides this cost.

10. **"Becomes the single, trustworthy second brain" is a *trust*-establishment problem, not just a *build* problem.** Trust is earned by **showing the sources** (C1) and by **degrading honestly** ("I don't have data on that" beats a confident guess). The architecture must make "I don't know / not enough sourced evidence" a **first-class answer**, or the first confident-but-wrong response destroys adoption.

---

## Appendix — every stated capability → where the design satisfies it

| Capability (from requirements) | Satisfied by |
|---|---|
| Unified knowledge / ingest all sources | Connectors → canonical store (§5.1) |
| Efficient, explainable, source-traceable answers | Provenance on every node/edge; cited composition (C1, §2-C) |
| Connect knowledge to code | `Decision→PR→CodeArtifact→Person` traversal (§5.1, Phase 2) |
| Post-meeting absorb (summary + per-person items) | Fathom webhook → extractor → ActionItem→resolves_to→Task (§5.1) |
| Periodic reconcile of task/people activity | ClickUp/git cron connectors (C11) |
| Manual/on-demand refresh | Manual trigger on every connector (C11) |
| Reliable, duplicate-free, "right item" updates | Deterministic keys + upsert + ER (C4, §1.2-H3) |
| Efficient — only what changed | CDC + content hashing (C5) |
| Deletions graceful, keep history | Bitemporal soft-delete (C6) |
| Mid-stream import + greenfield | Same connector, cursor at t₀ (C7) |
| Per-person profile (claimed) | LLM extraction → has_skill{claimed} (§5.2) |
| Track record (demonstrated) | Aggregation over Task/Commit edges (§5.2) |
| Task↔people awareness | Task entity + assigned/previously_on/requires_skill edges |
| "Who should do this task" | Skill-match query over capabilities (Phase 3) |
| Self-service assistant, opens with own context | Query pre-seeded with asker identity → their subgraph |
| Widen scope on demand | Planner expands traversal within access partition |
| Private chat memory, non-polluting | Separate per-user memory plane (C8) |
| Access boundaries enforced | Pre-retrieval, attribute-level filter (C9) |
| Stakeholder browse (not just ask) | Entities/graph are directly browsable (§4.2) |
| Role-based access to sensitive data | `{public|team|sensitive}` class + role filter (C9, §6.6) |
| LLM swappable | Provider abstraction behind extractor/planner/composer (C10) |
| Scheduled + manual | Webhook + cron + manual (C11) |
| Browser never calls LLM/3rd-party | BFF holds secrets; mediates all calls (C12) |
| Scales without full reprocessing | Incremental build path; change-rate scaling (C2/C5, H5) |
