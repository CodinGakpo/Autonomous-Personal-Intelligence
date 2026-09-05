import { StrictMode } from "react"
import { createRoot } from "react-dom/client"

import App from "@/App"
import { ThemeProvider } from "@/components/ThemeProvider"
import "@/index.css"

const root = document.getElementById("root")
if (!root) throw new Error("Root element not found")

createRoot(root).render(
  <StrictMode>
    <ThemeProvider defaultTheme="dark" storageKey="vite-ui-theme">
      <App />
    </ThemeProvider>
  </StrictMode>,
)
