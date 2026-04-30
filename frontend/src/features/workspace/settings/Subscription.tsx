import api from '@/api';
import { formatDate, formatDisplayDate, sleep } from '@/lib';
import { useAuth } from '@/shared';
import { Notification, Spin } from '@douyinfe/semi-ui';
import clsx from 'clsx';
import {
  Loader2,
  FileText,
  CircleDollarSign,
  ShieldQuestion
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { observer } from 'mobx-react-lite';

const Subscription = observer(() => {
  const { t } = useTranslation();
  const { profile } = useAuth();
  const [subscriptions, setSubscriptions] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [loadingUnsubscribe, setLoadingUnsubscribe] = useState(false);
  const credits = Number(profile?.credits_balance ?? 0);

  useEffect(() => {
    setIsLoading(true);
    api.subscription.invoices().then(data => {
      setSubscriptions(data.invoices);
    }).finally(() => {
      setIsLoading(false);
    })
  }, [])

  const handleUnsubscribe = async () => {
    setLoadingUnsubscribe(true)
    await sleep(2000);
    api.subscription.cancel().then(data => {
      Notification.success({content:t('settings.subscription.cancel_success')})
    }).catch(e => {
      Notification.warning({content:t('settings.subscription.cancel_failed')})
      console.log("subscription cancel_failed:",e)
    }).finally(() => {
      setLoadingUnsubscribe(false);
    })
  }

  return <div className="flex flex-col h-full">
    <div className='rounded border border-gray-300 m-3 p-4 shadow-md'>
      <div className='flex justify-between border-b border-gray-400 pb-4'>
        <div className='font-bold'>{t('settings.subscription.credits')}</div>
        <div className='flex items-center gap-1 text-yellow-600'><CircleDollarSign className='size-4' /> {credits}</div>
      </div>
      <div className='flex justify-between pt-4'>
        <div className='font-bold'>{t('settings.subscription.plan')}</div>
        <div className='flex items-center gap-1 capitalize'>{profile?.subscription_tier}</div>
      </div>
      <div className='flex justify-between pt-4'>
        <div className='font-bold'>{t('settings.subscription.cycle')}</div>
        <div className='flex items-center gap-1'>{profile?.current_period_end ? "Monthly" : "-"} </div>
      </div>
      <div className='flex justify-between pt-4'>
        <div className='font-bold'>{t('settings.subscription.nextPaymentDate')}</div>
        <div className='flex items-center gap-1'>{profile?.current_period_end ? formatDate(profile?.current_period_end) : "-"}</div>
      </div>
      <div className='flex justify-between pt-4'>
        <div className='font-bold'>{t('settings.subscription.actions')}</div>
        <Spin spinning={loadingUnsubscribe}>
          <button className='flex items-center gap-1 underline cursor-pointer' onClick={handleUnsubscribe}>{t('settings.subscription.unsubscribe')}</button>
        </Spin>
      </div>
    </div>
    <div className='text-[12px] text-gray-500 underline mr-3 mb-3 cursor-pointer flex items-center justify-end gap-1'><ShieldQuestion className='size-4' /> {t('settings.subscription.rules')}</div>
    {isLoading ? (
      <div className="flex-1 flex flex-col items-center justify-center text-black/40 dark:text-white/40 gap-3">
        <Loader2 className="w-6 h-6 animate-spin" />
        <p className="text-xs font-medium">{t('settings.subscription.loading')}</p>
      </div>
    ) : subscriptions.length > 0 ? (
      <div className="flex-1 overflow-y-auto">

        <table className="w-full text-left border-collapse table-fixed">
          <thead className="bg-[#EDECE9] dark:bg-white/5 sticky top-0 z-10">
            <tr>
              <th className="px-6 py-3 text-[10px] font-bold text-black/50 dark:text-white/50 uppercase tracking-wider w-[220px]">{t('settings.subscription.table.invoice_id')}</th>
              <th className="px-6 py-3 text-[10px] font-bold text-black/50 dark:text-white/50 uppercase tracking-wider w-[200px]">{t('settings.subscription.table.paid_date')}</th>
              <th className="px-6 py-3 text-[10px] font-bold text-black/50 dark:text-white/50 uppercase tracking-wider">{t('settings.subscription.table.amount')}</th>
              <th className="px-6 py-3 text-[10px] font-bold text-black/50 dark:text-white/50 uppercase tracking-wider">{t('settings.subscription.table.status')}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-black/5 dark:divide-white/5">
            {subscriptions.map((tx) => (
              <tr key={tx.invoice_id} className="hover:bg-black/[0.02] dark:hover:bg-white/[0.02] transition-colors group">
                <td className="px-6 py-3.5 text-xs font-medium text-black/60 dark:text-white/60 font-mono whitespace-nowrap w-[220px]">
                  {tx.invoice_id}
                </td>
                <td className={`px-6 py-3.5 text-sm font-mono w-[200px]`}>
                  {formatDate(tx.paid_at)}
                </td>
                <td className="px-6 py-3.5">
                  ${(tx.amount/100).toFixed(2)}
                </td>
                <td className={clsx(`px-6 py-3.5 text-sm font-bold font-mono`,{"text-green-500":tx.final_status === "success"})}>
                  {t(`settings.subscription.${tx.final_status === "success" ? "debit_success" : "debit_fail"}`)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    ) : (
      <div className="flex-1 flex flex-col items-center justify-center text-black/40 dark:text-white/40 gap-3 p-8">
        <div className="w-12 h-12 rounded-full bg-black/5 dark:bg-white/5 flex items-center justify-center">
          <FileText className="w-6 h-6 opacity-50" />
        </div>
        <p className="text-sm font-medium">{t('settings.subscription.noData')}</p>
      </div>
    )}
  </div>
});

export default Subscription