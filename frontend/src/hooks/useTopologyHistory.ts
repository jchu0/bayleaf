import { useCallback, useReducer, useRef, type Dispatch, type SetStateAction } from 'react'
import type { UserEdge, UserNode } from '../components/BuilderShared'

// Undo/redo for the Pipeline-Builder canvas topology (PB2 §3.2). Deliberately minimally-invasive: it
// does NOT own the graph state — it snapshots the current {nodes, edges} into a bounded ring and, on
// undo/redo, hands a prior snapshot back through the existing setters. One `record()` per discrete
// gesture ⇒ one undo step. This is the safety net that lets an edge-severing delete stay reversible
// (the maintainer's "no accidental cascade" rule — see the delete policy in PipelineBuilder).
//
// Scope: canvas topology only (nodes/edges). Locator/reference authoring (locEdits/refLoc) is not
// yet undoable — extending history to those is a state-consolidation refactor deferred to a follow-up.

export type Topology = { nodes: UserNode[]; edges: UserEdge[] }

export type TopologyHistory = {
  record: () => void // call BEFORE a mutation — snapshots the CURRENT nodes/edges, clears the redo stack
  undo: () => void
  redo: () => void
  reset: () => void // New / Cancel / Load — clears both stacks
  canUndo: boolean
  canRedo: boolean
}

export function useTopologyHistory(
  nodes: UserNode[],
  edges: UserEdge[],
  setNodes: Dispatch<SetStateAction<UserNode[]>>,
  setEdges: Dispatch<SetStateAction<UserEdge[]>>,
  cap = 50,
): TopologyHistory {
  const past = useRef<Topology[]>([])
  const future = useRef<Topology[]>([])
  // Latest committed arrays, refreshed every render, so record/undo/redo capture the current closure
  // values without needing them in their dependency lists (the setters are the only real deps).
  const cur = useRef<Topology>({ nodes, edges })
  cur.current = { nodes, edges }
  // A force-tick so canUndo/canRedo re-derive (the stacks live in refs, invisible to React otherwise).
  const [, tick] = useReducer((n: number) => n + 1, 0)

  const record = useCallback(() => {
    past.current.push(cur.current)
    if (past.current.length > cap) past.current.shift() // bounded ring — no unbounded growth
    future.current = []
    tick()
  }, [cap])

  const undo = useCallback(() => {
    const prev = past.current.pop()
    if (!prev) return
    future.current.push(cur.current)
    setNodes(prev.nodes)
    setEdges(prev.edges)
    tick()
  }, [setNodes, setEdges])

  const redo = useCallback(() => {
    const next = future.current.pop()
    if (!next) return
    past.current.push(cur.current)
    setNodes(next.nodes)
    setEdges(next.edges)
    tick()
  }, [setNodes, setEdges])

  const reset = useCallback(() => {
    past.current = []
    future.current = []
    tick()
  }, [])

  return { record, undo, redo, reset, canUndo: past.current.length > 0, canRedo: future.current.length > 0 }
}
