import "./App.css";
import { useState } from "react";
import { AppSidebar } from "@/components/app-sidebar";
import { BackendStatus } from "@/components/backend-status";
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { Separator } from "@/components/ui/separator";

import Chat from "@/views/Chat";
import Graph from "@/views/Graph";
import Library from "@/views/Library";
import Links from "@/views/Links";
import Search from "@/views/Search";
import Settings from "@/views/Settings";
import History from "@/views/History";
import Theories from "@/views/Theories";

const views = {
  library: Library,
  search: Search,
  graph: Graph,
  links: Links,
  chat: Chat,
  history: History,
  settings: Settings,
  theories: Theories,
};

const titles = {
  library: "Library",
  search: "Search",
  graph: "Graph",
  links: "Links",
  chat: "Chat",
  history: "History",
  settings: "Settings",
  theories: "Theories",
};

export default function App() {
  const [activeView, setActiveView] = useState("chat");

  const ActiveView = views[activeView];

  return (
    <SidebarProvider>
      <AppSidebar activeView={activeView} onViewChange={setActiveView} />

      <SidebarInset>
        <header className="flex h-14 shrink-0 items-center gap-3 border-b px-4">
          <SidebarTrigger />
          <Separator orientation="vertical" className="h-5" />
          <h1 className="text-sm font-semibold">{titles[activeView]}</h1>
          <div className="ml-auto">
            <BackendStatus />
          </div>
        </header>

        <main className="flex-1 overflow-auto p-6">
          {activeView === "history" ? (
            <History onOpenChat={() => setActiveView("chat")} />
          ) : (
            <ActiveView />
          )}
        </main>
      </SidebarInset>
    </SidebarProvider>
  );
}
