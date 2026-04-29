import { API_URL, LOCAL_ENGINE_URL } from "../config/runtimeEnv";
import { getOptionalApiBearerToken } from "@/services/apiAuth";
import axios, { AxiosInstance, InternalAxiosRequestConfig } from "axios";

declare module "axios" {
  interface AxiosRequestConfig {
    noAuth?: boolean;
  }
}

export type AppRequestConfig = InternalAxiosRequestConfig;

export const apiInstance = axios.create({
  baseURL: API_URL,
}) as AxiosInstance & { defaults: AppRequestConfig };

/** 请求拦截器 **/
apiInstance.interceptors.request.use(async (config) => {
  config.headers['Content-Type'] = 'application/json';

  const appConfig = config as AppRequestConfig;
  if (appConfig.noAuth) {
    return appConfig;
  }

  const token = getOptionalApiBearerToken();
  if (token) {
    config.headers['Authorization'] = `Bearer ${token}`;
  }

  return appConfig;
});

/** 响应拦截器 **/
apiInstance.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    return Promise.reject(error);
  }
);

/** Local Engine 的请求封装 **/
export const localEngineInstance = axios.create({
  baseURL: LOCAL_ENGINE_URL
});

localEngineInstance.interceptors.request.use(async (config) => {
  config.headers['Content-Type'] = 'application/json';
  return config;
});
