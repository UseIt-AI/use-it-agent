import React from 'react';
import { Cpu, MemoryStick, HardDrive, Monitor, Loader2, RefreshCw, AlertTriangle, ArrowRight } from 'lucide-react';
import type { VmSpecsState } from '../hooks/useVmSpecs';

interface DesktopSpecsCardProps {
  specs: VmSpecsState;
  onRefresh?: () => void;
}

export function DesktopSpecsCard({ specs, onRefresh }: DesktopSpecsCardProps) {
  const isLoading = specs.status === 'loading';

  // VM 不存在
  if (specs.status === 'vm_not_found') {
    return (
      <div className="flex items-center gap-4 w-full h-full px-2">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-amber-100 flex items-center justify-center flex-shrink-0">
            <AlertTriangle className="w-5 h-5 text-amber-600" />
          </div>
          <div className="min-w-0">
            <p className="text-xs font-semibold text-amber-800">VM Not Installed</p>
            <p className="text-[10px] text-amber-600 mt-0.5">
              Go to Desktop panel to install
            </p>
          </div>
        </div>

        <div className="w-px h-8 bg-black/10" />

        <div className="flex items-center gap-2 px-3 py-1.5 bg-amber-50 text-amber-700 text-[11px] font-medium rounded border border-amber-200">
          <span>Install in Desktop panel</span>
          <ArrowRight className="w-3.5 h-3.5" />
        </div>

        {onRefresh && (
          <>
            <div className="w-px h-8 bg-black/10" />
            <button
              onClick={onRefresh}
              disabled={isLoading}
              className="p-1.5 hover:bg-black/5 rounded text-black/30 hover:text-black/60 transition-colors disabled:opacity-50"
              title="Refresh"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          </>
        )}
      </div>
    );
  }

  // 加载中
  if (specs.status === 'loading') {
    return (
      <div className="flex items-center gap-4 w-full h-full px-2">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-gray-100 flex items-center justify-center flex-shrink-0">
            <Loader2 className="w-5 h-5 text-gray-400 animate-spin" />
          </div>
          <div className="min-w-0">
            <p className="text-xs font-medium text-black/50">Loading VM info...</p>
          </div>
        </div>
      </div>
    );
  }

  // 错误状态
  if (specs.status === 'error') {
    return (
      <div className="flex items-center gap-4 w-full h-full px-2">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-red-100 flex items-center justify-center flex-shrink-0">
            <AlertTriangle className="w-5 h-5 text-red-500" />
          </div>
          <div className="min-w-0">
            <p className="text-xs font-semibold text-red-600">Error</p>
            <p className="text-[10px] text-red-500 mt-0.5">{specs.error}</p>
          </div>
        </div>

        {onRefresh && (
          <>
            <div className="w-px h-8 bg-black/10" />
            <button
              onClick={onRefresh}
              className="p-1.5 hover:bg-black/5 rounded text-black/30 hover:text-black/60 transition-colors"
              title="Retry"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          </>
        )}
      </div>
    );
  }

  // 正常状态 (ready)
  const stateColor =
    specs.state === 'running'
      ? 'bg-green-500'
      : specs.state === 'off'
      ? 'bg-gray-400'
      : 'bg-yellow-500';

  const stateText =
    specs.state === 'running'
      ? 'Running'
      : specs.state === 'off'
      ? 'Stopped'
      : 'Unknown';

  return (
    <div className="flex items-center gap-4 w-full h-full px-2">
      {/* VM 名称和状态 */}
      <div className="flex items-center gap-3 min-w-[160px]">
        <div className="w-10 h-10 rounded-lg bg-orange-100 flex items-center justify-center flex-shrink-0">
          <Monitor className="w-5 h-5 text-orange-600" />
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <p className="text-xs font-semibold text-black/80 truncate">{specs.name}</p>
          </div>
          <div className="flex items-center gap-1.5 mt-0.5">
            <div className={`w-1.5 h-1.5 rounded-full ${stateColor}`} />
            <span className="text-[10px] text-black/50">{stateText}</span>
            {specs.uptime && specs.state === 'running' && (
              <>
                <span className="text-[10px] text-black/20">·</span>
                <span className="text-[10px] text-black/40 font-mono">{formatUptime(specs.uptime)}</span>
              </>
            )}
          </div>
        </div>
      </div>

      {/* 分隔线 */}
      <div className="w-px h-8 bg-black/10" />

      {/* CPU */}
      <SpecItem
        icon={<Cpu className="w-3.5 h-3.5 text-blue-500" />}
        label="CPU"
        value={specs.cpuCores > 0 ? `${specs.cpuCores} Cores` : '-'}
        subtext="Virtual"
      />

      {/* 分隔线 */}
      <div className="w-px h-8 bg-black/10" />

      {/* Memory */}
      <SpecItem
        icon={<MemoryStick className="w-3.5 h-3.5 text-purple-500" />}
        label="Memory"
        value={specs.memoryGB > 0 ? `${specs.memoryGB} GB` : '-'}
        subtext="DDR4"
      />

      {/* 分隔线 */}
      <div className="w-px h-8 bg-black/10" />

      {/* Storage */}
      <SpecItem
        icon={<HardDrive className="w-3.5 h-3.5 text-emerald-500" />}
        label="Storage"
        value={specs.storageGB > 0 ? `${specs.storageGB} GB` : '-'}
        subtext={specs.storageUsedGB > 0 ? `${specs.storageUsedGB} GB used` : 'VHDX'}
      />

      {/* 刷新按钮 */}
      {onRefresh && (
        <>
          <div className="w-px h-8 bg-black/10" />
          <button
            onClick={onRefresh}
            disabled={isLoading}
            className="p-1.5 hover:bg-black/5 rounded text-black/30 hover:text-black/60 transition-colors disabled:opacity-50"
            title="Refresh"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </>
      )}
    </div>
  );
}

