"use client";

import * as ToastPrimitive from "@radix-ui/react-toast";
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

type ToastVariant = "success" | "error" | "info";

type ToastMessage = {
  id: string;
  title: string;
  description?: string;
  variant: ToastVariant;
};

type ToastContextValue = {
  notify: (payload: Omit<ToastMessage, "id">) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastMessage[]>([]);

  const notify = useCallback((payload: Omit<ToastMessage, "id">) => {
    const id = crypto.randomUUID();
    setItems((current) => [...current, { id, ...payload }]);

    window.setTimeout(() => {
      setItems((current) => current.filter((item) => item.id !== id));
    }, 3800);
  }, []);

  const context = useMemo(() => ({ notify }), [notify]);

  return (
    <ToastContext.Provider value={context}>
      <ToastPrimitive.Provider swipeDirection="right" duration={3500}>
        {children}
        {items.map((item) => (
          <ToastPrimitive.Root
            key={item.id}
            open
            className={
              item.variant === "error"
                ? "group pointer-events-auto rounded-lg border border-danger bg-card px-4 py-3 shadow-lg"
                : item.variant === "success"
                  ? "group pointer-events-auto rounded-lg border border-accent bg-card px-4 py-3 shadow-lg"
                  : "group pointer-events-auto rounded-lg border border-secondary bg-card px-4 py-3 shadow-lg"
            }
          >
            <ToastPrimitive.Title className="text-sm font-semibold text-white">
              {item.title}
            </ToastPrimitive.Title>
            {item.description ? (
              <ToastPrimitive.Description className="mt-1 text-xs text-slate-300">
                {item.description}
              </ToastPrimitive.Description>
            ) : null}
          </ToastPrimitive.Root>
        ))}
        <ToastPrimitive.Viewport className="fixed bottom-4 right-4 z-[100] flex w-80 flex-col gap-2 outline-none" />
      </ToastPrimitive.Provider>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used inside ToastProvider");
  }
  return context;
}
