import React, { useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { AlertCircle, Download, Loader2, Plus, RefreshCw, X } from 'lucide-react';
import { useCreateWorkflow, usePublicWorkflows } from '../hooks/useWorkflow';

export default function WorkflowOverview({
  onCreate,
}: {
  onCreate?: (workflow: { id: string; name: string }) => void;
}) {
  const { create, creating } = useCreateWorkflow();
  const { workflows: publicWorkflows, loading: publicLoading, error: publicError, refresh: refreshPublic, fork, forking } =
    usePublicWorkflows();
  const [downloadOpen, setDownloadOpen] = useState(false);

  const defaultName = useMemo(() => {
    // match WorkflowList naming style (timestamp, zh-CN)
    const now = new Date();
    const timestamp = now
      .toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
      })
      .replace(/\//g, '-');
    return `New Workflow ${timestamp}`;
  }, []);

  return (
    <div className="flex-1 h-full overflow-hidden bg-canvas flex flex-col py-2 pr-2 pl-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-1.5 flex-shrink-0 h-5">
        <h2 className="text-xs font-bold text-black/60 flex items-center gap-2">
          Workflow Orchestration
          <span className="w-px h-3 bg-black/10"></span>
          <span className="text-[12px] text-black/60 font-normal">
            Design and manage complex agent workflows visually.
          </span>
        </h2>
      </div>

      <div className="flex-1 h-full w-full flex items-center justify-center">
        <div className="flex items-center flex-wrap justify-center text-sm font-medium text-black/90 leading-loose">
          <span>Select, </span>
          <button
            type="button"
            disabled={creating}
            onClick={async () => {
              try {
                const wf = await create({ name: defaultName, description: '' });
                onCreate?.({ id: wf.id, name: wf.name });
              } catch (e) {
                // ignore (WorkflowList will show errors; here keep UI minimal)
                console.error('Failed to create workflow:', e);
              }
            }}
            className="inline-flex items-center gap-1.5 px-3 mx-2 bg-white border border-black/10 text-black/70 hover:border-black/30 hover:text-black transition-all text-xs font-bold uppercase tracking-wide align-middle h-8 hover:shadow-sm"
          >
            <Plus className="w-3 h-3" />
            <span className="">Create</span>
          </button>
          <span> or </span>
          <button
            type="button"
            onClick={() => setDownloadOpen(true)}
            className="inline-flex items-center gap-1.5 px-3 mx-2 bg-white border border-black/10 text-black/70 hover:border-black/30 hover:text-black transition-all text-xs font-bold uppercase tracking-wide align-middle h-8 hover:shadow-sm"
          >
            <Download className="w-3 h-3" />
            <span className="">Download</span>
          </button>
          <span> a workflow to run.</span>
        </div>
      </div>

      {downloadOpen
        ? createPortal(
            <div className="fixed inset-0 z-[60] flex items-center justify-center">
              <div
                className="absolute inset-0 bg-black/30"
                onClick={() => setDownloadOpen(false)}
                role="button"
                tabIndex={-1}
                aria-label="Close download workflows"
              />
              <div className="relative w-[720px] max-w-[calc(100vw-32px)] max-h-[calc(100vh-32px)] bg-canvas border border-divider rounded-md shadow-xl overflow-hidden">
                <div className="h-[44px] px-4 flex items-center justify-between bg-canvas">
                  <div className="min-w-0">
                    <div className="text-[12px] font-semibold text-black/80 truncate">Download a workflow</div>
                    <div className="text-[10px] text-black/40 truncate">From Community (fork to My Workflows)</div>
                  </div>
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      className="w-8 h-8 inline-flex items-center justify-center rounded-sm text-black/40 hover:text-black/80 hover:bg-black/5 transition-colors"
                      onClick={refreshPublic}
                      title="Refresh"
                    >
                      <RefreshCw className="w-4 h-4" />
                    </button>
                    <button
                      type="button"
                      className="w-8 h-8 inline-flex items-center justify-center rounded-sm text-black/40 hover:text-black/80 hover:bg-black/5 transition-colors"
                      onClick={() => setDownloadOpen(false)}
                      title="Close"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                <div className="p-3 overflow-y-auto max-h-[calc(100vh-32px-44px)]">
                  {publicLoading ? (
                    <div className="flex items-center justify-center py-10 text-black/40">
                      <Loader2 className="w-4 h-4 animate-spin" />
                    </div>
                  ) : publicError ? (
                    <div className="flex flex-col items-center justify-center py-10 gap-2">
                      <AlertCircle className="w-5 h-5 text-red-500" />
                      <div className="text-[11px] text-black/60 text-center">{publicError.message}</div>
                      <button
                        type="button"
                        onClick={refreshPublic}
                        className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-sm bg-black/5 text-black/70 hover:bg-black/10 transition-colors"
                      >
                        <RefreshCw className="w-3.5 h-3.5" />
                        <span className="font-medium text-[11px]">Retry</span>
                      </button>
                    </div>
                  ) : publicWorkflows.length === 0 ? (
                    <div className="text-[11px] text-black/40 py-10 text-center">No community workflows.</div>
                  ) : (
                    <div className="flex flex-col">
                      {publicWorkflows.map((wf) => (
                        <div
                          key={wf.id}
                          className="flex items-center justify-between gap-3 px-3 py-2 border-b border-divider/50"
                        >
                          <div className="min-w-0">
                            <div className="text-[12px] font-medium text-black/80 truncate">{wf.name}</div>
                            <div className="text-[10px] text-black/40 truncate">{wf.updated_at ? new Date(wf.updated_at).toLocaleString() : ''}</div>
                          </div>
                          <button
                            type="button"
                            disabled={forking}
                            onClick={async () => {
                              try {
                                const forked = await fork(wf.id);
                                onCreate?.({ id: forked.id, name: forked.name });
                                setDownloadOpen(false);
                              } catch (e) {
                                console.error('Failed to download workflow:', e);
                              }
                            }}
                            className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-sm bg-black/5 text-black/80 hover:bg-black/10 hover:text-black transition-colors disabled:opacity-50 flex-shrink-0"
                            title="Download (fork)"
                          >
                            {forking ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
                            <span className="text-[11px] font-medium">Download</span>
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>,
            document.body
          )
        : null}
    </div>
  );
}