interface SpecItemProps {
  icon: React.ReactNode;
  label: string;
  value: string;
  subtext: string;
}

function SpecItem({ icon, label, value, subtext }: SpecItemProps) {
  return (
    <div className="flex items-center gap-2 min-w-[100px]">
      <div className="w-8 h-8 rounded bg-black/[0.03] flex items-center justify-center flex-shrink-0">
        {icon}
      </div>
      <div className="min-w-0">
        <p className="text-[9px] font-medium text-black/40 uppercase">{label}</p>
        <p className="text-xs font-semibold text-black/70">{value}</p>
        <p className="text-[9px] text-black/40">{subtext}</p>
      </div>
    </div>
  );
}

function formatUptime(uptime: string): string {
  // PowerShell TimeSpan 格式: "d.hh:mm:ss.fffffff" 或 "hh:mm:ss" 或 "hh:mm:ss.fffffff"
  // 输出: "1d 2h" 或 "2h 30m" 或 "5m"
  try {
    let days = 0;
    let hours = 0;
    let minutes = 0;

    // 先去掉毫秒部分（秒后面的 .xxx）
    let cleanUptime = uptime;
    const colonIdx = uptime.indexOf(':');
    if (colonIdx !== -1) {
      // 找到时间部分后的 . (毫秒分隔符)
      const msPart = uptime.indexOf('.', colonIdx);
      if (msPart !== -1) {
        cleanUptime = uptime.substring(0, msPart);
      }
    }

    // 检查是否有天数部分 (格式: "d.hh:mm:ss")
    const dotIdx = cleanUptime.indexOf('.');
    const firstColonIdx = cleanUptime.indexOf(':');
    
    if (dotIdx !== -1 && (firstColonIdx === -1 || dotIdx < firstColonIdx)) {
      // 有天数: "1.02:30:45"
      days = parseInt(cleanUptime.substring(0, dotIdx), 10) || 0;
      cleanUptime = cleanUptime.substring(dotIdx + 1);
    }

    // 解析时:分:秒
    const timeParts = cleanUptime.split(':');
    hours = parseInt(timeParts[0], 10) || 0;
    minutes = parseInt(timeParts[1], 10) || 0;

    if (days > 0) {
      return `${days}d ${hours}h`;
    } else if (hours > 0) {
      return `${hours}h ${minutes}m`;
    } else {
      return `${minutes}m`;
    }
  } catch {
    return uptime;
  }
}
