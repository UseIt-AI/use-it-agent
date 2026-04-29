import { apiInstance } from "./core";

/** 发起订阅请求 */
export const createIntent = async (planId: string) => {
    const response = await apiInstance.post(`/api/v1/billing/create-intent`, {
      plan_id: planId,
    }, { noAuth: true });
    return response.data;
  };

  /** 获取扣款记录 */
export const invoices = async () => {
  const response = await apiInstance.get(`/api/v1/billing/invoices`, { noAuth: true });
  return response.data;
}

/** 取消订阅 */
export const cancel = async () => {
  const response = await apiInstance.post(`/api/v1/billing/cancel`,{ immediate: true }, { noAuth: true });
  return response.data;
}
