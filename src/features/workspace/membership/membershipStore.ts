import { makeAutoObservable } from 'mobx';

export type Membership = {
  id: string;
  title: string;
  originalPrice: string;
  /** USD amount in cents for Stripe Elements (e.g. 2000 = $20.00) */
  price: number;
  features: string[];
  isRecommend?: boolean;
};

class MembershipStore {
  isOpen = false;
  currentMembership: Membership | null = null;
  private _onOpenSettings: (() => void) | null = null;

  constructor() {
    makeAutoObservable(this);
  }

  open = (onOpenSettings?: () => void) => {
    this._onOpenSettings = onOpenSettings ?? null;
    this.currentMembership = null;
    this.isOpen = true;
  };

  close = () => {
    this.isOpen = false;
    this.currentMembership = null;
    this._onOpenSettings = null;
  };

  selectMembership = (membership: Membership) => {
    this.currentMembership = membership;
  };

  back = () => {
    this.currentMembership = null;
  };

  openSettings = () => {
    const cb = this._onOpenSettings;
    this.close();
    cb?.();
  };
}

export const membershipStore = new MembershipStore();
