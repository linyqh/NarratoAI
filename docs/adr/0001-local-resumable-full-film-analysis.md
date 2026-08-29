# Local resumable full-film analysis

NarratoAI will analyze a locally stored source video across its full timeline by default, after showing an estimate of extracted frames, visual-model requests, and expected duration for creator confirmation. The work runs as a persistent local background task, records completed batches against the video identity for resume, retains the compact Visual Evidence Artifact, and cleans rebuildable keyframes by default; this avoids browser-upload limits and protects long-running, high-cost analyses from UI-session loss.

## Considered Options

We rejected raising the browser upload limit as the primary path because it would still require unreliable multi-gigabyte browser transfers and duplicate storage. We also rejected foreground-only analysis because a page refresh or close would discard work on long source videos.
