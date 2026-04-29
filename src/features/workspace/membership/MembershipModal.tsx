import { Spin } from "@douyinfe/semi-ui";
import { Modal } from "@/components/Modal";
import clsx from "clsx";
import { CheckIcon, ChevronLeft } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Payment } from "./MembershipPayment";
import { useAuth } from "@/shared";
import { observer } from "mobx-react-lite";
import { membershipStore, Membership } from "./membershipStore";

export type { Membership };

export const MembershipModal = observer(() => {
  const { t } = useTranslation();
  const { isOpen, currentMembership } = membershipStore;

  return (
    <Modal
      open={isOpen}
      onCancel={membershipStore.close}
      onConfirm={membershipStore.close}
      footer=""
      title={
        currentMembership ? (
          <div
            className="text-lg font-bold flex items-center gap-2 cursor-pointer"
            onClick={membershipStore.back}
          >
            <ChevronLeft /> {t('membership.backToPlan')}
          </div>
        ) : ""
      }
    >
      <div className="relative pb-2 w-[900px]">
        {currentMembership ? (
          <Payment membership={currentMembership} onSuccess={membershipStore.close} />
        ) : (
          <div className="px-5">
            <div className="text-center text-2xl font-bold mb-10 pt-8">{t('membership.selectPlan')}</div>
            <div className="grid grid-cols-3 gap-5">
              {memberships(t).map((membership) => (
                <MembershipCard key={membership.id} membership={membership} />
              ))}
            </div>
            <div className="flex justify-center mt-7">
              {t('membership.manageSubscription')}{' '}
              <span
                className="ml-1 underline cursor-pointer"
                onClick={membershipStore.openSettings}
              >
                {t('membership.settings')}
              </span>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
});

const memberships = (t: ReturnType<typeof useTranslation>['t']): Membership[] => [
  {
    id: 'free',
    title: t('membership.plans.free.title'),
    originalPrice: "0.00",
    price: 0,
    features: t('membership.plans.free.features', { returnObjects: true }) as string[],
  },
  {
    id: 'pro',
    title: t('membership.plans.pro.title'),
    originalPrice: "59.00",
    price: 2000,
    features: t('membership.plans.pro.features', { returnObjects: true }) as string[],
    isRecommend: true,
  },
  {
    id: 'enterprise',
    title: t('membership.plans.enterprise.title'),
    originalPrice: "159.00",
    price: 6000,
    features: t('membership.plans.enterprise.features', { returnObjects: true }) as string[],
  },
];

type MembershipCardProps = {
  membership: Membership;
};

function MembershipCard({ membership }: MembershipCardProps) {
  const { title, originalPrice, price, features, isRecommend } = membership;
  const { profile } = useAuth();
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);

  const subscribed = useMemo(
    () => profile?.subscription_tier === membership.id,
    [profile, membership]
  );

  const isDisabled = useMemo(() => {
    if (membership.id === 'free') return true;
    if (subscribed) return true;
    if (profile?.subscription_tier === 'enterprise') return true;
    return false;
  }, [membership.id, subscribed, profile]);

  const handleSubscribe = () => {
    if (loading || isDisabled) return;
    setLoading(true);
    setTimeout(() => {
      setLoading(false);
      membershipStore.selectMembership(membership);
    }, 1500);
  };

  return (
    <div
      className={clsx(
        "rounded-lg relative shadow-2xl bg-white p-5 pb-10 border",
        isRecommend ? "border-2 border-black" : "border border-black/10"
      )}
    >
      {isRecommend && (
        <div className="absolute top-0 right-0 bg-black text-white px-2 py-1 text-xs rounded-bl-lg">
          {t('membership.recommend')}
        </div>
      )}
      <div className="text-xl font-bold mb-5">{title}</div>
      <div className="line-through">${originalPrice}</div>
      <div className="mb-10">
        <span className="text-4xl font-bold">${(price / 100).toFixed(2)}</span>{' '}
        {t('membership.perMonth')}
      </div>
      <Spin spinning={loading}>
        <div
          className={clsx(
            "rounded-lg border border-gray-200 h-11 flex justify-center items-center",
            isDisabled ? 'bg-black/5 cursor-not-allowed' : 'bg-black text-white cursor-pointer'
          )}
          onClick={handleSubscribe}
        >
          {subscribed ? t('membership.currentPlan') : t('membership.subscribe')}
        </div>
      </Spin>
      <div className="text-[12px] mt-10 mb-1 text-gray-400">{t('membership.validity')}</div>
      <div className="font-semibold text-md flex flex-col gap-2">
        {features.map((feature) => (
          <div key={feature} className="flex gap-1 items-center">
            <CheckIcon className="size-4" /> {feature}
          </div>
        ))}
      </div>
    </div>
  );
}
