import "axios";

declare module "axios" {
  export interface AxiosRequestConfig<D = any> {
    /** 标记该请求不需要携带 accessToken */
    noAuth?: boolean;
  }

  export interface InternalAxiosRequestConfig<D = any> {
    /** 标记该请求不需要携带 accessToken */
    noAuth?: boolean;
  }
}

