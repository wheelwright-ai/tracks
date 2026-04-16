## Mission
Portable conversation records and prompt library for the WAI ecosystem. Provides a local web viewer for browsing session track files (JSONL format), analyzing conversation patterns, and surfacing decisions/insights across sessions. Serves as the canonical reference for what "a WAI track" looks like and how to parse one.

## Stack
TypeScript · local web app · JSONL parsing · browser-based file handling · session analytics

## Current Focus
Maintain phase — keeping track format documentation aligned with the evolving protocol, resolving metadata-missing teachings, and maintaining the authority model (Tracks is the spec, not just a viewer).

## Knowledge Appetite
What Forge should route here:
- **JSONL format evolution**: Any new patterns for structuring AI conversation logs; format extensions for tracking decisions, insights, and tool calls
- **Conversation analytics patterns**: Ways to extract value from conversation logs; clustering similar sessions; surface high-impact decisions
- **Browser-based file handling**: Patterns for reading/parsing local files in browser without server; File System Access API, drag-and-drop patterns
- **AI session metadata**: What metadata matters for understanding a session; how to tag and classify conversations for later retrieval
- **Visualization of temporal data**: UI patterns for browsing time-series conversation data; timeline UIs; diff views for session comparison
