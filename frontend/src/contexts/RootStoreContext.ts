import { createContext, useContext } from "react"
import type { ReactNode } from "react"
import { createElement } from "react"
import { rootStore, RootStore } from "@/stores/rootStore"

const StoreContext = createContext<RootStore>(rootStore)

export const StoreProvider = ({ children }: { children: ReactNode }) =>
  createElement(StoreContext.Provider, { value: rootStore }, children)

export const useStore = () => useContext(StoreContext)