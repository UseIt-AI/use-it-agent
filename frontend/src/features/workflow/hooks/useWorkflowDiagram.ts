import { useCallback } from 'react';
import {
  addEdge,
  Connection,
  Edge,
  MarkerType,
  useEdgesState,
  useNodesState,
} from 'reactflow';

const initialNodes = [
  {
    id: '1',
    type: 'input',
    data: { label: 'Start Task' },
    position: { x: 250, y: 25 },
    style: {
      background: '#f0fdf4',
      border: '1px solid #22c55e',
      color: '#15803d',
      borderRadius: '999px',
      width: 100,
      fontSize: 12,
      fontWeight: 500,
    },
  },
  {
    id: '2',
    data: { label: 'Task Parser Agent' },
    position: { x: 250, y: 125 },
    style: {
      background: '#eff6ff',
      border: '1px solid #3b82f6',
      color: '#1d4ed8',
      width: 140,
      fontSize: 12,
    },
  },
  {
    id: '3',
    data: { label: 'Browser Use Agent' },
    position: { x: 100, y: 250 },
    style: {
      background: '#fff7ed',
      border: '1px solid #f97316',
      color: '#c2410c',
      width: 140,
      fontSize: 12,
    },
  },
  {
    id: '4',
    data: { label: 'Excel Agent' },
    position: { x: 400, y: 250 },
    style: {
      background: '#fff7ed',
      border: '1px solid #f97316',
      color: '#c2410c',
      width: 140,
      fontSize: 12,
    },
  },
  {
    id: '5',
    type: 'output',
    data: { label: 'Result' },
    position: { x: 250, y: 375 },
    style: {
      background: '#fef2f2',
      border: '1px solid #ef4444',
      color: '#b91c1c',
      borderRadius: '999px',
      width: 80,
      fontSize: 12,
      fontWeight: 500,
    },
  },
];

const initialEdges = [
  {
    id: 'e1-2',
    source: '1',
    target: '2',
    markerEnd: { type: MarkerType.ArrowClosed, color: '#94a3b8' },
    style: { stroke: '#94a3b8' },
  },
  {
    id: 'e2-3',
    source: '2',
    target: '3',
    markerEnd: { type: MarkerType.ArrowClosed, color: '#94a3b8' },
    style: { stroke: '#94a3b8' },
  },
  {
    id: 'e2-4',
    source: '2',
    target: '4',
    markerEnd: { type: MarkerType.ArrowClosed, color: '#94a3b8' },
    style: { stroke: '#94a3b8' },
  },
  {
    id: 'e3-5',
    source: '3',
    target: '5',
    markerEnd: { type: MarkerType.ArrowClosed, color: '#94a3b8' },
    style: { stroke: '#94a3b8' },
  },
  {
    id: 'e4-5',
    source: '4',
    target: '5',
    markerEnd: { type: MarkerType.ArrowClosed, color: '#94a3b8' },
    style: { stroke: '#94a3b8' },
  },
];

export function useWorkflowDiagram() {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  const onConnect = useCallback(
    (params: Edge | Connection) => setEdges(eds => addEdge(params, eds)),
    [setEdges]
  );

  return {
    nodes,
    edges,
    onNodesChange,
    onEdgesChange,
    onConnect,
  };
}


