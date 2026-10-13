"use client";

import { CurrencyProvider } from "@/contexts/CurrencyContext";
import { AuthProvider } from "@/contexts";
import { ToastProvider } from "@/components/ui";
import type { ReactNode } from "react";

interface ProvidersProps {
  children: ReactNode;
}

export function Providers({ children }: ProvidersProps) {
  return (
    <AuthProvider>
      <CurrencyProvider>
        <ToastProvider>{children}</ToastProvider>
      </CurrencyProvider>
    </AuthProvider>
  );
}

export default Providers;
