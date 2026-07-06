import React from "react";
import ReactDOM from "react-dom/client";
import { ConfigProvider } from "antd";
import "antd/dist/reset.css";
import App from "./App";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ConfigProvider
      theme={{
        token: {
          colorPrimary: "#1677ff",
          borderRadius: 8,
          colorText: "#111827",
          colorTextSecondary: "#64748B",
          colorBorder: "#E2E8F0",
          boxShadowSecondary: "0 8px 22px rgba(15, 23, 42, 0.06)"
        }
      }}
    >
      <App />
    </ConfigProvider>
  </React.StrictMode>
);
