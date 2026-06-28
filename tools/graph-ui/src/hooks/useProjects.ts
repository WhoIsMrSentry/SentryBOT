import { useCallback, useEffect, useState } from "react";
import { callTool } from "../api/rpc";
import type { GraphData, Project, SchemaInfo } from "../lib/types";

interface ProjectInfo {
  project: Project;
  schema: SchemaInfo | null;
}

interface UseProjectsResult {
  projects: ProjectInfo[];
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

async function fetchStaticProjects(): Promise<ProjectInfo[]> {
  const res = await fetch("data.json");
  if (!res.ok) return [];
  const data: GraphData = await res.json();

  const labelCounts: Record<string, number> = {};
  const typeCounts: Record<string, number> = {};
  for (const n of data.nodes) {
    labelCounts[n.label] = (labelCounts[n.label] || 0) + 1;
  }
  for (const e of data.edges) {
    typeCounts[e.type] = (typeCounts[e.type] || 0) + 1;
  }

  return [{
    project: {
      name: data.project || "SentryBOT",
      root_path: "/",
      indexed_at: data.indexed_at || "",
    },
    schema: {
      node_labels: Object.entries(labelCounts).map(([label, count]) => ({ label, count })),
      edge_types: Object.entries(typeCounts).map(([type, count]) => ({ type, count })),
      total_nodes: data.total_nodes,
      total_edges: data.edges.length,
    },
  }];
}

export function useProjects(): UseProjectsResult {
  const [projects, setProjects] = useState<ProjectInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchProjects = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await callTool<{ projects: Project[] }>("list_projects");
      const list = result.projects ?? [];

      const infos: ProjectInfo[] = await Promise.all(
        list.map(async (p) => {
          try {
            const schema = await callTool<SchemaInfo>("get_graph_schema", {
              project: p.name,
            });
            return { project: p, schema };
          } catch {
            return { project: p, schema: null };
          }
        }),
      );

      setProjects(infos);
    } catch {
      try {
        const staticProjects = await fetchStaticProjects();
        setProjects(staticProjects);
      } catch {
        setError("Failed to fetch projects");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  return { projects, loading, error, refresh: fetchProjects };
}
