
import { toJS } from "mobx"
import ProjectStore from "./projectStore"
import AuthStore from "./authStore"

export class RootStore {
  projectStore: ProjectStore
  authStore: AuthStore

  constructor() {
    this.projectStore = new ProjectStore(this)
    this.projectStore.initialize()
    this.authStore = new AuthStore(this)
  }
}

export const rootStore = new RootStore()

if (process.env.NODE_ENV === "development") {
  (window as any).store = {
    raw: rootStore,
    js: () => toJS(rootStore),
  };
}
