import { formatRelativeTime } from '@/lib';
import { useAuth } from '@/contexts/AuthContext';
import { FileText, Loader2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { observer } from 'mobx-react-lite';

interface Transaction {
  id: string;
  amount: number;
  type: string;
  description: string;
  reference_id: string | null;
  created_at: string;
  merged_count: number;
}

function formatDescription(tx: Transaction): string {
  if (tx.type === 'usage') {
    const match = tx.description?.match(/Run \[(.+?)\]/);
    if (match) return match[1];
  }
  return tx.description || tx.type;
}

const Transactions = observer(() => {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [isLoadingTransactions, setIsLoadingTransactions] = useState(false);

  useEffect(() => {
    if (!user) return;
    setIsLoadingTransactions(true);
    setTransactions([]);
    setIsLoadingTransactions(false);
  }, [user]);

  return (
    <div className="flex flex-col h-full">
      {isLoadingTransactions ? (
        <div className="flex-1 flex flex-col items-center justify-center text-black/40 dark:text-white/40 gap-3">
          <Loader2 className="w-6 h-6 animate-spin" />
          <p className="text-xs font-medium">{t('settings.transactions.loading')}</p>
        </div>
      ) : transactions.length > 0 ? (
        <div className="flex-1 overflow-y-auto">
          <table className="w-full text-left border-collapse">
            <thead className="bg-[#EDECE9] dark:bg-white/5 sticky top-0 z-10">
              <tr>
                <th className="px-6 py-3 text-[10px] font-bold text-black/50 dark:text-white/50 uppercase tracking-wider">{t('settings.transactions.table.date')}</th>
                <th className="px-6 py-3 text-[10px] font-bold text-black/50 dark:text-white/50 uppercase tracking-wider">{t('settings.transactions.table.description')}</th>
                <th className="px-6 py-3 text-[10px] font-bold text-black/50 dark:text-white/50 uppercase tracking-wider text-right">{t('settings.transactions.table.amount')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-black/5 dark:divide-white/5">
              {transactions.map((tx) => (
                <tr key={tx.id} className="hover:bg-black/[0.02] dark:hover:bg-white/[0.02] transition-colors group">
                  <td className="px-6 py-3.5 text-xs font-medium text-black/60 dark:text-white/60 font-mono whitespace-nowrap">
                    {formatRelativeTime(new Date(tx.created_at).getTime(),{showDate:true,showTime:true})}
                  </td>
                  <td className="px-6 py-3.5">
                    <div className="flex items-center gap-2">
                      <div className={`w-1.5 h-1.5 min-w-1.5 min-h-1.5 rounded-full ${tx.amount > 0 ? 'bg-green-500' : 'bg-orange-500'}`}></div>
                      <span className="text-sm font-medium text-black/80 dark:text-white/80">{formatDescription(tx)}</span>
                      {tx.merged_count > 1 && (
                        <span className="text-[11px] font-mono text-orange-500 dark:text-white/30">×{tx.merged_count}</span>
                      )}
                    </div>
                  </td>
                  <td className={`px-6 py-3.5 text-sm font-bold font-mono text-right ${tx.amount > 0 ? 'text-green-600 dark:text-green-400' : 'text-black/80 dark:text-white/80'}`}>
                    {tx.amount > 0 ? '+' : ''}{tx.amount}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="flex-1 flex flex-col items-center justify-center text-black/40 dark:text-white/40 gap-3 px-6 text-center">
          <FileText className="w-8 h-8 opacity-50" />
          <p className="text-sm font-medium">离线发行版不连接云端账务，无交易记录。</p>
        </div>
      )}
    </div>
  );
});

export default Transactions;
