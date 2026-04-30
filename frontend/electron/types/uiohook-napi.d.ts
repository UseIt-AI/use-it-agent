declare module 'uiohook-napi' {
  export const uIOhook: {
    start: () => void;
    stop: () => void;
    on: (event: string, handler: (e: any) => void) => void;
  };

  export enum UiohookKey {
    CtrlL = 29,
    CtrlR = 3613,
    ShiftL = 42,
    ShiftR = 54,
    AltL = 56,
    AltR = 3640,
    MetaL = 3675,
    MetaR = 3676,
  }

  export type UiohookMouseEvent = { x: number; y: number; button: number };
  export type UiohookKeyboardEvent = { keycode: number };
  export type UiohookWheelEvent = { x: number; y: number; rotation: number };
}




