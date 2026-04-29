import { Notification, Spin } from "@douyinfe/semi-ui";
import { CheckIcon } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { observer } from "mobx-react-lite";
import { Membership } from "./MembershipModal";
import { loadStripe } from '@stripe/stripe-js';
import {
  PaymentElement,
  Elements,
  useStripe,
  useElements,
} from '@stripe/react-stripe-js';
import { useAuth } from "@/shared";
import api from "@/api";

const stripePromise = loadStripe(import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY, {
  developerTools: {
    assistant: {
      enabled: import.meta.env.DEV,
    },
  },
});

export const Payment = observer(({ membership, onSuccess }: { membership: Membership; onSuccess: () => void }) => {
  const { i18n } = useTranslation();

  const options = {
    mode: 'subscription' as const,
    amount: Number(membership.price)*100,
    currency: 'usd',
    paymentMethodTypes: ['card','link'],
    locale: i18n.language as 'en' | 'zh',
  };

  return <Elements stripe={stripePromise} options={options}>
    <PaymentForm membership={membership} onSuccess={onSuccess} />
  </Elements>;
});

const PaymentForm = observer(({ membership, onSuccess }: { membership: Membership; onSuccess: () => void }) => {
  const { t } = useTranslation();
  const { refreshProfile } = useAuth();
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | undefined>();
  const stripe = useStripe();
  const elements = useElements();

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!stripe || !elements) {
      return;
    }
    setLoading(true)
    // Trigger form validation and wallet collection
    const { error: submitError } = await elements.submit();
    if (submitError) {
      setLoading(false)
      setErrorMessage(submitError.message);
      return;
    }

    try {
      const data = await api.subscription.createIntent(membership.id);
      const { client_secret: clientSecret } = data;

      const { error } = await stripe.confirmPayment({
        elements,
        clientSecret,
        redirect: 'if_required',
      });
      if (error) {
        setErrorMessage(error.message);
        return;
      }
      Notification.success({ content: t('membership.subscribe_success') });
      onSuccess();
      setTimeout(() => { refreshProfile(); }, 2000);
    } catch (err: any) {
      const msg = err?.response?.data?.message ?? err?.message ?? t('membership.payment.error');
      setErrorMessage(msg);
    } finally {
      setLoading(false);
    }
  };

  return <div className="px-10 pb-8 pt-5 bg-[#FAF9F6] dark:bg-[#1A1A1A] z-10 rounded grid grid-cols-2 gap-10">
          <div className="flex-1">
          <PaymentElement />
          {errorMessage && <div>{errorMessage}</div>}
          </div>
          <div className="border rounded-lg p-8 w-[400px] shadow-sm">
              <div className="text-2xl font-semibold">{membership.title}</div>
              <div className="mt-5">
                  <div className="text-lg mb-2">{t('membership.payment.popularFeatures')}</div>
                  <ul className="mb-5">
                      {membership.features.map((feature, index) => (
                          <li className="flex items-center gap-3 pb-2" key={index}><CheckIcon className="size-4"/> {feature}</li>
                      ))}
                  </ul>
                  <div className="grid grid-cols-2 border-t pt-5 mx-auto text-[16px] gap-y-2">
                      <div className="text-gray-500">{t('membership.payment.subscriptionType')}</div>
                      <div className="text-right text-gray-500">{t('membership.payment.monthly')}</div>
                      <div className="text-gray-500">{t('membership.payment.originalPrice')}</div>
                      <div className="text-right text-gray-500 line-through">${membership.originalPrice}</div>
                      <div className="font-bold mt-3">{t('membership.payment.totalDue')}</div>
                      <div className="font-bold text-right mt-3">${(membership.price/100).toFixed(2)}</div>
                  </div>
                  <div className="mt-5">
                      <Spin spinning={loading}>
                        <div className="p-4 w-full text-center text-white font-bold bg-black rounded-lg cursor-pointer" onClick={handleSubmit}>
                          {t('membership.payment.subscribeButton')}
                        </div>
                      </Spin>
                  </div>
              </div>
          </div>
        </div>;
});
