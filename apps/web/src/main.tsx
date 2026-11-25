import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Unauthenticated } from "./api";
import { App } from "./App";
import { AuthProvider } from "./auth";
import "./styles.css";
import { applyTheme, readTheme } from "./theme";

applyTheme(readTheme());

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: (count, error) => !(error instanceof Unauthenticated) && count < 2, staleTime: 10_000 },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>,
);
